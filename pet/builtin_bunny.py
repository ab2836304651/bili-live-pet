"""内置矢量圆耳兔头（纯 Qt 绘制，无外部贴图依赖）。

只画一张圆圆的兔兔大头 + 两只圆耳朵（圆耳短萌风，不画身体）：
- 呼吸（头部轻微起伏）
- 眨眼（约每 3.5s 一次）
- 圆耳朵轻轻摆动 + 每 4s 抖一下
- 说话时嘴巴开合、耳朵微微竖起、腮红加深
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen

# 配色（柔和奶油系）
FUR = QColor("#FFF6EC")           # 奶白绒毛
FUR_SHADOW = QColor("#FFE7D2")    # 浅影/头毛
OUTLINE = QColor("#C6A98C")       # 柔和描边
EAR_INNER = QColor("#F8C8D6")     # 粉嫩耳内
EYE = QColor("#4A3428")           # 圆溜溜的眼睛
NOSE = QColor("#E88FA0")          # 小鼻头
BLUSH = QColor(248, 170, 188, 120)
WHITE = QColor("#FFFFFF")

_W = 220.0
_H = 240.0


def _pen(width: float = 3.0) -> QPen:
    pen = QPen(OUTLINE, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw_round_ear(
    painter: QPainter,
    cx: float, cy: float,
    r: float,
    lift: float = 0.0,
) -> None:
    """画一只圆耳朵：描边 + 绒毛 + 粉色内圆。"""
    cy = cy - lift
    painter.setBrush(QBrush(OUTLINE))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(cx, cy), r + 4, r + 4)
    painter.setBrush(QBrush(FUR))
    painter.drawEllipse(QPointF(cx, cy), r, r)
    painter.setBrush(QBrush(EAR_INNER))
    painter.drawEllipse(QPointF(cx, cy), r * 0.52, r * 0.52)


def draw_bunny(
    painter: QPainter,
    rect: QRect,
    talking: bool,
    t_ms: int,
    face_scale: float = 1.0,
    excited: float = 0.0,
) -> None:
    """在 rect 内绘制当前帧的圆耳兔头。t_ms 为动画时间（毫秒）。

    face_scale: 头缩小比例（0.6~1.0），五官大小不变（Q版大头小脸萌感）；
    excited: 兴奋程度 0~1（被戳/摸头时脸红加深、耳朵竖起）。
    """
    t = t_ms / 1000.0
    face_scale = max(0.5, min(face_scale, 1.0))
    excited = max(0.0, min(excited, 1.0))
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)

    scale = min(rect.width() / _W, rect.height() / _H)
    painter.translate(rect.x() + rect.width() / 2, rect.y() + rect.height() / 2)
    painter.scale(scale, scale)
    painter.translate(-_W / 2, -_H / 2)

    # ---- 动画参数 ----
    breathe = math.sin(t * 2 * math.pi / 1.7) * 1.8          # 呼吸
    ear_bob = math.sin(t * 2 * math.pi / 2.2) * 2.0          # 圆耳轻摆
    if (t % 4.0) < 0.35:                                     # 每 4s 抖一下
        ear_bob += math.sin(t * 2 * math.pi / 0.12) * 4.0
    blink = 0.08 if (t % 3.5) < 0.15 else 1.0                # 眨眼
    mouth_open = (math.sin(t * 2 * math.pi / 0.28) + 1) / 2 if talking else 0.0
    ear_lift = 7.0 if talking else 0.0                       # 说话竖耳
    ear_lift += 6.0 * excited                                # 被戳/摸头时耳朵竖起

    # ---- 头几何（中心固定 110,148；脸缩小则头椭圆变小，五官不变） ----
    hw, hh = 80.0 * face_scale, 78.0 * face_scale           # 头半宽/半高
    head_x, head_y = 110 - hw, 148 - hh + breathe * 0.6

    # ---- 圆耳朵（跟随头沿） ----
    ear_y = head_y - 8                                       # 耳朵在头上沿
    _draw_round_ear(painter, 110 - 38 * face_scale, ear_y + breathe * 0.4, 27, ear_lift + ear_bob)
    _draw_round_ear(painter, 110 + 38 * face_scale, ear_y + breathe * 0.4, 27, ear_lift - ear_bob)

    # ---- 兔头（大圆） ----
    head = QRectF(head_x, head_y, hw * 2, hh * 2)
    painter.setBrush(QBrush(FUR))
    painter.setPen(_pen())
    painter.drawEllipse(head)

    # ---- 眼睛（大眼双高光，大小不变） ----
    eye_y = 128 + breathe * 0.4
    for ex in (85, 135):
        painter.setBrush(QBrush(EYE))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(ex - 16, eye_y - 16 * blink, 32, 32 * blink))
        if blink > 0.5:
            painter.setBrush(QBrush(WHITE))
            painter.drawEllipse(QPointF(ex - 5, eye_y - 5), 5.5, 5.5)
            painter.drawEllipse(QPointF(ex + 6, eye_y + 5), 2.5, 2.5)
    painter.setPen(_pen())

    # ---- 小鼻头（心形，不变） ----
    ny = 152 + breathe * 0.3
    nose = QPainterPath(QPointF(110, ny + 5))
    nose.quadTo(QPointF(103, ny - 4), QPointF(110, ny - 1))
    nose.quadTo(QPointF(117, ny - 4), QPointF(110, ny + 5))
    painter.setBrush(QBrush(NOSE))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPath(nose)
    painter.setPen(_pen(2.5))

    # ---- 三瓣嘴 / 说话张嘴（不变） ----
    my = ny + 6
    if mouth_open > 0.15:
        painter.setBrush(QBrush(QColor("#6E4A3A")))
        painter.drawEllipse(QRectF(101, my, 18, 5 + 10 * mouth_open))
        painter.setPen(Qt.PenStyle.NoPen)
    else:
        mw = QPainterPath(QPointF(100, my))
        mw.quadTo(QPointF(105, my + 5), QPointF(110, my))
        mw.quadTo(QPointF(115, my + 5), QPointF(120, my))
        painter.drawPath(mw)
    painter.setPen(_pen(2.5))

    # ---- 腮红（大小不变，位置跟头沿内收；被戳/摸头时更红更圆） ----
    blush_r = 14 + 3 * mouth_open + 2.5 * excited
    blush_alpha = 120 + 60 * excited
    blush = QColor(248, 170, 188, min(blush_alpha, 220))
    painter.setBrush(QBrush(blush))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(110 - 52 * face_scale, ny + 10), blush_r, blush_r * 0.62)
    painter.drawEllipse(QPointF(110 + 52 * face_scale, ny + 10), blush_r, blush_r * 0.62)

    painter.restore()
