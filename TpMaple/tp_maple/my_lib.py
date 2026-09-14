"""
my_lib.py — 配置管理 / 数据存储 / 命令注册中枢
"""
import copy
import time

import mcdreforged as mcdr
from mcdreforged.api.command import Literal, Text, Float, Integer, QuotableText
from mcdreforged.api.rtext import RText, RTextList, RAction, RColor
import minecraft_data_api as api

from . import default_config
from . import utils
from .cooldown import CooldownManager

# ============================================================
# 全局状态
# ============================================================

config: dict = copy.deepcopy(default_config.DEFAULT_CONFIG)
plugin_server: mcdr.PluginServerInterface = None

# 运行时数据 (不持久化, 重启清零)
# 冷却管理: 按 (玩家 UUID, 功能名) 记录上次使用时间
cooldown = CooldownManager()


# ============================================================
# 配置文件 读/写 (基于 MCDR 官方 load_config_simple / save_config_simple)
# ============================================================

# 配置文件名; 实际路径为插件数据文件夹 config/tp_maple/TpMaple.json
CONFIG_FILE_NAME = "TpMaple.json"


def _fill_nested_defaults(data: dict, defaults: dict) -> bool:
    """递归用 defaults 补全 data 中缺失的键 (含嵌套 dict), 返回是否有改动。

    load_config_simple 对 dict 默认配置仅补第一层, 该函数作为 data_processor,
    用于补全 perm / cd 等嵌套子键, 实现新增配置项时的平滑升级。
    """
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


def save_config():
    """将当前 config 保存到插件数据文件夹"""
    plugin_server.save_config_simple(config, CONFIG_FILE_NAME)


def config_init():
    """加载配置: 文件缺失自动创建, 并补全缺失 (含嵌套) 的默认键"""
    global config
    config = plugin_server.load_config_simple(
        CONFIG_FILE_NAME,
        default_config=copy.deepcopy(default_config.DEFAULT_CONFIG),
        data_processor=_config_data_processor,
    )


# ============================================================
# 权限 / 冷却 / 配置读取 便捷函数
# ============================================================

def get_use_maple_prefix() -> bool:
    """是否启用 Maple 前缀 (!!m...); 关闭则使用默认前缀 (!!...)"""
    return config.get("use_maple_prefix", True)


def get_use_suggest_command() -> bool:
    """可点击文本是否用 suggest_command (填入聊天框); 关闭则用 run_command (直接执行)"""
    return config.get("use_suggest_command", True)


def get_click_action():
    """根据配置返回可点击文本的点击行为 (suggest_command / run_command)"""
    return RAction.suggest_command if get_use_suggest_command() else RAction.run_command


def cmd(name: str) -> str:
    """根据 use_maple_prefix 生成完整命令字符串。

    如 name='tpa' -> '!!mtpa' (启用) 或 '!!tpa' (关闭)。
    """
    prefix = "!!m" if get_use_maple_prefix() else "!!"
    return prefix + name


def get_help_msg(source: mcdr.CommandSource = None) -> str:
    """生成帮助信息; 传入 source 时按其权限过滤掉无权使用的命令行"""
    prefix = "!!m" if get_use_maple_prefix() else "!!"
    perm_filter = None
    if source is not None:
        # 仅展示该命令源权限足够的条目
        perm_filter = lambda perm_key: source.has_permission(get_perm(perm_key))
    return default_config.build_help_msg(prefix, perm_filter)


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


def get_cd(feature: str) -> int:
    """获取功能冷却时间 (秒)"""
    return config.get("cd", {}).get(feature, 0)


def check_cd(player_uuid: str, feature: str) -> int:
    """检查冷却, 返回剩余秒数; 0 表示可用"""
    return cooldown.check(player_uuid, feature, get_cd(feature))


def record_cd(player_uuid: str, feature: str):
    """记录本次使用时间戳"""
    cooldown.record(player_uuid, feature)


def get_sethome_max() -> int:
    """每个玩家可设置的家数量上限"""
    return config.get("default_sethome_max", 3)


