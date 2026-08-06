"""按配置创建弹幕监听后端。"""
from __future__ import annotations

from typing import Callable, Optional

from core.events import LiveEvent
from danmaku.base import DanmakuListener
from danmaku.community import CommunityBackend
from danmaku.open_live import OpenLiveBackend


def create_backend(
    config: dict,
    on_event: Callable[[LiveEvent], None],
    logger: Optional[Callable[[str], None]] = None,
) -> DanmakuListener:
    """根据 config['danmaku']['backend'] 创建监听器。"""
    dm = config.get("danmaku") or {}
    room_id = int(config.get("room_id", 0))
    backend = dm.get("backend", "open_live")

    if backend == "open_live":
        return OpenLiveBackend(
            room_id=room_id,
            on_event=on_event,
            logger=logger,
            app_id=dm.get("open_live", {}).get("app_id", ""),
            access_key_id=dm.get("open_live", {}).get("access_key_id", ""),
            access_key_secret=dm.get("open_live", {}).get("access_key_secret", ""),
            code=dm.get("open_live", {}).get("code", ""),
        )
    if backend == "community":
        return CommunityBackend(
            room_id=room_id,
            on_event=on_event,
            logger=logger,
            sessdata=dm.get("community", {}).get("sessdata", ""),
        )
    raise ValueError(f"未知弹幕后端: {backend}（可选: open_live / community）")
