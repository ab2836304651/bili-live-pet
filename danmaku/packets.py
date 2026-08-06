"""B站直播二进制弹幕协议（包头编解码）。

Open Live 与社区协议共用这套 16 字节大端包头：
    packetLength(4) | headerLength(2) | protocolVersion(2) | operation(4) | sequenceId(4)

说明（2026 实测）：
- 社区协议（broadcastlv）匿名连接已被官方封禁，仅返回"未登录无法查看"；
  本模块同时支持 Open Live（推荐）与社区协议两套解析。
- Open Live 的 wss 不压缩：operation=5 的消息体直接就是 JSON。
- 社区协议需要 zlib / brotli 解压，这里按需解压。
"""
from __future__ import annotations

import json
import struct
import zlib
from typing import List, Optional, Tuple

try:
    import brotli  # type: ignore
except ImportError:  # pragma: no cover
    brotli = None

HEADER_LEN = 16

# operation
OP_HEARTBEAT = 2            # 客户端 -> 服务端 心跳
OP_HEARTBEAT_REPLY = 3      # 服务端 -> 客户端 心跳回包（4字节人气值）
OP_MESSAGE = 5              # 服务端 -> 客户端 消息
OP_AUTH = 7                 # 客户端 -> 服务端 认证
OP_AUTH_REPLY = 8           # 服务端 -> 客户端 认证回包

# protocol version
VER_COMPRESSED_NONE = 0     # 不压缩，消息体即 JSON
VER_COMPRESSED_ZLIB = 2     # zlib 压缩
VER_COMPRESSED_BROTLI = 3   # brotli 压缩


def pack(op: int, body: bytes = b"", ver: int = 1) -> bytes:
    """构造一个数据包。"""
    return struct.pack(">IHHII", HEADER_LEN + len(body), HEADER_LEN, ver, op, 1) + body


def unpack(buf: bytes) -> Tuple[List[Tuple[int, int, bytes]], bytes]:
    """将缓冲区按包头拆分出若干 (op, ver, body) 元组，返回 (消息列表, 剩余字节)。"""
    msgs: List[Tuple[int, int, bytes]] = []
    while len(buf) >= HEADER_LEN:
        plen, hlen, ver, op, _seq = struct.unpack(">IHHII", buf[:HEADER_LEN])
        if plen < HEADER_LEN or len(buf) < plen:
            break
        msgs.append((op, ver, buf[hlen:plen]))
        buf = buf[plen:]
    return msgs, buf


def decompress_body(op: int, ver: int, body: bytes) -> List[Tuple[int, int, bytes]]:
    """解压（如需要）并拆分消息体为若干子包。

    - ver=0/1: body 即为 JSON（单条消息）
    - ver=2:   zlib 压缩，内部再嵌套若干包头
    - ver=3:   brotli 压缩，内部再嵌套若干包头
    """
    if ver in (VER_COMPRESSED_ZLIB, VER_COMPRESSED_BROTLI):
        if ver == VER_COMPRESSED_ZLIB:
            raw = zlib.decompress(body)
        else:
            if brotli is None:
                raise RuntimeError("收到 brotli 压缩消息但未安装 brotli 库")
            raw = brotli.decompress(body)
        return unpack(raw)[0]
    return [(op, ver, body)]


def parse_json(payload: bytes) -> Optional[dict]:
    """把消息负载解析为 JSON 对象，失败返回 None。"""
    try:
        obj = json.loads(payload.decode("utf-8"))
        return obj if isinstance(obj, dict) else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
