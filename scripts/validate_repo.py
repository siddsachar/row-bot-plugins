from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from _bootstrap_row_bot import bootstrap

bootstrap()

from row_bot.plugins.devtools import build_index, validate_plugin_path  # noqa: E402


REQUIRED_PATHS = (
    "README.md",
    "CONTRIBUTING.md",
    "AGENTS.md",
    "docs/PLUGIN_AUTHOR_GUIDE.md",
    "docs/MANIFEST_V2_REFERENCE.md",
    "docs/VALIDATION_AND_CATALOG.md",
    "docs/PLUGIN_REVIEW_CHECKLIST.md",
    "scripts/validate_plugin.py",
    "scripts/build_index.py",
)

SENSITIVE_PATTERNS = {
    "private Windows path": re.compile(r"[A-Za-z]:\\(?:Users|Code)\\"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "GitHub token": re.compile(r"\b(?:github_pat_|ghp_)[A-Za-z0-9_]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private key": re.compile(r"BEGIN (?:RSA |OPENSSH |)PRIVATE KEY"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the Row-Bot plugin marketplace repo.")
    parser.add_argument("root", nargs="?", default=".", help="row-bot-plugins repository root")
    parser.add_argument("--source", default="", help="Expected catalog source. Defaults to existing index source.")
    parser.add_argument("--write-index", action="store_true", help="Rewrite index.json before validation.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation output.")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if not root.is_dir():
        errors.append(f"Repository root not found: {root}")
        return _finish(False, errors, warnings, [], [], args.json)

    for rel in REQUIRED_PATHS:
        if not (root / rel).exists():
            errors.append(f"Missing required repository file: {rel}")

    plugin_results = _validate_dirs(root / "plugins")
    template_results = _validate_dirs(root / "templates")
    for section, results in (("plugins", plugin_results), ("templates", template_results)):
        if not results:
            errors.append(f"No directories found under {section}/")
        for result in results:
            if not result.get("ok"):
                errors.append(f"{section}/{Path(result.get('path', '')).name}: " + "; ".join(result.get("errors", [])))

    index_errors = _validate_index(root, source=args.source, write_index=args.write_index)
    errors.extend(index_errors)

    errors.extend(_scan_sensitive_text(root))

    ok = not errors
    return _finish(ok, errors, warnings, plugin_results, template_results, args.json)


def _validate_dirs(parent: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if not parent.is_dir():
        return results
    for plugin_dir in sorted(path for path in parent.iterdir() if path.is_dir()):
        result = validate_plugin_path(plugin_dir)
        results.append(asdict(result))
    return results


def _validate_index(root: Path, *, source: str, write_index: bool) -> list[str]:
    errors: list[str] = []
    index_path = root / "index.json"
    existing = _read_json(index_path)
    index_source = source or str(existing.get("source", "")) or str(root)
    expected = build_index(root, source=index_source)

    if write_index:
        index_path.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
        existing = expected

    if not index_path.exists():
        return ["Missing index.json"]
    if not existing:
        return ["index.json is not valid JSON"]
    if existing != expected:
        errors.append(
            "index.json is stale or was edited by hand. "
            "Run scripts/build_index.py with the same --source value."
        )
    return errors


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _scan_sensitive_text(root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts or ".local" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            errors.append(f"Could not read {rel}: {exc}")
            continue
        for label, pattern in SENSITIVE_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{rel} appears to contain {label}")
    return errors


def _finish(
    ok: bool,
    errors: list[str],
    warnings: list[str],
    plugin_results: list[dict[str, Any]],
    template_results: list[dict[str, Any]],
    json_output: bool,
) -> int:
    payload = {
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "plugins": plugin_results,
        "templates": template_results,
    }
    if json_output:
        print(json.dumps(payload, indent=2))
    else:
        print("Row-Bot plugin marketplace validation")
        print(f"plugins: {len(plugin_results)}")
        print(f"templates: {len(template_results)}")
        if warnings:
            print("warnings:")
            for warning in warnings:
                print(f"  - {warning}")
        if errors:
            print("errors:")
            for error in errors:
                print(f"  - {error}")
        print("result:", "ok" if ok else "failed")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
