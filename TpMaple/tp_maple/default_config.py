"""
default_config.py — 默认配置、维度数据、死亡关键词与帮助信息生成
"""

# ============================================================
# 默认配置
# ============================================================

DEFAULT_CONFIG = {
    # 是否使用 Maple 前缀，True则命令会变为!!mtpa，False则命令会变为!!tpa，用以区分已有插件命令冲突的可能
    "use_maple_prefix": True,
    # 可点击文本的点击行为:
    #   True  -> suggest_command, 点击把命令填入聊天框, 玩家按回车发送 (纯原版全版本兼容)
    #   False -> run_command, 点击直接执行 (需 MC<1.19.1 或客户端装 LetMeClickAndSend mod)
    "use_suggest_command": True,
    # 命令权限等级 (0=guest, 1=user, 2=helper, 3=admin, 4=owner)
    "perm": {
        "help": 0,
        "reload": 3,
        "reset": 3,
        "sethome": 1,
        "home": 1,
        "delhome": 1,
        "back": 1,
        "tpm": 1,
        "tpa": 1,
        "tpahere": 1,
        "tpaccept": 0,
        "tpacancel": 0,
    },
    # 各功能独立冷却时间 (秒), 0 表示无冷却
    "cd": {
        "home": 10,
        "back": 10,
        "tpm": 10,
        "tpa": 10,
    },
    # sethome 默认最大数量
    "default_sethome_max": 10,
    # !!mhome list 每页显示的家数量
    "home_list_page_size": 10,
    # tpa/tpahere 同意后延迟传送秒数, 0 表示立即
    "tp_delay": 3,
    # tpa/tpahere 请求超时秒数
    "tpa_timeout": 60,
    # 延迟传送期间移动取消阈值 (±格)
    "tp_move_threshold": 1.0,
    # 延迟传送期间位置检测间隔 (秒), 如 0.5 表示每 0.5 秒检查一次
    "tp_check_interval": 1.0,
    # 死亡消息匹配正则 (字符串, 代码里会 re.compile)。用于从服务端输出中识别玩家死亡消息,
    # 需包含命名捕获组: player (玩家名) 与 rest (死因描述)。
    # 默认兼容原版 vanilla 与整合端 (modded) 的 "System chat: " 前缀;
    # 若你的服务端输出格式不同, 可直接在配置文件中修改此正则, 无需改代码。
    "death_message_regex": r"^(?:System chat: )?(?P<player>\w+)(?P<rest>.*)$",
}


# ============================================================
# 维度数据
# ============================================================

DIMENSION_DATA = [
    {
        "dimension_name": "minecraft:the_nether",
        "dimension_cn": "下界",
        "dimension_id": -1,
    },
    {
        "dimension_name": "minecraft:the_end",
        "dimension_cn": "末地",
        "dimension_id": 1,
    },
    {
        "dimension_name": "minecraft:overworld",
        "dimension_cn": "主世界",
        "dimension_id": 0,
    },
]

# 所有维度全称列表, 用于命令提示词
DIMENSION_NAMES = [d["dimension_name"] for d in DIMENSION_DATA]


def dimension_to_cn(dimension: str) -> str:
    """维度全称转中文; 未知维度 (如自定义维度) 原样返回"""
    for d in DIMENSION_DATA:
        if d["dimension_name"] == dimension:
            return d["dimension_cn"]
    return dimension

# ============================================================
# 死亡消息关键词 (用于检测玩家死亡, 发送 back 提示)
# MCDR 无内置死亡事件, 通过匹配死亡消息实现, 故依赖服务端语言。
# 若你的服务端语言与下列不符, 可按需增删关键词。
# ============================================================

