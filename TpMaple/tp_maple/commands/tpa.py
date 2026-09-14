"""
tpa.py — !!mtpa / !!mtpahere / !!mtpaccept / !!mtpacancel

请求栈模型:
  tpa_stacks[目标玩家名] = [ TpaRequest, ... ]
  栈顶 = 最新一条请求
  accept/cancel 操作栈顶 (后进先出)

请求超时:
  每条请求带 created_at 时间戳, accept/cancel 时检测是否过期
"""
import time
from dataclasses import dataclass, field

import mcdreforged as mcdr
from mcdreforged.api.rtext import RText, RTextList, RColor

from .. import my_lib
from .. import teleport as tp_core

TAG = "§b[TpMaple] "


# ============================================================
# 数据结构
# ============================================================

@dataclass
class TpaRequest:
    """一条 tpa 请求"""
    requester: str          # 发起请求的玩家名
    target: str             # 被请求的玩家名
    req_type: str           # "tpa" 或 "tpahere"
    created_at: float = field(default_factory=time.time)
    # tpa:     requester 传送到 target 的位置
    # tpahere: target 传送到 requester 的位置


# tpa_stacks[被请求玩家名] = [TpaRequest, ...]  (栈: 末尾=栈顶)
tpa_stacks: dict[str, list[TpaRequest]] = {}


# ============================================================
# 工具函数
# ============================================================

def _is_expired(req: TpaRequest) -> bool:
    """判断单条请求是否过期; timeout <= 0 视为永不过期"""
    timeout = my_lib.get_tpa_timeout()
    if timeout <= 0:
        return False
    return time.time() - req.created_at > timeout


def _clean_expired(player: str):
    """清理指定玩家栈中已过期的请求"""
    stack = tpa_stacks.get(player, [])
    tpa_stacks[player] = [r for r in stack if not _is_expired(r)]


def clear_player_requests(player: str):
    """清理以该玩家为目标的请求栈 (玩家离线时调用), 防止内存泄漏。

    只删目标方的栈即可；
    由该玩家发起、散落在他人栈中的请求,会在对应目标玩家离线时一并清理。
    """
    tpa_stacks.pop(player, None)


def _tell(player_name: str, msg: str):
    """用 tellraw 给指定在线玩家发消息"""
    server = my_lib.plugin_server
    # 转义双引号
    safe = msg.replace("\\", "\\\\").replace('"', '\\"')
    server.execute(f'tellraw {player_name} {{"text":"{safe}"}}')


def _tell_request_prompt(player_name: str, prefix_msg: str):
    """向玩家发送带 [同意]/[拒绝] 可点击按钮的传送请求提示。

    点击按钮会自动执行对应的 tpaccept / tpacancel 命令。
    """
    accept_cmd = my_lib.cmd("tpaccept")
    cancel_cmd = my_lib.cmd("tpacancel")
    click_action = my_lib.get_click_action()
    message = RTextList(
        prefix_msg,
        "  ",
        RText("[同意]", color=RColor.green)
        .c(click_action, accept_cmd)
        .h(accept_cmd),
        "  ",
        RText("[拒绝]", color=RColor.red)
        .c(click_action, cancel_cmd)
        .h(cancel_cmd),
    )
    my_lib.plugin_server.tell(player_name, message)


# ============================================================
# !!mtpa <player>
# ============================================================

@mcdr.new_thread("TpMaple-tpa")
def tpa(source: mcdr.CommandSource, context: dict):
    """!!mtpa <玩家>: 发起"我传送到对方"的请求, 压入对方的请求栈。"""
    if not source.is_player:
        source.reply(f"{TAG}§c该命令只能由玩家执行")
        return

    requester = source.player
    target: str = context["target_player"]

    if requester == target:
        source.reply(f"{TAG}§c你不能对自己发起传送请求")
        return

    # 检查目标是否在线
    online = my_lib.get_server_player_list()
    if target not in online:
        source.reply(f"{TAG}§c玩家 §e{target} §c不在线")
        return

    # 发起方 CD 检查
    req_uuid = my_lib.get_player_uuid(requester)
    if req_uuid is not None:
        remain = my_lib.check_cd(req_uuid, "tpa")
        if remain > 0:
            source.reply(f"{TAG}§c传送冷却中, 还需等待 §6{remain}§c 秒")
            return

    req = TpaRequest(requester=requester, target=target, req_type="tpa")
    tpa_stacks.setdefault(target, []).append(req)

    source.reply(f"{TAG}§a传送请求已发给 §e{target}")
    _tell_request_prompt(target, f"{TAG}§e{requester} §6请求传送到你的位置")


