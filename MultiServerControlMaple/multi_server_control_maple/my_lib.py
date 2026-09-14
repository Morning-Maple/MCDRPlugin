"""
my_lib.py — 配置管理 / 前缀权限 / 事件分发 / 命令注册中枢

提供配置读写、权限/前缀/点击行为便捷函数、子服配置访问、自定义事件分发等通用能力,
并注册命令 (help / reload / show)。sync / start / stop / restart 等命令将在
对应功能实现后补充。
"""
import copy
import threading

import mcdreforged as mcdr
from mcdreforged.api.command import Literal, Text
from mcdreforged.api.event import LiteralEvent
from mcdreforged.api.rtext import RAction, RText, RTextList, RColor

from . import default_config

# ============================================================
# 全局状态
# ============================================================

config: dict = copy.deepcopy(default_config.DEFAULT_CONFIG)
plugin_server: mcdr.PluginServerInterface = None

TAG = "§b[MSC] §r"


# ============================================================
# 并发锁 (集中管理, 供 control / sync 共用, 避免各模块各自为政)
# ============================================================
#
# 两层锁, 配合使用:
#   1) 按子服的操作锁 _op_busy: 同一子服同一时刻只允许一个
#      start/stop/restart/sync 操作 (防重复提交、防交叉)。
#   2) 全局同步锁 _sync_lock: 全服同一时刻只允许一个同步任务。
#      因为同步会对【主服】执行 save-off/save-all/save-on, 这是全局状态;
#      若两个针对不同子服的同步并发, 一个先完成时 save-on 会在另一个仍在
#      拷贝时提前恢复主服自动保存, 破坏 save-off 的意义。故同步必须全局串行。
#
# 加锁顺序统一为「先 op 锁, 后 sync 锁」, 避免死锁。

_op_lock = threading.Lock()
_op_busy: dict = {}

_sync_lock = threading.Lock()


def try_acquire_op(name: str, op: str):
    """尝试占用某子服的操作。成功返回 None; 已被占用则返回当前操作标签 (如 '重启')。"""
    with _op_lock:
        current = _op_busy.get(name)
        if current is not None:
            return current
        _op_busy[name] = op
        return None


def release_op(name: str):
    """释放某子服的操作占用。"""
    with _op_lock:
        _op_busy.pop(name, None)


def clear_ops():
    """清空所有操作占用 (插件卸载时调用)。"""
    with _op_lock:
        _op_busy.clear()


def try_acquire_sync() -> bool:
    """尝试占用「全局同步」。成功返回 True; 已有同步进行中返回 False。非阻塞。"""
    return _sync_lock.acquire(blocking=False)


def release_sync():
    """释放全局同步锁 (仅应由持有者调用)。"""
    try:
        _sync_lock.release()
    except RuntimeError:
        pass

# 命令前缀: 固定为 !!mscm (本插件不与市面插件冲突, 无需提供前缀切换)
COMMAND_PREFIX = "!!mscm"

# 配置文件名; 实际路径为插件数据文件夹 config/multi_server_control_maple/MultiServerControlMaple.json
CONFIG_FILE_NAME = "MultiServerControlMaple.json"


# ============================================================
# 配置文件 读/写 (基于 MCDR 官方 load_config_simple / save_config_simple)
# ============================================================

def _config_data_processor(read_data) -> bool:
    """load_config_simple 的 data_processor 回调: 平滑升级旧配置。

    - 补全缺失的顶层键 (如新增的 probe_timeout);
    - 深补 perm 的子键 (新增命令的默认权限);
    - **不**递归进 servers: 它是用户数据, 否则会把用户删掉的示例子服又加回来。
      servers 内子服缺失的字段在读取时用 .get(默认值) 兜底。
    返回是否有改动 (有则 load_config_simple 会回写文件)。
    """
    if not isinstance(read_data, dict):
        return False
    changed = False
    for key, default_value in default_config.DEFAULT_CONFIG.items():
        if key not in read_data:
            read_data[key] = copy.deepcopy(default_value)
            changed = True
    perm = read_data.get("perm")
    if isinstance(perm, dict):
        for perm_key, perm_default in default_config.DEFAULT_CONFIG["perm"].items():
            if perm_key not in perm:
                perm[perm_key] = perm_default
                changed = True
    return changed


