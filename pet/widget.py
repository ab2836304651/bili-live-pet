"""桌宠主窗口：透明无边框置顶、可拖动、气泡对话、右键菜单。

气泡样式（QSS）与托盘菜单都可在下面按需调整。
"""
from __future__ import annotations

import math
import random
import time
from typing import Callable, Optional

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QLabel, QMenu, QWidget

from pet.sprite import SpriteRenderer

# 互动文案池
_CUTE_LINES = [  # 被戳/双击
    "呜哇！戳我干嘛～",
    "嘿嘿，好痒呀！",
    "不许挠我耳朵！",
    "啾？干嘛盯着我看",
    "软乎乎～没错就是本兔！",
    "再戳要生气了哦！",
    "耳朵都被你戳立起来了！",
    "嘿嘿嘿～",
]
_PET_LINES = [  # 摸摸头
    "唔…好舒服～",
    "再摸摸嘛，再摸摸嘛！",
    "嘿嘿，被摸头会变聪明！",
    "呼噜呼噜～",
    "摸头的人运气都不会差！",
    "舒服到想睡觉…不行，还要陪主人！",
]
_IDLE_LINES = [  # 空闲随机
    "好无聊呀…主播什么时候开播～",
    "没人陪，我自己蹦一蹦！",
    "今天也是元气满满的一天！",
    "咕噜噜～",
    "要不要来戳戳我试试？",
    "等一个夸我可爱的人！",
]


