"""
snbt.py — 把 minecraft_data_api 解析出的 Python 对象重新序列化为 SNBT

务实版: data_api 解析时丢失了 NBT 类型后缀 (1b/5s/3L/2.0f), 这里只能尽力还原。
覆盖附魔/命名/lore/耐久/数量等绝大多数常见物品组件; 极端组件可能失真。
"""
import re

# 不需要加引号的 SNBT 键 (NBT 标准: 字母数字下划线点加减)
_BARE_KEY = re.compile(r'^[A-Za-z0-9_.+\-]+$')


def _quote_string(s: str) -> str:
    """把字符串包装为 SNBT 双引号字符串, 转义反斜杠与双引号"""
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _quote_key(key: str) -> str:
    """compound 的键: 含特殊字符 (如命名空间冒号) 时需要加引号"""
    if _BARE_KEY.match(key):
        return key
    return _quote_string(key)


def to_snbt(obj) -> str:
    """把一个 Python 对象序列化为 SNBT 文本"""
    if isinstance(obj, bool):
        return 'true' if obj else 'false'
    if isinstance(obj, int):
        return str(obj)
    if isinstance(obj, float):
        return repr(obj)
    if isinstance(obj, str):
        return _quote_string(obj)
    if isinstance(obj, (list, tuple)):
        return '[' + ','.join(to_snbt(e) for e in obj) + ']'
    if isinstance(obj, dict):
        return '{' + ','.join(
            '{}:{}'.format(_quote_key(str(k)), to_snbt(v)) for k, v in obj.items()
        ) + '}'
    if obj is None:
        return '{}'
    return _quote_string(str(obj))


def serialize_components(components: dict) -> str:
    """把物品的 components 字典序列化为 give 命令方括号内的组件串。

    顶层组件键为资源路径 (如 minecraft:enchantments), 使用 '=' 连接, 不加引号。
    返回不含外层 [] 的字符串; 空字典返回 ""。
    """
    if not components:
        return ""
    parts = []
    for key, value in components.items():
        parts.append('{}={}'.format(key, to_snbt(value)))
    return ','.join(parts)