def save_config():
    """将当前 config 保存到插件数据文件夹"""
    if plugin_server is not None:
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
# 前缀 / 权限 / 点击行为 便捷函数
# ============================================================

def get_use_suggest_command() -> bool:
    """可点击文本是否用 suggest_command (填入聊天框); 关闭则用 run_command (直接执行)"""
    return config.get("use_suggest_command", True)


def get_click_action():
    """根据配置返回可点击文本的点击行为 (suggest_command / run_command)"""
    return RAction.suggest_command if get_use_suggest_command() else RAction.run_command


def cmd(sub: str = "") -> str:
    """生成完整命令字符串。

    前缀固定为 '!!mscm'。sub 留空时返回入口前缀 '!!mscm';
    传入子命令 (如 'start') 时返回 '!!mscm start'。
    """
    return COMMAND_PREFIX if not sub else "{} {}".format(COMMAND_PREFIX, sub)


def send_confirm(source: mcdr.CommandSource, title: str, confirm_cmd: str, cancel_cmd: str, warn: str = None):
    """统一的二次确认提示: 标题 + 可选警告 + [确认]/[取消] 按钮 + 命令式提示。

    同时给出可点击按钮与命令式输入, 两种方式都能确认/取消。
    """
    action = get_click_action()
    source.reply(TAG + title)
    if warn:
        source.reply(warn)
    source.reply(RTextList(
        "§7→ ",
        RText("[确认]", color=RColor.green).c(action, confirm_cmd).h(confirm_cmd),
        "  ",
        RText("[取消]", color=RColor.red).c(action, cancel_cmd).h(cancel_cmd),
    ))
    source.reply("§7  或输入 §a{}§7 确认、§c{}§7 取消".format(confirm_cmd, cancel_cmd))


def op_cancelled(source: mcdr.CommandSource, context: dict = None):
    """确认流程的「取消」处理: 仅回复已取消 (确认为无状态设计, 取消即什么都不做)。"""
    source.reply(TAG + "§7已取消操作")


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


def get_help_msg(source: mcdr.CommandSource = None) -> str:
    """生成帮助信息; 传入 source 时按其权限过滤掉无权使用的命令行"""
    base = cmd()
    perm_filter = None
    if source is not None:
        perm_filter = lambda perm_key: source.has_permission(get_perm(perm_key))
    return default_config.build_help_msg(base, perm_filter)


# ============================================================
# 子服配置访问
# ============================================================

def get_servers() -> dict:
    """返回所有子服配置 dict (键=子服英文名); 配置非法时返回空 dict"""
    servers = config.get("servers")
    return servers if isinstance(servers, dict) else {}


def get_server(name: str):
    """返回指定子服的配置 dict; 不存在时返回 None"""
    return get_servers().get(name)


def get_probe_timeout() -> float:
    """子服状态探测 (SLP) 的超时秒数"""
    try:
        return float(config.get("probe_timeout", 1.0))
    except (TypeError, ValueError):
        return 1.0


def get_startup_timeout() -> float:
    """start/restart 后监听子服启动的最长等待秒数"""
    try:
        return float(config.get("startup_timeout", 60))
    except (TypeError, ValueError):
        return 60.0


def get_startup_poll_interval() -> float:
    """启动监听时每次 SLP 探测的间隔秒数"""
    try:
        return float(config.get("startup_poll_interval", 5))
    except (TypeError, ValueError):
        return 5.0


# ============================================================
# 自定义事件分发 (供其他插件监听子服控制相关时机)
# ============================================================

def dispatch_event(event_name: str, args: tuple = ()):
    """向所有已加载插件分发一个自定义事件。

    事件 ID 统一加 'multi_server_control_maple.' 前缀 (见 default_config.EVENT_NS),
    避免与 MCDR 内置事件冲突。其他插件可用:
        server.register_event_listener('multi_server_control_maple.<event_name>', callback)
    进行监听; MCDR 会自动把 PluginServerInterface 作为第一个参数传入。

    :param event_name: 事件短名 (不含命名空间前缀), 如 'server_started'
    :param args: 传给监听器的参数元组
    """
    if plugin_server is None:
        return
    full_id = "{}.{}".format(default_config.EVENT_NS, event_name)
    plugin_server.dispatch_event(LiteralEvent(full_id), args)


# ============================================================
# 生命周期回调挂载点 (供 __init__ 调用)
# ============================================================

