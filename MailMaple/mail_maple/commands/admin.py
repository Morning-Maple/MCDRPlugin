"""
admin.py — 可发送对象 / 黑名单管理

  !!mail user add <玩家>     添加可发送对象 (要求该玩家在线)
  !!mail user remove <玩家>  移出可发送对象, 并加入精确黑名单
  !!mail black               查看精确名字黑名单
  !!mail black add <玩家>    加入黑名单 (并立即移出可发送对象)
  !!mail black remove <玩家> 移出黑名单
"""
import time

import mcdreforged as mcdr
from mcdreforged.api.rtext import RText, RTextList, RColor

from .. import mail_lib
from .. import item_util
from . import mail_list as ml

TAG = mail_lib.TAG


@mcdr.new_thread("MailMaple-user-add")
def user_add(source: mcdr.CommandSource, context: dict):
    name = context["name"]
    if not mail_lib.is_online(name):
        source.reply(TAG + "§c玩家 §e{} §c不在线; 添加可发送对象要求该玩家在线".format(name))
        return
    player_uuid = mail_lib.get_player_uuid(name)
    if player_uuid is None:
        source.reply(TAG + "§c无法获取 §e{} §c的 UUID, 添加失败".format(name))
        return
    # 用在线集合里记录的真实名 (大小写以实际为准)
    real_name = next((p for p in mail_lib.online_players if p.lower() == name.lower()), name)
    mail_lib.registry.known_players[player_uuid] = real_name
    mail_lib.remove_name_from(mail_lib.config.bot_list, real_name)  # 若在黑名单则解除
    mail_lib.save_registry()   # known_players 变更
    mail_lib.save_settings()   # bot_list 可能变更
    source.reply(TAG + "§a已将 §e{} §a加入可发送对象".format(real_name))


def user_remove(source: mcdr.CommandSource, context: dict):
    name = context["name"]
    player_uuid = mail_lib.resolve_player_uuid(name)
    if player_uuid is None:
        source.reply(TAG + "§c可发送对象中没有 §e{}".format(name))
        return
    real_name = mail_lib.registry.known_players.pop(player_uuid, name)
    # 加入精确黑名单, 防止自动重新登记
    if not mail_lib.name_in_list(real_name, mail_lib.config.bot_list):
        mail_lib.config.bot_list.append(real_name)
    mail_lib.save_registry()   # known_players 变更
    mail_lib.save_settings()   # bot_list 变更
    source.reply(TAG + "§a已将 §e{} §a移出可发送对象, 并加入黑名单".format(real_name))


def black_list(source: mcdr.CommandSource):
    bot_list = mail_lib.config.bot_list
    if not bot_list:
        source.reply(TAG + "§7精确名字黑名单为空")
        return
    source.reply(TAG + "§7精确名字黑名单 (§6{}§7): §e{}".format(len(bot_list), ", ".join(bot_list)))


def black_add(source: mcdr.CommandSource, context: dict):
    name = context["name"]
    if mail_lib.name_in_list(name, mail_lib.config.bot_list):
        source.reply(TAG + "§7§e{} §7已在黑名单中".format(name))
        return
    mail_lib.config.bot_list.append(name)
    # 同时移出可发送对象 (立即生效)
    player_uuid = mail_lib.resolve_player_uuid(name)
    extra = ""
    if player_uuid is not None:
        mail_lib.registry.known_players.pop(player_uuid, None)
        extra = " 并移出可发送对象"
        mail_lib.save_registry()
    mail_lib.save_settings()   # bot_list 变更
    source.reply(TAG + "§a已将 §e{} §a加入黑名单{}".format(name, extra))


def black_remove(source: mcdr.CommandSource, context: dict):
    name = context["name"]
    if not mail_lib.name_in_list(name, mail_lib.config.bot_list):
        source.reply(TAG + "§7§e{} §7不在黑名单中".format(name))
        return
    mail_lib.remove_name_from(mail_lib.config.bot_list, name)
    mail_lib.save_settings()   # bot_list 变更
    source.reply(TAG + "§a已将 §e{} §a移出黑名单 (下次上线/重载将按规则重新判定)".format(name))


