import importlib.util
import json
import pathlib
import sys
import time
import types
import unittest
import urllib.error
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

    class PluginAPI:
        pass

    api_module.PluginTool = PluginTool
    api_module.PluginAPI = PluginAPI
    plugins_module.api = api_module
    sys.modules["plugins"] = plugins_module
    sys.modules["plugins.api"] = api_module


def _load_module():
    _install_plugin_api_stub()
    spec = importlib.util.spec_from_file_location(
        "hacker_news_plugin_main",
        PLUGIN_DIR / "plugin_main.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))

    def test_manifest_v2_shape(self):
        self.assertEqual(self.manifest["schema_version"], 2)
        self.assertEqual(self.manifest["id"], "hacker-news")
        self.assertEqual(self.manifest["min_row_bot_version"], "0.0.0")
        self.assertEqual(self.manifest["permissions"], ["network"])

    def test_provides_tool_and_skill(self):
        provides = self.manifest["provides"]
        self.assertEqual(provides["native_tools"][0]["id"], "hacker_news")
        self.assertEqual(provides["native_tools"][0]["entrypoint"], "plugin_main.py")
        self.assertEqual(provides["skills"][0]["id"], "hacker_news_reader")


class TestRegister(unittest.TestCase):
    def test_register_registers_tool(self):
        module = _load_module()
        api = MagicMock()
        module.register(api)
        api.register_tool.assert_called_once()
        tool = api.register_tool.call_args[0][0]
        self.assertEqual(tool.name, "hacker_news")
        self.assertEqual(tool.display_name, "Hacker News")


class TestQueryParser(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_empty_query_defaults_to_top_stories(self):
        action, params = self.module._parse_query("", 10)
        self.assertEqual(action, "top_stories")
        self.assertEqual(params["count"], 10)

    def test_top_stories_with_count(self):
        action, params = self.module._parse_query("top_stories 5", 10)
        self.assertEqual(action, "top_stories")
        self.assertEqual(params["count"], 5)

    def test_new_stories(self):
        action, params = self.module._parse_query("new_stories", 10)
        self.assertEqual(action, "new_stories")
        self.assertEqual(params["count"], 10)

    def test_search_with_count(self):
        action, params = self.module._parse_query("search rust programming 5", 10)
        self.assertEqual(action, "search")
        self.assertEqual(params["query"], "rust programming")
        self.assertEqual(params["count"], 5)

    def test_story_detail_with_comments(self):
        action, params = self.module._parse_query("story_detail 123 comments:3", 10)
        self.assertEqual(action, "story_detail")
        self.assertEqual(params["story_id"], 123)
        self.assertEqual(params["comment_count"], 3)

    def test_bare_text_treated_as_search(self):
        action, params = self.module._parse_query("what is new in AI", 10)
        self.assertEqual(action, "search")
        self.assertEqual(params["query"], "what is new in AI")

    def test_errors(self):
        self.assertEqual(self.module._parse_query("search", 10)[0], "error")
        self.assertEqual(self.module._parse_query("story_detail", 10)[0], "error")
        self.assertEqual(self.module._parse_query("story_detail nope", 10)[0], "error")

    def test_count_clamping(self):
        self.assertEqual(self.module._parse_query("top_stories 100", 10)[1]["count"], 30)
        self.assertEqual(self.module._parse_query("top_stories 0", 10)[1]["count"], 1)


class TestFormatting(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_format_story_with_url(self):
        item = {
            "title": "Test Story",
            "url": "https://example.com",
            "score": 42,
            "by": "testuser",
            "time": int(time.time()) - 120,
            "descendants": 10,
            "id": 99999,
        }
        result = self.module._format_story(item, index=1)
        self.assertIn("[1] **Test Story**", result)
        self.assertIn("https://example.com", result)
        self.assertIn("42 points", result)
        self.assertIn("testuser", result)
        self.assertIn("https://news.ycombinator.com/item?id=99999", result)

    def test_strip_html(self):
        self.assertEqual(self.module._strip_html("<p>Hello &amp; bye</p>"), "Hello & bye")

    def test_relative_time(self):
        now = int(time.time())
        self.assertEqual(self.module._relative_time(now - 30), "just now")
        self.assertEqual(self.module._relative_time(now - 120), "2m ago")
        self.assertEqual(self.module._relative_time(now - 7200), "2h ago")
        self.assertEqual(self.module._relative_time(now - 172800), "2d ago")
        self.assertEqual(self.module._relative_time(None), "")


class TestNetworkMocked(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_fetch_stories_formats_results(self):
        mock_items = {
            1001: {
                "id": 1001,
                "type": "story",
                "title": "Test A",
                "score": 100,
                "by": "alice",
                "time": int(time.time()) - 60,
                "descendants": 20,
                "url": "https://a.com",
            },
            1002: {
                "id": 1002,
                "type": "story",
                "title": "Test B",
                "score": 50,
                "by": "bob",
                "time": int(time.time()) - 120,
                "descendants": 5,
            },
        }

        def mock_fetch(url):
            if "topstories" in url:
                return [1001, 1002]
            for item_id, item in mock_items.items():
                if str(item_id) in url:
                    return item
            return None

        with patch.object(self.module, "_fetch_json", side_effect=mock_fetch):
            result = self.module._fetch_stories("topstories", 2)
        self.assertIn("Test A", result)
        self.assertIn("Test B", result)
        self.assertIn("100 points", result)

    def test_search_no_results(self):
        with patch.object(self.module, "_fetch_json", return_value={"hits": []}):
            result = self.module._search_hn("nonexistent_query_xyz", 10)
        self.assertIn("No Hacker News results", result)

    def test_story_detail_not_found(self):
        with patch.object(self.module, "_fetch_item", return_value=None):
            result = self.module._story_detail(99999999)
        self.assertIn("Could not find", result)

    def test_story_detail_wrong_type(self):
        with patch.object(self.module, "_fetch_item", return_value={"type": "comment", "id": 123}):
            result = self.module._story_detail(123)
        self.assertIn("not a story", result)


class TestExecute(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()
        self.api = MagicMock()
        self.api.get_config.return_value = 10
        self.tool = self.module.HackerNewsTool(self.api)

    def test_execute_network_error(self):
        with patch.object(self.module, "_fetch_json", side_effect=urllib.error.URLError("timeout")):
            result = self.tool.execute("top_stories 3")
        self.assertIn("Network error", result)

    def test_execute_respects_config(self):
        self.api.get_config.return_value = 5
        with patch.object(self.module, "_fetch_stories", return_value="mocked") as mock:
            result = self.tool.execute("top_stories")
        self.assertEqual(result, "mocked")
        mock.assert_called_once_with("topstories", 5)

    def test_execute_empty_query(self):
        with patch.object(self.module, "_fetch_stories", return_value="mocked") as mock:
            result = self.tool.execute("")
        self.assertEqual(result, "mocked")
        mock.assert_called_once_with("topstories", 10)


class TestSkill(unittest.TestCase):
    def test_skill_file_exists_with_frontmatter(self):
        skill_path = PLUGIN_DIR / "skills" / "hacker_news_reader" / "SKILL.md"
        text = skill_path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---"))
        self.assertIn("name: hacker_news_reader", text)
        self.assertIn("display_name:", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
