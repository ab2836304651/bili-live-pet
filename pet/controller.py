"""桌宠控制器：串联 弹幕后端 -> AI 回复 -> 窗口气泡。

线程模型：
- 弹幕监听器在自己的线程跑，通过 Qt Signal 把 LiveEvent 发到 GUI 线程；
- AI 调用在独立线程执行（不卡 UI），结果通过 Signal 回到 GUI 线程；
- 对话历史只允许在 GUI 线程读写。
"""
from __future__ import annotations

import re
import threading
from collections import deque
from pathlib import Path
from typing import Callable, Deque, List, Optional

from PySide6.QtCore import QObject, Signal

from ai.responder import Responder
from core.events import LiveEvent, LiveEventType
from danmaku.factory import create_backend


def default_logger(prefix: str = "[Pet]") -> Callable[[str], None]:
    from core.log import log as safe_log

    def _log(msg: str) -> None:
        safe_log(f"{prefix} {msg}")

    return _log


class PetController(QObject):
    """桌宠逻辑中枢。"""

    # GUI 线程槽连接：事件到达 / 回复就绪 / 状态消息
    event_signal = Signal(object)          # LiveEvent
    reply_signal = Signal(object)          # (LiveEvent, str)
    status_signal = Signal(str)            # 状态文本

    def __init__(
        self,
        config: dict,
        logger: Optional[Callable[[str], None]] = None,
        config_path: Optional[str] = None,
        prompt_path: Optional[str] = None,
    ):
        super().__init__()
        self._cfg = config
        self._log = logger or default_logger()
        self._config_path = config_path
        self._prompt_path = prompt_path
        self._listener = None
        self._responder: Optional[Responder] = None
        self._history: Deque[dict] = deque(maxlen=64)
        self._history_lock = threading.Lock()
        self._max_history = int((config.get("ai") or {}).get("max_history", 6))

    # ---------- 生命周期 ----------

    def start(self) -> None:
        """创建后端与 AI 回复器并开始监听。"""
        ai_cfg = self._cfg.get("ai") or {}
        prompt_text = self.current_prompt() or ""
        if not prompt_text:
            try:
                prompt_text = self._load_prompt(self._cfg.get("prompt_file", "config/prompt.md"))
            except FileNotFoundError:
                prompt_text = "你是直播间里的桌宠，回复要短平快，像弹幕一样口语化。"
        self._responder = Responder(ai_cfg, prompt_text, self._log)

        self._listener = create_backend(
            self._cfg,
            on_event=self._on_listener_event,
            logger=self._log,
        )
        self._listener.start()
        room = self._cfg.get("room_id", "?")
        self.status_signal.emit(f"已启动，监听房间 {room}（{self._cfg.get('danmaku', {}).get('backend', 'open_live')}）")

    def set_room(self, room_id: int) -> None:
        """热切换直播间（右键菜单用）：停止旧监听 -> 持久化 -> 重建监听。"""
        if not room_id or room_id <= 0:
            self.status_signal.emit("房间号无效，未切换")
            return
        if self._listener:
            self._listener.stop()
        self._cfg["room_id"] = int(room_id)
        if self._config_path:
            self._persist_room(int(room_id))
        self._listener = create_backend(
            self._cfg,
            on_event=self._on_listener_event,
            logger=self._log,
        )
        self._listener.start()
        self.status_signal.emit(f"已切换到房间 {room_id}（{self._cfg.get('danmaku', {}).get('backend', 'open_live')}）")

    def _persist_room(self, room_id: int) -> None:
        """只改 config.yaml 里的 room_id 一行，保留其它注释。"""
        try:
            path = Path(self._config_path)
            text = path.read_text(encoding="utf-8")
            new_text = re.sub(r"^room_id:.*$", f"room_id: {room_id}", text, count=1, flags=re.M)
            if new_text != text:
                path.write_text(new_text, encoding="utf-8")
                self._log(f"已保存房间号到 {path}")
        except OSError as exc:
            self._log(f"保存配置失败: {exc}")

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
        self.status_signal.emit("已停止")

    # ---------- 配置热应用（设置面板） ----------

    def current_config(self) -> dict:
        return self._cfg

    def current_prompt(self) -> str:
        if not self._prompt_path:
            return ""
        try:
            return Path(self._prompt_path).read_text(encoding="utf-8")
        except OSError:
            return ""

    def apply_config(self, new_cfg: dict) -> None:
        """设置面板保存后调用：更新配置、重建 AI 回复器、必要时重连直播间。"""
        room_changed = int(new_cfg.get("room_id") or 0) != int(self._cfg.get("room_id") or 0)
        self._cfg = new_cfg
        self._max_history = int((new_cfg.get("ai") or {}).get("max_history", 6))

        # 重建 AI 回复器（api_key / 模型 / 提示词变化）
        ai_cfg = self._cfg.get("ai") or {}
        prompt_text = self.current_prompt() or self._load_prompt(self._cfg.get("prompt_file", "config/prompt.md"))
        self._responder = Responder(ai_cfg, prompt_text, self._log)

        if room_changed:
            if self._listener:
                self._listener.stop()
            self._listener = create_backend(
                self._cfg,
                on_event=self._on_listener_event,
                logger=self._log,
            )
            self._listener.start()
            self.status_signal.emit(f"已切换到房间 {self._cfg.get('room_id')}")

    def test_reply(self) -> None:
        """右键菜单触发：让 AI 主动说一句开场白（不依赖弹幕）。"""
        if not self._responder:
            return
        fake = LiveEvent(type=LiveEventType.DANMAKU, user_name="主播", content="和小猫打个招呼吧~")
        fake._test = True  # 测试触发标记：失败时在气泡显示错误原因
        self._log("[测试] 请求 AI 回复…")
        threading.Thread(target=self._do_reply, args=(fake,), daemon=True).start()

    # ---------- 事件流 ----------

    def _on_listener_event(self, event: LiveEvent) -> None:
        """监听器线程 -> GUI 线程。"""
        self.event_signal.emit(event)

    def _handle_event(self, event: LiveEvent) -> None:
        """GUI 线程内处理事件。"""
        self._log(event.summary())
        if event.type == LiveEventType.SYSTEM:
            self.status_signal.emit(event.content)
            return

        if self._responder and self._responder.should_reply(event):
            self._append_history("user", Responder._event_to_prompt(event))
            threading.Thread(target=self._do_reply, args=(event,), daemon=True).start()
        elif event.type in (LiveEventType.DANMAKU, LiveEventType.GIFT,
                            LiveEventType.SUPER_CHAT, LiveEventType.GUARD):
            # 收到了但被策略拦下（冷却/触发词/概率），打日志便于排查
            self._log("（收到但按策略未回复：冷却中或触发条件不满足）")

    def _do_reply(self, event: LiveEvent) -> None:
        """后台线程：调用 AI，成功后把回复发回 GUI 线程。

        AI 失败不再静默：状态写日志；测试触发时把错误原因显示到气泡，
        让主播能立刻看到"key 无效 / 没额度 / 模型名错"这类问题。
        """
        if not self._responder:
            return
        with self._history_lock:
            snapshot = list(self._history)
        try:
            text = self._responder.reply(event, snapshot)
        except Exception as exc:
            err = f"AI 调用失败: {exc}"
            self._log(err)
            self.status_signal.emit(err)
            if getattr(event, "_test", False):
                self.reply_signal.emit((event, f"⚠️ {err}"))
            return
        if text:
            self._append_history("assistant", text)
            self.reply_signal.emit((event, text))

    # ---------- 历史 ----------

    def _append_history(self, role: str, content: str) -> None:
        with self._history_lock:
            self._history.append({"role": role, "content": content})
            while len(self._history) > 2 * self._max_history:
                self._history.popleft()

    # ---------- 工具 ----------

    @staticmethod
    def _load_prompt(path: str) -> str:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"提示词文件不存在: {p.resolve()}")
        return p.read_text(encoding="utf-8")
