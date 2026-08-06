"""安全日志：控制台存在才打印（打包为 --windowed 后 sys.stdout 为 None）。"""

from __future__ import annotations


def log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except Exception:
        pass
