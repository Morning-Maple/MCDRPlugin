"""
utils.py — 通用工具函数
"""
import re
import struct
import uuid


def nbt_int_array_to_uuid(data: list[int]) -> uuid.UUID:
    """将 NBT int 数组 (4 个 32 位有符号整数) 转换为 UUID。

    Minecraft 1.16+ 的玩家 UUID 以 int array 形式存储 (如 [I; a, b, c, d])。
    这里把每个 int 按大端 32 位有符号 (>i) 打包成 4 字节, 拼成 16 字节再构造 UUID。

    :param data: 长度为 4 的整数列表
    :return: 对应的 UUID 对象
    """
    bytes_data = b''.join(struct.pack('>i', x) for x in data)
    return uuid.UUID(bytes=bytes_data)


# 数字块 (连续的数字字符); 用于 split 时保留分隔符, 得到「文本块/数字块」交替的列表
_DIGIT_CHUNK_RE = re.compile(r"(\d+)")

# 排序键中各类块的优先级: 数字块排在字母/其他块之前 (与 Windows 一致: '1' < 'a')
_RANK_DIGIT = 0
_RANK_TEXT = 1


def natural_sort_key(text: str) -> list:
    """生成「Windows 资源管理器」风格的自然排序键 (供 sorted(key=...) 使用)。

    规则按 Windows 的 ``StrCmpLogicalW`` (资源管理器实际调用的排序函数) 实测确定:

    1. **数字按数值比较**: ``wp2`` < ``wp10`` (而非按字符逐位比较), 且支持超长数字。
    2. **数字块整体排在字母之前**: ``1`` < ``a``, ``11`` < ``a``。
    3. **前导零: 位数多者在前**: ``wp001`` < ``wp01`` < ``wp1`` (数值相等时较长者优先)。
    4. **大小写不区分**: ``a`` 与 ``A`` 视为相等 (与 Windows 相同, 仅忽略大小写),
       相等者保持原有顺序 (Python 的 sorted 是稳定排序)。
    5. **短者在前**: ``wp`` < ``wp1`` (前缀关系)。

    与 Windows 的差异: 非 ASCII 字符 (如中文) 按 Unicode 码位比较, 而非拼音顺序。
    Windows 走的是按区域设置 (locale) 的拼音/笔画排序, 复刻它需要额外的拼音库;
    本插件的家名/地标名本身限定为 ASCII 字母数字, 因此不受影响。

    :param text: 待排序的文本
    :return: 可直接用于比较的键 (list of tuple)
    """
    parts = []
    # re.split 带捕获组时, 结果按「文本块, 数字块, 文本块, ...」交替排列
    for index, chunk in enumerate(_DIGIT_CHUNK_RE.split(str(text))):
        if not chunk:
            continue  # 空块不参与比较 (文本以数字开头/结尾时会产生空串)
        if index % 2 == 1:
            # 数字块: (优先级, 数值, -位数) —— -位数 让前导零多者排在前
            parts.append((_RANK_DIGIT, int(chunk), -len(chunk)))
        else:
            # 文本块: (优先级, 小写化文本) —— 小写化实现大小写不敏感
            parts.append((_RANK_TEXT, chunk.lower()))
    return parts