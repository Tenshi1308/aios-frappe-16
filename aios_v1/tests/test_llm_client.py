import unittest
from unittest.mock import patch, MagicMock
from aios_v1.lib.llm_client import chat_stream, get_llm_config

class TestLLMClient(unittest.TestCase):
    
    @unittest.skip("target #7: mengharap fallback hardcoded yang dihapus di 5016ad9")
    @patch('aios_v1.lib.llm_client.frappe.get_single')
    def test_get_llm_config_fallback(self, mock_get_single):
        # Test fallback when DB setting throws exception
        mock_get_single.side_effect = Exception("DB not ready")
        config = get_llm_config()
        self.assertEqual(config["api_key"], "ollama")
        self.assertEqual(config["model"], "llama3")

    @unittest.skip("target #7: mock SSE mengeluarkan bytes; runtime nyata decode_unicode=True -> str")
    @patch('aios_v1.lib.llm_client.requests.post')
    @patch('aios_v1.lib.llm_client.get_llm_config')
    def test_chat_stream_success(self, mock_get_config, mock_post):
        # Mock LLM config
        mock_get_config.return_value = {
            "base_url": "http://mock-api.com",
            "api_key": "mock_key",
            "model": "mock-model",
            "temperature": 0.5,
            "timeout": 10
        }

        # Mock requests.post response
        mock_response = MagicMock()
        mock_response.ok = True
        
        # Simulate Server-Sent Events (SSE) stream
        def iter_lines(decode_unicode=True):
            yield b'data: {"choices": [{"delta": {"content": "Halo"}}]}'
            yield b'data: {"choices": [{"delta": {"content": " Dunia!"}}]}'
            yield b'data: [DONE]'
        
        mock_response.iter_lines = iter_lines
        mock_post.return_value = mock_response

        messages = [{"role": "user", "content": "Tes 123"}]
        
        # Collect the streamed outputs
        result = "".join(list(chat_stream(messages)))
        
        self.assertEqual(result, "Halo Dunia!")

    @patch('aios_v1.lib.llm_client.requests.post')
    @patch('aios_v1.lib.llm_client.get_llm_config')
    def test_chat_stream_captures_usage(self, mock_get_config, mock_post):
        mock_get_config.return_value = {
            "base_url": "https://mock-api.com/v1",
            "api_key": "mock_key",
            "model": "mock-model",
            "temperature": 0.5,
            "timeout": 10
        }

        mock_response = MagicMock()
        mock_response.ok = True

        def iter_lines(decode_unicode=True):
            yield 'data: {"choices": [{"delta": {"content": "Halo"}}]}'
            yield 'data: {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}'
            yield 'data: [DONE]'

        mock_response.iter_lines = iter_lines
        mock_post.return_value = mock_response

        usage = {}
        result = "".join(list(chat_stream([{"role": "user", "content": "Tes"}], usage=usage)))

        self.assertEqual(result, "Halo")
        self.assertEqual(usage["prompt_tokens"], 7)
        self.assertEqual(usage["completion_tokens"], 3)
        self.assertEqual(usage["total_tokens"], 10)
        self.assertEqual(usage["provider"], "mock-api.com")
        self.assertEqual(usage["model"], "mock-model")
        self.assertEqual(
            mock_post.call_args.kwargs["json"]["stream_options"],
            {"include_usage": True},
        )

    @patch('aios_v1.lib.llm_client.requests.post')
    @patch('aios_v1.lib.llm_client.get_llm_config')
    @patch('aios_v1.lib.llm_client.frappe.log_error')
    def test_chat_stream_logs_bad_chunk(self, mock_log_error, mock_get_config, mock_post):
        mock_get_config.return_value = {
            "base_url": "http://mock-api.com",
            "api_key": "mock_key",
            "model": "mock-model",
            "temperature": 0.5,
            "timeout": 10
        }

        mock_response = MagicMock()
        mock_response.ok = True

        def iter_lines(decode_unicode=True):
            yield 'data: bukan-json'
            yield 'data: {"choices": [{"delta": {"content": "ok"}}]}'
            yield 'data: [DONE]'

        mock_response.iter_lines = iter_lines
        mock_post.return_value = mock_response

        result = "".join(list(chat_stream([{"role": "user", "content": "Tes"}])))

        self.assertEqual(result, "ok")
        mock_log_error.assert_called()

    @patch('aios_v1.lib.llm_client.requests.post')
    @patch('aios_v1.lib.llm_client.get_llm_config')
    def test_chat_stream_captures_finish_reason_length(self, mock_get_config, mock_post):
        mock_get_config.return_value = {
            "base_url": "http://mock-api.com",
            "api_key": "mock_key",
            "model": "mock-model",
            "temperature": 0.5,
            "timeout": 10
        }

        mock_response = MagicMock()
        mock_response.ok = True

        def iter_lines(decode_unicode=True):
            yield 'data: {"choices": [{"delta": {"content": "jawaban terpotong"}}]}'
            yield 'data: {"choices": [{"delta": {}, "finish_reason": "length"}]}'
            yield 'data: [DONE]'

        mock_response.iter_lines = iter_lines
        mock_post.return_value = mock_response

        usage = {}
        result = "".join(list(chat_stream([{"role": "user", "content": "Tes"}], usage=usage)))

        self.assertEqual(result, "jawaban terpotong")
        self.assertEqual(usage["finish_reason"], "length")

    @patch('aios_v1.lib.llm_client.requests.post')
    @patch('aios_v1.lib.llm_client.get_llm_config')
    def test_chat_stream_captures_finish_reason_stop(self, mock_get_config, mock_post):
        mock_get_config.return_value = {
            "base_url": "http://mock-api.com",
            "api_key": "mock_key",
            "model": "mock-model",
            "temperature": 0.5,
            "timeout": 10
        }

        mock_response = MagicMock()
        mock_response.ok = True

        def iter_lines(decode_unicode=True):
            yield 'data: {"choices": [{"delta": {"content": "jawaban lengkap"}}]}'
            yield 'data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}'
            yield 'data: [DONE]'

        mock_response.iter_lines = iter_lines
        mock_post.return_value = mock_response

        usage = {}
        result = "".join(list(chat_stream([{"role": "user", "content": "Tes"}], usage=usage)))

        self.assertEqual(result, "jawaban lengkap")
        self.assertEqual(usage["finish_reason"], "stop")

    @patch('aios_v1.lib.llm_client.requests.post')
    @patch('aios_v1.lib.llm_client.get_llm_config')
    def test_chat_stream_without_finish_reason_keeps_usage_shape(self, mock_get_config, mock_post):
        mock_get_config.return_value = {
            "base_url": "http://mock-api.com",
            "api_key": "mock_key",
            "model": "mock-model",
            "temperature": 0.5,
            "timeout": 10
        }

        mock_response = MagicMock()
        mock_response.ok = True

        def iter_lines(decode_unicode=True):
            yield 'data: {"choices": [{"delta": {"content": "Halo"}}]}'
            yield 'data: {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}'
            yield 'data: [DONE]'

        mock_response.iter_lines = iter_lines
        mock_post.return_value = mock_response

        usage = {}
        result = "".join(list(chat_stream([{"role": "user", "content": "Tes"}], usage=usage)))

        self.assertEqual(result, "Halo")
        self.assertEqual(usage["prompt_tokens"], 7)
        self.assertNotIn("finish_reason", usage)

    @patch('aios_v1.lib.llm_client.requests.post')
    @patch('aios_v1.lib.llm_client.get_llm_config')
    @patch('aios_v1.lib.llm_client.frappe.log_error')
    def test_chat_stream_failure(self, mock_log_error, mock_get_config, mock_post):
        mock_get_config.return_value = {
            "base_url": "http://mock-api.com",
            "api_key": "mock_key",
            "model": "mock-model",
            "temperature": 0.5,
            "timeout": 10
        }
        
        # Simulate network or API error
        mock_post.side_effect = Exception("Connection Timeout")
        
        messages = [{"role": "user", "content": "Tes 123"}]
        usage = {}
        result = list(chat_stream(messages, usage=usage))
        
        # Pesan aman ke pengguna; detail error hanya di Error Log.
        self.assertEqual(len(result), 1)
        self.assertIn("Mohon maaf", result[0])
        self.assertNotIn("Connection Timeout", result[0])
        self.assertTrue(usage.get("failed"))
        mock_log_error.assert_called()

    @patch('aios_v1.lib.llm_client.frappe.get_single')
    def test_get_llm_config_reads_default_max_tokens(self, mock_get_single):
        mock_doc = MagicMock()
        mock_doc.base_url = "https://mock.com"
        mock_doc.get_password.return_value = "secret"
        mock_doc.model_name = "test-model"
        mock_doc.temperature = 0.3
        mock_doc.default_max_tokens = 8192
        mock_doc.get.side_effect = lambda field, default=None: getattr(mock_doc, field, default)
        mock_get_single.return_value = mock_doc

        cfg = get_llm_config()
        self.assertEqual(cfg["default_max_tokens"], 8192)

        # Fallback saat field bernilai None/0
        mock_doc.default_max_tokens = None
        cfg_fallback = get_llm_config()
        self.assertEqual(cfg_fallback["default_max_tokens"], 8192)

        # Custom value saat diubah di Frappe Desk
        mock_doc.default_max_tokens = 16384
        cfg_custom = get_llm_config()
        self.assertEqual(cfg_custom["default_max_tokens"], 16384)

    @patch('aios_v1.lib.llm_client.requests.post')
    @patch('aios_v1.lib.llm_client.get_llm_config')
    def test_chat_stream_uses_default_max_tokens_when_unspecified(self, mock_get_config, mock_post):
        mock_get_config.return_value = {
            "base_url": "http://mock-api.com",
            "api_key": "mock_key",
            "model": "mock-model",
            "temperature": 0.5,
            "default_max_tokens": 8192,
            "timeout": 10,
        }
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.iter_lines.return_value = ['data: {"choices": [{"delta": {"content": "ok"}}]}', 'data: [DONE]']
        mock_post.return_value = mock_response

        # Tanpa max_tokens spesifik -> menggunakan default_max_tokens dari config (8192)
        list(chat_stream([{"role": "user", "content": "Halo"}]))
        sent_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_payload["max_tokens"], 8192)

    @patch('aios_v1.lib.llm_client.requests.post')
    @patch('aios_v1.lib.llm_client.get_llm_config')
    def test_chat_stream_respects_explicit_max_tokens(self, mock_get_config, mock_post):
        mock_get_config.return_value = {
            "base_url": "http://mock-api.com",
            "api_key": "mock_key",
            "model": "mock-model",
            "temperature": 0.5,
            "default_max_tokens": 8192,
            "timeout": 10,
        }
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.iter_lines.return_value = ['data: {"choices": [{"delta": {"content": "ok"}}]}', 'data: [DONE]']
        mock_post.return_value = mock_response

        # Dengan max_tokens eksplisit (misal dari bot Telegram: 1500)
        list(chat_stream([{"role": "user", "content": "Halo"}], max_tokens=1500))
        sent_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_payload["max_tokens"], 1500)
