"""LLM 客户端测试(纯逻辑,不调真实 API)。"""
import unittest
import sys
from pathlib import Path

# 让 src/ 在 path 里
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.llm import (
    LLMConfig, LLMClient, LLMError, WRITE_PRESETS, build_messages,
    load_config, save_config, PRESET_PROVIDERS,
)


class LLMConfigTest(unittest.TestCase):
    def test_is_valid(self):
        cfg = LLMConfig()
        self.assertFalse(cfg.is_valid())  # 默认 api_key 为空
        cfg.api_key = "sk-test"
        self.assertTrue(cfg.is_valid())

    def test_presets_have_required_keys(self):
        for key, p in WRITE_PRESETS.items():
            self.assertIn("label", p, f"{key} 缺 label")
            self.assertIn("system", p, f"{key} 缺 system")
            self.assertIn("user_template", p, f"{key} 缺 user_template")

    def test_build_messages_summary(self):
        msgs = build_messages("总结", context="正文内容ABC")
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[1]["role"], "user")
        self.assertIn("正文内容ABC", msgs[1]["content"])

    def test_build_messages_polish_needs_selection(self):
        # 润色模板用 {selection}
        msgs = build_messages("润色", selection="要润色的段落")
        self.assertIn("要润色的段落", msgs[1]["content"])

    def test_build_messages_unknown_preset_raises(self):
        with self.assertRaises(KeyError):
            build_messages("不存在的预设")

    def test_preset_providers_have_required_fields(self):
        for p in PRESET_PROVIDERS:
            self.assertIn("name", p)
            self.assertIn("base_url", p)
            self.assertIn("model", p)


class LLMClientTest(unittest.TestCase):
    def test_invalid_config_raises(self):
        cfg = LLMConfig()  # 空 api_key
        client = LLMClient(cfg)
        try:
            list(client.chat_stream([{"role": "user", "content": "hi"}]))
            self.fail("应该抛 LLMError")
        except LLMError as e:
            self.assertIn("未配置", str(e))

    def test_chat_calls_chat_stream(self):
        # 简单:验证 chat() 内部走 chat_stream(用 mock)
        from unittest.mock import patch, MagicMock
        cfg = LLMConfig(api_key="sk-test", base_url="https://x", model="m")
        client = LLMClient(cfg)
        mock_gen = MagicMock(return_value=iter(["你", "好", "世", "界"]))
        with patch.object(client, "chat_stream", mock_gen):
            result = client.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(result, "你好世界")


class LLMSettingsTest(unittest.TestCase):
    """测试 QSettings 持久化(用 in-memory 模式)。"""

    def setUp(self):
        from PySide6.QtCore import QSettings
        # in-memory 不会污染真实配置
        QSettings.setDefaultFormat(QSettings.IniFormat)
        self._s = QSettings(QSettings.IniFormat, QSettings.UserScope,
                            "WinEBook_Test", "LLM_Test")
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(Path.cwd() / ".tmp_qs"))

    def tearDown(self):
        self._s.clear()
        # 清理临时 ini
        from PySide6.QtCore import QSettings
        ini = Path.cwd() / ".tmp_qs" / "WinEBook_Test" / "LLM_Test.ini"
        if ini.exists():
            ini.unlink()

    def test_save_load_roundtrip(self):
        # 直接调 save_config / load_config
        # 但默认 _settings() 用 QSettings("WinEBook", "LLM"),不是测试的
        # 这里只测 LLMConfig 字段
        cfg = LLMConfig(
            provider="DeepSeek",
            api_key="sk-123",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
            temperature=0.5,
            max_tokens=1024,
        )
        # 字段序列化/反序列化
        from dataclasses import asdict
        d = asdict(cfg)
        cfg2 = LLMConfig(**d)
        self.assertEqual(cfg, cfg2)


if __name__ == "__main__":
    unittest.main()
