"""
config.py — 数据模型 (Serializable) 与默认配置

存储布局 (config/mail_maple/):
  MailMaple.json                 —— 仅设置项 (MailSettings), 由 MCDR config API 维护
  mail_data/                     —— 运行数据文件夹 (与设置文件同级)
    registry.json                —— 邮件编号计数 + 真人注册表 (MailRegistry)
    players/<uuid>.json          —— 单个玩家分片: 活跃邮件 + 过期邮件 (PlayerData)

设置与运行数据分离, 且玩家数据按 UUID 分片: 每次操作只重写受影响玩家的分片,
配合原子写 (临时文件 + os.replace), 避免整份重写与写坏损毁 (见 mail_lib.py)。
"""
from typing import Dict, List, Optional, Tuple

from mcdreforged.api.utils import Serializable


# ============================================================
# 帮助信息 (文案集中在此维护)
#   每项为 (权限键, 文本); 权限键为 None 表示始终显示 (如标题/页脚),
#   否则仅当命令源拥有对应权限 (perm[权限键]) 时才展示该行。
#   文本里的 {base} 会被替换为当前前缀入口命令 (如 !!mmail / !!mail)。
# ============================================================

HELP_LINES: List[Tuple[Optional[str], str]] = [
    (None, "{:=^50}".format(" §b[MailMaple] 帮助信息 §r")),
    ("send", "§b{base} send §e<目标玩家> <标题> [附件] §f- §6发送邮件"),
    ("send", "§7    附件: 留空=主手, allhand=快捷栏, [(1,5),27]=指定格子"),
    ("user", "§b{base} user §f- §6查看可发送对象列表"),
    ("manage", "§b{base} user add/remove §e<玩家> §f- §6添加(需在线)/移除可发送对象"),
    ("manage", "§b{base} black §f- §6查看精确名字黑名单"),
    ("manage", "§b{base} black add/remove §e<玩家> §f- §6管理黑名单"),
    ("list", "§b{base} list §f- §6查看收件箱"),
    ("accept", "§b{base} accept §e<邮件id> §f- §6接受邮件"),
    ("reject", "§b{base} reject §e<邮件id> §f- §6拒绝邮件 (退回发送者)"),
    ("cancel", "§b{base} cancel §e<邮件id> §f- §6取消自己发出的邮件"),
    ("expire", "§b{base} expire list §f- §6查看自己的过期邮件"),
    ("manage", "§b{base} check expire §e<玩家> §f- §6(管理)查看玩家过期邮件"),
    ("manage", "§b{base} expire push §e<id> [force] §f- §6(管理)重发过期邮件"),
    ("manage", "§b{base} expire return §e<id> [force] §f- §6(管理)退回过期邮件"),
    ("reload", "§b{base} reload §f- §6(管理)重载配置"),
    ("help", "§b{base} help §f- §6显示此帮助"),
    (None, "{:=^50}".format(" §lBy: §6§lMorning_Maple §r")),
]


# ============================================================
# 物品附件
# ============================================================

class AttachmentItem(Serializable):
    """一件邮件附件物品 (已转为 give 可用的形式)"""
    item_id: str = "minecraft:air"      # 物品 id, 含命名空间
    count: int = 1                       # 数量
    components: str = ""                 # give 组件串 (方括号内的内容, 不含 [])
    display_name: str = ""               # 自定义名 (custom_name) 的纯文本, 无则为空


# ============================================================
# 邮件
# ============================================================

class MailItem(Serializable):
    """一封邮件"""
    id: str = ""                         # 邮件唯一 id: 年月日-序号 (如 260622-18), 每天从 1 重新计数
    time: float = 0.0                    # 发送时间戳
    title: str = ""                      # 标题
    sender: str = ""                     # 发送者名
    receiver: str = ""                   # 接收者名
    is_rollback: bool = False            # 回退邮件: 只能接受, 不能再拒绝
    is_new: bool = True                  # 是否新邮件 (未向收件人推送过通知)
    is_expired: bool = False             # 是否已过期 (移入过期列表时置 True)
    is_admin_pushed: bool = False        # 是否由管理员重新推送/退回 (显示 [管理员操作])
    attachments: List[AttachmentItem] = []


# ============================================================
# 玩家邮箱 (内存中活跃收件箱的表示)
# ============================================================

class PlayerMailBox(Serializable):
    """单个玩家的活跃收件箱 (按 UUID 索引, 仅内存使用)"""
    player_name: str = ""
    mails: List[MailItem] = []


