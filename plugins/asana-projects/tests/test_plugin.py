import importlib.util
import json
import pathlib
import sys
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

        @property
        def destructive_tool_names(self):
            return set()

        @property
        def background_allowed_tool_names(self):
            return set()

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
        "asana_projects_plugin_main",
        PLUGIN_DIR / "plugin_main.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _http_error(code):
    return urllib.error.HTTPError(
        url="https://app.asana.com", code=code, msg="err", hdrs=None, fp=None
    )


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))

    def test_manifest_v2_shape(self):
        self.assertEqual(self.manifest["schema_version"], 2)
        self.assertEqual(self.manifest["id"], "asana-projects")
        self.assertEqual(self.manifest["min_row_bot_version"], "0.0.0")

    def test_permissions_minimal(self):
        self.assertEqual(sorted(self.manifest["permissions"]), ["account", "network"])

    def test_read_only_no_send_permissions(self):
        self.assertNotIn("external_send", self.manifest["permissions"])
        self.assertNotIn("messaging", self.manifest["permissions"])

    def test_provides_two_tools_and_skill(self):
        provides = self.manifest["provides"]
        ids = {t["id"] for t in provides["native_tools"]}
        self.assertEqual(ids, {"asana_projects", "asana_create_task"})
        for tool in provides["native_tools"]:
            self.assertEqual(tool["entrypoint"], "plugin_main.py")
        self.assertEqual(provides["skills"][0]["id"], "asana_projects")

    def test_declares_token_secret_and_auth(self):
        self.assertIn("access_token", self.manifest["secrets"])
        self.assertEqual(self.manifest["auth"]["account"]["type"], "bearer_token")
        self.assertEqual(self.manifest["auth"]["account"]["secret"], "access_token")

    def test_health_check_requires_token(self):
        checks = self.manifest["health_checks"]
        self.assertEqual(checks[0]["type"], "required_secrets")
        self.assertIn("access_token", checks[0]["secrets"])


class TestRegister(unittest.TestCase):
    def test_register_registers_both_tools(self):
        module = _load_module()
        api = MagicMock()
        module.register(api)
        self.assertEqual(api.register_tool.call_count, 2)
        names = {call.args[0].name for call in api.register_tool.call_args_list}
        self.assertEqual(names, {"asana_projects", "asana_create_task"})

    def test_read_tool_is_not_destructive(self):
        module = _load_module()
        tool = module.AsanaProjectsTool(MagicMock())
        self.assertEqual(tool.destructive_tool_names, set())

    def test_create_tool_is_destructive(self):
        module = _load_module()
        tool = module.AsanaCreateTaskTool(MagicMock())
        self.assertEqual(tool.destructive_tool_names, {"asana_create_task"})
        self.assertEqual(tool.name, "asana_create_task")