# ============================================================
# 过期邮件管理: check expire / expire push / expire return
# ============================================================

def check_expire(source: mcdr.CommandSource, context: dict):
    """管理员查看指定玩家的过期邮件 (带操作按钮)"""
    name = context["name"]
    player_uuid = mail_lib.resolve_player_uuid(name)
    if player_uuid is None:
        source.reply(TAG + "§c找不到玩家 §e{} §c(从未登录过)".format(name))
        return
    mail_lib.scan_box_expired(player_uuid)
    mails = mail_lib.expired_boxes.get(player_uuid) or []
    real_name = mail_lib.registry.known_players.get(player_uuid, name)
    if not mails:
        source.reply(TAG + "§7玩家 §e{} §7没有过期邮件".format(real_name))
        return

    base = mail_lib.cmd("mail")
    click = mail_lib.get_click_action()
    page = (context or {}).get("page", 1)
    page_mails, page, total_pages, total = ml.paginate(
        mails, page, ml._size(mail_lib.config.admin_expire_list_page_size))

    source.reply("{:=^50}".format(
        " §b[MailMaple] {} 的过期邮件 (共{}封 第{}/{}页) §r".format(real_name, total, page, total_pages)))

    for mail in page_mails:
        line = RTextList()

        ret = RText("§6[回退]", RColor.gold)
        ret.set_click_event(click, "{} expire return {}".format(base, mail.id))
        ret.set_hover_text("§6作为回退件退回发件人 (进其收件箱)")
        line.append(ret)
        line.append(RText(" "))

        ret_f = RText("§c[强制回退]", RColor.red)
        ret_f.set_click_event(click, "{} expire return {} force".format(base, mail.id))
        ret_f.set_hover_text("§c直接把附件发给发件人 (需其在线)")
        line.append(ret_f)
        line.append(RText(" "))

        push = RText("§a[重发]", RColor.green)
        push.set_click_event(click, "{} expire push {}".format(base, mail.id))
        push.set_hover_text("§a重新发回目标玩家收件箱")
        line.append(push)
        line.append(RText(" "))

        push_f = RText("§2[强制重发]", RColor.dark_green)
        push_f.set_click_event(click, "{} expire push {} force".format(base, mail.id))
        push_f.set_hover_text("§2直接把附件发给目标玩家 (需其在线)")
        line.append(push_f)

        for m in ml.markers(mail, include_expired=True):
            line.append(m)
        line.append(ml.mail_info(mail))
        source.reply(line)

    if total_pages > 1:
        source.reply(ml.nav_bar("{} check expire {}".format(base, real_name), page, total_pages, click))

    source.reply("{:=^50}".format(""))


def _resolve_target(name: str):
    """按名字解析 (uuid, 规范名); 失败返回 (None, name)"""
    player_uuid = mail_lib.resolve_player_uuid(name)
    if player_uuid is None:
        return None, name
    return player_uuid, mail_lib.registry.known_players.get(player_uuid, name)


