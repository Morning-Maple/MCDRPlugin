"""
item_util.py — 物品读取 / 槽位解析 / give 重建 / 精确扣除

槽位编号约定 (玩家视角, 1-based):
    1-9   = 快捷栏  (NBT Slot 0-8)
    10-36 = 主背包  (NBT Slot 9-35)
不含盔甲 / 副手。
"""
import ast
import json
from typing import List, Optional, Tuple

import minecraft_data_api as api

from . import mail_lib
from . import snbt
from .config import AttachmentItem

# parse_slot_arg 的特殊返回: 表示"主手物品"
MAINHAND = "__mainhand__"


# ============================================================
# 槽位参数解析
# ============================================================

def parse_slot_arg(arg: str):
    """解析附件参数, 返回 NBT 槽位列表 (0-35); 主手返回 MAINHAND。

    支持:
      - 空        -> 主手物品 (MAINHAND)
      - "allhand" -> 快捷栏 1-9 (NBT 0-8)
      - "[(1,5), 27, 28]" -> 区间/单格混合

    非法输入抛出 ValueError。
    """
    arg = (arg or "").strip()
    if arg == "":
        return MAINHAND
    if arg.lower() == "allhand":
        return list(range(0, 9))
    if arg.startswith("["):
        try:
            value = ast.literal_eval(arg)
        except (ValueError, SyntaxError):
            raise ValueError("附件列表格式错误")
        if not isinstance(value, (list, tuple)):
            raise ValueError("附件列表必须是 [] 形式")
        user_slots = set()
        for el in value:
            if isinstance(el, bool):
                raise ValueError("附件列表元素非法")
            if isinstance(el, int):
                user_slots.add(el)
            elif isinstance(el, (tuple, list)) and len(el) == 2 \
                    and all(isinstance(x, int) and not isinstance(x, bool) for x in el):
                lo, hi = min(el), max(el)
                for i in range(lo, hi + 1):
                    user_slots.add(i)
            else:
                raise ValueError("附件列表元素必须是整数或 (起, 止) 区间")
        # 1-based 用户编号 -> 0-based NBT 槽位, 过滤越界
        nbt_slots = sorted(s - 1 for s in user_slots if 1 <= s <= 36)
        if not nbt_slots:
            raise ValueError("附件列表没有有效的格子 (有效范围 1-36)")
        return nbt_slots
    raise ValueError("附件参数只支持: 留空(主手) / allhand / [格子列表]")


# ============================================================
# 槽位 <-> /item 选择器
# ============================================================

def nbt_slot_to_selector(nbt_slot: int) -> Optional[str]:
    """NBT 槽位 -> /item replace 的玩家槽位选择器"""
    if 0 <= nbt_slot <= 8:
        return "hotbar.{}".format(nbt_slot)
    if 9 <= nbt_slot <= 35:
        return "inventory.{}".format(nbt_slot - 9)
    return None


# ============================================================
# 物品读取 -> 附件
# ============================================================

def _plain_text(raw) -> str:
    """把文本组件 (custom_name) 尽力转为纯文本"""
    if raw is None:
        return ""
    if isinstance(raw, dict):
        text = str(raw.get("text", ""))
        for e in raw.get("extra", []) or []:
            text += _plain_text(e)
        return text
    if isinstance(raw, list):
        return "".join(_plain_text(e) for e in raw)
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                return _plain_text(json.loads(s))
            except (ValueError, TypeError):
                return s
        return s
    return str(raw)


def _build_attachment(item: dict) -> Optional[AttachmentItem]:
    """把一个库存物品 dict 转为 AttachmentItem; 空物品返回 None"""
    item_id = item.get("id")
    if not item_id or item_id == "minecraft:air":
        return None
    # 1.20.5+ 用 count, 兼容旧版 Count
    count = item.get("count", item.get("Count", 1))
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 1
    if count <= 0:
        return None
    # 1.20.5+ 用 components, 兼容旧版 tag
    components = item.get("components") or item.get("tag") or {}
    comp_str = snbt.serialize_components(components) if isinstance(components, dict) else ""
    display = _plain_text(components.get("minecraft:custom_name")) if isinstance(components, dict) else ""
    return AttachmentItem(
        item_id=str(item_id),
        count=count,
        components=comp_str,
        display_name=display,
    )


def collect_attachments(player: str, slot_spec) -> Tuple[List[AttachmentItem], List[int]]:
    """读取玩家指定槽位的物品。

    :param player: 玩家名
    :param slot_spec: parse_slot_arg 的返回值 (NBT 槽位列表 或 MAINHAND)
    :return: (附件列表, 实际有物品的 NBT 槽位列表)
    """
    inventory = api.get_player_info(player, "Inventory") or []
    by_slot = {}
    for it in inventory:
        if isinstance(it, dict) and "Slot" in it:
            try:
                by_slot[int(it["Slot"])] = it
            except (TypeError, ValueError):
                continue

    if slot_spec == MAINHAND:
        selected = api.get_player_info(player, "SelectedItemSlot")
        try:
            selected = int(selected)
        except (TypeError, ValueError):
            selected = 0
        target_slots = [selected]
    else:
        target_slots = list(slot_spec)

    attachments: List[AttachmentItem] = []
    used_slots: List[int] = []
    for s in target_slots:
        item = by_slot.get(s)
        if item is None:
            continue
        attach = _build_attachment(item)
        if attach is None:
            continue
        attachments.append(attach)
        used_slots.append(s)
    return attachments, used_slots


# ============================================================
# 扣除 / 发放
# ============================================================

def deduct_slots(player: str, nbt_slots: List[int]):
    """按格子精确清除玩家物品 (只清指定格, 不误删别处同种物品)"""
    server = mail_lib.plugin_server
    for s in nbt_slots:
        selector = nbt_slot_to_selector(s)
        if selector is None:
            continue
        server.execute("item replace entity {} {} with air".format(player, selector))


def give_attachments(player: str, attachments: List[AttachmentItem]):
    """把附件物品 give 给玩家 (背包满则掉地上, 可接受)"""
    server = mail_lib.plugin_server
    for a in attachments:
        item_arg = a.item_id
        if a.components:
            item_arg += "[{}]".format(a.components)
        server.execute("give {} {} {}".format(player, item_arg, a.count))
