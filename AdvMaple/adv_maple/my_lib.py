"""
my_lib.py — 配置管理 / 权限 / 在线玩家 / 命令注册中枢
"""
import copy
import uuid as uuidlib

import mcdreforged as mcdr
from mcdreforged.api.command import Literal, Text, Integer, QuotableText
from mcdreforged.api.rtext import RAction
import minecraft_data_api as api

from . import default_config
from . import utils

# ============================================================
# 全局状态
# ============================================================

# 插件统一消息前缀
TAG = "§b[AdvMaple] "

config: dict = copy.deepcopy(default_config.DEFAULT_CONFIG)
plugin_server: mcdr.PluginServerInterface = None

# 配置文件名; 实际路径为插件数据文件夹 config/adv_maple/AdvMaple.json
CONFIG_FILE_NAME = "AdvMaple.json"

# 自维护的在线玩家集合。
# 命令补全与「全服同步」都基于它, 走内存、非阻塞 (minecraft_data_api 的查询是阻塞的,
# 不能用在补全回调里)。插件加载时用 seed_online_players() 填充,
# 并在每次 get_online_players() 时用实时数据校正 (防止漏掉的离开事件造成残留)。
online_players: set = set()

# 已注册的命令前缀快照 ("!!m" 或 "!!")。
# 命令树只在插件加载时注册一次, 所以运行时所有提示/按钮/补全都必须用这个快照,
# 否则用户 reload 改了 use_maple_prefix 后, 会看到实际执行不了的新前缀命令。
_registered_prefix: str = None


# ============================================================
# 配置文件 读/写
# ============================================================

def _fill_nested_defaults(data: dict, defaults: dict) -> bool:
    """递归用 defaults 补全 data 中缺失的键 (含嵌套 dict), 返回是否有改动。"""
    changed = False
    for key, default_value in defaults.items():
        if key not in data:
            data[key] = copy.deepcopy(default_value)
            changed = True
        elif isinstance(default_value, dict) and isinstance(data[key], dict):
            if _fill_nested_defaults(data[key], default_value):
                changed = True
    return changed


def _config_data_processor(read_data) -> bool:
    """load_config_simple 的 data_processor 回调: 补全嵌套默认值"""
    if not isinstance(read_data, dict):
        return False
    return _fill_nested_defaults(read_data, default_config.DEFAULT_CONFIG)


def config_init():
    """加载配置: 文件缺失自动创建, 并补全缺失 (含嵌套) 的默认键"""
    global config
    config = plugin_server.load_config_simple(
        CONFIG_FILE_NAME,
        default_config=copy.deepcopy(default_config.DEFAULT_CONFIG),
        data_processor=_config_data_processor,
    )


def save_config():
    """把内存配置写回设置文件"""
    try:
        plugin_server.save_config_simple(config, CONFIG_FILE_NAME)
    except Exception as e:
        _log(f"[AdvMaple] 保存配置失败: {e}")


# ============================================================
# 权限 / 前缀 / 配置读取
# ============================================================

# 权限不足时统一提示文案
PERM_DENIED_MSG = "§c你没有足够的MCDR权限执行此命令"


def get_perm(cmd_name: str) -> int:
    """获取命令所需权限等级"""
    return config.get("perm", {}).get(cmd_name, 0)


def _perm(cmd_name: str):
    """生成带统一权限不足提示的 requires 参数对, 配合 .requires(*_perm("xxx")) 使用"""
    return (
        lambda src: src.has_permission(get_perm(cmd_name)),
        lambda: PERM_DENIED_MSG,
    )


def get_use_maple_prefix() -> bool:
    """是否启用 Maple 前缀 (!!madv); 关闭则使用默认前缀 (!!adv)"""
    return config.get("use_maple_prefix", True)


def get_use_suggest_command() -> bool:
    """可点击文本是否用 suggest_command (填入聊天框); 关闭则用 run_command (直接执行)"""
    return config.get("use_suggest_command", True)


def get_click_action():
    """根据配置返回可点击文本的点击行为"""
    return RAction.suggest_command if get_use_suggest_command() else RAction.run_command


def get_prefix_snapshot() -> str:
    """已注册的命令前缀 ("!!m" 或 "!!")。

    命令树只在插件加载时注册一次, 运行时不能再变。因此所有提示、按钮、
    补全都必须基于这个快照, 保证「显示的命令」与「实际注册的命令」一致。
    """
    if _registered_prefix is not None:
        return _registered_prefix
    # 尚未注册 (理论上不会走到) 时按当前配置兜底
    return "!!m" if get_use_maple_prefix() else "!!"


