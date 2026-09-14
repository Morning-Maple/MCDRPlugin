"""
handle.py — !!mail accept / reject / cancel
"""
import time

import mcdreforged as mcdr
from mcdreforged.api.rtext import RTextList

from .. import mail_lib
from .. import item_util
from ..config import MailItem

TAG = mail_lib.TAG


def _is_expired_of(player_uuid: str, mail_id: str) -> bool:
    """该邮件是否在此玩家的过期列表里"""
    return any(m.id == mail_id for m in mail_lib.expired_boxes.get(player_uuid, []))


def _own_uuid(source: mcdr.CommandSource):
    """获取命令玩家自己的 UUID"""
    player = source.player
    u = mail_lib.resolve_player_uuid(player)
    if u is None:
        u = mail_lib.get_player_uuid(player)
    return u


# ============================================================
# !!mail accept <id>
# ============================================================

@mcdr.new_thread("MailMaple-accept")
def accept_mail(source: mcdr.CommandSource, context: dict):
    if not source.is_player:
        source.reply(TAG + "§c该命令只能由玩家执行")
        return

    mail_id = context["mail_id"]
    player_uuid = _own_uuid(source)
    if player_uuid is None:
        source.reply(TAG + "§c无法获取你的 UUID, 请重新进服后再试")
        return

    mail_lib.scan_box_expired(player_uuid)
    box, mail = mail_lib.find_mail_in_box(player_uuid, mail_id)
    if mail is None:
        if _is_expired_of(player_uuid, mail_id):
            source.reply(TAG + "§c该邮件已过期, 无法接受, 请联系管理员处理")
        else:
            source.reply(TAG + "§c未找到邮件 §7#{}".format(mail_id))
        return

    # 事务: 先发放成功, 再删邮件; 发放失败则邮件保留 (附件不丢失)
    try:
        item_util.give_attachments(source.player, mail.attachments)
    except Exception as e:
        mail_lib._log("发放附件失败, 邮件保留: {}".format(e))
        source.reply(TAG + "§c发放附件失败, 邮件已保留, 请稍后重试")
        return

    with mail_lib.lock():
        if mail in box.mails:
            box.mails.remove(mail)
    mail_lib.save_player(player_uuid)

    source.reply(
        TAG + "§a已接受邮件 §7#{} §a(来自 §e{}§a), 附件 §6{} §a件已发放".format(
            mail_id, mail.sender, len(mail.attachments)
        )
    )


# ============================================================
# !!mail reject <id>  -> 生成回退邮件退回发送者
# ============================================================

@mcdr.new_thread("MailMaple-reject")
def reject_mail(source: mcdr.CommandSource, context: dict):
    if not source.is_player:
        source.reply(TAG + "§c该命令只能由玩家执行")
        return

    mail_id = context["mail_id"]
    player_uuid = _own_uuid(source)
    if player_uuid is None:
        source.reply(TAG + "§c无法获取你的 UUID, 请重新进服后再试")
        return

    mail_lib.scan_box_expired(player_uuid)
    box, mail = mail_lib.find_mail_in_box(player_uuid, mail_id)
    if mail is None:
        if _is_expired_of(player_uuid, mail_id):
            source.reply(TAG + "§c该邮件已过期, 无法拒绝, 请联系管理员处理")
        else:
            source.reply(TAG + "§c未找到邮件 §7#{}".format(mail_id))
        return
    if mail.is_rollback:
        source.reply(TAG + "§c回退邮件不可拒绝, 只能接受")
        return

    # 退回给原发送者
    sender_uuid = mail_lib.resolve_player_uuid(mail.sender)
    if sender_uuid is None:
        source.reply(TAG + "§c原发送者 §e{} §c已不可识别, 无法退回".format(mail.sender))
        return

    # 锁内原子: 移除原邮件 + 检查发件人容量 + 生成回退件 + 追加; 容量满则整体回滚
    rollback = None
    full = False
    already = False
    with mail_lib.lock():
        if mail not in box.mails:
            already = True
        else:
            box.mails.remove(mail)
            sender_box = mail_lib.get_mailbox(sender_uuid, mail.sender)
            if mail_lib.mailbox_full(sender_box):
                box.mails.append(mail)  # 回滚: 原邮件保留
                full = True
            else:
                rollback = MailItem(
                    id=mail_lib.gen_mail_id(),
                    time=time.time(),
                    title=mail.title,
                    sender=source.player,
                    receiver=mail.sender,
                    is_rollback=True,
                    attachments=list(mail.attachments),
                )
                sender_box.mails.append(rollback)

    if already:
        source.reply(TAG + "§c该邮件已被处理")
        return
    if full:
        source.reply(TAG + "§c原发送者邮箱已满, 无法退回, 邮件已保留")
        return

    # 自己收件箱 (移除) + 发件人收件箱 (新增回退件) + 注册表 (编号计数)
    mail_lib.save_player(player_uuid)
    mail_lib.save_player(sender_uuid)
    mail_lib.save_registry()

    source.reply(TAG + "§c已拒绝邮件 §7#{}§c, 附件已退回 §e{}".format(mail_id, mail.sender))

    if mail_lib.is_online(mail.sender):
        mail_lib.plugin_server.tell(
            mail.sender,
            RTextList(
                TAG,
                "§e{} §c拒绝了你的邮件 §f{}§c, 物品已退回 (邮件id §7{}§c) ".format(
                    source.player, mail.title, rollback.id
                ),
                mail_lib.view_list_button(),
            ),
        )


# ============================================================
# !!mail cancel <id>  -> 取消自己发出的、对方未处理的邮件
# ============================================================

@mcdr.new_thread("MailMaple-cancel")
def cancel_mail(source: mcdr.CommandSource, context: dict):
    if not source.is_player:
        source.reply(TAG + "§c该命令只能由玩家执行")
        return

    mail_id = context["mail_id"]
    box_uuid, box, mail = mail_lib.find_sent_mail(source.player, mail_id)
    if mail is None:
        source.reply(TAG + "§c未找到你发出的邮件 §7#{} §c(可能对方已处理)".format(mail_id))
        return

    # 事务: 先发放成功, 再删邮件; 发放失败则邮件保留
    try:
        item_util.give_attachments(source.player, mail.attachments)
    except Exception as e:
        mail_lib._log("退还附件失败, 邮件保留: {}".format(e))
        source.reply(TAG + "§c退还附件失败, 邮件已保留, 请稍后重试")
        return

    with mail_lib.lock():
        if mail in box.mails:
            box.mails.remove(mail)
    mail_lib.save_player(box_uuid)

    source.reply(
        TAG + "§a已取消邮件 §7#{} §a(原收件人 §e{}§a), 附件已退回你".format(mail_id, mail.receiver)
    )