class SpeechBubble(QLabel):
    """带小尾巴的圆角气泡。"""

    def __init__(self, parent: Optional[QWidget] = None, font_size: int = 14):
        super().__init__(parent)
        self._tail = True
        self._font_size = font_size
        self._apply_style()
        self.setWordWrap(True)
        self.setMaximumWidth(240)
        self.hide()

    def set_font_size(self, size: int) -> None:
        """热更新气泡字体大小（设置面板保存后调用）。"""
        self._font_size = size
        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            f"""
            QLabel {{
                background: rgba(255, 255, 255, 235);
                color: #4A3B2A;
                border: 2px solid #E8A96E;
                border-radius: 12px;
                padding: 8px 12px;
                font-size: {self._font_size}px;
            }}
            """
        )

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
        self._face_scale = float(self._cfg.get("face_scale") or 1.0)
        self._excited = 0.0  # 兴奋度 0~1（被戳/摸头时脸红竖耳，随时间消退）
        self._drag_offset: Optional[QPoint] = None
        self._press_pos: Optional[QPoint] = None
        self._last_click_at: Optional[float] = None
        self._base_pos = QPoint()
        self._bounce_t = 0.0
        self._bounce_duration = 0.9
        self._bounce_height = 62.0
        self._bubble = SpeechBubble(self, font_size=int(self._cfg.get("bubble_font_size") or 14))

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
        self._anim_timer.timeout.connect(self._tick_anim)
        self._anim_timer.start(66)  # ~15fps

        # 蹦跳动画定时器（只在互动时运行）
        self._bounce_timer = QTimer(self)
        self._bounce_timer.timeout.connect(self._tick_bounce)
        self._bounce_timer.setInterval(16)

        # 空闲随机小动作（每 20~40s 一次）
        self._idle_timer = QTimer(self)
        self._idle_timer.timeout.connect(self._idle_action)
        self._rearm_idle()

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

    def apply_appearance(self, pet_cfg: dict) -> None:
        """设置面板保存后热应用外观：兔团子大小 + 气泡字体大小 + 脸大小。"""
        self._cfg = pet_cfg or {}
        size = int(self._cfg.get("size", 220))
        self.setFixedSize(size, size + self.BUBBLE_ZONE)
        self._bubble.set_font_size(int(self._cfg.get("bubble_font_size") or 14))
        self._face_scale = float(self._cfg.get("face_scale") or 1.0)
        self._layout_bubble()

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
        self._renderer.draw(
            painter, rect, self._talking,
            int(time.monotonic() * 1000),
            self._face_scale, self._excited,
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._layout_bubble()

    # ---------- 拖动 ----------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            self._drag_offset = self._press_pos - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            # 按下→松开移动不超过 5px 视为点击（否则是拖动，不触发互动）
            moved = (event.globalPosition().toPoint() - self._press_pos).manhattanLength()
            if moved <= 5:
                now = time.monotonic()
                is_double = self._last_click_at is not None and now - self._last_click_at < 0.35
                self._last_click_at = None if is_double else now
                self._on_click(is_double)
        self._drag_offset = None

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        self._menu.exec(event.globalPos())

    # ---------- 菜单 ----------

    def _build_menu(self) -> None:
        self._menu = QMenu(self)

        test_action = QAction("🐾 测试回复一句", self)
        test_action.triggered.connect(self._on_test_reply or (lambda: None))
        self._menu.addAction(test_action)

        pet_action = QAction("🤚 摸摸头", self)
        pet_action.triggered.connect(self._pet_head)
        self._menu.addAction(pet_action)

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

    # ---------- 桌宠互动 ----------

    def _tick_anim(self) -> None:
        """每帧：脸红消退 + 触发重绘（蹦跳期间保持脸红）。"""
        if not self._bounce_timer.isActive() and self._excited > 0:
            self._excited = max(0.0, self._excited - 0.045)
        self.update()

    def _on_click(self, is_double: bool) -> None:
        """单击=戳一下；双击=蹦跳 + 卖萌气泡。"""
        if is_double:
            self.start_bounce()
            self._excited = 1.0
            self.show_bubble(random.choice(_CUTE_LINES), 4.0)
        else:
            self._excited = max(self._excited, 0.5)
            if random.random() < 0.35:
                self.show_bubble(random.choice(_CUTE_LINES), 3.5)

    def _pet_head(self) -> None:
        """右键「摸摸头」：脸红竖耳 + 轻蹦 + 撒娇气泡。"""
        self._excited = 1.0
        self.start_bounce(small=True)
        self.show_bubble(random.choice(_PET_LINES), 4.0)

    def start_bounce(self, small: bool = False) -> None:
        """从当前位置开始蹦跳动画（窗口整体做垂直正弦跳跃）。"""
        self._base_pos = self.pos()
        self._bounce_t = 0.0
        self._bounce_duration = 0.7 if small else 0.9
        self._bounce_height = 30.0 if small else 62.0
        self._excited = max(self._excited, 0.8 if small else 1.0)
        self._bounce_timer.start()

    def _tick_bounce(self) -> None:
        """蹦跳动画帧：主跳（前 60%）+ 落地小弹（后 40%），结束后归位。"""
        self._bounce_t += 0.016
        if self._bounce_t >= self._bounce_duration:
            self._bounce_timer.stop()
            self.move(self._base_pos)
            self.update()
            return
        p = self._bounce_t / self._bounce_duration
        if p < 0.6:
            q = p / 0.6
            h = self._bounce_height * 1.2 * math.sin(q * math.pi)
        else:
            q = (p - 0.6) / 0.4
            h = self._bounce_height * 0.25 * math.sin(q * math.pi)
        self.move(self._base_pos.x(), int(self._base_pos.y() - h))
        self.update()

    def _rearm_idle(self) -> None:
        """重排空闲动作定时器（45~90s 随机，防规律感）。"""
        self._idle_timer.start(random.randint(45_000, 90_000))

    def _idle_action(self) -> None:
        """空闲随机小动作：没人在戳时自己蹦一下或冒个泡。"""
        if not self._bubble.isHidden() or random.random() < 0.5:
            self.start_bounce(small=True)
        else:
            self._excited = max(self._excited, 0.7)
            self.show_bubble(random.choice(_IDLE_LINES), 4.0)
        self._rearm_idle()
