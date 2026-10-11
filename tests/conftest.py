"""Shared pytest setup for the self-learning-agent test suite.

Several test modules import ``ollama`` transitively, which constructs a
``httpx.Client`` at import time. httpx parses every entry of ``NO_PROXY`` as a
URL pattern, so a malformed IPv6 entry such as ``[::1]`` (with stray square
brackets instead of the bare ``::1``) raises ``httpx.InvalidURL`` and aborts
the collection phase.

To keep tests independent of the host environment, this fixture rewrites the
process-level ``NO_PROXY`` / ``no_proxy`` variables so that no item contains
raw square brackets before any test module imports the ``ollama`` package.
The original values are restored after the session ends so the rest of the
harness keeps working.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DEPS_DIR = PROJECT_ROOT / ".deps"

# Make the package under test importable without relying on the host's global
# PYTHONPATH. The runtime launcher (``start.ps1`` / ``start.sh``) sets the same
# variables, but tests should not require a manual setup step.
for path in (SRC_DIR, DEPS_DIR):
    resolved = str(path)
    if resolved not in sys.path:
        sys.path.insert(0, resolved)


def _sanitize(value: str | None) -> str | None:
    if not value:
        return value
    cleaned = ",".join(
        item.strip()
        for item in value.split(",")
        if item.strip() and "[" not in item and "]" not in item
    )
    return cleaned


def _scrub_no_proxy() -> dict[str, str | None]:
    saved: dict[str, str | None] = {}
    for name in ("NO_PROXY", "no_proxy"):
        if name in os.environ:
            saved[name] = os.environ[name]
            os.environ[name] = _sanitize(os.environ[name]) or ""
    return saved


def pytest_configure(config):  # noqa: ARG001 - pytest hook signature
    saved = _scrub_no_proxy()
    config._no_proxy_backup = saved


def pytest_unconfigure(config):
    backup = getattr(config, "_no_proxy_backup", None)
    if not backup:
        return
    for name, value in backup.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value