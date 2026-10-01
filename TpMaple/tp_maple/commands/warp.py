"""
warp.py — 地标相关命令: 全服共享传送点的 创建 / 列表 / 传送 / 删除

与 home 的区别:
  - 地标为全服共享 (所有人可见/可用), 不按玩家分片存储;
  - 创建/删除为管理级权限 (默认 helper), 且受全局数量上限约束。

流程类逻辑 (冷却 / back 点 / 传送执行 / 提示 / 审计日志) 统一由
teleport.TeleportService 提供, 本模块只负责「定位目标点 + 传参」。
"""
import time

import mcdreforged as mcdr
from mcdreforged.api.rtext import RText, RTextList, RColor

from .. import my_lib
from .. import teleport as tp_core
from ..context import resolve_player
from ..my_lib import TAG
from ..pagination import Paginator
from ..default_config import dimension_to_cn

# 地标名保留字 (与子命令冲突), 小写比较
RESERVED_WARP_NAMES = {"list"}


# ============================================================
# !!msetwp <warp_name>
# ============================================================

@mcdr.new_thread("TpMaple-setwp")
def set_warp(source: mcdr.CommandSource, context: dict):
    """!!msetwp <名字>: 将玩家当前坐标创建为一个全服地标。

    名字仅允许英文字母和数字; 同名地标已存在时拒绝 (需先 delwp);
    新增时受全服总数量上限 (warp_max) 限制。
    """
    # 地标不按玩家存储, 无需 UUID
    ctx = resolve_player(source, need_uuid=False)
    if ctx is None:
        return

    warp_name: str = context["warp_name"]

    # 地标名只允许英文字母和数字 (不含中文/下划线/特殊符号)
    if not warp_name.isascii() or not warp_name.isalnum():
        ctx.reply(f"{TAG}§c名称只能包含英文字母和数字")
        return

    # list 是子命令关键词 (!!mwp list), 不能作为地标名, 否则会被命令解析遮蔽
    if warp_name.lower() in RESERVED_WARP_NAMES:
        ctx.reply(f"{TAG}§c“{warp_name}”是关键词，不可作为地标的名称")
        return

    warps = my_lib.get_warps()

    # 重名: 拒绝, 避免误覆盖他人地标
    if warp_name in warps:
        ctx.reply(
            f"{TAG}§c地标 §e{warp_name} §c已存在, 如需修改请先 "
            f"§6{my_lib.cmd('delwp')} {warp_name}"
        )
        return

    # 数量上限 (全服共用)
    max_warps = my_lib.get_warp_max()
    if len(warps) >= max_warps:
        ctx.reply(f"{TAG}§c全服地标已达上限 §6{max_warps}§c, 请先删除不再使用的地标")
        return

    # 获取玩家当前位置
    pos, dimension = my_lib.get_player_position_and_dimension(ctx.name)
    if pos is None:
        ctx.reply(f"{TAG}§c无法获取你的位置, 请重试")
        return

    warps[warp_name] = {
        "x": pos.x,
        "y": pos.y,
        "z": pos.z,
        "dimension": dimension,
        "creator": ctx.name,
        "created_at": time.time(),
    }
    my_lib.save_warp_data()

    my_lib.audit(
        f"地标创建 [setwp] {ctx.name}: {warp_name} "
        f"{dimension_to_cn(dimension)} ({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f})"
    )
    ctx.reply(
        f"{TAG}§a地标 §e{warp_name} §a已创建 — §b{dimension_to_cn(dimension)} "
        f"§7({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f})"
    )


# ============================================================
# !!mwp  (列出全服地标)
# ============================================================

@mcdr.new_thread("TpMaple-warp")
def list_warps(source: mcdr.CommandSource, context: dict = None):
    """!!mwp / !!mwp list [页]: 分页列出全服所有地标。

    每条带可点击的 [传送] 按钮; 有 delwp 权限者额外显示 [删除] 按钮。
    底部带可点击翻页。页码省略默认第 1 页; 越界时由 Paginator 自动夹取。
    """
    warps = my_lib.get_warps()
    if not warps:
        source.reply(f"{TAG}§7还没有任何地标")
        return

    pg = Paginator(
        list(warps.items()),
        my_lib.get_warp_list_page_size(),
        (context or {}).get("page", 1),
    )
    source.reply(pg.header("全服地标列表", cap=my_lib.get_warp_max()))

    click_action = my_lib.get_click_action()
    # 无权限者不显示 [删除] 按钮
    can_delete = source.has_permission(my_lib.get_perm("delwp"))

    for name, info in pg.items:
        dim_cn = dimension_to_cn(info["dimension"])
        tp_command = f"{my_lib.cmd('wp')} {name}"
        parts = [
            "  ",
            RText("[传送]", color=RColor.green).c(click_action, tp_command).h(tp_command),
        ]
        if can_delete:
            del_command = f"{my_lib.cmd('delwp')} {name}"
            parts.append(" ")
            parts.append(
                RText("[删除]", color=RColor.red).c(click_action, del_command).h(del_command)
            )
        parts.append(
            f" §e{name} §f— §b{dim_cn} "
            f"§7({info['x']:.1f}, {info['y']:.1f}, {info['z']:.1f})"
        )
        creator = info.get("creator")
        if creator:
            parts.append(f" §8by {creator}")
        source.reply(RTextList(*parts))

    # 翻页控件 (仅在多于一页时显示)
    if pg.max_page > 1:
        source.reply(pg.controls(f"{my_lib.cmd('wp')} list"))


# ============================================================
# !!mwp <warp_name>  (传送到指定地标)
# ============================================================

@mcdr.new_thread("TpMaple-warp")
def go_warp(source: mcdr.CommandSource, context: dict):
    """!!mwp <名字>: 传送到指定的全服地标 (普通传送, 受 wp 冷却限制)。"""
    ctx = resolve_player(source)
    if ctx is None:
        return

    # 冷却预检: 先于目标查询, 保证「冷却中」优先于「未找到该地标」
    if not tp_core.service.ensure_ready(ctx, "wp"):
        return

    warp_name: str = context["warp_name"]
    info = my_lib.get_warps().get(warp_name)

    if info is None:
        ctx.reply(f"{TAG}§c未找到名为 §e{warp_name} §c的地标")
        return

    tp_core.service.precise(ctx, tp_core.TpTarget(
        x=info["x"], y=info["y"], z=info["z"], dimension=info["dimension"],
        feature="wp",
        label=f"地标 {warp_name}",
        success_msg="§a已传送到地标 §e" + warp_name + " §7— {dim_cn} ({x}, {y}, {z})",
    ))


# ============================================================
# !!mdelwp <warp_name>  (删除指定地标)
# ============================================================

@mcdr.new_thread("TpMaple-delwp")
def del_warp(source: mcdr.CommandSource, context: dict):
    """!!mdelwp <名字>: 删除指定的全服地标, 不存在时提示。"""
    # 地标不按玩家存储, 无需 UUID
    ctx = resolve_player(source, need_uuid=False)
    if ctx is None:
        return

    warp_name: str = context["warp_name"]
    warps = my_lib.get_warps()

    if warp_name not in warps:
        ctx.reply(f"{TAG}§c未找到名为 §e{warp_name} §c的地标")
        return

    del warps[warp_name]
    my_lib.save_warp_data()

    my_lib.audit(f"地标删除 [delwp] {ctx.name}: {warp_name}")
    ctx.reply(f"{TAG}§a已删除地标 §e{warp_name}")
