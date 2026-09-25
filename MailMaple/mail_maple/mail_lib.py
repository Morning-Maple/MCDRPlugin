"""
mail_lib.py — 配置管理 / 真人注册表(反假人) / 工具 / 命令注册中枢
"""
import json
import os
import re
import tempfile
import threading
import time
import uuid as uuidlib
from datetime import datetime
from typing import Dict, List, Optional

import mcdreforged as mcdr
from mcdreforged.api.command import Literal, Text, QuotableText, GreedyText, Integer
from mcdreforged.api.rtext import RText, RTextList, RColor, RAction
import minecraft_data_api as api

from . import config as config_module
from .config import MailSettings, MailRegistry, PlayerMailBox, PlayerData

TAG = "§b[MailMaple] §r"

# ---------------- 存储路径 (相对插件数据文件夹 config/mail_maple/) ----------------
SETTINGS_FILE = "MailMaple.json"      # 仅设置项
DATA_DIR = "mail_data"                # 运行数据文件夹 (与设置文件同级)
PLAYERS_DIR = "players"               # mail_data/players/ 分片目录
REGISTRY_FILE = "registry.json"       # mail_data/registry.json

# ============================================================
# 全局状态 (内存)
# ============================================================

config: MailSettings = MailSettings.get_default()
registry: MailRegistry = MailRegistry.get_default()
# 各玩家活跃收件箱: uuid -> PlayerMailBox
mailboxes: Dict[str, PlayerMailBox] = {}
# 各玩家过期邮件: uuid -> List[MailItem]
expired_boxes: Dict[str, list] = {}
plugin_server: mcdr.PluginServerInterface = None

# 在线玩家集合 (运行时维护, 供命令补全即时返回, 避免阻塞查询)
online_players: set = set()

# 全局锁 (可重入): 保护 mailboxes / expired_boxes / registry 的 check-then-act 复合操作。
# 仅包裹短内存操作; 阻塞操作 (api 查询 / server.execute / 磁盘 I/O) 一律在锁外执行,
# 避免长持锁降低并发。单锁可重入, 不存在多锁交叉, 因此不会死锁。
_lock = threading.RLock()


def lock():
    """返回全局可重入锁, 供命令回调包裹 check-then-act 内存临界区。"""
    return _lock


# ============================================================
# 存储层: 路径工具 / 原子写 / 分片读写
# ============================================================

def _data_folder() -> str:
    """插件数据文件夹绝对路径 (config/mail_maple)"""
    return plugin_server.get_data_folder()


def _data_dir() -> str:
    return os.path.join(_data_folder(), DATA_DIR)


def _players_dir() -> str:
    return os.path.join(_data_dir(), PLAYERS_DIR)


def _registry_path() -> str:
    return os.path.join(_data_dir(), REGISTRY_FILE)


def _shard_path(player_uuid: str) -> str:
    return os.path.join(_players_dir(), player_uuid + ".json")


