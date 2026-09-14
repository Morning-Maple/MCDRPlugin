"""
slp.py — Minecraft Server List Ping (SLP) 工具

用「多人服务器列表」同款的握手协议去探测一个 MC 子服是否「玩家可进入」, 并顺带
取回在线人数 / MOTD / 版本 / 延迟等信息。纯标准库 socket 实现, 零第三方依赖。

适配范围: 仅适配 Minecraft Java 版 1.20+ (现代 SLP 协议), 不考虑 1.6 及更早的
legacy ping 兼容。

对外只需用 ServerListPing 这个工具类:

    from .slp import ServerListPing

    status = ServerListPing.ping("127.0.0.1", 25566)
    if status is None:
        print("子服未就绪 (玩家进不去)")
    else:
        print(status.online, "/", status.max_players, status.version_name)

    # 只关心在线与否:
    if ServerListPing.is_online("127.0.0.1", 25566):
        ...

注意: ping() 会阻塞至多 timeout 秒, 在 MCDR 插件中请放进 @new_thread 里调用。
"""
import json
import socket
import struct
import time
from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# 结果数据结构
# ============================================================

@dataclass
class SlpStatus:
    """一次成功的 SLP 探测结果。

    :ivar online: 当前在线人数
    :ivar max_players: 最大人数上限
    :ivar players: 在线玩家名字样本 (来自 players.sample); 服务端可能不返回或只返回部分,
                   故其长度不一定等于 online
    :ivar version_name: 服务端版本名 (如 '1.20.1', 或整合端自定义字符串)
    :ivar protocol: 协议号
    :ivar motd: 服务器描述 (MOTD), 已展平为纯文本 (保留 §颜色码)
    :ivar latency_ms: ping/pong 往返延迟 (毫秒); 未测或测量失败为 None
    :ivar raw: 服务端返回的原始 JSON dict (需要更多字段时自取)
    """
    online: int
    max_players: int
    version_name: str
    protocol: int
    motd: str
    players: list = field(default_factory=list)
    latency_ms: Optional[float] = None
    raw: dict = field(default_factory=dict)


# ============================================================
# 工具类
# ============================================================