def get_home_list_page_size() -> int:
    """!!mhome list 每页显示的家数量 (至少 1)"""
    return max(1, config.get("home_list_page_size", 10))


def get_tp_delay() -> int:
    """tpa/tpahere 同意后的延迟传送秒数 (0 表示立即)"""
    return config.get("tp_delay", 5)


def get_tpa_timeout() -> int:
    """tpa/tpahere 请求超时秒数 (<=0 表示永不超时)"""
    return config.get("tpa_timeout", 60)


def get_tp_move_threshold() -> float:
    """延迟传送期间判定"移动取消"的单轴位移阈值 (格)"""
    return config.get("tp_move_threshold", 1.0)


def get_tp_check_interval() -> float:
    """延迟传送/传送校验期间的位置检测间隔 (秒)"""
    return config.get("tp_check_interval", 0.5)


# ============================================================
# 玩家持久化数据 (player_datas 按 UUID 索引)
# ============================================================

def get_player_data(player_uuid: str) -> dict:
    """获取指定玩家的持久化数据, 不存在则创建空数据"""
    datas = config.setdefault("player_datas", {})
    if player_uuid not in datas:
        datas[player_uuid] = {
            "player_name": "",
            "homes": {},       # { home_name: {x, y, z, dimension} }
        }
    return datas[player_uuid]


def save_player_data():
    """保存整个 config (含 player_datas)"""
    save_config()


# ============================================================
# Minecraft 数据获取
# ============================================================

def get_player_position_and_dimension(player_name: str):
    """
    获取玩家当前位置和维度
    :return: (Coordinate, dimension_name_str); 查询失败时返回 (None, None)
    """
    # minecraft_data_api 在查询失败时会抛出 ValueError, 这里统一转为 (None, None)
    try:
        player_position = api.get_player_coordinate(player_name)
        player_dimension = api.get_player_dimension(player_name)
    except ValueError:
        return None, None

    # 旧版 API 可能返回维度 id (int) 而非全称, 这里统一转成维度全称字符串
    if isinstance(player_dimension, int):
        # 非原版三维度 (自定义维度) 无法映射, 兜底当作主世界
        if player_dimension not in [0, -1, 1]:
            return player_position, "minecraft:overworld"
        for dim in default_config.DIMENSION_DATA:
            if dim["dimension_id"] == player_dimension:
                player_dimension = dim["dimension_name"]
                break

    return player_position, player_dimension


def get_player_uuid(player_name: str):
    """获取玩家 UUID 字符串; 查询或解析失败时返回 None"""
    try:
        raw = api.get_player_info(player_name, "UUID")
    except Exception as e:
        _log(f"[TpMaple] 获取 {player_name} 的 UUID 失败: {e}")
        return None

    if raw is None:
        return None

    # 1.16+ 的 UUID 为 int array (如 [I; a, b, c, d]), 转为标准 UUID 字符串
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        try:
            return str(utils.nbt_int_array_to_uuid(list(raw)))
        except Exception:
            return None

    return str(raw)


def get_player_last_death_position(player_name: str):
    """
    获取玩家上次死亡位置
    :return: (x, y, z, dimension) 或 None
    """
    data = api.get_player_info(player_name, "LastDeathLocation")
    if data is None:
        return None
    pos = data.get("pos")
    dimension = data.get("dimension")
    if pos is None or dimension is None:
        return None
    return pos[0], pos[1], pos[2], dimension


def get_server_player_list() -> list[str]:
    """获取在线玩家列表"""
    result = api.get_server_player_list()
    if result is None:
        return []
    return result[2] if len(result) > 2 else []


# ============================================================
# 命令补全 (suggests) 数据源 —— 必须非阻塞, 不能调用 minecraft_data_api
# ============================================================

def get_player_home_names(player_name: str) -> list[str]:
    """按玩家名从 player_datas 中查其所有家名 (纯内存查找, 不查询 API)"""
    for data in config.get("player_datas", {}).values():
        if data.get("player_name") == player_name:
            return list(data.get("homes", {}).keys())
    return []


