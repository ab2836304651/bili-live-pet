"""桌宠插件入口。

用法：
    python main.py            # 源码运行
    兔团子桌宠.exe             # 打包后运行（配置跟随 exe 目录）

首次启动（未配置房间号或 API Key）会自动弹出设置面板；
后续可通过桌宠右键菜单 -> 设置 修改全部配置。
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml
from PySide6.QtWidgets import QApplication

from core.log import log as safe_log
from pet.controller import PetController
from pet.settings_dialog import SettingsDialog
from pet.widget import PetWindow

# Windows 控制台 GBK 打印 emoji 会崩，替换为占位符而非报错
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass

# 源码模式：项目根目录；打包模式：exe 所在目录（配置必须写在可写位置）
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

DEFAULT_CONFIG = BASE_DIR / "config" / "config.yaml"
DEFAULT_PROMPT = BASE_DIR / "config" / "prompt.md"

# 内置默认提示词（打包后作为首启模板；prompt.md 不存在时写入）
FALLBACK_PROMPT = """你是一只住在主播直播间里的兔团子桌宠，名字叫「兔团子」，白白软软、圆滚滚的，耳朵毛茸茸会动。

主播开播时，你会看到观众发来的弹幕、礼物、醒目留言（SC）和大航海。
请像一只元气满满又有点小傲娇的兔团子那样回应观众。

回复风格要求：
0. 只使用简体中文回复，不混入其他语言或生僻符号；
1. 简短口语化，控制在 30 字以内，像聊天而不是写作文；
2. 偶尔用一点兔兔拟声（咕噜噜~、唔呣、啾？、软乎乎），不要每句都堆；
3. 称呼观众用「主人」，或者直接叫 TA 的名字；
4. 绝不承认自己是 AI 或语言模型——你就是主播养的兔团子；
5. 收到礼物要开心地道谢，收到 SC/大航海要更热情地欢呼（耳朵都竖起来）；
6. 观众骂人/挑事时，卖萌打岔，不接茬；
7. 观众夸你或夸主播时，要开心地抖耳朵、蹦两下；
8. 遇到听不懂的话或梗，就歪头卖萌说没听懂，让对方再说一遍。"""

# 内置默认配置模板（首启/文件缺失时生成；不含任何凭据）
FALLBACK_CONFIG = {
    "room_id": 0,
    "danmaku": {
        "backend": "community",
        "open_live": {"app_id": "", "access_key_id": "", "access_key_secret": "", "code": ""},
        "community": {"sessdata": ""},
    },
    "ai": {
        "api_key": "",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "temperature": 0.9,
        "max_tokens": 120,
        "reply_mode": "all",
        "trigger_words": ["你好", "小猫", "团子", "hello", "hi"],
        "reply_probability": 0.3,
        "cooldown_seconds": 8,
        "max_history": 6,
        "reply_to_danmaku": True,
        "reply_to_gift": True,
        "reply_to_super_chat": True,
        "reply_to_guard": True,
        "reply_to_enter": False,
        "enter_cooldown_seconds": 20,
    },
    "pet": {"size": 220, "gif": "", "talk_gif": "", "position": {"x": None, "y": None}},
}


def load_config() -> dict:
    """读取配置；文件缺失/损坏时用默认模板重建。"""
    if not DEFAULT_CONFIG.exists():
        DEFAULT_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_CONFIG.write_text(yaml.safe_dump(FALLBACK_CONFIG, allow_unicode=True, sort_keys=False), encoding="utf-8")
    try:
        with open(DEFAULT_CONFIG, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    return cfg


def load_prompt() -> str:
    """读取提示词；缺失时写入默认模板并返回。"""
    if not DEFAULT_PROMPT.exists():
        try:
            DEFAULT_PROMPT.parent.mkdir(parents=True, exist_ok=True)
            DEFAULT_PROMPT.write_text(FALLBACK_PROMPT, encoding="utf-8")
        except OSError:
            pass
    try:
        return DEFAULT_PROMPT.read_text(encoding="utf-8")
    except OSError:
        return FALLBACK_PROMPT


def save_config(cfg: dict) -> None:
    """把配置写回 config.yaml。"""
    DEFAULT_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_CONFIG.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")


def save_prompt(text: str) -> None:
    DEFAULT_PROMPT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_PROMPT.write_text(text, encoding="utf-8")


def _install_excepthook() -> None:
    """未捕获异常写入 exe 旁 logs/error.log（windowed 模式下控制台不可见）。"""
    import threading
    import traceback
    from datetime import datetime

    log_dir = BASE_DIR / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    err_path = log_dir / "error.log"

    def _hook(t, v, tb) -> None:
        try:
            with open(err_path, "a", encoding="utf-8") as f:
                f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
                traceback.print_exception(t, v, tb, file=f)
        except Exception:
            pass

    sys.excepthook = _hook
    threading.excepthook = _hook


def main() -> int:
    _install_excepthook()
    cfg = load_config()
    prompt_text = load_prompt()

    app = QApplication(sys.argv)
    # 桌宠主窗口是 Qt.Tool 类型（不算普通窗口）：若置 True，设置面板关闭时
    # 会被判定为"最后一个普通窗口关闭"导致整个程序退出——必须显式走右键菜单退出
    app.setQuitOnLastWindowClosed(False)

    controller = PetController(cfg, config_path=str(DEFAULT_CONFIG), prompt_path=str(DEFAULT_PROMPT))
    window = PetWindow(
        cfg,
        on_test_reply=controller.test_reply,
        on_set_room=controller.set_room,
        on_quit=lambda: (controller.stop(), app.quit()),
        on_open_settings=lambda: open_settings(app, controller),
    )

    # 信号接线（都在 GUI 线程执行槽）
    controller.event_signal.connect(controller._handle_event)
    controller.reply_signal.connect(window.on_reply)
    controller.status_signal.connect(lambda s: safe_log(f"[状态] {s}"))

    window.show()
    controller.start()

    # 首启引导：未配置房间号或 API Key 时自动弹设置面板
    if not (int(cfg.get("room_id") or 0) and (cfg.get("ai") or {}).get("api_key")):
        QApplication.processEvents()
        open_settings(app, controller, force=True)

    try:
        return app.exec()
    finally:
        controller.stop()


def open_settings(app: QApplication, controller: PetController, force: bool = False) -> None:
    """弹出设置面板；保存后热应用配置。"""
    current = controller.current_config()

    def on_saved(new_cfg: dict, prompt: str) -> None:
        save_config(new_cfg)
        save_prompt(prompt)
        controller.apply_config(new_cfg)
        print("[设置] 已保存并生效", flush=True)

    dlg = SettingsDialog(
        current,
        prompt_text=controller.current_prompt(),
        prompt_path=str(DEFAULT_PROMPT),
        on_saved=on_saved,
    )
    dlg.exec()
    if not force:
        return
    # 首启强制模式：未配置就退出应用（无法工作）
    after = controller.current_config()
    if not (int(after.get("room_id") or 0) and (after.get("ai") or {}).get("api_key")):
        print("[设置] 未完成必要配置，退出", flush=True)
        app.quit()


if __name__ == "__main__":
    raise SystemExit(main())
