"""Whether this turn can ask a person before a sprite sheet is written.

Hermes keeps a permanent always line and checks it before its own cron,
single-query, and unattended refusals. This module refuses those turns
from the public cron mark and the session flags, before any file is written.
It does not read yolo or the approvals mode.
"""

from __future__ import annotations

import contextvars
import os
from typing import Any, Callable

_TRUTHY = frozenset({"1", "true", "yes", "on"})
# The same platforms Hermes treats as unattended on v0.22.2.
_UNATTENDED_PLATFORMS = frozenset({"webhook", "msgraph_webhook", "api_server"})
_CRON_READER: Callable[[], Any] | None = None


def bind_cron_reader(reader: Callable[[], Any] | None) -> None:
    """``ctx.current_cron_execution`` from register, or None outside cron-aware Hermes."""
    global _CRON_READER
    _CRON_READER = reader if callable(reader) else None


def _context_values(name: str) -> list[Any]:
    try:
        current = contextvars.copy_context()
    except Exception:
        return []
    found = []
    for var, value in current.items():
        if getattr(var, "name", None) == name:
            found.append(value)
    return found


def session_flag(name: str) -> str:
    """A set string on a ContextVar of this name, else the process environment.

    Hermes binds cron and the session platform on ContextVars and does not copy
    them into the process environment. An explicit empty string masks the
    environment. A non-string value, including an unset sentinel, does not.
    The first non-empty string wins, so a platform name is kept.
    """
    explicit_empty = False
    for value in _context_values(name):
        if isinstance(value, bool):
            if value:
                return "1"
            explicit_empty = True
            continue
        if not isinstance(value, str):
            continue
        if value == "":
            explicit_empty = True
            continue
        return value
    if explicit_empty:
        return ""
    return str(os.environ.get(name) or "")


def _flag_on(name: str) -> bool:
    return session_flag(name).strip().lower() in _TRUTHY


def unattended_reason() -> str | None:
    """Why this turn cannot ask a person, or None when a person can answer.

    A missing cron module is not cron. A reader that raises is cron, so the
    files are not written.
    """
    if os.environ.get("HERMES_PLUGIN_HOST_PROCESS") == "1":
        return "the plugin host"
    if _flag_on("HERMES_CRON_SESSION"):
        return "a cron job"
    reader = _CRON_READER
    if reader is None:
        try:
            from cron.execution_identity import current_cron_execution as reader
        except Exception:
            reader = None
    if reader is not None:
        try:
            mark = reader()
        except Exception:
            return "a turn whose cron mark could not be read"
        if mark is not None:
            return "a cron job"
    if _flag_on("HERMES_SINGLE_QUERY_SESSION"):
        return "a single-query run (hermes -q)"
    platform = session_flag("HERMES_SESSION_PLATFORM").strip().lower()
    if platform in _UNATTENDED_PLATFORMS:
        return "an unattended " + platform + " session"
    # Hermes honors a saved always line before fail_closed_when_no_human.
    # A later process with none of the marks above still writes unless we refuse here.
    # An interactive CLI binds `hermes_interactive` on the turn. It does not always
    # copy that flag into the process environment (ACP sessions in particular).
    if not _person_present():
        return "a non-interactive session with no person"
    return None


def _interactive_cli() -> bool:
    """True when this turn can show a CLI approval.

    A set context value wins, including an explicit empty string, which masks
    the process environment. No set value falls back to HERMES_INTERACTIVE.
    """
    decided = False
    on = False
    for value in _context_values("hermes_interactive"):
        if value is None:
            continue
        decided = True
        if isinstance(value, str):
            if value.strip().lower() in _TRUTHY:
                on = True
        elif bool(value):
            on = True
    if decided:
        return on
    return _flag_on("HERMES_INTERACTIVE")


def _person_present() -> bool:
    """True when a person or a gateway can answer this turn."""
    if _interactive_cli():
        return True
    if _flag_on("HERMES_GATEWAY_SESSION") or _flag_on("HERMES_EXEC_ASK"):
        return True
    platform = session_flag("HERMES_SESSION_PLATFORM").strip().lower()
    return bool(platform) and platform not in _UNATTENDED_PLATFORMS


def unattended_block(reason: str) -> dict:
    return {
        "action": "block",
        "message": (
            "BLOCKED: "
            + reason
            + " cannot write the sprite sheet, even after always. Nothing was written."
        ),
    }
