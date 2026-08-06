"""弹幕后端独立测试（不启动桌宠窗口）。

用法：
    python tools/test_danmaku.py --room 123456 --backend open_live --seconds 60
    python tools/test_danmaku.py --room 123456 --backend community --seconds 60

凭据从 config/config.yaml 读取；--room 覆盖配置里的房间号。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Windows 控制台 GBK 打印 emoji 会崩，替换为占位符而非报错
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from core.events import LiveEventType  # noqa: E402
from danmaku.factory import create_backend  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="弹幕后端测试")
    parser.add_argument("--room", type=int, default=None, help="直播间房间号（覆盖配置）")
    parser.add_argument("--backend", choices=["open_live", "community"], default=None)
    parser.add_argument("--seconds", type=int, default=60, help="监听秒数")
    args = parser.parse_args()

    cfg_path = ROOT / "config" / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if args.room:
        cfg["room_id"] = args.room
    if args.backend:
        cfg.setdefault("danmaku", {})["backend"] = args.backend
    if not int(cfg.get("room_id") or 0):
        print("错误：请提供房间号（--room 或 config.yaml 的 room_id）")
        return 1

    print(f"房间 {cfg['room_id']} | 后端 {cfg['danmaku']['backend']} | 监听 {args.seconds}s")
    print("-" * 50)

    def on_event(ev):
        print(ev.summary(), flush=True)

    backend = create_backend(cfg, on_event=on_event, logger=lambda m: print(m, flush=True))
    backend.start()
    try:
        time.sleep(args.seconds)
    except KeyboardInterrupt:
        pass
    finally:
        backend.stop()
    print("-" * 50)
    print("测试结束")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
