"""
teleport.py — 传送底层: 普通传送 / 安全传送 / 延迟传送
"""
import time

import mcdreforged as mcdr

from . import my_lib


TAG = "§b[TpMaple] "


def teleport(player_name: str, x: float, y: float, z: float, dimension: str):
    """
    普通传送: 直接 tp 到指定维度坐标
    """
    server = my_lib.plugin_server
    server.execute(
        f"execute in {dimension} run tp {player_name} {x} {y} {z}"
    )


def safety_teleport(player_name: str, x: float, z: float, dimension: str, radius: float = 64):
    """
    安全传送: spreadplayers 在 xz ±radius 格范围内寻找安全落点, y 自动
    :param radius: 搜索半径 (格), 默认 64; 虚空降级时用较小值以贴近原死亡点
    """
    server = my_lib.plugin_server
    server.execute(
        f"execute in {dimension} run spreadplayers {x} {z} 0 {radius} false {player_name}"
    )


# 安全传送判定: 传送前后 x/y/z 偏差之和大于此值视为成功 (即确实被挪走了)
MOVE_SUM_THRESHOLD = 4


def verify_teleport_success(
    player_name: str,
    before_pos,
    before_dim,
    *,
    target_pos=None,
    target_dim=None,
    delay: float = None,
) -> bool:
    """传送后回查玩家位置, 判断是否传送成功 (server.execute 看不到命令结果, 故主动校验)。

    - 提供 target_pos/target_dim 时 (精确传送): 成功 = 落点接近目标坐标且维度一致
    - 否则 (安全传送, 落点未知): 成功 = 相对传送前位置 x/y/z 偏差之和大于阈值

    :param before_pos: 传送前坐标 (含 x/y/z); 安全传送判定位移用
    :param before_dim: 传送前维度
    :param delay: 回查前等待秒数, 默认取配置的 tp_check_interval
    :return: True=确认成功; False=疑似失败 (含无法获取位置)
    """
    if delay is None:
        delay = my_lib.get_tp_check_interval()
    time.sleep(delay)

    after_pos, after_dim = my_lib.get_player_position_and_dimension(player_name)
    if after_pos is None:
        return False

    if target_pos is not None:
        # 精确传送: 校验是否到达目标附近且维度一致
        if target_dim is not None and after_dim != target_dim:
            return False
        threshold = max(my_lib.get_tp_move_threshold(), 2.0)
        return _delta_sum(after_pos, target_pos) <= threshold

    # 安全传送: 落点未知, 用「相对传送前的位移偏差之和」判定
    if before_pos is None:
        return False
    return _delta_sum(after_pos, before_pos) > MOVE_SUM_THRESHOLD


def _delta_sum(a, b) -> float:
    """两坐标 x/y/z 三轴偏差的绝对值之和"""
    return abs(a.x - b.x) + abs(a.y - b.y) + abs(a.z - b.z)


@mcdr.new_thread("TpMaple-DelayedTP")
def delayed_teleport(source_player: str, target_player: str):
    """
    延迟传送: 等待 tp_delay 秒, 期间按 tp_check_interval 检测被传送方是否移动。
    移动取消只通知被传送方, 目标方无感。

    使用 MCDR @new_thread 装饰器在守护线程中执行, 不阻塞主线程。

    :param source_player: 被传送的玩家名 (实际执行 tp 的人)
    :param target_player: 传送目标玩家名 (tp 到此人坐标)
    """
    delay = my_lib.get_tp_delay()
    threshold = my_lib.get_tp_move_threshold()
    interval = my_lib.get_tp_check_interval()

    def _tell(player, msg):
        """给指定玩家发送一条消息 (支持 § 颜色码)。"""
        my_lib.plugin_server.tell(player, msg)

    # 记录被传送玩家的初始位置和维度
    init_pos, init_dim = my_lib.get_player_position_and_dimension(source_player)
    if init_pos is None:
        _tell(source_player, f"{TAG}§c无法获取你的位置, 传送已取消")
        return

    if delay > 0:
        # 按配置间隔循环检测
        elapsed = 0.0
        while elapsed < delay:
            time.sleep(interval)
            elapsed += interval

            cur_pos, cur_dim = my_lib.get_player_position_and_dimension(source_player)
            if cur_pos is None:
                _tell(source_player, f"{TAG}§c无法获取你的位置, 传送已取消")
                return

            # 维度变化也视为移动, 取消传送
            if cur_dim != init_dim:
                _tell(source_player, f"{TAG}§c检测到维度变化, 传送已取消!")
                return

            dx = abs(cur_pos.x - init_pos.x)
            dy = abs(cur_pos.y - init_pos.y)
            dz = abs(cur_pos.z - init_pos.z)
            if dx > threshold or dy > threshold or dz > threshold:
                _tell(source_player, f"{TAG}§c检测到移动, 传送已取消!")
                return

    # 获取目标玩家当前位置并传送
    target_pos, target_dim = my_lib.get_player_position_and_dimension(target_player)
    if target_pos is None:
        _tell(source_player, f"{TAG}§c无法获取目标玩家位置, 传送已取消")
        return

    # 记录被传送方传送前的位置, 供其之后 !!mback 返回
    my_lib.set_back_point(source_player, init_pos.x, init_pos.y, init_pos.z, init_dim)

    teleport(source_player, target_pos.x, target_pos.y, target_pos.z, target_dim)
    _tell(source_player, f"{TAG}§a传送完成!")
