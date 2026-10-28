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


def test_write_returns_approve(hermes, plugin, monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
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


def test_mismatch_after_preview_writes_nothing(plugin, monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
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


def test_preview_for_one_animation_does_not_cover_another(plugin, monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    project = _project(tmp_path)
    tools = _handlers(plugin)
    walk = {**_slice_args(project), "animation": "walk"}
    attack = {**_slice_args(project), "animation": "attack"}
    assert plugin._on_pre_tool_call("slice_grid", walk, **IDS)
    body = json.loads(tools["slice_grid"](attack, **IDS))
    assert body.get("wrote") is False
    assert not (project / "sprite_sheet" / "hero_sheet.spriteframes.tres").exists()


def test_silent_call_rewritten_to_a_write_finds_no_preview(plugin, monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
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


def test_preview_from_another_session_is_not_used(plugin, monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    project = _project(tmp_path)
    tools = _handlers(plugin)
    args = _slice_args(project)
    assert plugin._on_pre_tool_call("slice_grid", args, session_id="other", task_id="t1")
    body = json.loads(tools["slice_grid"](args, **IDS))
    assert body.get("wrote") is False


def test_old_preview_is_refused(plugin, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    project = _project(tmp_path)
    tools = _handlers(plugin)
    args = _slice_args(project)
    assert plugin._on_pre_tool_call("slice_grid", args, **IDS)
    real = plugin.time.monotonic
    monkeypatch.setattr(plugin.time, "monotonic", lambda: real() + plugin._STASH_TTL + 1)
    body = json.loads(tools["slice_grid"](args, **IDS))
    assert body.get("wrote") is False


def test_approved_preview_writes_once(plugin, monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    project = _project(tmp_path)
    tools = _handlers(plugin)
    args = _slice_args(project)
    assert plugin._on_pre_tool_call("slice_grid", args, **IDS)
    first = json.loads(tools["slice_grid"](args, **IDS))
    assert first.get("wrote") is True
    again = json.loads(tools["slice_grid"]({**args, "replace": True}, **IDS))
    assert again.get("wrote") is False


def test_rule_key_is_per_plan(hermes, monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
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


def _snapshot(project: Path) -> dict:
    found = {}
    for path in sorted(project.rglob("*")):
        if path.is_file() and not path.is_symlink():
            found[str(path.relative_to(project))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def _approve_always_then(hermes, plugin, project, args, ids):
    from tools.terminal_tool import set_approval_callback

    set_approval_callback(lambda *_a, **_k: "always")
    try:
        first, _modified = hermes._dispatch_pre_tool_call_hooks("slice_grid", args, **ids)
        assert first is None
        tools = _handlers(plugin)
        written = json.loads(tools["slice_grid"](args, **ids))
        assert written.get("wrote") is True
        return tools
    finally:
        set_approval_callback(None)


def test_always_then_cron_context_writes_nothing(hermes, plugin, monkeypatch, tmp_path):
    """The scheduler sets HERMES_CRON_SESSION on a ContextVar and not in the process environment.

    After always, Hermes would honor the saved line before its own denial. The same plan must not write.
    """
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    for name in (
        "HERMES_CRON_SESSION",
        "HERMES_SINGLE_QUERY_SESSION",
        "HERMES_SESSION_PLATFORM",
        "HERMES_PLUGIN_HOST_PROCESS",
    ):
        monkeypatch.delenv(name, raising=False)
    project = _project(tmp_path)
    args = {**_slice_args(project, replace=True), "animation": "walk"}
    ids = {"session_id": "room", "task_id": "task"}
    tools = _approve_always_then(hermes, plugin, project, args, ids)
    before = _snapshot(project)
    from gateway.session_context import _VAR_MAP

    token = _VAR_MAP["HERMES_CRON_SESSION"].set("1")
    try:
        block, _modified = hermes._dispatch_pre_tool_call_hooks("slice_grid", args, **ids)
        if not block:
            json.loads(tools["slice_grid"](args, **ids))
    finally:
        _VAR_MAP["HERMES_CRON_SESSION"].reset(token)
    assert block and "BLOCKED" in block and "always" in block
    assert _snapshot(project) == before


def test_always_then_cron_mark_without_env_writes_nothing(hermes, plugin, monkeypatch, tmp_path):
    from cron.execution_identity import enter_cron_execution, exit_cron_execution

    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    monkeypatch.delenv("HERMES_CRON_SESSION", raising=False)
    project = _project(tmp_path)
    args = {**_slice_args(project, replace=True), "animation": "walk"}
    ids = {"session_id": "mark", "task_id": "task"}
    tools = _approve_always_then(hermes, plugin, project, args, ids)
    before = _snapshot(project)
    attendance = plugin._attendance()
    attendance.bind_cron_reader(
        __import__("cron.execution_identity", fromlist=["current_cron_execution"]).current_cron_execution
    )
    token = enter_cron_execution(
        {"id": "job", "name": "cut"},
        "exec-1",
        {"source": "builtin", "started_at": "2026-10-28T08:00:00Z"},
    )
    try:
        block, _modified = hermes._dispatch_pre_tool_call_hooks("slice_grid", args, **ids)
        if not block:
            json.loads(tools["slice_grid"](args, **ids))
    finally:
        exit_cron_execution(token)
        plugin._attendance().bind_cron_reader(None)
    assert block and "BLOCKED" in block
    assert _snapshot(project) == before


def test_always_then_single_query_env_writes_nothing(hermes, plugin, monkeypatch, tmp_path):
    # hermes chat -q assigns the process environment in cli_single_query.py. There is no ContextVar for it.
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    monkeypatch.delenv("HERMES_CRON_SESSION", raising=False)
    project = _project(tmp_path)
    args = {**_slice_args(project, replace=True), "animation": "walk"}
    ids = {"session_id": "query", "task_id": "task"}
    tools = _approve_always_then(hermes, plugin, project, args, ids)
    before = _snapshot(project)
    monkeypatch.setenv("HERMES_SINGLE_QUERY_SESSION", "1")
    block, _modified = hermes._dispatch_pre_tool_call_hooks("slice_grid", args, **ids)
    if not block:
        json.loads(tools["slice_grid"](args, **ids))
    assert block and "BLOCKED" in block
    assert _snapshot(project) == before


def test_always_then_webhook_context_writes_nothing(hermes, plugin, monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    monkeypatch.delenv("HERMES_CRON_SESSION", raising=False)
    monkeypatch.delenv("HERMES_SESSION_PLATFORM", raising=False)
    project = _project(tmp_path)
    args = {**_slice_args(project, replace=True), "animation": "walk"}
    ids = {"session_id": "hook", "task_id": "task"}
    tools = _approve_always_then(hermes, plugin, project, args, ids)
    before = _snapshot(project)
    from gateway.session_context import _VAR_MAP

    token = _VAR_MAP["HERMES_SESSION_PLATFORM"].set("webhook")
    try:
        block, _modified = hermes._dispatch_pre_tool_call_hooks("slice_grid", args, **ids)
        if not block:
            json.loads(tools["slice_grid"](args, **ids))
    finally:
        _VAR_MAP["HERMES_SESSION_PLATFORM"].reset(token)
    assert block and "BLOCKED" in block
    assert _snapshot(project) == before


def test_always_then_plugin_host_writes_nothing(hermes, plugin, monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    monkeypatch.delenv("HERMES_CRON_SESSION", raising=False)
    project = _project(tmp_path)
    args = {**_slice_args(project, replace=True), "animation": "walk"}
    ids = {"session_id": "host", "task_id": "task"}
    tools = _approve_always_then(hermes, plugin, project, args, ids)
    before = _snapshot(project)
    monkeypatch.setenv("HERMES_PLUGIN_HOST_PROCESS", "1")
    block, _modified = hermes._dispatch_pre_tool_call_hooks("slice_grid", args, **ids)
    if not block:
        json.loads(tools["slice_grid"](args, **ids))
    assert block and "BLOCKED" in block
    assert _snapshot(project) == before


def test_dry_run_under_cron_stays_silent(hermes, monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_CRON_SESSION", "1")
    project = _project(tmp_path)
    details = hermes._get_pre_tool_call_directive_details("slice_grid", _slice_args(project, write=False))
    assert details.action is None


def test_yolo_does_not_write_a_cron_job(hermes, plugin, monkeypatch, tmp_path):
    import tools.approval as approval

    monkeypatch.setattr(approval, "_YOLO_MODE_FROZEN", True)
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    monkeypatch.delenv("HERMES_CRON_SESSION", raising=False)
    project = _project(tmp_path)
    args = _slice_args(project, replace=True)
    ids = {"session_id": "yolo", "task_id": "task"}
    from gateway.session_context import _VAR_MAP

    token = _VAR_MAP["HERMES_CRON_SESSION"].set("1")
    try:
        block, _modified = hermes._dispatch_pre_tool_call_hooks("slice_grid", args, **ids)
        if not block:
            json.loads(_handlers(plugin)["slice_grid"](args, **ids))
    finally:
        _VAR_MAP["HERMES_CRON_SESSION"].reset(token)
    assert block and "BLOCKED" in block
    assert not (project / "sprite_sheet" / "hero_sheet.spriteframes.tres").exists()


def test_another_room_keeps_its_preview(plugin, monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
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


def _drop_person(monkeypatch):
    for name in (
        "HERMES_INTERACTIVE",
        "HERMES_GATEWAY_SESSION",
        "HERMES_EXEC_ASK",
        "HERMES_CRON_SESSION",
        "HERMES_SINGLE_QUERY_SESSION",
        "HERMES_SESSION_PLATFORM",
        "HERMES_PLUGIN_HOST_PROCESS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_no_person_blocks_before_the_saved_line(hermes, monkeypatch, tmp_path):
    _drop_person(monkeypatch)
    project = _project(tmp_path)
    details = hermes._get_pre_tool_call_directive_details("slice_grid", _slice_args(project))
    assert details.action == "block"
    assert "no person" in (details.message or "")


def test_turn_interactive_flag_can_approve_without_the_environment(hermes, monkeypatch, tmp_path):
    _drop_person(monkeypatch)
    import importlib

    mod = importlib.import_module("tools." + "approval" + "_context")
    token = mod.set_hermes_interactive_context(True)
    try:
        project = _project(tmp_path)
        details = hermes._get_pre_tool_call_directive_details("slice_grid", _slice_args(project))
        assert details.action == "approve"
    finally:
        mod.reset_hermes_interactive_context(token)


def test_blank_interactive_context_masks_the_environment(hermes, monkeypatch, tmp_path):
    _drop_person(monkeypatch)
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    import contextvars

    var = contextvars.ContextVar("hermes_interactive", default=None)
    token = var.set("")
    try:
        project = _project(tmp_path)
        details = hermes._get_pre_tool_call_directive_details("slice_grid", _slice_args(project))
        assert details.action == "block"
        assert "no person" in (details.message or "")
    finally:
        var.reset(token)


def test_always_then_no_person_writes_nothing(hermes, plugin, monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    project = _project(tmp_path)
    args = {**_slice_args(project, replace=True), "animation": "walk"}
    ids = {"session_id": "room", "task_id": "task"}
    tools = _approve_always_then(hermes, plugin, project, args, ids)
    target = project / "sprite_sheet" / "hero_sheet.spriteframes.tres"
    original = target.read_bytes()
    target.write_bytes(original + b"; tamper\n")
    stuck = _snapshot(project)
    _drop_person(monkeypatch)
    block, _modified = hermes._dispatch_pre_tool_call_hooks(
        "slice_grid", args, session_id="bare", task_id="bare"
    )
    if not block:
        json.loads(tools["slice_grid"](args, session_id="bare", task_id="bare"))
    assert block and "BLOCKED" in block and "no person" in block
    assert _snapshot(project) == stuck
    assert target.read_bytes().endswith(b"; tamper\n")


def _tileset_project(tmp_path: Path) -> Path:
    project = tmp_path / "game"
    (project / "sprite_sheet").mkdir(parents=True)
    shutil.copy(TRIAL / "sprite_sheet" / "tiles.png", project / "sprite_sheet" / "tiles.png")
    (project / "sprite_sheet" / "tiles.png.meta").write_text("; stale-hand\n", encoding="utf-8")
    return project


def _tileset_args(project: Path, contract) -> dict:
    return {
        "project": str(project),
        "path": "sprite_sheet/tiles.png",
        "cell_w": 32,
        "cell_h": 32,
        "kind": "tileset",
        "tile_names": ["grass", "water", "sand", "path"],
        "tile_coords": contract.shore_coords(),
        "tile_anim": {"water": {"frames": 3, "fps": 4}},
        "tile_peering": contract.shore_peering(),
        "write": True,
        "replace": True,
        "emit_scene": False,
    }


def test_unlink_name_stays_when_the_path_list_is_long(hermes, plugin, monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    project = _tileset_project(tmp_path)
    contract = plugin._contract()
    args = _tileset_args(project, contract)
    preview = contract.slice_grid(**plugin._slice_call(args), dry_run=True)
    paths = [str(item) for item in (preview.get("paths") or [])]
    assert len(paths) > 8
    assert "tiles.png.meta" not in " ".join(paths)
    assert preview.get("deletes") == ["sprite_sheet/tiles.png.meta"]
    details = hermes._get_pre_tool_call_directive_details("slice_grid", args)
    assert details.action == "approve"
    assert "tiles.png.meta" in (details.message or "")
    assert "\n" not in (details.message or "")


def test_unlink_rule_key_changes_every_call(hermes, plugin, monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    project = _tileset_project(tmp_path)
    args = _tileset_args(project, plugin._contract())
    first = hermes._get_pre_tool_call_directive_details("slice_grid", args, session_id="a", task_id="1")
    second = hermes._get_pre_tool_call_directive_details("slice_grid", args, session_id="b", task_id="2")
    assert first.action == second.action == "approve"
    assert first.rule_key != second.rule_key


def test_always_does_not_cover_the_next_unlink(hermes, plugin, monkeypatch, tmp_path):
    from tools.terminal_tool import set_approval_callback

    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    project = _tileset_project(tmp_path)
    args = _tileset_args(project, plugin._contract())
    meta = project / "sprite_sheet" / "tiles.png.meta"
    asked = []

    def answer(*_a, **_k):
        asked.append(1)
        return "always" if len(asked) == 1 else "deny"

    set_approval_callback(answer)
    try:
        ids = {"session_id": "one", "task_id": "t"}
        block, _modified = hermes._dispatch_pre_tool_call_hooks("slice_grid", args, **ids)
        assert block is None
        body = json.loads(_handlers(plugin)["slice_grid"](args, **ids))
        assert body.get("wrote") is True
        assert not meta.exists()
        meta.write_text("; stale-hand\n", encoding="utf-8")
        block2, _modified = hermes._dispatch_pre_tool_call_hooks(
            "slice_grid", args, session_id="two", task_id="t2"
        )
        assert block2 and "BLOCKED" in block2
        assert meta.is_file()
        assert len(asked) == 2
    finally:
        set_approval_callback(None)
