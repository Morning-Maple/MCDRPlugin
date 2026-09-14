"""
mail_list.py — !!mail list / !!mail user / !!mail expire list
收件箱 / 可发送对象 / 过期邮件列表 (RText 可点击 + 附件 hover + 分页)
"""
from datetime import datetime

import mcdreforged as mcdr
from mcdreforged.api.rtext import RText, RTextList, RColor, RAction

from .. import mail_lib

TAG = mail_lib.TAG


# ============================================================
# 附件展示
# ============================================================

def _display_limit() -> int:
    """附件展示数量: <0 视为默认 3, >36 按 36, 0 表示只显示总数"""
    n = mail_lib.config.list_attachment_display
    if n < 0:
        return 3
    if n > 36:
        return 36
    return n


def _item_label(attach) -> str:
    """单件附件的展示文本: 【物品名(x数量)】, 自定义名优先, 否则用物品 id (去命名空间)"""
    if attach.display_name:
        name = attach.display_name
    else:
        name = attach.item_id.split(":", 1)[-1]
    return "【{}(x{})】".format(name, attach.count)


def _attachment_summary(attachments) -> RTextList:
    """附件摘要 RText: 按配置展示前若干件, 其余用可悬停的"等"省略;
    配置为 0 时只展示"共 x 个附件"。完整清单始终可悬停查看。"""
    result = RTextList()
    total = len(attachments)
    limit = _display_limit()
    full_lines = "\n".join("§b{}§r".format(_item_label(a)) for a in attachments)

    if limit == 0:
        only = RText("共 {} 个附件".format(total), RColor.aqua)
        only.set_hover_text("§f全部附件 ({}件):\n{}".format(total, full_lines))
        result.append(only)
        return result

    shown = attachments[:limit]
    result.append(RText("".join(_item_label(a) for a in shown), RColor.aqua))
    if total > limit:
        etc = RText(" 等{}件".format(total), RColor.gray)
        etc.set_hover_text("§f全部附件 ({}件):\n{}".format(total, full_lines))
        result.append(etc)
    return result


# ============================================================
# 通用: 标识 / 邮件信息 / 分页
# ============================================================

def _size(value: int) -> int:
    """每页条数 (<=0 视为默认 10)"""
    return value if value > 0 else 10


def markers(mail, include_expired: bool) -> list:
    """邮件标识 RText 列表: [管理员操作] [回退件] [过期]"""
    parts = []
    if mail.is_admin_pushed:
        parts.append(RText(" §d[管理员操作]§r"))
    if mail.is_rollback:
        parts.append(RText(" §6[回退件]§r"))
    if include_expired and mail.is_expired:
        parts.append(RText(" §c[过期]§r"))
    return parts


def mail_info(mail) -> RTextList:
    """邮件信息: #id 标题 (来自X, 时间) 附件摘要"""
    time_str = datetime.fromtimestamp(mail.time).strftime("%m-%d %H:%M") if mail.time else "?"
    info = RTextList()
    info.append(RText(" §7#{}§r ".format(mail.id)))
    info.append(RText("§f{}§r ".format(mail.title)))
    info.append(RText("§7(来自 §e{}§7, {}) ".format(mail.sender, time_str)))
    info.append(_attachment_summary(mail.attachments))
    return info


