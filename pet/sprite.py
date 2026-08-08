"""贴图渲染器：GIF 模式 / 内置矢量兔团子模式。

美术方案说明（按需求原则 3 调研后的取舍）：
- 默认使用内置 Qt 矢量兔团子（pet/builtin_bunny.py，离线可用、无版权问题）；
- 也支持透明 GIF：普通 GIF + 可选"说话 GIF"（回复时切到蹦跳动画），
  可放入 assets/ 目录并配置 pet.gif / pet.talk_gif。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QMovie, QPainter
from PySide6.QtWidgets import QWidget

from pet.builtin_bunny import draw_bunny


class SpriteRenderer:
    """在指定区域渲染桌宠形象。"""

    def __init__(self, gif_path: Optional[str] = None, talk_gif_path: Optional[str] = None):
        self._movie: Optional[QMovie] = None
        self._talk_movie: Optional[QMovie] = None
        if gif_path:
            self._movie = QMovie(gif_path)
            self._movie.setCacheMode(QMovie.CacheAll)
            self._movie.start()
        if talk_gif_path:
            self._talk_movie = QMovie(talk_gif_path)
            self._talk_movie.setCacheMode(QMovie.CacheAll)

    @property
    def is_gif(self) -> bool:
        return self._movie is not None and self._movie.isValid()

    def preferred_size(self) -> QSize:
        if self.is_gif:
            return self._movie.currentPixmap().size()
        return QSize(220, 240)

    def _active_movie(self, talking: bool) -> Optional[QMovie]:
        """说话且有 talk_gif 时切到蹦跳动画；否则用普通 GIF。"""
        if talking and self._talk_movie and self._talk_movie.isValid():
            return self._talk_movie
        return self._movie

    def draw(
        self,
        painter: QPainter,
        rect: QRect,
        talking: bool,
        t_ms: int,
        face_scale: float = 1.0,
        excited: float = 0.0,
    ) -> None:
        movie = self._active_movie(talking)
        if movie is not None:
            pix = movie.currentPixmap()
            if not pix.isNull():
                # 像素风素材用最近邻缩放，避免发糊
                scaled = pix.scaled(
                    rect.size(),
                    aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
                    mode=Qt.TransformationMode.FastTransformation,
                )
                x = rect.x() + (rect.width() - scaled.width()) // 2
                y = rect.y() + (rect.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
            return
        draw_bunny(painter, rect, talking, t_ms, face_scale, excited)

    def frame_changed(self, widget: QWidget) -> None:
        """GIF 模式下任一动画帧变化时通知刷新。"""
        if self.is_gif:
            self._movie.frameChanged.connect(widget.update)
        if self._talk_movie and self._talk_movie.isValid():
            self._talk_movie.frameChanged.connect(widget.update)

    def start_talk(self) -> None:
        """回复开始时切到说话动画（若配置了 talk_gif）。"""
        if self._talk_movie and self._talk_movie.isValid():
            self._talk_movie.jumpToFrame(0)
            self._talk_movie.start()

    def stop_talk(self) -> None:
        if self._talk_movie and self._talk_movie.isValid():
            self._talk_movie.stop()
