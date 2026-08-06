"""桌宠主窗口：透明无边框置顶、可拖动、气泡对话、右键菜单。

气泡样式（QSS）与托盘菜单都可在下面按需调整。
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QLabel, QMenu, QWidget

from pet.sprite import SpriteRenderer


class SpeechBubble(QLabel):
    """带小尾巴的圆角气泡。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._tail = True
        self.setStyleSheet(
            """
            QLabel {
                background: rgba(255, 255, 255, 235);
                color: #4A3B2A;
                border: 2px solid #E8A96E;
                border-radius: 12px;
                padding: 8px 12px;
                font-size: 14px;
            }
            """
        )
        self.setWordWrap(True)
        self.setMaximumWidth(240)
        self.hide()

    def show_text(self, text: str, seconds: float = 6.0) -> None:
        self.setText(text)
        self.adjustSize()
        self.show()
        self.raise_()
        if seconds > 0:
            QTimer.singleShot(int(seconds * 1000), self.hide)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self._tail:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        w, h = self.width(), self.height()
        # 底部中间小三角
        p.setBrush(QColor(255, 255, 255, 235))
        path = QPainterPath()
        path.moveTo(w / 2 - 8, h - 1)
        path.lineTo(w / 2, h + 8)
        path.lineTo(w / 2 + 8, h - 1)
        path.closeSubpath()
        p.drawPath(path)
        p.setBrush(QColor("#E8A96E"))
        p.drawRect(w / 2 - 8, h - 3, 16, 2)


class PetWindow(QWidget):
    """透明桌宠窗口。

    窗口分为上下两区：顶部 BUBBLE_ZONE 显示气泡，底部画桌宠本体，
    这样气泡不会因超出窗口被系统裁剪。
    """

    BUBBLE_ZONE = 96

    def __init__(
        self,
        config: dict,
        on_test_reply: Optional[Callable[[], None]] = None,
        on_set_room: Optional[Callable[[int], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
        on_open_settings: Optional[Callable[[], None]] = None,
    ):
        super().__init__(None)
        self._cfg = config.get("pet", {}) or {}
        self._room_id = int(config.get("room_id", 0) or 0)
        self._on_test_reply = on_test_reply
        self._on_set_room = on_set_room
        self._on_quit = on_quit
        self._on_open_settings = on_open_settings

        self._gif_path = self._cfg.get("gif") or ""
        self._talk_gif_path = self._cfg.get("talk_gif") or ""
        self._renderer = SpriteRenderer(self._gif_path, self._talk_gif_path)
        self._talking = False
        self._drag_offset: Optional[QPoint] = None
        self._bubble = SpeechBubble(self)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        size = int(self._cfg.get("size", 220))
        self.setFixedSize(size, size + self.BUBBLE_ZONE)

        # 动画帧定时器（内置猫用；GIF 模式由 QMovie 驱动）
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self.update)
        self._anim_timer.start(66)  # ~15fps

        if self._renderer.is_gif:
            self._renderer.frame_changed(self)

        self._build_menu()
        self._pos = self._cfg.get("position", {"x": None, "y": None})
        self._move_to_default()

    # ---------- 窗口行为 ----------

    def _move_to_default(self) -> None:
        x, y = self._pos.get("x"), self._pos.get("y")
        if x is None or y is None:
            screen = self.screen()
            avail = screen.availableGeometry() if screen else None
            if avail is None:
                self.move(100, 100)
                return
            x = avail.right() - self.width() - 40
            y = avail.bottom() - self.height() - 80
        self.move(x, y)

    def show_bubble(self, text: str, seconds: float = 6.0) -> None:
        self._bubble.show_text(text, seconds)
        self._layout_bubble()

    def set_talking(self, talking: bool) -> None:
        self._talking = talking
        if talking:
            self._renderer.start_talk()
        else:
            self._renderer.stop_talk()

    def on_reply(self, payload) -> None:
        """收到 AI 回复（GUI 线程）：显示气泡并切到说话动画。"""
        _event, text = payload
        self.show_bubble(text)
        self.set_talking(True)
        QTimer.singleShot(2600, lambda: self.set_talking(False))

    def _layout_bubble(self) -> None:
        """把气泡放在顶部气泡区内。"""
        if self._bubble.isHidden():
            return
        self._bubble.adjustSize()
        bw, bh = self._bubble.width(), self._bubble.height()
        bx = (self.width() - bw) // 2
        by = max(2, self.BUBBLE_ZONE - bh - 4)
        self._bubble.move(bx, by)

    # ---------- 绘制 ----------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        # 桌宠画在气泡区下方
        rect = self.rect().adjusted(
            4, self.BUBBLE_ZONE + 4, -4, -4
        )
        self._renderer.draw(painter, rect, self._talking, int(time.monotonic() * 1000))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._layout_bubble()

    # ---------- 拖动 ----------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        self._menu.exec(event.globalPos())

    # ---------- 菜单 ----------

    def _build_menu(self) -> None:
        self._menu = QMenu(self)

        test_action = QAction("🐾 测试回复一句", self)
        test_action.triggered.connect(self._on_test_reply or (lambda: None))
        self._menu.addAction(test_action)

        room_action = QAction("🎯 设置直播间号…", self)
        room_action.triggered.connect(self._ask_room)
        self._menu.addAction(room_action)

        settings_action = QAction("⚙️ 设置（房间/AI/提示词）…", self)
        settings_action.triggered.connect(self._on_open_settings or (lambda: None))
        self._menu.addAction(settings_action)

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._on_quit or self.close)
        self._menu.addAction(quit_action)

    def _ask_room(self) -> None:
        """弹输入框让用户填房间号，交给控制器热切换。"""
        from PySide6.QtWidgets import QInputDialog

        number, ok = QInputDialog.getInt(
            self, "设置直播间号",
            "输入直播间房间号（直播间网址 live.bilibili.com/ 后面的数字）：",
            self._room_id or 27130187, 1, 999999999,
        )
        if ok and self._on_set_room:
            self._room_id = number
            self._on_set_room(number)
