"""
home.py — 家园相关命令: 设置 / 列表 / 传送 / 删除

流程类逻辑 (冷却 / back 点 / 传送执行 / 提示 / 审计日志) 统一由
teleport.TeleportService 提供, 本模块只负责「定位目标点 + 传参」。
"""
import mcdreforged as mcdr
from mcdreforged.api.rtext import RText, RTextList, RColor

from .. import my_lib
from .. import teleport as tp_core
from .. import utils
from ..context import resolve_player
from ..my_lib import TAG
from ..pagination import Paginator
from ..default_config import dimension_to_cn

# 家名保留字 (与子命令冲突), 小写比较
RESERVED_HOME_NAMES = {"list"}


# ============================================================
# !!msethome <home_name>
# ============================================================

@mcdr.new_thread("TpMaple-sethome")
def set_home(source: mcdr.CommandSource, context: dict):
    """!!msethome <名字>: 将玩家当前坐标记为一个家。

    名字仅允许英文字母和数字; 重名则覆盖, 新增时受数量上限限制。
    """
    ctx = resolve_player(source)
    if ctx is None:
        return

    home_name: str = context["home_name"]

    # home 名只允许英文字母和数字 (不含中文/下划线/特殊符号)
    if not home_name.isascii() or not home_name.isalnum():
        ctx.reply(f"{TAG}§c名称只能包含英文字母和数字")
        return

    # list 是子命令关键词 (!!mhome list), 不能作为家名, 否则会被命令解析遮蔽
    if home_name.lower() in RESERVED_HOME_NAMES:
        ctx.reply(f"{TAG}§c“{home_name}”是关键词，不可作为家的名称")
        return

    # 获取玩家当前位置
    pos, dimension = my_lib.get_player_position_and_dimension(ctx.name)
    if pos is None:
        ctx.reply(f"{TAG}§c无法获取你的位置, 请重试")
        return

    # 读取玩家持久化数据
    pdata = my_lib.get_player_data(ctx.uuid)
    my_lib.set_player_name(ctx.uuid, ctx.name)  # 顺便更新名字映射

    homes: dict = pdata.setdefault("homes", {})

    # 名字重复 → 覆盖; 不重复 → 检查数量上限
    if home_name not in homes:
        max_homes = my_lib.get_sethome_max()
        if len(homes) >= max_homes:
            ctx.reply(f"{TAG}§c你已设置 {len(homes)} 个家, 达到上限 §6{max_homes}")
            return

    homes[home_name] = {
        "x": pos.x,
        "y": pos.y,
        "z": pos.z,
        "dimension": dimension,
    }
    my_lib.save_player(ctx.uuid)

    ctx.reply(
        f"{TAG}§a家 §e{home_name} §a已设置为 §b{dimension_to_cn(dimension)} "
        f"§7({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f})"
    )


# ============================================================
# !!mhome  (列出所有家)
# ============================================================

@mcdr.new_thread("TpMaple-home")
def list_homes(source: mcdr.CommandSource, context: dict = None):
    """!!mhome / !!mhome list [页]: 分页列出玩家所有的家。

    每条带可点击的 [传送] / [删除] 按钮, 底部带可点击翻页。
    家按名字以 Windows 资源管理器风格 (自然排序) 排序, 与 !!mwp 一致;
    页码省略默认第 1 页, 越界时由 Paginator 自动夹取到 [1, 最大页]。
    """
    ctx = resolve_player(source)
    if ctx is None:
        return

    homes: dict = my_lib.get_player_data(ctx.uuid).get("homes", {})
    if not homes:
        ctx.reply(f"{TAG}§7你还没有设置任何家")
        return

    # 按名字自然排序 (Windows 资源管理器风格), 排序先于分页以保证每页内容稳定
    items = sorted(homes.items(), key=lambda kv: utils.natural_sort_key(kv[0]))

    pg = Paginator(
        items,
        my_lib.get_home_list_page_size(),
        (context or {}).get("page", 1),
    )
    ctx.reply(pg.header("已设置的家列表", cap=my_lib.get_sethome_max()))

    click_action = my_lib.get_click_action()
    for name, info in pg.items:
        dim_cn = dimension_to_cn(info["dimension"])
        tp_command = f"{my_lib.cmd('home')} {name}"
        del_command = f"{my_lib.cmd('delhome')} {name}"
        ctx.reply(RTextList(
            "  ",
            RText("[传送]", color=RColor.green).c(click_action, tp_command).h(tp_command),
            " ",
            RText("[删除]", color=RColor.red).c(click_action, del_command).h(del_command),
            f" §e{name} §f— §b{dim_cn} "
            f"§7({info['x']:.1f}, {info['y']:.1f}, {info['z']:.1f})",
        ))

    # 翻页控件 (仅在多于一页时显示)
    if pg.max_page > 1:
        ctx.reply(pg.controls(f"{my_lib.cmd('home')} list"))


# ============================================================
# !!mhome <home_name>  (传送到指定家)
# ============================================================

@mcdr.new_thread("TpMaple-home")
def go_home(source: mcdr.CommandSource, context: dict):
    """!!mhome <名字>: 传送到指定的家 (普通传送, 受 home 冷却限制)。"""
    ctx = resolve_player(source)
    if ctx is None:
        return

    # 冷却预检: 先于目标查询, 保证「冷却中」优先于「未找到该家」
    if not tp_core.service.ensure_ready(ctx, "home"):
        return

    home_name: str = context["home_name"]
    info = my_lib.get_player_data(ctx.uuid).get("homes", {}).get(home_name)

    if info is None:
        ctx.reply(f"{TAG}§c未找到名为 §e{home_name} §c的家")
        return

    tp_core.service.precise(ctx, tp_core.TpTarget(
        x=info["x"], y=info["y"], z=info["z"], dimension=info["dimension"],
        feature="home",
        label=f"家 {home_name}",
        success_msg="§a已传送到 §e" + home_name + " §7— {dim_cn} ({x}, {y}, {z})",
    ))


# ============================================================
# !!mdelhome <home_name>  (删除指定家)
# ============================================================

@mcdr.new_thread("TpMaple-delhome")
def del_home(source: mcdr.CommandSource, context: dict):
    """!!mdelhome <名字>: 删除指定的家, 不存在时提示。"""
    ctx = resolve_player(source)
    if ctx is None:
        return

    home_name: str = context["home_name"]
    homes: dict = my_lib.get_player_data(ctx.uuid).get("homes", {})

    if home_name not in homes:
        ctx.reply(f"{TAG}§c未找到名为 §e{home_name} §c的家")
        return

    del homes[home_name]
    my_lib.save_player(ctx.uuid)

    ctx.reply(f"{TAG}§a已删除家 §e{home_name}")
