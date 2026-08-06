"""扫码登录（Qt 版）：弹窗显示二维码，手机 B 站 App 扫码后返回 SESSDATA。

轮询接口状态以 data.code 为准（实测 2026-08-05）：
    86101 未扫码 / 86090 已扫码待确认 / 0 成功 / 86102 二维码失效
"""
from __future__ import annotations

import time
from typing import Optional

import requests
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
GEN_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
TIMEOUT_SEC = 240


def _poll_status(resp: dict) -> int:
    data = resp.get("data") or {}
    return int(data.get("code", resp.get("code", -1)) if isinstance(data, dict) else resp.get("code", -1))


class QrLoginDialog(QDialog):
    """扫码登录弹窗。登录成功设置 self.sessdata 并自动关闭。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sessdata: Optional[str] = None
        self.setWindowTitle("B站扫码登录")
        self.setModal(True)
        self.setFixedWidth(320)

        self._session = requests.Session()
        self._session.headers.update({"User-Agent": UA, "Referer": "https://www.bilibili.com/"})
        self._start_t = time.time()

        self._qr_label = QLabel(self)
        self._qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label = QLabel("正在获取二维码…", self)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet("color: #555; padding: 4px;")

        layout = QVBoxLayout(self)
        layout.addWidget(self._qr_label)
        layout.addWidget(self._status_label)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(1000)

    def _show_status(self, text: str) -> None:
        self._status_label.setText(text)

    def _start(self) -> None:
        """生成二维码并开始轮询。"""
        try:
            self._session.get("https://www.bilibili.com/", timeout=15)  # 拿 buvid 风控 Cookie
            gen = self._session.get(GEN_URL, timeout=15).json()
        except Exception as exc:
            self._show_status(f"获取二维码失败: {exc}")
            self._timer.stop()
            return
        if gen.get("code") != 0:
            self._show_status(f"获取二维码失败: {gen}")
            self._timer.stop()
            return
        self._qrcode_key = gen["data"]["qrcode_key"]
        url = gen["data"]["url"]
        try:
            import qrcode
            from PIL.ImageQt import ImageQt

            img = qrcode.make(url).resize((260, 260))
            qimg = ImageQt(img)
            self._qr_label.setPixmap(QPixmap.fromImage(QImage(qimg)))
        except Exception:
            self._show_status("二维码图片生成失败")
            self._timer.stop()
            return
        self._show_status("用手机 B 站 App「扫一扫」登录（4 分钟有效）")

    def _poll(self) -> None:
        if time.time() - self._start_t > TIMEOUT_SEC:
            self._show_status("超时未扫码，请关闭重试")
            self._timer.stop()
            return
        if not getattr(self, "_qrcode_key", None):
            self._start()
            return
        try:
            resp = self._session.get(
                POLL_URL,
                params={"qrcode_key": self._qrcode_key, "source": "main-fe-header"},
                timeout=15,
            ).json()
        except Exception:
            return  # 网络抖动，下轮再试
        code = _poll_status(resp)
        if code == 0:
            sess = self._session.cookies.get("SESSDATA")
            if sess:
                self.sessdata = sess
                self._show_status("登录成功！")
                self._timer.stop()
                QTimer.singleShot(600, self.accept)
                return
            self._show_status("登录成功但未拿到 Cookie，请重试")
        elif code == 86090:
            self._show_status("已扫码！请在手机上点「确认登录」")
        elif code == 86102:
            self._show_status("二维码已失效，请关闭重试")
            self._timer.stop()
        else:
            self._show_status("用手机 B 站 App「扫一扫」登录（4 分钟有效）")
