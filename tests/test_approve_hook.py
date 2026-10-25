"""Exercise Hermes's real pre_tool_call dispatcher with this plugin's hook."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / "trial"
HERMES_SRC = Path(os.environ.get("HERMES_SRC") or ROOT.parent / "hermes-agent-ref")
SHEET = TRIAL / "sprite_sheet" / "hero_sheet.png"


def _load_plugin():
    spec = importlib.util.spec_from_file_location("cut_sprite_sheet_plugin", ROOT / "__init__.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def plugin():
    return _load_plugin()


@pytest.fixture
def hermes(tmp_path, monkeypatch, plugin):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
    monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
    monkeypatch.delenv("HERMES_EXEC_ASK", raising=False)
    monkeypatch.delenv("HERMES_YOLO", raising=False)
    if not (HERMES_SRC / "hermes_cli" / "plugins.py").is_file():
        pytest.skip("set HERMES_SRC to a Hermes source tree")
    src = str(HERMES_SRC)
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        import hermes_cli.plugins as hp
    except Exception as exc:
        pytest.skip("Hermes source needs a newer Python: " + str(exc))

    mgr = hp.PluginManager(scope_key=str(tmp_path))
    mgr._discovered = True
    mgr._hooks["pre_tool_call"] = [plugin._on_pre_tool_call]
    monkeypatch.setattr(hp, "get_plugin_manager", lambda: mgr)
    monkeypatch.setattr(hp, "_plugin_manager", mgr)
    return hp


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "game"
    (project / "sprite_sheet").mkdir(parents=True)
    shutil.copy(SHEET, project / "sprite_sheet" / "hero_sheet.png")
    return project


def _slice_args(project: Path, write=True, replace=False):
    return {
        "project": str(project),
        "path": "sprite_sheet/hero_sheet.png",
        "cell_w": 16,
        "cell_h": 32,
        "write": write,
        "replace": replace,
    }


def test_write_returns_approve(hermes, plugin, tmp_path):
    project = _project(tmp_path)
    details = hermes._get_pre_tool_call_directive_details("slice_grid", _slice_args(project))
    assert details.action == "approve"
    assert details.message
    assert "\n" not in details.message
    assert "`" not in details.message
    assert "sprite_sheet/" in details.message


def test_inspect_and_dry_run_are_silent(hermes, tmp_path):
    project = _project(tmp_path)
    inspect = hermes._get_pre_tool_call_directive_details(
        "inspect_grid",
        {"project": str(project), "path": "sprite_sheet/hero_sheet.png", "cell_w": 16, "cell_h": 32},
    )
    dry = hermes._get_pre_tool_call_directive_details("slice_grid", _slice_args(project, write=False))
    assert inspect.action is None
    assert inspect.message is None
    assert dry.action is None
    assert dry.message is None


def test_denied_gate_writes_nothing(hermes, plugin, tmp_path):
    project = _project(tmp_path)
    target = project / "sprite_sheet" / "hero_sheet.png"
    before = hashlib.sha256(target.read_bytes()).hexdigest()
    extra = project / "sprite_sheet" / "hero_sheet.spriteframes.tres"
    assert not extra.exists()
    block, _modified = hermes._dispatch_pre_tool_call_hooks("slice_grid", _slice_args(project))
    assert block
    assert "BLOCKED" in block
    assert hashlib.sha256(target.read_bytes()).hexdigest() == before
    assert not extra.exists()


def test_mismatch_after_preview_writes_nothing(plugin, tmp_path):
    project = _project(tmp_path)

    class Ctx:
        def __init__(self):
            self.tools = {}

        def register_tool(self, name, toolset, schema, handler):
            self.tools[name] = handler

        def register_skill(self, *a, **k):
            return None

        def register_hook(self, name, callback):
            return None

    ctx = Ctx()
    plugin.register(ctx)
    first = _slice_args(project)
    assert plugin._on_pre_tool_call("slice_grid", first)
    written = json.loads(ctx.tools["slice_grid"](first))
    assert written.get("wrote") is True
    again = _slice_args(project, replace=True)
    hooked = plugin._on_pre_tool_call("slice_grid", again)
    assert hooked and hooked.get("action") == "approve"
    marker = project / "sprite_sheet" / "hero_sheet.slice.json"
    marker.write_text(marker.read_text(encoding="utf-8") + "tampered-before-write\n", encoding="utf-8")
    before = hashlib.sha256(marker.read_bytes()).hexdigest()
    body = json.loads(ctx.tools["slice_grid"](again))
    assert body.get("wrote") is False
    assert body.get("isError") is True
    assert "changed" in body.get("error", "").lower()
    assert hashlib.sha256(marker.read_bytes()).hexdigest() == before


def test_no_private_imports():
    pattern = "|".join(
        [
            "tools\\." + "approval",
            "_" + "yolo" + "_active",
            "approval" + "_context",
            "approval" + "_prompt",
        ]
    )
    proc = subprocess.run(
        ["grep", "-rn", pattern, "--include=*.py", "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1, proc.stdout


class _Ctx:
    def __init__(self):
        self.tools = {}

    def register_tool(self, name, toolset, schema, handler):
        self.tools[name] = handler

    def register_skill(self, *a, **k):
        return None

    def register_hook(self, name, callback):
        return None


def _handlers(plugin):
    ctx = _Ctx()
    plugin.register(ctx)
    return ctx.tools


IDS = {"session_id": "s1", "task_id": "t1"}


def test_handler_without_a_hook_writes_nothing(plugin, tmp_path):
    project = _project(tmp_path)
    tools = _handlers(plugin)
    body = json.loads(tools["slice_grid"](_slice_args(project), **IDS))
    assert body.get("wrote") is False
    assert not (project / "sprite_sheet" / "hero_sheet.spriteframes.tres").exists()


def test_preview_for_one_animation_does_not_cover_another(plugin, tmp_path):
    project = _project(tmp_path)
    tools = _handlers(plugin)
    walk = {**_slice_args(project), "animation": "walk"}
    attack = {**_slice_args(project), "animation": "attack"}
    assert plugin._on_pre_tool_call("slice_grid", walk, **IDS)
    body = json.loads(tools["slice_grid"](attack, **IDS))
    assert body.get("wrote") is False
    assert not (project / "sprite_sheet" / "hero_sheet.spriteframes.tres").exists()


def test_silent_call_rewritten_to_a_write_finds_no_preview(plugin, tmp_path):
    # An earlier write was refused (its preview stayed), then a write:false call is
    # rewritten into that same write by another plugin's modify directive.
    project = _project(tmp_path)
    tools = _handlers(plugin)
    refused = _slice_args(project)
    assert plugin._on_pre_tool_call("slice_grid", refused, **IDS)
    assert plugin._on_pre_tool_call("slice_grid", _slice_args(project, write=False), **IDS) is None
    body = json.loads(tools["slice_grid"](refused, **IDS))
    assert body.get("wrote") is False
    assert not (project / "sprite_sheet" / "hero_sheet.spriteframes.tres").exists()


def test_preview_from_another_session_is_not_used(plugin, tmp_path):
    project = _project(tmp_path)
    tools = _handlers(plugin)
    args = _slice_args(project)
    assert plugin._on_pre_tool_call("slice_grid", args, session_id="other", task_id="t1")
    body = json.loads(tools["slice_grid"](args, **IDS))
    assert body.get("wrote") is False


def test_old_preview_is_refused(plugin, tmp_path, monkeypatch):
    project = _project(tmp_path)
    tools = _handlers(plugin)
    args = _slice_args(project)
    assert plugin._on_pre_tool_call("slice_grid", args, **IDS)
    real = plugin.time.monotonic
    monkeypatch.setattr(plugin.time, "monotonic", lambda: real() + plugin._STASH_TTL + 1)
    body = json.loads(tools["slice_grid"](args, **IDS))
    assert body.get("wrote") is False


def test_approved_preview_writes_once(plugin, tmp_path):
    project = _project(tmp_path)
    tools = _handlers(plugin)
    args = _slice_args(project)
    assert plugin._on_pre_tool_call("slice_grid", args, **IDS)
    first = json.loads(tools["slice_grid"](args, **IDS))
    assert first.get("wrote") is True
    again = json.loads(tools["slice_grid"]({**args, "replace": True}, **IDS))
    assert again.get("wrote") is False


def test_rule_key_is_per_plan(hermes, tmp_path):
    project = _project(tmp_path)
    walk = {**_slice_args(project), "animation": "walk"}
    attack = {**_slice_args(project), "animation": "attack"}
    a = hermes._get_pre_tool_call_directive_details("slice_grid", walk)
    b = hermes._get_pre_tool_call_directive_details("slice_grid", attack)
    again = hermes._get_pre_tool_call_directive_details("slice_grid", dict(walk))
    assert a.action == b.action == "approve"
    assert a.rule_key and a.rule_key.startswith("slice_grid:")
    assert a.rule_key != b.rule_key
    assert a.rule_key == again.rule_key


def _gate(hermes, monkeypatch, env, project):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    block, _ = hermes._dispatch_pre_tool_call_hooks("slice_grid", _slice_args(project), session_id="s1", task_id="t1")
    return block


@pytest.mark.parametrize(
    "env",
    [{"HERMES_CRON_SESSION": "1"}, {"HERMES_SINGLE_QUERY_SESSION": "1"}, {"HERMES_SESSION_PLATFORM": "webhook"}],
)
def test_cron_single_query_and_unattended_are_refused(hermes, monkeypatch, tmp_path, env):
    project = _project(tmp_path)
    block = _gate(hermes, monkeypatch, {"HERMES_INTERACTIVE": "1", **env}, project)
    assert block and "BLOCKED" in block
    assert not (project / "sprite_sheet" / "hero_sheet.spriteframes.tres").exists()


def test_yolo_lets_hermes_skip_the_prompt(hermes, monkeypatch, tmp_path):
    # Hermes design, stated in the README: yolo skips the approval prompt.
    # --yolo is frozen when Hermes imports its approval module, so the test sets that state.
    import tools.approval as approval

    monkeypatch.setattr(approval, "_YOLO_MODE_FROZEN", True)
    project = _project(tmp_path)
    assert _gate(hermes, monkeypatch, {"HERMES_INTERACTIVE": "1"}, project) is None


def test_always_covers_only_the_same_plan(hermes, plugin, monkeypatch, tmp_path):
    from tools.terminal_tool import set_approval_callback

    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    asked = []

    def answer(command, description, **kwargs):
        asked.append(description)
        return "always" if len(asked) == 1 else "deny"

    set_approval_callback(answer)
    try:
        project = _project(tmp_path)
        walk = {**_slice_args(project), "animation": "walk"}
        attack = {**_slice_args(project), "animation": "attack", "replace": True}
        first, _ = hermes._dispatch_pre_tool_call_hooks("slice_grid", walk, session_id="a", task_id="t1")
        assert first is None
        second, _ = hermes._dispatch_pre_tool_call_hooks("slice_grid", attack, session_id="b", task_id="t2")
        assert second and "BLOCKED" in second
        assert len(asked) == 2
    finally:
        set_approval_callback(None)


def test_another_room_keeps_its_preview(plugin, tmp_path):
    project = _project(tmp_path)
    other = tmp_path / "other"
    (other / "sprite_sheet").mkdir(parents=True)
    shutil.copy(SHEET, other / "sprite_sheet" / "hero_sheet.png")
    tools = _handlers(plugin)
    args = _slice_args(project)
    assert plugin._on_pre_tool_call("slice_grid", args, session_id="a", task_id="t1")
    assert plugin._on_pre_tool_call("slice_grid", _slice_args(other), session_id="b", task_id="t2")
    body = json.loads(tools["slice_grid"](args, session_id="a", task_id="t1"))
    assert body.get("wrote") is True
