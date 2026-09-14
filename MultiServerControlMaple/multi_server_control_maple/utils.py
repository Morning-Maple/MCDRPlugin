"""
utils.py — 通用工具函数

当前为基础框架, 仅放置与具体业务无关的通用校验/格式化工具。
子服名校验沿用参考插件的约定: 仅接受 [a-z][a-z0-9]*, 即首字符为小写字母,
其余为小写字母或数字。
"""
import re

# 子服名合法性: 首字符小写字母, 其余小写字母或数字 (参考原 MultiServerControl)
_SERVER_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*$")


def is_valid_server_name(name: str) -> bool:
    """校验子服名是否合法 (首字符小写字母, 其余小写字母或数字)。"""
    return bool(name) and bool(_SERVER_NAME_PATTERN.match(name))
