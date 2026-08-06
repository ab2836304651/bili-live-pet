"""弹幕监听器抽象基类。

新增后端时只需继承 DanmakuListener 并实现 connect/stop，
把解析出的 LiveEvent 通过 self._emit() 发出即可。
"""
from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from typing import Callable, Optional

from core.events import LiveEvent
from core.log import log as safe_log


class DanmakuListener(ABC):
    """直播间弹幕监听器接口。"""

    def __init__(
        self,
        room_id: int,
        on_event: Callable[[LiveEvent], None],
        logger: Optional[Callable[[str], None]] = None,
    ):
        self.room_id = room_id
        self._on_event = on_event
        self._log = logger or safe_log
        self._thread: Optional[threading.Thread] = None
        self._running = threading.Event()

    # ---- 子类需实现 ----

    @abstractmethod
    def connect(self) -> None:
        """建立连接并阻塞运行（应在本类内部自行起线程调用）。"""
        raise NotImplementedError

    # ---- 公共 ----

    def start(self) -> None:
        """在后台线程中启动监听，断开后自动重连。"""
        if self._thread and self._thread.is_alive():
            return
        self._running.set()

        def _run() -> None:
            while self._running.is_set():
                t0 = time.monotonic()
                self.connect()  # 阻塞直到断开/失败
                if not self._running.is_set():
                    break
                # 连接刚建立就被掐断（<10秒）说明配置/风控问题，不再重试刷屏
                if time.monotonic() - t0 < 10:
                    self._info("连接在 10 秒内异常退出，停止自动重连")
                    break
                self._info("连接断开，5 秒后自动重连…")
                time.sleep(5)

        self._thread = threading.Thread(target=_run, name=f"danmaku-{self.__class__.__name__}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止监听。"""
        self._running.clear()

    @property
    def running(self) -> bool:
        return self._running.is_set()

    def _emit(self, event: LiveEvent) -> None:
        self._on_event(event)

    def _info(self, msg: str) -> None:
        self._log(f"[{self.__class__.__name__}] {msg}")
