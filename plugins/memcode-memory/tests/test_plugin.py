import importlib.util
import json
import pathlib
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]


def _install_plugin_api_stub():
    if "plugins.api" in sys.modules:
        return
    plugins_module = types.ModuleType("plugins")
    api_module = types.ModuleType("plugins.api")

    class PluginTool:
        def __init__(self, plugin_api):
            self.plugin_api = plugin_api

        @property
        def destructive_tool_names(self):
            return set()

    api_module.PluginTool = PluginTool
    plugins_module.api = api_module
    sys.modules["plugins"] = plugins_module
    sys.modules["plugins.api"] = api_module


def _load_module():
    _install_plugin_api_stub()
    spec = importlib.util.spec_from_file_location(
        "memcode_memory_plugin_main", PLUGIN_DIR / "plugin_main.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _api(secret="test-secret", base_url="https://memory.memcode.in"):
    api = MagicMock()
    api.get_secret.return_value = secret
    api.get_config.side_effect = lambda key, default=None: {
        "base_url": base_url,
        "default_count": 5,
    }.get(key, default)
    return api


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((PLUGIN_DIR / "plugin.json").read_text())

    def test_manifest_declares_minimal_permissions(self):
        self.assertEqual(sorted(self.manifest["permissions"]), ["account", "network"])
        self.assertEqual(self.manifest["auth"]["account"]["secret"], "api_key")

    def test_manifest_lists_all_tools(self):
        ids = {item["id"] for item in self.manifest["provides"]["native_tools"]}
        self.assertEqual(
            ids,
            {
                "memcode_search",
                "memcode_retrieve",
                "memcode_list",
                "memcode_remember",
                "memcode_ingest_status",
            },
        )


class TestRegistrationAndApproval(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_registers_five_tools(self):
        api = _api()
        self.module.register(api)
        self.assertEqual(api.register_tool.call_count, 5)

    def test_memory_mutations_require_approval(self):
        api = _api()
        self.assertEqual(
            self.module.MemcodeRememberTool(api).destructive_tool_names,
            {"memcode_remember"},
        )
        self.assertEqual(
            self.module.MemcodeRetrieveTool(api).destructive_tool_names,
            {"memcode_retrieve"},
        )
        for cls in (
            self.module.MemcodeSearchTool,
            self.module.MemcodeListTool,
            self.module.MemcodeIngestStatusTool,
        ):
            self.assertEqual(cls(api).destructive_tool_names, set())

    @patch("urllib.request.urlopen")
    def test_missing_secret_never_calls_network(self, urlopen):
        result = self.module.MemcodeSearchTool(_api(secret="")).execute("release")
        self.assertIn("not configured", result)
        urlopen.assert_not_called()


class TestRequests(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    @patch("urllib.request.urlopen")
    def test_search_uses_personal_v2_route_without_user_id(self, urlopen):
        urlopen.return_value = _Response(
            {"status": "ok", "data": {"memory_results": [{"domain": "profile", "content": "Prefers concise updates", "score": 0.9}]}}
        )
        result = self.module.MemcodeSearchTool(_api()).execute("communication style count=3")
        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, "https://memory.memcode.in/v2/memory/search")
        self.assertEqual(body["query"], "communication style")
        self.assertEqual(body["top_k"], 3)
        self.assertNotIn("user_id", body)
        self.assertIn("Prefers concise updates", result)

    @patch("urllib.request.urlopen")
    def test_search_preserves_numeric_query_suffix(self, urlopen):
        urlopen.return_value = _Response({"status": "ok", "data": {"memory_results": []}})
        self.module.MemcodeSearchTool(_api()).execute("budget 2026")
        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body["query"], "budget 2026")
        self.assertEqual(body["top_k"], 5)

    @patch("urllib.request.urlopen")
    def test_remember_returns_receipt_and_sends_exact_text(self, urlopen):
        urlopen.return_value = _Response(
            {"status": "ok", "data": {"job_id": "job-123", "status": "queued"}}
        )
        result = self.module.MemcodeRememberTool(_api()).execute("Use short release notes")
        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body["user_query"], "Use short release notes")
        self.assertNotIn("user_id", body)
        self.assertIn("job-123", result)

    @patch("urllib.request.urlopen")
    def test_token_is_bearer_header_but_not_output(self, urlopen):
        urlopen.return_value = _Response({"status": "ok", "data": {"items": []}})
        result = self.module.MemcodeListTool(_api(secret="very-secret")).execute("5 0")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer very-secret")
        self.assertNotIn("very-secret", result)


if __name__ == "__main__":
    unittest.main()