def suggest_home_names(source) -> list[str]:
    """home / delhome / sethome 的家名补全: 返回该玩家已设置的家名"""
    if getattr(source, "is_player", False):
        return get_player_home_names(source.player)
    return []


def suggest_online_players() -> list[str]:
    """tpa / tpahere 的目标玩家补全: 返回自维护的在线玩家集合 (非阻塞)"""
    return list(online_players)


# ============================================================
# 在线玩家追踪 / 死亡检测
# ============================================================

# 自维护的在线玩家集合 (on_info 在任务执行线程上, 无法调用阻塞的在线列表查询)
online_players: set = set()

# 运行时 back 点 (不持久化): back_points[玩家名] = {x, y, z, dimension}
# 由本插件的传送 (传送前位置) 和死亡 (死亡地点) 覆盖, 供 !!mback 返回
back_points: dict = {}


def set_back_point(player_name: str, x: float, y: float, z: float, dimension: str):
    """记录一个 back 点 (覆盖该玩家旧的 back 点)"""
    back_points[player_name] = {"x": x, "y": y, "z": z, "dimension": dimension}


def get_back_point(player_name: str):
    """获取该玩家的 back 点, 不存在返回 None"""
    return back_points.get(player_name)


def record_back_point(player_name: str):
    """查询玩家当前位置并记录为 back 点 (传送前调用); 查询失败则不记录。

    注意: 内部有阻塞查询, 须在 @new_thread 线程中调用。
    """
    pos, dim = get_player_position_and_dimension(player_name)
    if pos is not None:
        set_back_point(player_name, pos.x, pos.y, pos.z, dim)


def mark_player_online(player: str):
    """玩家加入时登记到在线集合"""
    online_players.add(player)


def mark_player_offline(player: str):
    """玩家离线时移出在线集合"""
    online_players.discard(player)


@mcdr.new_thread("TpMaple-seed-online")
def seed_online_players():
    """插件加载时填充在线玩家集合 (应对重载时玩家已在线的情况)"""
    for p in get_server_player_list():
        online_players.add(p)


def handle_info_for_death(info):
    """解析服务端输出, 检测玩家死亡并发送 back 提示。

    MCDR 无内置死亡事件, 这里通过匹配死亡消息实现, 依赖服务端语言
    (关键词见 default_config.DEATH_KEYWORDS)。
    """
    content = getattr(info, "content", None)
    if not content:
        return
    # 玩家聊天消息 (info.player 非空) 一定不是死亡广播, 跳过
    if getattr(info, "player", None):
        return

    for player in online_players:
        if not content.startswith(player):
            continue
        # 确认玩家名是完整词 (后续字符非字母数字下划线, 兼容中英文死亡消息)
        rest = content[len(player):]
        if rest and (rest[0].isalnum() or rest[0] == "_"):
            continue
        if any(kw in rest for kw in default_config.DEATH_KEYWORDS):
            _on_player_death(player)
        return


@mcdr.new_thread("TpMaple-death")
def _on_player_death(player: str):
    """玩家死亡后台处理: 把死亡地点记录为 back 点, 并发送可点击提示。

    在新线程中执行: 一是 on_info 在任务执行线程上不能阻塞查询,
    二是死亡数据需稍等才写入存档。
    """
    time.sleep(0.5)  # 等待 LastDeathLocation 写入
    try:
        death = get_player_last_death_position(player)
    except Exception:
        death = None
    if death is not None:
        x, y, z, dimension = death
        set_back_point(player, x, y, z, dimension)
    _send_death_hint(player)


def _send_death_hint(player: str):
    """向死亡玩家发送可点击的 back / back s 提示"""
    back_cmd = cmd("back")
    safe_cmd = f"{back_cmd} s"
    click_action = get_click_action()
    message = RTextList(
        "§b[TpMaple] §6可通过：",
        RText("[精确返回]", color=RColor.green)
        .c(click_action, back_cmd)
        .h(back_cmd),
        " §6或 ",
        RText("[安全返回]", color=RColor.yellow)
        .c(click_action, safe_cmd)
        .h(safe_cmd),
        " §6到死亡地点！",
    )
    plugin_server.tell(player, message)


