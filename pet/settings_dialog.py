"""设置面板：房间号 / B站登录 / AI 配置 / 回复策略 / 提示词编辑。

收礼方（非开发者）在此完成全部配置，无需碰任何文件。
保存后回调 on_saved(full_cfg)，由控制器热应用并持久化。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pet.qrcode_login import QrLoginDialog


class SettingsDialog(QDialog):
    """桌宠设置面板。构造后调用 run() 显示，保存时调用 on_saved(cfg)。"""

    def __init__(
        self,
        config: dict,
        prompt_text: str,
        prompt_path: str,
        on_saved: Optional[Callable[[dict, str], None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("桌宠设置")
        self.setMinimumWidth(460)
        self._config = config
        self._prompt_path = Path(prompt_path)
        self._on_saved = on_saved

        tabs = QTabWidget(self)
        tabs.addTab(self._build_live_tab(), "直播间")
        tabs.addTab(self._build_ai_tab(), "AI 回复")
        tabs.addTab(self._build_appearance_tab(), "外观")
        tabs.addTab(self._build_prompt_tab(prompt_text), "提示词")

        btn_save = QPushButton("保存", self)
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("取消", self)
        btn_cancel.clicked.connect(self.reject)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_save)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addLayout(btns)

    # ---------- 直播间 Tab ----------

    def _build_live_tab(self) -> QWidget:
        dm = self._config.get("danmaku", {}) or {}
        community = dm.get("community", {}) or {}
        self._room_edit = QLineEdit(str(self._config.get("room_id") or ""), self)
        self._room_edit.setPlaceholderText("你的直播间网址后面的数字，如 7653781")
        self._sessdata_edit = QLineEdit(community.get("sessdata") or "", self)
        self._sessdata_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._sessdata_edit.setPlaceholderText("手机扫码自动填入（不填收不到弹幕）")

        qr_btn = QPushButton("📱 扫码登录（推荐）", self)
        qr_btn.clicked.connect(self._do_qr_login)

        sess_row = QHBoxLayout()
        sess_row.addWidget(self._sessdata_edit, 1)
        sess_row.addWidget(qr_btn)

        form = QFormLayout()
        form.addRow("直播间房间号", self._room_edit)
        form.addRow("B站登录态", sess_row)
        hint = QLabel("B站已封禁匿名看弹幕，必须登录后才能接收弹幕。\n"
                      "点「扫码登录」用手机 B 站 App 扫码，自动填入。\n"
                      "登录态约 30 天有效，失效后重新扫码即可。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 12px;")

        box = QGroupBox("直播设置", self)
        box.setLayout(form)
        layout = QVBoxLayout()
        layout.addWidget(box)
        layout.addWidget(hint)
        layout.addStretch(1)
        w = QWidget(self)
        w.setLayout(layout)
        return w

    def _do_qr_login(self) -> None:
        dlg = QrLoginDialog(self)
        dlg.exec()
        if dlg.sessdata:
            self._sessdata_edit.setText(dlg.sessdata)

    # ---------- AI Tab ----------

    def _build_ai_tab(self) -> QWidget:
        ai = self._config.get("ai", {}) or {}
        self._api_edit = QLineEdit(ai.get("api_key") or "", self)
        self._api_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_edit.setPlaceholderText("DeepSeek 官方 API Key（sk- 开头）")
        self._base_edit = QLineEdit(ai.get("base_url") or "https://api.deepseek.com", self)
        self._model_edit = QLineEdit(ai.get("model") or "deepseek-chat", self)
        self._model_edit.setPlaceholderText("deepseek-chat / deepseek-v4-flash / deepseek-v4-pro")
        self._mode_combo = QComboBox(self)
        self._mode_combo.addItems(["all", "trigger", "probability"])
        self._mode_combo.setCurrentText(ai.get("reply_mode") or "all")
        self._triggers_edit = QLineEdit(",".join(ai.get("trigger_words") or []), self)
        self._prob_spin = QDoubleSpinBox(self)
        self._prob_spin.setRange(0.0, 1.0)
        self._prob_spin.setSingleStep(0.05)
        self._prob_spin.setValue(float(ai.get("reply_probability") or 0.3))
        self._cooldown_spin = QSpinBox(self)
        self._cooldown_spin.setRange(0, 600)
        self._cooldown_spin.setValue(int(ai.get("cooldown_seconds") or 8))

        self._enter_check = QCheckBox("自动欢迎进直播间的观众（冷清直播间也能热闹）", self)
        self._enter_check.setChecked(bool(ai.get("reply_to_enter", False)))
        self._enter_cooldown_spin = QSpinBox(self)
        self._enter_cooldown_spin.setRange(5, 600)
        self._enter_cooldown_spin.setValue(int(ai.get("enter_cooldown_seconds") or 20))

        self._reply_danmaku = QCheckBox("弹幕", self)
        self._reply_danmaku.setChecked(bool(ai.get("reply_to_danmaku", True)))
        self._reply_gift = QCheckBox("礼物", self)
        self._reply_gift.setChecked(bool(ai.get("reply_to_gift", True)))
        self._reply_sc = QCheckBox("醒目留言 SC", self)
        self._reply_sc.setChecked(bool(ai.get("reply_to_super_chat", True)))
        self._reply_guard = QCheckBox("大航海", self)
        self._reply_guard.setChecked(bool(ai.get("reply_to_guard", True)))

        form = QFormLayout()
        form.addRow("API Key", self._api_edit)
        form.addRow("接口地址", self._base_edit)
        form.addRow("模型", self._model_edit)
        form.addRow("回复模式", self._mode_combo)
        form.addRow("触发词（逗号分隔）", self._triggers_edit)
        form.addRow("回复概率", self._prob_spin)
        form.addRow("回复冷却（秒）", self._cooldown_spin)
        form.addRow("", self._enter_check)
        form.addRow("欢迎冷却（秒）", self._enter_cooldown_spin)

        reply_row = QHBoxLayout()
        reply_row.addWidget(self._reply_danmaku)
        reply_row.addWidget(self._reply_gift)
        reply_row.addWidget(self._reply_sc)
        reply_row.addWidget(self._reply_guard)
        reply_row.addStretch(1)
        form.addRow("回复这些事件", reply_row)

        hint = QLabel("API Key 在 https://platform.deepseek.com 申请（需充值）。\n"
                      "回复模式：all=每条弹幕都回；trigger=只回含触发词的；probability=按概率回。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 12px;")

        box = QGroupBox("AI 配置（DeepSeek）", self)
        box.setLayout(form)
        layout = QVBoxLayout()
        layout.addWidget(box)
        layout.addWidget(hint)
        layout.addStretch(1)
        w = QWidget(self)
        w.setLayout(layout)
        return w

    # ---------- 外观 Tab ----------

    def _build_appearance_tab(self) -> QWidget:
        pet = self._config.get("pet", {}) or {}
        self._size_spin = QSpinBox(self)
        self._size_spin.setRange(80, 400)
        self._size_spin.setValue(int(pet.get("size") or 220))
        self._size_spin.setSuffix(" px")

        self._font_spin = QSpinBox(self)
        self._font_spin.setRange(10, 28)
        self._font_spin.setValue(int(pet.get("bubble_font_size") or 14))
        self._font_spin.setSuffix(" px")

        form = QFormLayout()
        form.addRow("兔团子大小", self._size_spin)
        form.addRow("气泡字体大小", self._font_spin)

        hint = QLabel("兔团子大小：桌宠本体的显示尺寸。\n"
                      "气泡字体大小：回复气泡里文字的大小（文字太大可能被气泡宽度截断）。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 12px;")

        box = QGroupBox("外观设置", self)
        box.setLayout(form)
        layout = QVBoxLayout()
        layout.addWidget(box)
        layout.addWidget(hint)
        layout.addStretch(1)
        w = QWidget(self)
        w.setLayout(layout)
        return w

    # ---------- 提示词 Tab ----------

    def _build_prompt_tab(self, prompt_text: str) -> QWidget:
        self._prompt_edit = QPlainTextEdit(self)
        self._prompt_edit.setPlainText(prompt_text)
        self._prompt_edit.setPlaceholderText("在这里编辑桌宠的人设与回复风格…")
        hint = QLabel("这里定义桌宠的性格、语气、称呼与回复风格，保存后重启生效。")
        hint.setStyleSheet("color: #888; font-size: 12px;")

        layout = QVBoxLayout()
        layout.addWidget(self._prompt_edit, 1)
        layout.addWidget(hint)
        w = QWidget(self)
        w.setLayout(layout)
        return w

    # ---------- 保存 ----------

    def _save(self) -> None:
        try:
            room_id = int(self._room_edit.text().strip())
            if room_id <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "提示", "房间号必须是正整数（直播间网址后面的数字）")
            return
        if not self._api_edit.text().strip():
            QMessageBox.warning(self, "提示", "请填写 API Key（AI 回复需要）")
            return

        new_cfg = dict(self._config)
        new_cfg["room_id"] = room_id
        new_cfg.setdefault("danmaku", {})
        new_cfg["danmaku"].setdefault("community", {})
        new_cfg["danmaku"]["community"]["sessdata"] = self._sessdata_edit.text().strip()

        ai = dict(new_cfg.get("ai", {}) or {})
        ai["api_key"] = self._api_edit.text().strip()
        ai["base_url"] = self._base_edit.text().strip()
        ai["model"] = self._model_edit.text().strip()
        ai["reply_mode"] = self._mode_combo.currentText()
        ai["trigger_words"] = [w.strip() for w in self._triggers_edit.text().split(",") if w.strip()]
        ai["reply_probability"] = self._prob_spin.value()
        ai["cooldown_seconds"] = self._cooldown_spin.value()
        ai["reply_to_enter"] = self._enter_check.isChecked()
        ai["enter_cooldown_seconds"] = self._enter_cooldown_spin.value()
        ai["reply_to_danmaku"] = self._reply_danmaku.isChecked()
        ai["reply_to_gift"] = self._reply_gift.isChecked()
        ai["reply_to_super_chat"] = self._reply_sc.isChecked()
        ai["reply_to_guard"] = self._reply_guard.isChecked()
        new_cfg["ai"] = ai

        pet = dict(new_cfg.get("pet", {}) or {})
        pet["size"] = self._size_spin.value()
        pet["bubble_font_size"] = self._font_spin.value()
        new_cfg["pet"] = pet

        if self._on_saved:
            self._on_saved(new_cfg, self._prompt_edit.toPlainText())
        self.accept()
