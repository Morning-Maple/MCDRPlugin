"""
teleport.py — 全局传送服务 (base 能力)

把「冷却校验 → 记录 back 点 → 执行传送 → 扣冷却 → 提示玩家 → 审计日志」这套
统一流程收敛到 TeleportService; 业务命令 (home / warp / tpm / back / tpa) 只负责
定位目标点并调用, 不再各自实现流程。

对外能力:
  - precise(ctx, target)          精确传送 (普通 tp)
  - safe(ctx, target, radius)     安全传送 (spreadplayers 找落点 + 回查校验, 失败退还冷却)
  - delayed_teleport(src, dst)    延迟传送 (模块级函数, 在新线程执行; 供 tpa/tpahere 使用)

冷却归属:
  precise / safe 的冷却由服务统一处理, 记在「被传送者」身上。
  delayed_teleport 的冷却由调用方处理 —— tpa/tpahere 的冷却记在「请求发起方」而非
  被传送方, 属于请求语义, 不适合下沉到传送服务。
"""
import time
from dataclasses import dataclass
from typing import Any, Optional, Tuple

import mcdreforged as mcdr

from . import my_lib
from .context import PlayerContext
from .default_config import dimension_to_cn

TAG = my_lib.TAG

# 安全传送判定: 传送前后 x/y/z 偏差之和大于此值视为成功 (即确实被挪走了)
MOVE_SUM_THRESHOLD = 4


# ============================================================
# 数据模型
# ============================================================

@dataclass
class TpTarget:
    """一次传送的目标点, 由业务命令组装后交给传送服务。

    :param feature:     冷却与日志用的功能名 (如 'home' / 'wp' / 'tpm' / 'back');
                        空串表示该次传送不计冷却。
    :param label:       纯文本目标描述, 仅用于审计日志 (如 '家 base' / '地标 spawn')。
    :param success_msg: 成功提示模板 (不含插件 TAG 前缀), 支持占位符
                        {dim_cn} / {x} / {y} / {z} / {label}; 空串表示不提示玩家。
                        由业务提供, 以便各命令保留自己的措辞。
    """
    x: float
    y: float
    z: float
    dimension: str
    feature: str = ""
    label: str = ""
    success_msg: str = ""

    def format_success(self) -> str:
        """渲染成功提示语 (坐标固定保留 1 位小数, 与旧实现一致)"""
        return self.success_msg.format(
            dim_cn=dimension_to_cn(self.dimension),
            x=f"{self.x:.1f}",
            y=f"{self.y:.1f}",
            z=f"{self.z:.1f}",
            label=self.label,
        )


@dataclass
class TpResult:
    """一次传送的结果 (bool(result) 即是否成功)"""
    ok: bool
    reason: str = ""          # 失败原因 (纯文本, 用于审计日志)

    def __bool__(self) -> bool:
        return self.ok


# 坐标元组: (pos, dimension); pos 为 minecraft_data_api 返回的坐标对象, 查询失败时为 None
Position = Tuple[Any, Optional[str]]


# ============================================================
# 传送服务
# ============================================================

