"""
default_config.py — 默认配置与帮助信息

AdvMaple: 把某个玩家的成就「抓取」成一份库存 (stock) 持久化保存,
之后随时可以分发 (give) 给其他在线玩家。库存抓取后可脱离原玩家独立存在。
"""

# ============================================================
# 默认配置
# ============================================================

DEFAULT_CONFIG = {
    # 是否使用 Maple 前缀: True -> !!madv, False -> !!adv
    "use_maple_prefix": True,
    # 可点击文本的点击行为 (列表翻页按钮):
    #   True  -> suggest_command, 点击把命令填入聊天框 (纯原版全版本兼容)
    #   False -> run_command, 点击直接执行 (需 MC<1.19.1 或客户端装 LetMeClickAndSend mod)
    "use_suggest_command": True,

    # ---- 抓取 (stock) 时的数据来源 ----
    # 玩家成就存档目录; 随服务端 level-name / 目录结构变化时改这里。
    # 相对路径基于 MCDR 工作目录 (即 MCDR 根目录)。
    "advancements_dir": "./server/world/advancements",
    # 服务端的 usercache.json (玩家名 -> UUID), 用于解析离线玩家
    "usercache_path": "./server/usercache.json",

    # 抓取时排除的成就 id 前缀。
    # 默认排除配方类 (minecraft:recipes/...) —— 那些是配方解锁而非成就,
    # 分发它们会一次灌入数百条并让玩家配方书爆满。
    "exclude_prefixes": ["minecraft:recipes/"],

    # ---- 分发 (give) ----
    # 逐条下发 advancement grant 的间隔 (秒), 避免瞬间灌入大量命令导致卡服。
    # 0 表示不限速。
    "grant_interval": 0.02,

    # !!madv stock list 每页条数 (至少 1)
    "list_page_size": 10,

    # 命令权限等级 (0=guest, 1=user, 2=helper, 3=admin, 4=owner)
    "perm": {
        "help": 0,
        "stock": 1,     # 查看库存
        "grab": 2,      # 抓取库存 (写操作)
        "give": 2,      # 分发库存 (写操作)
        "reload": 3,
    },
}


# ============================================================
# 插件元数据
# ============================================================

PLUGIN_METADATA = "1.0.0"

# 帮助信息: 每条 = (权限键, 文本模板)。权限键对应 perm 配置, 用于按权限过滤显示。
# 文本模板中的 {p} 会被替换为**完整入口命令** (!!madv 或 !!adv), 所以模板里不要再写 adv。
HELP_ENTRIES = [
    ("stock", "§b{p} stock §7[list [页]]  §f-- §6查看当前库存 (含成就明细)"),
    ("grab", "§b{p} stock §e<玩家>  §f-- §6抓取该玩家的成就作为库存"),
    ("give", "§b{p} give  §f-- §6把库存分发给§a全服在线玩家"),
    ("give", "§b{p} give §e<玩家>  §f-- §6把库存分发给指定玩家"),
    ("give", "§b{p} give §e<玩家> <成就id>  §f-- §6只分发单个成就"),
    ("help", "§b{p} help  §f-- §6显示此帮助信息"),
    ("reload", "§b{p} reload  §f-- §6重新载入配置文件"),
]

# 帮助信息的固定头/尾 (与权限无关, 始终展示)
HELP_HEADER = "{:=^50}".format(" §b[AdvMaple] 帮助信息 §r")
HELP_FOOTER = "{:=^50}".format(" §b[AdvMaple] Version: {} §r".format(PLUGIN_METADATA))
HELP_SIGN = "§lBy：§6§lMorning_Maple"


def build_help_msg(prefix: str = "!!madv", perm_filter=None) -> str:
    """根据命令前缀生成帮助信息, 可按权限过滤条目。

    :param prefix: 完整入口命令, 如 '!!madv' (启用 Maple 前缀) 或 '!!adv' (默认前缀)
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
