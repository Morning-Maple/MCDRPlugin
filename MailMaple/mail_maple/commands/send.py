"""
send.py — !!mail send <目标玩家> <标题> [附件]
"""
import time

import mcdreforged as mcdr

from .. import mail_lib
from .. import item_util
from ..config import MailItem

TAG = mail_lib.TAG


@mcdr.new_thread("MailMaple-send")
def send_mail(source: mcdr.CommandSource, context: dict):
    if not source.is_player:
        source.reply(TAG + "§c该命令只能由玩家执行")
        return

    sender = source.player
    target: str = context["target_player"]
    title: str = context["title"]
    attach_arg: str = context.get("attach", "")

    # 是否允许给自己发邮件
    if not mail_lib.config.allow_send_to_self and target.lower() == sender.lower():
        source.reply(TAG + "§c不允许给自己发送邮件")
        return

    # 目标真人校验
    target_uuid = mail_lib.resolve_player_uuid(target)
    if target_uuid is None:
        source.reply(TAG + "§c玩家 §e{} §c从未登录过服务器, 无法发送".format(target))
        return
    # 用注册表里记录的规范名作为接收者名
    target_name = mail_lib.registry.known_players.get(target_uuid, target)

    # 邮箱容量校验
    box = mail_lib.get_mailbox(target_uuid, target_name)
    max_count = mail_lib.config.default_mail_max
    if max_count > 0 and len(box.mails) >= max_count:
        source.reply(TAG + "§c对方邮箱已满 (上限 §6{}§c), 无法发送".format(max_count))
        return

    # 解析附件参数
    try:
        slot_spec = item_util.parse_slot_arg(attach_arg)
    except ValueError as e:
        source.reply(TAG + "§c{}".format(e))
        return

    # 读取物品
    attachments, used_slots = item_util.collect_attachments(sender, slot_spec)
    if not attachments:
        source.reply(TAG + "§c没有可发送的物品 (指定的格子是空的)")
        return

    # 显式指定格子列表时, 提示哪些格子为空被跳过 (便于排查)
    if isinstance(slot_spec, list):
        empty = sorted(s + 1 for s in slot_spec if s not in used_slots)
        if empty:
            source.reply(
                TAG + "§7提示: 以下格子为空, 已跳过: §e{}".format(", ".join(map(str, empty)))
            )

    # 扣除物品成功才算发送成功
    item_util.deduct_slots(sender, used_slots)

    online = mail_lib.is_online(target_name)
    mail = MailItem(
        id=mail_lib.gen_mail_id(),
        time=time.time(),
        title=title,
        sender=sender,
        receiver=target_name,
        is_rollback=False,
        # 在线即时推送通知, 因此不再算"新邮件"; 离线则保持 is_new 待上线汇总
        is_new=not online,
        attachments=attachments,
    )
    box.mails.append(mail)
    # 只写目标玩家分片 + 注册表 (gen_mail_id 变更了编号计数)
    mail_lib.save_player(target_uuid)
    mail_lib.save_registry()

    source.reply(
        TAG + "§a邮件已发送给 §e{} §a(附件 §6{} §a件), 邮件id: §7{}".format(
            target_name, len(attachments), mail.id
        )
    )

    # 在线则即时通知对方
    if online:
        mail_lib.notify_received_online(target_name, sender, box)