class TeleportService:
    """全局传送服务: 业务只传参, 流程 / 冷却 / back 点 / 提示 / 日志统一在此实现。"""

    # ---------------- 对外能力 ----------------

    def ensure_ready(self, ctx: PlayerContext, feature: str) -> bool:
        """冷却预检: 可用返回 True; 被冷却拦下时已回复提示并返回 False。

        业务命令统一在「查询目标点」之前调用本方法, 以保证提示顺序为
        「冷却中」优先于「未找到目标」—— 否则冷却中的玩家会先看到目标查询结果
        甚至「正在查询死亡记录……」「已降级为安全传送」这类过程性提示,
        随后才被冷却拦下, 造成「传送已开始」的误导。

        precise / safe 内部仍会再校验一次冷却 (幂等, 不会重复提示),
        因此即使某处漏调本方法, 冷却也不会失效。
        """
        remain = self._blocked_by_cd(ctx, feature)
        if remain <= 0:
            return True
        ctx.reply(self._cd_msg(remain))
        if my_lib.is_debug_teleport_log():
            my_lib.audit(f"传送取消 [{feature or '-'}] {ctx.name} | 原因 冷却剩余 {remain}s")
        return False

    def precise(self, ctx: PlayerContext, target: TpTarget) -> TpResult:
        """精确传送: 直接 tp 到目标坐标与维度。

        普通 tp 几乎不会失败, 故不做回查校验。传送前会记 back 点 (供 !!mback 返回),
        成功后扣冷却, 并按 target.success_msg 提示玩家。
        """
        remain = self._blocked_by_cd(ctx, target.feature)
        if remain > 0:
            ctx.reply(self._cd_msg(remain))
            self._audit_skip(ctx.name, target, f"冷却剩余 {remain}s")
            return TpResult(False, f"冷却剩余 {remain}s")

        before = self._capture_back_point(ctx.name)
        started = time.time()

        self._exec_tp(ctx.name, target)
        self._record_cd(ctx, target.feature)

        if target.success_msg:
            ctx.reply(f"{TAG}{target.format_success()}")

        if my_lib.is_debug_teleport_log():
            # 精确传送的落点就是目标点, 但仍回查一次, 便于发现 tp 静默失败
            after = self._query_position(ctx.name, delay=my_lib.get_tp_check_interval())
            self._audit_ok(ctx.name, target, before, after, time.time() - started)
        return TpResult(True)

    def safe(self, ctx: PlayerContext, target: TpTarget, *, radius: float = 64) -> TpResult:
        """安全传送: spreadplayers 在 xz ±radius 格内寻找安全落点 (y 自动)。

        落点未知且可能静默失败, 故传送后回查位置校验: 失败则退还冷却且不更新 back 点;
        成功才把传送前位置记为 back 点。
        """
        remain = self._blocked_by_cd(ctx, target.feature)
        if remain > 0:
            ctx.reply(self._cd_msg(remain))
            self._audit_skip(ctx.name, target, f"冷却剩余 {remain}s")
            return TpResult(False, f"冷却剩余 {remain}s")

        before = my_lib.get_player_position_and_dimension(ctx.name)
        started = time.time()

        self._exec_spread(ctx.name, target, radius)
        self._record_cd(ctx, target.feature)

        ok, after = self._verify_moved(ctx.name, before[0])
        if not ok:
            # 未真正传送成功: 退还冷却, 且不更新 back 点
            self._refund_cd(ctx, target.feature)
            ctx.reply(f"{TAG}§c未找到安全的落点，传送失败（冷却未消耗）")
            self._audit_fail(ctx.name, target, "未找到安全落点")
            return TpResult(False, "未找到安全落点")

        if before[0] is not None:
            my_lib.set_back_point(ctx.name, before[0].x, before[0].y, before[0].z, before[1])

        if target.success_msg:
            ctx.reply(f"{TAG}{target.format_success()}")

        self._audit_ok(ctx.name, target, before, after, time.time() - started)
        return TpResult(True)

    # ---------------- 底层执行 ----------------

    @staticmethod
    def _exec_tp(player_name: str, target: TpTarget):
        """普通传送: tp 到指定维度的坐标"""
        my_lib.plugin_server.execute(
            f"execute in {target.dimension} run tp {player_name} {target.x} {target.y} {target.z}"
        )

    @staticmethod
    def _exec_spread(player_name: str, target: TpTarget, radius: float):
        """安全传送: spreadplayers 在 xz ±radius 内找安全落点"""
        my_lib.plugin_server.execute(
            f"execute in {target.dimension} run "
            f"spreadplayers {target.x} {target.z} 0 {radius} false {player_name}"
        )

    # ---------------- 冷却 ----------------

    @staticmethod
    def _blocked_by_cd(ctx: PlayerContext, feature: str) -> int:
        """检查冷却, 返回剩余秒数; 0 表示可用 (无功能名或无 UUID 时视为无冷却)"""
        if not feature or not ctx.uuid:
            return 0
        return my_lib.check_cd(ctx.uuid, feature)

    @staticmethod
    def _record_cd(ctx: PlayerContext, feature: str):
        if feature and ctx.uuid:
            my_lib.record_cd(ctx.uuid, feature)

    @staticmethod
    def _refund_cd(ctx: PlayerContext, feature: str):
        if feature and ctx.uuid:
            my_lib.cooldown.reset(ctx.uuid, feature)

    @staticmethod
    def _cd_msg(remain: int) -> str:
        return f"{TAG}§c传送冷却中, 还需等待 §6{remain}§c 秒"

    # ---------------- 位置 / back 点 ----------------

    @staticmethod
    def _capture_back_point(player_name: str) -> Position:
        """查询玩家当前位置并记为 back 点; 返回该位置 (查询失败则不记录)。"""
        pos, dim = my_lib.get_player_position_and_dimension(player_name)
        if pos is not None:
            my_lib.set_back_point(player_name, pos.x, pos.y, pos.z, dim)
        return pos, dim

    @staticmethod
    def _query_position(player_name: str, *, delay: float = 0.0) -> Position:
        """等待片刻后回查玩家位置 (服务端 tp 生效需要时间)"""
        if delay > 0:
            time.sleep(delay)
        return my_lib.get_player_position_and_dimension(player_name)

    @staticmethod
    def _verify_moved(player_name: str, before_pos) -> Tuple[bool, Position]:
        """安全传送校验: 落点相对传送前位置 x/y/z 偏差之和大于阈值即视为成功。

        注意: server.execute 看不到命令结果, 只能靠回查位置判断。
        """
        after = TeleportService._query_position(player_name, delay=my_lib.get_tp_check_interval())
        if after[0] is None:
            return False, after
        if before_pos is None:
            return False, after
        moved = (
            abs(after[0].x - before_pos.x)
            + abs(after[0].y - before_pos.y)
            + abs(after[0].z - before_pos.z)
        )
        return moved > MOVE_SUM_THRESHOLD, after

    # ---------------- 审计日志 (受 debug_teleport_log 开关控制) ----------------

    @staticmethod
    def _pos_desc(pos: Position) -> str:
        """位置描述, 如 '主世界 (10.0, 64.0, 20.0)'; 无位置时返回 '未知'"""
        if pos[0] is None:
            return "未知"
        return (
            f"{dimension_to_cn(pos[1])} "
            f"({pos[0].x:.1f}, {pos[0].y:.1f}, {pos[0].z:.1f})"
        )

    def _audit_ok(self, player_name: str, target: TpTarget, before: Position,
                  after: Position, cost: float):
        if not my_lib.is_debug_teleport_log():
            return
        my_lib.audit(
            f"传送成功 [{target.feature or '-'}] {player_name}"
            f" → {self._target_desc(target)}"
            f" | 前 {self._pos_desc(before)}"
            f" | 后 {self._pos_desc(after)}"
            f" | 耗时 {cost:.2f}s"
        )

    def _audit_skip(self, player_name: str, target: TpTarget, reason: str):
        if not my_lib.is_debug_teleport_log():
            return
        my_lib.audit(
            f"传送取消 [{target.feature or '-'}] {player_name}"
            f" → {self._target_desc(target)} | 原因 {reason}"
        )

    def _audit_fail(self, player_name: str, target: TpTarget, reason: str):
        if not my_lib.is_debug_teleport_log():
            return
        my_lib.audit(
            f"传送失败 [{target.feature or '-'}] {player_name}"
            f" → {self._target_desc(target)} | 原因 {reason}"
        )

    @staticmethod
    def _target_desc(target: TpTarget) -> str:
        label = target.label or "目标点"
        return f"{label} {dimension_to_cn(target.dimension)} ({target.x:.1f}, {target.y:.1f}, {target.z:.1f})"

    # ---------------- 延迟传送 (供 tpa / tpahere 使用) ----------------

    def delayed(self, source_player: str, target_player: str):
        """延迟传送: 等待 tp_delay 秒后把 source_player 传到 target_player 的位置。

        延迟期间按 tp_check_interval 检测被传送方是否移动 / 切换维度, 是则取消。
        移动取消只通知被传送方, 目标方无感。

        注意: 冷却不在此处理 (见模块 docstring)。
        """
        delay = my_lib.get_tp_delay()
        threshold = my_lib.get_tp_move_threshold()
        interval = my_lib.get_tp_check_interval()

        def _tell(player, msg):
            my_lib.plugin_server.tell(player, msg)

        # 记录被传送玩家的初始位置和维度
        init_pos, init_dim = my_lib.get_player_position_and_dimension(source_player)
        if init_pos is None:
            _tell(source_player, f"{TAG}§c无法获取你的位置, 传送已取消")
            my_lib.audit(f"传送取消 [tpa] {source_player} → {target_player} | 原因 无法获取自身位置")
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
                    my_lib.audit(f"传送取消 [tpa] {source_player} → {target_player} | 原因 位置查询失败")
                    return

                # 维度变化也视为移动, 取消传送
                if cur_dim != init_dim:
                    _tell(source_player, f"{TAG}§c检测到维度变化, 传送已取消!")
                    my_lib.audit(f"传送取消 [tpa] {source_player} → {target_player} | 原因 维度变化")
                    return

                dx = abs(cur_pos.x - init_pos.x)
                dy = abs(cur_pos.y - init_pos.y)
                dz = abs(cur_pos.z - init_pos.z)
                if dx > threshold or dy > threshold or dz > threshold:
                    _tell(source_player, f"{TAG}§c检测到移动, 传送已取消!")
                    my_lib.audit(f"传送取消 [tpa] {source_player} → {target_player} | 原因 检测到移动")
                    return

        # 获取目标玩家当前位置并传送
        target_pos, target_dim = my_lib.get_player_position_and_dimension(target_player)
        if target_pos is None:
            _tell(source_player, f"{TAG}§c无法获取目标玩家位置, 传送已取消")
            my_lib.audit(f"传送取消 [tpa] {source_player} → {target_player} | 原因 无法获取目标位置")
            return

        # 记录被传送方传送前的位置, 供其之后 !!mback 返回
        my_lib.set_back_point(source_player, init_pos.x, init_pos.y, init_pos.z, init_dim)

        my_lib.plugin_server.execute(
            f"execute in {target_dim} run tp {source_player} {target_pos.x} {target_pos.y} {target_pos.z}"
        )
        _tell(source_player, f"{TAG}§a传送完成!")
        my_lib.audit(
            f"传送成功 [tpa] {source_player} → 玩家 {target_player} "
            f"{dimension_to_cn(target_dim)} ({target_pos.x:.1f}, {target_pos.y:.1f}, {target_pos.z:.1f})"
            f" | 前 {self._pos_desc((init_pos, init_dim))}"
        )


# 全局单例: 业务命令统一通过 tp_core.service 调用
service = TeleportService()


@mcdr.new_thread("TpMaple-DelayedTP")
def delayed_teleport(source_player: str, target_player: str):
    """延迟传送入口 (在新线程中执行, 不阻塞调用方)。

    保留模块级函数形式: tpa/tpahere 在同意请求后立即调用, 需异步执行。
    """
    service.delayed(source_player, target_player)
