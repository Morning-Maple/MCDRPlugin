"""
default_config.py — 默认配置与帮助信息生成

注: 本插件命令前缀固定为 !!mscm, 不与市面插件冲突, 故不提供前缀切换开关。
子服状态通过 Server List Ping (见 slp.py) 探测; 「玩家能进服」即视为在线。
"""

# ============================================================
# 默认配置
# ============================================================

DEFAULT_CONFIG = {
    # 可点击文本的点击行为:
    #   True  -> suggest_command, 点击把命令填入聊天框, 玩家按回车发送 (纯原版全版本兼容)
    #   False -> run_command, 点击直接执行 (需 MC<1.19.1 或客户端装 LetMeClickAndSend mod)
    "use_suggest_command": True,
    # 子服状态探测 (SLP) 的超时秒数
    "probe_timeout": 1.0,
    # start/restart 后监听子服启动的最长等待秒数 (超时则提示未检测到在线)
    "startup_timeout": 60,
    # 启动监听时每次 SLP 探测的间隔秒数
    "startup_poll_interval": 5,
    # 命令权限等级 (0=guest, 1=user, 2=helper, 3=admin, 4=owner)
    "perm": {
        "help": 0,
        "reload": 3,
        "show": 0,
        "sync": 3,
        "start": 3,
        "stop": 3,
        "restart": 3,
    },
    # 子服务器配置: 键为「子服英文名」(命令参数; 同时用于 Velocity 的 /server 名)。
    # ！！本插件的启停仅适配 Windows ！！
    #   cn_name        : 中文名 (展示用; 不填则展示英文 key)
    #   can_sync       : 是否可与主服同步存档 (True=可同步主服, False=独立服务器), 展示用
    #   host           : 子服地址 (一般为本机 127.0.0.1); 用于 SLP 状态探测, 也复用为 rcon 地址
    #   port           : 子服游戏端口, 用于 SLP 状态探测
    #   rcon_enable    : 是否启用 rcon (默认 False; 不启用则无法用 stop 关闭子服)
    #   rcon_port      : 子服 rcon 端口, 必须 != port
    #   rcon_password  : 子服 rcon 密码
    #   path           : 子服根目录, 即 server 文件夹的上一级 (例: server 在 C:/game/server, 则 path=C:/game)
    #   start_command  : 启动命令, 支持两种写法:
    #                      - list[str]: 进入 path 开 cmd, 按顺序执行列表里每条命令 (各元素=一条 cmd 指令)
    #                      - str      : 执行 path 下指定的文件 (相对 path, 一般是启动脚本如 start.bat)
    #                    启动时会为子服开一个独立的新控制台窗口。
    #   sync_source    : 同步源 = 主服(本机)的 world 目录 (一般 ./server/world); 仅同步 world 内资源
    #   sync_target    : 同步目标 = 子服的 world 目录 (路径可绝对, 或相对主服 MCDR 工作目录)
    #   sync_ignore_files : 复制时忽略的列表 (正则); 结尾带 / 表示忽略该目录下全部 (如 "session/");
    #                       其余按正则 re.search 匹配「相对 sync_source 的相对路径」(以 / 分隔);
    #                       session.lock 始终强制忽略
    #   description    : 备注 (可选)
    # 同步(sync)安全策略: 目标子服在线则拒绝同步(须先 stop); 同步前对主服 save-off + save-all,
    #   完成后 save-on, 避免拷贝时存档被写坏。
    # 首次加载会写入下面两个示例, 可自行增删修改。
    "servers": {
        "mirror": {
            "cn_name": "镜像服",
            "can_sync": True,
            "host": "127.0.0.1",
            "port": 25566,
            "rcon_enable": True,
            "rcon_port": 25576,
            "rcon_password": "123456",
            "path":"",
            "start_command":"",
            "sync_source":"",
            "sync_target":"",
            "sync_ignore_files":["session.lock"],
            "description": "主服镜像, 可与主服同步存档",
        },
        "create": {
            "can_sync": False,
            "host": "127.0.0.1",
            "port": 25567,
            "description": "创造服, 独立存档",
        },
    },
}


# ============================================================
# 插件事件 (供其他插件通过 register_event_listener 监听)
#   后续子服启动 / 关闭 / 同步完成等时机将通过 my_lib.dispatch_event 分发自定义事件,
#   事件 ID 统一以 'multi_server_control_maple.' 为前缀, 避免与 MCDR 内置事件冲突。
# ============================================================

EVENT_NS = "multi_server_control_maple"


# ============================================================
# 帮助信息
# ============================================================

PLUGIN_VERSION = "1.0.0"

# 帮助信息: 每条 = (权限键, 文本模板)。权限键对应 perm 配置, 用于按玩家权限过滤显示。
# 文本模板中的 {p} 会被替换为命令前缀 (!!mscm)。
HELP_ENTRIES = [
    ("help", "§b{p} help  §f-- §6显示此帮助信息"),
    ("show", "§b{p} show §7[名字]  §f-- §6查看所有/指定子服信息"),
    ("sync", "§b{p} sync §7<名字>  §f-- §6全量同步主服存档到子服"),
    ("start", "§b{p} start §7<名字>  §f-- §6启动子服"),
    ("stop", "§b{p} stop §7<名字>  §f-- §6关闭子服（依赖 rcon）"),
    ("restart", "§b{p} restart §7<名字> [sync]  §f-- §6重启子服（可选先同步）"),
    ("reload", "§b{p} reload  §f-- §6重新载入配置文件"),
]

# 帮助信息的固定头/尾 (与权限无关, 始终展示)
HELP_HEADER = "{:=^50}".format(" §b[MSC] 帮助信息 §r")
HELP_FOOTER = "{:=^50}".format(" §b[MSC] Version: {} §r".format(PLUGIN_VERSION))
HELP_SIGN = "§lBy：§6§lMorning_Maple"


def build_help_msg(base: str = "!!mscm", perm_filter=None) -> str:
    """根据入口命令生成帮助信息, 可按权限过滤条目。

    :param base: 入口命令前缀, 固定为 '!!mscm'
    :param perm_filter: 可选回调 (权限键) -> bool, 返回 False 的条目不显示;
                        为 None 时显示全部条目
    """
    lines = [HELP_HEADER]
    for perm_key, template in HELP_ENTRIES:
        if perm_filter is None or perm_filter(perm_key):
            lines.append(template.format(p=base))
    lines.append(HELP_FOOTER)
    lines.append(HELP_SIGN)
    return "\n".join(lines)
