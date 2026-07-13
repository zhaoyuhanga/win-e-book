"""LLM 设置弹窗。

- 选 provider(预置 / 自定义)
- 填 API key / base_url / model / temperature / max_tokens
- 「测试连接」按钮发一个 hello
- 保存到 QSettings
"""
from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, QThread, QObject, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QPushButton, QLabel, QDoubleSpinBox, QSpinBox, QDialogButtonBox, QMessageBox,
)

from src.core.llm import LLMConfig, LLMClient, LLMError, PRESET_PROVIDERS


# ============================================================
# 测试连接 worker
# ============================================================

class _TestWorker(QObject):
    ok = Signal(str)
    fail = Signal(str)

    def __init__(self, cfg: LLMConfig):
        super().__init__()
        self._cfg = cfg

    def run(self):
        try:
            client = LLMClient(self._cfg)
            # 发个 hello,流式
            buf = []
            for delta in client.chat_stream([
                {"role": "user", "content": "你好,请用 5 个字以内回复。"},
            ]):
                buf.append(delta)
                if len("".join(buf)) >= 20:
                    break
            self.ok.emit("".join(buf))
        except LLMError as e:
            self.fail.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.fail.emit(f"未知错误: {e}")


class LLMSettingsDialog(QDialog):
    """LLM 设置弹窗。"""

    def __init__(self, current: LLMConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM 设置  ·  墨写")
        self.setMinimumWidth(520)
        self.setModal(True)

        self._result_cfg: LLMConfig = current

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(14)

        # 标题
        title = QLabel("配置大模型 API")
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #1f2937;")
        root.addWidget(title)

        # 表单
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # provider 下拉
        self.cmb_provider = QComboBox()
        self.cmb_provider.setEditable(True)  # 允许自定义
        for p in PRESET_PROVIDERS:
            self.cmb_provider.addItem(p["name"], p)
        self.cmb_provider.setCurrentText(current.provider)
        self.cmb_provider.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("Provider:", self.cmb_provider)

        # API key
        self.ed_key = QLineEdit(current.api_key)
        self.ed_key.setEchoMode(QLineEdit.Password)
        self.ed_key.setPlaceholderText("sk-...")
        form.addRow("API Key:", self.ed_key)

        # base url
        self.ed_base = QLineEdit(current.base_url)
        self.ed_base.setPlaceholderText("https://api.example.com/v1")
        form.addRow("Base URL:", self.ed_base)

        # model
        self.ed_model = QLineEdit(current.model)
        self.ed_model.setPlaceholderText("deepseek-chat")
        form.addRow("Model:", self.ed_model)

        # temperature
        self.sp_temp = QDoubleSpinBox()
        self.sp_temp.setRange(0.0, 2.0)
        self.sp_temp.setSingleStep(0.1)
        self.sp_temp.setValue(current.temperature)
        form.addRow("Temperature:", self.sp_temp)

        # max tokens
        self.sp_max = QSpinBox()
        self.sp_max.setRange(64, 32000)
        self.sp_max.setSingleStep(256)
        self.sp_max.setValue(current.max_tokens)
        form.addRow("Max Tokens:", self.sp_max)

        root.addLayout(form)

        # 测试按钮
        test_row = QHBoxLayout()
        self.btn_test = QPushButton("🔌 测试连接")
        self.btn_test.setCursor(Qt.PointingHandCursor)
        self.btn_test.clicked.connect(self._on_test)
        test_row.addWidget(self.btn_test)
        test_row.addStretch(1)
        self.lbl_test = QLabel("")
        self.lbl_test.setStyleSheet("color: #6b7280; font-size: 12px;")
        test_row.addWidget(self.lbl_test, 1)
        root.addLayout(test_row)

        root.addStretch(1)

        # 按钮
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText("保存")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(self._on_save)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

        # 初始化:按 provider 触发
        if current.provider:
            idx = self.cmb_provider.findText(current.provider)
            if idx < 0:
                # 自定义 provider
                self.cmb_provider.setCurrentText(current.provider)
            else:
                self.cmb_provider.setCurrentIndex(idx)

    def _on_provider_changed(self, idx: int):
        data = self.cmb_provider.itemData(idx)
        if isinstance(data, dict):
            self.ed_base.setText(data.get("base_url", ""))
            self.ed_model.setText(data.get("model", ""))

    def _on_test(self):
        cfg = self._collect()
        if not cfg.is_valid():
            self.lbl_test.setText("❌ 请先填完必填项")
            return
        self.lbl_test.setText("测试中…")
        self.btn_test.setEnabled(False)
        # 后台跑
        self._test_thread = QThread(self)
        self._test_worker = _TestWorker(cfg)
        self._test_worker.moveToThread(self._test_thread)
        self._test_thread.started.connect(self._test_worker.run)
        self._test_worker.ok.connect(self._on_test_ok)
        self._test_worker.fail.connect(self._on_test_fail)
        self._test_worker.ok.connect(self._test_thread.quit)
        self._test_worker.fail.connect(self._test_thread.quit)
        self._test_thread.finished.connect(self._test_thread.deleteLater)
        self._test_thread.start()

    def _on_test_ok(self, msg: str):
        self.btn_test.setEnabled(True)
        self.lbl_test.setText(f"✅ 连接成功 · 模型回复: {msg[:60]!r}")

    def _on_test_fail(self, err: str):
        self.btn_test.setEnabled(True)
        self.lbl_test.setText(f"❌ {err[:200]}")

    def _collect(self) -> LLMConfig:
        return LLMConfig(
            provider=self.cmb_provider.currentText().strip() or "Custom",
            api_key=self.ed_key.text().strip(),
            base_url=self.ed_base.text().strip(),
            model=self.ed_model.text().strip(),
            temperature=float(self.sp_temp.value()),
            max_tokens=int(self.sp_max.value()),
        )

    def _on_save(self):
        cfg = self._collect()
        if not cfg.is_valid():
            QMessageBox.warning(self, "配置不完整", "API Key / Base URL / Model 都不能为空。")
            return
        self._result_cfg = cfg
        self.accept()

    def get_config(self) -> LLMConfig:
        return self._result_cfg