def _read_json(path: str):
    """读 JSON; 文件不存在或损坏时返回 None"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _atomic_write_json(path: str, data) -> None:
    """原子写 JSON: 先写同目录临时文件并 fsync, 再 os.replace 覆盖目标。

    保证任何时刻目标文件要么是旧的完整内容、要么是新的完整内容,
    不会出现写到一半的半截文件。
    """
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _delete_shard(player_uuid: str) -> None:
    """删除某玩家分片文件 (数据已空时)"""
    try:
        os.remove(_shard_path(player_uuid))
    except OSError:
        pass


# ---------------- 保存 (按需, 只写受影响的部分) ----------------

def save_settings():
    """保存设置项 (仅设置变更命令调用, 如 black add/remove)"""
    if plugin_server is not None:
        plugin_server.save_config_simple(config, SETTINGS_FILE)


def save_registry():
    """保存全局注册表 (邮件编号 + 真人注册表), 原子写"""
    if plugin_server is not None:
        _atomic_write_json(_registry_path(), registry.serialize())


def save_player(player_uuid: str):
    """保存单个玩家分片 (活跃 + 过期), 原子写; 数据全空则删除分片文件"""
    if plugin_server is None:
        return
    box = mailboxes.get(player_uuid)
    expired = expired_boxes.get(player_uuid) or []
    mails = box.mails if box is not None else []
    if not mails and not expired:
        _delete_shard(player_uuid)
        return
    name = box.player_name if box is not None else registry.known_players.get(player_uuid, "")
    data = PlayerData(player_name=name, mails=mails, expired=expired)
    _atomic_write_json(_shard_path(player_uuid), data.serialize())


def save_players(player_uuids) -> None:
    """批量保存多个玩家分片 (自动去重)"""
    for u in set(player_uuids):
        save_player(u)


def load():
    """加载设置 + 注册表 + 所有玩家分片到内存 (缺失用默认值)"""
    global config, registry, mailboxes, expired_boxes
    config = plugin_server.load_config_simple(SETTINGS_FILE, target_class=MailSettings)

    reg_raw = _read_json(_registry_path())
    if reg_raw is None:
        registry = MailRegistry.get_default()
        save_registry()  # 首次创建
    else:
        try:
            registry = MailRegistry.deserialize(reg_raw)
        except Exception as e:  # noqa: BLE001 - 损坏时回退默认, 避免整插件加载失败
            _log("§eregistry.json 解析失败, 使用默认值: {}".format(e))
            registry = MailRegistry.get_default()

    mailboxes = {}
    expired_boxes = {}
    players_dir = _players_dir()
    os.makedirs(players_dir, exist_ok=True)
    for fname in os.listdir(players_dir):
        if not fname.endswith(".json") or fname.startswith(".tmp_"):
            continue
        player_uuid = fname[:-len(".json")]
        raw = _read_json(os.path.join(players_dir, fname))
        if raw is None:
            _log("§e玩家分片损坏, 已跳过: {}".format(fname))
            continue
        try:
            pdata = PlayerData.deserialize(raw)
        except Exception as e:  # noqa: BLE001
            _log("§e玩家分片解析失败 {}: {}".format(fname, e))
            continue
        if pdata.mails:
            mailboxes[player_uuid] = PlayerMailBox(player_name=pdata.player_name, mails=pdata.mails)
        if pdata.expired:
            expired_boxes[player_uuid] = pdata.expired


# ============================================================
# 命令前缀 / 权限 / 帮助
# ============================================================

def cmd(name: str) -> str:
    """根据 use_maple_prefix 生成完整命令, 如 'mail' -> '!!mmail' 或 '!!mail'"""
    prefix = "!!m" if config.use_maple_prefix else "!!"
    return prefix + name


def get_perm(name: str) -> int:
    """获取命令所需权限等级"""
    return config.perm.get(name, 0)


def get_click_action() -> RAction:
    """根据配置返回可点击文本的点击行为 (suggest_command / run_command)"""
    return RAction.suggest_command if config.use_suggest_command else RAction.run_command


def get_help_msg(source: mcdr.CommandSource = None) -> List[str]:
    """生成帮助信息 (文案见 config.HELP_LINES, 按当前前缀填充)。

    若给出 source, 则按其 MCDR 权限过滤: 仅展示其有权使用的命令行
    (权限键为 None 的标题/页脚始终展示)。
    """
    base = cmd("mail")
    lines = []
    for perm_key, text in config_module.HELP_LINES:
        if source is not None and perm_key is not None \
                and not source.has_permission(get_perm(perm_key)):
            continue
        lines.append(text.format(base=base))
    return lines


def display_help(source: mcdr.CommandSource):
    for line in get_help_msg(source):
        source.reply(line)


def reload_cmd(source: mcdr.CommandSource):
    source.reply(TAG + "§2正在重载配置文件……")
    load()
    seed_known_players_from_usercache()
    source.reply(TAG + "§a重载完成! §7(当前过期设置: §e{}§7)".format(describe_expire()))


def reset_data():
    """清空所有运行数据 (注册表 + 所有玩家邮件分片), 恢复为刚创建状态。

    仅清运行数据, 不触碰设置文件 MailMaple.json (perm/容量/过期等设置保留)。
    """
    global registry, mailboxes, expired_boxes
    registry = MailRegistry.get_default()
    mailboxes = {}
    expired_boxes = {}
    # 删除所有玩家分片文件
    players_dir = _players_dir()
    if os.path.isdir(players_dir):
        for fname in os.listdir(players_dir):
            path = os.path.join(players_dir, fname)
            try:
                os.remove(path)
            except OSError:
                pass
    # 重写注册表为默认 (空)
    save_registry()


@mcdr.new_thread("MailMaple-reset")
def reset_confirm(source: mcdr.CommandSource):
    """!!mail reset confirm — 二次确认后执行清空"""
    reset_data()
    source.reply(TAG + "§a已清空所有邮件数据, 插件恢复为初始状态")
    _log("管理员 {} 清空了所有邮件数据".format(
        source.player if getattr(source, "is_player", False) else "控制台"
    ))


def reset_prompt(source: mcdr.CommandSource):
    """!!mail reset — 二次确认提示"""
    base = cmd("mail")
    click = get_click_action()
    confirm = RText("§c[点击确认清空]", RColor.red)
    confirm.set_click_event(click, "{} reset confirm".format(base))
    confirm.set_hover_text("§c确认清空所有邮件数据")
    source.reply(RTextList(
        TAG,
        "§c即将清空所有邮件数据 (注册表 + 所有玩家邮件), 此操作不可撤销! ",
        confirm,
    ))
    source.reply(TAG + "§7也可输入 §a{} reset confirm §7确认".format(base))


def describe_expire() -> str:
    """把 mail_expire_seconds 描述成人类可读的过期设置文本"""
    seconds = config.mail_expire_seconds
    if seconds <= 0:
        return "永不过期"
    if seconds % 86400 == 0:
        return "{} 天后过期".format(seconds // 86400)
    if seconds % 3600 == 0:
        return "{} 小时后过期".format(seconds // 3600)
    if seconds % 60 == 0:
        return "{} 分钟后过期".format(seconds // 60)
    return "{} 秒后过期".format(seconds)


# ============================================================
# 真人识别 / 反假人
# ============================================================

def name_in_list(name: str, names: list) -> bool:
    """名字是否在给定名单中 (按 ignore_case 配置决定是否忽略大小写)"""
    if config.ignore_case:
        lower = name.lower()
        return any(str(n).lower() == lower for n in names)
    return name in names


def remove_name_from(names: list, name: str):
    """从名单中移除指定名字 (按 ignore_case 配置, 原地修改)"""
    if config.ignore_case:
        lower = name.lower()
        names[:] = [n for n in names if str(n).lower() != lower]
    else:
        names[:] = [n for n in names if n != name]


def matches_blacklist_pattern(name: str) -> bool:
    """名字是否命中任一假人正则 (bot_name_blacklist)"""
    flags = re.IGNORECASE if config.ignore_case else 0
    for pattern in config.bot_name_blacklist:
        try:
            if re.search(pattern, name, flags):
                return True
        except re.error:
            continue
    return False


def classify_player(name: str, player_uuid: Optional[str]) -> str:
    """判定玩家是 'real' (真人) 还是 'bot' (假人/排除)。

    优先级: 精确黑名单 > 正则黑名单 > UUID 版本号 > 默认真人
    注意: 手动 mail user add 进注册表的玩家不受此判定移除, 仅影响"自动登记"。
    """
    if name_in_list(name, config.bot_list):
        return "bot"
    if matches_blacklist_pattern(name):
        return "bot"
    if config.detect_bot_by_uuid_version and player_uuid:
        try:
            version = uuidlib.UUID(player_uuid).version
            if version == 4:
                return "real"
            if version == 3:
                return "bot"
        except (ValueError, AttributeError):
            pass
    return "real"


def resolve_player_uuid(name: str) -> Optional[str]:
    """在真人注册表里按名字 (忽略大小写) 反查 UUID"""
    lower = name.lower()
    for u, n in registry.known_players.items():
        if n.lower() == lower:
            return u
    return None


def get_mailbox(player_uuid: str, player_name: str = "") -> PlayerMailBox:
    """获取 (或创建) 指定 UUID 的邮箱"""
    box = mailboxes.get(player_uuid)
    if box is None:
        box = PlayerMailBox(player_name=player_name)
        mailboxes[player_uuid] = box
    elif player_name and box.player_name != player_name:
        box.player_name = player_name
    return box


# ============================================================
# 过期邮件: 判定 / 扫描移动 / 查找
# ============================================================

def is_mail_expired(mail) -> bool:
    """按 mail_expire_seconds 判断邮件是否过期 (<=0 永不过期, N=N秒后)。

    注意: 0 与负数都视为"关闭过期", 只有正数秒数才启用过期。
    """
    seconds = config.mail_expire_seconds
    if seconds <= 0:
        return False
    return time.time() >= mail.time + seconds


def mailbox_full(box: PlayerMailBox) -> bool:
    """邮箱是否已达上限 (default_mail_max, 0=不限制)"""
    cap = config.default_mail_max
    return cap > 0 and len(box.mails) >= cap


def get_expired_box(player_uuid: str) -> list:
    """获取 (或创建) 指定 UUID 的过期邮件列表"""
    return expired_boxes.setdefault(player_uuid, [])


def scan_box_expired(player_uuid: str) -> int:
    """扫描指定邮箱, 把已过期邮件从活跃收件箱移入过期列表; 返回移动数量"""
    with _lock:
        box = mailboxes.get(player_uuid)
        if box is None or not box.mails:
            return 0
        moved = 0
        remaining = []
        for mail in box.mails:
            if is_mail_expired(mail):
                mail.is_expired = True
                get_expired_box(player_uuid).append(mail)
                moved += 1
            else:
                remaining.append(mail)
        if moved > 0:
            box.mails = remaining
    if moved > 0:
        save_player(player_uuid)  # 磁盘 I/O 放锁外
    return moved


def scan_all_expired() -> int:
    """扫描所有邮箱的过期邮件; 返回移动总数"""
    total = 0
    for player_uuid in list(mailboxes.keys()):
        total += scan_box_expired(player_uuid)
    return total


def find_expired_mail(mail_id: str):
    """在所有过期列表里按 id 查找, 返回 (uuid, mail) 或 (None, None)"""
    for player_uuid, mails in expired_boxes.items():
        for mail in mails:
            if mail.id == mail_id:
                return player_uuid, mail
    return None, None


def remove_expired_mail(player_uuid: str, mail) -> None:
    """从过期列表移除一封邮件"""
    mails = expired_boxes.get(player_uuid)
    if mails and mail in mails:
        mails.remove(mail)


def seed_known_players_from_usercache():
    """加载时扫描服务端 usercache.json 预填已知真人 (过滤假人)"""
    path = config.usercache_path
    if not path or not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        _log("§e读取 usercache.json 失败: {}".format(e))
        return
    if not isinstance(data, list):
        return
    added = 0
    for entry in data:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        u = entry.get("uuid")
        if not name or not u:
            continue
        if classify_player(name, u) == "bot":
            continue
        if u not in registry.known_players:
            registry.known_players[u] = name
            added += 1
    if added > 0:
        save_registry()
        _log("§a从 usercache.json 预填了 {} 名真人玩家".format(added))


# ============================================================
# 事件处理
# ============================================================

@mcdr.new_thread("MailMaple-join")
def on_player_joined(player: str):
    """玩家上线: 记录真人 + 汇总离线期间收到的新邮件 (含阻塞查询, 放独立线程)"""
    player_uuid = get_player_uuid(player)
    if player_uuid is None:
        return
    # 已在注册表中 (含手动 mail user add) 的玩家始终视为真人; 否则按规则判定
    if player_uuid not in registry.known_players and classify_player(player, player_uuid) == "bot":
        return  # 假人不入注册表
    if registry.known_players.get(player_uuid) != player:
        registry.known_players[player_uuid] = player
        save_registry()
    box = get_mailbox(player_uuid, player)

    # 先把过期邮件移入过期列表, 再统计新邮件 (scan_box_expired 内部已按需保存分片)
    scan_box_expired(player_uuid)

    # 统计离线期间收到的新邮件 (is_new), 汇总提示后全部置 False
    new_count = sum(1 for m in box.mails if m.is_new)
    if new_count > 0:
        for m in box.mails:
            m.is_new = False
        save_player(player_uuid)
        notify_offline_summary(player, new_count, box)


def view_list_button() -> RText:
    """[查看邮件列表] 可点击按钮 (点击行为跟随 use_suggest_command)"""
    btn = RText("[查看邮件列表]", RColor.aqua)
    btn.set_click_event(get_click_action(), cmd("mail") + " list")
    btn.set_hover_text("§a点击查看你的收件箱")
    return btn


def capacity_line(box: PlayerMailBox) -> str:
    """邮箱容量提示行: 持有邮件数 / 邮箱上限"""
    cap = config.default_mail_max
    cap_str = "无限" if cap <= 0 else str(cap)
    return TAG + "§7当前邮件箱容量为： §6{}§7 / §6{}".format(len(box.mails), cap_str)


def notify_received_online(player_name: str, sender_name: str, box: PlayerMailBox):
    """收件人在线时的即时通知"""
    plugin_server.tell(
        player_name,
        RTextList(TAG, "§a你收到了来自 §e{} §a的邮件，".format(sender_name), view_list_button(), "§a 进行查看！"),
    )
    plugin_server.tell(player_name, capacity_line(box))


def notify_offline_summary(player_name: str, count: int, box: PlayerMailBox):
    """收件人上线时的离线邮件汇总通知"""
    plugin_server.tell(
        player_name,
        RTextList(TAG, "§a在你离线期间，你共计收到了 §6{} §a封邮件，".format(count), view_list_button(), "§a 进行查看！"),
    )
    plugin_server.tell(player_name, capacity_line(box))


def on_unload():
    # 不在卸载时保存: 所有数据改动 (邮件/注册表/序号/黑名单等) 均已在变更时即时保存 (分片/注册表)。
    # 若在此处保存, 会把内存里的旧配置写回文件, 覆盖用户在重载前对配置文件的手动修改
    # (例如 detect_bot_by_uuid_version), 这正是"reload 后配置被重置"的根因。
    pass


# ============================================================
# Minecraft 数据获取
# ============================================================

def _int_array_to_uuid(ints) -> str:
    """将 Minecraft 的 4 个 32 位有符号整数 (UUID int array) 转为标准 UUID 字符串"""
    value = 0
    for i in ints:
        value = (value << 32) | (int(i) & 0xFFFFFFFF)
    return str(uuidlib.UUID(int=value))


def get_player_uuid(player_name: str) -> Optional[str]:
    """获取玩家 UUID 字符串; 查询或解析失败时返回 None"""
    try:
        raw = api.get_player_info(player_name, "UUID")
    except Exception as e:
        _log("§e获取 {} 的 UUID 失败: {}".format(player_name, e))
        return None

    if raw is None:
        return None

    # 1.16+ 的 UUID 为 int array (如 [I; a, b, c, d]), 转为标准 UUID 字符串
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        try:
            return _int_array_to_uuid(raw)
        except (ValueError, TypeError):
            return None

    # 字符串形式: 校验是否为合法 UUID 格式, 否则视为无效。
    # 防止上游 minecraft_data_api 返回脏数据 (如带 System chat: 前缀的整串文本)
    # 时被误当 UUID 写入注册表, 进而污染玩家分片文件名。
    if isinstance(raw, str):
        try:
            return str(uuidlib.UUID(raw))
        except (ValueError, AttributeError):
            return None

    # 其他类型一律视为无效
    return None


def get_server_player_list() -> List[str]:
    """获取在线玩家列表 (阻塞查询)"""
    result = api.get_server_player_list()
    if result is None:
        return []
    return result[2] if len(result) > 2 else []


# ============================================================
# 在线玩家集合维护 (供补全即时返回, 免去阻塞查询)
# ============================================================

def mark_player_online(player: str):
    online_players.add(player)


def mark_player_offline(player: str):
    online_players.discard(player)


@mcdr.new_thread("MailMaple-seed-online")
def seed_online_players():
    """插件加载时填充在线玩家集合, 并把当前在线的真人补进注册表。

    应对插件在玩家已在线时才加载/重载的情况: 此时这些玩家不会再触发
    on_player_joined, 仅靠 usercache.json 预填并不可靠 (服务端未必已刷写),
    故这里直接查询在线玩家的 UUID 并登记 (玩家在线, 查询必然成功)。
    """
    players = get_server_player_list()
    changed = False
    seeded = 0
    for p in players:
        online_players.add(p)
        player_uuid = get_player_uuid(p)
        if player_uuid is None:
            _log("§e无法获取在线玩家 {} 的 UUID, 暂不登记".format(p))
            continue
        # 已登记 (含手动添加) 的始终保留; 未登记的按规则过滤假人
        if player_uuid not in registry.known_players and classify_player(p, player_uuid) == "bot":
            continue
        if registry.known_players.get(player_uuid) != p:
            registry.known_players[player_uuid] = p
            changed = True
            seeded += 1
    if changed:
        save_registry()
    if seeded > 0:
        _log("§a已登记 {} 名当前在线的真人玩家".format(seeded))


def is_online(player: str) -> bool:
    """玩家是否在线 (走维护的集合, 非阻塞)"""
    return player in online_players


def suggest_recipients() -> List[str]:
    """命令补全: 在线的真人玩家 (从维护的集合即时返回)"""
    return [n for n in online_players if resolve_player_uuid(n) is not None]


# ---------------- 邮件 id 补全 (纯内存, 不做阻塞查询) ----------------

def suggest_inbox_ids(source: mcdr.CommandSource) -> List[str]:
    """补全: 命令源自己收件箱里的邮件 id"""
    if not getattr(source, "is_player", False):
        return []
    player_uuid = resolve_player_uuid(source.player)
    if player_uuid is None:
        return []
    box = mailboxes.get(player_uuid)
    return [m.id for m in box.mails] if box else []


def suggest_reject_ids(source: mcdr.CommandSource) -> List[str]:
    """补全: 自己收件箱里可拒绝 (非回退) 的邮件 id"""
    if not getattr(source, "is_player", False):
        return []
    player_uuid = resolve_player_uuid(source.player)
    if player_uuid is None:
        return []
    box = mailboxes.get(player_uuid)
    return [m.id for m in box.mails if not m.is_rollback] if box else []


def suggest_sent_ids(source: mcdr.CommandSource) -> List[str]:
    """补全: 自己发出的、对方未处理的邮件 id (可取消的)"""
    if not getattr(source, "is_player", False):
        return []
    lower = source.player.lower()
    ids = []
    for box in mailboxes.values():
        for m in box.mails:
            if m.sender.lower() == lower:
                ids.append(m.id)
    return ids


def suggest_expired_ids() -> List[str]:
    """补全: 所有过期邮件 id (管理员用)"""
    ids = []
    for mails in expired_boxes.values():
        for m in mails:
            ids.append(m.id)
    return ids


# ============================================================
# 邮件 id 生成
# ============================================================

def gen_mail_id() -> str:
    """生成邮件 id: 年月日-编号 (如 260622-18), 每天从 1 重新计数。

    注意: 只改内存中的 registry 计数, 由调用方在完成操作后 save_registry()。
    全程纯内存操作, 加锁保护以防并发下编号冲突。
    """
    with _lock:
        today = datetime.now().strftime("%y%m%d")
        if registry.mail_id_date != today:
            registry.mail_id_date = today
            registry.mail_id_seq = 0
        existing = set()
        for box in mailboxes.values():
            for m in box.mails:
                existing.add(m.id)
        for mails in expired_boxes.values():
            for m in mails:
                existing.add(m.id)
        seq = registry.mail_id_seq + 1
        mail_id = "{}-{}".format(today, seq)
        # 兜底: 万一与现有 id 冲突 (如手动改过配置), 继续向后找
        while mail_id in existing:
            seq += 1
            mail_id = "{}-{}".format(today, seq)
        registry.mail_id_seq = seq
        return mail_id


def find_mail_in_box(player_uuid: str, mail_id: str):
    """在指定邮箱里找邮件, 返回 (邮箱, 邮件) 或 (None, None)"""
    box = mailboxes.get(player_uuid)
    if box is None:
        return None, None
    for m in box.mails:
        if m.id == mail_id:
            return box, m
    return None, None


def find_sent_mail(sender_name: str, mail_id: str):
    """在所有邮箱里找该发送者发出的、指定 id 的邮件。

    返回 (收件人 uuid, 邮箱, 邮件) 或 (None, None, None)。
    (uuid 用于保存对应玩家分片)
    """
    lower = sender_name.lower()
    for player_uuid, box in mailboxes.items():
        for m in box.mails:
            if m.id == mail_id and m.sender.lower() == lower:
                return player_uuid, box, m
    return None, None, None


# ============================================================
# 内部工具
# ============================================================

def _log(msg: str):
    if plugin_server is not None:
        plugin_server.logger.info(msg)
    else:
        print(msg)


# ============================================================
# 命令注册
# ============================================================

def register(server: mcdr.PluginServerInterface):
    global plugin_server
    plugin_server = server
    load()
    seed_known_players_from_usercache()
    seed_online_players()

    # 延迟导入命令模块, 避免循环导入
    from .commands import send as send_cmd
    from .commands import mail_list as list_cmd
    from .commands import handle as handle_cmd
    from .commands import admin as admin_cmd

    server.register_help_message(cmd("mail"), "MailMaple 邮件插件帮助")

    server.register_command(
        Literal(cmd("mail"))
        .requires(lambda src: src.has_permission(get_perm("help")))
        .runs(display_help)
        .then(
            Literal("help")
            .requires(lambda src: src.has_permission(get_perm("help")))
            .runs(display_help)
        )
        .then(
            Literal("reload")
            .requires(lambda src: src.has_permission(get_perm("reload")))
            .runs(reload_cmd)
        )
        .then(
            Literal("reset")
            .requires(lambda src: src.has_permission(get_perm("reset")))
            .runs(reset_prompt)
            .then(
                Literal("confirm")
                .runs(reset_confirm)
            )
        )
        .then(
            Literal("user")
            .requires(lambda src: src.has_permission(get_perm("user")))
            .runs(list_cmd.list_users)
            .then(
                Literal("add")
                .requires(lambda src: src.has_permission(get_perm("manage")))
                .then(
                    Text("name")
                    .suggests(lambda: sorted(online_players))
                    .runs(admin_cmd.user_add)
                )
            )
            .then(
                Literal("remove")
                .requires(lambda src: src.has_permission(get_perm("manage")))
                .then(
                    Text("name")
                    .suggests(lambda: sorted(set(registry.known_players.values())))
                    .runs(admin_cmd.user_remove)
                )
            )
        )
        .then(
            Literal("black")
            .requires(lambda src: src.has_permission(get_perm("manage")))
            .runs(admin_cmd.black_list)
            .then(
                Literal("add")
                .then(
                    Text("name")
                    .suggests(lambda: sorted(online_players))
                    .runs(admin_cmd.black_add)
                )
            )
            .then(
                Literal("remove")
                .then(
                    Text("name")
                    .suggests(lambda: list(config.bot_list))
                    .runs(admin_cmd.black_remove)
                )
            )
        )
        .then(
            Literal("list")
            .requires(lambda src: src.has_permission(get_perm("list")))
            .runs(list_cmd.list_mails)
            .then(Integer("page").runs(list_cmd.list_mails))
        )
        .then(
            Literal("send")
            .requires(lambda src: src.has_permission(get_perm("send")))
            .then(
                Text("target_player")
                .suggests(lambda: suggest_recipients())
                .then(
                    QuotableText("title")
                    .runs(send_cmd.send_mail)
                    .then(
                        GreedyText("attach")
                        .runs(send_cmd.send_mail)
                    )
                )
            )
        )
        .then(
            Literal("accept")
            .requires(lambda src: src.has_permission(get_perm("accept")))
            .then(
                Text("mail_id")
                .suggests(lambda src: suggest_inbox_ids(src))
                .runs(handle_cmd.accept_mail)
            )
        )
        .then(
            Literal("reject")
            .requires(lambda src: src.has_permission(get_perm("reject")))
            .then(
                Text("mail_id")
                .suggests(lambda src: suggest_reject_ids(src))
                .runs(handle_cmd.reject_mail)
            )
        )
        .then(
            Literal("cancel")
            .requires(lambda src: src.has_permission(get_perm("cancel")))
            .then(
                Text("mail_id")
                .suggests(lambda src: suggest_sent_ids(src))
                .runs(handle_cmd.cancel_mail)
            )
        )
        .then(
            Literal("expire")
            .then(
                Literal("list")
                .requires(lambda src: src.has_permission(get_perm("expire")))
                .runs(list_cmd.expire_list)
                .then(Integer("page").runs(list_cmd.expire_list))
            )
            .then(
                Literal("push")
                .requires(lambda src: src.has_permission(get_perm("manage")))
                .then(
                    Text("mail_id")
                    .suggests(lambda: suggest_expired_ids())
                    .runs(admin_cmd.expire_push)
                    .then(Literal("force").runs(admin_cmd.expire_push_force))
                )
            )
            .then(
                Literal("return")
                .requires(lambda src: src.has_permission(get_perm("manage")))
                .then(
                    Text("mail_id")
                    .suggests(lambda: suggest_expired_ids())
                    .runs(admin_cmd.expire_return)
                    .then(Literal("force").runs(admin_cmd.expire_return_force))
                )
            )
        )
        .then(
            Literal("check")
            .requires(lambda src: src.has_permission(get_perm("manage")))
            .then(
                Literal("expire")
                .then(
                    Text("name")
                    .suggests(lambda: sorted(set(registry.known_players.values())))
                    .runs(admin_cmd.check_expire)
                    .then(Integer("page").runs(admin_cmd.check_expire))
                )
            )
        )
    )

    _log("[MailMaple] 所有命令注册完毕")
