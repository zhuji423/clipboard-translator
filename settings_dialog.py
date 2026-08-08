from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from platform_ui import ui_font
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

from browser_bridge import DEFAULT_BRIDGE_PORT
from config import BridgeSettings, LlmConfig


@dataclass(frozen=True)
class LlmSettingsValues:
    base_url: str
    api_key: str
    model: str


@dataclass(frozen=True)
class BridgeSettingsValues:
    enabled: bool
    port: int


class SettingsDialog(QDialog):
    font_size_changed = Signal(int)
    llm_settings_changed = Signal(object)  # LlmSettingsValues
    bridge_settings_changed = Signal(object)  # BridgeSettingsValues
    check_updates_requested = Signal()
    start_pairing_requested = Signal()
    revoke_pairing_requested = Signal()

    def __init__(
        self,
        font_size: int = 12,
        llm: LlmConfig | None = None,
        bridge: BridgeSettings | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        self.resize(480, 520)

        llm = llm or LlmConfig(base_url="", api_key="", model="")
        bridge = bridge or BridgeSettings()

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("大模型"))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.url_edit = QLineEdit(llm.base_url)
        self.url_edit.setPlaceholderText("https://api.example.com 或 http://127.0.0.1:11434/v1")
        form.addRow("API URL", self.url_edit)

        key_row = QHBoxLayout()
        self.key_edit = QLineEdit(llm.api_key)
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("sk-...")
        self.show_key = QCheckBox("显示")
        self.show_key.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self.key_edit, stretch=1)
        key_row.addWidget(self.show_key)
        form.addRow("API Key", key_row)

        self.model_edit = QLineEdit(llm.model)
        self.model_edit.setPlaceholderText("模型名")
        form.addRow("模型名", self.model_edit)
        layout.addLayout(form)

        layout.addWidget(QLabel("浏览器集成（YouTube 字幕点词）"))
        bridge_form = QFormLayout()
        bridge_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.bridge_enabled = QCheckBox("启用本机桥接（仅 127.0.0.1）")
        self.bridge_enabled.setChecked(bridge.enabled)
        bridge_form.addRow("", self.bridge_enabled)

        self.bridge_port = QSpinBox()
        self.bridge_port.setRange(1024, 65535)
        self.bridge_port.setValue(bridge.port or DEFAULT_BRIDGE_PORT)
        bridge_form.addRow("端口", self.bridge_port)

        paired = "已配对" if bridge.token else "未配对"
        self.bridge_status = QLabel(paired)
        bridge_form.addRow("状态", self.bridge_status)
        layout.addLayout(bridge_form)

        pair_row = QHBoxLayout()
        self.pair_btn = QPushButton("开始配对")
        self.pair_btn.setToolTip("生成一次性短码，在浏览器扩展中输入以连接")
        self.pair_btn.clicked.connect(self.start_pairing_requested.emit)
        self.revoke_btn = QPushButton("撤销配对")
        self.revoke_btn.clicked.connect(self.revoke_pairing_requested.emit)
        pair_row.addWidget(self.pair_btn)
        pair_row.addWidget(self.revoke_btn)
        pair_row.addStretch(1)
        layout.addLayout(pair_row)

        self.pair_code_label = QLabel("")
        self.pair_code_label.setWordWrap(True)
        layout.addWidget(self.pair_code_label)

        layout.addWidget(QLabel("界面字号（主窗口 / 历史）"))

        row = QHBoxLayout()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(10, 22)
        self.slider.setValue(font_size)
        self.spin = QSpinBox()
        self.spin.setRange(10, 22)
        self.spin.setValue(font_size)
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self.slider.setValue)
        self.spin.valueChanged.connect(self._preview_font)
        row.addWidget(self.slider, stretch=1)
        row.addWidget(self.spin)
        layout.addLayout(row)

        self.preview = QLabel("预览：原文 / 译文 Abc 123")
        layout.addWidget(self.preview)

        update_row = QHBoxLayout()
        self.check_update_btn = QPushButton("检查更新")
        self.check_update_btn.setToolTip("从 GitHub 正式版 Release 检查并安装更新")
        self.check_update_btn.clicked.connect(self.check_updates_requested.emit)
        update_row.addWidget(self.check_update_btn)
        update_row.addStretch(1)
        layout.addLayout(update_row)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        ok = QPushButton("确定")
        ok.clicked.connect(self._accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

        self.setStyleSheet(
            """
            QDialog, QWidget { background: #1e1f22; color: #e8eaed; }
            QLabel { color: #c4c7cc; }
            QSpinBox, QSlider, QLineEdit, QCheckBox { color: #e8eaed; }
            QLineEdit {
                background: #2b2d31;
                border: 1px solid #3c4048;
                border-radius: 6px;
                padding: 6px 8px;
                selection-background-color: #3c78d8;
            }
            QPushButton {
                background: #3c78d8;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover { background: #4b86e0; }
            """
        )
        self._preview_font(font_size)

    def set_pair_code(self, code: str, port: int, expires_in: int) -> None:
        self.pair_code_label.setText(
            f"配对码：{code}\n端口：{port}（{expires_in} 秒内有效）\n"
            "请在浏览器扩展弹窗中输入该配对码。"
        )
        self.bridge_status.setText("等待扩展连接…")

    def set_bridge_paired(self, paired: bool) -> None:
        self.bridge_status.setText("已配对" if paired else "未配对")
        if not paired:
            self.pair_code_label.setText("")

    def _toggle_key_visibility(self, checked: bool) -> None:
        mode = (
            QLineEdit.EchoMode.Normal
            if checked
            else QLineEdit.EchoMode.Password
        )
        self.key_edit.setEchoMode(mode)

    def _preview_font(self, size: int) -> None:
        self.preview.setFont(ui_font(size))

    def _accept(self) -> None:
        base_url = self.url_edit.text().strip().rstrip("/")
        api_key = self.key_edit.text().strip()
        model = self.model_edit.text().strip()
        if not base_url or not model:
            QMessageBox.warning(self, "设置", "API URL 与模型名不能为空。")
            return
        self.llm_settings_changed.emit(
            LlmSettingsValues(base_url=base_url, api_key=api_key, model=model)
        )
        self.bridge_settings_changed.emit(
            BridgeSettingsValues(
                enabled=self.bridge_enabled.isChecked(),
                port=self.bridge_port.value(),
            )
        )
        self.font_size_changed.emit(self.spin.value())
        self.accept()

    def current_size(self) -> int:
        return self.spin.value()