def cmd(name: str) -> str:
    """生成完整命令字符串。

    如 name='adv' -> '!!madv' (启用 Maple 前缀) 或 '!!adv' (关闭)。
    """
    return get_prefix_snapshot() + name


def get_exclude_prefixes() -> list:
    """抓取时排除的成就 id 前缀列表 (容错: 非 list 视为空)"""
    raw = config.get("exclude_prefixes", [])
    if not isinstance(raw, list):
        return []
    return [str(p) for p in raw if p]


def get_grant_interval() -> float:
    """逐条 grant 的间隔秒数 (<=0 表示不限速)"""
    try:
        value = float(config.get("grant_interval", 0.02))
    except (TypeError, ValueError):
        return 0.02
    return value if value > 0 else 0.0


def get_list_page_size() -> int:
    """!!madv stock 明细每页条数 (至少 1)"""
    try:
        value = int(config.get("list_page_size", 10))
    except (TypeError, ValueError):
        return 10
    return max(1, value)


# ============================================================
# 帮助 / 重载
# ============================================================

def get_help_msg(source: mcdr.CommandSource = None) -> str:
    """生成帮助信息; 传入 source 时按其权限过滤掉无权使用的命令行"""
    perm_filter = None
    if source is not None:
        perm_filter = lambda perm_key: source.has_permission(get_perm(perm_key))
    return default_config.build_help_msg(cmd("adv"), perm_filter)


def display_help(source: mcdr.CommandSource):
    """逐行回复帮助信息 (按当前前缀生成, 并按命令源权限过滤)"""
    for line in get_help_msg(source).splitlines():
        source.reply(line)


def reload_cmd(source: mcdr.CommandSource):
    """重载配置文件"""
    source.reply(f"{TAG}§2正在重载配置文件……")
    old_prefix = get_prefix_snapshot()
    config_init()
    # 配置可能改了 advancements_dir / usercache_path, 清掉缓存让其重新读取
    from . import advancement
    advancement.clear_cache()

    new_prefix = "!!m" if get_use_maple_prefix() else "!!"
    source.reply(f"{TAG}§a重载完成！")
    if new_prefix != old_prefix:
        # 命令树只在加载时注册一次, 改前缀必须重载插件才能生效
        source.reply(
            f"{TAG}§e注意: §fuse_maple_prefix §e已变更, 但命令前缀需要"
            f"§6重载插件§e才能生效。当前实际命令仍为 §f{old_prefix}adv§e。"
        )


# ============================================================
# 在线玩家追踪
# ============================================================

def mark_player_online(player: str):
    """玩家加入时登记到在线集合"""
    online_players.add(player)


def mark_player_offline(player: str):
    """玩家离线时移出在线集合"""
    online_players.discard(player)


@mcdr.new_thread("AdvMaple-seed-online")
def seed_online_players():
    """插件加载时重建在线玩家集合 (应对重载时玩家已经在线的情况)。

    先清空再填充 —— 重载插件时旧集合可能残留已离线玩家。
    查询失败时保持为空 (后续 get_online_players 会再尝试)。
    """
    online_players.clear()
    players = get_server_player_list()
    if players:
        online_players.update(players)


def get_online_players() -> list:
    """**权威**在线玩家名列表。

    实时查询成功时以它为准并校正自维护集合 —— 包括「确实没人在线」的情况
    (会清空集合), 这样才能修掉「漏掉离开事件导致集合残留」的问题;
    只有查询**失败** (返回 None) 时才回退到缓存。

    注意: 该函数可能阻塞, 只能在 @new_thread 中调用。
    """
    live = get_server_player_list()
    if live is None:
        # 查询失败: 用缓存兜底
        return sorted(online_players)

    # 查询成功: 无论是否为空都校正缓存
    online_players.clear()
    online_players.update(live)
    return sorted(live)


def get_cached_online_players() -> list:
    """**缓存版**在线玩家列表 (非阻塞, 供 Tab 补全使用)。"""
    return sorted(online_players)


# ============================================================
# Minecraft 数据获取 (minecraft_data_api)
# ============================================================

def get_server_player_list():
    """查询在线玩家列表。

    :return: 玩家名列表; **查询失败时返回 None** (区别于「确实没人在线」的 ``[]``)。
        这个区分很重要: 只有失败时才该用缓存兜底, 查询成功但为空时必须清空缓存,
        否则漏掉离开事件后会永久残留离线玩家。
    """
    try:
        result = api.get_server_player_list()
    except Exception as e:
        _log(f"[AdvMaple] 查询在线玩家列表失败: {e}")
        return None
    if result is None:
        return None
    if len(result) > 2:
        return list(result[2])
    # 返回值结构异常, 同样视为失败
    return None


