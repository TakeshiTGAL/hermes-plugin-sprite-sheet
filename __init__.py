"""Sprite sheet, tileset, and local placement tools. They do not launch Godot or Unity."""

import importlib.util
import json
from pathlib import Path

INSPECT_DESCRIPTION = (
    "Read a sprite sheet or tileset png grid, frames, defects. "
    "Use it when a 2D game needs the width, height, frame count, and defects of a sprite sheet or a tileset png. "
    "Pixel art stays on this computer. It does not write files and does not launch Godot or Unity."
)
SLICE_DESCRIPTION = (
    "Cut and slice a sprite sheet or tileset png for 2D. "
    "Use it when a 2D game png needs a Godot SpriteFrames resource, a TileSet, or a Unity .meta. "
    "A tight grid with no margin and no spacing still gets SpriteFrames and a Unity Multiple slice. The png bytes stay. "
    "write false writes nothing. "
    "A write shows the project-relative paths once on the approval screen. "
    "A replace keeps a sprite's alignment, pivot, border, fileID, and guid when the name matches. "
    "It names text lines, meta values, and png byte counts it will drop, and writes nothing when it cannot name them. "
    "Pixel art stays on this computer. Does not launch Godot or Unity."
)
PLACE_DESCRIPTION = (
    "Place a walk cycle or shore tiles in the game. "
    "This plugin does not create a 3D model or a sound effect. "
    "walk also writes shore tiles under the feet and, when project.godot is missing, one project file with integer pixel snap. "
    "Pixels stay on this computer. Music and voice are not created and audio is not sent. "
    "A write shows the project-relative paths once on the approval screen. "
    "A replace names text lines, meta values, and png byte counts it will drop, and writes nothing when it cannot name them. "
    "Does not launch Godot or Unity."
)
_CONTRACT = None