DEATH_KEYWORDS = [
    # --- 中文 (zh_cn) ---
    "杀死", "淹死", "烧死", "炸死", "刺死", "戳死", "冻死", "饿死", "摔死",
    "凋零", "缺氧", "窒息", "落地过猛", "从高处摔", "雷劈", "死亡",
    "掉出了这个世界", "掉进了虚空", "试图游泳逃离岩浆", "脚下的方块是岩浆",
    "燃烧殆尽", "受到了过多的动能", "被刺穿", "被压扁", "被射杀", "被击杀",
    "走入了火中", "被烧死", "被闷死",
    # --- English (en_us) ---
    "was slain", "was shot", "was killed", "was fireballed", "was blown up",
    "blew up", "was pummeled", "was struck by lightning", "was squashed",
    "was squished", "was impaled", "was skewered", "was poked to death",
    "was pricked to death", "was stung to death", "was frozen", "froze to death",
    "was burnt", "burned to death", "went up in flames", "walked into fire",
    "walked into a cactus", "drowned", "experienced kinetic energy",
    "hit the ground too hard", "fell from a high place", "fell off",
    "fell out of the world", "was doomed to fall", "was knocked into the void",
    "starved to death", "suffocated", "withered away", "tried to swim in lava",
    "discovered the floor was lava", "died",
]

# ============================================================
# 插件元数据
# ============================================================

PLUGIN_METADATA = "1.0.0"

# 帮助信息: 每条 = (权限键, 文本模板)。权限键对应 perm 配置, 用于按玩家权限过滤显示。
# 文本模板中的 {p} 会被替换为命令前缀 (!!m 或 !!)。
HELP_ENTRIES = [
    ("sethome", "§b{p}sethome §e<名字>  §f-- §6设置家"),
    ("home", "§b{p}home  §f-- §6列出所有家"),
    ("home", "§b{p}home list §7[页]  §f-- §6分页查看家列表"),
    ("home", "§b{p}home §e<名字>  §f-- §6传送到指定的家"),
    ("delhome", "§b{p}delhome §e<名字>  §f-- §6删除指定的家"),
    ("back", "§b{p}back  §f-- §6精确传送回上次死亡地点"),
    ("back", "§b{p}back safe  §f-- §6安全传送到死亡地点附近 (死在岩浆/危险处时用)"),
    ("tpm", "§b{p}tpm §e<x> <y> <z> §7[维度]  §f-- §6传送到指定坐标"),
    ("tpa", "§b{p}tpa §e<玩家名>  §f-- §6请求传送到目标玩家"),
    ("tpahere", "§b{p}tpahere §e<玩家名>  §f-- §6请求目标玩家传送到你身边"),
    ("tpaccept", "§b{p}tpaccept  §f-- §6同意最近一条传送请求"),
    ("tpacancel", "§b{p}tpacancel  §f-- §6拒绝最近一条传送请求"),
    ("help", "§b{p}tpm help  §f-- §6显示此帮助信息"),
    ("reload", "§b{p}tpm reload  §f-- §6重新载入配置文件"),
    ("reset", "§b{p}tpm reset  §f-- §6清空所有玩家数据"),
]

# 帮助信息的固定头/尾 (与权限无关, 始终展示)
HELP_HEADER = "{:=^50}".format(" §b[TpMaple] 帮助信息 §r")
HELP_FOOTER = "{:=^50}".format(" §b[TpMaple] Version: {} §r".format(PLUGIN_METADATA))
HELP_SIGN = "§lBy：§6§lMorning_Maple"


def build_help_msg(prefix: str = "!!m", perm_filter=None) -> str:
    """根据命令前缀生成帮助信息, 可按权限过滤条目。

    :param prefix: 命令前缀, 如 '!!m' (启用 Maple 前缀) 或 '!!' (默认前缀)
    :param perm_filter: 可选回调 (权限键) -> bool, 返回 False 的条目不显示;
                        为 None 时显示全部条目
    """
    lines = [HELP_HEADER]
    for perm_key, template in HELP_ENTRIES:
        if perm_filter is None or perm_filter(perm_key):
            lines.append(template.format(p=prefix))
    lines.append(HELP_FOOTER)
    lines.append(HELP_SIGN)
    return "\n".join(lines)