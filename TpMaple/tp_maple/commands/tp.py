"""
tp.py — !!tpm <x> <y> <z> [dimension]  传送到指定坐标
"""
import mcdreforged as mcdr

from .. import my_lib
from .. import teleport as tp_core
from ..default_config import DIMENSION_NAMES, dimension_to_cn

TAG = "§b[TpMaple] "


@mcdr.new_thread("TpMaple-tpm")
def tp_to_pos(source: mcdr.CommandSource, context: dict):
    """!!tpm <x> <y> <z> [维度]: 传送到指定坐标。

    维度为可选参数, 省略时使用玩家当前所在维度; 受 tpm 冷却限制。
    """
    if not source.is_player:
        source.reply(f"{TAG}§c该命令只能由玩家执行")
        return

    player_name = source.player

    player_uuid = my_lib.get_player_uuid(player_name)
    if player_uuid is None:
        source.reply(f"{TAG}§c无法获取你的 UUID")
        return

    # CD 检查
    remain = my_lib.check_cd(player_uuid, "tpm")
    if remain > 0:
        source.reply(f"{TAG}§c传送冷却中, 还需等待 §6{remain}§c 秒")
        return

    x: float = context["x"]
    y: float = context["y"]
    z: float = context["z"]

    # 维度: 可选参数, 不填则使用玩家当前维度
    dimension: str = context.get("dimension", None)
    if dimension is None:
        _, cur_dim = my_lib.get_player_position_and_dimension(player_name)
        if cur_dim is None:
            source.reply(f"{TAG}§c无法获取你当前的维度")
            return
        dimension = cur_dim

    # 校验维度名称
    if dimension not in DIMENSION_NAMES:
        source.reply(
            f"{TAG}§c未知维度 §e{dimension}§c, 可选: §f{', '.join(DIMENSION_NAMES)}"
        )
        return

    # 记录传送前位置为 back 点, 再普通传送
    my_lib.record_back_point(player_name)
    tp_core.teleport(player_name, x, y, z, dimension)
    my_lib.record_cd(player_uuid, "tpm")

    dim_cn = dimension_to_cn(dimension)
    source.reply(
        f"{TAG}§a已传送到 §f{dim_cn} §7({x:.1f}, {y:.1f}, {z:.1f})"
    )