def on_unload():
    """插件卸载回调挂载点。

    数据改动均在变更时即时 save(), 故此处不再统一回写, 避免覆盖用户在
    重载前对配置文件的手动修改。

    另外通知 control 模块尽快结束其后台监听线程 (启动监听 / 等待离线轮询),
    避免卸载/重载后线程仍空转到超时才退出。
    """
    try:
        from .commands import control as control_cmd
        control_cmd.on_unload()
    except Exception as e:  # noqa: BLE001 - 卸载清理不应因异常中断
        _log("[MSC] control 卸载清理异常: {}".format(e))


# ============================================================
# 帮助 / 重载 命令处理
# ============================================================

def display_help(source: mcdr.CommandSource):
    """逐行回复帮助信息 (按当前前缀生成, 并按命令源权限过滤)"""
    for line in get_help_msg(source).splitlines():
        source.reply(line)


def reload_cmd(source: mcdr.CommandSource):
    """重载配置文件命令处理"""
    source.reply(TAG + "§2正在重载配置文件……")
    config_init()
    source.reply(TAG + "§a重载完成！")


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
    """插件加载入口: 保存 server 引用、加载配置、注册命令与帮助信息"""
    global plugin_server
    plugin_server = server
    config_init()

    # 延迟导入命令模块, 避免循环导入
    from .commands import show as show_cmd
    from .commands import sync as sync_cmd
    from .commands import control as control_cmd

    # --- 帮助信息 ---
    server.register_help_message(cmd(), "MultiServerControl 多子服控制插件帮助")

    # 子服英文名 Tab 补全 (用 lambda 包起来, 每次补全都取最新配置)
    def _suggest_servers():
        return list(get_servers().keys())

    # --- !!mscm [help | show [名字] | sync <名字> [confirm] | reload] ---
    server.register_command(
        Literal(cmd())
        .requires(*_perm("help"))
        .runs(display_help)
        .then(
            Literal("help")
            .requires(*_perm("help"))
            .runs(display_help)
        )
        .then(
            Literal("show")
            .requires(*_perm("show"))
            .runs(show_cmd.show_all)
            .then(
                Text("server_name")
                .requires(*_perm("show"))
                .suggests(lambda: _suggest_servers())
                .runs(show_cmd.show_one)
            )
        )
        .then(
            Literal("sync")
            .requires(*_perm("sync"))
            .then(
                Text("server_name")
                .requires(*_perm("sync"))
                .suggests(lambda: _suggest_servers())
                .runs(sync_cmd.sync_prompt)
                .then(
                    Literal("confirm")
                    .runs(sync_cmd.sync_confirm)
                )
                .then(
                    Literal("cancel")
                    .runs(op_cancelled)
                )
            )
        )
        .then(
            Literal("start")
            .requires(*_perm("start"))
            .then(
                Text("server_name")
                .requires(*_perm("start"))
                .suggests(lambda: _suggest_servers())
                .runs(control_cmd.start_cmd)
            )
        )
        .then(
            Literal("stop")
            .requires(*_perm("stop"))
            .then(
                Text("server_name")
                .requires(*_perm("stop"))
                .suggests(lambda: _suggest_servers())
                .runs(control_cmd.stop_prompt)
                .then(
                    Literal("confirm")
                    .runs(control_cmd.stop_confirm)
                )
                .then(
                    Literal("cancel")
                    .runs(op_cancelled)
                )
            )
        )
        .then(
            Literal("restart")
            .requires(*_perm("restart"))
            .then(
                Text("server_name")
                .requires(*_perm("restart"))
                .suggests(lambda: _suggest_servers())
                .runs(control_cmd.restart_prompt)
                .then(
                    Literal("confirm")
                    .runs(control_cmd.restart_confirm)
                )
                .then(
                    Literal("cancel")
                    .runs(op_cancelled)
                )
                .then(
                    Literal("sync")
                    .requires(*_perm("sync"))
                    .runs(control_cmd.restart_sync_prompt)
                    .then(
                        Literal("confirm")
                        .runs(control_cmd.restart_sync_confirm)
                    )
                    .then(
                        Literal("cancel")
                        .runs(op_cancelled)
                    )
                )
            )
        )
        .then(
            Literal("reload")
            .requires(*_perm("reload"))
            .runs(reload_cmd)
        )
    )

    _log("[MultiServerControlMaple] 所有命令注册完毕")