def _expire_push(source: mcdr.CommandSource, context: dict, force: bool):
    mail_id = context["mail_id"]
    mail_lib.scan_all_expired()
    src_uuid, mail = mail_lib.find_expired_mail(mail_id)
    if mail is None:
        source.reply(TAG + "§c未找到过期邮件 §7#{}".format(mail_id))
        return

    target_uuid, target_name = _resolve_target(mail.receiver)
    if target_uuid is None:
        source.reply(TAG + "§c目标玩家 §e{} §c未登记, 无法重发".format(mail.receiver))
        return

    if force:
        if not mail_lib.is_online(target_name):
            source.reply(TAG + "§c目标玩家 §e{} §c当前不在线, 无法强制重发 (force 需对方在线)".format(target_name))
            return
        item_util.give_attachments(target_name, mail.attachments)
        mail_lib.remove_expired_mail(src_uuid, mail)
        mail_lib.save_player(src_uuid)
        source.reply(TAG + "§a已强制重发: 附件已直接发放给 §e{}".format(target_name))
        return

    box = mail_lib.get_mailbox(target_uuid, target_name)
    if not mail_lib.config.admin_ignore_mail_max and mail_lib.mailbox_full(box):
        source.reply(TAG + "§c目标邮箱已满, 重发失败 (可开启 admin_ignore_mail_max)")
        return

    mail_lib.remove_expired_mail(src_uuid, mail)
    online = mail_lib.is_online(target_name)
    mail.time = time.time()
    mail.is_expired = False
    mail.is_admin_pushed = True
    mail.is_new = not online
    box.mails.append(mail)
    # src_uuid: 过期件原属玩家分片 (已移除); target_uuid: 目标玩家分片 (已新增)
    mail_lib.save_players([src_uuid, target_uuid])
    source.reply(TAG + "§a已重发给 §e{} §a(邮件id §7{}§a)".format(target_name, mail.id))
    if online:
        mail_lib.notify_received_online(target_name, mail.sender, box)


def _expire_return(source: mcdr.CommandSource, context: dict, force: bool):
    mail_id = context["mail_id"]
    mail_lib.scan_all_expired()
    src_uuid, mail = mail_lib.find_expired_mail(mail_id)
    if mail is None:
        source.reply(TAG + "§c未找到过期邮件 §7#{}".format(mail_id))
        return

    sender_uuid, sender_name = _resolve_target(mail.sender)
    if sender_uuid is None:
        source.reply(TAG + "§c发件人 §e{} §c未登记, 无法退回".format(mail.sender))
        return

    if force:
        if not mail_lib.is_online(sender_name):
            source.reply(TAG + "§c发件人 §e{} §c当前不在线, 无法强制退回 (force 需对方在线)".format(sender_name))
            return
        item_util.give_attachments(sender_name, mail.attachments)
        mail_lib.remove_expired_mail(src_uuid, mail)
        mail_lib.save_player(src_uuid)
        source.reply(TAG + "§a已强制退回: 附件已直接发放给 §e{}".format(sender_name))
        return

    box = mail_lib.get_mailbox(sender_uuid, sender_name)
    if not mail_lib.config.admin_ignore_mail_max and mail_lib.mailbox_full(box):
        source.reply(TAG + "§c发件人邮箱已满, 退回失败 (可开启 admin_ignore_mail_max)")
        return

    mail_lib.remove_expired_mail(src_uuid, mail)
    online = mail_lib.is_online(sender_name)
    original_receiver = mail.receiver
    mail.time = time.time()
    mail.is_expired = False
    mail.is_admin_pushed = True
    mail.is_rollback = True
    mail.sender = original_receiver   # 退回件: 来自原收件人
    mail.receiver = sender_name       # 退回给原发件人
    mail.is_new = not online
    box.mails.append(mail)
    # src_uuid: 过期件原属玩家分片 (已移除); sender_uuid: 发件人分片 (已新增退回件)
    mail_lib.save_players([src_uuid, sender_uuid])
    source.reply(TAG + "§a已退回给 §e{} §a(邮件id §7{}§a)".format(sender_name, mail.id))
    if online:
        mail_lib.notify_received_online(sender_name, mail.sender, box)


def expire_push(source: mcdr.CommandSource, context: dict):
    _expire_push(source, context, force=False)


def expire_push_force(source: mcdr.CommandSource, context: dict):
    _expire_push(source, context, force=True)


def expire_return(source: mcdr.CommandSource, context: dict):
    _expire_return(source, context, force=False)


def expire_return_force(source: mcdr.CommandSource, context: dict):
    _expire_return(source, context, force=True)
