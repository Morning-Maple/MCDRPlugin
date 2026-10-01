"""
tp.py — !!tpm <x> <y> <z> [dimension]  传送到指定坐标

传送流程由 teleport.TeleportService 提供, 本模块只负责解析参数与校验维度。
"""
import mcdreforged as mcdr

from .. import my_lib
from .. import teleport as tp_core
from ..context import resolve_player
from ..my_lib import TAG
from ..default_config import DIMENSION_NAMES


@mcdr.new_thread("TpMaple-tpm")
def tp_to_pos(source: mcdr.CommandSource, context: dict):
    """!!tpm <x> <y> <z> [维度]: 传送到指定坐标。

    维度为可选参数, 省略时使用玩家当前所在维度; 受 tpm 冷却限制。
    """
    ctx = resolve_player(source)
    if ctx is None:
        return

    # 冷却预检: 先于维度解析, 保证「冷却中」优先于「未知维度」等目标校验提示
    if not tp_core.service.ensure_ready(ctx, "tpm"):
        return

    x: float = context["x"]
    y: float = context["y"]
    z: float = context["z"]

    # 维度: 可选参数, 不填则使用玩家当前维度
    dimension: str = context.get("dimension", None)
    if dimension is None:
        _, cur_dim = my_lib.get_player_position_and_dimension(ctx.name)
        if cur_dim is None:
            ctx.reply(f"{TAG}§c无法获取你当前的维度")
            return
        dimension = cur_dim

    # 校验维度名称
    if dimension not in DIMENSION_NAMES:
        ctx.reply(
            f"{TAG}§c未知维度 §e{dimension}§c, 可选: §f{', '.join(DIMENSION_NAMES)}"
        )
        return

    tp_core.service.precise(ctx, tp_core.TpTarget(
        x=x, y=y, z=z, dimension=dimension,
        feature="tpm",
        label="坐标",
        success_msg="§a已传送到 §f{dim_cn} §7({x}, {y}, {z})",
    ))