# ============================================================
# 帮助 / 重载 命令处理
# ============================================================

def display_help(source: mcdr.CommandSource):
    """逐行回复帮助信息 (按当前前缀生成, 并按命令源权限过滤)"""
    for line in get_help_msg(source).splitlines():
        source.reply(line)


def reload_cmd(source: mcdr.CommandSource):
    """重载配置文件命令处理"""
    source.reply("§b[TpMaple] §2正在重载配置文件……")
    config_init()
    source.reply("§b[TpMaple] §a重载完成！")


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
    """插件加载入口: 保存 server 引用、加载配置、注册所有命令与帮助信息"""
    global plugin_server
    plugin_server = server
    config_init()

    # 延迟导入命令模块, 避免循环导入
    from .commands import home as home_cmd
    from .commands import back as back_cmd
    from .commands import tp as tp_cmd
    from .commands import tpa as tpa_cmd

    # --- 帮助信息 ---
    server.register_help_message(cmd("tpm"), "TpMaple 传送插件帮助")

    # --- !!tpm [help | reload | <x> <y> <z> [dimension]] ---
    server.register_command(
        Literal(cmd("tpm"))
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
            # !!tpm <x> <y> <z> [dimension]
            Float("x").then(
                Float("y").then(
                    Float("z")
                    .requires(*_perm("tpm"))
                    .runs(tp_cmd.tp_to_pos)
                    .then(
                        Text("dimension")
                        .suggests(lambda: default_config.DIMENSION_NAMES)
                        .runs(tp_cmd.tp_to_pos)
                    )
                )
            )
        )
    )

    # --- !!msethome <name> ---
    server.register_command(
        Literal(cmd("sethome"))
        .requires(*_perm("sethome"))
        .then(
            QuotableText("home_name")
            .suggests(suggest_home_names)
            .runs(home_cmd.set_home)
        )
    )

    # --- !!mhome [list [page] | <name>] ---
    server.register_command(
        Literal(cmd("home"))
        .requires(*_perm("home"))
        .runs(home_cmd.list_homes)
        .then(
            # !!mhome list [页]: 分页查看家列表
            Literal("list")
            .runs(home_cmd.list_homes)
            .then(
                Integer("page").runs(home_cmd.list_homes)
            )
        )
        .then(
            QuotableText("home_name")
            .suggests(suggest_home_names)
            .runs(home_cmd.go_home)
        )
    )

    # --- !!mdelhome <name> ---
    server.register_command(
        Literal(cmd("delhome"))
        .requires(*_perm("delhome"))
        .then(
            QuotableText("home_name")
            .suggests(suggest_home_names)
            .runs(home_cmd.del_home)
        )
    )

    # --- !!mback ---
    server.register_command(
        Literal(cmd("back"))
        .requires(*_perm("back"))
        .runs(back_cmd.go_back)
        .then(
            Literal(["safe", "s"])
            .requires(*_perm("back"))
            .runs(back_cmd.go_back_safe)
        )
    )

    # --- !!mtpa <player> ---
    server.register_command(
        Literal(cmd("tpa"))
        .requires(*_perm("tpa"))
        .then(
            Text("target_player")
            .suggests(suggest_online_players)
            .runs(tpa_cmd.tpa)
        )
    )

    # --- !!mtpahere <player> ---
    server.register_command(
        Literal(cmd("tpahere"))
        .requires(*_perm("tpahere"))
        .then(
            Text("target_player")
            .suggests(suggest_online_players)
            .runs(tpa_cmd.tpa_here)
        )
    )

    # --- !!mtpaccept ---
    server.register_command(
        Literal(cmd("tpaccept"))
        .requires(*_perm("tpaccept"))
        .runs(tpa_cmd.tp_accept)
    )

    # --- !!mtpacancel ---
    server.register_command(
        Literal(cmd("tpacancel"))
        .requires(*_perm("tpacancel"))
        .runs(tpa_cmd.tpa_cancel)
    )

    seed_online_players()
    _log("[TpMaple] 所有命令注册完毕")
