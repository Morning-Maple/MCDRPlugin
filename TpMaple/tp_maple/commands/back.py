"""
back.py — !!mback  回到上次死亡地点 (精确 / 安全传送)

传送流程由 teleport.TeleportService 提供, 本模块只负责定位 back 点、
选择传送方式 (精确 / 安全) 以及虚空降级判定。
"""
import mcdreforged as mcdr

from .. import my_lib
from .. import teleport as tp_core
from ..context import resolve_player
from ..my_lib import TAG

# 安全传送搜索半径 (格): 主动 back safe 用大范围, 虚空降级用小范围以贴近原点
SAFE_RADIUS = 64
VOID_FALLBACK_RADIUS = 8

# 成功提示模板 (服务负责填充 {dim_cn}/{x}/{y}/{z})
MSG_BACK_PRECISE = "§a已回到上一次的传送/死亡地点 §7— {dim_cn} ({x}, {y}, {z})"
MSG_BACK_SAFE = "§a已安全回到上一次的传送/死亡地点附近 §7— {dim_cn} ({x}, {y}, {z})"


@mcdr.new_thread("TpMaple-back")
def go_back(source: mcdr.CommandSource):
    """!!mback — 精确传送回死亡坐标"""
    _back_impl(source, safe=False)


@mcdr.new_thread("TpMaple-back")
def go_back_safe(source: mcdr.CommandSource):
    """!!mback safe — 安全传送 (spreadplayers) 到死亡点附近"""
    _back_impl(source, safe=True)


def _back_impl(source: mcdr.CommandSource, safe: bool):
    """back / back safe 的共用实现 (目标定位 + 传送方式选择)。

    :param safe: True 走安全传送 (spreadplayers); False 走精确传送,
                 但精确模式下若死亡点在虚空会自动降级为高精度安全传送。
    """
    ctx = resolve_player(source)
    if ctx is None:
        return

    # 先做冷却预检: 下面的流程会输出「正在查询死亡记录……」「已降级……」等过程性提示,
    # 若冷却中就不该让玩家看到这些 (与 home/wp/tpm 保持一致: 冷却优先于目标查询)。
    if not tp_core.service.ensure_ready(ctx, "back"):
        return

    # 取 back 目标点: 优先用运行时记录的传送/死亡点; 没有则回退实时查原版死亡点
    target = my_lib.get_back_point(ctx.name)
    if target is not None:
        x, y, z, dimension = target["x"], target["y"], target["z"], target["dimension"]
    else:
        ctx.reply(f"{TAG}§6正在查询死亡记录……")
        death = my_lib.get_player_last_death_position(ctx.name)
        if death is None:
            ctx.reply(f"{TAG}§c没有可返回的传送或死亡地点")
            return
        x, y, z, dimension = death

    # 精确模式下, 若目标点在虚空高度则强制降级为高精度安全传送, 避免回去再次坠亡
    void_fallback = (not safe) and _is_void_death(dimension, y)
    if void_fallback:
        ctx.reply(f"{TAG}§e精确传送不可用，已降级使用高精度安全传送替代")

    tp_target = tp_core.TpTarget(
        x=x, y=y, z=z, dimension=dimension,
        feature="back",
        label="back点",
    )

    if safe or void_fallback:
        tp_target.success_msg = MSG_BACK_SAFE
        tp_core.service.safe(
            ctx, tp_target,
            radius=VOID_FALLBACK_RADIUS if void_fallback else SAFE_RADIUS,
        )
    else:
        tp_target.success_msg = MSG_BACK_PRECISE
        tp_core.service.precise(ctx, tp_target)


def _is_void_death(dimension: str, y: float) -> bool:
    """判断死亡点是否在虚空高度 (精确传送回去会再次坠亡)

    主世界 y < -128, 地狱/末地 y < -64 时视为虚空。
    """
    if dimension == "minecraft:overworld":
        return y < -128
    if dimension in ("minecraft:the_nether", "minecraft:the_end"):
        return y < -64
    return False
