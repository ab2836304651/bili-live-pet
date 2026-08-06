"""直播间事件数据模型。

所有弹幕后端（Open Live / 社区协议）解析后的消息都会统一转换为
LiveEvent 对象再交给上层（AI 回复 / 桌宠展示），
这样更换后端时不需要改动 UI 与 AI 逻辑。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class LiveEventType(Enum):
    """统一事件类型。"""

    DANMAKU = "danmaku"          # 普通弹幕
    SUPER_CHAT = "super_chat"    # 醒目留言（SC）
    GIFT = "gift"                # 礼物
    GUARD = "guard"              # 大航海（舰长/提督/总督）
    LIKE = "like"                # 点赞
    ENTER = "enter"              # 进场
    SYSTEM = "system"            # 连接/系统状态（不触发 AI 回复）


@dataclass
class LiveEvent:
    """一条归一化的直播间事件。"""

    type: LiveEventType
    user_name: str = ""
    user_id: int = 0
    content: str = ""            # 弹幕文本 / SC 内容
    extra: dict = field(default_factory=dict)  # 礼物名、数量等附加信息
    time: datetime = field(default_factory=datetime.now)

    def summary(self) -> str:
        """便于日志输出的简短描述。"""
        if self.type == LiveEventType.DANMAKU:
            return f"[弹幕] {self.user_name}: {self.content}"
        if self.type == LiveEventType.SUPER_CHAT:
            price = self.extra.get("price", "")
            return f"[SC {price}元] {self.user_name}: {self.content}"
        if self.type == LiveEventType.GIFT:
            name = self.extra.get("gift_name", "")
            num = self.extra.get("num", 1)
            return f"[礼物] {self.user_name} 送出 {name} x{num}"
        if self.type == LiveEventType.GUARD:
            return f"[大航海] {self.user_name} 上船（{self.extra.get('guard_level', '')}）"
        if self.type == LiveEventType.LIKE:
            return f"[点赞] {self.user_name} 点赞了直播间"
        if self.type == LiveEventType.ENTER:
            return f"[进场] {self.user_name} 进入了直播间"
        return f"[系统] {self.content}"
