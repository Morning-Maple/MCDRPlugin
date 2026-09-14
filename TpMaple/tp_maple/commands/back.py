"""
back.py — !!mback  回到上次死亡地点 (精确 / 安全传送)
"""
import mcdreforged as mcdr

from .. import my_lib
from .. import teleport as tp_core
from ..default_config import dimension_to_cn

TAG = "§b[TpMaple] "


@mcdr.new_thread("TpMaple-back")
def go_back(source: mcdr.CommandSource):
    """!!mback — 精确传送回死亡坐标"""
    _back_impl(source, safe=False)


@mcdr.new_thread("TpMaple-back")
def go_back_safe(source: mcdr.CommandSource):
    """!!mback safe — 安全传送 (spreadplayers) 到死亡点附近"""
    _back_impl(source, safe=True)


def _back_impl(source: mcdr.CommandSource, safe: bool):
    """back / back safe 的共用实现。

    :param safe: True 走安全传送 (spreadplayers); False 走精确传送,
                 但精确模式下若死亡点在虚空会自动降级为高精度安全传送。

    安全传送可能找不到落点而静默失败, 故传送后回查位置确认,
    失败时退还冷却并提示玩家。
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
    remain = my_lib.check_cd(player_uuid, "back")
    if remain > 0:
        source.reply(f"{TAG}§c传送冷却中, 还需等待 §6{remain}§c 秒")
        return

    # 取 back 目标点: 优先用运行时记录的传送/死亡点; 没有则回退实时查原版死亡点
    target = my_lib.get_back_point(player_name)
    if target is not None:
        x, y, z, dimension = target["x"], target["y"], target["z"], target["dimension"]
    else:
        source.reply(f"{TAG}§6正在查询死亡记录……")
        death = my_lib.get_player_last_death_position(player_name)
        if death is None:
            source.reply(f"{TAG}§c没有可返回的传送或死亡地点")
            return
        x, y, z, dimension = death

    dim_cn = dimension_to_cn(dimension)

    # back 自身也记录: 先抓当前位置, 传送成功后再提交为新的 back 点 (实现来回横跳)
    cur_pos, cur_dim = my_lib.get_player_position_and_dimension(player_name)

    def _commit_new_back_point():
        if cur_pos is not None:
            my_lib.set_back_point(player_name, cur_pos.x, cur_pos.y, cur_pos.z, cur_dim)

    # 精确模式下, 若目标点在虚空高度则强制降级为高精度安全传送, 避免回去再次坠亡
    void_fallback = (not safe) and _is_void_death(dimension, y)
    if void_fallback:
        source.reply(f"{TAG}§e精确传送不可用，已降级使用高精度安全传送替代")

    if safe or void_fallback:
        # 安全传送 (spreadplayers): 主动 back safe 用 ±64, 虚空降级用 ±8 贴近原点
        # 该命令可能找不到落点而静默失败, 故传送后回查位置确认
        radius = 8 if void_fallback else 64
        tp_core.safety_teleport(player_name, x, z, dimension, radius=radius)
        my_lib.record_cd(player_uuid, "back")

        if tp_core.verify_teleport_success(player_name, cur_pos, cur_dim):
            _commit_new_back_point()
            source.reply(
                f"{TAG}§a已安全回到上一次的传送/死亡地点附近 §7— {dim_cn} ({x:.1f}, {y:.1f}, {z:.1f})"
            )
        else:
            # 未真正传送成功: 退还冷却并提示, 且不更新 back 点
            my_lib.cooldown.reset(player_uuid, "back")
            source.reply(f"{TAG}§c未找到安全的落点，传送失败（冷却未消耗）")
        return

    # 精确传送 (普通 tp 几乎不会失败, 不做校验)
    tp_core.teleport(player_name, x, y, z, dimension)
    my_lib.record_cd(player_uuid, "back")
    _commit_new_back_point()
    source.reply(
        f"{TAG}§a已回到上一次的传送/死亡地点 §7— {dim_cn} ({x:.1f}, {y:.1f}, {z:.1f})"
    )


def _is_void_death(dimension: str, y: float) -> bool:
    """判断死亡点是否在虚空高度 (精确传送回去会再次坠亡)

    主世界 y < -128, 地狱/末地 y < -64 时视为虚空。
    """
    if dimension == "minecraft:overworld":
        return y < -128
    if dimension in ("minecraft:the_nether", "minecraft:the_end"):
        return y < -64
    return False