def _contract():
    global _CONTRACT
    if _CONTRACT is None:
        path = Path(__file__).resolve().parent / "trial" / "contract.py"
        spec = importlib.util.spec_from_file_location("sprite_sheet_contract", path)
        if spec is None or spec.loader is None:
            raise ImportError(path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _CONTRACT = module
    return _CONTRACT


def _args(args):
    if not args:
        return {}
    if isinstance(args, str):
        loaded = json.loads(args)
        if not isinstance(loaded, dict):
            raise ValueError("arguments")
        return loaded
    if isinstance(args, dict):
        return args
    raise ValueError("arguments")


def _flag(args, key, default=False):
    if key not in args or args[key] is None:
        return default
    value = args[key]
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise ValueError(key)


def _optional_int(args, key):
    if key not in args or args[key] is None or args[key] == "":
        return None
    return int(args[key])


def _bad(key):
    name = str(key)[:80]
    return json.dumps(
        {
            "ok": False,
            "error": f"missing or invalid {name}.",
            "next": f"Pass {name} as described. Nothing was written.",
            "next_ja": f"{name} を直す。まだ書いていない。",
            "wrote": False,
            "paths": [],
        },
        ensure_ascii=False,
    )


def _session_block():
    """Refuse a write when nobody can approve it. Fail closed when the check cannot load."""
    try:
        approval_context = importlib.import_module("tools.approval_context")
        approval = importlib.import_module("tools.approval")
    except Exception:
        return "Could not check cron, yolo, or approvals, so nothing was written."
    try:
        if approval_context._is_cron_approval_context():
            return "Refused in cron. Nothing was written."
        if approval._yolo_active():
            return "Refused while yolo is on. Nothing was written."
        if approval_context._get_approval_mode() == "off":
            return "Refused while approvals are off. Nothing was written."
        if approval_context._is_single_query_approval_context():
            return "Refused in a single-query session. Nothing was written."
        if approval_context._is_unattended_platform_approval_context():
            return "Refused in an unattended session. Nothing was written."
    except Exception:
        return "Could not check cron, yolo, or approvals, so nothing was written."
    return ""


def _blocked_reply(reason):
    return json.dumps(
        {
            "ok": False,
            "error": reason,
            "next": "Use an attended chat with approvals on. Nothing was written.",
            "next_ja": "承認が聞ける会話で使う。まだ書いていない。",
            "wrote": False,
            "paths": [],
        },
        ensure_ascii=False,
    )


def _common(args):
    kind = str(args.get("kind") or "sprite")
    if kind not in ("sprite", "tileset"):
        raise ValueError("kind")
    origin = str(args.get("origin") or "top_left")
    if origin not in ("top_left", "bottom_left"):
        raise ValueError("origin")
    return {
        "project": Path(str(args["project"])),
        "rel": str(args["path"]),
        "cell_w": int(args["cell_w"]),
        "cell_h": int(args["cell_h"]),
        "margin": (int(args.get("margin_x") or 0), int(args.get("margin_y") or 0)),
        "spacing": (int(args.get("spacing_x") or 0), int(args.get("spacing_y") or 0)),
        "columns": _optional_int(args, "columns"),
        "origin": origin,
        "extrude_px": int(args.get("extrude_px") or 0),
        "kind": kind,
    }


def _coords(raw):
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("tile_coords")
    out = {}
    for name, pair in raw.items():
        out[str(name)] = (int(pair[0]), int(pair[1]))
    return out


def _peering(raw):
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("tile_peering")
    out = {}
    for name, bits in raw.items():
        if not isinstance(bits, dict):
            raise ValueError("tile_peering")
        parsed = {}
        for bit, pair in bits.items():
            parsed[int(bit)] = (int(pair[0]), int(pair[1]))
        out[str(name)] = parsed
    return out


def _names(raw):
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError("names")
    return [str(item) for item in raw]


def _foot(args):
    fx = args.get("foot_x")
    fy = args.get("foot_y")
    if fx is None and fy is None:
        return None
    return (-1 if fx is None else int(fx), -1 if fy is None else int(fy))


def register(ctx) -> None:
    contract = _contract()

    def _commit(preview, again):
        if not preview.get("ok") or not preview.get("approval"):
            return contract.dump_reply(preview)
        reason = _session_block()
        if reason:
            return _blocked_reply(reason)
        try:
            prompt = importlib.import_module("tools.approval_prompt")
        except Exception:
            return _blocked_reply("Could not check cron, yolo, or approvals, so nothing was written.")
        try:
            choice = prompt.prompt_dangerous_approval(
                preview["approval"],
                "cut-sprite-sheet",
                allow_permanent=False,
                allow_session=False,
            )
        except Exception:
            return _blocked_reply("Could not check cron, yolo, or approvals, so nothing was written.")
        if str(choice) != "once":
            preview = dict(preview)
            preview["wrote"] = False
            preview["next"] = "The approval was not accepted. Nothing was written."
            preview["next_ja"] = "承認されなかった。まだ書いていない。"
            return contract.dump_reply(preview)
        return contract.dump_reply(again())

    def _inspect(args, **_kwargs):
        try:
            payload = _args(args)
            if _optional_int(payload, "cell_w") is None or _optional_int(payload, "cell_h") is None:
                reply = contract.inspect_grid(Path(str(payload["project"])), str(payload["path"]))
            else:
                reply = contract.inspect_grid(**_common(payload))
        except (KeyError, ValueError, TypeError) as exc:
            return _bad(exc.args[0] if exc.args else "argument")
        return contract.dump_reply(reply)

    def _slice(args, **_kwargs):
        try:
            payload = _args(args)
            common = _common(payload)
            durations = payload.get("durations")
            if durations is not None:
                durations = [float(item) for item in durations]
            tile_names = payload.get("tile_names")
            if tile_names is not None:
                tile_names = [str(item) for item in tile_names]
            call = dict(
                common,
                fps=8 if payload.get("fps") is None else int(payload["fps"]),
                durations=durations,
                trim=_flag(payload, "trim"),
                foot=_foot(payload),
                names=_names(payload.get("names")),
                tile_names=tile_names,
                tile_coords=_coords(payload.get("tile_coords")),
                tile_solid=payload.get("tile_solid"),
                tile_anim=payload.get("tile_anim"),
                tile_peering=_peering(payload.get("tile_peering")),
                write=_flag(payload, "write", True),
                emit_scene=_flag(payload, "emit_scene", True),
                replace=_flag(payload, "replace"),
                animation=str(payload.get("animation") or "walk"),
                guid=str(payload.get("guid") or ""),
                ppu=_optional_int(payload, "ppu"),
                tileset_rel=str(payload.get("tileset_rel") or ""),
            )
            preview = contract.slice_grid(**call, dry_run=True)
        except (KeyError, ValueError, TypeError) as exc:
            return _bad(exc.args[0] if exc.args else "argument")
        return _commit(preview, lambda: contract.slice_grid(**call, dry_run=False))

    def _place(args, **_kwargs):
        try:
            payload = _args(args)
            kind = str(payload.get("kind") or "")
            if kind not in ("walk", "shore", "glb", "music", "voice", "sfx"):
                raise ValueError("kind")
            call = dict(
                project=Path(str(payload["project"])),
                rel=str(payload["path"]),
                kind=kind,
                write=_flag(payload, "write", True),
                replace=_flag(payload, "replace"),
            )
            preview = contract.place_kit(**call, dry_run=True)
        except (KeyError, ValueError, TypeError) as exc:
            return _bad(exc.args[0] if exc.args else "argument")
        return _commit(preview, lambda: contract.place_kit(**call, dry_run=False))

    grid = {
        "type": "object",
        "properties": {
            "project": {"type": "string", "description": "Directory of the 2D game project. The png path is relative to it."},
            "path": {"type": "string", "description": "Project-relative png, such as sprite_sheet/hero.png."},
            "cell_w": {"type": "integer", "description": "Cell width in pixels, from 1 to 4096. Omit on inspect_grid to get suggest_cell_w without cutting."},
            "cell_h": {"type": "integer", "description": "Cell height in pixels, from 1 to 4096. Omit on inspect_grid to get suggest_cell_h without cutting."},
            "margin_x": {"type": "integer", "description": "Left margin in pixels. Default 0."},
            "margin_y": {"type": "integer", "description": "Top margin in pixels. Default 0."},
            "spacing_x": {"type": "integer", "description": "Horizontal gap between cells in pixels. Default 0."},
            "spacing_y": {"type": "integer", "description": "Vertical gap between cells in pixels. Default 0."},
            "columns": {"type": "integer", "description": "How many columns to cut. Omit to use the whole grid."},
            "origin": {"type": "string", "enum": ["top_left", "bottom_left"], "description": "Where frame 0 starts. Default top_left."},
            "extrude_px": {"type": "integer", "enum": [0, 1], "description": "1 copies each cell edge into a separate png when spacing is at least 1. 0 leaves the png bytes."},
            "kind": {"type": "string", "enum": ["sprite", "tileset"], "description": "sprite cuts a character sheet. tileset cuts terrain."},
        },
        "required": ["project", "path"],
    }
    ctx.register_tool(
        name="inspect_grid",
        toolset="cut-sprite-sheet",
        schema={
            "name": "inspect_grid",
            "description": INSPECT_DESCRIPTION,
            "parameters": grid,
        },
        handler=_inspect,
    )
    slice_parameters = {
        "type": "object",
        "properties": dict(grid["properties"]),
        "required": ["project", "path", "cell_w", "cell_h"],
    }
    slice_parameters["properties"].update(
        {
            "fps": {"type": "integer", "description": "Playback speed from 1 to 60. Default 8."},
            "durations": {"type": "array", "items": {"type": "number"}, "description": "One duration per frame. Omit for 1 each."},
            "trim": {"type": "boolean", "description": "Cut each frame to its opaque pixels. Default false."},
            "foot_x": {"type": "integer", "description": "Foot column inside the frame. Omit to measure the center column."},
            "foot_y": {"type": "integer", "description": "One pixel past the opaque bottom, inside the cell. Omit to measure it."},
            "names": {"type": "array", "items": {"type": "string"}, "description": "Frame names. Default is the animation name plus the frame index."},
            "guid": {"type": "string", "description": "Unity texture guid. Omit to derive one from the png path."},
            "ppu": {"type": "integer", "description": "Pixels per unit. Omit to use the cell height."},
            "replace": {"type": "boolean", "description": "Overwrite files that already exist. Default false. Keeps a matching sprite's alignment, pivot, border, fileID, and guid, and names text lines, meta values, and png byte counts it will drop on the approval line."},
            "emit_scene": {"type": "boolean", "description": "Also write the stage scene. Default true."},
            "write": {"type": "boolean", "description": "False skips the files. Default true."},
            "animation": {"type": "string", "description": "Animation name for a sprite. Default walk. One name per row."},
            "tile_names": {"type": "array", "items": {"type": "string"}, "description": "Terrain names, in sheet order."},
            "tile_coords": {"type": "object", "description": "Terrain name to [column, row] on the sheet."},
            "tile_solid": {"type": "object", "description": "Terrain name to true when the tile blocks movement. Omitted water is false. Other omitted names are solid."},
            "tile_anim": {"type": "object", "description": "Terrain name to {frames, fps}. columns is optional and defaults to frames."},
            "tile_peering": {"type": "object", "description": "Terrain name to a neighbor bit, then [column, row] of that shore picture."},
            "tileset_rel": {"type": "string", "description": "Project-relative TileSet used by the stage scene."},
        }
    )
    ctx.register_tool(
        name="slice_grid",
        toolset="cut-sprite-sheet",
        schema={
            "name": "slice_grid",
            "description": SLICE_DESCRIPTION,
            "parameters": slice_parameters,
        },
        handler=_slice,
    )
    ctx.register_tool(
        name="place_kit",
        toolset="cut-sprite-sheet",
        schema={
            "name": "place_kit",
            "description": PLACE_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Directory of the game project."},
                    "path": {"type": "string", "description": "Project-relative output, such as sprite_sheet/hero.png."},
                    "kind": {
                        "type": "string",
                        "enum": ["walk", "shore"],
                        "description": "walk writes a 4-frame sheet and shore tiles. shore writes shore tiles. This plugin does not create a 3D model or a sound effect.",
                    },
                    "write": {"type": "boolean", "description": "False skips the files. Default true."},
                    "replace": {"type": "boolean", "description": "Overwrite files that already exist. Default false. Names text lines, meta values, and png byte counts it will drop on the approval line."},
                },
                "required": ["project", "path", "kind"],
            },
        },
        handler=_place,
    )
    ctx.register_skill(
        "cut-sprite-sheet",
        Path(__file__).resolve().parent / "SKILL.md",
        description=(
            "Cut a grid png into a sprite sheet or a tileset, or place a walk cycle or shore tiles, for a 2D game in Godot or Unity. "
            "tool_search in English for inspect_grid, slice_grid, or place_kit before using web_search."
        ),
    )
