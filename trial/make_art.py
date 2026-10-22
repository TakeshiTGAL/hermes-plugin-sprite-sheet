"""Draw the trial sheets. Pillow is only for this art."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, PngImagePlugin

import contract as C

FILL = (220, 40, 40, 255)
CLEAR = (0, 0, 0, 0)
HERO_GUID = "a11ce0000000000000000000000a0001"
PAD_GUID = "b22ce0000000000000000000000b0003"
TILE_GUID = "a11ce0000000000000000000000a0002"
LICENSE = "Trial sheet drawn for this design. No third-party artwork."


def _fill(mask: set[tuple[int, int]], x0: int, y0: int, x1: int, y1: int) -> None:
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            mask.add((x, y))


def _frame_masks() -> list[set[tuple[int, int]]]:
    frames: list[set[tuple[int, int]]] = []

    standing_left: set[tuple[int, int]] = set()
    _fill(standing_left, 5, 2, 10, 7)
    _fill(standing_left, 6, 8, 9, 15)
    _fill(standing_left, 4, 10, 6, 16)
    _fill(standing_left, 9, 9, 12, 13)
    _fill(standing_left, 4, 15, 6, 30)
    _fill(standing_left, 9, 15, 11, 23)
    _fill(standing_left, 4, 31, 11, 31)
    frames.append(standing_left)

    passing: set[tuple[int, int]] = set()
    _fill(passing, 5, 4, 10, 9)
    _fill(passing, 6, 10, 9, 17)
    _fill(passing, 2, 11, 6, 13)
    _fill(passing, 9, 11, 14, 13)
    _fill(passing, 6, 17, 9, 30)
    _fill(passing, 4, 31, 11, 31)
    frames.append(passing)

    standing_right: set[tuple[int, int]] = set()
    _fill(standing_right, 5, 2, 10, 7)
    _fill(standing_right, 6, 8, 9, 15)
    _fill(standing_right, 3, 9, 6, 13)
    _fill(standing_right, 9, 10, 12, 16)
    _fill(standing_right, 4, 15, 6, 30)
    _fill(standing_right, 9, 15, 11, 30)
    _fill(standing_right, 4, 31, 6, 31)
    _fill(standing_right, 9, 31, 11, 31)
    frames.append(standing_right)

    wide: set[tuple[int, int]] = set()
    _fill(wide, 5, 1, 10, 6)
    _fill(wide, 6, 7, 9, 14)
    _fill(wide, 2, 4, 6, 8)
    _fill(wide, 9, 4, 13, 8)
    _fill(wide, 2, 14, 6, 30)
    _fill(wide, 9, 14, 13, 30)
    frames.append(wide)
    return frames


def _paint(im: Image.Image, masks: list[set[tuple[int, int]]], origin: tuple[int, int], step: int) -> None:
    px = im.load()
    for index, mask in enumerate(masks):
        ox = origin[0] + index * step
        oy = origin[1]
        for x, y in mask:
            px[ox + x, oy + y] = FILL


def hero_image() -> Image.Image:
    im = Image.new("RGBA", (64, 32), CLEAR)
    _paint(im, _frame_masks(), (0, 0), 16)
    return im


def padded_image() -> Image.Image:
    im = Image.new("RGBA", (74, 36), CLEAR)
    _paint(im, _frame_masks(), (2, 2), 18)
    return im


def _paint_cell(px, ox: int, oy: int, painter) -> None:
    for y in range(32):
        for x in range(32):
            px[ox + x, oy + y] = painter(x, y)


def tiles_image() -> Image.Image:
    im = Image.new("RGBA", (128, 64), CLEAR)
    px = im.load()

    def grass(x, y):
        if y % 7 == 0 and x % 3 == 0:
            return (24, 100, 36, 255)
        return (46, 140, 52, 255)

    def water(band: int):
        def painter(x, y):
            if band <= y <= band + 2:
                return (180, 220, 240, 255)
            return (36, 96, 180, 255)

        return painter

    def sand(x, y):
        if x % 7 == 0 and y % 5 == 0:
            return (180, 150, 80, 255)
        return (214, 190, 120, 255)

    def path(x, y):
        if 12 <= x <= 19:
            return (168, 124, 78, 255)
        return (120, 82, 48, 255)

    _paint_cell(px, 0, 0, grass)
    _paint_cell(px, 32, 0, water(12))
    _paint_cell(px, 64, 0, water(8))
    _paint_cell(px, 96, 0, water(16))
    _paint_cell(px, 0, 32, sand)
    _paint_cell(px, 32, 32, path)
    return im


def _save(path: Path, image: Image.Image, source: str) -> None:
    info = PngImagePlugin.PngInfo()
    info.add_text("License", LICENSE)
    info.add_text("Source", source)
    image.save(path, pnginfo=info)


def write(root: Path) -> None:
    folder = root / "sprite_sheet"
    folder.mkdir(parents=True, exist_ok=True)
    for stale in (
        "hero_sheet.spriteframes.tres",
        "hero_sheet.png.meta",
        "hero_sheet.slice.json",
        "hero_sheet.extruded.png",
        "tiles.png.meta",
    ):
        path = folder / stale
        if path.is_file():
            path.unlink()
    (folder / "hero_sheet.png").write_bytes(C.encode_png(C.walk_raster(LICENSE)))
    (folder / "tiles.png").write_bytes(C.encode_png(C.shore_raster(LICENSE)))
    (folder / "padded_sheet.png").write_bytes(C.encode_png(C.padded_raster(LICENSE)))
    hero_png = C.read_png(folder / "hero_sheet.png")
    if hero_png.text.get("License") != LICENSE:
        raise SystemExit(f"license text missing {hero_png.text}")
    if C.lowest_opaque_y(hero_png, (0, 0, 16, 32)) != 31:
        raise SystemExit("foot row is not y=31")
    bodies = C.component_count(hero_png)
    if bodies != 4:
        raise SystemExit(f"hero components {bodies}")
    (folder / "hero_sheet.png.import").write_text(
        C.import_sidecar("sprite_sheet/hero_sheet.png", ""),
        encoding="utf-8",
    )
    hero_reply = C.slice_grid(
        root,
        "sprite_sheet/hero_sheet.png",
        16,
        32,
        kind="sprite",
        fps=8,
        durations=[1, 2, 1, 1],
        names=["walk_0", "walk_1", "walk_2", "walk_3"],
        write=True,
        animation="walk",
        emit_scene=True,
        guid=HERO_GUID,
        replace=True,
        tileset_rel="sprite_sheet/tiles.tileset.tres",
    )
    if not hero_reply["ok"] or hero_reply["frame_count"] != 4 or not hero_reply.get("wrote") or hero_reply["hframes"] != 4:
        raise SystemExit(json.dumps(hero_reply, ensure_ascii=False))
    for index in range(4):
        if C.lowest_opaque_y(hero_png, (index * 16, 0, 16, 32)) != 31:
            raise SystemExit(f"frame {index} does not meet y=31")
    pad_reply = C.slice_grid(
        root,
        "sprite_sheet/padded_sheet.png",
        16,
        32,
        kind="sprite",
        margin=(2, 2),
        spacing=(2, 2),
        fps=8,
        durations=[1, 2, 1, 1],
        names=["walk_0", "walk_1", "walk_2", "walk_3"],
        write=True,
        animation="walk",
        guid=PAD_GUID,
        replace=True,
    )
    if not pad_reply["ok"] or not pad_reply.get("wrote"):
        raise SystemExit(json.dumps(pad_reply, ensure_ascii=False))
    tiles_reply = C.slice_grid(
        root,
        "sprite_sheet/tiles.png",
        32,
        32,
        kind="tileset",
        extrude_px=0,
        tile_names=["grass", "water", "sand", "path"],
        tile_coords=C.shore_coords(),
        tile_anim={"water": {"frames": 3, "fps": 4}},
        tile_peering=C.shore_peering(),
        guid=TILE_GUID,
        replace=True,
    )
    if not tiles_reply["ok"]:
        raise SystemExit(json.dumps(tiles_reply, ensure_ascii=False))
    tiles_doc = json.loads((folder / "tiles.slice.json").read_text(encoding="utf-8"))
    if tiles_reply["frame_count"] != 24 or "foot" in tiles_doc or tiles_doc["tile_animation"]["water"]["columns"] != 3:
        raise SystemExit(f"tiles frames {tiles_reply['frame_count']}")
    if tiles_doc.get("file") != "sprite_sheet/tiles.extruded.png" or tiles_doc.get("spacing") != [1, 1]:
        raise SystemExit(f"tiles file {tiles_doc.get('file')} spacing {tiles_doc.get('spacing')}")
    if (folder / "tiles.png.meta").exists() or not (folder / "tiles.extruded.png.meta").is_file():
        raise SystemExit("tiles meta is not the extruded png")
    (folder / "hero_sheet_stage.gd").write_text(
        C.stage_script("sprite_sheet/", "hero_sheet", "sprite_sheet/tiles.tileset.tres", 4, 1, (8, 32), "walk", 8),
        encoding="utf-8",
    )
    (folder / "hero_sheet_stage.tscn").write_text(C._stage_tscn("sprite_sheet/", "hero_sheet"), encoding="utf-8")
    print(f"bodies={bodies} hero_frames={hero_reply['frame_count']} tiles_ok={tiles_reply['ok']}")
    print("HERO_NEXT " + hero_reply.get("next", ""))
    print("PAD_NEXT " + pad_reply.get("next", ""))


if __name__ == "__main__":
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    write(dest)
