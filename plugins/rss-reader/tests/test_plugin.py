import importlib.util
import json
import pathlib
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
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
        "rss_reader_plugin_main",
        PLUGIN_DIR / "plugin_main.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_api(**config_overrides):
    store = dict(config_overrides)
    api = MagicMock()
    api.get_config = MagicMock(side_effect=lambda key, default=None: store.get(key, default))
    api.set_config = MagicMock(side_effect=lambda key, value: store.__setitem__(key, value))
    api._store = store
    return api


def _entry(title="Test", link="https://example.com", summary="A test entry", minutes_ago=10):
    return {
        "title": title,
        "link": link,
        "summary": summary,
        "published": datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    }


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))

    def test_manifest_v2_shape(self):
        self.assertEqual(self.manifest["schema_version"], 2)
        self.assertEqual(self.manifest["id"], "rss-reader")
        self.assertEqual(self.manifest["min_row_bot_version"], "0.0.0")
        self.assertEqual(self.manifest["permissions"], ["network"])

    def test_provides_tool_and_skill(self):
        provides = self.manifest["provides"]
        self.assertEqual(provides["native_tools"][0]["id"], "rss_reader")
        self.assertEqual(provides["native_tools"][0]["entrypoint"], "plugin_main.py")
        self.assertEqual(provides["skills"][0]["id"], "rss_reader")


class TestRegister(unittest.TestCase):
    def test_register_registers_tool(self):
        module = _load_module()
        api = MagicMock()
        module.register(api)
        api.register_tool.assert_called_once()
        tool = api.register_tool.call_args[0][0]
        self.assertEqual(tool.name, "rss_reader")
        self.assertEqual(tool.display_name, "RSS Reader")