def paginate(items, page, size):
    """返回 (本页项, 钳后页码, 总页数, 总数)"""
    total = len(items)
    total_pages = max(1, (total + size - 1) // size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * size
    return items[start:start + size], page, total_pages, total


def nav_bar(nav_cmd: str, page: int, total_pages: int, click_action) -> RTextList:
    """翻页栏: [上一页] x/y [下一页]; nav_cmd 形如 '!!mmail list'"""
    nav = RTextList()
    if page > 1:
        prev_btn = RText("§a[上一页]", RColor.green)
        prev_btn.set_click_event(click_action, "{} {}".format(nav_cmd, page - 1))
        prev_btn.set_hover_text("§a第 {} 页".format(page - 1))
        nav.append(prev_btn)
    else:
        nav.append(RText("§8[上一页]", RColor.dark_gray))

    nav.append(RText(" §e{}§7/§e{} ".format(page, total_pages)))

    if page < total_pages:
        next_btn = RText("§a[下一页]", RColor.green)
        next_btn.set_click_event(click_action, "{} {}".format(nav_cmd, page + 1))
        next_btn.set_hover_text("§a第 {} 页".format(page + 1))
        nav.append(next_btn)
    else:
        nav.append(RText("§8[下一页]", RColor.dark_gray))
    return nav


# ============================================================
# !!mail user — 可发送对象
# ============================================================

def list_users(source: mcdr.CommandSource):
    """打印所有可发送邮件的对象 (真人注册表), 含自己; 点击名字可填入发送指令"""
    known = mail_lib.registry.known_players
    names = sorted(set(known.values()), key=str.lower)
    if not names:
        source.reply(TAG + "§7暂无可发送对象 (还没有玩家登录被登记)")
        return

    base = mail_lib.cmd("mail")
    self_name = source.player if source.is_player else None
    allow_self = mail_lib.config.allow_send_to_self

    source.reply("{:=^50}".format(" §b[MailMaple] 可发送对象 ({}) §r".format(len(names))))
    for name in names:
        is_self = self_name is not None and name.lower() == self_name.lower()
        status = "§a在线§r" if mail_lib.is_online(name) else "§7离线§r"

        name_text = RText(name, RColor.aqua)
        if not (is_self and not allow_self):
            name_text.set_click_event(RAction.suggest_command, "{} send {} ".format(base, name))
            name_text.set_hover_text("§a点击填入发送指令")

        line = RTextList("§f- ", name_text, " §7(", status, "§7)")
        if is_self:
            line.append("§6 [你自己]" + ("" if allow_self else " §8(已禁止自寄)"))
        source.reply(line)
    source.reply("{:=^50}".format(""))


# ============================================================
# !!mail list — 收件箱 (未过期)
# ============================================================

@mcdr.new_thread("MailMaple-list")
def list_mails(source: mcdr.CommandSource, context: dict = None):
    if not source.is_player:
        source.reply(TAG + "§c该命令只能由玩家执行")
        return

    player = source.player
    player_uuid = mail_lib.resolve_player_uuid(player)
    if player_uuid is None:
        player_uuid = mail_lib.get_player_uuid(player)
    if player_uuid is None:
        source.reply(TAG + "§c无法获取你的 UUID, 请重新进服后再试")
        return

    # 先把过期邮件移入过期列表
    mail_lib.scan_box_expired(player_uuid)

    box = mail_lib.mailboxes.get(player_uuid)
    if box is None or not box.mails:
        source.reply(TAG + "§7你的收件箱是空的")
        return

    base = mail_lib.cmd("mail")
    click_action = mail_lib.get_click_action()

    page = (context or {}).get("page", 1)
    page_mails, page, total_pages, total = paginate(box.mails, page, _size(mail_lib.config.list_page_size))

    source.reply("{:=^50}".format(
        " §b[MailMaple] 收件箱 (共{}封 第{}/{}页) §r".format(total, page, total_pages)))

    for mail in page_mails:
        line = RTextList()

        # 操作按钮统一放在最前面
        accept = RText("§a[接受]", RColor.green)
        accept.set_click_event(click_action, "{} accept {}".format(base, mail.id))
        accept.set_hover_text("§a点击接受这封邮件, 领取附件")
        line.append(accept)
        line.append(RText("  "))  # 接受与拒绝之间留点空

        if not mail.is_rollback:
            reject = RText("§c[拒绝]", RColor.red)
            reject.set_click_event(click_action, "{} reject {}".format(base, mail.id))
            reject.set_hover_text("§c点击拒绝, 附件退回发送者")
            line.append(reject)
        else:
            line.append(RText("§8[不可拒绝]", RColor.dark_gray))

        for m in markers(mail, include_expired=False):
            line.append(m)
        line.append(mail_info(mail))

        source.reply(line)

    if total_pages > 1:
        source.reply(nav_bar("{} list".format(base), page, total_pages, click_action))

    source.reply("{:=^50}".format(""))


# ============================================================
# !!mail expire list — 自己的过期邮件 (只读)
# ============================================================

@mcdr.new_thread("MailMaple-expire-list")
def expire_list(source: mcdr.CommandSource, context: dict = None):
    if not source.is_player:
        source.reply(TAG + "§c该命令只能由玩家执行")
        return

    player = source.player
    player_uuid = mail_lib.resolve_player_uuid(player)
    if player_uuid is None:
        player_uuid = mail_lib.get_player_uuid(player)
    if player_uuid is None:
        source.reply(TAG + "§c无法获取你的 UUID, 请重新进服后再试")
        return

    mail_lib.scan_box_expired(player_uuid)
    mails = mail_lib.expired_boxes.get(player_uuid) or []
    if not mails:
        source.reply(TAG + "§7你没有过期邮件")
        return

    base = mail_lib.cmd("mail")
    click_action = mail_lib.get_click_action()

    page = (context or {}).get("page", 1)
    page_mails, page, total_pages, total = paginate(mails, page, _size(mail_lib.config.expire_list_page_size))

    source.reply("{:=^50}".format(
        " §b[MailMaple] 过期邮件 (共{}封 第{}/{}页) §r".format(total, page, total_pages)))

    for mail in page_mails:
        line = RTextList()
        for m in markers(mail, include_expired=True):
            line.append(m)
        line.append(mail_info(mail))
        source.reply(line)

    if total_pages > 1:
        source.reply(nav_bar("{} expire list".format(base), page, total_pages, click_action))

    source.reply("{:=^50}".format(""))
