"""
utils.py — 通用工具函数
"""
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