class TestQueryParser(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_empty_query_defaults_to_list_feeds(self):
        self.assertEqual(self.module._parse_query("", 10)[0], "list_feeds")

    def test_add_feed_url_only(self):
        action, params = self.module._parse_query("add_feed https://example.com/feed.xml", 10)
        self.assertEqual(action, "add_feed")
        self.assertEqual(params["url"], "https://example.com/feed.xml")
        self.assertEqual(params["name"], "")

    def test_add_feed_url_with_name(self):
        action, params = self.module._parse_query("add_feed https://example.com/feed.xml My Blog", 10)
        self.assertEqual(action, "add_feed")
        self.assertEqual(params["name"], "My Blog")

    def test_remove_and_list(self):
        self.assertEqual(self.module._parse_query("remove_feed TechCrunch", 10)[0], "remove_feed")
        self.assertEqual(self.module._parse_query("list", 10)[0], "list_feeds")
        self.assertEqual(self.module._parse_query("list_feeds", 10)[0], "list_feeds")

    def test_fetch_by_name_and_count(self):
        action, params = self.module._parse_query("fetch TechCrunch 5", 10)
        self.assertEqual(action, "fetch")
        self.assertEqual(params["identifier"], "TechCrunch")
        self.assertEqual(params["count"], 5)

    def test_fetch_all_and_bare_url(self):
        self.assertEqual(self.module._parse_query("fetch_all 5", 10)[1]["count"], 5)
        action, params = self.module._parse_query("https://example.com/feed.xml", 10)
        self.assertEqual(action, "fetch")
        self.assertEqual(params["identifier"], "https://example.com/feed.xml")

    def test_unknown_command_returns_error(self):
        action, params = self.module._parse_query("explode everything", 10)
        self.assertEqual(action, "error")
        self.assertIn("Unknown command", params["message"])


class TestFeedStorage(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_get_feeds_empty(self):
        self.assertEqual(self.module._get_feeds(_make_api()), [])

    def test_get_feeds_json_string(self):
        feeds = self.module._get_feeds(_make_api(feeds='[{"url":"https://a.com","name":"A"}]'))
        self.assertEqual(len(feeds), 1)
        self.assertEqual(feeds[0]["url"], "https://a.com")

    def test_save_and_find_feed(self):
        api = _make_api()
        feeds = [{"url": "https://a.com/feed", "name": "Blog A"}]
        self.module._save_feeds(api, feeds)
        saved = json.loads(api._store["feeds"])
        self.assertEqual(saved, feeds)
        self.assertEqual(self.module._find_feed(saved, "blog a")["url"], "https://a.com/feed")


class TestParser(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_parse_rss_fixture(self):
        rss = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Example RSS</title>
    <item>
      <title>First Post</title>
      <link>https://example.com/first</link>
      <description><![CDATA[<p>Hello RSS</p>]]></description>
      <pubDate>Tue, 30 Jun 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""
        with patch.object(self.module, "_fetch_url", return_value=rss):
            result = self.module._parse_feed("https://example.com/rss")
        self.assertFalse(result.bozo)
        self.assertEqual(result.feed["title"], "Example RSS")
        self.assertEqual(result.entries[0]["title"], "First Post")
        self.assertEqual(result.entries[0]["summary"], "Hello RSS")

    def test_parse_atom_fixture(self):
        atom = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example Atom</title>
  <entry>
    <title>Atom Post</title>
    <link href="https://example.com/atom-post" />
    <summary>Atom summary</summary>
    <updated>2026-06-30T10:00:00Z</updated>
  </entry>
</feed>"""
        with patch.object(self.module, "_fetch_url", return_value=atom):
            result = self.module._parse_feed("https://example.com/atom")
        self.assertFalse(result.bozo)
        self.assertEqual(result.feed["title"], "Example Atom")
        self.assertEqual(result.entries[0]["link"], "https://example.com/atom-post")

    def test_parse_bad_xml(self):
        with patch.object(self.module, "_fetch_url", return_value=b"<rss>"):
            result = self.module._parse_feed("https://example.com/bad")
        self.assertTrue(result.bozo)


class TestFormatting(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_truncate_and_html_cleanup(self):
        self.assertEqual(self.module._truncate("<p>Hello &amp; world</p>"), "Hello & world")
        result = self.module._truncate("a" * 300, 50)
        self.assertEqual(len(result), 50)
        self.assertTrue(result.endswith("..."))

    def test_format_entry(self):
        result = self.module._format_entry(_entry(title="Big News"), 1, feed_name="My Blog")
        self.assertIn("Big News", result)
        self.assertIn("[1]", result)
        self.assertIn("My Blog", result)


class TestCommands(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_add_feed_success(self):
        api = _make_api()
        feed_result = self.module.FeedResult(
            feed={"title": "My Blog"},
            entries=[_entry()],
        )
        with patch.object(self.module, "_parse_feed", return_value=feed_result):
            result = self.module._add_feed(api, "https://example.com/feed.xml", "")
        self.assertIn("Subscribed", result)
        self.assertIn("My Blog", result)
        self.assertIn("feeds", api._store)

    def test_add_feed_validation_errors(self):
        api = _make_api()
        self.assertIn("Error", self.module._add_feed(api, "", ""))
        self.assertIn("Invalid URL", self.module._add_feed(api, "not-a-url", ""))
        duplicate_api = _make_api(feeds='[{"url":"https://example.com/feed.xml","name":"X"}]')
        self.assertIn("Already subscribed", self.module._add_feed(duplicate_api, "https://example.com/feed.xml", ""))

    def test_remove_feed(self):
        api = _make_api(feeds='[{"url":"https://a.com","name":"A"}]')
        self.assertIn("Unsubscribed", self.module._remove_feed(api, "A"))
        self.assertEqual(json.loads(api._store["feeds"]), [])
        self.assertIn("No feed found", self.module._remove_feed(_make_api(), "Missing"))

    def test_list_feeds(self):
        self.assertIn("No feeds subscribed", self.module._list_feeds(_make_api()))
        api = _make_api(feeds='[{"url":"https://a.com","name":"A"},{"url":"https://b.com","name":"B"}]')
        result = self.module._list_feeds(api)
        self.assertIn("2 subscribed feeds", result)
        self.assertIn("A", result)
        self.assertIn("B", result)

    def test_fetch_feed_success(self):
        api = _make_api(feeds='[{"url":"https://a.com/feed","name":"Blog A"}]')
        feed_result = self.module.FeedResult(
            feed={"title": "Blog A"},
            entries=[_entry(title="Post 1"), _entry(title="Post 2", minutes_ago=1)],
        )
        with patch.object(self.module, "_parse_feed", return_value=feed_result):
            result = self.module._fetch_feed(api, "Blog A", 10)
        self.assertIn("Blog A", result)
        self.assertIn("Post 1", result)
        self.assertIn("Post 2", result)

    def test_fetch_feed_errors(self):
        self.assertIn("Error", self.module._fetch_feed(_make_api(), "", 10))
        self.assertIn("No feed found", self.module._fetch_feed(_make_api(), "Missing", 10))
        api = _make_api(feeds='[{"url":"https://a.com/feed","name":"Blog A"}]')
        with patch.object(self.module, "_parse_feed", return_value=self.module.FeedResult(entries=[])):
            self.assertIn("No entries found", self.module._fetch_feed(api, "Blog A", 10))

    def test_fetch_all_success_and_partial_failure(self):
        api = _make_api(feeds=json.dumps([
            {"url": "https://a.com/feed", "name": "Blog A"},
            {"url": "https://bad.com/feed", "name": "Bad"},
        ]))

        def mock_parse(url):
            if "bad.com" in url:
                raise RuntimeError("timeout")
            return self.module.FeedResult(feed={"title": "Blog A"}, entries=[_entry(title="Good Post")])

        with patch.object(self.module, "_parse_feed", side_effect=mock_parse):
            result = self.module._fetch_all(api, 10)
        self.assertIn("Good Post", result)
        self.assertIn("Bad: timeout", result)


class TestExecute(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_execute_list_empty(self):
        tool = self.module.RSSReaderTool(_make_api(default_count=10))
        self.assertIn("No feeds subscribed", tool.execute("list_feeds"))

    def test_execute_add_feed(self):
        api = _make_api(default_count=10)
        tool = self.module.RSSReaderTool(api)
        feed_result = self.module.FeedResult(feed={"title": "Test"}, entries=[_entry()])
        with patch.object(self.module, "_parse_feed", return_value=feed_result):
            result = tool.execute("add_feed https://example.com/feed.xml")
        self.assertIn("Subscribed", result)

    def test_execute_unknown_action(self):
        tool = self.module.RSSReaderTool(_make_api(default_count=10))
        self.assertIn("Unknown command", tool.execute("explode 123"))


class TestSkill(unittest.TestCase):
    def test_skill_file_exists_with_frontmatter(self):
        skill_path = PLUGIN_DIR / "skills" / "rss_reader" / "SKILL.md"
        text = skill_path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---"))
        self.assertIn("name: rss_reader", text)
        self.assertIn("display_name:", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