class TestQueryParser(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_empty_query_is_help(self):
        self.assertEqual(self.module._parse_query("", 10)[0], "help")

    def test_list_workspaces(self):
        action, params = self.module._parse_query("list_workspaces 5", 10)
        self.assertEqual(action, "list_workspaces")
        self.assertEqual(params["count"], 5)

    def test_list_tasks_requires_gid(self):
        self.assertEqual(self.module._parse_query("list_tasks", 10)[0], "error")
        self.assertEqual(self.module._parse_query("list_tasks abc", 10)[0], "error")

    def test_list_tasks_valid(self):
        action, params = self.module._parse_query("list_tasks 900 15", 10)
        self.assertEqual(action, "list_tasks")
        self.assertEqual(params["project"], "900")
        self.assertEqual(params["count"], 15)

    def test_search_tasks(self):
        action, params = self.module._parse_query("search_tasks onboarding 3", 10)
        self.assertEqual(action, "search_tasks")
        self.assertEqual(params["query"], "onboarding")
        self.assertEqual(params["count"], 3)

    def test_task_detail_valid_and_invalid(self):
        self.assertEqual(self.module._parse_query("task 777", 10)[1]["task"], "777")
        self.assertEqual(self.module._parse_query("task abc", 10)[0], "error")
        self.assertEqual(self.module._parse_query("task", 10)[0], "error")

    def test_blockers(self):
        self.assertEqual(self.module._parse_query("blockers 55", 10)[1]["project"], "55")
        self.assertEqual(self.module._parse_query("blockers x", 10)[0], "error")

    def test_bare_query_searches_tasks(self):
        action, params = self.module._parse_query("quarterly review", 10)
        self.assertEqual(action, "search_tasks")
        self.assertEqual(params["query"], "quarterly review")

    def test_count_clamping(self):
        self.assertEqual(self.module._parse_query("list_tasks 5 100", 10)[1]["count"], 30)
        self.assertEqual(self.module._parse_query("list_tasks 5 0", 10)[1]["count"], 1)


class TestListProjectsGrammar(unittest.TestCase):
    """Explicit grammar: first arg is always the workspace (gid or 'default')."""

    def setUp(self):
        self.module = _load_module()

    def test_no_args_uses_default(self):
        action, params = self.module._parse_query("list_projects", 10)
        self.assertEqual(action, "list_projects")
        self.assertEqual(params["workspace"], "")
        self.assertEqual(params["count"], 10)

    def test_default_keyword(self):
        action, params = self.module._parse_query("list_projects default", 10)
        self.assertEqual(action, "list_projects")
        self.assertEqual(params["workspace"], "")

    def test_default_keyword_with_count(self):
        action, params = self.module._parse_query("list_projects default 7", 10)
        self.assertEqual(params["workspace"], "")
        self.assertEqual(params["count"], 7)

    def test_gid_only_is_workspace_not_count(self):
        # The whole point: "list_projects 5" means workspace 5, NOT five projects.
        action, params = self.module._parse_query("list_projects 5", 10)
        self.assertEqual(action, "list_projects")
        self.assertEqual(params["workspace"], "5")
        self.assertEqual(params["count"], 10)

    def test_gid_with_count(self):
        action, params = self.module._parse_query("list_projects 123 5", 10)
        self.assertEqual(params["workspace"], "123")
        self.assertEqual(params["count"], 5)

    def test_invalid_workspace_is_rejected(self):
        action, params = self.module._parse_query("list_projects abc", 10)
        self.assertEqual(action, "error")
        self.assertIn("Invalid workspace", params["message"])


class TestFormatting(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_format_task_incomplete(self):
        task = {"gid": "1", "name": "Write spec", "completed": False,
                "assignee": {"name": "Ada"}, "due_on": "2026-08-01"}
        text = self.module._format_task(task, index=1)
        self.assertIn("[1] [ ] **Write spec**", text)
        self.assertIn("gid: 1", text)
        self.assertIn("Assignee: Ada", text)
        self.assertIn("Due: 2026-08-01", text)

    def test_format_task_shows_due_at(self):
        task = {"gid": "2", "name": "Timed", "completed": False,
                "due_at": "2026-08-01T17:00:00.000Z"}
        text = self.module._format_task(task)
        self.assertIn("Due: 2026-08-01T17:00:00.000Z", text)

    def test_format_task_completed(self):
        task = {"gid": "2", "name": "Done thing", "completed": True}
        self.assertIn("[x]", self.module._format_task(task))

    def test_format_project_uses_status_update(self):
        project = {"gid": "9", "name": "Website", "archived": False,
                   "current_status_update": {"text": "On track"}}
        text = self.module._format_project(project)
        self.assertIn("**Website**", text)
        self.assertIn("Status: On track", text)


class TestDueDateHandling(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_parse_due_on(self):
        self.assertEqual(self.module._parse_due_on("2026-08-01").isoformat(), "2026-08-01")
        self.assertIsNone(self.module._parse_due_on(None))
        self.assertIsNone(self.module._parse_due_on("not-a-date"))

    def test_parse_due_at_returns_local_date(self):
        # Any valid timestamp resolves to a local calendar date.
        d = self.module._parse_due_at("2026-08-01T12:00:00.000Z")
        self.assertIsNotNone(d)
        self.assertIsNone(self.module._parse_due_at(None))
        self.assertIsNone(self.module._parse_due_at("garbage"))

    def test_task_due_date_prefers_due_at(self):
        task = {"due_on": "2026-08-01", "due_at": "2030-01-01T00:00:00.000Z"}
        self.assertEqual(self.module._task_due_date(task).year, 2030)

    def test_blockers_classifies_both_due_forms(self):
        tasks = [
            {"gid": "1", "name": "OverdueOn", "completed": False, "due_on": "2000-01-01"},
            {"gid": "2", "name": "FutureOn", "completed": False, "due_on": "2999-01-01"},
            {"gid": "3", "name": "OverdueAt", "completed": False,
             "due_at": "2000-01-01T12:00:00.000Z"},
            {"gid": "4", "name": "FutureAt", "completed": False,
             "due_at": "2999-01-01T12:00:00.000Z"},
            {"gid": "5", "name": "NoDue", "completed": False},
        ]
        summary = self.module._summarize_blockers(tasks)
        self.assertIn("Open tasks: 5", summary)
        self.assertIn("Overdue: 2", summary)
        self.assertIn("Upcoming (has due date): 2", summary)
        self.assertIn("No due date: 1", summary)


class TestBlockersSummary(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_partial_label(self):
        tasks = [{"gid": "1", "name": "x", "completed": False, "due_on": "2000-01-01"}]
        summary = self.module._summarize_blockers(tasks, partial=True)
        self.assertIn("partial", summary.lower())

    def test_overdue_list_truncated(self):
        tasks = [
            {"gid": str(i), "name": f"T{i}", "completed": False, "due_on": "2000-01-01"}
            for i in range(25)
        ]
        summary = self.module._summarize_blockers(tasks)
        self.assertIn("Overdue: 25", summary)
        self.assertIn("5 more overdue", summary)  # 25 - 20 shown


class TestTypeaheadRequest(unittest.TestCase):
    """Assert the ACTUAL provider request, not a mock of _search_tasks."""

    def setUp(self):
        self.module = _load_module()

    def test_search_calls_typeahead_with_name_only(self):
        captured = {}

        def fake(method, path, token, **kwargs):
            captured["method"] = method
            captured["path"] = path
            captured["params"] = kwargs.get("params")
            return {"data": [{"gid": "1", "name": "Onboard client"}]}

        with patch.object(self.module, "_api_request", side_effect=fake):
            tasks = self.module._search_tasks("555", "onboard", 5, "tok")

        self.assertEqual(tasks[0]["name"], "Onboard client")
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["path"], "/workspaces/555/typeahead")
        params = captured["params"]
        self.assertEqual(params["resource_type"], "task")
        self.assertEqual(params["query"], "onboard")
        self.assertEqual(params["count"], 5)
        self.assertEqual(params["opt_fields"], "name")


class TestBlockersPagination(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_follows_offset_across_two_pages(self):
        pages = [
            {"data": [{"gid": "1", "name": "A", "completed": False}],
             "next_page": {"offset": "OFFSET_2"}},
            {"data": [{"gid": "2", "name": "B", "completed": False}],
             "next_page": None},
        ]
        offsets_seen = []

        def fake(method, path, token, **kwargs):
            params = kwargs.get("params", {})
            offsets_seen.append(params.get("offset"))
            return pages[len(offsets_seen) - 1]

        with patch.object(self.module, "_api_request", side_effect=fake):
            tasks, partial = self.module._project_open_tasks("900", "tok")

        self.assertEqual([t["gid"] for t in tasks], ["1", "2"])  # both pages contribute
        self.assertFalse(partial)
        self.assertIsNone(offsets_seen[0])          # first page: no offset
        self.assertEqual(offsets_seen[1], "OFFSET_2")  # second page: offset passed through

    def test_cap_marks_partial(self):
        # Every page reports another page -> cap reached -> partial True.
        def fake(method, path, token, **kwargs):
            return {"data": [{"gid": "1", "name": "x", "completed": False}],
                    "next_page": {"offset": "MORE"}}

        with patch.object(self.module, "_api_request", side_effect=fake):
            tasks, partial = self.module._project_open_tasks("900", "tok")

        self.assertTrue(partial)
        self.assertEqual(len(tasks), self.module._MAX_BLOCKER_PAGES)


class TestReadRunnersMocked(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_run_list_workspaces(self):
        fake = [{"gid": "1", "name": "Acme"}, {"gid": "2", "name": "Beta"}]
        with patch.object(self.module, "_list_workspaces", return_value=fake):
            result = self.module._run_list_workspaces(10, "tok")
        self.assertIn("Workspaces (2)", result)
        self.assertIn("Acme", result)

    def test_run_list_tasks_empty(self):
        with patch.object(self.module, "_list_tasks", return_value=[]):
            result = self.module._run_list_tasks("900", 10, "tok")
        self.assertIn("No tasks found in project 900", result)

    def test_run_search_tasks(self):
        fake = [{"gid": "5", "name": "Onboard client"}]
        with patch.object(self.module, "_search_tasks", return_value=fake):
            result = self.module._run_search_tasks("123", "onboard", 10, "tok")
        self.assertIn("Found 1 task(s)", result)
        self.assertIn("Onboard client", result)

    def test_run_task_detail_not_found(self):
        with patch.object(self.module, "_get_task", return_value=None):
            result = self.module._run_task_detail("999", "tok")
        self.assertIn("Could not find task with GID 999", result)

    def test_run_blockers_none_open(self):
        with patch.object(self.module, "_project_open_tasks", return_value=([], False)):
            result = self.module._run_blockers("55", "tok")
        self.assertIn("Nothing is blocking", result)

    def test_run_blockers_partial_forwarded(self):
        tasks = [{"gid": "1", "name": "x", "completed": False, "due_on": "2000-01-01"}]
        with patch.object(self.module, "_project_open_tasks", return_value=(tasks, True)):
            result = self.module._run_blockers("55", "tok")
        self.assertIn("partial", result.lower())


class TestReadExecute(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()
        self.api = MagicMock()
        self.api.get_config.side_effect = lambda key, default=None: {
            "default_count": 10,
            "default_workspace": "555",
        }.get(key, default)
        self.api.get_secret.return_value = "tok"
        self.tool = self.module.AsanaProjectsTool(self.api)

    def test_execute_without_token(self):
        self.api.get_secret.return_value = None
        self.assertIn("not configured", self.tool.execute("list_workspaces"))

    def test_execute_help(self):
        result = self.tool.execute("")
        self.assertIn("Commands", result)
        self.assertIn("list_workspaces", result)

    def test_execute_routes_to_list_tasks(self):
        with patch.object(self.module, "_run_list_tasks", return_value="ok") as mock:
            result = self.tool.execute("list_tasks 900 5")
        self.assertEqual(result, "ok")
        mock.assert_called_once_with("900", 5, "tok")

    def test_list_projects_default_uses_configured_workspace(self):
        with patch.object(self.module, "_run_list_projects", return_value="ok") as mock:
            self.tool.execute("list_projects")
        mock.assert_called_once_with("555", 10, "tok")

    def test_list_projects_explicit_gid_overrides_default(self):
        with patch.object(self.module, "_run_list_projects", return_value="ok") as mock:
            self.tool.execute("list_projects 999")
        mock.assert_called_once_with("999", 10, "tok")

    def test_list_projects_no_default_configured_errors(self):
        self.api.get_config.side_effect = lambda key, default=None: {
            "default_count": 10,
        }.get(key, default)
        self.assertIn("No workspace GID", self.tool.execute("list_projects"))

    def test_search_uses_default_workspace(self):
        with patch.object(self.module, "_run_search_tasks", return_value="ok") as mock:
            self.tool.execute("search_tasks onboarding")
        mock.assert_called_once_with("555", "onboarding", 10, "tok")

    def test_search_without_default_workspace_errors(self):
        self.api.get_config.side_effect = lambda key, default=None: {
            "default_count": 10,
        }.get(key, default)
        self.assertIn("No workspace GID", self.tool.execute("search_tasks x"))

    def test_execute_handles_http_401(self):
        with patch.object(self.module, "_run_list_workspaces", side_effect=_http_error(401)):
            self.assertIn("401", self.tool.execute("list_workspaces"))

    def test_execute_handles_rate_limit(self):
        with patch.object(self.module, "_run_list_workspaces", side_effect=_http_error(429)):
            self.assertIn("rate limit", self.tool.execute("list_workspaces").lower())


class TestCreateTask(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()
        self.api = MagicMock()
        self.api.get_secret.return_value = "tok"
        self.tool = self.module.AsanaCreateTaskTool(self.api)

    def test_parse_create(self):
        self.assertEqual(self.module._parse_create("900 Draft the plan"), ("900", "Draft the plan"))

    def test_parse_create_missing_name(self):
        self.assertEqual(self.module._parse_create("900"), (None, ""))

    def test_parse_create_non_gid(self):
        self.assertEqual(self.module._parse_create("abc Draft"), (None, ""))

    def test_run_create_posts_and_reports_gid(self):
        with patch.object(self.module, "_create_task", return_value={"gid": "7001"}) as mock:
            result = self.module._run_create_task("900", "New task", "tok")
        self.assertIn("Created task 'New task' in project 900 (gid: 7001)", result)
        mock.assert_called_once_with("900", "New task", "tok")

    def test_create_task_request_shape(self):
        captured = {}

        def fake(method, path, token, **kwargs):
            captured["method"] = method
            captured["path"] = path
            captured["body"] = kwargs.get("body")
            return {"data": {"gid": "7001"}}

        with patch.object(self.module, "_api_request", side_effect=fake):
            self.module._create_task("900", "New task", "tok")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["path"], "/tasks")
        self.assertEqual(captured["body"], {"data": {"name": "New task", "projects": ["900"]}})

    def test_run_create_bad_usage(self):
        self.assertIn("Usage", self.module._run_create_task(None, "", "tok"))

    def test_execute_without_token_is_blocked(self):
        self.api.get_secret.return_value = None
        self.assertIn("not configured", self.tool.execute("900 New task"))

    def test_execute_routes(self):
        with patch.object(self.module, "_run_create_task", return_value="ok") as mock:
            result = self.tool.execute("900 New task")
        self.assertEqual(result, "ok")
        project, name, token = mock.call_args.args
        self.assertEqual(project, "900")
        self.assertEqual(name, "New task")
        self.assertEqual(token, "tok")

    def test_execute_handles_http_403(self):
        with patch.object(self.module, "_run_create_task", side_effect=_http_error(403)):
            self.assertIn("Forbidden", self.tool.execute("900 New task"))


class TestSkill(unittest.TestCase):
    def test_skill_file_exists_with_frontmatter(self):
        skill_path = PLUGIN_DIR / "skills" / "asana_projects" / "SKILL.md"
        text = skill_path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---"))
        self.assertIn("name: asana_projects", text)
        self.assertIn("display_name:", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
