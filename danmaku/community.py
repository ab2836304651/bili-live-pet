"""社区协议弹幕后端（broadcastlv WebSocket）。

重要说明（2026-08-05 多房间实测）：
- B站已全面封禁匿名弹幕查看：匿名连接（即使认证 code=0）一律返回
  LOG_IN_NOTICE（"未登录无法查看消息"），不会推送任何弹幕。
- 因此本后端必须填写登录 Cookie（SESSDATA）才能收到弹幕；
  sessdata 为空时收到 LOG_IN_NOTICE 会给出明确提示并停止重连。
- 官方推荐使用 danmaku/open_live.py（Open Live 开放平台后端）。

实现细节（2026-08 实测验证）：
- getDanmuInfo 接口需要 WBI 签名（w_rid/wts）+ buvid 风控 Cookie 才能通过；
- 连接 wss://<host>:2245/sub，认证包 protover=3；
- 消息包需 zlib/brotli 解压。
"""
from __future__ import annotations

import base64
import json
import time
from hashlib import md5
from typing import Callable, Optional

import requests
import websocket

from core.events import LiveEvent, LiveEventType
from danmaku import packets as pk
from danmaku.base import DanmakuListener

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DANMU_PORT = 2245

# WBI 签名参数混合表（公开固定值）
_MIXIN_TABLE = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


def _get_mixin_key(session: requests.Session) -> str:
    """从 nav 接口取 WBI img/sub key 并混合出 32 位 mixin key。"""
    nav = session.get("https://api.bilibili.com/x/web-interface/nav", timeout=15).json()
    wbi = (nav.get("data") or {}).get("wbi_img")
    if not wbi:
        raise RuntimeError("获取 WBI 密钥失败（nav 接口无 wbi_img）")
    img_key = wbi["img_url"].rsplit("/", 1)[-1].split(".")[0]
    sub_key = wbi["sub_url"].rsplit("/", 1)[-1].split(".")[0]
    raw = img_key + sub_key
    return "".join(raw[i] for i in _MIXIN_TABLE)[:32]


def wbi_sign(session: requests.Session, mixin_key: str, params: dict) -> dict:
    """对接口参数做 WBI 签名（追加 wts 与 w_rid）。"""
    params = dict(params)
    params["wts"] = int(time.time())
    query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    params["w_rid"] = md5((query + mixin_key).encode("utf-8")).hexdigest()
    return params


def _read_varint(data: bytes, i: int) -> tuple:
    """读取 protobuf varint，返回 (值, 新下标)。"""
    val, shift = 0, 0
    while i < len(data):
        b = data[i]
        i += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            return val, i
        shift += 7
    return val, i


def parse_interact_v2(pb_b64: str) -> tuple:
    """解析 INTERACT_WORD_V2 的 data.pb（base64 protobuf），返回 (uid, uname)。

    高流量房间的进场事件改用 protobuf 编码（bilibili message.Interact）：
    field1=uid(varint)、field2=uname(string)；其余字段跳过。解析失败返回 (0, "")。
    """
    try:
        data = base64.b64decode(pb_b64)
    except Exception:
        return 0, ""
    uid, uname = 0, ""
    i, n = 0, len(data)
    while i < n:
        tag = data[i]
        i += 1
        field, wire = tag >> 3, tag & 7
        if wire == 0:  # varint
            val, i = _read_varint(data, i)
            if field == 1:
                uid = val
        elif wire == 1:  # 64-bit
            i += 8
        elif wire == 2:  # length-delimited
            ln, i = _read_varint(data, i)
            if field == 2:
                uname = data[i:i + ln].decode("utf-8", errors="replace")
            i += ln
        elif wire == 5:  # 32-bit
            i += 4
        else:
            break  # 未知 wire type，停止解析
        if uid and uname:
            break
    return uid, uname


