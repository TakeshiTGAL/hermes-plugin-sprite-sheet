"""Lock the sprite-sheet trial to the design, the samples, and one Godot run."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import sys
import struct
import subprocess
import time
import zlib
from pathlib import Path

from PIL import Image

import contract as C
import make_art

ROOT = Path(__file__).resolve().parent
SHIP = ROOT.parent
DESIGN = (SHIP / "DESIGN.md").read_text(encoding="utf-8")
SAMPLES = json.loads((SHIP / "failure_samples.json").read_text(encoding="utf-8"))
GODOT = "/opt/homebrew/bin/godot"
INSPECT_FIRST = "Read a sprite sheet or tileset png grid, frames, defects."
SLICE_FIRST = "Cut and slice a sprite sheet or tileset png for 2D."


def check(name: str, ok: bool, detail: str) -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
    if not ok:
        raise SystemExit(1)


def godot(args: list[str], cwd: Path, env: dict, timeout: float) -> tuple[int, str, float]:
    started = time.perf_counter()
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        out, _ = proc.communicate(timeout=timeout)
        code = proc.returncode if proc.returncode is not None else 1
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGTERM)
        time.sleep(0.4)
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
        out, _ = proc.communicate()
        code = proc.returncode if proc.returncode is not None else -9
    return code, out or "", time.perf_counter() - started


def lines_with(text: str, prefix: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith(prefix)]


def png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def fresh(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def output_symlinks() -> None:
    """A symlink at an output, or in a parent, stops the plan and writes nothing outside."""
    sheet = ROOT / "sprite_sheet" / "hero_sheet.png"
    base = Path("/tmp/ga_contract_outlink")
    fresh(base)
    outside = base / "outside"
    outside.mkdir()

    def cut(project: Path, dry_run: bool, replace: bool = True) -> dict:
        return C.slice_grid(
            project,
            "sprites/hero.png",
            16,
            32,
            kind="sprite",
            write=True,
            emit_scene=True,
            replace=replace,
            dry_run=dry_run,
        )

    live = base / "live"
    (live / "sprites").mkdir(parents=True)
    shutil.copy(sheet, live / "sprites" / "hero.png")
    live_target = outside / "live_target.tres"
    live_target.write_text("outside original\n", encoding="utf-8")
    live_before = live_target.read_bytes()
    (live / "sprites" / "hero.spriteframes.tres").symlink_to(live_target)
    live_plan = cut(live, True)
    check(
        "outlink_live_plan",
        live_plan["ok"] is False
        and live_plan.get("wrote") is False
        and live_plan.get("error") == "refusing a symlink: sprites/hero.spriteframes.tres."
        and live_plan.get("approval", "") == ""
        and live_target.read_bytes() == live_before
        and not (live / "sprites" / "hero.png.meta").exists(),
        live_plan.get("error", ""),
    )
    live_apply = cut(live, False)
    check(
        "outlink_live_apply",
        live_apply["ok"] is False
        and live_apply.get("wrote") is False
        and live_target.read_bytes() == live_before
        and (live / "sprites" / "hero.spriteframes.tres").is_symlink(),
        live_apply.get("error", ""),
    )

    dang = base / "dang"
    (dang / "sprites").mkdir(parents=True)
    shutil.copy(sheet, dang / "sprites" / "hero.png")
    missing = outside / "dangling_target.tres"
    (dang / "sprites" / "hero.spriteframes.tres").symlink_to(missing)
    dang_plan = cut(dang, True, replace=False)
    dang_apply = cut(dang, False, replace=False)
    check(
        "outlink_dangling_plan",
        dang_plan["ok"] is False
        and dang_plan.get("wrote") is False
        and dang_plan.get("error") == "refusing a symlink: sprites/hero.spriteframes.tres."
        and not missing.exists(),
        dang_plan.get("error", ""),
    )
    check(
        "outlink_dangling_apply",
        dang_apply["ok"] is False
        and dang_apply.get("wrote") is False
        and not missing.exists()
        and (dang / "sprites" / "hero.spriteframes.tres").is_symlink()
        and not (dang / "sprites" / "hero.png.meta").exists(),
        dang_apply.get("error", ""),
    )

    parent = base / "parent"
    real = outside / "parent_real"
    real.mkdir()
    shutil.copy(sheet, real / "hero.png")
    (real / "keep.txt").write_text("keep\n", encoding="utf-8")
    parent.mkdir()
    (parent / "sprites").symlink_to(real)
    before_names = sorted(item.name for item in real.iterdir())
    parent_reply = cut(parent, False, replace=True)
    check(
        "outlink_parent_slice",
        parent_reply["ok"] is False
        and parent_reply.get("wrote") is False
        and sorted(item.name for item in real.iterdir()) == before_names
        and (real / "keep.txt").read_text(encoding="utf-8") == "keep\n",
        parent_reply.get("error", ""),
    )

    proj = base / "rewrite_parent"
    proj.mkdir()
    ext = outside / "rewrite_ext"
    ext.mkdir()
    (ext / "keep.txt").write_text("keep\n", encoding="utf-8")
    (proj / "linked").symlink_to(ext)
    clause, err = C.rewrite_files(proj, [("linked/new.txt", "pwned\n")], True)
    check(
        "outlink_parent_plan",
        clause is None
        and err == "refusing a symlink: linked."
        and not (ext / "new.txt").exists()
        and (ext / "keep.txt").read_text(encoding="utf-8") == "keep\n",
        err,
    )
    clause, err = C.rewrite_files(proj, [("linked/new.txt", "pwned\n")], False)
    check(
        "outlink_parent_apply",
        clause is None
        and err == "refusing a symlink: linked."
        and not (ext / "new.txt").exists(),
        err,
    )

    inner = base / "inner"
    (inner / "sprites").mkdir(parents=True)
    shutil.copy(sheet, inner / "sprites" / "hero.png")
    victim = inner / "sprites" / "kept.tres"
    victim.write_text("inside original\n", encoding="utf-8")
    (inner / "sprites" / "hero.spriteframes.tres").symlink_to(victim)
    inner_before = victim.read_bytes()
    inner_plan = cut(inner, True)
    check(
        "outlink_inside_plan",
        inner_plan["ok"] is False
        and inner_plan.get("wrote") is False
        and inner_plan.get("error") == "refusing a symlink: sprites/hero.spriteframes.tres."
        and victim.read_bytes() == inner_before,
        inner_plan.get("error", ""),
    )

    plain = base / "plain"
    (plain / "sprites").mkdir(parents=True)
    shutil.copy(sheet, plain / "sprites" / "hero.png")
    plain_reply = cut(plain, True, replace=False)
    plain_names = sorted(item.name for item in (plain / "sprites").iterdir())
    check(
        "outlink_plain",
        plain_reply["ok"] is True
        and plain_reply.get("wrote") is False
        and plain_reply.get("error") == ""
        and plain_names == ["hero.png"],
        plain_reply.get("error", "") or str(plain_names),
    )

    kit = base / "kit"
    kit.mkdir()
    (kit / "sprite_sheet").mkdir()
    kit_target = outside / "kit_target.tres"
    kit_target.write_text("kit original\n", encoding="utf-8")
    kit_before = kit_target.read_bytes()
    (kit / "sprite_sheet" / "hero.spriteframes.tres").symlink_to(kit_target)
    kit_plan = C.place_kit(kit, "sprite_sheet/hero.png", kind="walk", write=True, replace=True, dry_run=True)
    kit_apply = C.place_kit(kit, "sprite_sheet/hero.png", kind="walk", write=True, replace=True, dry_run=False)
    check(
        "outlink_place_plan",
        kit_plan["ok"] is False
        and kit_plan.get("wrote") is False
        and kit_plan.get("error") == "refusing a symlink: sprite_sheet/hero.spriteframes.tres."
        and kit_target.read_bytes() == kit_before
        and not (kit / "sprite_sheet" / "hero.png").exists()
        and not (kit / "project.godot").exists(),
        kit_plan.get("error", ""),
    )
    check(
        "outlink_place_apply",
        kit_apply["ok"] is False
        and kit_apply.get("wrote") is False
        and kit_target.read_bytes() == kit_before
        and not (kit / "sprite_sheet" / "hero.png").exists(),
        kit_apply.get("error", ""),
    )


def output_atomic() -> None:
    """A hard link is detached. A parent symlink, `..`, and a swap cannot write outside."""
    sheet = ROOT / "sprite_sheet" / "hero_sheet.png"
    base = Path("/tmp/ga_contract_atomic")
    fresh(base)
    outside = base / "outside"
    outside.mkdir()
    phrase = "外の名前とつながったハードリンクを切る"

    proj = base / "slice"
    (proj / "sprites").mkdir(parents=True)
    shutil.copy(sheet, proj / "sprites" / "hero.png")
    ext = outside / "hard.tres"
    ext.write_text("outside hard original\n", encoding="utf-8")
    dest = proj / "sprites" / "hero.spriteframes.tres"
    os.link(ext, dest)
    before = ext.read_bytes()
    ext_ino = ext.stat().st_ino
    plan = C.slice_grid(
        proj, "sprites/hero.png", 16, 32, kind="sprite", write=True, replace=True, dry_run=True
    )
    check(
        "hardlink_plan",
        plan["ok"] is True
        and plan.get("wrote") is False
        and phrase in (plan.get("approval") or "")
        and ext.read_bytes() == before
        and ext.stat().st_ino == ext_ino,
        (plan.get("approval") or plan.get("error") or "")[-160:],
    )
    applied = C.slice_grid(
        proj, "sprites/hero.png", 16, 32, kind="sprite", write=True, replace=True, dry_run=False
    )
    check(
        "hardlink_apply",
        applied["ok"] is True
        and applied.get("wrote") is True
        and ext.read_bytes() == before
        and ext.stat().st_ino == ext_ino
        and dest.is_file()
        and not dest.is_symlink()
        and dest.stat().st_ino != ext_ino
        and dest.read_bytes() != before,
        applied.get("error", ""),
    )

    byte_proj = base / "bytes"
    (byte_proj / "sprites").mkdir(parents=True)
    byte_ext = outside / "pic.bin"
    byte_ext.write_bytes(b"PNG-OUT")
    byte_dest = byte_proj / "sprites" / "pic.png"
    os.link(byte_ext, byte_dest)
    byte_clause, byte_err = C.rewrite_files(byte_proj, [("sprites/pic.png", b"PNG-NEW")], True)
    byte_apply, byte_apply_err = C.rewrite_files(byte_proj, [("sprites/pic.png", b"PNG-NEW")], False)
    check(
        "hardlink_bytes",
        byte_err == ""
        and byte_clause is not None
        and phrase in byte_clause
        and byte_apply_err == ""
        and byte_ext.read_bytes() == b"PNG-OUT"
        and byte_dest.read_bytes() == b"PNG-NEW"
        and byte_dest.stat().st_ino != byte_ext.stat().st_ino,
        byte_err or byte_apply_err or (byte_clause or ""),
    )

    drop_proj = base / "drop"
    (drop_proj / "sprites").mkdir(parents=True)
    drop_ext = outside / "drop.txt"
    drop_ext.write_text("drop-outside\n", encoding="utf-8")
    drop_dest = drop_proj / "sprites" / "gone.txt"
    os.link(drop_ext, drop_dest)
    drop_clause, drop_err = C.rewrite_files(drop_proj, [("sprites/gone.txt", None)], True)
    _, drop_apply_err = C.rewrite_files(drop_proj, [("sprites/gone.txt", None)], False)
    check(
        "hardlink_delete",
        drop_err == ""
        and drop_clause is not None
        and phrase in drop_clause
        and drop_apply_err == ""
        and not drop_dest.exists()
        and drop_ext.read_text(encoding="utf-8") == "drop-outside\n",
        drop_err or drop_apply_err or (drop_clause or ""),
    )

    boom = base / "boom"
    (boom / "sprites").mkdir(parents=True)
    kept = boom / "sprites" / "note.txt"
    kept.write_text("original\n", encoding="utf-8")
    kept_bytes = kept.read_bytes()
    real_write = C._write_all

    def explode(fd: int, data: bytes) -> None:
        raise RuntimeError("boom")

    C._write_all = explode
    try:
        _clause, boom_err = C.rewrite_files(boom, [("sprites/note.txt", "new\n")], False)
    finally:
        C._write_all = real_write
    boom_names = sorted(os.listdir(boom / "sprites"))
    check(
        "partial_keeps_dest",
        boom_err == "refusing a partial write: sprites/note.txt."
        and kept.read_bytes() == kept_bytes
        and boom_names == ["note.txt"],
        boom_err + " " + " ".join(boom_names),
    )

    case = base / "case"
    (case / "sprites").mkdir(parents=True)
    case_ext = outside / "case.txt"
    case_ext.write_text("case-outside\n", encoding="utf-8")
    os.link(case_ext, case / "sprites" / "note.txt")
    case_clause, case_err = C.rewrite_files(case, [("sprites/NOTE.txt", "changed\n")], True)
    _, case_apply_err = C.rewrite_files(case, [("sprites/NOTE.txt", "changed\n")], False)
    case_note = case / "sprites" / "note.txt"
    check(
        "case_hardlink",
        case_err == ""
        and case_clause is not None
        and phrase in case_clause
        and case_apply_err == ""
        and case_ext.read_text(encoding="utf-8") == "case-outside\n"
        and case_note.read_text(encoding="utf-8") == "changed\n"
        and case_note.stat().st_ino != case_ext.stat().st_ino,
        case_err or case_apply_err or (case_clause or ""),
    )

    case_link = base / "case_link"
    (case_link / "sprites").mkdir(parents=True)
    case_target = outside / "case_sym.txt"
    case_target.write_text("sym-outside\n", encoding="utf-8")
    (case_link / "sprites" / "hero.spriteframes.tres").symlink_to(case_target)
    _clause, case_sym_err = C.rewrite_files(
        case_link, [("sprites/HERO.spriteframes.tres", "nope\n")], False
    )
    check(
        "case_symlink_file",
        case_sym_err == "refusing a symlink: sprites/HERO.spriteframes.tres."
        and case_target.read_text(encoding="utf-8") == "sym-outside\n"
        and (case_link / "sprites" / "hero.spriteframes.tres").is_symlink(),
        case_sym_err,
    )

    case_parent = base / "case_parent"
    case_real = outside / "case_real"
    case_real.mkdir()
    (case_real / "keep.txt").write_text("keep\n", encoding="utf-8")
    case_parent.mkdir()
    (case_parent / "Out").symlink_to(case_real)
    _clause, case_parent_err = C.rewrite_files(case_parent, [("out/new.txt", "pwned\n")], False)
    check(
        "case_symlink_parent",
        case_parent_err == "refusing a symlink: out."
        and not (case_real / "new.txt").exists()
        and (case_real / "keep.txt").read_text(encoding="utf-8") == "keep\n",
        case_parent_err,
    )

    dot = base / "dot"
    (dot / "sprites").mkdir(parents=True)
    dot_rel = "sprites/../../outside/pwned.txt"
    dot_clause, dot_err = C.rewrite_files(dot, [(dot_rel, "pwned\n")], True)
    _, dot_apply_err = C.rewrite_files(dot, [(dot_rel, "pwned\n")], False)
    walk_fd, walk_fds, walk_err = C._open_parent(dot, dot_rel)
    C._close_all(walk_fds)
    check(
        "dotdot_refused",
        dot_clause is None
        and dot_err == f"refusing a path outside the project: {dot_rel}."
        and dot_apply_err == f"refusing a path outside the project: {dot_rel}."
        and walk_fd is None
        and walk_err == f"refusing a path outside the project: {dot_rel}."
        and not (outside / "pwned.txt").exists()
        and not (base / "pwned.txt").exists(),
        dot_err or walk_err,
    )

    swap = base / "swap"
    (swap / "sprites").mkdir(parents=True)
    (swap / "sprites" / "marker.txt").write_text("marker\n", encoding="utf-8")
    attacker = outside / "attacker"
    attacker.mkdir()
    (attacker / "keep.txt").write_text("keep\n", encoding="utf-8")
    hold = swap / "sprites_real"
    real_block = C._output_block
    parent_calls = {"n": 0, "done": False}

    def swap_parent(project: Path, rel: str) -> str | None:
        result = real_block(project, rel)
        parent_calls["n"] += 1
        if parent_calls["n"] == 2 and result is None and not parent_calls["done"]:
            os.rename(swap / "sprites", hold)
            (swap / "sprites").symlink_to(attacker)
            parent_calls["done"] = True
        return result

    C._output_block = swap_parent
    try:
        _clause, swap_err = C.rewrite_files(swap, [("sprites/new.txt", "pwned\n")], False)
    finally:
        C._output_block = real_block
    check(
        "swap_parent",
        parent_calls["done"] is True
        and swap_err == "refusing a symlink: sprites."
        and not (attacker / "new.txt").exists()
        and not (hold / "new.txt").exists()
        and (hold / "marker.txt").read_text(encoding="utf-8") == "marker\n"
        and (attacker / "keep.txt").read_text(encoding="utf-8") == "keep\n"
        and not any(name.startswith(".rewrite.") for name in os.listdir(attacker))
        and not any(name.startswith(".rewrite.") for name in os.listdir(hold)),
        swap_err,
    )

    planted = base / "planted"
    (planted / "sprites").mkdir(parents=True)
    planted_target = outside / "planted.txt"
    planted_target.write_text("planted-outside\n", encoding="utf-8")
    planted_dest = planted / "sprites" / "new.txt"
    real_block = C._output_block
    planted_calls = {"n": 0, "done": False}

    def swap_symlink(project: Path, rel: str) -> str | None:
        result = real_block(project, rel)
        planted_calls["n"] += 1
        if planted_calls["n"] == 2 and result is None and not planted_calls["done"]:
            planted_dest.symlink_to(planted_target)
            planted_calls["done"] = True
        return result

    C._output_block = swap_symlink
    try:
        _clause, planted_err = C.rewrite_files(planted, [("sprites/new.txt", "pwned\n")], False)
    finally:
        C._output_block = real_block
    check(
        "swap_symlink_file",
        planted_calls["done"] is True
        and planted_err == "refusing a symlink: sprites/new.txt."
        and planted_dest.is_symlink()
        and planted_target.read_text(encoding="utf-8") == "planted-outside\n"
        and not any(name.startswith(".rewrite.") for name in os.listdir(planted / "sprites")),
        planted_err,
    )

    late = base / "late"
    (late / "sprites").mkdir(parents=True)
    late_ext = outside / "late.txt"
    late_ext.write_text("late-outside\n", encoding="utf-8")
    late_dest = late / "sprites" / "new.txt"
    real_block = C._output_block
    late_calls = {"n": 0, "done": False}

    def swap_hard(project: Path, rel: str) -> str | None:
        result = real_block(project, rel)
        late_calls["n"] += 1
        if late_calls["n"] == 2 and result is None and not late_calls["done"]:
            os.link(late_ext, late_dest)
            late_calls["done"] = True
        return result

    C._output_block = swap_hard
    try:
        _clause, late_err = C.rewrite_files(late, [("sprites/new.txt", "fresh\n")], False)
    finally:
        C._output_block = real_block
    check(
        "swap_hardlink",
        late_calls["done"] is True
        and late_err == ""
        and late_ext.read_text(encoding="utf-8") == "late-outside\n"
        and late_dest.read_text(encoding="utf-8") == "fresh\n"
        and late_dest.stat().st_ino != late_ext.stat().st_ino
        and not any(name.startswith(".rewrite.") for name in os.listdir(late / "sprites")),
        late_err or late_ext.read_text(encoding="utf-8"),
    )

    spell = base / "spell"
    (spell / "sprites").mkdir(parents=True)
    outside_before = sorted(item.name for item in outside.iterdir())
    refused = [
        "/tmp/ga_contract_atomic/outside/abs.txt",
        "sprites/../outside_rel.txt",
        "sprites/./../outside_dot.txt",
        "sprites/foo/../../../outside/deep.txt",
        "sprites\\new.txt",
        "",
        "sprites/new\x00.txt",
    ]
    spell_errors = []
    for rel in refused:
        _clause, err = C.rewrite_files(spell, [(rel, "pwned\n")], False)
        spell_errors.append(err)
    check(
        "spell_refused",
        all(err.startswith("refusing a path outside the project:") for err in spell_errors)
        and sorted(item.name for item in outside.iterdir()) == outside_before
        and not (base / "outside_rel.txt").exists()
        and not (base / "outside_dot.txt").exists()
        and not (spell / "sprites" / "new.txt").exists(),
        " | ".join(spell_errors),
    )


def overwrite_routes(ctx, calls, fake_prompt) -> None:
    """One check per rewrite route. Each check shows what an existing file would lose."""
    sys.modules["tools.approval_context"]._is_cron_approval_context = lambda: False
    source = Path(C.__file__).read_text(encoding="utf-8")
    found = [line.split("# route:", 1)[1].strip() for line in source.splitlines() if "# route:" in line]
    order = [
        "paths_txt",
        "png_meta",
        "png_import",
        "extruded_import",
        "slice_json",
        "sprite_tres",
        "tileset_tres",
        "tile_asset",
        "tile_asset_meta",
        "extruded_png",
        "stage_gd",
        "stage_tscn",
        "stale_meta",
        "walk_png",
        "walk_shore_png",
        "shore_png",
    ]
    sprite = Path("/tmp/ga_route_sprite")
    fresh(sprite)
    (sprite / "sprite_sheet").mkdir()
    shutil.copy(ROOT / "sprite_sheet" / "hero_sheet.png", sprite / "sprite_sheet" / "hero_sheet.png")
    made = C.slice_grid(sprite, "sprite_sheet/hero_sheet.png", 16, 32, kind="sprite", write=True, emit_scene=True)
    sprite_ready = made.get("ok") is True and made.get("wrote") is True

    def dry_sprite():
        return C.slice_grid(
            sprite,
            "sprite_sheet/hero_sheet.png",
            16,
            32,
            kind="sprite",
            write=True,
            emit_scene=True,
            replace=True,
            dry_run=True,
        )

    def shows(path: Path, marker: str, reply: dict) -> bool:
        line = reply.get("approval") or ""
        return (
            reply.get("ok") is True
            and reply.get("wrote") is False
            and marker in line
            and "\n" not in line
            and "`" not in line
            and len(line) <= 1500
            and marker in path.read_text(encoding="utf-8")
        )

    meta = sprite / "sprite_sheet" / "hero_sheet.png.meta"
    meta_before = meta.read_text(encoding="utf-8")
    meta.write_text(meta_before.replace("  userData: \n", "  userData: hand-meta\n", 1), encoding="utf-8")
    meta_reply = dry_sprite()
    check(
        "route_png_meta",
        sprite_ready and shows(meta, "hand-meta", meta_reply) and "lost walk_0" not in (meta_reply.get("approval") or ""),
        made.get("error", "") or (meta_reply.get("approval") or "")[-80:],
    )
    meta.write_text(meta_before, encoding="utf-8")

    imp = sprite / "sprite_sheet" / "hero_sheet.png.import"
    imp_before = imp.read_text(encoding="utf-8")
    imp.write_text(imp_before + "; import-hand\n", encoding="utf-8")
    check("route_png_import", shows(imp, "; import-hand", dry_sprite()), "")
    imp.write_text(imp_before, encoding="utf-8")

    doc = sprite / "sprite_sheet" / "hero_sheet.slice.json"
    doc_before = doc.read_text(encoding="utf-8")
    doc.write_text(doc_before + "; json-hand\n", encoding="utf-8")
    check("route_slice_json", shows(doc, "; json-hand", dry_sprite()), "")
    doc.write_text(doc_before, encoding="utf-8")

    stage_gd = sprite / "sprite_sheet" / "hero_sheet_stage.gd"
    gd_before = stage_gd.read_text(encoding="utf-8")
    stage_gd.write_text(gd_before + "; gd-hand\n", encoding="utf-8")
    check("route_stage_gd", shows(stage_gd, "; gd-hand", dry_sprite()), "")
    stage_gd.write_text(gd_before, encoding="utf-8")

    stage_tscn = sprite / "sprite_sheet" / "hero_sheet_stage.tscn"
    tscn_before = stage_tscn.read_text(encoding="utf-8")
    stage_tscn.write_text(tscn_before + "; tscn-hand\n", encoding="utf-8")
    check("route_stage_tscn", shows(stage_tscn, "; tscn-hand", dry_sprite()), "")
    stage_tscn.write_text(tscn_before, encoding="utf-8")

    tile = Path("/tmp/ga_route_tile")
    fresh(tile)
    (tile / "sprite_sheet").mkdir()
    shutil.copy(ROOT / "sprite_sheet" / "tiles.png", tile / "sprite_sheet" / "tiles.png")
    tiled = C.slice_grid(
        tile,
        "sprite_sheet/tiles.png",
        32,
        32,
        kind="tileset",
        tile_names=["grass", "water", "sand", "path"],
        tile_coords=C.shore_coords(),
        tile_anim={"water": {"frames": 3, "fps": 4}},
        tile_peering=C.shore_peering(),
        write=True,
    )
    tile_ready = tiled.get("ok") is True and tiled.get("wrote") is True

    def dry_tile():
        return C.slice_grid(
            tile,
            "sprite_sheet/tiles.png",
            32,
            32,
            kind="tileset",
            tile_names=["grass", "water", "sand", "path"],
            tile_coords=C.shore_coords(),
            tile_anim={"water": {"frames": 3, "fps": 4}},
            tile_peering=C.shore_peering(),
            write=True,
            replace=True,
            dry_run=True,
        )

    tileset = tile / "sprite_sheet" / "tiles.tileset.tres"
    tileset_before = tileset.read_text(encoding="utf-8")
    tileset.write_text(tileset_before + "; tileset-hand\n", encoding="utf-8")
    check("route_tileset_tres", tile_ready and shows(tileset, "; tileset-hand", dry_tile()), tiled.get("error", ""))
    tileset.write_text(tileset_before, encoding="utf-8")

    asset = tile / "sprite_sheet" / "tiles.grass.asset"
    asset_before = asset.read_text(encoding="utf-8")
    asset.write_text(asset_before + "; asset-hand\n", encoding="utf-8")
    check("route_tile_asset", shows(asset, "; asset-hand", dry_tile()), "")
    asset.write_text(asset_before, encoding="utf-8")

    asset_meta = tile / "sprite_sheet" / "tiles.grass.asset.meta"
    asset_meta_before = asset_meta.read_text(encoding="utf-8")
    asset_meta.write_text(asset_meta_before + "; asset-meta-hand\n", encoding="utf-8")
    meta_line = dry_tile()
    asset_meta.write_text(asset_meta_before.replace("guid: ", "guid: deadbeefdeadbeefdeadbeefdeadbeef", 1), encoding="utf-8")
    carried = C.slice_grid(
        tile,
        "sprite_sheet/tiles.png",
        32,
        32,
        kind="tileset",
        tile_names=["grass", "water", "sand", "path"],
        tile_coords=C.shore_coords(),
        tile_anim={"water": {"frames": 3, "fps": 4}},
        tile_peering=C.shore_peering(),
        write=True,
        replace=True,
    )
    carried_text = asset_meta.read_text(encoding="utf-8")
    check(
        "route_tile_asset_meta",
        shows(asset_meta, "; asset-meta-hand", meta_line) is False
        and "; asset-meta-hand" in (meta_line.get("approval") or "")
        and meta_line.get("wrote") is False
        and carried.get("wrote") is True
        and "guid: deadbeefdeadbeefdeadbeefdeadbeef" in carried_text,
        carried.get("error", ""),
    )
    # shows() requires the marker to still be in the file. The guid write replaced that file.
    # The marker check above uses the approval captured before the guid write.

    extra_import = tile / "sprite_sheet" / "tiles.extruded.png.import"
    extra_before = extra_import.read_text(encoding="utf-8")
    extra_import.write_text(extra_before + "; extrude-import-hand\n", encoding="utf-8")
    check("route_extruded_import", shows(extra_import, "; extrude-import-hand", dry_tile()), "")
    extra_import.write_text(extra_before, encoding="utf-8")

    extruded = tile / "sprite_sheet" / "tiles.extruded.png"
    extruded_bytes = extruded.read_bytes()
    extruded_line = dry_tile().get("approval") or ""
    extruded_sha = hashlib.sha256(extruded_bytes).hexdigest()
    check(
        "route_extruded_png",
        f"bytes {len(extruded_bytes)} {len(extruded_bytes)}" in extruded_line
        and extruded_sha in extruded_line
        and "sha256" in extruded_line
        and extruded.read_bytes() == extruded_bytes,
        str(len(extruded_line)),
    )

    stale = tile / "sprite_sheet" / "tiles.png.meta"
    stale.write_text("; stale-hand\n", encoding="utf-8")
    stale_reply = dry_tile()
    stale.write_text("; stale-hand\n`no`\n", encoding="utf-8")
    stale_refused = C.slice_grid(
        tile,
        "sprite_sheet/tiles.png",
        32,
        32,
        kind="tileset",
        tile_names=["grass", "water", "sand", "path"],
        tile_coords=C.shore_coords(),
        tile_anim={"water": {"frames": 3, "fps": 4}},
        tile_peering=C.shore_peering(),
        write=True,
        replace=True,
    )
    check(
        "route_stale_meta",
        shows(stale, "; stale-hand", stale_reply)
        and stale_refused.get("ok") is False
        and stale_refused.get("wrote") is False
        and "`no`" in stale.read_text(encoding="utf-8"),
        stale_refused.get("error", "") or (stale_reply.get("approval") or "")[-80:],
    )

    long = Path("/tmp/ga_route_long")
    fresh(long)
    folder = "p" * 245
    (long / folder).mkdir()
    shutil.copy(ROOT / "sprite_sheet" / "hero_sheet.png", long / folder / "hero.png")
    long_rel = f"{folder}/hero.png"
    listed = C.slice_grid(long, long_rel, 16, 32, kind="sprite", write=True, emit_scene=True)
    list_files = list((long / folder).glob("*.paths.txt"))
    list_ok = listed.get("ok") is True and listed.get("wrote") is True and len(list_files) == 1
    if list_ok:
        list_path = list_files[0]
        list_before = list_path.read_text(encoding="utf-8")
        list_path.write_text(list_before + "; list-hand\n", encoding="utf-8")
        listed_again = C.slice_grid(long, long_rel, 16, 32, kind="sprite", write=True, emit_scene=True, replace=True, dry_run=True)
        list_line = listed_again.get("approval") or ""
        list_ok = shows(list_path, "; list-hand", listed_again) and "paths.txt" in list_line
    check("route_paths_txt", list_ok, listed.get("error", "") or listed.get("approval", "")[:40])

    placed = Path("/tmp/ga_route_place")
    fresh(placed)
    first_place = C.place_kit(placed, "sprite_sheet/hero.png", kind="walk", write=True)
    hero_tres = placed / "sprite_sheet" / "hero.spriteframes.tres"
    hero_png = placed / "sprite_sheet" / "hero.png"
    shore_png = placed / "sprite_sheet" / "hero_tiles.png"
    tres_before = hero_tres.read_text(encoding="utf-8").replace('"speed": 8.0', '"speed": 12.0', 1) + "; hand\n"
    hero_tres.write_text(tres_before, encoding="utf-8")
    preview = C.place_kit(placed, "sprite_sheet/hero.png", kind="walk", write=True, replace=True, dry_run=True)
    preview_line = preview.get("approval") or ""
    hero_sha = hashlib.sha256(hero_png.read_bytes()).hexdigest()
    shore_sha = hashlib.sha256(shore_png.read_bytes()).hexdigest()
    calls.clear()
    fake_prompt.choice = "deny"
    denied = json.loads(
        ctx.tools["place_kit"]["handler"](
            {"project": str(placed), "path": "sprite_sheet/hero.png", "kind": "walk", "replace": True}
        )
    )
    denied_ok = (
        denied.get("wrote") is False
        and hero_tres.read_text(encoding="utf-8") == tres_before
        and len(calls) == 1
        and "; hand" in calls[0]["line"]
        and '"speed": 12.0' in calls[0]["line"]
    )
    hero_tres.write_text(tres_before + "`no`\n", encoding="utf-8")
    blocked = C.place_kit(placed, "sprite_sheet/hero.png", kind="walk", write=True, replace=True)
    fake_prompt.choice = "once"
    check(
        "route_sprite_tres",
        first_place.get("wrote") is True
        and preview.get("ok") is True
        and preview.get("wrote") is False
        and "lost sprite_sheet/hero.spriteframes.tres" in preview_line
        and '"speed": 12.0' in preview_line
        and "; hand" in preview_line
        and "\n" not in preview_line
        and "`" not in preview_line
        and denied_ok
        and blocked.get("ok") is False
        and blocked.get("wrote") is False
        and "`no`" in hero_tres.read_text(encoding="utf-8"),
        preview.get("error", "") or blocked.get("error", "") or str(len(preview_line)),
    )
    check(
        "route_walk_png",
        f"bytes {hero_png.stat().st_size} {len(hero_png.read_bytes())}" in preview_line
        and hero_sha in preview_line
        and preview_line.count(hero_sha) >= 2
        and "sha256" in preview_line,
        str(len(preview_line)),
    )
    check(
        "route_walk_shore_png",
        f"bytes {shore_png.stat().st_size} {len(shore_png.read_bytes())}" in preview_line
        and shore_sha in preview_line
        and preview_line.count(shore_sha) >= 2,
        "",
    )
    shore = Path("/tmp/ga_route_shore")
    fresh(shore)
    shore_first = C.place_kit(shore, "sprite_sheet/shore.png", kind="shore", write=True)
    shore_file = shore / "sprite_sheet" / "shore.png"
    shore_bytes = shore_file.read_bytes()
    shore_digest = hashlib.sha256(shore_bytes).hexdigest()
    shore_preview = C.place_kit(shore, "sprite_sheet/shore.png", kind="shore", write=True, replace=True, dry_run=True)
    shore_line = shore_preview.get("approval") or ""
    check(
        "route_shore_png",
        shore_first.get("wrote") is True
        and shore_preview.get("wrote") is False
        and f"bytes {len(shore_bytes)} {len(shore_bytes)}" in shore_line
        and shore_digest in shore_line
        and shore_line.count(shore_digest) >= 2
        and shore_file.read_bytes() == shore_bytes
        and found == order,
        shore_preview.get("error", "") or " ".join(found),
    )


def main() -> None:
    make_art.write(ROOT)
    hero = Image.open(ROOT / "sprite_sheet" / "hero_sheet.png").convert("RGBA")
    tiles = Image.open(ROOT / "sprite_sheet" / "tiles.png").convert("RGBA")
    padded = Image.open(ROOT / "sprite_sheet" / "padded_sheet.png").convert("RGBA")
    check("hero_size", hero.size == (64, 32), str(hero.size))
    check("bodies", C.component_count(hero) == 4, str(C.component_count(hero)))
    hero_raster = C.read_png(ROOT / "sprite_sheet" / "hero_sheet.png")
    check("foot_row", C.lowest_opaque_y(hero_raster, (0, 0, 16, 32)) == 31, "y31")
    check(
        "all_feet",
        all(C.lowest_opaque_y(hero_raster, (index * 16, 0, 16, 32)) == 31 for index in range(4)),
        "y31",
    )
    center = hero.load()
    check("empty_center_foot", center[32 + 8, 31][3] == 0 and center[32 + 4, 31][3] == 255, "gap")

    good = C.inspect_image(hero, 16, 32, source="sprite_sheet/hero_sheet.png")
    check("cell_16x32", good["ok"] and good["frame_count"] == 4 and good["defects"] == [], str(good["defects"]))
    check("hframes", good["hframes"] == 4 and good["vframes"] == 1 and "hframes to 4" in good["next"], good["next"])
    check("no_pixels", not C.reply_has_pixels(good), "reply keys only")

    split = C.inspect_image(hero, 16, 16)
    check("split", split["ok"] is False and split["error"] == SAMPLES["split_line"]["error"], split["error"])
    check("split_next", split["next"] == SAMPLES["split_line"]["next"], split["next"])
    check("no_square_round", "16 or 32" not in split["next"] and "Set cell" not in split["next"], split["next"])
    repaired = C.inspect_image(hero, split["suggest_cell_w"], split["suggest_cell_h"])
    check("repair_once", repaired["ok"] and repaired["frame_count"] == 4, f"{split['suggest_cell_w']}x{split['suggest_cell_h']}")

    bad = C.inspect_image(hero, 48, 40)
    check("indivisible", bad["error"] == SAMPLES["indivisible"]["error"] and bad["total"] == 0, bad["next"])
    square = C.inspect_image(hero, 24, 24)
    check(
        "square_24_cuts",
        square["ok"] is False and square["suggest_cell_w"] == 16 and square["suggest_cell_h"] == 32 and "does not divide" not in square["error"],
        square["error"],
    )

    wide = C.inspect_image(hero, 32, 32)
    check("multi_body", wide["ok"] is False and wide["error"] == SAMPLES["multi_body"]["error"], wide["error"])
    check("multi_suggest", wide["suggest_cell_w"] == 16 and wide["suggest_cell_h"] == 32, f"{wide['suggest_cell_w']}x{wide['suggest_cell_h']}")

    many = C.grid_rects(80 * 8, 8, 8, 8)
    check("no_frame_cap_64", many is not None and len(many[2]) == 80, str(len(many[2]) if many else None))
    huge = C.inspect_image(Image.new("RGBA", (4097, 1), (0, 0, 0, 0)), 1, 1)
    check("edge_cap", huge["ok"] is False and "4096" in huge["error"], huge["error"])

    class Huge:
        size = (4096, 4096)

        def load(self):
            raise AssertionError("load")

    capped = C.inspect_image(Huge(), 1, 1)
    check(
        "frame_cap",
        capped["truncated"] is True and capped["total"] == 16777216 and capped["ok"] is False and capped["frame_count"] == 0,
        f"total={capped['total']} truncated={capped['truncated']}",
    )
    check("frame_cap_text", capped["error"] == SAMPLES["truncated"]["error"] and capped["next"] == SAMPLES["truncated"]["next"], capped["next"])

    pad = C.inspect_image(padded, 16, 32, margin=(2, 2), spacing=(2, 2))
    check("padding", pad["ok"] and pad["frame_count"] == 4 and pad["columns"] == 4, str(pad["defects"]))
    check(
        "padding_next",
        "Margin is 2,2 and spacing is 2,2." in pad["next"] and "No margin" not in pad["next"] and "Nearest" in pad["next"],
        pad["next"],
    )

    tiles_ok = C.inspect_image(tiles, 32, 32)
    check("tiles_not_solid", tiles_ok["ok"] and "solid_cell" not in tiles_ok["defects"], str(tiles_ok["defects"]))

    bridge = Image.new("RGBA", (32, 16), (0, 0, 0, 0))
    bp = bridge.load()
    for y in range(2, 14):
        for x in range(2, 15):
            bp[x, y] = (200, 30, 30, 255)
        for x in range(17, 30):
            bp[x, y] = (30, 30, 200, 255)
    bp[15, 8] = (200, 30, 30, 255)
    bp[16, 8] = (30, 30, 200, 255)
    bridged = C.inspect_image(bridge, 16, 16)
    check(
        "one_pixel_touch",
        bridged["ok"] is False and "split_line" in bridged["defects"] and bridged["suggest_cell_w"] == 32 and bridged["suggest_cell_h"] == 16,
        bridged["next"],
    )

    span = Image.new("RGBA", (32, 16), (0, 0, 0, 0))
    sp = span.load()
    for y in range(4, 12):
        for x in range(4, 28):
            sp[x, y] = (200, 40, 40, 255)
    zero = C.inspect_image(span, 16, 16)
    check(
        "suggest_body",
        zero["ok"] is False and zero["suggest_cell_w"] == 32 and zero["suggest_cell_h"] == 16 and "0x0" not in zero["next"],
        zero["next"],
    )
    stacked = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    stack_px = stacked.load()
    for index in range(8):
        ox = (index % 4) * 16
        oy = (index // 4) * 32
        for yy in range(oy + 2, oy + 32):
            for xx in range(ox + 4, ox + 12):
                stack_px[xx, yy] = (180, 40, 40, 255)
    stacked_reply = C.inspect_image(stacked, 16, 16)
    check(
        "suggest_two_rows",
        stacked_reply["suggest_cell_w"] == 16 and stacked_reply["suggest_cell_h"] == 32,
        f"{stacked_reply['suggest_cell_w']}x{stacked_reply['suggest_cell_h']}",
    )

    speck = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    sk = speck.load()
    for y in range(2, 12):
        for x in range(2, 12):
            sk[x, y] = (10, 20, 30, 255)
    sk[15, 15] = (10, 20, 30, 255)
    loose = C.inspect_image(speck, 16, 16)
    check("loose_part", loose["ok"] and loose["error"] == "" and "loose_part" in loose["defects"], loose["next"])

    recolor = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    px = recolor.load()
    for frame, color in ((0, (220, 40, 40, 255)), (1, (40, 180, 60, 255))):
        for y in range(4, 28):
            for x in range(frame * 16 + 4, frame * 16 + 12):
                px[x, y] = color
    same = C.inspect_image(recolor, 16, 32)
    check("same_mask", same["ok"] and same["error"] == "" and same["next"] == SAMPLES["same_mask"]["next"] and same["next_ja"] == SAMPLES["same_mask"]["next_ja"], str(same["defects"]))
    twin = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    twin_px = twin.load()
    for frame in (0, 1):
        for yy in range(4, 28):
            for xx in range(frame * 16 + 4, frame * 16 + 12):
                twin_px[xx, yy] = (220, 40, 40, 255)
    twin_reply = C.inspect_image(twin, 16, 32)
    check("not_a_swap", twin_reply["ok"] and "color swap" not in twin_reply["next"] and "same_mask" not in twin_reply["defects"], twin_reply["next"])

    solid = Image.new("RGBA", (16, 16), (10, 20, 30, 255))
    solid_reply = C.inspect_image(solid, 16, 16)
    check("solid", solid_reply["ok"] and solid_reply["error"] == "" and solid_reply["next"] == SAMPLES["solid_cell"]["next"] and solid_reply["next_ja"] == SAMPLES["solid_cell"]["next_ja"], str(solid_reply["defects"]))

    tinted = Image.new("RGBA", (16, 32), (0, 0, 0, 0))
    tp = tinted.load()
    tp[1, 1] = (1, 2, 3, 0)
    for y in range(4, 20):
        for x in range(4, 12):
            tp[x, y] = (220, 40, 40, 255)
    tint = C.inspect_image(tinted, 16, 32)
    check("transparent_rgb", tint["ok"] and tint["error"] == "" and tint["next"] == SAMPLES["transparent_rgb"]["next"] and tint["next_ja"] == SAMPLES["transparent_rgb"]["next_ja"], str(tint["defects"]))
    raster = C.Raster(16, 32, bytearray(), {})
    raw = bytearray(16 * 32 * 4)
    raw[1 * 16 * 4 + 1 * 4 : 1 * 16 * 4 + 1 * 4 + 4] = bytes((1, 2, 3, 0))
    for y in range(4, 20):
        for x in range(4, 12):
            i = (y * 16 + x) * 4
            raw[i : i + 4] = bytes((220, 40, 40, 255))
    raster.pixels = raw
    check("zero_rgb", C.zero_transparent_rgb(raster) == 1, "one pixel")
    cleared = C.inspect_image(raster, 16, 32)
    check("transparent_cleared", cleared["ok"] and "transparent_rgb" not in cleared["defects"], str(cleared["defects"]))

    columns = C.inspect_image(hero, 16, 32, columns=8)
    check("columns", columns["ok"] is False and columns["total"] == 4 and columns["error"] == SAMPLES["columns"]["error"], columns["error"])
    fewer = C.inspect_image(hero, 16, 32, columns=2)
    check("columns_fewer", fewer["ok"] and fewer["frame_count"] == 2 and fewer["columns"] == 2, str(fewer["frame_count"]))
    stray = Image.new("RGBA", (20, 16), (0, 0, 0, 0))
    stray_px = stray.load()
    for x in range(20):
        stray_px[x, 0] = (1, 2, 3, 255)
    stray_reply = C.inspect_image(stray, 16, 16)
    check(
        "remainder_opaque",
        stray_reply["ok"] is False and stray_reply["error"] == SAMPLES["remainder"]["error"] and stray_reply["next"] == SAMPLES["remainder"]["next"],
        stray_reply["error"],
    )
    clear_edge = Image.new("RGBA", (20, 16), (0, 0, 0, 0))
    clear_edge.putpixel((1, 1), (1, 2, 3, 255))
    clear_reply = C.inspect_image(clear_edge, 16, 16)
    check("remainder_clear", clear_reply["ok"] is True and clear_reply["error"] == "", clear_reply["error"])
    touching = Image.new("RGBA", (64, 32), (0, 0, 0, 0))
    touch_px = touching.load()
    for y in range(4, 28):
        touch_px[31, y] = (20, 80, 20, 255)
        touch_px[32, y] = (20, 120, 40, 255)
    tile_touch = C.inspect_image(touching, 32, 32, kind="tileset")
    sprite_touch = C.inspect_image(touching, 32, 32, kind="sprite")
    check(
        "tile_edge",
        tile_touch["ok"] is True
        and "tile_edge" in tile_touch["defects"]
        and "1px spacing" in tile_touch["next"]
        and "64" not in tile_touch["next"]
        and sprite_touch["ok"] is False,
        tile_touch["next"],
    )
    wide_sheet = Image.new("RGBA", (120, 32), (0, 0, 0, 0))
    seven = C.inspect_image(wide_sheet, 16, 32)
    check("godot_columns", seven["ok"] and seven["frame_count"] == 7 and seven["columns"] == 7, str(seven["frame_count"]))
    leftover = C.grid_shape(72, 34, 16, 32, 2, 2, 2, 2)
    check("godot_margin", leftover == (4, 1), str(leftover))
    kept = C.inspect_image(Image.new("RGBA", (128, 32), (0, 0, 0, 0)), 16, 32, columns=7)
    check("columns_keep", kept["ok"] and kept["frame_count"] == 7 and kept["columns"] == 7, str(kept["frame_count"]))
    origin = C.inspect_image(hero, 16, 32, origin="center")
    check("origin", origin["ok"] is False and origin["error"].startswith("origin must be"), origin["error"])
    bottom = C.inspect_image(padded, 16, 32, margin=(2, 2), spacing=(2, 2), origin="bottom_left")
    check("origin_bottom", bottom["ok"] and bottom["frame_count"] == 4, str(bottom["defects"]))
    extruded = C.inspect_image(hero, 16, 32, extrude_px=1)
    check("extrude_clamped", extruded["ok"] and extruded["extrude_px"] == 0 and "extrude_clamped" in extruded["defects"], str(extruded["defects"]))

    project = Path("/tmp/ga_contract_paths")
    fresh(project)
    sheet = project / "sprite_sheet"
    sheet.mkdir()
    hero.save(sheet / "hero_sheet.png")
    hero.save(sheet / "npc.png")
    hero.save(sheet / "secret_door.png")
    hero.save(sheet / "secretary.png")
    hero.save(sheet / "id_rsa.png")
    hero.save(sheet / "credentials.png")
    outside = Path("/tmp/ga_contract_outside.png")
    hero.save(outside)
    (sheet / "linked.png").symlink_to(outside)
    (project / ".env").write_text("nope", encoding="utf-8")
    (project / "secrets.json").write_bytes(b"{}")
    before = (sheet / "hero_sheet.png").stat().st_mtime_ns
    linked = C.inspect_grid(project, "sprite_sheet/linked.png", 16, 32)
    check("symlink", linked["error"] == SAMPLES["symlink"]["error"], linked["error"])
    escaped = C.inspect_grid(project, "/tmp/ga_contract_outside.png", 16, 32)
    check("outside", escaped["error"] == SAMPLES["outside"]["error"], escaped["error"])
    secret = C.inspect_grid(project, ".env", 16, 32)
    check("secret_name", secret["ok"] is False and secret["error"] == "refusing a credential file.", secret["error"])
    secrets_json = C.inspect_grid(project, "secrets.json", 16, 32)
    check("secrets_json", secrets_json["error"] == "refusing a credential file.", secrets_json["error"])
    door = C.inspect_grid(project, "sprite_sheet/secret_door.png", 16, 32)
    check("secret_door", door["ok"] and door["frame_count"] == 4, door["error"])
    secretary = C.inspect_grid(project, "sprite_sheet/secretary.png", 16, 32)
    check("secretary", secretary["ok"] and secretary["frame_count"] == 4, secretary["error"])
    rsa = C.inspect_grid(project, "sprite_sheet/id_rsa.png", 16, 32)
    cred = C.inspect_grid(project, "sprite_sheet/credentials.png", 16, 32)
    check("id_rsa", rsa["error"] == "refusing a credential file.", rsa["error"])
    check("credentials_png", cred["error"] == "refusing a credential file.", cred["error"])
    check("inspect_writes_nothing", (sheet / "hero_sheet.png").stat().st_mtime_ns == before, "mtime")
    (sheet / "broken.png").write_bytes(b"not a png")
    try:
        broken = C.inspect_grid(project, "sprite_sheet/broken.png", 16, 32)
    except Exception as exc:
        check("bad_png", False, type(exc).__name__)
        return
    check("bad_png", broken["error"] == SAMPLES["bad_png"]["error"] and broken["next"] == SAMPLES["bad_png"]["next"], broken["error"])
    depth = sheet / "deep.png"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 16, 6, 0, 0, 0)
    depth.write_bytes(b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr))
    deep = C.inspect_grid(project, "sprite_sheet/deep.png", 1, 1)
    check("bit_depth", deep["ok"] is False and "16" in deep["error"] and deep["next"], deep["error"])

    gray = Image.new("L", (8, 8), 200)
    gray.save(sheet / "gray.png")
    gray_raster = C.read_png(sheet / "gray.png")
    check("gray_rgba", gray_raster.load()[0, 0] == (200, 200, 200, 255), str(gray_raster.load()[0, 0]))
    indexed = Image.new("P", (8, 8))
    indexed.putpalette([10, 20, 30] + [0] * (256 * 3 - 3))
    indexed.save(sheet / "indexed.png")
    indexed_raster = C.read_png(sheet / "indexed.png")
    check("indexed_rgba", indexed_raster.load()[0, 0][:3] == (10, 20, 30), str(indexed_raster.load()[0, 0]))

    held = C.replace_decision(True, False)
    check("replace", held["error"] == SAMPLES["replace"]["error"] and held["ok"] is False, held["next"])
    hero_paths = C.output_paths("sprite_sheet/hero_sheet.png", "sprite", emit_scene=True)
    npc_paths = C.output_paths("sprite_sheet/npc.png", "sprite", emit_scene=True)
    tile_paths = C.output_paths("sprite_sheet/tiles.png", "tileset", tile_names=["grass", "water", "sand", "path"])
    check("paths_differ", hero_paths != npc_paths and all("npc" in item for item in npc_paths), npc_paths[0])
    check("no_fixed_nine", "hero_frames.tres" not in hero_paths and "tiles.tres" not in tile_paths and "manifest.json" not in hero_paths, str(len(hero_paths)))
    text, mode = C.approval_text(hero_paths + tile_paths, replace=False)
    check("one_approval", mode == "inline" and len(text) < 1500 and "\n" not in text and "`" not in text, f"{mode} {len(text)}")
    print(f"APPROVAL_CHARS {len(text)}")
    replaced, rmode = C.approval_text(hero_paths, replace=True)
    check("replace_word", rmode == "inline" and replaced.startswith("replace "), replaced[:24])
    long = [f"sprite_sheet/{'frame' * 12}_{i:02d}.png" for i in range(68)]
    refused, refuse_mode = C.approval_text(long)
    check("overflow_is_manifest", refuse_mode == "manifest" and refused == "", str(len(" ".join(long))))
    check("plain_sprite_writes_nothing", C.writes_files("sprite", (0, 0), (0, 0), False, False, [1, 1, 1, 1]) is False, "hframes only")
    check("tight_sprite_writes", C.writes_files("sprite", (0, 0), (0, 0), True, True, [1, 1, 1, 1]) is True, "sidecars")

    quiet = Path("/tmp/ga_contract_quiet")
    fresh(quiet)
    (quiet / "sprite_sheet").mkdir()
    hero.save(quiet / "sprite_sheet" / "hero_sheet.png")
    skipped = C.slice_grid(quiet, "sprite_sheet/hero_sheet.png", 16, 32, kind="sprite", write=False)
    check("skip_write", skipped["ok"] and skipped.get("wrote") is False and not (quiet / "sprite_sheet" / "hero_sheet.png.meta").exists(), str(skipped.get("wrote")))
    default_dir = Path("/tmp/ga_contract_default")
    fresh(default_dir)
    (default_dir / "sprite_sheet").mkdir()
    shutil.copy(ROOT / "sprite_sheet" / "hero_sheet.png", default_dir / "sprite_sheet" / "hero_sheet.png")
    default_reply = C.slice_grid(default_dir, "sprite_sheet/hero_sheet.png", 16, 32, kind="sprite")
    check(
        "default_write",
        default_reply["ok"]
        and default_reply.get("wrote") is True
        and default_reply.get("hframes") == 4
        and default_reply.get("vframes") == 1
        and default_reply.get("foot") == [8, 32]
        and "SpriteFrames and a Unity Multiple slice were written" in default_reply.get("next", "")
        and (default_dir / "sprite_sheet" / "hero_sheet.spriteframes.tres").is_file()
        and '"speed": 8.0' in (default_dir / "sprite_sheet" / "hero_sheet.spriteframes.tres").read_text(encoding="utf-8")
        and (default_dir / "sprite_sheet" / "hero_sheet.png").read_bytes() == (ROOT / "sprite_sheet" / "hero_sheet.png").read_bytes(),
        str(default_reply.get("hframes")),
    )
    preview_dir = Path("/tmp/ga_contract_preview")
    fresh(preview_dir)
    (preview_dir / "sprite_sheet").mkdir()
    shutil.copy(ROOT / "sprite_sheet" / "padded_sheet.png", preview_dir / "sprite_sheet" / "padded_sheet.png")
    preview = C.slice_grid(
        preview_dir,
        "sprite_sheet/padded_sheet.png",
        16,
        32,
        kind="sprite",
        margin=(2, 2),
        spacing=(2, 2),
        dry_run=True,
    )
    preview_meta = preview_dir / "sprite_sheet" / "padded_sheet.png.meta"
    check(
        "dry_run",
        preview["ok"] and preview.get("wrote") is False and bool(preview.get("approval")) and "\n" not in preview["approval"] and not preview_meta.exists(),
        str(preview.get("wrote")),
    )
    preview_write = C.slice_grid(
        preview_dir,
        "sprite_sheet/padded_sheet.png",
        16,
        32,
        kind="sprite",
        margin=(2, 2),
        spacing=(2, 2),
    )
    check(
        "dry_run_same_line",
        preview_write.get("wrote") is True and preview_write.get("approval") == preview["approval"] and preview_meta.exists(),
        preview.get("approval", "")[:48],
    )
    wide_dir = Path("/tmp/ga_contract_wide")
    fresh(wide_dir)
    (wide_dir / "sprite_sheet").mkdir()
    hero.save(wide_dir / "sprite_sheet" / "hero_sheet.png")
    refused_wide = C.slice_grid(wide_dir, "sprite_sheet/hero_sheet.png", 32, 32, kind="sprite", write=True, replace=True)
    check("wide_writes_nothing", refused_wide["ok"] is False and not (wide_dir / "sprite_sheet" / "hero_sheet.png.meta").exists(), refused_wide["error"])

    emit = Path("/tmp/ga_contract_emit")
    fresh(emit)
    (emit / "sprite_sheet").mkdir()
    shutil.copy(ROOT / "sprite_sheet" / "padded_sheet.png", emit / "sprite_sheet" / "hero_sheet.png")
    emitted = C.slice_grid(
        emit,
        "sprite_sheet/hero_sheet.png",
        16,
        32,
        kind="sprite",
        margin=(2, 2),
        spacing=(2, 2),
        write=True,
        emit_scene=True,
        replace=True,
        extrude_px=1,
        trim=True,
        durations=[1, 2, 1, 1],
        foot=(8, 32),
        animation="walk",
        names=["walk_0", "walk_1", "walk_2", "walk_3"],
    )
    check("emit_ok", emitted["ok"] and emitted.get("wrote") is True, str(emitted.get("defects")))
    stage = (emit / "sprite_sheet" / "hero_sheet_stage.gd").read_text(encoding="utf-8")
    check(
        "emit_stage",
        "--probe" in stage
        and "SPRITE_SHEET_PROBE" in stage
        and "TEXTURE_FILTER_NEAREST" in stage
        and "ProjectSettings" in stage
        and "local_to_map" in stage
        and "frames_seen" in stage
        and "sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST" in stage
        and "map.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST" in stage
        and 'DisplayServer.get_name() == "headless"' in stage
        and stage.count("quit(0)") == 1,
        "stage",
    )
    emit_meta = (emit / "sprite_sheet" / "hero_sheet.png.meta").read_text(encoding="utf-8")
    check("extrude_meta", "spriteExtrude: 0" in emit_meta, "clamped")
    check("trim_pivot", "alignment: 9" in emit_meta, "measured foot")
    emit_doc = json.loads((emit / "sprite_sheet" / "hero_sheet.slice.json").read_text(encoding="utf-8"))
    check("durations", emit_doc["durations"] == [1, 2, 1, 1], str(emit_doc["durations"]))
    check("trim_bounds", bool(emit_doc["trim_bounds"]) and emit_doc["trim_bounds"][0][2] - emit_doc["trim_bounds"][0][0] < 15, str(emit_doc["trim_bounds"][0]))
    check("license_copied", emit_doc["license"] == make_art.LICENSE and emit_doc["slicing_creates_rights"] is False, emit_doc["license"][:40])
    emit_tres = (emit / "sprite_sheet" / "hero_sheet.spriteframes.tres").read_text(encoding="utf-8")
    check("trim_margin", "margin = Rect2(" in emit_tres and '"offset"' not in emit_tres, "margin")
    regions = [line for line in emit_tres.splitlines() if line.startswith("region = Rect2(")]
    check(
        "trim_rect",
        bool(regions) and any(int(line.split(",")[2]) < 16 for line in regions) and any(item.endswith(".spriteframes.tres") for item in emitted["paths"]),
        regions[0] if regions else "none",
    )
    check("extrude_json", emit_doc["extrude_px"] == 1, str(emit_doc["extrude_px"]))
    check(
        "spacing0_png",
        (emit / "sprite_sheet" / "hero_sheet.png").read_bytes() == (ROOT / "sprite_sheet" / "padded_sheet.png").read_bytes()
        and (emit / "sprite_sheet" / "hero_sheet.extruded.png").is_file(),
        "separate",
    )
    godot_rect = regions[0][len("region = Rect2(") : -1].split(", ")
    gx, gy, gw, gh = [int(float(part)) for part in godot_rect]
    unity_block = emit_meta.split("rect:", 1)[1]
    unity_vals = {}
    for key in ("x", "y", "width", "height"):
        unity_vals[key] = int(unity_block.split(f"{key}: ", 1)[1].splitlines()[0])
    check(
        "trim_same_rect",
        unity_vals["x"] == gx and unity_vals["width"] == gw and unity_vals["height"] == gh and unity_vals["y"] + gh + gy == 36,
        str(unity_vals),
    )
    kept_sidecar = emit / "sprite_sheet" / "hero_sheet.png.import"
    kept_sidecar.write_text(
        kept_sidecar.read_text(encoding="utf-8").replace(
            'type="CompressedTexture2D"\n',
            'type="CompressedTexture2D"\nuid="uid://crxo5rqm4suv3"\n',
            1,
        ),
        encoding="utf-8",
    )
    C.slice_grid(
        emit,
        "sprite_sheet/hero_sheet.png",
        16,
        32,
        kind="sprite",
        margin=(2, 2),
        spacing=(2, 2),
        write=True,
        replace=True,
        foot=(8, 32),
    )
    kept_text = kept_sidecar.read_text(encoding="utf-8")
    check("uid_kept", 'uid="uid://crxo5rqm4suv3"' in kept_text and "process/fix_alpha_border=false" in kept_text, "uid")

    gates = Path("/tmp/ga_contract_gates")
    fresh(gates)
    (gates / "sprite_sheet").mkdir()
    shutil.copy(ROOT / "sprite_sheet" / "hero_sheet.png", gates / "sprite_sheet" / "hero_sheet.png")
    shutil.copy(ROOT / "sprite_sheet" / "tiles.png", gates / "sprite_sheet" / "tiles.png")
    fps_reply = C.slice_grid(gates, "sprite_sheet/hero_sheet.png", 16, 32, kind="sprite", fps=0, write=True, replace=True)
    check(
        "fps_writes_nothing",
        fps_reply["ok"] is False and fps_reply["error"] == SAMPLES["fps"]["error"] and fps_reply["next"] == SAMPLES["fps"]["next"] and not (gates / "sprite_sheet" / "hero_sheet.png.meta").exists(),
        fps_reply["error"],
    )
    bare_png = gates / "sprite_sheet" / "bare.png"
    clean = Image.new("RGBA", (32, 32))
    bare_px = clean.load()
    for y in range(32):
        for x in range(32):
            bare_px[x, y] = (40, 120, 40, 255) if (x + y) % 5 else (20, 80, 30, 255)
    clean.save(bare_png)
    bare_reply = C.slice_grid(
        gates,
        "sprite_sheet/bare.png",
        32,
        32,
        kind="tileset",
        tile_names=["grass"],
        tile_coords={"grass": [0, 0]},
        write=True,
        replace=True,
    )
    check(
        "license_absent_writes",
        bare_reply["ok"] is True
        and bare_reply.get("wrote") is True
        and bare_reply.get("license") == ""
        and (gates / "sprite_sheet" / "bare.png.meta").exists(),
        str(bare_reply.get("license")),
    )
    restricted = gates / "sprite_sheet" / "restricted.png"
    restricted_ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    restricted_scan = zlib.compress(b"\x00" + bytes((255, 0, 0, 255)))
    restricted.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", restricted_ihdr)
        + png_chunk(b"tEXt", b"License\x00All Rights Reserved")
        + png_chunk(b"IDAT", restricted_scan)
        + png_chunk(b"IEND", b"")
    )
    restricted_reply = C.slice_grid(gates, "sprite_sheet/restricted.png", 1, 1, kind="sprite", write=True, replace=True, foot=(0, 1))
    check(
        "license_restricted",
        restricted_reply["ok"] is False
        and restricted_reply["error"] == SAMPLES["license"]["error"]
        and restricted_reply["next"] == SAMPLES["license"]["next"]
        and not (gates / "sprite_sheet" / "restricted.png.meta").exists(),
        restricted_reply["error"],
    )
    (gates / "sprite_sheet" / "copy.png").write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", restricted_ihdr)
        + png_chunk(b"tEXt", b"Copyright\x00CC0")
        + png_chunk(b"IDAT", restricted_scan)
        + png_chunk(b"IEND", b"")
    )
    copy_reply = C.slice_grid(gates, "sprite_sheet/copy.png", 1, 1, kind="sprite", write=True, replace=True, foot=(0, 1))
    check("copyright_cc0", copy_reply["ok"] and copy_reply.get("license") == "CC0", str(copy_reply.get("license")))
    (gates / "sprite_sheet" / "spdx.png").write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", restricted_ihdr)
        + png_chunk(b"tEXt", b"SPDX-License-Identifier\x00MIT")
        + png_chunk(b"IDAT", restricted_scan)
        + png_chunk(b"IEND", b"")
    )
    spdx_reply = C.slice_grid(gates, "sprite_sheet/spdx.png", 1, 1, kind="sprite", write=True, replace=True, foot=(0, 1))
    check("spdx_mit", spdx_reply["ok"] and spdx_reply.get("license") == "MIT", str(spdx_reply.get("license")))
    (gates / "sprite_sheet" / "unknown_words.png").write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", restricted_ihdr)
        + png_chunk(b"tEXt", b"License\x00Workshop doodle for my game")
        + png_chunk(b"IDAT", restricted_scan)
        + png_chunk(b"IEND", b"")
    )
    unknown_reply = C.slice_grid(gates, "sprite_sheet/unknown_words.png", 1, 1, kind="sprite", write=True, replace=True, foot=(0, 1))
    check(
        "license_warning",
        unknown_reply["ok"]
        and unknown_reply.get("license") == "Workshop doodle for my game"
        and "not a known free license" in unknown_reply["next"],
        unknown_reply["next"],
    )
    (gates / "sprite_sheet" / "empty_license.png").write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", restricted_ihdr)
        + png_chunk(b"tEXt", b"License\x00")
        + png_chunk(b"IDAT", restricted_scan)
        + png_chunk(b"IEND", b"")
    )
    empty_reply = C.slice_grid(gates, "sprite_sheet/empty_license.png", 1, 1, kind="sprite", write=True, replace=True, foot=(0, 1))
    check(
        "license_empty",
        empty_reply["ok"] is False and empty_reply["error"] == SAMPLES["license"]["error"] and not (gates / "sprite_sheet" / "empty_license.png.meta").exists(),
        empty_reply["error"],
    )
    quiet_bare = C.slice_grid(gates, "sprite_sheet/hero_sheet.png", 16, 32, kind="sprite", write=False)
    check("unlicensed_hframes", quiet_bare["ok"] and quiet_bare.get("wrote") is False, quiet_bare["next"])
    missing_coords = C.slice_grid(
        gates,
        "sprite_sheet/tiles.png",
        32,
        32,
        kind="tileset",
        tile_names=["grass", "water", "sand", "path"],
        replace=True,
    )
    check(
        "tile_coords_writes_nothing",
        missing_coords["ok"] is False
        and missing_coords["error"] == SAMPLES["tile_coords"]["error"]
        and missing_coords["next"] == SAMPLES["tile_coords"]["next"]
        and not (gates / "sprite_sheet" / "tiles.png.meta").exists(),
        missing_coords["error"],
    )
    long_names = [f"{'terrain' * 12}_{i:02d}" for i in range(20)]
    long_reply = C.slice_grid(
        gates,
        "sprite_sheet/tiles.png",
        32,
        32,
        kind="tileset",
        tile_names=long_names,
        tile_coords={name: [0, 0] for name in long_names},
        replace=True,
    )
    check(
        "approval_list_file",
        long_reply["ok"] is True
        and long_reply.get("wrote") is True
        and long_reply.get("approval", "").endswith("tiles.paths.txt")
        and len(long_reply.get("approval", "")) < 1500
        and (gates / "sprite_sheet" / "tiles.tileset.tres").exists()
        and (gates / "sprite_sheet" / "tiles.paths.txt").is_file(),
        long_reply.get("approval", long_reply.get("error", "")),
    )
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    scan = zlib.compress(b"\x00" + bytes((255, 0, 0, 255)))
    itxt = b"License\x00\x00\x00\x00\x00" + b"Trial iTXt license."
    ztxt = b"Note\x00\x00" + zlib.compress(b"Trial zTXt note.")
    tiny = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"iTXt", itxt)
        + png_chunk(b"zTXt", ztxt)
        + png_chunk(b"IDAT", scan)
        + png_chunk(b"IEND", b"")
    )
    (gates / "sprite_sheet" / "tiny.png").write_bytes(tiny)
    tiny_raster = C.read_png(gates / "sprite_sheet" / "tiny.png")
    check("itxt_license", tiny_raster.text.get("License") == "Trial iTXt license." and tiny_raster.text.get("Note") == "Trial zTXt note.", str(tiny_raster.text))
    tiny_reply = C.slice_grid(gates, "sprite_sheet/tiny.png", 1, 1, kind="sprite", write=True, replace=True, foot=(0, 1))
    check("itxt_slice", tiny_reply["ok"] and tiny_reply.get("license") == "Trial iTXt license.", tiny_reply.get("error", ""))
    corrupt = bytearray(tiny)
    corrupt[29] ^= 0xFF
    (gates / "sprite_sheet" / "corrupt.png").write_bytes(corrupt)
    corrupt_reply = C.inspect_grid(gates, "sprite_sheet/corrupt.png", 1, 1)
    check("bad_crc", corrupt_reply["error"] == SAMPLES["bad_png"]["error"] and corrupt_reply["next"] == SAMPLES["bad_png"]["next"], corrupt_reply["error"])

    source_text = (ROOT / "contract.py").read_text(encoding="utf-8")
    check("stdlib_png", "PIL" not in source_text and "Pillow" not in source_text, "contract")
    check("first_inspect", INSPECT_FIRST in DESIGN and len(INSPECT_FIRST) <= 60 and "cut" not in INSPECT_FIRST.lower() and not INSPECT_FIRST.startswith("Read-only"), INSPECT_FIRST)
    check("first_slice", SLICE_FIRST in DESIGN and len(SLICE_FIRST) <= 60 and all(word in SLICE_FIRST.lower() for word in ("cut", "slice", "png", "2d")), SLICE_FIRST)
    start = DESIGN.index("pixel art sprite sheet cutter")
    disclosure = DESIGN[start : DESIGN.index("```", start)].strip()
    needed = [
        "Disclosure —",
        "inspect_grid",
        "slice_grid",
        "place_kit",
        "Nothing is sent",
        "No API key",
        "No daily cap",
        "gateway",
        "hermes tools",
        "One approval",
        "cron",
        "yolo",
        "approvals off",
        "always",
        "list file",
        "writes nothing",
        "restrictive license is not written",
        "Unknown text is copied",
        "share-alike",
        "no rights are attached",
        "godot --headless --editor --quit --path <project>",
        "solid-color box",
        "sound effect",
        "Does not launch Godot or Unity",
        "app-userdata",
        "no cron job",
        "2D game",
        "pixel art",
        "Linux",
        "Unity editor",
        "スプライトシート",
        "タイルセット",
    ]
    missing = [item for item in needed if item not in disclosure]
    hidden = [item for item in ("fix_alpha_border", "spriteID", "peering", "--probe", "spriteExtrude") if item in disclosure]
    check("disclosure", not missing and not hidden, f"chars={len(disclosure)} missing={missing} hidden={hidden}")
    print(f"DISCLOSURE_CHARS {len(disclosure)}")
    readme_md = (SHIP / "README.md").read_text(encoding="utf-8")
    check(
        "readme_import",
        "Godot は自分で開き" not in readme_md
        and "Open the editor yourself" not in readme_md
        and C.IMPORT_CMD in readme_md
        and C.IMPORT_CMD in source_text,
        "readme",
    )
    check("design_margin0", "余白か間隔があるシートだけ" not in DESIGN, "line")
    readme = DESIGN[DESIGN.index("## README に回すこと") :]
    for item in ("fix_alpha_border", "spriteID", "peering", "--probe", "spriteExtrude", "uid", "32", "Full Rect", "internalIDToNameTable"):
        check(f"readme_{item}", item in readme, item)
    for banned in ("この本", "this book", "takeshitgal", ".harness", "loop.wav", "Set cell to 16 or 32", "pip install"):
        check(f"banned_{banned}", banned not in DESIGN, "absent")
    for key, sample in SAMPLES.items():
        if sample["error"]:
            check(f"design_quotes_{key}", sample["error"] in DESIGN and sample["next"] in DESIGN, key)
        else:
            check(f"design_quotes_{key}", sample["next"] in DESIGN, key)

    doc = json.loads((ROOT / "sprite_sheet" / "padded_sheet.slice.json").read_text(encoding="utf-8"))
    check("source_license", doc["license"] == make_art.LICENSE and doc["slicing_creates_rights"] is False and "music" not in doc, doc["license"][:24])
    check("source_duration", doc["durations"] == [1, 2, 1, 1] and doc["foot"] == [8, 32] and doc["animation"] == "walk" and "default" not in doc["animations"], str(doc["animations"]))
    meta = (ROOT / "sprite_sheet" / "padded_sheet.png.meta").read_text(encoding="utf-8")
    hero_meta_body = (ROOT / "sprite_sheet" / "hero_sheet.png.meta").read_text(encoding="utf-8")
    tile_meta = (ROOT / "sprite_sheet" / "tiles.extruded.png.meta").read_text(encoding="utf-8")
    for label, body in (("hero_meta", meta), ("tile_meta", tile_meta)):
        check(
            label,
            "spritePixelsToUnits: 32" in body
            and "spriteExtrude: 0" in body
            and "alphaIsTransparency: 0" in body
            and "spriteMeshType: 0" in body
            and "spriteID:" in body
            and "nameFileIdTable:" in body
            and "platformSettings:" in body
            and "spriteBorder:" in body
            and "textureCompression: 0" in body
            and "enableMipMap: 0" in body
            and "serializedVersion: 11" in body
            and "maxTextureSize: 4096" in body
            and "maxTextureSize: 2048" not in body,
            label,
        )
    water = (ROOT / "sprite_sheet" / "tiles.water.asset").read_text(encoding="utf-8")
    grass = (ROOT / "sprite_sheet" / "tiles.grass.asset").read_text(encoding="utf-8")
    check(
        "water_animated",
        "m_AnimatedSprites:" in water
        and "13b75c95f34a00d4e8c04f76b73312e6" in water
        and "m_TileColliderType: 0" in water
        and "m_MinSpeed: 4.0" in water
        and water.count("type: 3") >= 3
        and "fileID: 13312" not in water,
        "water",
    )
    check(
        "grass_collider",
        grass.count("m_Sprites:") == 16
        and "m_DefaultColliderType: 2" in grass
        and "9d1514134bc4fbd41bb739b1b9a49231" in grass
        and "fileID: 13312" not in grass,
        "rule",
    )
    digest = hashlib.md5(b"res://sprite_sheet/hero_sheet.png").hexdigest()
    sidecar = (ROOT / "sprite_sheet" / "hero_sheet.png.import").read_text(encoding="utf-8")
    check("hero_pivot", "alignment: 7" in meta and "pivot: {x: 0.5, y: 0}" in meta and "internalIDToNameTable: []" not in meta and "213:" in meta, "bottom")
    check("tile_pivot", "alignment: 0" in tile_meta and "pivot: {x: 0.5, y: 0.5}" in tile_meta and "213:" in tile_meta, "center")
    grass_at = tile_meta.find("name: grass_1")
    grass_block = tile_meta[grass_at : grass_at + 500]
    check(
        "guid_split",
        "guid: a11ce0000000000000000000000a0001" in hero_meta_body
        and "guid: b22ce0000000000000000000000b0003" in meta
        and "guid: a11ce0000000000000000000000a0001" not in meta
        and not (ROOT / "sprite_sheet" / "tiles.png.meta").exists(),
        "unique",
    )
    check(
        "sprite_id_shape",
        "691f6e4395d0ca9788fc488a7d6c3913" not in hero_meta_body
        and "691f6e4395d0ca9788fc488a7d6c3913" not in tile_meta
        and hero_meta_body.count("0800000000000000") >= 4
        and "0800000000000000" in tile_meta,
        "suffix",
    )
    sys.path.insert(0, str(SHIP / "tests"))
    from test_fileid_reopen import check_fileids

    fileid_count = check_fileids()
    check("fileid_reopen", fileid_count == "4", fileid_count)
    check("extruded_gap_x", grass_at >= 0 and "x: 33" in grass_block, grass_block[:80])
    hero_png = C.read_png(ROOT / "sprite_sheet" / "hero_sheet.png")
    opaque_colors = set()
    raw_px = hero_png.pixels
    for index in range(0, len(raw_px), 4):
        if raw_px[index + 3]:
            opaque_colors.add(tuple(raw_px[index : index + 4]))
    check(
        "walk_colors",
        len(opaque_colors) >= 3
        and (220, 40, 40, 255) in opaque_colors
        and (42, 36, 52, 255) in opaque_colors
        and (255, 214, 170, 255) in opaque_colors,
        str(sorted(opaque_colors)),
    )
    tiles_doc = json.loads((ROOT / "sprite_sheet" / "tiles.slice.json").read_text(encoding="utf-8"))
    check(
        "tiles_json",
        tiles_doc["frames"] == 24 and "foot" not in tiles_doc and tiles_doc["animation"] == "" and tiles_doc.get("unity_water") == "animated_tile" and tiles_doc["durations"] == [] and tiles_doc["tile_animation"]["water"]["columns"] == 3 and tiles_doc["file"].endswith("tiles.extruded.png") and tiles_doc["spacing"] == [1, 1] and tiles_doc["columns"] == 8 and tiles_doc["rows"] == 3,
        str(tiles_doc["frames"]),
    )
    tiles_tres = (ROOT / "sprite_sheet" / "tiles.tileset.tres").read_text(encoding="utf-8")
    check(
        "tileset_text",
        "tile_size = Vector2i(32, 32)" in tiles_tres
        and "texture_region_size = Vector2i(32, 32)" in tiles_tres
        and "7:1/0/terrain = 0" in tiles_tres
        and "0:2/animation_columns = 3" in tiles_tres
        and "/15/" not in tiles_tres
        and "terrains_peering_bit/right_side = 0" in tiles_tres
        and "0:2/0/physics_layer_0" not in tiles_tres
        and "Color(0.18, 0.55, 0.22, 1)" in tiles_tres
        and "Color(0.15, 0.38, 0.78, 1)" in tiles_tres
        and "Color(0.84, 0.75, 0.47, 1)" in tiles_tres
        and "Color(0.47, 0.32, 0.19, 1)" in tiles_tres
        and "Color(0.5, 0.5, 0.5, 1)" not in tiles_tres
        and "separation = Vector2i(1, 1)" in tiles_tres
        and 'path="res://sprite_sheet/tiles.extruded.png"' in tiles_tres
        and (ROOT / "sprite_sheet" / "tiles.extruded.png").is_file(),
        "32",
    )
    check("import_sidecar", digest in sidecar and "process/fix_alpha_border=false" in sidecar and "uid=" not in sidecar, digest)
    check("no_old_names", not (ROOT / "sprite_sheet" / "manifest.json").exists() and not (ROOT / "sprite_sheet" / "play.gd").exists() and not (ROOT / "loop.wav").exists(), "gone")
    check("no_loose_png", not list(ROOT.rglob("frame_*.png")), "0")
    play = (ROOT / "sprite_sheet" / "hero_sheet_stage.gd").read_text(encoding="utf-8")
    check(
        "stage_source",
        "@tool" not in play
        and "ProjectSettings" in play
        and "local_to_map" in play
        and "sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST" in play
        and "map.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST" in play
        and "snap=" not in play
        and "z_index = 1" in play
        and "foot_y - 1" in play
        and "while frame_acc" in play
        and "step = 1" not in play
        and "tile=" in play
        and "if not probe:" in play
        and play.count("quit(0)") == 1
        and "2000" not in play
        and "warn: a frame does not meet the ground." in play
        and '_fail("a frame does not meet the ground.' not in play
        and "The scene still plays. A floating frame is allowed." in play,
        "probe",
    )
    project_text = (ROOT / "project.godot").read_text(encoding="utf-8")
    check(
        "project_settings",
        'run/main_scene="res://sprite_sheet/hero_sheet_stage.tscn"' in project_text
        and "viewport_width=320" in project_text
        and 'scale_mode="integer"' in project_text
        and "snap_2d_transforms_to_pixel=true" in project_text
        and "snap_2d_vertices_to_pixel=true" in project_text,
        "stage 320",
    )
    query = C.english_search_query("スプライトシートを切って")
    check(
        "japanese_to_english",
        "sprite sheet" in query and "tileset" in query and "pixel art" in query and "2D" in query and not any("\u3040" <= ch <= "\u30ff" for ch in query),
        query,
    )

    pad_dir = Path("/tmp/ga_contract_extrude")
    fresh(pad_dir)
    (pad_dir / "sprite_sheet").mkdir()
    gap = Image.new("RGBA", (33, 16), (0, 0, 0, 0))
    gap_px = gap.load()
    for y in range(16):
        gap_px[15, y] = (9, 8, 7, 255)
        gap_px[17, y] = (1, 2, 3, 255)
    from PIL import PngImagePlugin

    gap_info = PngImagePlugin.PngInfo()
    gap_info.add_text("License", "CC0")
    gap.save(pad_dir / "sprite_sheet" / "gap.png", pnginfo=gap_info)
    gap_reply = C.slice_grid(
        pad_dir,
        "sprite_sheet/gap.png",
        16,
        16,
        kind="sprite",
        spacing=(1, 1),
        extrude_px=1,
        write=True,
        replace=True,
        foot=(0, 16),
    )
    after_gap = C.read_png(pad_dir / "sprite_sheet" / "gap.png")
    extruded_gap = C.read_png(pad_dir / "sprite_sheet" / "gap.extruded.png")
    copied = tuple(extruded_gap.pixels[16 * 4 : 16 * 4 + 4])
    source_gap = tuple(after_gap.pixels[16 * 4 : 16 * 4 + 4])
    check(
        "extrude_pixels",
        gap_reply["ok"]
        and gap_reply.get("extrude_px") == 1
        and copied == (9, 8, 7, 255)
        and source_gap != (9, 8, 7, 255)
        and after_gap.text.get("License") == "CC0"
        and any(item.endswith("gap.extruded.png") for item in gap_reply.get("paths", [])),
        str(copied),
    )
    check("extrude_keeps_mesh", "spriteExtrude: 0" in (pad_dir / "sprite_sheet" / "gap.png.meta").read_text(encoding="utf-8"), "0")
    blind = json.loads((SHIP / "queries_eval.json").read_text(encoding="utf-8"))
    expected_queries = [
        "pixel art sprite sheet cutter",
        "png to tileset splitter",
        "cut pixel art into game tiles",
        "sprite sheet from pixel png",
        "2d walk cycle sprite sheet",
        "tileset cutter for pixel art",
        "split png into sprite sheet",
        "shore tiles tileset tool",
        "pixel art walk cycle sheet",
        "png sprite and shore tiles",
    ]
    check("queries_eval", blind.get("queries") == expected_queries and "作る担当は10語を直していない" in blind.get("_note", ""), str(len(blind.get("queries", []))))
    plugin_yaml = (SHIP / "plugin.yaml").read_text(encoding="utf-8")
    desc_raw = plugin_yaml.split("description: >-\n", 1)[1].split("\nauthor:", 1)[0].strip()
    missed_queries = [item for item in expected_queries if item not in desc_raw]
    check("blind_in_description", not missed_queries and "pixel art" in desc_raw and desc_raw == disclosure, str(missed_queries or len(desc_raw)))
    check("pixel_hyphen", "pixel-art" in desc_raw and "Cuts a pixel-art png into frames." in desc_raw, "pixel-art")
    check(
        "catalog_name",
        "name: cut-sprite-sheet\n" in plugin_yaml
        and "cloudflare-web-search.yaml" < "cut-sprite-sheet.yaml" < "devin.yaml"
        and "cut-sprite-sheet.yaml" < "memory-zvec.yaml",
        "cut-sprite-sheet.yaml",
    )
    check(
        "design_sprite_id",
        "0800000000000000" in readme
        and "スプライト名の MD4 ではない" in DESIGN
        and "spriteID` はスプライト名の MD4" not in DESIGN,
        "suffix",
    )
    check("design_float", "地面に届かなければ終了コード 2" not in DESIGN, "warn")
    check(
        "stage_doc",
        "Every frame must meet that line." not in source_text
        and C.stage_script.__doc__ == "Side-view stage. The foot sits on the top edge of the tile. A floating frame warns and the scene still plays.",
        C.stage_script.__doc__ or "",
    )
    skill_text = (SHIP / "SKILL.md").read_text(encoding="utf-8")
    plugin_py = (SHIP / "__init__.py").read_text(encoding="utf-8")
    check("plugin_floor", 'requires_hermes: ">=0.21.6"' in plugin_yaml and "manifest_version: 2" in plugin_yaml, "0.21.6")
    place_first = "Place a walk cycle or shore tiles in the game."
    check(
        "skill_entry",
        INSPECT_FIRST in skill_text
        and SLICE_FIRST in skill_text
        and place_first in skill_text
        and place_first in DESIGN
        and len(place_first) <= 60
        and len(INSPECT_DESCRIPTION if False else INSPECT_FIRST) <= 60
        and "requires_toolsets" not in skill_text
        and "requires_tools" not in skill_text
        and "confirm" not in skill_text,
        "skill",
    )
    check("plugin_no_env", "os.environ" not in plugin_py and "getenv" not in plugin_py, "env")
    check("no_confirm_arg", "confirm" not in plugin_py, "approval screen")
    import importlib.util
    import types

    spec = importlib.util.spec_from_file_location("sprite_sheet_plugin", SHIP / "__init__.py")
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    check("desc_len", all(len(text) <= 1024 for text in (plugin.INSPECT_DESCRIPTION, plugin.SLICE_DESCRIPTION, plugin.PLACE_DESCRIPTION)), "1024")
    check("place_lead", plugin.PLACE_DESCRIPTION.startswith(place_first), plugin.PLACE_DESCRIPTION[:60])

    class Ctx:
        def __init__(self):
            self.tools = {}

        def register_tool(self, name, toolset, schema, handler):
            self.tools[name] = {"schema": schema, "handler": handler}

        def register_skill(self, name, path, description=""):
            self.skill = description

    ctx = Ctx()
    plugin.register(ctx)
    check("three_tools", set(ctx.tools) == {"inspect_grid", "slice_grid", "place_kit"}, str(set(ctx.tools)))
    check(
        "inspect_schema_optional_cell",
        ctx.tools["inspect_grid"]["schema"]["parameters"]["required"] == ["project", "path"]
        and ctx.tools["slice_grid"]["schema"]["parameters"]["required"] == ["project", "path", "cell_w", "cell_h"],
        str(ctx.tools["inspect_grid"]["schema"]["parameters"]["required"]),
    )
    check("schema_names", "names" in ctx.tools["slice_grid"]["schema"]["parameters"]["properties"] and "guid" in ctx.tools["slice_grid"]["schema"]["parameters"]["properties"] and "confirm" not in ctx.tools["slice_grid"]["schema"]["parameters"]["properties"], "schema")
    seen = plugin._args({"project": str(ROOT), "path": "sprite_sheet/hero_sheet.png", "cell_w": 16, "cell_h": 32})
    inspected = json.loads(ctx.tools["inspect_grid"]["handler"](seen))
    check("inspect_outside_hermes", inspected["ok"] and inspected["hframes"] == 4 and inspected.get("wrote") is not True, inspected.get("error", "ok"))
    suggested = json.loads(ctx.tools["inspect_grid"]["handler"]({"project": str(ROOT), "path": "sprite_sheet/hero_sheet.png"}))
    check(
        "inspect_omits_cell",
        suggested["ok"]
        and suggested.get("frame_count") == 0
        and suggested.get("suggest_cell_w") == 16
        and suggested.get("suggest_cell_h") == 32
        and suggested.get("wrote") is not True,
        str(suggested.get("suggest_cell_w")),
    )
    empty_dir = Path("/tmp/ga_contract_empty_cell")
    fresh(empty_dir)
    (empty_dir / "sprite_sheet").mkdir()
    Image.new("RGBA", (8, 8), (0, 0, 0, 0)).save(empty_dir / "sprite_sheet" / "blank.png")
    blank = C.inspect_grid(empty_dir, "sprite_sheet/blank.png")
    check(
        "inspect_no_body",
        blank["ok"] is False
        and blank["error"] == "no cell holds one body."
        and blank["next"] == "No single cell holds one body. Do not use 0x0."
        and blank.get("frame_count") == 0,
        blank.get("error", ""),
    )

    calls = []
    approval_context = types.ModuleType("tools.approval_context")
    approval_mod = types.ModuleType("tools.approval")
    prompt_mod = types.ModuleType("tools.approval_prompt")
    approval_context._is_cron_approval_context = lambda: False
    approval_context._get_approval_mode = lambda: "manual"
    approval_context._is_single_query_approval_context = lambda: False
    approval_context._is_unattended_platform_approval_context = lambda: False
    approval_mod._yolo_active = lambda: False

    def fake_prompt(command, description, timeout_seconds=None, allow_permanent=True, approval_callback=None, *, allow_session=True, smart_denied=False, title=None):
        calls.append({"line": command, "allow_permanent": allow_permanent, "allow_session": allow_session})
        return fake_prompt.choice

    fake_prompt.choice = "once"
    prompt_mod.prompt_dangerous_approval = fake_prompt
    sys.modules["tools.approval_context"] = approval_context
    sys.modules["tools.approval"] = approval_mod
    sys.modules["tools.approval_prompt"] = prompt_mod

    place_dir = Path("/tmp/ga_contract_place")
    fresh(place_dir)
    fake_prompt.choice = "once"
    placed = json.loads(ctx.tools["place_kit"]["handler"]({"project": str(place_dir), "path": "sprite_sheet/hero.png", "kind": "walk"}))
    check(
        "place_once",
        placed["ok"]
        and placed.get("wrote") is True
        and len(calls) == 1
        and calls[0]["allow_permanent"] is False
        and calls[0]["allow_session"] is False
        and calls[0]["line"] == placed["approval"]
        and "\n" not in placed["approval"]
        and "`" not in placed["approval"]
        and len(placed["approval"]) < 1500
        and "project.godot" in placed["approval"]
        and (place_dir / "sprite_sheet" / "hero.png").is_file()
        and (place_dir / "sprite_sheet" / "hero.spriteframes.tres").is_file()
        and (place_dir / "sprite_sheet" / "hero_tiles.tileset.tres").is_file()
        and (place_dir / "project.godot").is_file()
        and "snap_2d_transforms_to_pixel=true" in (place_dir / "project.godot").read_text(encoding="utf-8")
        and "hero_tiles.tileset.tres" in (place_dir / "sprite_sheet" / "hero_stage.gd").read_text(encoding="utf-8")
        and "9d1514134bc4fbd41bb739b1b9a49231" in (place_dir / "sprite_sheet" / "hero_tiles.grass.asset").read_text(encoding="utf-8")
        and "hero_tiles.extruded.png.meta" in placed["approval"]
        and "hero_tiles.png.meta" not in placed["approval"]
        and (place_dir / "sprite_sheet" / "hero_tiles.extruded.png.meta").is_file()
        and not (place_dir / "sprite_sheet" / "hero_tiles.png.meta").exists(),
        str(calls),
    )
    print(f"PLACE_APPROVAL chars={len(placed['approval'])} paths={len(placed['paths'])}")
    calls.clear()
    fake_prompt.choice = "deny"
    denied = json.loads(ctx.tools["place_kit"]["handler"]({"project": str(place_dir), "path": "sprite_sheet/denied_shore.png", "kind": "shore"}))
    check("place_deny", denied.get("wrote") is False and not (place_dir / "sprite_sheet" / "denied_shore.png").exists() and len(calls) == 1, denied.get("next", ""))
    calls.clear()
    approval_context._is_cron_approval_context = lambda: True
    croned = json.loads(ctx.tools["place_kit"]["handler"]({"project": str(place_dir), "path": "sprite_sheet/cron_shore.png", "kind": "shore"}))
    check("place_cron", croned["ok"] is False and "cron" in croned["error"] and not calls and not (place_dir / "sprite_sheet" / "cron_shore.png").exists(), croned["error"])
    approval_context._is_cron_approval_context = lambda: False
    music = json.loads(ctx.tools["place_kit"]["handler"]({"project": str(place_dir), "path": "sprite_sheet/song.png", "kind": "music"}))
    check("place_music", music["ok"] is False and music.get("wrote") is False and "not send audio" in music["next"], music.get("next", ""))

    foot_dir = Path("/tmp/ga_contract_foot")
    fresh(foot_dir)
    (foot_dir / "sprite_sheet").mkdir()
    cell16 = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    px16 = cell16.load()
    for x in range(16):
        px16[x, 15] = (9, 9, 9, 255)
    cell16.save(foot_dir / "sprite_sheet" / "cell16.png")
    from PIL import PngImagePlugin

    info = PngImagePlugin.PngInfo()
    info.add_text("License", "CC0")
    cell16.save(foot_dir / "sprite_sheet" / "cell16.png", pnginfo=info)
    before16 = (foot_dir / "sprite_sheet" / "cell16.png").read_bytes()
    foot16 = C.slice_grid(foot_dir, "sprite_sheet/cell16.png", 16, 16, kind="sprite", write=True)
    check(
        "foot_16",
        foot16["ok"]
        and foot16.get("wrote") is True
        and foot16.get("foot") == [8, 16]
        and (foot_dir / "sprite_sheet" / "cell16.spriteframes.tres").is_file()
        and (foot_dir / "sprite_sheet" / "cell16.png").read_bytes() == before16,
        str(foot16.get("foot")),
    )
    cell64 = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    px64 = cell64.load()
    for x in range(64):
        px64[x, 63] = (9, 9, 9, 255)
    cell64.save(foot_dir / "sprite_sheet" / "cell64.png", pnginfo=info)
    before64 = (foot_dir / "sprite_sheet" / "cell64.png").read_bytes()
    foot64 = C.slice_grid(foot_dir, "sprite_sheet/cell64.png", 64, 64, kind="sprite", write=True)
    check(
        "foot_64",
        foot64["ok"]
        and foot64.get("foot") == [32, 64]
        and foot64.get("wrote") is True
        and (foot_dir / "sprite_sheet" / "cell64.spriteframes.tres").is_file()
        and (foot_dir / "sprite_sheet" / "cell64.png").read_bytes() == before64,
        str(foot64.get("foot")),
    )

    rows = Image.new("RGBA", (8, 35), (0, 0, 0, 0))
    rpx = rows.load()
    for row in range(4):
        rpx[1, row * 9 + 1] = (200, 20, 20, 255)
    rows.save(foot_dir / "sprite_sheet" / "rows.png", pnginfo=info)
    attacked = C.slice_grid(
        foot_dir,
        "sprite_sheet/rows.png",
        8,
        8,
        kind="sprite",
        spacing=(0, 1),
        animation="attack",
        write=True,
        replace=True,
    )
    attack_tres = (foot_dir / "sprite_sheet" / "rows.spriteframes.tres").read_text(encoding="utf-8")
    check(
        "row_names",
        attacked["ok"]
        and attacked.get("wrote") is True
        and '&"attack"' in attack_tres
        and '&"attack_1"' in attack_tres
        and '&"attack_3"' in attack_tres
        and '&"default"' not in attack_tres
        and '&"walk"' not in attack_tres,
        attack_tres[attack_tres.find("animations"):],
    )
    skipped_gap = C.slice_grid(pad_dir, "sprite_sheet/gap.png", 16, 16, kind="sprite", spacing=(1, 1), write=False, replace=True)
    check("write_false_gap", skipped_gap["ok"] and skipped_gap.get("wrote") is False, str(skipped_gap.get("wrote")))

    one = struct.pack(">IIBBBBB", 32, 32, 8, 6, 0, 0, 0)
    varied = bytearray()
    for y in range(32):
        varied.append(0)
        for x in range(32):
            varied.extend((40, 80, 40, 255) if (x + y) % 3 else (10, 40, 20, 255))
    scan32 = zlib.compress(bytes(varied))

    def tiny_license(text: bytes, name: str) -> None:
        (foot_dir / "sprite_sheet" / name).write_bytes(
            b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", one) + png_chunk(b"tEXt", b"License\x00" + text) + png_chunk(b"IDAT", scan32) + png_chunk(b"IEND", b"")
        )

    tiny_license(b"not all rights reserved, CC0", "negated.png")
    negated = C.slice_grid(foot_dir, "sprite_sheet/negated.png", 32, 32, kind="tileset", tile_names=["grass"], tile_coords={"grass": [0, 0]}, write=True, replace=True)
    check("license_negated_cc0", negated["ok"] and negated.get("wrote") is True and negated.get("license") == "not all rights reserved, CC0", negated.get("error", ""))
    tiny_license(b"CC-BY-ND", "nd.png")
    nd = C.slice_grid(foot_dir, "sprite_sheet/nd.png", 32, 32, kind="tileset", tile_names=["grass"], tile_coords={"grass": [0, 0]}, write=True, replace=True)
    check("license_nd", nd["ok"] is False and nd["next"] == SAMPLES["license"]["next"] and "remove" not in nd["next"] and not (foot_dir / "sprite_sheet" / "nd.png.meta").exists(), nd.get("next", ""))
    decisions = {
        "smith": C.license_decision({"Copyright": "2024 Smith"}),
        "limited": C.license_decision({"License": "limited license"}),
        "not_pd": C.license_decision({"License": "not public domain"}),
        "trial": C.license_decision({"License": "Trial sheet drawn for this design. No third-party artwork."}),
        "sa30": C.license_decision({"License": "CC-BY-SA-3.0"}),
        "sa40": C.license_decision({"License": "CC BY-SA 4.0"}),
        "by40": C.license_decision({"License": "CC-BY 4.0"}),
        "by40hyphen": C.license_decision({"License": "CC-BY-4.0"}),
        "empty_copy": C.license_decision({"Copyright": "", "License": "CC0"}),
        "absent": C.license_decision({}),
        "ban": C.license_decision({"License": "無断転載禁止"}),
        "nd_word": C.license_decision({"License": "CC-BY-ND"}),
        "arr": C.license_decision({"License": "All Rights Reserved"}),
        "neg_arr": C.license_decision({"License": "not all rights reserved, CC0"}),
    }
    check(
        "license_words",
        decisions["smith"] == ("ok", "2024 Smith", C._UNKNOWN_WARNING)
        and decisions["limited"][2] == C._UNKNOWN_WARNING
        and decisions["not_pd"][2] == C._UNKNOWN_WARNING
        and decisions["trial"][2] == C._UNKNOWN_WARNING
        and decisions["sa30"] == ("ok", "CC-BY-SA-3.0", C._SHARE_WARNING)
        and decisions["sa40"] == ("ok", "CC BY-SA 4.0", C._SHARE_WARNING)
        and decisions["by40"] == ("ok", "CC-BY 4.0", "")
        and decisions["by40hyphen"] == ("ok", "CC-BY-4.0", "")
        and decisions["empty_copy"] == ("ok", "CC0", "")
        and decisions["absent"] == ("absent", "", "")
        and decisions["ban"][0] == "stop"
        and decisions["nd_word"][0] == "stop"
        and decisions["arr"][0] == "stop"
        and decisions["neg_arr"] == ("ok", "not all rights reserved, CC0", ""),
        str(decisions["smith"]),
    )
    (foot_dir / "sprite_sheet" / "ban.png").write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", one)
        + png_chunk(b"iTXt", b"License\x00\x00\x00\x00\x00" + "無断転載禁止".encode())
        + png_chunk(b"IDAT", scan32)
        + png_chunk(b"IEND", b"")
    )
    banned = C.slice_grid(foot_dir, "sprite_sheet/ban.png", 32, 32, kind="tileset", tile_names=["grass"], tile_coords={"grass": [0, 0]}, write=True, replace=True)
    check("license_ban", banned["ok"] is False and not (foot_dir / "sprite_sheet" / "ban.png.meta").exists(), banned.get("next", ""))
    (foot_dir / "sprite_sheet" / "absent.png").write_bytes(
        b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", one) + png_chunk(b"IDAT", scan32) + png_chunk(b"IEND", b"")
    )
    absent = C.slice_grid(foot_dir, "sprite_sheet/absent.png", 32, 32, kind="tileset", tile_names=["grass"], tile_coords={"grass": [0, 0]}, write=True, replace=True)
    check(
        "license_absent",
        absent["ok"] and absent.get("wrote") is True and "No rights are attached" in absent.get("next", "") and (foot_dir / "sprite_sheet" / "absent.png.meta").is_file(),
        absent.get("next", ""),
    )
    (foot_dir / "sprite_sheet" / "smith.png").write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", one)
        + png_chunk(b"tEXt", b"Copyright\x002024 Smith")
        + png_chunk(b"IDAT", scan32)
        + png_chunk(b"IEND", b"")
    )
    smith = C.slice_grid(foot_dir, "sprite_sheet/smith.png", 32, 32, kind="sprite", write=True, replace=True, foot=(16, 32))
    check(
        "license_smith",
        smith["ok"] and smith.get("wrote") is True and smith.get("license") == "2024 Smith" and "not a known free license" in smith.get("next", ""),
        smith.get("next", ""),
    )
    tiny_license(b"CC-BY-SA", "sa.png")
    sa = C.slice_grid(foot_dir, "sprite_sheet/sa.png", 32, 32, kind="tileset", tile_names=["grass"], tile_coords={"grass": [0, 0]}, write=True, replace=True)
    check(
        "license_sa",
        sa["ok"] is True
        and sa.get("wrote") is True
        and "Share-alike" in sa.get("next", "")
        and "CC-BY-SA" in str(sa.get("license"))
        and (foot_dir / "sprite_sheet" / "sa.tileset.tres").is_file(),
        sa.get("next", ""),
    )
    bare_anim = C.slice_grid(
        foot_dir,
        "sprite_sheet/negated.png",
        32,
        32,
        kind="tileset",
        tile_names=["water"],
        tile_coords={"water": [0, 0]},
        tile_anim={"water": {"fps": 4}},
        write=True,
        replace=True,
    )
    check("tile_anim_frames", bare_anim["ok"] is False and bare_anim["error"] == SAMPLES["tile_anim"]["error"] and bare_anim["next"] == SAMPLES["tile_anim"]["next"], bare_anim.get("error", ""))
    axis = Image.new("RGBA", (17, 8), (0, 0, 0, 0))
    apx = axis.load()
    for y in range(8):
        apx[7, y] = (9, 8, 7, 255)
        apx[9, y] = (1, 2, 3, 255)
    axis.save(foot_dir / "sprite_sheet" / "axis.png", pnginfo=info)
    before_axis = (foot_dir / "sprite_sheet" / "axis.png").read_bytes()
    axis_reply = C.slice_grid(foot_dir, "sprite_sheet/axis.png", 8, 8, kind="sprite", spacing=(1, 0), extrude_px=1, write=True, replace=True)
    axis_png = C.read_png(foot_dir / "sprite_sheet" / "axis.extruded.png")
    check(
        "extrude_one_axis",
        axis_reply["ok"]
        and axis_reply.get("extrude_px") == 1
        and (foot_dir / "sprite_sheet" / "axis.png").read_bytes() == before_axis
        and tuple(axis_png.pixels[8 * 4 : 8 * 4 + 4]) == (9, 8, 7, 255),
        str(axis_reply.get("extrude_px")),
    )
    plain = C.slice_grid(
        foot_dir,
        "sprite_sheet/negated.png",
        32,
        32,
        kind="tileset",
        tile_names=["grass", "water"],
        tile_coords={"grass": [0, 0], "water": [0, 0]},
        write=True,
        replace=True,
    )
    plain_tres = (foot_dir / "sprite_sheet" / "negated.tileset.tres").read_text(encoding="utf-8")
    plain_grass = (foot_dir / "sprite_sheet" / "negated.grass.asset").read_text(encoding="utf-8")
    plain_water = (foot_dir / "sprite_sheet" / "negated.water.asset").read_text(encoding="utf-8")
    check(
        "omitted_solid",
        plain["ok"]
        and "/15/" not in plain_tres
        and "0:0/0/physics_layer_0" in plain_tres
        and "m_ColliderType: 2" in plain_grass
        and "fileID: 13312" in plain_grass
        and "9d1514134bc4fbd41bb739b1b9a49231" not in plain_grass
        and "m_ColliderType: 0" in plain_water,
        "solid",
    )
    check("queries_still_present", json.loads((SHIP / "queries_eval.json").read_text(encoding="utf-8"))["queries"] == expected_queries, "10")

    touch_dir = Path("/tmp/ga_contract_touch")
    fresh(touch_dir)
    (touch_dir / "sprite_sheet").mkdir()
    touch = Image.new("RGBA", (64, 32), (0, 0, 0, 0))
    touch_px = touch.load()
    for y in range(32):
        for x in range(64):
            touch_px[x, y] = (20, 90, 30, 255)
    touch_info = PngImagePlugin.PngInfo()
    touch_info.add_text("License", "CC0")
    touch.save(touch_dir / "sprite_sheet" / "touch.png", pnginfo=touch_info)
    touch_before = (touch_dir / "sprite_sheet" / "touch.png").read_bytes()
    touch_reply = C.slice_grid(
        touch_dir,
        "sprite_sheet/touch.png",
        32,
        32,
        kind="tileset",
        tile_names=["grass", "sand"],
        tile_coords={"grass": [0, 0], "sand": [1, 0]},
        write=True,
        replace=True,
    )
    touch_tres = (touch_dir / "sprite_sheet" / "touch.tileset.tres").read_text(encoding="utf-8")
    touch_extruded = C.read_png(touch_dir / "sprite_sheet" / "touch.extruded.png")
    check(
        "expand_gap",
        touch_reply["ok"]
        and touch_reply.get("wrote") is True
        and (touch_dir / "sprite_sheet" / "touch.png").read_bytes() == touch_before
        and touch_extruded.size[0] == 65
        and "separation = Vector2i(1, 1)" in touch_tres
        and 'path="res://sprite_sheet/touch.extruded.png"' in touch_tres
        and (touch_dir / "sprite_sheet" / "touch.extruded.png.import").is_file(),
        str(touch_extruded.size),
    )
    glb_dir = Path("/tmp/ga_contract_glb")
    fresh(glb_dir)
    try:
        C.glb_bytes()
        glb_raised = False
    except RuntimeError as exc:
        glb_raised = str(exc) == "This plugin does not create a 3D model."
    glb_reply = C.place_kit(glb_dir, "props/crate.glb", kind="glb", write=True)
    sfx_reply = C.place_kit(glb_dir, "audio/step.wav", kind="sfx", write=True)
    check(
        "glb_not_a_model",
        glb_raised
        and glb_reply["ok"] is False
        and glb_reply.get("wrote") is False
        and glb_reply.get("paths") == []
        and glb_reply["error"] == "This plugin does not create a 3D model."
        and not (glb_dir / "props" / "crate.glb").exists()
        and sfx_reply["ok"] is False
        and sfx_reply.get("wrote") is False
        and sfx_reply.get("paths") == []
        and sfx_reply["error"] == "This plugin does not create a sound effect."
        and "not send audio" in sfx_reply["next"],
        glb_reply.get("error", ""),
    )

    if not Path(GODOT).exists():
        raise SystemExit(f"FAIL godot missing {GODOT}")
    for port in (8000, 9500):
        listened = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], capture_output=True, text=True)
        check(f"port_{port}", listened.returncode != 0, "free")

    home = Path("/tmp/ga_contract_home")
    work = Path("/tmp/ga_contract_proj")
    fresh(home)
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".godot"))
    for tres in work.glob("sprite_sheet/*.tres"):
        if tres.name.endswith(".tileset.tres"):
            continue
        tres.unlink()
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(home / "xdg")
    env["XDG_DATA_HOME"] = str(home / "data")
    project_bytes = (work / "project.godot").read_bytes()
    png_bytes = (work / "sprite_sheet" / "hero_sheet.png").read_bytes()
    tileset_path = work / "sprite_sheet" / "tiles.tileset.tres"
    tileset_bytes = tileset_path.read_bytes()
    tileset_path.unlink()

    code, out, sec = godot([GODOT, "--headless", "--path", str(work), "--", "--probe"], work, env, 12)
    err = lines_with(out, "error:")
    check("region_missing", code == 2 and err == [f"error: {SAMPLES['region_missing']['error']}"], f"exit={code} sec={sec:.3f} {err}")
    tileset_path.write_bytes(tileset_bytes)

    bare = Path("/tmp/ga_contract_bare")
    if bare.exists():
        shutil.rmtree(bare)
    shutil.copytree(work, bare, ignore=shutil.ignore_patterns("*.import", ".godot"))
    code, out, sec = godot([GODOT, "--headless", "--path", str(bare), "--", "--probe"], bare, env, 12)
    err = lines_with(out, "error:")
    check("no_sidecar_exit", code == 2 and err == [f"error: {SAMPLES['missing_import']['error']}"], f"exit={code} sec={sec:.3f} {err}")

    code, out, sec = godot([GODOT, "--headless", "--path", str(work), "--import", "--quit"], work, env, 150)
    check("import", code == 0, f"exit={code} sec={sec:.3f}")
    print(f"UX_IMPORT_SEC {sec:.3f}")
    alpha = (work / "sprite_sheet" / "hero_sheet.png.import").read_text(encoding="utf-8")
    check("alpha_stays_off", "process/fix_alpha_border=false" in alpha, "false")
    check("uid_after_import", C.sidecar_uid(alpha).startswith("uid://") or C.sidecar_uid(alpha) == "", C.sidecar_uid(alpha) or "none")
    check("png_unchanged", (work / "sprite_sheet" / "hero_sheet.png").read_bytes() == png_bytes, "bytes")
    check("project_untouched", (work / "project.godot").read_bytes() == project_bytes, "same bytes")

    code, out, sec = godot([GODOT, "--headless", "--path", str(work), "--script", str(work / "build.gd")], work, env, 30)
    check(
        "build",
        code == 0
        and "water_polys=0" in out
        and "anim_cols=3" in out
        and "peering_grass=0" in out
        and "TEXT_GRASS 9" in out
        and "distinct=" in out
        and "center=(7, 1)" in out
        and "TEXT_WATER atlas=(0, 2) frames=3" in out
        and "TERRAIN_ONE 1" in out
        and "TERRAIN_FILL 9" in out
        and "TILE_SIZE" in out
        and "(32, 32)" in out,
        f"exit={code} sec={sec:.3f}",
    )
    check("region_cell", "REGION 0 2 2 16 32" in out, "rect")
    check("duration0", "duration0=1" in out.replace(" ", ""), out[out.find("RELOAD"):out.find("RELOAD")+240] if "RELOAD" in out else out[-200:])
    print(f"UX_BUILD_SEC {sec:.3f}")

    nocache = Path("/tmp/ga_contract_nocache")
    if nocache.exists():
        shutil.rmtree(nocache)
    shutil.copytree(work, nocache, ignore=shutil.ignore_patterns(".godot", "__pycache__", "*.pyc"))
    code, out, sec = godot([GODOT, "--headless", "--path", str(nocache), "--", "--probe"], nocache, env, 12)
    err = lines_with(out, "error:")
    check("no_cache_exit", code == 2 and err == [f"error: {SAMPLES['import_without_cache']['error']}"], f"exit={code} sec={sec:.3f} {err}")

    code, out, sec = godot([GODOT, "--headless", "--path", str(work), "--", "--probe"], work, env, 15)
    play_lines = lines_with(out, "PLAY ")
    check("play_exit", code == 0 and len(play_lines) == 1, f"exit={code} sec={sec:.3f}")
    line = play_lines[0] if play_lines else ""
    print(f"PLAY_LINE {line}")
    print(f"UX_PROBE_SEC {sec:.3f}")
    check(
        "play_line",
        "frames_seen=" in line
        and "foot=160,90" in line
        and "water_frames=3" in line
        and "foot_px=" in line
        and int(line.split("foot_px=")[1].split()[0]) == 31
        and "changes=" in line
        and 2 <= int(line.split("changes=")[1].split()[0]) <= 24
        and int(line.split("frames_seen=")[1].split()[0]) >= 4
        and "tile=grass" in line
        and "nearest=true" in line
        and "filter=" not in line
        and "snap=" not in line
        and "foot_px=31" in DESIGN
        and "filter=0 snap=true,true" not in DESIGN,
        line,
    )
    found = line
    seen = 0
    if "frames_seen=" in found:
        seen = int(found.split("frames_seen=")[1].split()[0])
    check("frames_seen", seen >= 2, str(seen))

    authored = Path("/tmp/ga_contract_authored")
    if authored.exists():
        shutil.rmtree(authored)
    shutil.copytree(ROOT, authored, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".godot"))
    code, out, sec = godot([GODOT, "--headless", "--path", str(authored), "--import", "--quit"], authored, env, 150)
    check("authored_import", code == 0, f"exit={code} sec={sec:.3f}")
    authored_alpha = (authored / "sprite_sheet" / "hero_sheet.png.import").read_text(encoding="utf-8")
    check("authored_alpha", "process/fix_alpha_border=false" in authored_alpha, "false")
    code, out, sec = godot([GODOT, "--headless", "--path", str(authored), "--", "--probe"], authored, env, 15)
    authored_lines = lines_with(out, "PLAY ")
    authored_line = authored_lines[0] if authored_lines else ""
    print(f"AUTHORED_PLAY {authored_line}")
    check(
        "authored_play",
        code == 0
        and "foot=160,90" in authored_line
        and "water_frames=3" in authored_line
        and "foot_px=" in authored_line
        and int(authored_line.split("foot_px=")[1].split()[0]) == 31
        and 2 <= int(authored_line.split("changes=")[1].split()[0]) <= 24
        and int(authored_line.split("frames_seen=")[1].split()[0]) >= 4
        and "tile=grass" in authored_line
        and "cell=0" in authored_line
        and "nearest=true" in authored_line
        and "filter=" not in authored_line,
        f"exit={code} sec={sec:.3f} {authored_line or lines_with(out, 'error:')}",
    )
    authored_tres = (authored / "sprite_sheet" / "tiles.tileset.tres").read_text(encoding="utf-8")
    check("authored_tres_kept", "terrains_peering_bit/top_side" in authored_tres and "7:1/0/terrain = 0" in authored_tres and "/15/" not in authored_tres, "text")
    linear = Path("/tmp/ga_contract_linear")
    if linear.exists():
        shutil.rmtree(linear)
    shutil.copytree(work, linear)
    linear_project = (linear / "project.godot").read_text(encoding="utf-8").replace(
        "default_texture_filter=0",
        "default_texture_filter=1",
    )
    (linear / "project.godot").write_text(linear_project, encoding="utf-8")
    code, out, sec = godot([GODOT, "--headless", "--path", str(linear), "--", "--probe"], linear, env, 15)
    linear_lines = lines_with(out, "PLAY ")
    linear_line = linear_lines[0] if linear_lines else ""
    print(f"LINEAR_PLAY {linear_line}")
    check(
        "linear_project",
        code == 0 and "nearest=true" in linear_line and "foot=160,90" in linear_line and "water_frames=3" in linear_line and "filter=" not in linear_line,
        f"exit={code} sec={sec:.3f} {linear_line or lines_with(out, 'error:')}",
    )

    code, out, sec = godot([GODOT, "--headless", "--path", str(place_dir), "--import", "--quit"], place_dir, env, 150)
    check("place_import", code == 0, f"exit={code} sec={sec:.3f}")
    code, out, sec = godot([GODOT, "--headless", "--path", str(place_dir), "--", "--probe"], place_dir, env, 15)
    place_lines = lines_with(out, "PLAY ")
    place_line = place_lines[0] if place_lines else ""
    print(f"PLACE_PLAY {place_line}")
    check(
        "place_play",
        code == 0
        and "foot=160,90" in place_line
        and "foot_px=31" in place_line
        and "tile=grass" in place_line
        and "water_frames=3" in place_line
        and "frames_seen=" in place_line
        and int(place_line.split("frames_seen=")[1].split()[0]) >= 4
        and 2 <= int(place_line.split("changes=")[1].split()[0]) <= 24,
        f"exit={code} sec={sec:.3f} {place_line or lines_with(out, 'error:')}",
    )

    float_dir = Path("/tmp/ga_contract_float")
    fresh(float_dir)
    (float_dir / "sprite_sheet").mkdir()
    for tile_name in (
        "tiles.png",
        "tiles.png.import",
        "tiles.extruded.png",
        "tiles.extruded.png.import",
        "tiles.tileset.tres",
        "tiles.slice.json",
    ):
        shutil.copy(ROOT / "sprite_sheet" / tile_name, float_dir / "sprite_sheet" / tile_name)
    floating = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    for y in range(10, 32):
        floating.putpixel((4, y), (220, 40, 40, 255))
    floating.putpixel((20, 2), (220, 40, 40, 255))
    float_info = PngImagePlugin.PngInfo()
    float_info.add_text("License", "CC0")
    floating.save(float_dir / "sprite_sheet" / "float.png", pnginfo=float_info)
    floated = C.slice_grid(
        float_dir,
        "sprite_sheet/float.png",
        16,
        32,
        kind="sprite",
        foot=(8, 32),
        write=True,
        emit_scene=True,
        replace=True,
        tileset_rel="sprite_sheet/tiles.tileset.tres",
    )
    (float_dir / "project.godot").write_text(C.project_godot_text("sprite_sheet/float_stage.tscn"), encoding="utf-8")
    check("float_wrote", floated["ok"] and floated.get("wrote") is True and floated.get("foot") == [8, 32], floated.get("error", ""))
    code, out, sec = godot([GODOT, "--headless", "--path", str(float_dir), "--import", "--quit"], float_dir, env, 150)
    check("float_import", code == 0, f"exit={code} sec={sec:.3f}")
    code, out, sec = godot([GODOT, "--headless", "--path", str(float_dir), "--", "--probe"], float_dir, env, 15)
    float_err = lines_with(out, "error:")
    float_play = lines_with(out, "PLAY ")
    check(
        "float_ground",
        code == 0
        and float_err == []
        and len(float_play) == 1
        and "warn: a frame does not meet the ground." in out
        and SAMPLES["ground"]["next"] in out,
        f"exit={code} sec={sec:.3f} {float_play or float_err or out[-300:]}",
    )

    tamper = Path("/tmp/ga_contract_tamper")
    if tamper.exists():
        shutil.rmtree(tamper)
    shutil.copytree(work, tamper, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    slice_path = tamper / "sprite_sheet" / "hero_sheet.slice.json"
    if slice_path.is_file():
        tamper_doc = json.loads(slice_path.read_text(encoding="utf-8"))
    else:
        tamper_doc = {"foot": [8, 32]}
    tamper_doc["foot"] = [1000, 1000]
    slice_path.write_text(json.dumps(tamper_doc), encoding="utf-8")
    code, out, sec = godot([GODOT, "--headless", "--path", str(tamper), "--", "--probe"], tamper, env, 12)
    tamper_lines = lines_with(out, "PLAY ")
    check(
        "foot_tamper",
        code == 0 and len(tamper_lines) == 1 and "foot=160,90" in tamper_lines[0],
        f"exit={code} sec={sec:.3f} {tamper_lines or lines_with(out, 'error:')}",
    )
    def sprite_ids(meta: str) -> dict:
        found = {}
        name = None
        for line in meta.splitlines():
            if line.startswith("      name: "):
                name = line.split("name: ", 1)[1].strip()
            elif name and line.startswith("      internalID: "):
                found[name] = line.split("internalID: ", 1)[1].strip()
                name = None
        return found

    keep_dir = Path("/tmp/ga_contract_keep")
    fresh(keep_dir)
    (keep_dir / "sprite_sheet").mkdir()
    shutil.copy(ROOT / "sprite_sheet" / "hero_sheet.png", keep_dir / "sprite_sheet" / "hero_sheet.png")
    first_keep = C.slice_grid(keep_dir, "sprite_sheet/hero_sheet.png", 16, 32, kind="sprite", write=True)
    keep_meta = keep_dir / "sprite_sheet" / "hero_sheet.png.meta"
    before_meta = keep_meta.read_text(encoding="utf-8")
    ids_before = sprite_ids(before_meta)
    guid_before = before_meta.split("guid: ", 1)[1].splitlines()[0].strip()
    keep_meta.write_text(
        before_meta.replace(
            "      name: walk_0\n      rect:\n        serializedVersion: 2\n        x: 0\n        y: 0\n        width: 16\n        height: 32\n      alignment: 7\n      pivot: {x: 0.5, y: 0}\n      border: {x: 0, y: 0, z: 0, w: 0}",
            "      name: walk_0\n      rect:\n        serializedVersion: 2\n        x: 0\n        y: 0\n        width: 16\n        height: 32\n      alignment: 9\n      pivot: {x: 0.5, y: 0.1}\n      border: {x: 1, y: 2, z: 3, w: 4}",
            1,
        ),
        encoding="utf-8",
    )
    kept_reply = C.slice_grid(keep_dir, "sprite_sheet/hero_sheet.png", 16, 32, kind="sprite", write=True, replace=True)
    after_meta = keep_meta.read_text(encoding="utf-8")
    check(
        "replace_keeps_pivot",
        first_keep["ok"]
        and kept_reply["ok"]
        and kept_reply.get("wrote") is True
        and "pivot: {x: 0.5, y: 0.1}" in after_meta
        and "border: {x: 1, y: 2, z: 3, w: 4}" in after_meta
        and "name: walk_0" in after_meta
        and sprite_ids(after_meta) == ids_before
        and len(ids_before) == 4
        and after_meta.split("guid: ", 1)[1].splitlines()[0].strip() == guid_before
        and "lost walk_0" not in kept_reply.get("approval", "")
        and "\n" not in kept_reply.get("approval", ""),
        str(sprite_ids(after_meta)),
    )

    drop_dir = Path("/tmp/ga_contract_drop")
    fresh(drop_dir)
    (drop_dir / "sprite_sheet").mkdir()
    shutil.copy(ROOT / "sprite_sheet" / "hero_sheet.png", drop_dir / "sprite_sheet" / "hero_sheet.png")
    C.slice_grid(drop_dir, "sprite_sheet/hero_sheet.png", 16, 32, kind="sprite", write=True)
    drop_meta = drop_dir / "sprite_sheet" / "hero_sheet.png.meta"
    drop_before = drop_meta.read_text(encoding="utf-8")
    drop_meta.write_text(
        drop_before.replace(
            "      name: walk_3\n      rect:\n        serializedVersion: 2\n        x: 48\n        y: 0\n        width: 16\n        height: 32\n      alignment: 7\n      pivot: {x: 0.5, y: 0}\n      border: {x: 0, y: 0, z: 0, w: 0}",
            "      name: walk_3\n      rect:\n        serializedVersion: 2\n        x: 48\n        y: 0\n        width: 16\n        height: 32\n      alignment: 9\n      pivot: {x: 0.25, y: 0.75}\n      border: {x: 8, y: 7, z: 6, w: 5}",
            1,
        ),
        encoding="utf-8",
    )
    drop_reply = C.slice_grid(
        drop_dir,
        "sprite_sheet/hero_sheet.png",
        16,
        32,
        kind="sprite",
        columns=2,
        write=True,
        replace=True,
        dry_run=True,
    )
    drop_line = drop_reply.get("approval", "")
    check(
        "replace_names_lost_sprite",
        drop_reply["ok"]
        and drop_reply.get("wrote") is False
        and "walk_3" in drop_line
        and "pivot {x: 0.25, y: 0.75}" in drop_line
        and "border {x: 8, y: 7, z: 6, w: 5}" in drop_line
        and "alignment 9" in drop_line
        and "\n" not in drop_line
        and "`" not in drop_line
        and "pivot: {x: 0.25, y: 0.75}" in drop_meta.read_text(encoding="utf-8"),
        drop_line[-180:],
    )

    tres_dir = Path("/tmp/ga_contract_tres")
    fresh(tres_dir)
    (tres_dir / "sprite_sheet").mkdir()
    shutil.copy(ROOT / "sprite_sheet" / "hero_sheet.png", tres_dir / "sprite_sheet" / "hero_sheet.png")
    C.slice_grid(tres_dir, "sprite_sheet/hero_sheet.png", 16, 32, kind="sprite", write=True)
    tres_path = tres_dir / "sprite_sheet" / "hero_sheet.spriteframes.tres"
    tres_path.write_text(tres_path.read_text(encoding="utf-8").replace('"speed": 8.0', '"speed": 12.0', 1), encoding="utf-8")
    tres_reply = C.slice_grid(tres_dir, "sprite_sheet/hero_sheet.png", 16, 32, kind="sprite", write=True, replace=True, dry_run=True)
    tres_line = tres_reply.get("approval", "")
    check(
        "replace_names_lost_tres",
        tres_reply["ok"]
        and tres_reply.get("wrote") is False
        and "sprite_sheet/hero_sheet.spriteframes.tres" in tres_line
        and '"speed": 12.0' in tres_line
        and "\n" not in tres_line
        and "`" not in tres_line
        and '"speed": 12.0' in tres_path.read_text(encoding="utf-8"),
        tres_line[-180:],
    )
    tres_path.write_text(tres_path.read_text(encoding="utf-8") + "`hand`\n", encoding="utf-8")
    refused_drop = C.slice_grid(tres_dir, "sprite_sheet/hero_sheet.png", 16, 32, kind="sprite", write=True, replace=True)
    check(
        "replace_unnamed_writes_nothing",
        refused_drop["ok"] is False
        and refused_drop["error"] == SAMPLES["unnamed_drop"]["error"]
        and refused_drop["next"] == SAMPLES["unnamed_drop"]["next"]
        and refused_drop.get("wrote") is False
        and "`hand`" in tres_path.read_text(encoding="utf-8"),
        refused_drop.get("error", ""),
    )

    output_symlinks()
    overwrite_routes(ctx, calls, fake_prompt)
    output_atomic()

    check("no_godot_dir", not (ROOT / ".godot").exists() and not (SHIP / ".godot").exists(), "absent")
    for port in (8000, 9500):
        listened = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], capture_output=True, text=True)
        check(f"port_{port}_after", listened.returncode != 0, "free")
    print("ALL_PASS")


if __name__ == "__main__":
    main()
