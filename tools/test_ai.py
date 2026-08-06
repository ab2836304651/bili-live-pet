"""AI 接口独立测试：验证 config.yaml 里的 Key/模型/提示词是否可用。

用法：
    python tools/test_ai.py
    python tools/test_ai.py "你好呀小猫咪"
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from ai.client import ChatClient  # noqa: E402


def main() -> int:
    cfg_path = ROOT / "config" / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    ai_cfg = cfg.get("ai") or {}

    client = ChatClient(
        api_key=ai_cfg.get("api_key", ""),
        base_url=ai_cfg.get("base_url", "https://api.deepseek.com"),
        model=ai_cfg.get("model", "deepseek-chat"),
    )

    print("1) 连接测试（列出可用模型）…")
    try:
        print("   models:", client.ping())
    except Exception as exc:
        print("   [失败]", exc)
        return 1

    text = sys.argv[1] if len(sys.argv) > 1 else "你好呀，小猫咪！"
    prompt = (ROOT / "config" / "prompt.md").read_text(encoding="utf-8")
    print("2) 对话测试…")
    try:
        reply = client.chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"观众「测试君」发来弹幕说：{text}"},
            ],
            temperature=ai_cfg.get("temperature", 0.9),
            max_tokens=ai_cfg.get("max_tokens", 120),
        )
        print("   回复:", reply)
    except Exception as exc:
        print("   [失败]", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