# ============================================================
# !!mtpahere <player>
# ============================================================

@mcdr.new_thread("TpMaple-tpahere")
def tpa_here(source: mcdr.CommandSource, context: dict):
    """!!mtpahere <玩家>: 发起"对方传送到我"的请求, 压入对方的请求栈。"""
    if not source.is_player:
        source.reply(f"{TAG}§c该命令只能由玩家执行")
        return

    requester = source.player
    target: str = context["target_player"]

    if requester == target:
        source.reply(f"{TAG}§c你不能对自己发起传送请求")
        return

    online = my_lib.get_server_player_list()
    if target not in online:
        source.reply(f"{TAG}§c玩家 §e{target} §c不在线")
        return

    # 发起方 CD 检查
    req_uuid = my_lib.get_player_uuid(requester)
    if req_uuid is not None:
        remain = my_lib.check_cd(req_uuid, "tpa")
        if remain > 0:
            source.reply(f"{TAG}§c传送冷却中, 还需等待 §6{remain}§c 秒")
            return

    req = TpaRequest(requester=requester, target=target, req_type="tpahere")
    tpa_stacks.setdefault(target, []).append(req)

    source.reply(f"{TAG}§a已请求 §e{target} §a传送到你的位置")
    _tell_request_prompt(target, f"{TAG}§e{requester} §6请求§c你传送到TA§6的位置")


# ============================================================
# !!mtpaccept
# ============================================================

@mcdr.new_thread("TpMaple-tpaccept")
def tp_accept(source: mcdr.CommandSource):
    """!!mtpaccept: 同意自己栈顶 (最新) 的一条请求, 按类型执行延迟传送。"""
    if not source.is_player:
        source.reply(f"{TAG}§c该命令只能由玩家执行")
        return

    player = source.player
    _clean_expired(player)

    stack = tpa_stacks.get(player, [])
    if not stack:
        source.reply(f"{TAG}§7没有待处理的传送请求")
        return

    req = stack.pop()  # 栈顶 (最新一条)

    # 超时再检一次 (理论上 _clean_expired 已清, 保险)
    if _is_expired(req):
        source.reply(f"{TAG}§c该请求已超时")
        return

    # 记录发起方 CD
    req_uuid = my_lib.get_player_uuid(req.requester)
    if req_uuid is not None:
        my_lib.record_cd(req_uuid, "tpa")

    delay = my_lib.get_tp_delay()

    if req.req_type == "tpa":
        # tpa: requester 传送到 target (当前玩家) 的位置
        # B(当前) 收到: 已同意A的传送请求
        source.reply(f"{TAG}§a已同意 §e{req.requester} §a的传送请求")
        # A 收到: B同意了您的传送请求[, 请勿移动, 将在x秒后开始传送]
        if delay > 0:
            _tell(req.requester,
                  f"{TAG}§e{player} §a同意了您的传送请求, 请勿移动, 将在 §6{delay} §a秒后开始传送")
        else:
            _tell(req.requester, f"{TAG}§e{player} §a同意了您的传送请求")
        tp_core.delayed_teleport(
            source_player=req.requester,
            target_player=player,
        )
    elif req.req_type == "tpahere":
        # tpahere: target (当前玩家) 传送到 requester 的位置
        # A 收到: B已同意您的传送请求
        _tell(req.requester, f"{TAG}§e{player} §a已同意您的传送请求")
        # B(当前) 收到: 已同意传送请求[, 请勿移动, 将在x秒后开始传送]
        if delay > 0:
            source.reply(
                f"{TAG}§a已同意传送请求, 请勿移动, 将在 §6{delay} §a秒后开始传送")
        else:
            source.reply(f"{TAG}§a已同意传送请求")
        tp_core.delayed_teleport(
            source_player=player,
            target_player=req.requester,
        )
    else:
        source.reply(f"{TAG}§c未知请求类型: {req.req_type}")
        return


# ============================================================
# !!mtpacancel
# ============================================================

def tpa_cancel(source: mcdr.CommandSource):
    """!!mtpacancel: 拒绝自己栈顶 (最新) 的一条请求, 并通知发起方。"""
    if not source.is_player:
        source.reply(f"{TAG}§c该命令只能由玩家执行")
        return

    player = source.player
    _clean_expired(player)

    stack = tpa_stacks.get(player, [])
    if not stack:
        source.reply(f"{TAG}§7没有待处理的传送请求")
        return

    req = stack.pop()  # 拒绝栈顶
    source.reply(f"{TAG}§c已拒绝 §e{req.requester} §c的传送请求")
    _tell(req.requester, f"{TAG}§c{player} §c拒绝了你的传送请求")