# ============================================================
# 玩家数据分片 (落盘: mail_data/players/<uuid>.json)
#   一个玩家一个文件, 含其活跃邮件与过期邮件
# ============================================================

class PlayerData(Serializable):
    """单个玩家的落盘数据分片"""
    player_name: str = ""
    mails: List[MailItem] = []       # 活跃收件箱
    expired: List[MailItem] = []     # 过期邮件


# ============================================================
# 全局注册表 (落盘: mail_data/registry.json)
#   邮件编号计数 + 真人注册表 (体量小, 单文件即可)
# ============================================================

class MailRegistry(Serializable):
    """全局运行数据 (非玩家分片)"""
    # 邮件 id 按天编号: 记录当前日期 (YYMMDD) 与当天已用到的序号, 每天从 1 重新计数
    mail_id_date: str = ""
    mail_id_seq: int = 0
    # 已知真人注册表: uuid -> 玩家名
    known_players: Dict[str, str] = {}


# ============================================================
# 插件设置 (落盘: MailMaple.json, 仅设置项, 不含运行数据)
# ============================================================

class MailSettings(Serializable):
    # 是否使用 Maple 前缀: True -> !!mmail, False -> !!mail (避免与已有插件冲突)
    use_maple_prefix: bool = True

    # 可点击文本的点击行为:
    #   True  -> suggest_command, 点击把命令填入聊天框, 玩家按回车发送 (纯原版全版本兼容)
    #   False -> run_command, 点击直接执行 (需 MC<1.19.1 或客户端装 LetMeClickAndSend mod)
    use_suggest_command: bool = True

    # 命令权限等级 (0=guest, 1=user, 2=helper, 3=admin, 4=owner)
    perm: Dict[str, int] = {
        "help": 0,
        "user": 0,
        "list": 0,
        "send": 0,
        "accept": 0,
        "reject": 0,
        "cancel": 0,
        "expire": 0,
        "manage": 3,
        "reload": 3,
    }

    # 是否允许给自己发邮件
    allow_send_to_self: bool = False

    # 邮件列表中每封邮件最多直接展示的附件数:
    #   >0  -> 展示该数量, 多出的用"等N件"省略 (上限 36, 超过按 36)
    #   =0  -> 只展示"共 x 个附件"
    #   <0  -> 视为默认值 3
    list_attachment_display: int = 3

    # 收件箱列表每页显示的邮件条数 (<=0 视为默认 10)
    list_page_size: int = 10
    # 玩家过期邮件列表每页条数 (<=0 视为默认 10)
    expire_list_page_size: int = 10
    # 管理员查看玩家过期邮件每页条数 (<=0 视为默认 10)
    admin_expire_list_page_size: int = 10

    # 单个玩家邮箱最大邮件数, 0 表示不限制
    default_mail_max: int = 50
    # 邮件过期时间 (秒): <=0 = 永不过期 (0 与负数均视为关闭), 正数 N = 发送 N 秒后过期
    # 默认 259200 秒 = 3 天。常用换算: 1 小时=3600, 1 天=86400, 7 天=604800
    mail_expire_seconds: int = 259200
    # 管理员重发/退回邮件时是否无视邮箱容量上限
    admin_ignore_mail_max: bool = False

    # ---------------- 反假人 / 真人识别 ----------------
    # 是否按 UUID 版本号识别假人 (在线模式下: v4=真人, v3=假人)
    # 离线/盗版模式请关掉此项, 改用 bot_name_blacklist / bot_list 维护
    detect_bot_by_uuid_version: bool = True
    # 假人名字黑名单 (标准正则列表, 命中则不自动登记; 可用 mail user add 手动加入)
    # 例: ["^bot_", "^jqr_"] 表示以 bot_ / jqr_ 开头的玩家
    bot_name_blacklist: List[str] = []
    # 精确名字黑名单 (由 mail black add/remove、mail user remove 维护, 命中视为假人)
    bot_list: List[str] = []
    # 名字/正则匹配是否忽略大小写 (默认忽略)
    ignore_case: bool = True
    # 服务端 usercache.json 路径, 加载时扫描以预填已知真人
    usercache_path: str = "./server/usercache.json"

    # 说明: 运行数据 (邮件编号/真人注册表/各玩家邮箱) 已不再存于本文件,
    #       分别落在 mail_data/registry.json 与 mail_data/players/<uuid>.json
