"""AI 回复策略：决定回不回、怎么回、回什么。

提示词（persona）由用户编辑 config/prompt.md；
回复风格在 config.yaml 的 ai 段配置（称呼、语气、回复模式、冷却等）。
"""
from __future__ import annotations

import random
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

from ai.client import ChatClient
from core.events import LiveEvent, LiveEventType
from core.log import log as safe_log


class Responder:
    """把直播间事件转成 AI 对话并取回回复。"""

    # 进场欢迎语模板（即时欢迎不耗 AI 额度；随机挑选 + 不重复上句）
    _ENTER_TEMPLATES = [
        "欢迎{name}主人光临~ 团子在这里等你好久了！",
        "{name}来啦！团子竖起耳朵欢迎你~",
        "欢迎欢迎{name}！这里是软乎乎的兔团子直播间~",
        "{name}主人进来啦，团子跳起来迎接你！",
        "呀，{name}来了！团子耳朵都竖起来了~",
        "{name}快请进~ 兔团子的窝一直给你留着呢",
        "咕噜噜~ {name}来啦，团子好开心！",
        "欢迎{name}！先坐，团子给你蹦一个~",
    ]

    def __init__(
        self,
        ai_cfg: dict,
        prompt_text: str,
        logger: Optional[Callable[[str], None]] = None,
    ):
        self._cfg = ai_cfg or {}
        self._log = logger or safe_log
        self._prompt = prompt_text.strip()
        self._client = ChatClient(
            api_key=self._cfg.get("api_key", ""),
            base_url=self._cfg.get("base_url", "https://api.deepseek.com"),
            model=self._cfg.get("model", "deepseek-v4-flash"),
        )
        self._mode = self._cfg.get("reply_mode", "all")          # all/trigger/probability
        self._triggers = [w.lower() for w in self._cfg.get("trigger_words", [])]
        self._probability = float(self._cfg.get("reply_probability", 0.3))
        self._cooldown = float(self._cfg.get("cooldown_seconds", 8))
        self._temperature = float(self._cfg.get("temperature", 0.9))
        self._max_tokens = int(self._cfg.get("max_tokens", 120))
        self._last_reply_at = 0.0
        self._lock = threading.Lock()
        # 按事件类型分冷却槽：礼物/SC/大航海不抢占弹幕的冷却，
        # 否则礼物多时弹幕全被拦（"投喂能回、弹幕回复低"的根因）
        self._last_danmaku_at = 0.0
        self._last_welcome_at = 0.0          # 全局欢迎冷却
        self._welcomed: dict = {}            # {user_id: 上次欢迎时间}，防止同一人反复进出刷屏
        self._enter_cooldown = float(self._cfg.get("enter_cooldown_seconds", 20))

    # ---------- 策略 ----------

    def should_reply(self, event: LiveEvent) -> bool:
        """决定该事件是否触发 AI 回复（含冷却与概率）。"""
        if event.type == LiveEventType.SYSTEM:
            return False
        if event.type == LiveEventType.DANMAKU:
            if not self._cfg.get("reply_to_danmaku", True):
                return False
            if self._mode == "trigger":
                if not any(w in event.content.lower() for w in self._triggers):
                    return False
            elif self._mode == "probability":
                if random.random() > self._probability:
                    return False
        elif event.type == LiveEventType.GIFT:
            if not self._cfg.get("reply_to_gift", True):
                return False
        elif event.type == LiveEventType.SUPER_CHAT:
            if not self._cfg.get("reply_to_super_chat", True):
                return False
        elif event.type == LiveEventType.GUARD:
            if not self._cfg.get("reply_to_guard", True):
                return False
        elif event.type == LiveEventType.ENTER:
            if not self._cfg.get("reply_to_enter", False):
                return False
            # 欢迎走独立冷却：不抢占弹幕回复的冷却槽；同一用户冷却期内不重复欢迎
            now = time.monotonic()
            if now - self._last_welcome_at < self._enter_cooldown:
                return False
            if event.user_id and now - self._welcomed.get(event.user_id, 0.0) < self._enter_cooldown:
                return False
            self._welcomed[event.user_id] = now
            if len(self._welcomed) > 500:  # 防内存无限增长，冷清直播间不会到
                self._welcomed.clear()
            self._last_welcome_at = now
            return True
        elif event.type == LiveEventType.LIKE:
            return False  # 点赞默认不回，避免刷屏

        # 弹幕用独立冷却槽，避免被礼物/SC 抢占；其余事件共用冷却槽
        if event.type == LiveEventType.DANMAKU:
            with self._lock:
                if time.monotonic() - self._last_danmaku_at < self._cooldown:
                    return False
                self._last_danmaku_at = time.monotonic()
        else:
            with self._lock:
                if time.monotonic() - self._last_reply_at < self._cooldown:
                    return False
                self._last_reply_at = time.monotonic()
        return True

    # ---------- 对话构建 ----------

    @staticmethod
    def _event_to_prompt(event: LiveEvent) -> str:
        """把事件转成发给 AI 的"观众行为"描述。"""
        if event.type == LiveEventType.DANMAKU:
            return f"观众「{event.user_name}」发来弹幕说：{event.content}"
        if event.type == LiveEventType.SUPER_CHAT:
            return f"观众「{event.user_name}」发来醒目留言（SC，{event.extra.get('price', '')}元）：{event.content}"
        if event.type == LiveEventType.GIFT:
            return f"观众「{event.user_name}」送出了礼物「{event.extra.get('gift_name', '')}」x{event.extra.get('num', 1)}"
        if event.type == LiveEventType.GUARD:
            return f"观众「{event.user_name}」开通了{event.extra.get('guard_level', '')}！"
        if event.type == LiveEventType.ENTER:
            return f"观众「{event.user_name}」刚进入了直播间，现在没别人在场，热情地欢迎 TA 一句"
        return f"观众「{event.user_name}」发生了{event.type.value}事件"

    def build_messages(self, event: LiveEvent, history: List[dict]) -> List[dict]:
        """组装 messages：system（提示词）+ 最近对话 + 当前事件。"""
        messages = [{"role": "system", "content": self._prompt}]
        messages.extend(history[-int(self._cfg.get("max_history", 6)):])
        messages.append({"role": "user", "content": self._event_to_prompt(event)})
        return messages

    # ---------- 调用 ----------

    def _template_welcome(self, event: LiveEvent) -> str:
        """从模板池随机挑欢迎语，避免与上一句重复。"""
        tpl = random.choice(self._ENTER_TEMPLATES)
        if len(self._ENTER_TEMPLATES) > 1:
            while tpl == getattr(self, "_last_welcome_tpl", None):
                tpl = random.choice(self._ENTER_TEMPLATES)
        self._last_welcome_tpl = tpl
        return tpl.format(name=event.user_name or "主人")

    def reply(self, event: LiveEvent, history: List[dict]) -> Optional[str]:
        """同步调用 AI 生成回复；进场欢迎走模板（秒出、不耗额度）。

        AI 调用失败直接抛异常，由上层（controller）捕获后展示原因，
        避免"静默无气泡"让用户以为没反应。
        """
        if event.type == LiveEventType.ENTER:
            return self._template_welcome(event)
        messages = self.build_messages(event, history)
        text = self._client.chat(messages, self._temperature, self._max_tokens)
        with self._lock:
            self._last_reply_at = time.monotonic()
        return text
