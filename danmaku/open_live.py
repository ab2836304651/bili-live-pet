"""哔哩哔哩直播开放平台（Open Live）官方弹幕后端。

接入流程（2026 实测核实自官方 .NET SDK 与第三方 Java SDK）：
1. 在 https://open-live.bilibili.com 开放平台创建应用，拿到 app_id、
   access_key_id、access_key_secret，并在应用里绑定自己的直播间；
2. 应用启动：POST https://live-open.biliapi.com/v2/app/start
   （body: {"code": 连接码, "app_id": 应用ID}，请求头 HMAC-SHA256 签名）
   -> 返回 websocket_info.auth_body / wss_link / game_info.game_id；
3. 连接 wss_link[0]，把 auth_body 原样作为认证包（op=7）发送；
4. 每 30s 发送 WS 心跳（op=2），每 20s 调用 /v2/app/heartbeat 保活；
5. 接收 op=5 消息：WSS 不压缩，body 即 JSON，
   cmd 前缀 LIVE_OPEN_PLATFORM_*。

优点：官方渠道、稳定合规，专为直播姬/直播间工具设计。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
import uuid
from typing import Callable, Optional

import requests
import websocket

from core.events import LiveEvent, LiveEventType
from danmaku import packets as pk
from danmaku.base import DanmakuListener

API_BASE = "https://live-open.biliapi.com"
WS_HEARTBEAT_SEC = 30   # 长连心跳
APP_HEARTBEAT_SEC = 20  # 项目（应用）心跳


class OpenLiveBackend(DanmakuListener):
    """官方 Open Live 弹幕后端。"""

    def __init__(
        self,
        room_id: int,
        on_event: Callable[[LiveEvent], None],
        logger: Optional[Callable[[str], None]] = None,
        *,
        app_id: str = "",
        access_key_id: str = "",
        access_key_secret: str = "",
        code: str = "",
    ):
        super().__init__(room_id, on_event, logger)
        self.app_id = str(app_id).strip()
        self.access_key_id = access_key_id.strip()
        self.access_key_secret = access_key_secret.strip()
        self.code = code.strip()
        self._game_id: str = ""
        self._ws: Optional[websocket.WebSocket] = None
        self._lock = threading.Lock()
        self._unknown_cmds: dict = {}

    # ---------- 签名 ----------

    def _sign_headers(self, body_json: str) -> dict:
        """构造 /v2/app/start 所需的签名请求头。"""
        ts = str(int(time.time()))
        headers = {
            "x-bili-accesskeyid": self.access_key_id,
            "x-bili-content-md5": hashlib.md5(body_json.encode("utf-8")).hexdigest(),
            "x-bili-signature-method": "HMAC-SHA256",
            "x-bili-signature-nonce": str(uuid.uuid4()),
            "x-bili-signature-version": "1.0",
            "x-bili-timestamp": ts,
        }
        sig_str = "\n".join(f"{k}:{headers[k]}" for k in sorted(headers))
        sig = hmac.new(
            self.access_key_secret.encode("utf-8"),
            sig_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers["Authorization"] = sig
        headers["Accept"] = "application/json"
        headers["Content-Type"] = "application/json"
        return headers

    # ---------- HTTP API ----------

    def _http_post(self, path: str, body: dict) -> dict:
        resp = requests.post(
            API_BASE + path,
            data=json.dumps(body),
            headers=self._sign_headers(json.dumps(body)),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"开放平台接口 {path} 失败: code={data.get('code')} msg={data.get('message')}")
        return data.get("data") or {}

    def _app_start(self) -> dict:
        data = self._http_post("/v2/app/start", {"code": self.code, "app_id": int(self.app_id)})
        ws_info = data.get("websocket_info") or {}
        game_info = data.get("game_info") or {}
        self._game_id = game_info.get("game_id", "")
        auth_body = ws_info.get("auth_body") or ""
        wss_links = ws_info.get("wss_link") or []
        if not auth_body or not wss_links:
            raise RuntimeError("app/start 未返回 auth_body/wss_link，请检查连接码与应用配置")
        return {"auth_body": auth_body, "wss_link": wss_links[0]}

    def _app_heartbeat(self) -> None:
        try:
            self._http_post("/v2/app/heartbeat", {"game_id": self._game_id})
        except Exception as exc:
            self._info(f"应用心跳失败: {exc}")

    def _app_end(self) -> None:
        try:
            self._http_post("/v2/app/end", {"app_id": int(self.app_id), "game_id": self._game_id})
        except Exception as exc:
            self._info(f"应用关闭失败: {exc}")

    # ---------- 消息解析 ----------

    def _handle_auth_reply(self, body: bytes) -> None:
        """处理 op=8 认证回包；失败时提示并停止。"""
        try:
            obj = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            obj = {}
        code = obj.get("code", 0)
        if code != 0:
            msg = (f"Open Live 认证失败 (code={code})：{obj.get('message', '')}。\n"
                   "连接码（code）有效期约 24 小时，请在开放平台重新获取后再试。")
            self._info(msg)
            self._emit(LiveEvent(type=LiveEventType.SYSTEM, content=msg))
            self._running.clear()
        else:
            self._info("认证成功")

    def _handle_message(self, obj: dict) -> None:
        cmd = obj.get("cmd", "")
        data = obj.get("data") or {}
        if cmd == "LIVE_OPEN_PLATFORM_DM":
            self._emit(LiveEvent(
                type=LiveEventType.DANMAKU,
                user_name=data.get("uname", ""),
                user_id=data.get("open_id", "") or data.get("uid", 0),
                content=data.get("msg", ""),
                extra={"fans_medal": data.get("fans_medal_name", "")},
            ))
        elif cmd == "LIVE_OPEN_PLATFORM_SUPER_CHAT":
            user = data.get("user_info") or {}
            self._emit(LiveEvent(
                type=LiveEventType.SUPER_CHAT,
                user_name=user.get("uname", ""),
                user_id=data.get("open_id", "") or user.get("open_id", 0),
                content=data.get("message", ""),
                extra={"price": data.get("price", 0) / 100 if data.get("price") else 0},
            ))
        elif cmd == "LIVE_OPEN_PLATFORM_SEND_GIFT":
            user = data.get("user_info") or {}
            self._emit(LiveEvent(
                type=LiveEventType.GIFT,
                user_name=user.get("uname", ""),
                user_id=data.get("open_id", "") or user.get("open_id", 0),
                extra={
                    "gift_name": data.get("gift_name", ""),
                    "num": data.get("gift_num", 1),
                },
            ))
        elif cmd == "LIVE_OPEN_PLATFORM_GUARD":
            user = data.get("user_info") or {}
            self._emit(LiveEvent(
                type=LiveEventType.GUARD,
                user_name=user.get("uname", ""),
                user_id=data.get("open_id", "") or user.get("open_id", 0),
                extra={"guard_level": data.get("guard_level", "")},
            ))
        elif cmd == "LIVE_OPEN_PLATFORM_LIKE":
            user = data.get("user_info") or {}
            self._emit(LiveEvent(
                type=LiveEventType.LIKE,
                user_name=user.get("uname", ""),
                user_id=data.get("open_id", "") or user.get("open_id", 0),
                extra={"count": data.get("like_count", 1)},
            ))
        else:
            # 其他命令仅记录前 20 种，避免高流量房间刷屏
            self._unknown_cmds[cmd] = self._unknown_cmds.get(cmd, 0) + 1
            if len(self._unknown_cmds) <= 20:
                self._info(f"未知命令: {cmd}")

    # ---------- 连接主循环 ----------

    def connect(self) -> None:
        """阻塞运行：启动应用 -> 建 WS -> 心跳 -> 收消息。"""
        if not (self.app_id and self.access_key_id and self.access_key_secret and self.code):
            self._info("Open Live 配置不完整（app_id/access_key_id/access_key_secret/code），请填写 config.yaml")
            self._emit(LiveEvent(type=LiveEventType.SYSTEM, content="Open Live 配置不完整，请检查 config.yaml"))
            return

        try:
            info = self._app_start()
        except Exception as exc:
            self._info(f"应用启动失败: {exc}")
            self._emit(LiveEvent(type=LiveEventType.SYSTEM, content=f"应用启动失败: {exc}"))
            return

        auth_body, wss_url = info["auth_body"], info["wss_link"]
        self._info(f"应用已启动 game_id={self._game_id}，连接 {wss_url}")

        # 项目心跳（须先于长连发送）
        hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        hb_thread.start()

        try:
            ws = websocket.create_connection(
                wss_url,
                timeout=15,
                header=["User-Agent: Mozilla/5.0 (bili-live-pet)"],
            )
        except Exception as exc:
            self._info(f"WebSocket 连接失败: {exc}")
            self._emit(LiveEvent(type=LiveEventType.SYSTEM, content=f"WebSocket 连接失败: {exc}"))
            return

        self._ws = ws
        ws.send_binary(pk.pack(pk.OP_AUTH, auth_body.encode("utf-8"), ver=1))
        self._info("认证包已发送，等待服务器确认…")

        buf = b""
        last_heartbeat = time.time()
        while self.running and self._ws:
            ws.settimeout(10)
            try:
                buf += ws.recv()
            except websocket.WebSocketTimeoutException:
                pass
            except Exception as exc:
                self._info(f"连接中断: {exc}")
                break

            # 定时心跳
            if time.time() - last_heartbeat >= WS_HEARTBEAT_SEC:
                try:
                    ws.send_binary(pk.pack(pk.OP_HEARTBEAT, b"", ver=1))
                    last_heartbeat = time.time()
                except Exception:
                    break

            msgs, buf = pk.unpack(buf)
            for op, ver, body in msgs:
                if op == pk.OP_AUTH_REPLY:
                    self._handle_auth_reply(body)
                    if not self.running:  # 认证失败时已停止
                        break
                elif op == pk.OP_HEARTBEAT_REPLY:
                    pass  # 4 字节人气值，无需处理
                elif op == pk.OP_MESSAGE:
                    try:
                        obj = pk.parse_json(body)
                        if obj:
                            self._handle_message(obj)
                    except Exception as exc:
                        # 单条消息解析失败不影响连接
                        self._info(f"消息解析失败（已跳过）: {exc}")
                # 忽略其他 op
            if not self.running:
                break

        self._info("连接已退出，清理资源…")
        self._cleanup()

    def _heartbeat_loop(self) -> None:
        """每 20s 调一次 HTTP 应用心跳，直到连接退出。"""
        while self.running:
            time.sleep(APP_HEARTBEAT_SEC)
            if not self.running:
                break
            self._app_heartbeat()

    def _cleanup(self) -> None:
        with self._lock:
            if self._ws:
                try:
                    self._ws.close()
                except Exception:
                    pass
                self._ws = None
        # 仅当应用成功启动（拿到 game_id）后才调用 end，避免空凭据报错
        if self._game_id:
            self._app_end()
            self._game_id = ""

    def stop(self) -> None:
        super().stop()
        self._cleanup()