class CommunityBackend(DanmakuListener):
    """社区协议弹幕后端（需登录 Cookie，仅作备选）。"""

    def __init__(
        self,
        room_id: int,
        on_event: Callable[[LiveEvent], None],
        logger: Optional[Callable[[str], None]] = None,
        *,
        sessdata: str = "",
    ):
        super().__init__(room_id, on_event, logger)
        self.sessdata = sessdata.strip()
        self._danmaku_count = 0
        self._uid = 0

    def _new_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Referer": "https://live.bilibili.com/"})
        s.get("https://www.bilibili.com/", timeout=15)  # 拿 buvid3/b_nut
        spi = s.get("https://api.bilibili.com/x/frontend/finger/spi", timeout=15).json()["data"]
        s.cookies.set("buvid3", spi["b_3"])
        s.cookies.set("buvid4", spi["b_4"])
        if self.sessdata:
            s.cookies.set("SESSDATA", self.sessdata)
            try:
                nav = s.get("https://api.bilibili.com/x/web-interface/nav", timeout=15).json()
                self._uid = int((nav.get("data") or {}).get("mid") or 0)
            except Exception:
                self._uid = 0
        return s

    def _get_danmu_conf(self, s: requests.Session) -> tuple:
        """获取弹幕服务器 host 与 token（需 WBI 签名）。"""
        mixin_key = _get_mixin_key(s)
        s.headers["Referer"] = f"https://live.bilibili.com/{self.room_id}"
        conf = s.get(
            "https://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo",
            params=wbi_sign(s, mixin_key, {"id": self.room_id, "type": 0}),
            timeout=15,
        ).json()
        if conf.get("code") != 0:
            raise RuntimeError(f"getDanmuInfo 失败: code={conf.get('code')} msg={conf.get('message')}")
        data = conf["data"]
        host = data["host_list"][0]["host"]
        return host, data.get("token", "")

    def connect(self) -> None:
        try:
            s = self._new_session()
            host, token = self._get_danmu_conf(s)
        except Exception as exc:
            self._info(f"获取弹幕配置失败: {exc}")
            self._emit(LiveEvent(type=LiveEventType.SYSTEM, content=f"弹幕配置获取失败: {exc}"))
            return

        url = f"wss://{host}:{DANMU_PORT}/sub"
        self._info(f"连接 {url}" + ("（已带登录 Cookie）" if self.sessdata else "（匿名，B站已封禁匿名弹幕，建议填 SESSDATA）"))
        try:
            ws = websocket.create_connection(
                url, timeout=15,
                header=["User-Agent: Mozilla/5.0", f"Referer: https://live.bilibili.com/{self.room_id}"],
            )
        except Exception as exc:
            self._info(f"WebSocket 连接失败: {exc}")
            return

        auth = {
            "uid": self._uid, "roomid": self.room_id, "protover": 3,
            "platform": "web", "type": 2, "key": token,
        }
        ws.send_binary(pk.pack(pk.OP_AUTH, json.dumps(auth).encode("utf-8"), ver=1))
        ws.send_binary(pk.pack(pk.OP_HEARTBEAT, b"", ver=1))

        buf = b""
        last_hb = time.time()
        start_time = time.time()
        warn_done = False
        while self.running:
            ws.settimeout(10)
            try:
                buf += ws.recv()
            except websocket.WebSocketTimeoutException:
                pass
            except Exception as exc:
                self._info(f"连接中断: {exc}")
                break

            if time.time() - last_hb >= 30:
                try:
                    ws.send_binary(pk.pack(pk.OP_HEARTBEAT, b"", ver=1))
                    last_hb = time.time()
                except Exception:
                    break

            msgs, buf = pk.unpack(buf)
            for op, ver, body in msgs:
                if op == pk.OP_AUTH_REPLY:
                    self._handle_auth_reply(body)
                    if not self.running:  # 认证失败时已停止，退出外层循环
                        break
                elif op == pk.OP_HEARTBEAT_REPLY:
                    pass  # 4 字节人气值，无需处理
                elif op == pk.OP_MESSAGE:
                    try:
                        for _op, _ver, sub in pk.decompress_body(op, ver, body):
                            obj = pk.parse_json(sub)
                            if obj:
                                self._handle_message(obj)
                    except Exception as exc:
                        # 单条消息解压/解析失败不影响连接，跳过并记录
                        self._info(f"消息处理失败（已跳过）: {exc}")
            if not self.running:
                break

            # 连上 30 秒仍一条弹幕都没有 -> 提示一次（冷清房间/被风控两种可能）
            if not warn_done and time.time() - start_time > 30 and self._danmaku_count == 0:
                warn_done = True
                warn = ("提示：已连接直播间，但 30 秒内没有收到弹幕。\n"
                        "多半是房间当前比较冷清（无人发言，冷清房间可能几分钟才有一条弹幕），\n"
                        "也可能被官方风控（若启动日志里有 LOG_IN_NOTICE/认证失败提示则必是风控）。\n"
                        "风控时请填 config.yaml 的 danmaku.community.sessdata（登录 Cookie），"
                        "或改用官方 open_live 后端（见 README）")
                self._info(warn)
                self._emit(LiveEvent(type=LiveEventType.SYSTEM, content=warn))
        try:
            ws.close()
        except Exception:
            pass

    def _handle_auth_reply(self, body: bytes) -> None:
        """处理 op=8 认证回包；失败时提示并停止重连。"""
        try:
            obj = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            obj = {}
        code = obj.get("code", 0)
        if code != 0:
            msg = (f"弹幕服务器拒绝认证 (code={code})：{obj.get('message', '')}。\n"
                   "请检查 config.yaml 的 danmaku.community.sessdata（登录 Cookie）是否有效。")
            self._info(msg)
            self._emit(LiveEvent(type=LiveEventType.SYSTEM, content=msg))
            self._running.clear()
        else:
            self._info("认证成功")

    def _handle_message(self, obj: dict) -> None:
        cmd = obj.get("cmd", "")
        if cmd == "LOG_IN_NOTICE":
            # 官方风控：该房间未登录无法查看弹幕，匿名连接不会推送任何弹幕
            msg = ("直播间要求登录才能查看弹幕（官方风控：未登录无法查看消息）。\n"
                   "解决：① 浏览器登录 bilibili 后按 F12 → 应用 → Cookie，复制 SESSDATA "
                   "填入 config.yaml 的 danmaku.community.sessdata；"
                   "② 或申请 open_live 官方凭据（见 README）。")
            self._info(msg)
            self._emit(LiveEvent(type=LiveEventType.SYSTEM, content=msg))
            self._running.clear()  # 停止无意义的挂等/重连
            return
        if cmd.startswith("DANMU_MSG"):
            self._danmaku_count += 1
            info = obj.get("info") or []
            user = (info[2] or []) if len(info) > 2 else []
            self._emit(LiveEvent(
                type=LiveEventType.DANMAKU,
                user_name=user[1] if len(user) > 1 else "?",
                user_id=user[0] if user else 0,
                content=info[1] if len(info) > 1 else "",
            ))
        elif cmd in ("INTERACT_WORD", "INTERACT_WORD_V2"):
            data = obj.get("data") or {}
            if cmd == "INTERACT_WORD":
                uname, uid = data.get("uname", ""), data.get("uid", 0)
            else:
                # V2 用户名在 protobuf（data.pb）里，需解包
                uid, uname = parse_interact_v2(str(data.get("pb", "")))
            self._emit(LiveEvent(
                type=LiveEventType.ENTER,
                user_name=uname,
                user_id=uid,
            ))
        elif cmd == "SEND_GIFT":
            data = obj.get("data") or {}
            self._emit(LiveEvent(
                type=LiveEventType.GIFT,
                user_name=data.get("uname", ""),
                user_id=data.get("uid", 0),
                extra={"gift_name": data.get("giftName", ""), "num": data.get("num", 1)},
            ))
        elif cmd == "SUPER_CHAT_MESSAGE":
            data = obj.get("data") or {}
            user = data.get("user_info") or {}
            self._emit(LiveEvent(
                type=LiveEventType.SUPER_CHAT,
                user_name=user.get("uname", ""),
                user_id=user.get("uid", 0),
                content=data.get("message", ""),
                extra={"price": data.get("price", 0) / 100},
            ))
        elif cmd == "DANMU_AGGREGATION":
            # 高流量房间的聚合弹幕包：可能含多条消息
            data = obj.get("data") or {}
            msgs = str(data.get("msg", "")).split("\n")
            for m in msgs:
                m = m.strip()
                if m:
                    self._emit(LiveEvent(
                        type=LiveEventType.DANMAKU,
                        user_name=data.get("uname", "") or "?",
                        user_id=data.get("uid", 0),
                        content=m,
                    ))
        elif cmd == "COMBO_SEND":
            # 连击礼物
            data = obj.get("data") or {}
            self._emit(LiveEvent(
                type=LiveEventType.GIFT,
                user_name=data.get("uname", ""),
                user_id=data.get("uid", 0),
                extra={"gift_name": data.get("gift_name", ""), "num": data.get("combo_num", 1)},
            ))
        elif cmd == "GUARD_BUY":
            data = obj.get("data") or {}
            self._emit(LiveEvent(
                type=LiveEventType.GUARD,
                user_name=data.get("username", ""),
                user_id=data.get("uid", 0),
                extra={"guard_level": data.get("gift_name", "")},
            ))
        elif cmd in ("LIKE", "LIKE_INFO_V3_CLICK"):
            data = obj.get("data") or {}
            self._emit(LiveEvent(
                type=LiveEventType.LIKE,
                user_name=data.get("uname", ""),
                user_id=data.get("uid", 0),
            ))