class ServerListPing:
    """Minecraft Java 版 1.20+ 的 Server List Ping 客户端。

    全部方法为类方法, 无需实例化, 外部直接 ServerListPing.ping(...) 调用。
    """

    DEFAULT_PORT = 25565
    DEFAULT_TIMEOUT = 1.0
    # 握手包里的协议版本号; 仅占位, status 探测中服务端会回传它自己的版本, 此值无影响。
    HANDSHAKE_PROTOCOL = 767  # 1.21 的协议号, 随便填一个 >=1.20 的即可

    # ----------------------------------------------------------------
    # 对外主入口
    # ----------------------------------------------------------------

    @classmethod
    def ping(
        cls,
        host: str,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
        with_latency: bool = True,
    ) -> Optional[SlpStatus]:
        """探测目标子服状态。

        探测成功 (服务端按 SLP 协议正常应答) 返回 SlpStatus, 这等价于「玩家此刻能
        进入该服」; 连接失败 / 超时 / 应答非法一律返回 None (视为不可进入)。

        :param host: 子服地址 (一般为 127.0.0.1)
        :param port: 子服游戏端口
        :param timeout: 连接与读写的超时秒数
        :param with_latency: 是否额外发送 ping 包测量延迟 (失败不影响状态获取)
        :return: SlpStatus 或 None
        """
        try:
            with socket.create_connection((host, port), timeout=timeout) as sock:
                sock.settimeout(timeout)

                # 1) 握手包 (next state = 1, 即 status)
                handshake = (
                    b"\x00"  # packet id: handshake
                    + cls._pack_varint(cls.HANDSHAKE_PROTOCOL)
                    + cls._pack_string(host)
                    + struct.pack(">H", port)
                    + b"\x01"  # next state: status
                )
                sock.sendall(cls._pack_packet(handshake))

                # 2) status request 包 (空)
                sock.sendall(cls._pack_packet(b"\x00"))

                # 3) 读取 status response
                payload = cls._read_packet(sock)
                if not payload or payload[0] != 0x00:
                    return None
                # 去掉 packet id 后, 是一个 (VarInt 长度 + UTF-8) 的 JSON 字符串
                offset = 1
                str_len, offset = cls._read_varint_from_bytes(payload, offset)
                json_bytes = payload[offset:offset + str_len]
                data = json.loads(json_bytes.decode("utf-8"))

                # 4) 可选: ping/pong 测延迟
                latency_ms = None
                if with_latency:
                    latency_ms = cls._measure_latency(sock)

                return cls._build_status(data, latency_ms)
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    @classmethod
    def is_online(
        cls,
        host: str,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> bool:
        """仅判断子服是否「玩家可进入」(不关心人数等详情)。"""
        return cls.ping(host, port, timeout, with_latency=False) is not None

    # ----------------------------------------------------------------
    # 内部: 结果构建
    # ----------------------------------------------------------------

    @classmethod
    def _build_status(cls, data: dict, latency_ms: Optional[float]) -> SlpStatus:
        players = data.get("players") or {}
        version = data.get("version") or {}
        sample = players.get("sample") or []
        names = [str(p.get("name", "")) for p in sample if isinstance(p, dict) and p.get("name")]
        return SlpStatus(
            online=int(players.get("online", 0)),
            max_players=int(players.get("max", 0)),
            version_name=str(version.get("name", "")),
            protocol=int(version.get("protocol", 0)),
            motd=cls._extract_text(data.get("description")),
            players=names,
            latency_ms=latency_ms,
            raw=data,
        )

    @staticmethod
    def _extract_text(desc) -> str:
        """把 MOTD (可能是字符串 / chat component dict / 列表) 展平为纯文本。

        保留 § 颜色码原样; 不解析 1.16+ 的 RGB color 字段 (展示够用)。
        """
        if desc is None:
            return ""
        if isinstance(desc, str):
            return desc
        if isinstance(desc, dict):
            text = str(desc.get("text", ""))
            for extra in desc.get("extra", []) or []:
                text += ServerListPing._extract_text(extra)
            return text
        if isinstance(desc, list):
            return "".join(ServerListPing._extract_text(x) for x in desc)
        return str(desc)

    # ----------------------------------------------------------------
    # 内部: 延迟测量 (ping/pong)
    # ----------------------------------------------------------------

    @classmethod
    def _measure_latency(cls, sock: socket.socket) -> Optional[float]:
        """发送 ping 包并等待 pong, 返回往返毫秒数; 任何异常返回 None。"""
        try:
            token = int(time.time() * 1000) & 0x7FFFFFFFFFFFFFFF
            ping_packet = b"\x01" + struct.pack(">q", token)
            start = time.perf_counter()
            sock.sendall(cls._pack_packet(ping_packet))
            pong = cls._read_packet(sock)
            elapsed = (time.perf_counter() - start) * 1000
            if not pong or pong[0] != 0x01:
                return None
            return round(elapsed, 1)
        except (OSError, ValueError):
            return None

    # ----------------------------------------------------------------
    # 内部: 协议编解码 (VarInt / String / Packet)
    # ----------------------------------------------------------------

    @staticmethod
    def _pack_varint(value: int) -> bytes:
        """把一个 (非负) 整数编码为 VarInt 字节序列。"""
        if value < 0:
            value &= 0xFFFFFFFF
        out = bytearray()
        while True:
            byte = value & 0x7F
            value >>= 7
            if value:
                out.append(byte | 0x80)
            else:
                out.append(byte)
                return bytes(out)

    @classmethod
    def _pack_string(cls, text: str) -> bytes:
        """把字符串编码为 (VarInt 长度 + UTF-8 字节)。"""
        raw = text.encode("utf-8")
        return cls._pack_varint(len(raw)) + raw

    @classmethod
    def _pack_packet(cls, payload: bytes) -> bytes:
        """给包体加上 VarInt 长度前缀, 形成一个完整未压缩数据包。"""
        return cls._pack_varint(len(payload)) + payload

    @classmethod
    def _read_packet(cls, sock: socket.socket) -> bytes:
        """读取一个完整数据包的包体 (已剥离长度前缀, 仍含 packet id)。"""
        length = cls._read_varint_from_sock(sock)
        return cls._read_fully(sock, length)

    @staticmethod
    def _read_fully(sock: socket.socket, n: int) -> bytes:
        """从 socket 精确读取 n 个字节, 不足则继续读, 连接断开则报错。"""
        if n <= 0:
            return b""
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("连接在读取过程中被关闭")
            buf.extend(chunk)
        return bytes(buf)

    @classmethod
    def _read_varint_from_sock(cls, sock: socket.socket) -> int:
        """从 socket 逐字节读取一个 VarInt。"""
        num = 0
        for i in range(5):  # VarInt 最多 5 字节
            byte = cls._read_fully(sock, 1)[0]
            num |= (byte & 0x7F) << (7 * i)
            if not (byte & 0x80):
                return num
        raise ValueError("VarInt 超过 5 字节, 数据非法")

    @staticmethod
    def _read_varint_from_bytes(data: bytes, offset: int):
        """从字节串的 offset 处解析一个 VarInt, 返回 (值, 新 offset)。"""
        num = 0
        for i in range(5):
            byte = data[offset]
            offset += 1
            num |= (byte & 0x7F) << (7 * i)
            if not (byte & 0x80):
                return num, offset
        raise ValueError("VarInt 超过 5 字节, 数据非法")


# ============================================================
# 手动测试: python -m multi_server_control_maple.slp <host> [port]
# ============================================================

if __name__ == "__main__":
    import sys

    _host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    _port = int(sys.argv[2]) if len(sys.argv) > 2 else 25565
    print(f"正在探测 {_host}:{_port} ...")
    _status = ServerListPing.ping(_host, _port)
    if _status is None:
        print("结果: 不可进入 (未开启 / 启动中 / 连接失败)")
    else:
        print("结果: 运行中 (玩家可进入)")
        print(f"  人数  : {_status.online}/{_status.max_players}")
        print(f"  玩家  : {', '.join(_status.players) if _status.players else '(无样本)'}")
        print(f"  版本  : {_status.version_name} (protocol {_status.protocol})")
        print(f"  延迟  : {_status.latency_ms} ms")
        print(f"  MOTD  : {_status.motd!r}")
