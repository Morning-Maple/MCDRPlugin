"""
warp.py — 地标相关命令: 全服共享传送点的 创建 / 列表 / 传送 / 删除

与 home 的区别:
  - 地标为全服共享 (所有人可见/可用), 不按玩家分片存储;
  - 创建/删除为管理级权限 (默认 helper), 且受全局数量上限约束。

流程类逻辑 (冷却 / back 点 / 传送执行 / 提示 / 审计日志) 统一由
teleport.TeleportService 提供, 本模块只负责「定位目标点 + 传参」。
"""
import re
import time

import mcdreforged as mcdr
from mcdreforged.api.rtext import RText, RTextList, RColor

from .. import my_lib
from .. import teleport as tp_core
from .. import utils
from ..context import resolve_player
from ..my_lib import TAG
from ..pagination import Paginator
from ..default_config import dimension_to_cn

# 地标名保留字 (与 !!mwp 的子命令冲突), 小写比较。
# 保留字依据: MCDR 解析时字面量子命令优先于参数, 因此这些名字一旦成为地标名,
# 就无法通过 !!mwp <名字> 到达 (会被解析成子命令), 故在创建时直接拒绝。
RESERVED_WARP_NAMES = {"list", "help", "h", "reload", "reset"}

# 注释最大长度 (字符); 超长直接拒绝, 避免撑爆列表渲染
MAX_COMMENT_LEN = 32


def _clean_comment(raw) -> str:
    """清洗地标注释: 移除颜色码 / 换行, 并规整连续空白。

    注释允许中文与空格 (命令中含空格时需用引号包裹)。颜色码与换行会污染
    列表渲染 (甚至能伪造出额外行), 故一律剔除。
    """
    if not raw:
        return ""
    # 颜色码是 '§' + 一个格式字符 (如 §c), 需整体剔除; 末尾孤立的 '§' 单独兜底
    text = re.sub(r"§.", "", str(raw)).replace("§", "")
    text = text.replace("\n", " ").replace("\r", " ")
    return " ".join(text.split())


def _format_time(ts) -> str:
    """把创建时间戳格式化为 'YYYY-MM-DD HH:MM' (本地时区); 缺失或非法时返回 '未知'

    需捕获 OverflowError: 超出平台 time_t 范围的数值 (如超大数 / inf) 会抛出它,
    且比 ValueError 更隐蔽 —— 漏掉会让整个列表线程中断, 后续地标与翻页栏都不再渲染。
    """
    if not ts:
        return "未知"
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(ts)))
    except (TypeError, ValueError, OverflowError, OSError):
        return "未知"


# ============================================================
# !!msetwp <warp_name> [comment]
# ============================================================

@mcdr.new_thread("TpMaple-setwp")
def set_warp(source: mcdr.CommandSource, context: dict):
    """!!msetwp <名字> [注释]: 将玩家当前坐标创建为一个全服地标。

    名字仅允许英文字母和数字; 注释可选 (允许中文, 含空格时需加引号,
    长度上限见 MAX_COMMENT_LEN); 同名地标已存在时拒绝 (需先 delwp);
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

    # list / help / h / reload / reset 是 !!mwp 的子命令关键词, 不能作为地标名,
    # 否则会被命令解析遮蔽 (字面量子命令优先于参数)
    if warp_name.lower() in RESERVED_WARP_NAMES:
        ctx.reply(f"{TAG}§c“{warp_name}”是关键词，不可作为地标的名称")
        return

    # 注释: 可选参数
    comment = _clean_comment(context.get("comment"))
    if len(comment) > MAX_COMMENT_LEN:
        ctx.reply(f"{TAG}§c注释过长, 最多 §6{MAX_COMMENT_LEN}§c 个字符")
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
        "comment": comment,
    }
    my_lib.save_warp_data()

    comment_desc = f" | 注释 {comment}" if comment else ""
    my_lib.audit(
        f"地标创建 [setwp] {ctx.name}: {warp_name} "
        f"{dimension_to_cn(dimension)} ({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f}){comment_desc}"
    )
    reply = (
        f"{TAG}§a地标 §e{warp_name} §a已创建 — §b{dimension_to_cn(dimension)} "
        f"§7({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f})"
    )
    if comment:
        reply += f" §7| §f{comment}"
    ctx.reply(reply)


# ============================================================
# !!mwp  (列出全服地标)
# ============================================================

@mcdr.new_thread("TpMaple-warp")
def list_warps(source: mcdr.CommandSource, context: dict = None):
    """!!mwp / !!mwp list [页]: 分页列出全服所有地标。

    每条占两行: 第一行是 可点击按钮([传送], 有权限则含 [删除]) + 名字 + 维度 + 坐标,
    第二行是 "-- 注释内容" + "@创建人" + 创建时间; 底部带可点击翻页。
    地标按名字以 Windows 资源管理器风格 (自然排序: 数字按数值、数字优先、
    忽略大小写) 排序; 页码省略默认第 1 页, 越界时由 Paginator 自动夹取。
    """
    warps = my_lib.get_warps()
    if not warps:
        source.reply(f"{TAG}§7还没有任何地标")
        return

    # 按名字自然排序 (Windows 资源管理器风格), 排序先于分页以保证每页内容稳定
    items = sorted(warps.items(), key=lambda kv: utils.natural_sort_key(kv[0]))

    pg = Paginator(
        items,
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
        # 第二行: -- 注释内容 / @创建人 / 创建时间。
        # 用 \n 在同一条消息内换行 (而非再 reply 一次), 避免刷屏并保持每条可点击行为一体。
        creator = info.get("creator")
        # 有创建人时用 @名字; 旧数据缺该字段时退化为「未知」(不加 @, 避免出现 @未知 这种假句柄)
        creator_desc = f"§7@§f{creator}" if creator else "§7未知"
        parts.append("\n")
        parts.append(
            f"    §7-- §f{info.get('comment') or '无'}"
            f"  §8| {creator_desc}"
            f"  §8| §7{_format_time(info.get('created_at'))}"
        )
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