def get_player_uuid(player_name: str):
    """获取玩家 UUID 字符串; 查询或解析失败时返回 None"""
    try:
        raw = api.get_player_info(player_name, "UUID")
    except Exception as e:
        _log(f"[AdvMaple] 获取 {player_name} 的 UUID 失败: {e}")
        return None

    if raw is None:
        return None

    # 1.16+ 的 UUID 为 int array (如 [I; a, b, c, d]), 转为标准 UUID 字符串
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        try:
            return str(utils.nbt_int_array_to_uuid(list(raw)))
        except Exception:
            return None

    # 字符串形式: 校验是否为合法 UUID 格式, 否则视为无效
    if isinstance(raw, str):
        try:
            return str(uuidlib.UUID(raw))
        except (ValueError, AttributeError):
            return None

    return None


# ============================================================
# 命令补全数据源 —— 必须非阻塞, 不能调用 minecraft_data_api
# ============================================================

def suggest_online_players() -> list:
    """give 的目标玩家补全: 返回**缓存**的在线玩家集合 (非阻塞)"""
    return get_cached_online_players()


def suggest_stock_ids() -> list:
    """give <玩家> <成就> 的成就 id 补全: 返回库存里的成就 (内存读取, 非阻塞)"""
    from . import advancement
    stock = advancement.get_stock()
    if not stock:
        return []
    return list(stock["ids"])


# ============================================================
# 内部工具
# ============================================================

def _log(msg: str):
    """输出日志; plugin_server 未就绪时回退到 print"""
    if plugin_server is not None:
        plugin_server.logger.info(msg)
    else:
        print(msg)


# ============================================================
# 命令注册
# ============================================================

def register(server: mcdr.PluginServerInterface):
    """插件加载入口: 保存 server 引用、加载配置与库存、注册所有命令与帮助信息"""
    global plugin_server, _registered_prefix
    plugin_server = server
    config_init()

    # 固化本次注册使用的命令前缀 (运行时所有提示/按钮都基于它)
    _registered_prefix = "!!m" if get_use_maple_prefix() else "!!"

    # 延迟导入命令模块, 避免循环导入
    from . import advancement
    from .commands import stock as stock_cmd
    from .commands import give as give_cmd

    # 载入持久化的库存
    advancement.load_stock()

    # --- 帮助信息 ---
    server.register_help_message(cmd("adv"), "AdvMaple 成就库存插件帮助")

    # --- !!madv [help | reload | stock [玩家 | 页] | give [玩家 [成就id]]] ---
    server.register_command(
        Literal(cmd("adv"))
        .requires(*_perm("help"))
        .runs(display_help)
        .then(
            Literal("help")
            .requires(*_perm("help"))
            .runs(display_help)
        )
        .then(
            Literal("reload")
            .requires(*_perm("reload"))
            .runs(reload_cmd)
        )
        .then(
            # !!madv stock                → 查看库存 (第 1 页明细)
            # !!madv stock list [页]      → 查看明细 (指定页)
            # !!madv stock <玩家>          → 抓取
            #
            # 分页用字面量 list 而非直接 <页>, 避免与 <玩家> 冲突:
            # MCDR 参数节点按注册顺序匹配, 若这里是 Integer, 则纯数字的玩家名
            # (离线服常见) 会被当成分页参数而无法抓取。
            Literal("stock")
            .requires(*_perm("stock"))
            .runs(stock_cmd.show_stock)
            .then(
                Literal("list")
                .runs(stock_cmd.show_stock)
                .then(
                    Integer("page").runs(stock_cmd.show_stock)
                )
            )
            .then(
                Text("player")
                .requires(*_perm("grab"))
                .runs(stock_cmd.grab_stock)
            )
        )
        .then(
            # !!madv give [玩家 [成就id]]
            Literal("give")
            .requires(*_perm("give"))
            .runs(give_cmd.give_all)
            .then(
                Text("target")
                .suggests(suggest_online_players)
                .runs(give_cmd.give_one)
                .then(
                    QuotableText("adv_id")
                    .suggests(suggest_stock_ids)
                    .runs(give_cmd.give_single)
                )
            )
        )
    )

    seed_online_players()
    _log("[AdvMaple] 所有命令注册完毕")
