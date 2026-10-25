"""
stock.py — 库存相关: 抓取 / 查看 / 明细

!!madv stock <玩家>  抓取
!!madv stock         查看概要
!!madv stock [页]    查看明细 (分页)
"""
import time

import mcdreforged as mcdr

from .. import advancement
from .. import my_lib
from ..my_lib import TAG
from ..pagination import Paginator


def _format_time(ts) -> str:
    """时间戳 -> 'YYYY-MM-DD HH:MM'; 缺失或非法返回 '未知'"""
    if not ts:
        return "未知"
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(ts)))
    except (TypeError, ValueError, OverflowError, OSError):
        return "未知"


# 抓取时会被子命令遮蔽的玩家名 (小写)。
# MCDR 解析时字面量子命令优先于参数, 所以叫 list 的玩家无法通过
# !!madv stock list 抓取 (会被当成查看明细), 创建时明确拒绝。
RESERVED_PLAYER_NAMES = {"list"}


# ============================================================
# !!madv stock <玩家>   抓取
# ============================================================

@mcdr.new_thread("AdvMaple-stock")
def grab_stock(source: mcdr.CommandSource, context: dict):
    """!!madv stock <玩家> — 抓取该玩家已完成的成就作为库存 (覆盖旧库存)"""
    player: str = (context.get("player") or "").strip()
    if not player:
        source.reply(f"{TAG}§c玩家名不能为空")
        return

    if player.lower() in RESERVED_PLAYER_NAMES:
        source.reply(
            f"{TAG}§c“{player}”与 §f{my_lib.cmd('adv')} stock list §c冲突, 无法用该名字抓取"
        )
        return

    ok, result = advancement.grab(player)
    if not ok:
        source.reply(f"{TAG}§c抓取失败: §f{result}")
        return

    count = result
    source.reply(
        f"{TAG}§a库存已更新: §e{player} §7— 共 §f{count} §7个成就"
        f"\n§8  用 §7{my_lib.cmd('adv')} stock §8查看明细, "
        f"§7{my_lib.cmd('adv')} give §8分发给玩家"
    )


# ============================================================
# !!madv stock [页]   查看
# ============================================================

@mcdr.new_thread("AdvMaple-stock")
def show_stock(source: mcdr.CommandSource, context: dict = None):
    """!!madv stock [页] — 查看库存概要; 带页码时显示成就明细"""
    stock = advancement.get_stock()
    if stock is None:
        source.reply(
            f"{TAG}§7当前没有任何库存, 使用 §f{my_lib.cmd('adv')} stock <玩家> §7抓取"
        )
        return

    page = (context or {}).get("page")

    # 概要行: 来源 / 数量 / 抓取时间
    source.reply(
        f"{TAG}§6当前库存: §e{stock['source']} §7— 共 §f{len(stock['ids'])} §7个成就"
        f"  §8| §7抓取于 §f{_format_time(stock.get('created_at'))}"
    )

    # 明细 (分页)
    pg = Paginator(
        stock["ids"],
        my_lib.get_list_page_size(),
        page if page is not None else 1,
    )
    for adv_id in pg.items:
        source.reply(f"  §7· §f{adv_id}")

    if pg.max_page > 1:
        source.reply(pg.controls(f"{my_lib.cmd('adv')} stock list"))
