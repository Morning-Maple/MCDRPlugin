"""
warp.py — 地标相关命令: 全服共享传送点的 创建 / 列表 / 传送 / 删除

与 home 的区别:
  - 地标为全服共享 (所有人可见/可用), 不按玩家分片存储;
  - 创建/删除为管理级权限 (默认 helper), 且受全局数量上限约束。

所有命令回调均用 @new_thread 装饰, 以便安全调用会阻塞的 minecraft_data_api。
"""
import time

import mcdreforged as mcdr
from mcdreforged.api.rtext import RText, RTextList, RColor

from .. import my_lib
from .. import teleport as tp_core
from ..default_config import dimension_to_cn

TAG = "§b[TpMaple] "

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
    if not source.is_player:
        source.reply(f"{TAG}§c该命令只能由玩家执行")
        return

    player_name = source.player
    warp_name: str = context["warp_name"]

    # 地标名只允许英文字母和数字 (不含中文/下划线/特殊符号)
    if not warp_name.isascii() or not warp_name.isalnum():
        source.reply(f"{TAG}§c名称只能包含英文字母和数字")
        return

    # list 是子命令关键词 (!!mwp list), 不能作为地标名, 否则会被命令解析遮蔽
    if warp_name.lower() in RESERVED_WARP_NAMES:
        source.reply(f"{TAG}§c“{warp_name}”是关键词，不可作为地标的名称")
        return

    warps = my_lib.get_warps()

    # 重名: 拒绝, 避免误覆盖他人地标
    if warp_name in warps:
        source.reply(
            f"{TAG}§c地标 §e{warp_name} §c已存在, 如需修改请先 "
            f"§6{my_lib.cmd('delwp')} {warp_name}"
        )
        return

    # 数量上限 (全服共用)
    max_warps = my_lib.get_warp_max()
    if len(warps) >= max_warps:
        source.reply(f"{TAG}§c全服地标已达上限 §6{max_warps}§c, 请先删除不再使用的地标")
        return

    # 获取玩家当前位置
    pos, dimension = my_lib.get_player_position_and_dimension(player_name)
    if pos is None:
        source.reply(f"{TAG}§c无法获取你的位置, 请重试")
        return

    warps[warp_name] = {
        "x": pos.x,
        "y": pos.y,
        "z": pos.z,
        "dimension": dimension,
        "creator": player_name,
        "created_at": time.time(),
    }
    my_lib.save_warp_data()

    source.reply(
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
    底部带可点击翻页。页码省略默认第 1 页; 越界时自动夹取到 [1, 最大页]。
    """
    warps = my_lib.get_warps()

    if not warps:
        source.reply(f"{TAG}§7还没有任何地标")
        return

    # 分页计算
    page_size = my_lib.get_warp_list_page_size()
    items = list(warps.items())
    total = len(items)
    max_page = (total + page_size - 1) // page_size  # 向上取整, total>0 时至少为 1
    page = (context or {}).get("page", 1)
    # 越界夹取到 [1, max_page]
    page = max(1, min(page, max_page))

    start = (page - 1) * page_size
    source.reply(
        f"{TAG}§6全服地标列表 ({total}/{my_lib.get_warp_max()})  §7第 {page}/{max_page} 页"
    )

    click_action = my_lib.get_click_action()
    # 无权限者不显示 [删除] 按钮
    can_delete = source.has_permission(my_lib.get_perm("delwp"))

    for name, info in items[start:start + page_size]:
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
    if max_page > 1:
        source.reply(my_lib.build_page_controls(f"{my_lib.cmd('wp')} list", page, max_page))


# ============================================================
# !!mwp <warp_name>  (传送到指定地标, 受 wp 冷却限制, 普通传送)
# ============================================================

@mcdr.new_thread("TpMaple-warp")
def go_warp(source: mcdr.CommandSource, context: dict):
    """!!mwp <名字>: 传送到指定的全服地标 (普通传送, 受 wp 冷却限制)。"""
    if not source.is_player:
        source.reply(f"{TAG}§c该命令只能由玩家执行")
        return

    player_name = source.player
    warp_name: str = context["warp_name"]

    player_uuid = my_lib.get_player_uuid(player_name)
    if player_uuid is None:
        source.reply(f"{TAG}§c无法获取你的 UUID")
        return

    # CD 检查
    remain = my_lib.check_cd(player_uuid, "wp")
    if remain > 0:
        source.reply(f"{TAG}§c传送冷却中, 还需等待 §6{remain}§c 秒")
        return

    info = my_lib.get_warps().get(warp_name)
    if info is None:
        source.reply(f"{TAG}§c未找到名为 §e{warp_name} §c的地标")
        return

    # 记录传送前位置为 back 点, 再普通传送
    my_lib.record_back_point(player_name)
    tp_core.teleport(player_name, info["x"], info["y"], info["z"], info["dimension"])
    my_lib.record_cd(player_uuid, "wp")

    source.reply(
        f"{TAG}§a已传送到地标 §e{warp_name} §7— {dimension_to_cn(info['dimension'])} "
        f"({info['x']:.1f}, {info['y']:.1f}, {info['z']:.1f})"
    )


# ============================================================
# !!mdelwp <warp_name>  (删除指定地标)
# ============================================================

@mcdr.new_thread("TpMaple-delwp")
def del_warp(source: mcdr.CommandSource, context: dict):
    """!!mdelwp <名字>: 删除指定的全服地标, 不存在时提示。"""
    if not source.is_player:
        source.reply(f"{TAG}§c该命令只能由玩家执行")
        return

    warp_name: str = context["warp_name"]
    warps = my_lib.get_warps()

    if warp_name not in warps:
        source.reply(f"{TAG}§c未找到名为 §e{warp_name} §c的地标")
        return

    del warps[warp_name]
    my_lib.save_warp_data()

    source.reply(f"{TAG}§a已删除地标 §e{warp_name}")
