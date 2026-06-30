from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path


def bootstrap() -> None:
    """Make Row-Bot source and dependencies available to repo scripts."""

    if _row_bot_importable() and _row_bot_dependencies_importable():
        return

    row_bot_root = _find_row_bot_root()
    if row_bot_root is None:
        return

    src = row_bot_root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    if _row_bot_dependencies_importable():
        return

    _reexec_with_row_bot_python(row_bot_root)


def _find_row_bot_root() -> Path | None:
    repo_root = Path(__file__).resolve().parents[1]
    candidates: list[Path] = []
    env_source = os.environ.get("ROW_BOT_SOURCE")
    if env_source:
        candidates.append(Path(env_source))
    candidates.extend([
        repo_root.parent / "row-bot",
        repo_root.parent / "Row-Bot",
        repo_root / "row-bot",
    ])

    for candidate in candidates:
        root = candidate.expanduser().resolve()
        src = root / "src"
        if (src / "row_bot").is_dir():
            return root
    return None


def _reexec_with_row_bot_python(row_bot_root: Path) -> None:
    if os.environ.get("ROW_BOT_BOOTSTRAPPED") == "1":
        return
    python = _row_bot_venv_python(row_bot_root)
    if python is None:
        return
    try:
        if Path(sys.executable).resolve() == python.resolve():
            return
    except OSError:
        pass
    env = os.environ.copy()
    env["ROW_BOT_BOOTSTRAPPED"] = "1"
    env["ROW_BOT_SOURCE"] = str(row_bot_root)
    completed = subprocess.run([str(python), *sys.argv], env=env, check=False)
    raise SystemExit(completed.returncode)


def _row_bot_venv_python(row_bot_root: Path) -> Path | None:
    candidates = [
        row_bot_root / ".venv" / "Scripts" / "python.exe",
        row_bot_root / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _row_bot_importable() -> bool:
    try:
        return importlib.util.find_spec("row_bot.plugins.manifest") is not None
    except (ImportError, ModuleNotFoundError):
        return False


def _row_bot_dependencies_importable() -> bool:
    try:
        return importlib.util.find_spec("langchain_core.tools") is not None
    except (ImportError, ModuleNotFoundError):
        return False
