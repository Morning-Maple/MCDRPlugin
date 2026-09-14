"""
home.py — 家园相关命令: 设置 / 列表 / 传送 / 删除

所有命令回调均用 @new_thread 装饰, 以便安全调用会阻塞的 minecraft_data_api。
"""
import mcdreforged as mcdr
from mcdreforged.api.rtext import RText, RTextList, RColor

from .. import my_lib
from .. import teleport as tp_core
from ..default_config import dimension_to_cn

TAG = "§b[TpMaple] "

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
    if not source.is_player:
        source.reply(f"{TAG}§c该命令只能由玩家执行")
        return

    player_name = source.player
    home_name: str = context["home_name"]

    # home 名只允许英文字母和数字 (不含中文/下划线/特殊符号)
    if not home_name.isascii() or not home_name.isalnum():
        source.reply(f"{TAG}§c名称只能包含英文字母和数字")
        return

    # list 是子命令关键词 (!!mhome list), 不能作为家名, 否则会被命令解析遮蔽
    if home_name.lower() in RESERVED_HOME_NAMES:
        source.reply(f"{TAG}§c“{home_name}”是关键词，不可作为家的名称")
        return

    # 获取 UUID
    player_uuid = my_lib.get_player_uuid(player_name)
    if player_uuid is None:
        source.reply(f"{TAG}§c无法获取你的 UUID, 请重试")
        return

    # 获取玩家当前位置
    pos, dimension = my_lib.get_player_position_and_dimension(player_name)
    if pos is None:
        source.reply(f"{TAG}§c无法获取你的位置, 请重试")
        return

    # 读取玩家持久化数据
    pdata = my_lib.get_player_data(player_uuid)
    pdata["player_name"] = player_name  # 顺便更新名字映射

    homes: dict = pdata.setdefault("homes", {})

    # 名字重复 → 覆盖; 不重复 → 检查数量上限
    if home_name not in homes:
        max_homes = my_lib.get_sethome_max()
        if len(homes) >= max_homes:
            source.reply(f"{TAG}§c你已设置 {len(homes)} 个家, 达到上限 §6{max_homes}")
            return

    homes[home_name] = {
        "x": pos.x,
        "y": pos.y,
        "z": pos.z,
        "dimension": dimension,
    }
    my_lib.save_player_data()

    source.reply(
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
    页码省略默认第 1 页; 越界时自动夹取到 [1, 最大页]。
    """
    if not source.is_player:
        source.reply(f"{TAG}§c该命令只能由玩家执行")
        return

    player_name = source.player
    player_uuid = my_lib.get_player_uuid(player_name)
    if player_uuid is None:
        source.reply(f"{TAG}§c无法获取你的 UUID")
        return

    pdata = my_lib.get_player_data(player_uuid)
    homes: dict = pdata.get("homes", {})

    if not homes:
        source.reply(f"{TAG}§7你还没有设置任何家")
        return

    # 分页计算
    page_size = my_lib.get_home_list_page_size()
    items = list(homes.items())
    total = len(items)
    max_page = (total + page_size - 1) // page_size  # 向上取整, total>0 时至少为 1
    page = (context or {}).get("page", 1)
    # 越界夹取到 [1, max_page]
    page = max(1, min(page, max_page))

    start = (page - 1) * page_size
    source.reply(
        f"{TAG}§6已设置的家列表 ({total}/{my_lib.get_sethome_max()})  §7第 {page}/{max_page} 页"
    )
    click_action = my_lib.get_click_action()
    for name, info in items[start:start + page_size]:
        dim_cn = dimension_to_cn(info["dimension"])
        tp_command = f"{my_lib.cmd('home')} {name}"
        del_command = f"{my_lib.cmd('delhome')} {name}"
        source.reply(RTextList(
            "  ",
            RText("[传送]", color=RColor.green).c(click_action, tp_command).h(tp_command),
            " ",
            RText("[删除]", color=RColor.red).c(click_action, del_command).h(del_command),
            f" §e{name} §f— §b{dim_cn} "
            f"§7({info['x']:.1f}, {info['y']:.1f}, {info['z']:.1f})",
        ))

    # 翻页控件 (仅在多于一页时显示)
    if max_page > 1:
        source.reply(_build_page_controls(page, max_page, click_action))


def _build_page_controls(page: int, max_page: int, click_action) -> RTextList:
    """构建底部可点击翻页栏: [上一页] 第 X/Y 页 [下一页]"""
    list_cmd = my_lib.cmd("home") + " list"
    parts = ["  "]
    if page > 1:
        prev_cmd = f"{list_cmd} {page - 1}"
        parts.append(
            RText("[上一页]", color=RColor.aqua).c(click_action, prev_cmd).h(prev_cmd)
        )
    else:
        parts.append(RText("[上一页]", color=RColor.dark_gray))  # 已是首页, 不可点
    parts.append(f" §7{page}/{max_page} ")
    if page < max_page:
        next_cmd = f"{list_cmd} {page + 1}"
        parts.append(
            RText("[下一页]", color=RColor.aqua).c(click_action, next_cmd).h(next_cmd)
        )
    else:
        parts.append(RText("[下一页]", color=RColor.dark_gray))  # 已是末页, 不可点
    return RTextList(*parts)


# ============================================================
# !!mhome <home_name>  (传送到指定家, 受 CD 限制, 普通传送)
# ============================================================

@mcdr.new_thread("TpMaple-home")
def go_home(source: mcdr.CommandSource, context: dict):
    """!!mhome <名字>: 传送到指定的家 (普通传送, 受 home 冷却限制)。"""
    if not source.is_player:
        source.reply(f"{TAG}§c该命令只能由玩家执行")
        return

    player_name = source.player
    home_name: str = context["home_name"]

    player_uuid = my_lib.get_player_uuid(player_name)
    if player_uuid is None:
        source.reply(f"{TAG}§c无法获取你的 UUID")
        return

    # CD 检查
    remain = my_lib.check_cd(player_uuid, "home")
    if remain > 0:
        source.reply(f"{TAG}§c传送冷却中, 还需等待 §6{remain}§c 秒")
        return

    pdata = my_lib.get_player_data(player_uuid)
    homes: dict = pdata.get("homes", {})
    info = homes.get(home_name)

    if info is None:
        source.reply(f"{TAG}§c未找到名为 §e{home_name} §c的家")
        return

    # 记录回家前位置为 back 点, 再普通传送
    my_lib.record_back_point(player_name)
    tp_core.teleport(player_name, info["x"], info["y"], info["z"], info["dimension"])
    my_lib.record_cd(player_uuid, "home")

    dim_cn = dimension_to_cn(info["dimension"])
    source.reply(
        f"{TAG}§a已传送到 §e{home_name} §7— {dim_cn} "
        f"({info['x']:.1f}, {info['y']:.1f}, {info['z']:.1f})"
    )


# ============================================================
# !!mdelhome <home_name>  (删除指定家)
# ============================================================

@mcdr.new_thread("TpMaple-delhome")
def del_home(source: mcdr.CommandSource, context: dict):
    """!!mdelhome <名字>: 删除指定的家, 不存在时提示。"""
    if not source.is_player:
        source.reply(f"{TAG}§c该命令只能由玩家执行")
        return

    player_name = source.player
    home_name: str = context["home_name"]

    player_uuid = my_lib.get_player_uuid(player_name)
    if player_uuid is None:
        source.reply(f"{TAG}§c无法获取你的 UUID")
        return

    pdata = my_lib.get_player_data(player_uuid)
    homes: dict = pdata.get("homes", {})

    if home_name not in homes:
        source.reply(f"{TAG}§c未找到名为 §e{home_name} §c的家")
        return

    del homes[home_name]
    my_lib.save_player_data()

    source.reply(f"{TAG}§a已删除家 §e{home_name}")