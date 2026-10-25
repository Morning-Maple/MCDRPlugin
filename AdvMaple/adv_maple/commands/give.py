"""
give.py — 分发库存给玩家

!!madv give                     全服在线玩家
!!madv give <玩家>               指定玩家
!!madv give <玩家> <成就id>      只分发单个成就

规则:
  - 只增不减: 只下发「库存有、目标没有」的差集, 从不撤销目标自己的成就。
  - 只处理在线玩家: 分发走 advancement grant 命令, 离线玩家无法写入。
"""
import os

import mcdreforged as mcdr

from .. import advancement
from .. import my_lib
from ..my_lib import TAG


def _get_stock_or_reply(source: mcdr.CommandSource):
    """取库存; 没有库存时已回复提示并返回 None"""
    stock = advancement.get_stock()
    if stock is None:
        source.reply(
            f"{TAG}§c当前没有任何库存, 请先执行 §6{my_lib.cmd('adv')} stock <玩家>"
        )
        return None
    return stock


def _is_online(player: str) -> bool:
    """是否在线 (忽略大小写)。

    走 my_lib.get_online_players() —— 它会实时查询 API 并用结果校正缓存,
    因此不会因为漏掉的离开事件把已离线玩家误判为在线。
    调用方必须在 @new_thread 中 (该查询是阻塞的)。
    """
    low = player.lower()
    return any(p.lower() == low for p in my_lib.get_online_players())


def _give_to_targets(source: mcdr.CommandSource, stock: dict, targets: list,
                     only_id: str = None):
    """把库存分发给一批目标玩家, 输出逐人结果与汇总。

    :param only_id: 非 None 时只分发该单个成就
    """
    # 目录体检: advancements_dir 不可用时, 每个目标的存档都「不存在」,
    # 若继续执行会把所有人当成零成就而灌入整份库存。必须先整体拦截。
    adv_dir = advancement.get_advancements_dir()
    if not os.path.isdir(adv_dir):
        source.reply(
            f"{TAG}§c分发已中止: 成就目录不可用\n"
            f"§7  查找路径: §f{adv_dir}\n"
            f"§7  请检查 §fadvancements_dir §7配置 (需指向服务端的 advancements 目录)"
        )
        return

    stock_ids = stock["ids"]
    lines = []
    processed = 0
    total_sent = 0
    total_failed = 0

    for target in targets:
        target_uuid = advancement.resolve_uuid(target)
        if not target_uuid:
            lines.append(f"  §c{target} §7跳过: 无法解析 UUID")
            continue

        # 目标可能是从未获得成就的新玩家 (服务端不会生成其存档文件)
        # → 文件不存在视为零成就; 但若文件存在却读不出来, 必须跳过,
        #   否则会把「读失败」误当成「零成就」而灌入整份库存。
        target_ids = advancement.read_player_advancements(target_uuid, missing_as_empty=True)
        if target_ids is None:
            lines.append(f"  §c{target} §7跳过: 成就存档读取失败 (不会按零成就处理)")
            continue

        if only_id is None:
            to_grant = advancement.compute_diff(stock_ids, target_ids)
        else:
            if only_id in target_ids:
                lines.append(f"  §7{target} §f已拥有 §e{only_id}§f, 无需分发")
                continue
            if only_id not in stock_ids:
                lines.append(f"  §c{target} §7跳过: 库存中没有 §e{only_id}")
                continue
            to_grant = [only_id]

        if not to_grant:
            lines.append(f"  §7{target} §f无需分发 §7(已拥有全部 {len(stock_ids)} 个成就)")
            continue

        sent, failed = advancement.grant(target, to_grant)
        total_sent += sent
        total_failed += failed
        processed += 1
        if only_id is None:
            lines.append(f"  §a{target} §f新增 §e{len(to_grant)} §f个成就")
        else:
            lines.append(f"  §a{target} §f新增 §e{only_id}")

    # ---- 输出 ----
    header = f"{TAG}§6分发完成: 库存来自 §e{stock['source']}§6 ({len(stock_ids)} 个成就)"
    if only_id is not None:
        header += f"§6 → §e{only_id}"
    source.reply(header)
    for line in lines:
        source.reply(line)

    summary = f"{TAG}§7共处理 §f{processed}§7 名玩家, 下发 §f{total_sent}§7 条 grant 命令"
    if total_failed:
        summary += f", §c{total_failed} 条下发异常"
    source.reply(summary)


# ============================================================
# !!madv give   (全服在线玩家)
# ============================================================

@mcdr.new_thread("AdvMaple-give")
def give_all(source: mcdr.CommandSource):
    """!!madv give — 把库存分发给全服在线玩家"""
    stock = _get_stock_or_reply(source)
    if stock is None:
        return

    targets = my_lib.get_online_players()
    if not targets:
        source.reply(f"{TAG}§7当前没有在线玩家, 无可分发对象")
        return

    source.reply(
        f"{TAG}§6开始分发: 库存 §e{stock['source']}§6 ({len(stock['ids'])} 个成就)"
        f" → §f{len(targets)} §6名在线玩家……"
    )
    _give_to_targets(source, stock, targets)


# ============================================================
# !!madv give <玩家>
# ============================================================

@mcdr.new_thread("AdvMaple-give")
def give_one(source: mcdr.CommandSource, context: dict):
    """!!madv give <玩家> — 把库存分发给指定玩家"""
    stock = _get_stock_or_reply(source)
    if stock is None:
        return

    target: str = context["target"]
    if not _is_online(target):
        source.reply(f"{TAG}§c玩家 §e{target} §c不在线 (本插件只处理在线玩家)")
        return

    _give_to_targets(source, stock, [target])


# ============================================================
# !!madv self   (自助增量同步: 玩家给自己补齐)
# ============================================================

@mcdr.new_thread("AdvMaple-self")
def self_sync(source: mcdr.CommandSource):
    """!!madv self — 玩家给自己增量补齐库存里的成就 (已有的跳过)。

    需要服务器开启 allow_self_sync 开关 (权限 3 可用 !!madv switch on 热更新)。
    """
    if not getattr(source, "is_player", False):
        source.reply(f"{TAG}§c该命令只能由玩家执行 (控制台请用 give <玩家>)")
        return

    if not my_lib.is_self_sync_allowed():
        source.reply(
            f"{TAG}§c自助同步当前未开放"
            f"\n§7  请管理员执行 §f{my_lib.cmd('adv')} switch on §7开启"
        )
        return

    stock = _get_stock_or_reply(source)
    if stock is None:
        return

    _give_to_targets(source, stock, [source.player])


# ============================================================
# !!madv give <玩家> <成就id>
# ============================================================

@mcdr.new_thread("AdvMaple-give")
def give_single(source: mcdr.CommandSource, context: dict):
    """!!madv give <玩家> <成就id> — 只分发单个成就"""
    stock = _get_stock_or_reply(source)
    if stock is None:
        return

    target: str = context["target"]
    adv_id: str = context["adv_id"]

    if adv_id not in stock["ids"]:
        source.reply(
            f"{TAG}§c库存中没有成就 §e{adv_id}"
            f"\n§7可用 §f{my_lib.cmd('adv')} stock §7查看库存明细"
        )
        return

    if not _is_online(target):
        source.reply(f"{TAG}§c玩家 §e{target} §c不在线 (本插件只处理在线玩家)")
        return

    _give_to_targets(source, stock, [target], only_id=adv_id)
