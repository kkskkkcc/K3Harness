"""Self-learning AI agent package.

The system learns through durable, versioned memories. It does not update model
weights from live conversations.
"""

import os

__version__ = "0.1.0"


def _scrub_proxy_env() -> None:
    """Strip bracketed fragments from ``NO_PROXY`` before ollama loads.

    The ollama-python client eagerly constructs an ``httpx.Client`` on import,
    and httpx parses each ``NO_PROXY`` entry as a URL pattern. A host with
    ``NO_PROXY=localhost,127.0.0.1,::1,[::1]`` (square brackets around the
    IPv6 loopback) makes httpx raise ``InvalidURL: Invalid port: ':1]'`` at
    import time and the whole agent process fails to start. Removing the
    bracketed entries before any submodule imports ``ollama`` keeps the
    agent usable on such hosts while still honouring the well-formed items.
    """
    for name in ("NO_PROXY", "no_proxy"):
        value = os.environ.get(name)
        if not value:
            continue
        cleaned = ",".join(
            item.strip()
            for item in value.split(",")
            if item.strip() and "[" not in item and "]" not in item
        )
        os.environ[name] = cleaned


_scrub_proxy_env()