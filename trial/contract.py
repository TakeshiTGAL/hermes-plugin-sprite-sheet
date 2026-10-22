"""Grid contract for a sprite sheet and a tileset. Standard library only."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
import struct
import zlib
from pathlib import Path

MAX_EDGE = 4096
MAX_FRAMES = 4096
APPROVAL_LIMIT = 1500
PPU = 32
CREDENTIAL_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "id_rsa.pub",
    "credentials",
    "credentials.json",
    "secrets.json",
    "password",
    "password.txt",
}
CREDENTIAL_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
RIGHTS = "Slicing copies rectangles and creates no new rights."


class PngError(Exception):
    def __init__(self, error: str, nxt: str, nxt_ja: str) -> None:
        super().__init__(error)
        self.error = error
        self.next = nxt
        self.next_ja = nxt_ja


class Raster:
    def __init__(self, width: int, height: int, pixels: bytearray, text: dict[str, str]) -> None:
        self.size = (width, height)
        self.pixels = pixels
        self.text = text

    def load(self):
        return _Pixels(self)


class _Pixels:
    def __init__(self, raster: Raster) -> None:
        self._raster = raster

    def __getitem__(self, xy: tuple[int, int]) -> tuple[int, int, int, int]:
        x, y = xy
        width = self._raster.size[0]
        i = (y * width + x) * 4
        raw = self._raster.pixels
        return raw[i], raw[i + 1], raw[i + 2], raw[i + 3]


def divisors(n: int) -> list[int]:
    if n < 1:
        return []
    return [i for i in range(1, n + 1) if n % i == 0]


def grid_shape(
    img_w: int,
    img_h: int,
    cell_w: int,
    cell_h: int,
    margin_x: int = 0,
    margin_y: int = 0,
    spacing_x: int = 0,
    spacing_y: int = 0,
) -> tuple[int, int] | None:
    """Godot atlas grid. Margin is the top-left only. A right or bottom remainder is not a frame."""
    if min(cell_w, cell_h, img_w, img_h) < 1:
        return None
    if min(margin_x, margin_y, spacing_x, spacing_y) < 0:
        return None
    step_w = cell_w + spacing_x
    step_h = cell_h + spacing_y
    if step_w < 1 or step_h < 1:
        return None
    if img_w < margin_x + cell_w or img_h < margin_y + cell_h:
        return None
    cols = (img_w - margin_x + spacing_x) // step_w
    rows = (img_h - margin_y + spacing_y) // step_h
    if cols < 1 or rows < 1:
        return None
    return cols, rows


def grid_rects(
    img_w: int,
    img_h: int,
    cell_w: int,
    cell_h: int,
    margin_x: int = 0,
    margin_y: int = 0,
    spacing_x: int = 0,
    spacing_y: int = 0,
    max_columns: int | None = None,
) -> tuple[int, int, list[tuple[int, int, int, int]]] | None:
    shape = grid_shape(img_w, img_h, cell_w, cell_h, margin_x, margin_y, spacing_x, spacing_y)
    if shape is None:
        return None
    cols, rows = shape
    if max_columns is not None:
        if max_columns < 1 or max_columns > cols:
            return None
        cols = max_columns
    if cols * rows > MAX_FRAMES:
        return None
    step_w = cell_w + spacing_x
    step_h = cell_h + spacing_y
    rects = []
    for row in range(rows):
        for col in range(cols):
            x = margin_x + col * step_w
            y = margin_y + row * step_h
            rects.append((x, y, cell_w, cell_h))
    return cols, rows, rects


def _opaque(px, x: int, y: int) -> bool:
    return px[x, y][3] > 0


def _walk(im, rect, labels: list[int] | None, width: int) -> list[int]:
    x0, y0, w, h = rect
    px = im.load()
    seen = bytearray(w * h)
    sizes: list[int] = []
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if seen[i] or not _opaque(px, x0 + x, y0 + y):
                continue
            stack = [(x, y)]
            seen[i] = 1
            count = 0
            mark = len(sizes)
            while stack:
                cx, cy = stack.pop()
                count += 1
                if labels is not None:
                    labels[(y0 + cy) * width + (x0 + cx)] = mark
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if nx < 0 or ny < 0 or nx >= w or ny >= h:
                        continue
                    j = ny * w + nx
                    if seen[j] or not _opaque(px, x0 + nx, y0 + ny):
                        continue
                    seen[j] = 1
                    stack.append((nx, ny))
            sizes.append(count)
    return sizes


def component_count(im) -> int:
    w, h = im.size
    return len(_walk(im, (0, 0, w, h), None, w))


def cell_component_sizes(im, rect) -> list[int]:
    return _walk(im, rect, None, im.size[0])


def _labels(im) -> list[int]:
    w, h = im.size
    labels = [-1] * (w * h)
    _walk(im, (0, 0, w, h), labels, w)
    return labels


def _fully_opaque(im, rect) -> bool:
    px = im.load()
    x, y, w, h = rect
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            if px[xx, yy][3] == 0:
                return False
    return True


def _crossings(px, labels, width: int, x: int, y: int, length: int, horizontal: bool) -> int:
    count = 0
    for i in range(length):
        if horizontal:
            lx, ly, rx, ry = x + i, y, x + i, y + 1
        else:
            lx, ly, rx, ry = x, y + i, x + 1, y + i
        if not _opaque(px, lx, ly) or not _opaque(px, rx, ry):
            continue
        if labels[ly * width + lx] == labels[ry * width + rx] and labels[ly * width + lx] != -1:
            count += 1
    return count


def split_line(im, rects) -> bool:
    """True when one body crosses a cell edge. A one-pixel arm or sword is a cut."""
    if len(rects) < 2:
        return False
    labels = _labels(im)
    width = im.size[0]
    px = im.load()
    by_origin = {(r[0], r[1]): r for r in rects}
    for x, y, w, h in rects:
        if _fully_opaque(im, (x, y, w, h)):
            continue
        right = by_origin.get((x + w, y))
        if right is not None and not _fully_opaque(im, right):
            if _crossings(px, labels, width, x + w - 1, y, h, False) >= 1:
                return True
        below = by_origin.get((x, y + h))
        if below is not None and not _fully_opaque(im, below):
            if _crossings(px, labels, width, x, y + h - 1, w, True) >= 1:
                return True
    return False


def masks_equal(im, rects) -> bool:
    if len(rects) < 2:
        return False
    px = im.load()
    alpha_seen = set()
    color_seen = set()
    any_transparent = False
    for x, y, w, h in rects:
        alpha_bits = []
        color_bits = []
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                r, g, b, a = px[xx, yy]
                opaque = a > 0
                alpha_bits.append(1 if opaque else 0)
                color_bits.append((r, g, b, a))
                if not opaque:
                    any_transparent = True
        alpha_seen.add(tuple(alpha_bits))
        color_seen.add(tuple(color_bits))
    if len(alpha_seen) != 1 or not any_transparent or len(color_seen) < 2:
        return False
    return True


def solid_cells(im, rects) -> bool:
    px = im.load()
    for x, y, w, h in rects:
        colors = set()
        flat = True
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                colors.add(px[xx, yy])
                if len(colors) > 1:
                    flat = False
                    break
            if not flat:
                break
        if flat and len(colors) == 1 and next(iter(colors))[3] == 255:
            return True
    return False


def transparent_rgb(im) -> bool:
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0 and (r or g or b):
                return True
    return False


def zero_transparent_rgb(im) -> int:
    if not isinstance(im, Raster):
        raise TypeError("zero_transparent_rgb expects a png raster")
    count = 0
    raw = im.pixels
    for i in range(0, len(raw), 4):
        if raw[i + 3] == 0 and (raw[i] or raw[i + 1] or raw[i + 2]):
            raw[i] = raw[i + 1] = raw[i + 2] = 0
            count += 1
    return count


def lowest_opaque_y(im, rect: tuple[int, int, int, int]) -> int:
    px = im.load()
    x, y, w, h = rect
    for yy in range(y + h - 1, y - 1, -1):
        for xx in range(x, x + w):
            if _opaque(px, xx, yy):
                return yy - y
    return -1


def suggest_cell(im) -> tuple[int, int]:
    """Largest divisor grid that keeps each body in its own cell. 0x0 only when none exists."""
    w, h = im.size
    components = component_count(im)
    if w < 1 or h < 1 or components < 1:
        return 0, 0
    best: tuple[tuple[int, int], int, int] | None = None
    for cell_w in divisors(w):
        for cell_h in divisors(h):
            grid = grid_rects(w, h, cell_w, cell_h)
            if grid is None:
                continue
            cols, rows, rects = grid
            if split_line(im, rects):
                continue
            occupied = 0
            multi = False
            for rect in rects:
                sizes = sorted(cell_component_sizes(im, rect), reverse=True)
                if not sizes:
                    continue
                occupied += 1
                if len(sizes) >= 2 and sizes[1] * 4 >= sizes[0]:
                    multi = True
                    break
            if multi or occupied != components:
                continue
            rank = (cols * rows - occupied, -(cell_w * cell_h))
            if best is None or rank < best[0]:
                best = (rank, cell_w, cell_h)
    if best is None:
        return 0, 0
    return best[1], best[2]


def _base_reply(source: str, as_of: int, w: int, h: int, cell_w: int, cell_h: int) -> dict:
    return {
        "ok": False,
        "error": "",
        "next": "",
        "next_ja": "",
        "truncated": False,
        "total": 0,
        "source": source,
        "as_of": as_of,
        "width": w,
        "height": h,
        "cell_w": cell_w,
        "cell_h": cell_h,
        "columns": 0,
        "rows": 0,
        "frame_count": 0,
        "hframes": 0,
        "vframes": 0,
        "defects": [],
        "width_divisors": [],
        "height_divisors": [],
        "suggest_cell_w": 0,
        "suggest_cell_h": 0,
        "extrude_px": 0,
        "paths": [],
    }


def _order_rects(rects, cols: int, rows: int, origin: str):
    if origin != "bottom_left" or rows < 2:
        return rects
    ordered = []
    for row in range(rows - 1, -1, -1):
        ordered.extend(rects[row * cols : (row + 1) * cols])
    return ordered


def remainder_opaque(im, cell_w: int, cell_h: int, margin, spacing, cols: int, rows: int) -> int:
    """Opaque pixels in the right or bottom strip that did not fit a cell."""
    w, h = im.size
    end_x = margin[0] + cols * (cell_w + spacing[0]) - spacing[0]
    end_y = margin[1] + rows * (cell_h + spacing[1]) - spacing[1]
    px = im.load()
    count = 0
    for y in range(h):
        for x in range(w):
            if (x >= end_x or y >= end_y) and _opaque(px, x, y):
                count += 1
    return count


def inspect_image(
    im,
    cell_w: int,
    cell_h: int,
    margin=(0, 0),
    spacing=(0, 0),
    source: str = "",
    as_of: int = 0,
    columns: int | None = None,
    origin: str = "top_left",
    extrude_px: int = 0,
    kind: str = "sprite",
) -> dict:
    w, h = im.size
    reply = _base_reply(source, as_of, w, h, cell_w, cell_h)
    if origin not in ("top_left", "bottom_left"):
        reply["error"] = "origin must be top_left or bottom_left."
        reply["next"] = "Pass top_left or bottom_left."
        reply["next_ja"] = "origin は top_left か bottom_left。"
        return reply
    if extrude_px not in (0, 1):
        reply["error"] = "extrude_px must be 0 or 1."
        reply["next"] = "Pass extrude_px 0 or 1."
        reply["next_ja"] = "extrude_px は 0 か 1。"
        return reply
    if w > MAX_EDGE or h > MAX_EDGE:
        reply["error"] = f"image edge exceeds {MAX_EDGE}."
        reply["next"] = f"Use a png whose width and height are at most {MAX_EDGE}."
        reply["next_ja"] = f"幅と高さは {MAX_EDGE} 以下の png にする。"
        return reply
    shape = grid_shape(w, h, cell_w, cell_h, margin[0], margin[1], spacing[0], spacing[1])
    if shape is None:
        reply["defects"].append("indivisible")
        reply["width_divisors"] = divisors(max(0, w - margin[0]))
        reply["height_divisors"] = divisors(max(0, h - margin[1]))
        wd = ", ".join(str(n) for n in reply["width_divisors"])
        hd = ", ".join(str(n) for n in reply["height_divisors"])
        reply["error"] = f"cell {cell_w}x{cell_h} does not divide image {w}x{h}."
        reply["next"] = f"Width divisors: {wd}. Height divisors: {hd}."
        reply["next_ja"] = f"幅の約数は {wd}。高さの約数は {hd}。"
        return reply
    full_cols, rows = shape
    if columns is not None and (columns < 1 or columns > full_cols):
        reply["columns"] = full_cols
        reply["rows"] = rows
        reply["total"] = full_cols * rows
        reply["frame_count"] = reply["total"]
        reply["error"] = f"columns {columns} does not match the sheet ({full_cols})."
        reply["next"] = f"Pass columns {full_cols}, or omit columns."
        reply["next_ja"] = f"列数は {full_cols}。columns を省いてもよい。"
        return reply
    cols = columns if columns is not None else full_cols
    total = cols * rows
    reply["columns"] = cols
    reply["rows"] = rows
    reply["total"] = total
    if margin == (0, 0) and spacing == (0, 0):
        reply["hframes"] = cols
        reply["vframes"] = rows
    if total > MAX_FRAMES:
        reply["truncated"] = True
        reply["frame_count"] = 0
        reply["error"] = f"frame count exceeds {MAX_FRAMES}."
        reply["next"] = "Use a larger cell. total is the full frame count. Nothing was written."
        reply["next_ja"] = f"フレームが {MAX_FRAMES} を超えた。セルを大きくする。total が全枚数。まだ書いていない。"
        return reply
    grid = grid_rects(w, h, cell_w, cell_h, margin[0], margin[1], spacing[0], spacing[1], cols)
    if grid is None:
        reply["error"] = "grid check failed."
        reply["next"] = "Pass a cell that divides the png."
        reply["next_ja"] = "png を割り切るセルを渡す。"
        return reply
    _cols, _rows, rects = grid
    rects = _order_rects(rects, cols, rows, origin)
    reply["frame_count"] = len(rects)
    hard = []
    warnings = []
    if split_line(im, rects):
        if kind == "tileset":
            warnings.append("tile_edge")
        else:
            hard.append("split_line")
    for rect in rects:
        sizes = sorted(cell_component_sizes(im, rect), reverse=True)
        if len(sizes) >= 2 and sizes[1] * 4 >= sizes[0]:
            hard.append("multi_body")
            break
        if len(sizes) >= 2:
            warnings.append("loose_part")
    if masks_equal(im, rects):
        warnings.append("same_mask")
    if solid_cells(im, rects):
        warnings.append("solid_cell")
    if transparent_rgb(im):
        warnings.append("transparent_rgb")
    applied = extrude_px
    if extrude_px > 0 and spacing[0] < 1 and spacing[1] < 1:
        applied = 0
        warnings.append("extrude_clamped")
    reply["extrude_px"] = applied
    reply["defects"] = hard + warnings
    sw, sh = suggest_cell(im) if hard else (0, 0)
    reply["suggest_cell_w"] = sw
    reply["suggest_cell_h"] = sh
    if hard:
        if "split_line" in hard and sw and sh:
            reply["error"] = f"cell {cell_w}x{cell_h} cuts a sprite body."
            reply["next"] = f"Cover each body with cell_w {sw} and cell_h {sh}."
            reply["next_ja"] = f"体を割らないセルは幅 {sw}、高さ {sh}。"
        elif "split_line" in hard:
            wd = ", ".join(str(n) for n in divisors(w))
            reply["error"] = f"cell {cell_w}x{cell_h} cuts a sprite body."
            reply["next"] = f"The body is cut, and no other cell size was found. Width divisors: {wd}. Do not use 0x0."
            reply["next_ja"] = f"体が割れている。幅の約数は {wd}。0x0 は使わない。"
        elif "multi_body" in hard and sw and sh:
            reply["error"] = f"cell {cell_w}x{cell_h} holds more than one body."
            reply["next"] = f"Cover each body with cell_w {sw} and cell_h {sh}."
            reply["next_ja"] = f"1マスに体が2つある。幅 {sw}、高さ {sh}。"
        else:
            reply["error"] = f"cell {cell_w}x{cell_h} holds more than one body."
            reply["next"] = "Use a cell that holds one body. Do not use 0x0."
            reply["next_ja"] = "体が1つのセルにする。0x0 は使わない。"
        reply["ok"] = False
        return reply
    outside = remainder_opaque(im, cell_w, cell_h, margin, spacing, full_cols, rows)
    if outside:
        wd = ", ".join(str(n) for n in divisors(w))
        reply["error"] = f"cell {cell_w}x{cell_h} leaves {outside} opaque pixels outside the grid."
        reply["next"] = f"Crop the sheet or pick a cell that covers those pixels. Width divisors: {wd}."
        reply["next_ja"] = f"格子の外に不透明画素が {outside} ある。シートを切るか、画素を覆うセルにする。幅の約数は {wd}。"
        reply["ok"] = False
        return reply
    notes = []
    notes_ja = []
    if "same_mask" in warnings:
        notes.append("Masks match, so this is a color swap. The frames are still cut.")
        notes_ja.append("形が同じなので色の差し替え。コマはそのまま切る。")
    if "solid_cell" in warnings:
        notes.append("A cell is one flat color. The cell is still cut.")
        notes_ja.append("セルが単色。セルはそのまま切る。")
    if "transparent_rgb" in warnings:
        notes.append("Zero the RGB of transparent pixels, or write the sheet with this defect. Keep fix_alpha_border off.")
        notes_ja.append("透過画素の RGB を 0 にするか、この欠陥のまま書く。fix_alpha_border はオフのままにする。")
    if "loose_part" in warnings:
        notes.append("A small separate part is in the cell. The frame is still cut.")
        notes_ja.append("セルに小さい別部品がある。コマはそのまま切る。")
    if "tile_edge" in warnings:
        notes.append(
            f"Edge contact is normal for a tileset. Add 1px spacing, or cut these cells at {cell_w}x{cell_h}."
        )
        notes_ja.append(f"タイルは縁で接してよい。間隔を 1px 足すか、この {cell_w}x{cell_h} で切る。")
    if "extrude_clamped" in warnings:
        notes.append("extrude_px is 0 because spacing is 0.")
        notes_ja.append("間隔が 0 なので押し出しは 0。")
    if any(margin) or any(spacing):
        notes.append(
            f"Margin is {margin[0]},{margin[1]} and spacing is {spacing[0]},{spacing[1]}. hframes ignores margin, so use the slice."
        )
        notes_ja.append(
            f"余白は {margin[0]},{margin[1]}、間隔は {spacing[0]},{spacing[1]}。hframes は余白を見ないので、slice を使う。"
        )
    elif not notes and reply["hframes"]:
        notes.append(f"No margin and no spacing. Set hframes to {cols} and vframes to {rows}.")
        notes_ja.append(f"余白も間隔も無い。hframes を {cols}、vframes を {rows} にする。")
    reply["ok"] = True
    reply["error"] = ""
    reply["next"] = " ".join(notes)
    reply["next_ja"] = "".join(notes_ja)
    if "Nearest" not in reply["next"]:
        reply["next"] = (reply["next"] + " " if reply["next"] else "") + "Set the node's texture filter to Nearest."
        reply["next_ja"] = reply["next_ja"] + "ノードの texture filter を Nearest にする。"
    return reply


def _refuse(error: str, nxt: str, nxt_ja: str, source: str) -> dict:
    reply = _base_reply(source, 0, 0, 0, 0, 0)
    reply["error"] = error
    reply["next"] = nxt
    reply["next_ja"] = nxt_ja
    return reply


def is_credential_name(name: str) -> bool:
    """Refuse the credential stem too. id_rsa.png is still id_rsa."""
    low = name.lower()
    stem = Path(low).stem.lower()
    if low in CREDENTIAL_NAMES or stem in CREDENTIAL_NAMES:
        return True
    if low.startswith(".env.") or stem.startswith(".env"):
        return True
    if Path(low).suffix in CREDENTIAL_SUFFIXES or Path(stem).suffix in CREDENTIAL_SUFFIXES:
        return True
    return False


def resolve_png(project: Path, rel: str, must_exist: bool = True) -> tuple[Path | None, dict | None]:
    if not rel or rel.startswith("/") or "\\" in rel:
        return None, _refuse(
            "refusing a path outside the project.",
            "Pass a regular png inside the project.",
            "プロジェクトの中の普通の png を渡す。",
            rel,
        )
    parts = Path(rel).parts
    if any(part in ("", ".", "..") for part in parts):
        return None, _refuse(
            "refusing a path outside the project.",
            "Pass a regular png inside the project.",
            "プロジェクトの中の普通の png を渡す。",
            rel,
        )
    cur = project
    for part in parts:
        cur = cur / part
        if cur.is_symlink():
            return None, _refuse(
                "refusing a symlink.",
                "Pass a regular png inside the project.",
                "シンボリックリンクは拒否した。プロジェクトの中の普通の png を渡す。",
                rel,
            )
    if is_credential_name(cur.name):
        return None, _refuse(
            "refusing a credential file.",
            "Pass the sprite sheet png, not a credential file.",
            "資格情報のファイルは読まない。スプライトシートの png を渡す。",
            rel,
        )
    if cur.suffix.lower() != ".png":
        return None, _refuse(
            "refusing a file that is not a png.",
            "Pass a .png file. Other files are not read.",
            "png 以外は読まない。",
            rel,
        )
    if not cur.is_file():
        if cur.exists() or must_exist:
            return None, _refuse(
                "png not found.",
                "Pass a regular png inside the project.",
                "プロジェクトの中の普通の png を渡す。",
                rel,
            )
        return cur, None
    try:
        cur.resolve().relative_to(project.resolve())
    except ValueError:
        return None, _refuse(
            "refusing a path outside the project.",
            "Pass a regular png inside the project.",
            "プロジェクトの中の普通の png を渡す。",
            rel,
        )
    return cur, None


def inspect_grid(
    project: Path,
    rel: str,
    cell_w: int | None = None,
    cell_h: int | None = None,
    margin=(0, 0),
    spacing=(0, 0),
    columns: int | None = None,
    origin: str = "top_left",
    extrude_px: int = 0,
    kind: str = "sprite",
) -> dict:
    path, err = resolve_png(project, rel)
    if err:
        return err
    try:
        raster = read_png(path)
    except PngError as exc:
        return _refuse(exc.error, exc.next, exc.next_ja, rel)
    except Exception:
        return _refuse(
            "png did not parse.",
            "Pass a png file. The bytes were not read as an image.",
            "png として読めなかった。png のファイルを渡す。",
            rel,
        )
    if cell_w is None or cell_h is None:
        sw, sh = suggest_cell(raster)
        reply = _base_reply(rel, int(path.stat().st_mtime), raster.size[0], raster.size[1], int(sw), int(sh))
        reply["ok"] = bool(sw and sh)
        reply["suggest_cell_w"] = int(sw)
        reply["suggest_cell_h"] = int(sh)
        reply["frame_count"] = 0
        if sw and sh:
            reply["error"] = ""
            reply["next"] = (
                f"Suggested cell is {sw} by {sh}. Pass cell_w and cell_h to cut. "
                "Set the node's texture filter to Nearest."
            )
            reply["next_ja"] = (
                f"提案は幅 {sw}、高さ {sh}。切るときは cell_w と cell_h を渡す。"
                "ノードの texture filter を Nearest にする。"
            )
        else:
            reply["error"] = "no cell holds one body."
            reply["next"] = "No single cell holds one body. Do not use 0x0."
            reply["next_ja"] = "体が1つに収まるセルが無い。0x0 は使わない。"
        return reply
    return inspect_image(
        raster,
        cell_w,
        cell_h,
        margin,
        spacing,
        source=rel,
        as_of=int(path.stat().st_mtime),
        columns=columns,
        origin=origin,
        extrude_px=extrude_px,
        kind=kind,
    )


def import_sidecar(rel: str, uid: str = "") -> str:
    res = "res://" + rel
    digest = hashlib.md5(res.encode("utf-8")).hexdigest()
    stem = Path(rel).name
    dest = f"res://.godot/imported/{stem}-{digest}.ctex"
    uid_line = f'uid="{uid}"\n' if uid.startswith("uid://") else ""
    return (
        "[remap]\n\n"
        'importer="texture"\n'
        'type="CompressedTexture2D"\n'
        f"{uid_line}"
        f'path="{dest}"\n'
        "metadata={\n"
        '"vram_texture": false\n'
        "}\n\n"
        "[deps]\n\n"
        f'source_file="{res}"\n'
        f'dest_files=["{dest}"]\n\n'
        "[params]\n\n"
        "compress/mode=0\n"
        "compress/high_quality=false\n"
        "compress/lossy_quality=0.7\n"
        "compress/uastc_level=0\n"
        "compress/rdo_quality_loss=0.0\n"
        "compress/hdr_compression=1\n"
        "compress/normal_map=0\n"
        "compress/channel_pack=0\n"
        "mipmaps/generate=false\n"
        "mipmaps/limit=-1\n"
        "roughness/mode=0\n"
        'roughness/src_normal=""\n'
        "process/channel_remap/red=0\n"
        "process/channel_remap/green=1\n"
        "process/channel_remap/blue=2\n"
        "process/channel_remap/alpha=3\n"
        "process/fix_alpha_border=false\n"
        "process/premult_alpha=false\n"
        "process/normal_map_invert_y=false\n"
        "process/hdr_as_srgb=false\n"
        "process/hdr_clamp_exposure=false\n"
        "process/size_limit=0\n"
        "detect_3d/compress_to=1\n"
    )


def _prefix(rel: str) -> tuple[str, str]:
    path = Path(rel)
    parent = path.parent.as_posix()
    base = "" if parent == "." else parent + "/"
    return base, path.stem


def output_paths(rel: str, kind: str, emit_scene: bool = False, tile_names: list[str] | None = None) -> list[str]:
    base, stem = _prefix(rel)
    paths: list[str] = []
    if kind == "sprite":
        paths.append(f"{base}{stem}.spriteframes.tres")
    elif kind == "tileset":
        paths.append(f"{base}{stem}.tileset.tres")
    else:
        raise ValueError(kind)
    paths.extend(
        [
            f"{base}{stem}.png.meta",
            f"{base}{stem}.png.import",
            f"{base}{stem}.slice.json",
        ]
    )
    if kind == "tileset":
        for name in tile_names or []:
            paths.append(f"{base}{stem}.{name}.asset")
            paths.append(f"{base}{stem}.{name}.asset.meta")
    if emit_scene and kind == "sprite":
        paths.append(f"{base}{stem}_stage.gd")
        paths.append(f"{base}{stem}_stage.tscn")
    return paths


def writes_files(kind: str, margin, spacing, write: bool, emit_scene: bool, durations) -> bool:
    """write false creates no file. A tight sprite still gets SpriteFrames and a Unity slice."""
    del emit_scene, durations, margin, spacing
    if not write:
        return False
    return kind in ("sprite", "tileset")


def approval_text(paths: list[str], replace: bool = False) -> tuple[str, str]:
    for path in paths:
        if "\n" in path or "`" in path or path.startswith("/") or ".." in Path(path).parts:
            raise ValueError(path)
    body = " ".join(paths)
    if replace:
        body = "replace " + body
    if "\n" in body or "`" in body:
        return "", "refuse"
    if len(body) > APPROVAL_LIMIT:
        return "", "manifest"
    return body, "inline"


def _sprite_identity(name: str) -> tuple[str, int]:
    """spriteID uses the 6000.6.6f1 suffix. It is not the MD4 hex of the name.

    Unity 6000.6.6f1 on macOS kept this fileID after the editor was closed and opened again.
    """
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    sprite_id = digest[:8].hex() + "0800000000000000"
    internal = int.from_bytes(digest[8:16], "little", signed=True) or 1
    return sprite_id, internal


def sidecar_uid(text: str) -> str:
    """The uid Godot left in an import sidecar. A value we invent before import is not one."""
    for line in text.splitlines():
        if line.startswith("uid="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def sprite_adjustments(text: str) -> dict | None:
    """Per-sprite alignment, pivot, and border, keyed by name.

    None means the text has sprite fields this parser cannot name. Unity uses a custom
    pivot only when alignment is 9, so the three fields stay together.
    """
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line == "    sprites:":
            start = index + 1
            break
    if start is None:
        if any(line.startswith("      name: ") for line in lines):
            return None
        return {}
    found: dict = {}
    current: dict | None = None

    def finish(sprite: dict | None) -> bool:
        if sprite is None:
            return True
        if not all(sprite.get(key) for key in ("name", "alignment", "pivot", "border")):
            return False
        if sprite["name"] in found:
            return False
        found[sprite["name"]] = {
            "alignment": sprite["alignment"],
            "pivot": sprite["pivot"],
            "border": sprite["border"],
            "internal_id": sprite.get("internal_id", ""),
            "sprite_id": sprite.get("sprite_id", ""),
        }
        return True

    for line in lines[start:]:
        if line[:4] == "    " and not line.startswith("      ") and not line.startswith("    - "):
            break
        if line.startswith("    - "):
            if not finish(current):
                return None
            current = {"name": "", "alignment": "", "pivot": "", "border": "", "internal_id": "", "sprite_id": ""}
            continue
        if current is None:
            continue
        if line.startswith("      name: "):
            current["name"] = line.split("name: ", 1)[1].strip()
        elif line.startswith("      alignment: "):
            current["alignment"] = line.split("alignment: ", 1)[1].strip()
        elif line.startswith("      pivot: "):
            current["pivot"] = line.split("pivot: ", 1)[1].strip()
        elif line.startswith("      border: "):
            current["border"] = line.split("border: ", 1)[1].strip()
        elif line.startswith("      internalID: "):
            current["internal_id"] = line.split("internalID: ", 1)[1].strip()
        elif line.startswith("      spriteID: "):
            current["sprite_id"] = line.split("spriteID: ", 1)[1].strip()
    if not finish(current):
        return None
    return found


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _meta_keep(path: Path, new_names: list[str]) -> tuple[dict, list, bool]:
    """Keep name-matched sprite fields. The third value is false when they cannot be named."""
    if not path.is_file():
        return {}, [], True
    text = _read_text(path)
    if text is None:
        return {}, [], False
    parsed = sprite_adjustments(text)
    if parsed is None:
        return {}, [], False
    wanted = set(new_names)
    kept = {name: fields for name, fields in parsed.items() if name in wanted}
    lost = [(name, fields) for name, fields in parsed.items() if name not in wanted]
    return kept, lost, True


def _dropped_lines(old: str, new: str) -> list[str] | None:
    """Lines in old that new does not keep. None when a dropped line contains a backtick."""
    left: dict[str, int] = {}
    for line in new.splitlines():
        stripped = line.strip()
        if stripped:
            left[stripped] = left.get(stripped, 0) + 1
    dropped = []
    for line in old.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if left.get(stripped, 0):
            left[stripped] -= 1
            continue
        if "`" in stripped or "\n" in stripped or "\r" in stripped:
            return None
        dropped.append(stripped)
    return dropped


def _tres_drop(path: Path, rel: str, new_text: str) -> tuple[list, bool]:
    if not path.is_file():
        return [], True
    old = _read_text(path)
    if old is None:
        return [], False
    dropped = _dropped_lines(old, new_text)
    if dropped is None:
        return [], False
    if not dropped:
        return [], True
    return [(rel, dropped)], True


def _drop_clause(sprites: list, tres_parts: list) -> str | None:
    """One line naming values a replace will not keep. None when that line cannot be said."""
    parts = []
    for name, fields in sprites:
        file_id = fields.get("internal_id") or ""
        ident = f" fileID {file_id}" if file_id else ""
        piece = (
            f"lost {name} alignment {fields['alignment']} "
            f"pivot {fields['pivot']} border {fields['border']}{ident}"
        )
        if "`" in piece or "\n" in piece or "\r" in piece:
            return None
        parts.append(piece)
    for rel, lines in tres_parts:
        piece = "lost " + rel + " " + " | ".join(lines)
        if "`" in piece or "\n" in piece or "\r" in piece:
            return None
        parts.append(piece)
    clause = " ".join(parts)
    if "`" in clause or "\n" in clause:
        return None
    return clause


def _guid_line(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("guid: "):
            return line.split("guid: ", 1)[1].strip()
    return ""


def _carried_guid(path: Path) -> str:
    if not path.is_file():
        return ""
    text = _read_text(path)
    if not text:
        return ""
    return _guid_line(text)


def _meta_lines_for_diff(text: str, omit_names: set[str]) -> list[str]:
    """Drop sprite blocks and id-table rows for names already named in the compact clause."""
    lines = text.splitlines()
    kept: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line == "  - first:" and index + 2 < len(lines) and lines[index + 2].startswith("    second: "):
            name = lines[index + 2].split("second: ", 1)[1].strip()
            if name in omit_names:
                index += 3
                continue
        if line.startswith("      ") and not line.startswith("       "):
            key, _, rest = line.strip().partition(":")
            if key in omit_names and rest.strip().lstrip("-").isdigit():
                index += 1
                continue
        if line.startswith("    - serializedVersion:"):
            block = [line]
            index += 1
            while index < len(lines) and (
                lines[index].startswith("      ") or lines[index].startswith("        ")
            ):
                block.append(lines[index])
                index += 1
            name = ""
            for item in block:
                if item.startswith("      name: "):
                    name = item.split("name: ", 1)[1].strip()
            if name not in omit_names:
                kept.extend(block)
            continue
        kept.append(line)
        index += 1
    return kept


def _text_loss(rel: str, old: str, new: str) -> str | None:
    dropped = _dropped_lines(old, new)
    if dropped is None:
        return None
    if not dropped:
        return ""
    piece = "lost " + rel + " " + " | ".join(dropped)
    if "`" in piece or "\n" in piece or "\r" in piece:
        return None
    return piece


def _meta_loss(path: Path, rel: str, new_text: str) -> str | None:
    """Values a .meta replace cannot carry. None when those values cannot be named."""
    old = _read_text(path)
    if old is None:
        return None
    if "    sprites:" in old or "    sprites:" in new_text:
        parsed = sprite_adjustments(old)
        if parsed is None:
            return None
        new_parsed = sprite_adjustments(new_text)
        if new_parsed is None:
            return None
        lost = [(name, fields) for name, fields in parsed.items() if name not in new_parsed]
        omit = {name for name, _fields in lost}
        extra = _dropped_lines(
            "\n".join(_meta_lines_for_diff(old, omit)),
            "\n".join(_meta_lines_for_diff(new_text, omit)),
        )
        if extra is None:
            return None
        return _drop_clause(lost, [(rel, extra)] if extra else [])
    return _text_loss(rel, old, new_text)


def _binary_loss(rel: str, old: bytes, new: bytes) -> str | None:
    piece = (
        f"lost {rel} bytes {len(old)} {len(new)} "
        f"sha256 {hashlib.sha256(old).hexdigest()} {hashlib.sha256(new).hexdigest()}"
    )
    if "`" in piece or "\n" in piece or "\r" in piece:
        return None
    return piece


def _one_loss(project: Path, rel: str, new: str | bytes | None) -> str | None:
    """What one existing file would lose. Empty when the file is absent or nothing changes.
    None when the loss cannot be shown.
    """
    path = project / rel
    if not path.exists():
        return ""
    if not path.is_file():
        return None
    if new is None:
        if rel.lower().endswith(".png"):
            try:
                return _binary_loss(rel, path.read_bytes(), b"")
            except OSError:
                return None
        if rel.endswith(".meta"):
            return _meta_loss(path, rel, "")
        old = _read_text(path)
        if old is None:
            try:
                return _binary_loss(rel, path.read_bytes(), b"")
            except OSError:
                return None
        return _text_loss(rel, old, "")
    if isinstance(new, bytes) or rel.lower().endswith(".png"):
        try:
            old_bytes = path.read_bytes()
        except OSError:
            return None
        new_bytes = new if isinstance(new, bytes) else new.encode("utf-8")
        return _binary_loss(rel, old_bytes, new_bytes)
    if rel.endswith(".meta"):
        return _meta_loss(path, rel, new)
    old_text = _read_text(path)
    if old_text is None:
        return None
    return _text_loss(rel, old_text, new)


def _fit_approval(body: str, clause: str | None) -> str | None:
    if clause is None:
        return None
    if not clause:
        return body
    named = body + " " + clause
    if "\n" in named or "`" in named or "\r" in named or len(named) > APPROVAL_LIMIT:
        return None
    return named


def _symlink_component(project: Path, rel: str) -> str | None:
    """Project-relative path of a symlink at rel or a parent inside the project."""
    parts = Path(rel).parts
    for index in range(len(parts)):
        if project.joinpath(*parts[: index + 1]).is_symlink():
            return Path(*parts[: index + 1]).as_posix()
    return None


def _output_block(project: Path, rel: str) -> str | None:
    """Error when an output, or a parent up to the project root, is a symlink.

    The resolved path is checked again so a link cannot point outside the project.
    """
    parts = Path(rel).parts
    if (
        not rel
        or rel.startswith("/")
        or "\\" in rel
        or any(part in ("", ".", "..") for part in parts)
    ):
        return f"refusing a path outside the project: {rel or '.'}."
    linked = _symlink_component(project, rel)
    if linked:
        return f"refusing a symlink: {linked}."
    try:
        (project / rel).resolve().relative_to(project.resolve())
    except (OSError, ValueError, RuntimeError):
        return f"refusing a path outside the project: {rel}."
    return None


def _planned_block(project: Path, planned: list[tuple[str, str | bytes | None]]) -> str:
    for rel, _new in planned:
        blocked = _output_block(project, rel)
        if blocked:
            return blocked
    return ""


_HARD_LINK_CUT = "外の名前とつながったハードリンクを切る"
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _rel_parts(rel: str) -> tuple[str, ...] | None:
    """One safe relative path. `..`, `.`, and a separator cannot leave the project."""
    if not rel or rel.startswith("/") or "\\" in rel or "\x00" in rel:
        return None
    parts = Path(rel).parts
    if not parts or any(part in ("", ".", "..") or "/" in part or "\\" in part or "\x00" in part for part in parts):
        return None
    return parts


def _hardlink_note(project: Path, rel: str) -> str:
    """Name a regular file that has another directory entry. Symlinks are not counted."""
    path = project / rel
    try:
        info = path.lstat()
    except OSError:
        return ""
    if stat.S_ISREG(info.st_mode) and info.st_nlink >= 2:
        return _HARD_LINK_CUT
    return ""


def _close_all(fds: list[int]) -> None:
    for fd in reversed(fds):
        try:
            os.close(fd)
        except OSError:
            pass


def _open_child(parent_fd: int, name: str) -> tuple[int | None, str]:
    """Open one existing directory. macOS returns ENOTDIR, not ELOOP, for a symlink."""
    try:
        return os.open(name, _DIR_FLAGS, dir_fd=parent_fd), ""
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            return None, "missing"
        try:
            info = os.lstat(name, dir_fd=parent_fd)
        except OSError:
            return None, "error"
        if stat.S_ISLNK(info.st_mode):
            return None, "symlink"
        return None, "error"


def _ensure_dir(parent_fd: int, name: str) -> tuple[int | None, str]:
    fd, kind = _open_child(parent_fd, name)
    if kind != "missing":
        return fd, kind
    try:
        os.mkdir(name, dir_fd=parent_fd)
    except FileExistsError:
        pass
    except OSError:
        return None, "error"
    return _open_child(parent_fd, name)


def _open_parent(project: Path, rel: str) -> tuple[int | None, list[int], str]:
    """Re-open each parent from the project root. The returned fds must be closed."""
    parts = _rel_parts(rel)
    opened: list[int] = []
    if parts is None:
        return None, opened, f"refusing a path outside the project: {rel or '.'}."
    root = os.open(project, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    opened.append(root)
    current = root
    walked: list[str] = []
    for part in parts[:-1]:
        walked.append(part)
        shown = Path(*walked).as_posix()
        fd, kind = _ensure_dir(current, part)
        if kind == "symlink":
            return None, opened, f"refusing a symlink: {shown}."
        if fd is None:
            return None, opened, f"refusing a path outside the project: {rel}."
        opened.append(fd)
        current = fd
    return current, opened, ""


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        wrote = os.write(fd, view)
        if wrote <= 0:
            raise OSError("short write")
        view = view[wrote:]


def _place_new(parent_fd: int, name: str, data: bytes) -> None:
    """Write a new file in parent_fd, then replace the name. A crash leaves the old name."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    label = name if len(name) <= 80 else "out"
    fd = -1
    tmp = ""
    for _attempt in range(4):
        tmp = f".rewrite.{label}.{os.getpid()}.{os.urandom(8).hex()}.tmp"
        try:
            fd = os.open(tmp, flags, 0o666, dir_fd=parent_fd)
            break
        except FileExistsError:
            fd = -1
    if fd < 0:
        raise OSError("temporary file exists")
    try:
        _write_all(fd, data)
    except Exception:
        os.close(fd)
        os.unlink(tmp, dir_fd=parent_fd)
        raise
    os.close(fd)
    try:
        os.replace(tmp, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
    except Exception:
        try:
            os.unlink(tmp, dir_fd=parent_fd)
        except OSError:
            pass
        raise


def rewrite_files(project: Path, planned: list[tuple[str, str | bytes | None]], dry_run: bool) -> tuple[str | None, str]:
    """The only rewrite of an existing project file.

    Returns the loss clause and an error. A set error means nothing was written.
    A symlink at an output, or in a parent directory inside the project, is an error
    at dry_run and again immediately before a write. The resolved path must stay
    inside the project. None for the clause means that loss cannot be shown.
    Each write is a temporary file in the parent directory opened with O_NOFOLLOW,
    then os.replace on that directory fd. An existing hard link is detached.
    """
    blocked = _planned_block(project, planned)
    if blocked:
        return None, blocked
    parts: list[str] = []
    for rel, new in planned:
        one = _one_loss(project, rel, new)
        if one is None:
            return None, ""
        note = _hardlink_note(project, rel)
        if note:
            one = (one + " " + note).strip() if one else note
        if one:
            parts.append(one)
    clause = " ".join(parts)
    if "`" in clause or "\n" in clause or "\r" in clause:
        return None, ""
    if clause and len(clause) > APPROVAL_LIMIT:
        return None, ""
    if dry_run:
        return clause, ""
    for rel, new in planned:
        blocked = _output_block(project, rel)
        if blocked:
            return None, blocked
        if _rel_parts(rel) is None:
            return None, f"refusing a path outside the project: {rel or '.'}."
        parent_fd, fds, err = _open_parent(project, rel)
        try:
            if err or parent_fd is None:
                return None, err or f"refusing a path outside the project: {rel}."
            name = Path(rel).name
            if name in ("", ".", "..") or "/" in name or "\\" in name or "\x00" in name:
                return None, f"refusing a path outside the project: {rel}."
            try:
                info = os.lstat(name, dir_fd=parent_fd)
            except FileNotFoundError:
                info = None
            if info is not None and stat.S_ISLNK(info.st_mode):
                return None, f"refusing a symlink: {rel}."
            if new is None:
                if info is not None and stat.S_ISREG(info.st_mode):
                    os.unlink(name, dir_fd=parent_fd)
                continue
            data = new if isinstance(new, bytes) else new.encode("utf-8")
            try:
                _place_new(parent_fd, name, data)
            except Exception:
                return None, f"refusing a partial write: {rel}."
        finally:
            _close_all(fds)
    return clause, ""


def unity_meta(
    name_rects: list[tuple[str, int, int, int, int]],
    image_h: int,
    guid: str,
    ppu: int = PPU,
    extrude_px: int = 0,
    center_pivot: bool = False,
    pivots: list | None = None,
    kept: dict | None = None,
) -> str:
    """TextureImporter fields. spriteExtrude stays 0: it is mesh margin, not texel padding."""
    del extrude_px
    sprites = []
    table = []
    id_rows = []
    default_alignment = 0 if center_pivot else 7
    default_pivot = "{x: 0.5, y: 0.5}" if center_pivot else "{x: 0.5, y: 0}"
    for index, (name, x, top, w, h) in enumerate(name_rects):
        sprite_id, internal = _sprite_identity(f"{guid}:{name}")
        unity_y = image_h - (top + h)
        alignment = default_alignment
        pivot = default_pivot
        border = "{x: 0, y: 0, z: 0, w: 0}"
        saved = (kept or {}).get(name)
        if saved:
            alignment = saved["alignment"]
            pivot = saved["pivot"]
            border = saved["border"]
            if saved.get("sprite_id"):
                sprite_id = saved["sprite_id"]
            if saved.get("internal_id"):
                try:
                    internal = int(saved["internal_id"])
                except ValueError:
                    pass
        elif pivots and index < len(pivots) and pivots[index] is not None:
            px, py = pivots[index]
            alignment = 9
            pivot = "{x: " + f"{float(px):.4f}" + ", y: " + f"{float(py):.4f}" + "}"
        table.append(f"      {name}: {internal}")
        id_rows.append(f"  - first:\n      213: {internal}\n    second: {name}")
        sprites.append(
            "\n".join(
                [
                    "    - serializedVersion: 2",
                    f"      name: {name}",
                    "      rect:",
                    "        serializedVersion: 2",
                    f"        x: {x}",
                    f"        y: {unity_y}",
                    f"        width: {w}",
                    f"        height: {h}",
                    f"      alignment: {alignment}",
                    f"      pivot: {pivot}",
                    f"      border: {border}",
                    "      outline: []",
                    "      physicsShape: []",
                    "      tessellationDetail: 0",
                    "      bones: []",
                    f"      spriteID: {sprite_id}",
                    f"      internalID: {internal}",
                    "      vertices: []",
                    "      indices: ",
                    "      edges: []",
                    "      weights: []",
                ]
            )
        )
    sheet_id, _sheet_internal = _sprite_identity(guid)
    body = "\n".join(sprites)
    names = "\n".join(table)
    id_table = "\n".join(id_rows) if id_rows else "[]"
    id_key = f"  internalIDToNameTable:\n{id_table}" if id_rows else "  internalIDToNameTable: []"
    return (
        "fileFormatVersion: 2\n"
        f"guid: {guid}\n"
        "TextureImporter:\n"
        f"{id_key}\n"
        "  externalObjects: {}\n"
        "  serializedVersion: 11\n"
        "  mipmaps:\n"
        "    mipMapMode: 0\n"
        "    enableMipMap: 0\n"
        "    sRGBTexture: 1\n"
        "  isReadable: 0\n"
        "  textureSettings:\n"
        "    serializedVersion: 2\n"
        "    filterMode: 0\n"
        "    aniso: 1\n"
        "    mipBias: 0\n"
        "    wrapU: 1\n"
        "    wrapV: 1\n"
        "    wrapW: 1\n"
        "  spriteMode: 2\n"
        "  spriteExtrude: 0\n"
        "  spriteMeshType: 0\n"
        f"  alignment: {default_alignment}\n"
        f"  spritePivot: {default_pivot}\n"
        f"  spritePixelsToUnits: {ppu}\n"
        "  spriteBorder: {x: 0, y: 0, z: 0, w: 0}\n"
        "  spriteGenerateFallbackPhysicsShape: 0\n"
        "  alphaUsage: 1\n"
        "  alphaIsTransparency: 0\n"
        "  textureType: 8\n"
        "  textureShape: 1\n"
        "  platformSettings:\n"
        "  - serializedVersion: 3\n"
        "    buildTarget: DefaultTexturePlatform\n"
        "    maxTextureSize: 4096\n"
        "    textureFormat: -1\n"
        "    textureCompression: 0\n"
        "    compressionQuality: 50\n"
        "    crunchedCompression: 0\n"
        "    allowsAlphaSplitting: 0\n"
        "    overridden: 0\n"
        "  - serializedVersion: 3\n"
        "    buildTarget: Standalone\n"
        "    maxTextureSize: 4096\n"
        "    textureFormat: -1\n"
        "    textureCompression: 0\n"
        "    compressionQuality: 50\n"
        "    crunchedCompression: 0\n"
        "    allowsAlphaSplitting: 0\n"
        "    overridden: 0\n"
        "  spriteSheet:\n"
        "    serializedVersion: 2\n"
        "    sprites:\n"
        f"{body}\n"
        "    outline: []\n"
        "    physicsShape: []\n"
        "    bones: []\n"
        f"    spriteID: {sheet_id}\n"
        "    internalID: 0\n"
        "    vertices: []\n"
        "    indices: \n"
        "    edges: []\n"
        "    weights: []\n"
        "    secondaryTextures: []\n"
        "    nameFileIdTable:\n"
        f"{names}\n"
        "  spritePackingTag: \n"
        "  userData: \n"
    )


# guids from the public com.unity.2d.tilemap.extras metas. Not editor-assigned ids.
ANIMATED_TILE_GUID = "13b75c95f34a00d4e8c04f76b73312e6"
RULE_TILE_GUID = "9d1514134bc4fbd41bb739b1b9a49231"


def unity_animated_tile(
    name: str,
    texture_guid: str,
    sprite_internals: list[int],
    collider: int,
    guid: str,
    fps: float,
) -> tuple[str, str]:
    """Animated Tile. Three water frames stay addressable. Collider 0 is None."""
    sprites = "\n".join(
        f"  - {{fileID: {internal}, guid: {texture_guid}, type: 3}}" for internal in sprite_internals
    )
    speed = f"{float(fps):.1f}"
    asset = (
        "%YAML 1.1\n"
        "%TAG !u! tag:unity3d.com,2011:\n"
        "--- !u!114 &11400000\n"
        "MonoBehaviour:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        "  m_GameObject: {fileID: 0}\n"
        "  m_Enabled: 1\n"
        "  m_EditorHideFlags: 0\n"
        "  m_Script: {fileID: 11500000, guid: "
        f"{ANIMATED_TILE_GUID}, type: 3}}\n"
        f"  m_Name: {name}\n"
        "  m_EditorClassIdentifier: \n"
        "  m_AnimatedSprites:\n"
        f"{sprites}\n"
        f"  m_MinSpeed: {speed}\n"
        f"  m_MaxSpeed: {speed}\n"
        "  m_AnimationStartTime: 0\n"
        "  m_AnimationStartFrame: 0\n"
        f"  m_TileColliderType: {collider}\n"
    )
    meta = (
        "fileFormatVersion: 2\n"
        f"guid: {guid}\n"
        "NativeFormatImporter:\n"
        "  externalObjects: {}\n"
        "  mainObjectFileID: 11400000\n"
        "  userData: \n"
        "  assetBundleName: \n"
        "  assetBundleVariant: \n"
    )
    return asset, meta


def unity_tile_asset(name: str, texture_guid: str, sprite_internal: int, collider: int, guid: str) -> tuple[str, str]:
    """Unity Tile asset. collider 0 is None, 2 is Grid. fileID 13312 is UnityEngine.Tilemaps.Tile."""
    asset = (
        "%YAML 1.1\n"
        "%TAG !u! tag:unity3d.com,2011:\n"
        "--- !u!114 &11400000\n"
        "MonoBehaviour:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        "  m_GameObject: {fileID: 0}\n"
        "  m_Enabled: 1\n"
        "  m_EditorHideFlags: 0\n"
        "  m_Script: {fileID: 13312, guid: 0000000000000000e000000000000000, type: 0}\n"
        f"  m_Name: {name}\n"
        "  m_EditorClassIdentifier: \n"
        f"  m_Sprite: {{fileID: {sprite_internal}, guid: {texture_guid}, type: 3}}\n"
        "  m_Color: {r: 1, g: 1, b: 1, a: 1}\n"
        "  m_Transform:\n"
        "    e00: 1\n"
        "    e01: 0\n"
        "    e02: 0\n"
        "    e03: 0\n"
        "    e10: 0\n"
        "    e11: 1\n"
        "    e12: 0\n"
        "    e13: 0\n"
        "    e20: 0\n"
        "    e21: 0\n"
        "    e22: 1\n"
        "    e23: 0\n"
        "    e30: 0\n"
        "    e31: 0\n"
        "    e32: 0\n"
        "    e33: 1\n"
        "  m_InstancedGameObject: {fileID: 0}\n"
        "  m_Flags: 1\n"
        f"  m_ColliderType: {collider}\n"
    )
    meta = (
        "fileFormatVersion: 2\n"
        f"guid: {guid}\n"
        "NativeFormatImporter:\n"
        "  externalObjects: {}\n"
        "  mainObjectFileID: 11400000\n"
        "  userData: \n"
        "  assetBundleName: \n"
        "  assetBundleVariant: \n"
    )
    return asset, meta


def unity_rule_tile(
    name: str,
    texture_guid: str,
    rules: list[tuple[int, int]],
    default_internal: int,
    collider: int,
    guid: str,
) -> tuple[str, str]:
    """16 side-bit rules. Bit 1 is right, 2 is bottom, 4 is left, 8 is top, in image space."""
    blocks = []
    for index, (bit, internal) in enumerate(rules):
        neighbors = [
            (1, 0, 1 if bit & 1 else 2),
            (0, -1, 1 if bit & 2 else 2),
            (-1, 0, 1 if bit & 4 else 2),
            (0, 1, 1 if bit & 8 else 2),
        ]
        neighbor_values = "\n".join(f"    - {value}" for _x, _y, value in neighbors)
        positions = "\n".join(f"    - {{x: {x}, y: {y}, z: 0}}" for x, y, _value in neighbors)
        blocks.append(
            "  - m_Neighbors:\n"
            f"{neighbor_values}\n"
            "    m_NeighborPositions:\n"
            f"{positions}\n"
            "    m_RuleTransform: 0\n"
            f"    m_Id: {index}\n"
            "    m_Sprites:\n"
            f"    - {{fileID: {internal}, guid: {texture_guid}, type: 3}}\n"
            "    m_GameObject: {fileID: 0}\n"
            "    m_MinAnimationSpeed: 1\n"
            "    m_MaxAnimationSpeed: 1\n"
            "    m_PerlinScale: 0.5\n"
            "    m_Output: 0\n"
            f"    m_ColliderType: {collider}\n"
            "    m_RandomTransform: 0"
        )
    joined = "\n".join(blocks)
    asset = (
        "%YAML 1.1\n"
        "%TAG !u! tag:unity3d.com,2011:\n"
        "--- !u!114 &11400000\n"
        "MonoBehaviour:\n"
        "  m_ObjectHideFlags: 0\n"
        "  m_CorrespondingSourceObject: {fileID: 0}\n"
        "  m_PrefabInstance: {fileID: 0}\n"
        "  m_PrefabAsset: {fileID: 0}\n"
        "  m_GameObject: {fileID: 0}\n"
        "  m_Enabled: 1\n"
        "  m_EditorHideFlags: 0\n"
        f"  m_Script: {{fileID: 11500000, guid: {RULE_TILE_GUID}, type: 3}}\n"
        f"  m_Name: {name}\n"
        "  m_EditorClassIdentifier: \n"
        f"  m_DefaultSprite: {{fileID: {default_internal}, guid: {texture_guid}, type: 3}}\n"
        "  m_DefaultGameObject: {fileID: 0}\n"
        f"  m_DefaultColliderType: {collider}\n"
        "  m_TilingRules:\n"
        f"{joined}\n"
    )
    meta = (
        "fileFormatVersion: 2\n"
        f"guid: {guid}\n"
        "NativeFormatImporter:\n"
        "  externalObjects: {}\n"
        "  mainObjectFileID: 11400000\n"
        "  userData: \n"
        "  assetBundleName: \n"
        "  assetBundleVariant: \n"
    )
    return asset, meta


def opaque_bounds(im, rect: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    px = im.load()
    x, y, w, h = rect
    xs = []
    ys = []
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            if _opaque(px, xx, yy):
                xs.append(xx - x)
                ys.append(yy - y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def english_search_query(user_text: str) -> str:
    """tool_search indexes English words only. Keep Latin words and add the sheet terms."""
    words = []
    for raw in user_text.replace(",", " ").split():
        token = "".join(ch for ch in raw if ch.isascii() and ch.isalnum())
        if len(token) >= 3 and token.lower() not in words:
            words.append(token.lower())
    tail = "sprite sheet tileset cut png slice pixel art 2D game godot unity walk cycle shore"
    if not words:
        return tail
    return " ".join(words) + " " + tail


def replace_decision(exists: bool, replace: bool) -> dict:
    if exists and not replace:
        reply = _base_reply("", 0, 0, 0, 0, 0)
        reply["error"] = "output already exists."
        reply["next"] = "Pass replace true to overwrite that path. Nothing was written."
        reply["next_ja"] = "出力が既にある。置き換えるなら replace を true にする。まだ書いていない。"
        return reply
    return {"ok": True, "error": "", "next": "", "next_ja": ""}


def reply_has_pixels(reply: dict) -> bool:
    banned = ("pixel", "rgba", "color", "bytes", "image", "mask", "png_bytes")
    for key, value in reply.items():
        if any(word in key.lower() for word in banned):
            return True
        if isinstance(value, (bytes, bytearray)):
            return True
    return False


def dump_reply(reply: dict) -> str:
    return json.dumps(reply, ensure_ascii=False, indent=2)


def _png_error(kind: str) -> PngError:
    if kind == "depth":
        return PngError(
            "png bit depth 16 is not read.",
            "Re-export the png as 8-bit.",
            "png は 8bit で書き出す。",
        )
    if kind == "interlace":
        return PngError(
            "interlaced png is not read.",
            "Re-export the png without interlacing.",
            "インターレース無しで書き出す。",
        )
    return PngError(
        "png did not parse.",
        "Pass a png file. The bytes were not read as an image.",
        "png として読めなかった。png のファイルを渡す。",
    )


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter(raw: bytes, height: int, row_bytes: int, bpp: int) -> bytearray:
    if len(raw) < height * (row_bytes + 1):
        raise _png_error("parse")
    out = bytearray(height * row_bytes)
    prev = bytearray(row_bytes)
    pos = 0
    for y in range(height):
        filt = raw[pos]
        pos += 1
        row = bytearray(raw[pos : pos + row_bytes])
        pos += row_bytes
        for x in range(row_bytes):
            left = row[x - bpp] if x >= bpp else 0
            up = prev[x]
            ul = prev[x - bpp] if x >= bpp else 0
            if filt == 0:
                value = row[x]
            elif filt == 1:
                value = (row[x] + left) & 255
            elif filt == 2:
                value = (row[x] + up) & 255
            elif filt == 3:
                value = (row[x] + ((left + up) // 2)) & 255
            elif filt == 4:
                value = (row[x] + _paeth(left, up, ul)) & 255
            else:
                raise _png_error("parse")
            row[x] = value
        out[y * row_bytes : (y + 1) * row_bytes] = row
        prev = row
    return out


def _channels(color_type: int) -> int:
    return {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]


def read_png(path: Path) -> Raster:
    return read_png_bytes(path.read_bytes())


def read_png_bytes(data: bytes) -> Raster:
    if len(data) < 8 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise _png_error("parse")
    pos = 8
    width = height = bit_depth = color_type = 0
    interlace = 0
    idat = bytearray()
    text: dict[str, str] = {}
    palette = b""
    transparency = b""
    seen_ihdr = False
    while pos + 12 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        if length < 0 or pos + 12 + length > len(data):
            raise _png_error("parse")
        kind = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        crc_got = struct.unpack(">I", data[pos + 8 + length : pos + 12 + length])[0]
        crc_calc = zlib.crc32(kind + chunk) & 0xFFFFFFFF
        if crc_got != crc_calc:
            raise _png_error("parse")
        pos += 12 + length
        if kind == b"IHDR":
            if length != 13:
                raise _png_error("parse")
            width, height, bit_depth, color_type, comp, flt, interlace = struct.unpack(">IIBBBBB", chunk)
            seen_ihdr = True
            if comp != 0 or flt != 0 or color_type not in (0, 2, 3, 4, 6):
                raise _png_error("parse")
            if bit_depth == 16:
                raise _png_error("depth")
            if bit_depth not in (1, 2, 4, 8):
                raise _png_error("parse")
            if interlace:
                raise _png_error("interlace")
        elif kind == b"PLTE":
            palette = chunk
        elif kind == b"tRNS":
            transparency = chunk
        elif kind == b"IDAT":
            idat.extend(chunk)
        elif kind == b"tEXt" and b"\x00" in chunk:
            key, value = chunk.split(b"\x00", 1)
            text[key.decode("latin1", "replace")] = value.decode("latin1", "replace")
        elif kind == b"zTXt" and b"\x00" in chunk:
            key, rest = chunk.split(b"\x00", 1)
            if len(rest) < 2 or rest[0] != 0:
                raise _png_error("parse")
            try:
                value = zlib.decompress(rest[1:])
            except zlib.error as exc:
                raise _png_error("parse") from exc
            text[key.decode("latin1", "replace")] = value.decode("latin1", "replace")
        elif kind == b"iTXt" and b"\x00" in chunk:
            key, rest = chunk.split(b"\x00", 1)
            if len(rest) < 2:
                raise _png_error("parse")
            flag = rest[0]
            method = rest[1]
            rest = rest[2:]
            if rest.count(b"\x00") < 2:
                raise _png_error("parse")
            _lang, rest = rest.split(b"\x00", 1)
            _translated, raw = rest.split(b"\x00", 1)
            if flag == 1:
                if method != 0:
                    raise _png_error("parse")
                try:
                    raw = zlib.decompress(raw)
                except zlib.error as exc:
                    raise _png_error("parse") from exc
            elif flag != 0:
                raise _png_error("parse")
            text[key.decode("utf-8", "replace")] = raw.decode("utf-8", "replace")
        elif kind == b"IEND":
            break
    if not seen_ihdr or width < 1 or height < 1 or not idat:
        raise _png_error("parse")
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error as exc:
        raise _png_error("parse") from exc
    channels = _channels(color_type)
    if bit_depth == 8:
        row_bytes = width * channels
        bpp = channels
        samples = _unfilter(raw, height, row_bytes, bpp)
    else:
        row_bytes = (width * channels * bit_depth + 7) // 8
        packed = _unfilter(raw, height, row_bytes, 1)
        samples = _unpack_bits(packed, width, height, channels, bit_depth)
    pixels = _to_rgba(samples, width, height, color_type, bit_depth, palette, transparency)
    return Raster(width, height, pixels, text)


def _unpack_bits(packed: bytearray, width: int, height: int, channels: int, bit_depth: int) -> bytearray:
    out = bytearray(width * height * channels)
    mask = (1 << bit_depth) - 1
    row_bytes = (width * channels * bit_depth + 7) // 8
    dest = 0
    for y in range(height):
        row = packed[y * row_bytes : (y + 1) * row_bytes]
        acc = 0
        bits = 0
        index = 0
        need = width * channels
        produced = 0
        while produced < need:
            if bits < bit_depth:
                if index >= len(row):
                    raise _png_error("parse")
                acc = (acc << 8) | row[index]
                index += 1
                bits += 8
            bits -= bit_depth
            out[dest] = (acc >> bits) & mask
            dest += 1
            produced += 1
    return out


def _to_rgba(
    samples: bytearray,
    width: int,
    height: int,
    color_type: int,
    bit_depth: int,
    palette: bytes,
    transparency: bytes,
) -> bytearray:
    count = width * height
    out = bytearray(count * 4)
    if color_type == 6:
        if len(samples) < count * 4:
            raise _png_error("parse")
        return samples
    if color_type == 2:
        if len(samples) < count * 3:
            raise _png_error("parse")
        for i in range(count):
            out[i * 4 : i * 4 + 3] = samples[i * 3 : i * 3 + 3]
            out[i * 4 + 3] = 255
        return out
    if color_type == 0:
        span = (1 << bit_depth) - 1
        for i, value in enumerate(samples[:count]):
            gray = value * 255 // span if span not in (0, 255) else value
            out[i * 4 : i * 4 + 3] = bytes((gray, gray, gray))
            out[i * 4 + 3] = 255
        return out
    if color_type == 4:
        for i in range(count):
            gray = samples[i * 2]
            out[i * 4 : i * 4 + 3] = bytes((gray, gray, gray))
            out[i * 4 + 3] = samples[i * 2 + 1]
        return out
    if color_type == 3:
        if not palette:
            raise _png_error("parse")
        colors = len(palette) // 3
        for i, index in enumerate(samples[:count]):
            if index >= colors:
                raise _png_error("parse")
            out[i * 4 : i * 4 + 3] = palette[index * 3 : index * 3 + 3]
            out[i * 4 + 3] = transparency[index] if index < len(transparency) else 255
        return out
    raise _png_error("parse")


def _num(value: float) -> str:
    if float(value) == int(value):
        return str(int(value))
    return str(value)


def animation_names(animation: str, frame_count: int, columns: int) -> list[str]:
    """One animation per row. The passed name is the first row, not a second copy."""
    cols = columns if columns else max(1, frame_count)
    rows = max(1, (frame_count + cols - 1) // cols) if frame_count else 1
    if rows == 1:
        return [animation]
    return [animation if index == 0 else f"{animation}_{index}" for index in range(rows)]


def measured_foot(im, rects, cell_w: int, cell_h: int) -> tuple[int, int]:
    """Foot is the center column and one pixel past the lowest opaque row, inside the cell."""
    lowest = -1
    for rect in rects:
        row = lowest_opaque_y(im, rect)
        if row > lowest:
            lowest = row
    if lowest < 0:
        return (cell_w // 2, cell_h)
    return (cell_w // 2, min(cell_h, lowest + 1))


def _is_solid(name: str, solid: dict | None) -> bool:
    if solid is not None and name in solid:
        return bool(solid[name])
    return not str(name).lower().startswith("water")


def normalize_anims(tile_anim: dict | None) -> tuple[dict | None, str]:
    """frames and fps are enough. columns, when omitted, is the frame count across the row."""
    if not tile_anim:
        return {}, ""
    out = {}
    for name, anim in tile_anim.items():
        if not isinstance(anim, dict) or "frames" not in anim:
            return None, "frames"
        if "fps" not in anim:
            return None, "fps"
        try:
            frames = int(anim["frames"])
            fps = float(anim["fps"])
            columns = frames if anim.get("columns") in (None, "") else int(anim["columns"])
        except (TypeError, ValueError):
            return None, "frames"
        if frames < 1:
            return None, "frames"
        out[str(name)] = {"frames": frames, "fps": fps, "columns": columns}
    return out, ""


def spriteframes_text(
    rel: str,
    rects: list[tuple[int, int, int, int]],
    durations: list[float],
    fps: float,
    trim_bounds: list,
    animation: str = "walk",
    columns: int = 0,
    offsets: list | None = None,
) -> str:
    """Text SpriteFrames. Each row is the animation name that was passed."""
    ext = "1_tex"
    lines = [
        '[gd_resource type="SpriteFrames" format=3]',
        "",
        f'[ext_resource type="Texture2D" path="res://{rel}" id="{ext}"]',
        "",
    ]
    ids: list[str] = []
    for index, rect in enumerate(rects):
        x, y, w, h = rect
        ox = oy = 0
        if trim_bounds and index < len(trim_bounds) and trim_bounds[index]:
            min_x, min_y, max_x, max_y = trim_bounds[index]
            ox, oy = int(min_x), int(min_y)
            x = x + ox
            y = y + oy
            w = int(max_x) - int(min_x) + 1
            h = int(max_y) - int(min_y) + 1
        sid = f"AtlasTexture_{index}"
        ids.append(sid)
        cell_w, cell_h = int(rect[2]), int(rect[3])
        right = max(0, cell_w - ox - int(w))
        bottom = max(0, cell_h - oy - int(h))
        lines.extend(
            [
                f'[sub_resource type="AtlasTexture" id="{sid}"]',
                f'atlas = ExtResource("{ext}")',
                f"region = Rect2({x}, {y}, {w}, {h})",
            ]
        )
        if ox or oy or right or bottom:
            lines.append(f"margin = Rect2({ox}, {oy}, {right}, {bottom})")
        lines.append("")
    names = animation_names(animation, len(rects), columns)
    cols = columns if columns else max(1, len(rects))

    def anim(name: str, indexes: list[int]) -> str:
        frames = []
        for index in indexes:
            sid = ids[index]
            duration = float(durations[index]) if index < len(durations) else 1.0
            frames.append(
                "{\n"
                f'"duration": {duration:.1f},\n'
                f'"texture": SubResource("{sid}")\n'
                "}"
            )
        joined = ", ".join(frames)
        return "{\n" f'"frames": [{joined}],\n' '"loop": 1,\n' f'"name": &"{name}",\n' f'"speed": {float(fps):.1f}\n' "}"

    bodies = []
    for row, name in enumerate(names):
        indexes = list(range(row * cols, min(len(rects), (row + 1) * cols)))
        if indexes:
            bodies.append(anim(name, indexes))
    lines.append("[resource]")
    lines.append(f"animations = [{', '.join(bodies)}]")
    lines.append("")
    return "\n".join(lines)


_TERRAIN_COLOR = {
    "grass": "Color(0.18, 0.55, 0.22, 1)",
    "water": "Color(0.15, 0.38, 0.78, 1)",
    "sand": "Color(0.84, 0.75, 0.47, 1)",
    "path": "Color(0.47, 0.32, 0.19, 1)",
}
_PEERING_SIDES = ("right_side", "bottom_side", "left_side", "top_side")


def _terrain_color(name: str, index: int) -> str:
    if name in _TERRAIN_COLOR:
        return _TERRAIN_COLOR[name]
    shade = (0.25, 0.45, 0.65, 0.85)
    return f"Color({shade[index % 4]}, {shade[(index + 1) % 4]}, {shade[(index + 2) % 4]}, 1)"


def _tile_block(cx: int, cy: int, index: int, name: str, points: str, solid: bool, bits: int | None) -> list[str]:
    """One atlas cell. bits is None when this terrain has no shore map."""
    lines = [
        f"{cx}:{cy}/0 = 0",
        f"{cx}:{cy}/0/terrain_set = 0",
        f"{cx}:{cy}/0/terrain = {index}",
    ]
    if bits is not None:
        for bit, side in enumerate(_PEERING_SIDES):
            if bits & (1 << bit):
                lines.append(f"{cx}:{cy}/0/terrains_peering_bit/{side} = {index}")
    if solid:
        lines.append(f"{cx}:{cy}/0/physics_layer_0/polygon_0/points = PackedVector2Array({points})")
    lines.append(f'{cx}:{cy}/0/custom_data_0 = "{name}"')
    return lines


def tileset_text(
    rel: str,
    cell_w: int,
    cell_h: int,
    margin: tuple[int, int],
    spacing: tuple[int, int],
    names: list[str],
    coords: dict,
    solid: dict,
    anims: dict,
    peering: dict | None = None,
) -> str:
    """A shore map uses a different atlas cell per neighbor bit. Without one, the terrain is one tile."""
    ext = "1_tex"
    sub = "TileSetAtlasSource_atlas"
    lines = [
        '[gd_resource type="TileSet" format=3]',
        "",
        f'[ext_resource type="Texture2D" path="res://{rel}" id="{ext}"]',
        "",
        f'[sub_resource type="TileSetAtlasSource" id="{sub}"]',
        f'texture = ExtResource("{ext}")',
        f"texture_region_size = Vector2i({cell_w}, {cell_h})",
    ]
    if margin[0] or margin[1]:
        lines.append(f"margins = Vector2i({margin[0]}, {margin[1]})")
    if spacing[0] or spacing[1]:
        lines.append(f"separation = Vector2i({spacing[0]}, {spacing[1]})")
    half_w = cell_w / 2.0
    half_h = cell_h / 2.0
    points = ", ".join(
        [
            _num(-half_w),
            _num(-half_h),
            _num(half_w),
            _num(-half_h),
            _num(half_w),
            _num(half_h),
            _num(-half_w),
            _num(half_h),
        ]
    )
    for index, name in enumerate(names):
        patterns = (peering or {}).get(name) or {}
        anim = (anims or {}).get(name)
        if patterns:
            for raw_bit, pair in sorted(patterns.items(), key=lambda item: int(item[0])):
                cx, cy = int(pair[0]), int(pair[1])
                lines.extend(
                    _tile_block(cx, cy, index, name, points, bool(solid.get(name)), int(raw_bit))
                )
                if anim and int(raw_bit) == 0:
                    lines.append(f"{cx}:{cy}/animation_columns = {int(anim['columns'])}")
                    lines.append(f"{cx}:{cy}/animation_speed = {float(anim['fps']):.1f}")
                    for frame in range(int(anim["frames"])):
                        lines.append(f"{cx}:{cy}/animation_frame_{frame}/duration = 1.0")
            continue
        pair = coords[name]
        cx, cy = int(pair[0]), int(pair[1])
        lines.extend(_tile_block(cx, cy, index, name, points, bool(solid.get(name)), None))
        if anim:
            lines.append(f"{cx}:{cy}/animation_columns = {int(anim['columns'])}")
            lines.append(f"{cx}:{cy}/animation_speed = {float(anim['fps']):.1f}")
            for frame in range(int(anim["frames"])):
                lines.append(f"{cx}:{cy}/animation_frame_{frame}/duration = 1.0")
    lines.extend(
        [
            "",
            "[resource]",
            f"tile_size = Vector2i({cell_w}, {cell_h})",
            "physics_layer_0/collision_layer = 1",
            "terrain_set_0/mode = 2",
        ]
    )
    for index, name in enumerate(names):
        lines.append(f'terrain_set_0/terrain_{index}/name = "{name}"')
        lines.append(f"terrain_set_0/terrain_{index}/color = {_terrain_color(name, index)}")
    lines.extend(
        [
            'custom_data_layer_0/name = "display_name"',
            "custom_data_layer_0/type = 4",
            f'sources/0 = SubResource("{sub}")',
            "",
        ]
    )
    return "\n".join(lines)


def stage_script(
    base: str,
    stem: str,
    tileset_rel: str = "",
    hframes: int = 4,
    vframes: int = 1,
    foot: tuple[int, int] = (8, 32),
    animation: str = "walk",
    fps: int = 8,
) -> str:
    """Side-view stage. The foot sits on the top edge of the tile. A floating frame warns and the scene still plays."""
    png_path = f"res://{base}{stem}.png"
    frames_path = f"res://{base}{stem}.spriteframes.tres"
    import_path = f"res://{base}{stem}.png.import"
    scene = f"res://{base}{stem}_stage.tscn"
    tileset_path = f"res://{tileset_rel}" if tileset_rel else ""
    tiles_import = ""
    tiles_slice = ""
    if tileset_rel.endswith(".tileset.tres"):
        stem_path = tileset_rel[: -len(".tileset.tres")]
        tiles_import = f"res://{stem_path}.png.import"
        tiles_slice = f"res://{stem_path}.slice.json"
    import_next = f"{IMPORT_CMD}. Then play {scene} again."
    import_ja = f"png の import が無い。{IMPORT_CMD}。そのあと {scene} を再生する。"
    load_ja = f"png を読めなかった。{IMPORT_CMD}。そのあと {scene} を再生する。"
    tiles_check = "false"
    if tiles_import:
        tiles_check = f'not FileAccess.file_exists("{tiles_import}")'
    foot_x, foot_y = int(foot[0]), int(foot[1])
    return f'''extends Node2D

var sprite: Node2D
var map: TileMapLayer
var foot_x := {foot_x}
var foot_y := {foot_y}
var started_ms := 0
var last_frame := -1
var changes := 0
var seen := {{}}
var failed := false
var probe := false
var anim_name := "{animation}"
var water_frames := 0
var using_frames := false
var frame_acc := 0.0
var fps := {fps}

func _fail(error_en: String, next_en: String, next_ja: String) -> void:
	failed = true
	sprite = null
	print("error: ", error_en)
	print("next: ", next_en)
	print("次: ", next_ja)
	if DisplayServer.get_name() == "headless":
		get_tree().quit(2)

func _bottom_of(image: Image, origin: Vector2i, size: Vector2i) -> int:
	for y in range(size.y - 1, -1, -1):
		for x in range(size.x):
			if image.get_pixel(origin.x + x, origin.y + y).a > 0.0:
				return y
	return -1

func _frame_index() -> int:
	if using_frames:
		return (sprite as AnimatedSprite2D).frame
	return (sprite as Sprite2D).frame

func _ready() -> void:
	probe = "--probe" in OS.get_cmdline_user_args() or OS.get_environment("SPRITE_SHEET_PROBE") == "1"
	if not FileAccess.file_exists("{import_path}") or {tiles_check}:
		_fail("no import sidecar for the png.", "{import_next}", "{import_ja}")
		return
	var tileset_path := "{tileset_path}"
	if tileset_path != "" and not FileAccess.file_exists(tileset_path):
		_fail("region resource is missing.", "Build the SpriteFrames and the TileSet from the slice json, then play again.", "slice json から SpriteFrames と TileSet を作ってから、再度再生する。")
		return
	var sheet := load("{png_path}")
	if sheet == null:
		_fail("png did not load.", "{import_next}", "{load_ja}")
		return
	if FileAccess.file_exists("{frames_path}"):
		var frames = load("{frames_path}")
		if frames == null:
			_fail("png did not load.", "{import_next}", "{load_ja}")
			return
		var animated := AnimatedSprite2D.new()
		animated.sprite_frames = frames
		if frames.has_animation(anim_name):
			animated.animation = anim_name
		using_frames = true
		sprite = animated
	else:
		var still := Sprite2D.new()
		still.texture = sheet
		still.hframes = {hframes}
		still.vframes = {vframes}
		still.frame = 0
		sprite = still
	sprite.centered = false
	sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	sprite.z_index = 1
	var view := get_viewport_rect().size
	if view.x < 1.0 or view.y < 1.0:
		view = Vector2(float(ProjectSettings.get_setting("display/window/size/viewport_width")), float(ProjectSettings.get_setting("display/window/size/viewport_height")))
	var foot_world := view * 0.5
	sprite.position = foot_world - Vector2(foot_x, foot_y)
	if tileset_path != "" and FileAccess.file_exists(tileset_path):
		var tileset = load(tileset_path)
		if tileset == null:
			_fail("png did not load.", "{import_next}", "{load_ja}")
			return
		var tiles_doc = JSON.parse_string(FileAccess.get_file_as_string("{tiles_slice}"))
		if typeof(tiles_doc) != TYPE_DICTIONARY or not tiles_doc.has("coords"):
			_fail("tile_coords is missing.", "Pass tile_coords for every tile name. Nothing was written.", "各地形の tile_coords を渡す。まだ書いていない。")
			return
		var expected := Vector2i(int(tiles_doc["cell_w"]), int(tiles_doc["cell_h"]))
		if tileset.tile_size != expected:
			_fail("tile_size does not match the cell.", "Set TileSet.tile_size to the cell width and height.", "TileSet.tile_size をセルの幅と高さにする。")
			return
		map = TileMapLayer.new()
		map.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		map.tile_set = tileset
		var grass: Array = tiles_doc["coords"]["grass"]
		var water: Array = tiles_doc["coords"]["water"]
		var grass_atlas := Vector2i(int(grass[0]), int(grass[1]))
		var water_atlas := Vector2i(int(water[0]), int(water[1]))
		var center := map.map_to_local(Vector2i(0, 0))
		var tile_size := map.tile_set.tile_size
		var top := center - Vector2(0, float(tile_size.y) * 0.5)
		map.position = Vector2(foot_world.x - center.x, foot_world.y - top.y)
		add_child(map)
		map.set_cell(Vector2i(0, 0), 0, grass_atlas)
		map.set_cell(Vector2i(1, 0), 0, water_atlas)
		var source = tileset.get_source(0)
		water_frames = source.get_tile_animation_frames_count(water_atlas)
	add_child(sprite)
	if using_frames:
		(sprite as AnimatedSprite2D).play(anim_name)
	started_ms = Time.get_ticks_msec()
	if not probe:
		return

func _nearest() -> bool:
	var node_filter: int = sprite.texture_filter
	var project_filter := int(ProjectSettings.get_setting("rendering/textures/canvas_textures/default_texture_filter"))
	if node_filter == CanvasItem.TEXTURE_FILTER_NEAREST or node_filter == CanvasItem.TEXTURE_FILTER_NEAREST_WITH_MIPMAPS:
		return true
	if node_filter == CanvasItem.TEXTURE_FILTER_PARENT_NODE:
		return project_filter == 0 or project_filter == 3
	return false

func _current_image() -> Image:
	if using_frames:
		return (sprite as AnimatedSprite2D).sprite_frames.get_frame_texture(anim_name, _frame_index()).get_image()
	var image := (sprite as Sprite2D).texture.get_image()
	var fw := int(image.get_width() / {hframes})
	var fh := int(image.get_height() / {vframes})
	var frame := _frame_index()
	var origin := Vector2i((frame % {hframes}) * fw, int(frame / {hframes}) * fh)
	return image.get_region(Rect2i(origin, Vector2i(fw, fh)))

func _all_bottoms() -> Array:
	var out: Array = []
	if using_frames:
		var frames = (sprite as AnimatedSprite2D).sprite_frames
		var count := frames.get_frame_count(anim_name)
		for i in count:
			var image := frames.get_frame_texture(anim_name, i).get_image()
			out.append(_bottom_of(image, Vector2i(0, 0), image.get_size()))
		return out
	var image := (sprite as Sprite2D).texture.get_image()
	var fw := int(image.get_width() / {hframes})
	var fh := int(image.get_height() / {vframes})
	var total := {hframes} * {vframes}
	for frame in total:
		var origin := Vector2i((frame % {hframes}) * fw, int(frame / {hframes}) * fh)
		out.append(_bottom_of(image, origin, Vector2i(fw, fh)))
	return out

func _process(delta: float) -> void:
	if failed or sprite == null:
		return
	if not using_frames:
		frame_acc += delta
		var step_time := 1.0 / float(fps)
		var still := sprite as Sprite2D
		var count := still.hframes * still.vframes
		while frame_acc >= step_time and step_time > 0.0:
			frame_acc -= step_time
			still.frame = (still.frame + 1) % count
	if not probe:
		return
	var frame := _frame_index()
	if frame != last_frame:
		changes += 1
		last_frame = frame
		seen[frame] = true
	if Time.get_ticks_msec() - started_ms < 800:
		return
	if seen.size() < 2 or changes < 2:
		_fail("animation stayed on one frame.", "Set fps from 1 to 60 and probe for at least one cycle.", "fps は 1 から 60。1周見えるまで探る。")
		return
	var ground_warn := false
	var bottoms := _all_bottoms()
	for ground in bottoms:
		if int(ground) != foot_y - 1:
			ground_warn = true
			break
	if ground_warn:
		print("warn: a frame does not meet the ground.")
		print("next: The scene still plays. A floating frame is allowed.")
		print("次: シーンは残す。浮いたコマも再生する。")
	var row := _bottom_of(_current_image(), Vector2i(0, 0), _current_image().get_size())
	var foot := sprite.global_position + Vector2(foot_x, foot_y)
	if map == null:
		_fail("foot is on an empty cell.", "Place a tile under the foot, then probe again.", "足の下にタイルを置いてから、再度探る。")
		return
	var cell := map.local_to_map(map.to_local(foot))
	var cell_id := map.get_cell_source_id(cell)
	if cell_id < 0:
		var inside := foot + Vector2(0, 1)
		cell = map.local_to_map(map.to_local(inside))
		cell_id = map.get_cell_source_id(cell)
	if cell_id < 0:
		_fail("foot is on an empty cell.", "Place a tile under the foot, then probe again.", "足の下にタイルを置いてから、再度探る。")
		return
	var atlas := map.get_cell_atlas_coords(cell)
	var data = map.tile_set.get_source(cell_id).get_tile_data(atlas, 0)
	var tile_name := str(data.get_custom_data("display_name"))
	if not _nearest():
		_fail("texture filter is not nearest.", "Set texture_filter = TEXTURE_FILTER_NEAREST on the AnimatedSprite2D. The project default is not enough.", "AnimatedSprite2D に texture_filter = TEXTURE_FILTER_NEAREST を入れる。プロジェクトの既定では足りない。")
		return
	print("PLAY frame=", frame, " frames_seen=", seen.size(), " changes=", changes, " anim=", anim_name, " foot=", int(foot.x), ",", int(foot.y), " foot_px=", row, " cell=", cell_id, " tile=", tile_name, " nearest=true water_frames=", water_frames)
	get_tree().quit(0)
'''
def _stage_gd(base: str, stem: str) -> str:
    return stage_script(base, stem)


def _stage_tscn(base: str, stem: str) -> str:
    return (
        "[gd_scene load_steps=2 format=3]\n\n"
        f'[ext_resource type="Script" path="res://{base}{stem}_stage.gd" id="1_play"]\n\n'
        '[node name="Stage" type="Node2D"]\n'
        'script = ExtResource("1_play")\n'
    )


_LICENSE_KEYS = ("License", "license", "Copyright", "copyright", "SPDX-License-Identifier")
IMPORT_CMD = "godot --headless --editor --quit --path <project>"
_STOP_NEXT = "That sheet is not written."
_STOP_NEXT_JA = "そのシートは書かない。"
_FREE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"cc0(?:[-\s.]?\d+(?:\.\d+)?)?"
    r"|mit"
    r"|unlicense"
    r"|(?<!not )public\s+domain"
    r"|cc[-\s]?by(?![-\s]?(?:nc|nd|sa)\b)"
    r")(?![a-z0-9])",
    re.IGNORECASE,
)
_SA_RE = re.compile(r"(?<![a-z0-9])cc[-\s]?by[-\s]?sa\b", re.IGNORECASE)
_STOP_RE = re.compile(
    r"(?<!not )all rights reserved"
    r"|proprietary"
    r"|non-?commercial"
    r"|無断転載禁止"
    r"|(?<![a-z0-9])cc[-\s]?by[-\s]?(?:nc|nd)\b",
    re.IGNORECASE,
)
_SHARE_WARNING = "Share-alike applies. Keep this license on adaptations."
_UNKNOWN_WARNING = "License text is not a known free license. It was copied and not rewritten."
_ABSENT_WARNING = "No rights are attached to this sheet."


def license_decision(text: dict[str, str]) -> tuple[str, str, str]:
    """Copy CC0, CC-BY, MIT, Unlicense, and public domain. Copy CC-BY-SA with a warning.

    Match on word boundaries. Stop on an empty license, unknown, NC, ND,
    proprietary, All Rights Reserved, and 無断転載禁止.
    """
    found = [(key, text[key].strip()) for key in _LICENSE_KEYS if key in text]
    if not found:
        return "absent", "", ""
    nonempty: list[tuple[str, str]] = []
    for _key, value in found:
        if value.lower() == "unknown":
            return "stop", value, ""
        if value == "":
            continue
        nonempty.append((_key, value))
    if not nonempty:
        return "stop", "unknown", ""
    for _key, value in nonempty:
        if _STOP_RE.search(value):
            return "stop", value, ""
    preferred = nonempty[0][1]
    for key, value in nonempty:
        if key.lower() in ("license", "spdx-license-identifier"):
            preferred = value
            break
    for _key, value in nonempty:
        if _SA_RE.search(value):
            return "ok", value, _SHARE_WARNING
    if _FREE_RE.search(preferred):
        return "ok", preferred, ""
    return "ok", preferred, _UNKNOWN_WARNING


def _license_ja(warning: str) -> str:
    if warning == _SHARE_WARNING:
        return "継承（share-alike）が付く。改変したものも同じライセンスにする。"
    if warning == _ABSENT_WARNING:
        return "このシートに権利は付いていない。"
    if warning == _UNKNOWN_WARNING:
        return "知らないライセンス文は写しただけで、定型は作っていない。"
    return ""


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def encode_png(raster: Raster) -> bytes:
    width, height = raster.size
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = bytearray()
    row_bytes = width * 4
    for y in range(height):
        raw.append(0)
        start = y * row_bytes
        raw.extend(raster.pixels[start : start + row_bytes])
    parts = [_png_chunk(b"IHDR", ihdr)]
    for key, value in raster.text.items():
        try:
            parts.append(_png_chunk(b"tEXt", key.encode("latin-1") + b"\x00" + value.encode("latin-1")))
        except UnicodeEncodeError:
            parts.append(_png_chunk(b"iTXt", key.encode("utf-8") + b"\x00\x00\x00\x00\x00" + value.encode("utf-8")))
    parts.append(_png_chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
    parts.append(_png_chunk(b"IEND", b""))
    return b"\x89PNG\r\n\x1a\n" + b"".join(parts)


def extrude_raster(raster: Raster, rects, spacing, extrude_px: int) -> Raster:
    """Copy each cell edge one pixel into a gap on that axis. One axis is enough."""
    gap_x = int(spacing[0])
    gap_y = int(spacing[1])
    if extrude_px != 1 or (gap_x < 1 and gap_y < 1):
        return raster
    width, height = raster.size
    pixels = bytearray(raster.pixels)
    origins = {(int(item[0]), int(item[1])) for item in rects}

    def get(x: int, y: int) -> bytes:
        i = (y * width + x) * 4
        return bytes(pixels[i : i + 4])

    def put(x: int, y: int, src: bytes) -> None:
        if x < 0 or y < 0 or x >= width or y >= height:
            return
        i = (y * width + x) * 4
        pixels[i : i + 4] = src

    for raw in rects:
        x, y, cw, ch = int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3])
        if gap_x >= 1 and (x + cw + gap_x, y) in origins:
            for row in range(ch):
                right = get(x + cw - 1, y + row)
                for step in range(min(extrude_px, gap_x)):
                    put(x + cw + step, y + row, right)
        if gap_y >= 1 and (x, y + ch + gap_y) in origins:
            for col in range(cw):
                bottom = get(x + col, y + ch - 1)
                for step in range(min(extrude_px, gap_y)):
                    put(x + col, y + ch + step, bottom)
    return Raster(width, height, pixels, dict(raster.text))


def _grid_edge_opaque(raster: Raster, rects) -> bool:
    px = raster.load()
    for raw in rects:
        x, y, w, h = int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3])
        if w < 1 or h < 1:
            continue
        for xx in range(x, x + w):
            if _opaque(px, xx, y) or _opaque(px, xx, y + h - 1):
                return True
        for yy in range(y, y + h):
            if _opaque(px, x, yy) or _opaque(px, x + w - 1, yy):
                return True
    return False


def expand_tile_gaps(raster: Raster, cols: int, rows: int, cell_w: int, cell_h: int, margin, gap: int = 1) -> Raster:
    """A new png with a 1px gap. The gap copies the cell edge. The source bytes stay."""
    width = raster.size[0]
    new_w = cols * cell_w + max(0, cols - 1) * gap
    new_h = rows * cell_h + max(0, rows - 1) * gap
    pixels = bytearray(new_w * new_h * 4)
    source = raster.pixels

    def get(x: int, y: int) -> bytes:
        i = (y * width + x) * 4
        return bytes(source[i : i + 4])

    def put(x: int, y: int, color: bytes) -> None:
        i = (y * new_w + x) * 4
        pixels[i : i + 4] = color

    for row in range(rows):
        for col in range(cols):
            sx0 = int(margin[0]) + col * cell_w
            sy0 = int(margin[1]) + row * cell_h
            dx0 = col * (cell_w + gap)
            dy0 = row * (cell_h + gap)
            for yy in range(cell_h):
                for xx in range(cell_w):
                    put(dx0 + xx, dy0 + yy, get(sx0 + xx, sy0 + yy))
            if col + 1 < cols:
                for yy in range(cell_h):
                    edge = get(sx0 + cell_w - 1, sy0 + yy)
                    for step in range(gap):
                        put(dx0 + cell_w + step, dy0 + yy, edge)
            if row + 1 < rows:
                for xx in range(cell_w):
                    edge = get(sx0 + xx, sy0 + cell_h - 1)
                    for step in range(gap):
                        put(dx0 + xx, dy0 + cell_h + step, edge)
            if col + 1 < cols and row + 1 < rows:
                corner = get(sx0 + cell_w - 1, sy0 + cell_h - 1)
                for gy in range(gap):
                    for gx in range(gap):
                        put(dx0 + cell_w + gx, dy0 + cell_h + gy, corner)
    return Raster(new_w, new_h, pixels, dict(raster.text))


def _names_for(kind: str, frame_count: int, names, tile_names) -> list[str]:
    if kind == "tileset":
        return list(tile_names or [])
    if names:
        return list(names)
    return [f"frame_{i}" for i in range(frame_count)]


def slice_grid(
    project: Path,
    rel: str,
    cell_w: int,
    cell_h: int,
    kind: str = "sprite",
    margin=(0, 0),
    spacing=(0, 0),
    columns: int | None = None,
    origin: str = "top_left",
    fps: int = 8,
    durations: list[float] | None = None,
    trim: bool = False,
    extrude_px: int = 0,
    foot: tuple[int, int] | None = None,
    names: list[str] | None = None,
    tile_names: list[str] | None = None,
    tile_coords: dict | None = None,
    tile_solid: dict | None = None,
    tile_anim: dict | None = None,
    tile_peering: dict | None = None,
    write: bool = True,
    emit_scene: bool = False,
    replace: bool = False,
    animation: str = "walk",
    guid: str = "",
    ppu: int | None = None,
    tileset_rel: str = "",
    dry_run: bool = False,
    png_bytes: bytes | None = None,
    sink: list | None = None,
) -> dict:
    """Write the slice, the Unity meta, and the Godot tres. This call does not launch Godot.

    dry_run returns the same approval line and writes nothing.
    """
    def _stop(error: str, nxt: str, nxt_ja: str, **extra) -> dict:
        inspected["ok"] = False
        inspected["error"] = error
        inspected["next"] = nxt
        inspected["next_ja"] = nxt_ja
        inspected["paths"] = []
        inspected["wrote"] = False
        inspected.update(extra)
        return inspected

    raster_override = None
    if png_bytes is None:
        inspected = inspect_grid(
            project,
            rel,
            cell_w,
            cell_h,
            margin,
            spacing,
            columns=columns,
            origin=origin,
            extrude_px=extrude_px,
            kind=kind,
        )
    else:
        located, err = resolve_png(project, rel, must_exist=False)
        if err:
            return err
        try:
            raster_override = read_png_bytes(png_bytes)
        except PngError as exc:
            return _refuse(exc.error, exc.next, exc.next_ja, rel)
        except Exception:
            return _refuse(
                "png did not parse.",
                "Pass a png file. The bytes were not read as an image.",
                "png として読めなかった。png のファイルを渡す。",
                rel,
            )
        as_of = int(located.stat().st_mtime) if located is not None and located.is_file() else 0
        inspected = inspect_image(
            raster_override,
            cell_w,
            cell_h,
            margin,
            spacing,
            source=rel,
            as_of=as_of,
            columns=columns,
            origin=origin,
            extrude_px=extrude_px,
            kind=kind,
        )
    if not inspected["ok"]:
        inspected["paths"] = []
        inspected["wrote"] = False
        return inspected
    if fps < 1 or fps > 60:
        return _stop(
            "fps must be from 1 to 60.",
            "Pass fps from 1 to 60. Nothing was written.",
            "fps は 1 から 60。まだ書いていない。",
        )
    if durations is not None and len(durations) != inspected["frame_count"]:
        return _stop(
            "durations do not match the frame count.",
            "Pass one duration per frame, or omit durations.",
            "duration はコマの数だけ渡すか、省く。",
        )
    if kind == "sprite" and not names:
        names = [f"{animation}_{i}" for i in range(inspected["frame_count"])]
    label_names = _names_for(kind, inspected["frame_count"], names, tile_names)
    anims, anim_missing = normalize_anims(tile_anim)
    if anims is None:
        return _stop(
            f"missing or invalid {anim_missing}.",
            f"Pass {anim_missing} as described. columns is optional. Nothing was written.",
            f"{anim_missing} を直す。columns は省ける。まだ書いていない。",
        )
    if kind == "tileset" and (not label_names or any(name not in (tile_coords or {}) for name in label_names)):
        return _stop(
            "tile_coords is missing.",
            "Pass tile_coords for every tile name. Nothing was written.",
            "各地形の tile_coords を渡す。まだ書いていない。",
        )
    path, _err = resolve_png(project, rel, must_exist=png_bytes is None)
    if path is None:
        return inspected
    if raster_override is None:
        raster = read_png(path)
    else:
        raster = raster_override
    license_state, license_text, license_warning = license_decision(raster.text)
    if license_state == "stop":
        return _stop(
            "png license text is empty or restricted.",
            _STOP_NEXT,
            _STOP_NEXT_JA,
            license="unknown",
        )
    if license_state == "absent":
        license_warning = _ABSENT_WARNING
    inspected["license"] = license_text
    if license_warning:
        inspected["next"] = ((inspected.get("next") or "") + " " + license_warning).strip()
        inspected["next_ja"] = ((inspected.get("next_ja") or "") + _license_ja(license_warning)).strip()
    shape = grid_rects(
        raster.size[0],
        raster.size[1],
        cell_w,
        cell_h,
        margin[0],
        margin[1],
        spacing[0],
        spacing[1],
        inspected["columns"],
    )
    if shape is None:
        inspected["ok"] = False
        return inspected
    cols, rows, rects = shape
    rects = _order_rects(rects, cols, rows, origin)
    if foot is None:
        foot = measured_foot(raster, rects, cell_w, cell_h)
    else:
        measured = measured_foot(raster, rects, cell_w, cell_h)
        foot = (
            measured[0] if int(foot[0]) < 0 else int(foot[0]),
            measured[1] if int(foot[1]) < 0 else int(foot[1]),
        )
    if ppu is None:
        ppu = cell_h
    if kind == "sprite":
        inspected["foot"] = [int(foot[0]), int(foot[1])]
    if not writes_files(kind, margin, spacing, write, emit_scene, durations):
        inspected["paths"] = []
        inspected["wrote"] = False
        return inspected
    paths = output_paths(rel, kind, emit_scene, label_names if kind == "tileset" else None)
    base, stem = _prefix(rel)
    applied = inspected["extrude_px"]
    extruded = raster
    texture_rel = rel
    extrude_rel = ""
    out_margin = (int(margin[0]), int(margin[1]))
    out_spacing = (int(spacing[0]), int(spacing[1]))
    if applied == 1 and (int(spacing[0]) >= 1 or int(spacing[1]) >= 1):
        extruded = extrude_raster(raster, rects, spacing, 1)
        extrude_rel = f"{base}{stem}.extruded.png"
        paths = paths + [extrude_rel]
        if bytes(extruded.pixels) != bytes(raster.pixels):
            texture_rel = extrude_rel
    elif (
        kind == "tileset"
        and int(spacing[0]) == 0
        and int(spacing[1]) == 0
        and (cols > 1 or rows > 1)
        and _grid_edge_opaque(raster, rects)
    ):
        extruded = expand_tile_gaps(raster, cols, rows, cell_w, cell_h, margin, 1)
        extrude_rel = f"{base}{stem}.extruded.png"
        texture_rel = extrude_rel
        applied = 1
        out_margin = (0, 0)
        out_spacing = (1, 1)
        paths = paths + [extrude_rel, f"{extrude_rel}.import"]
    if kind == "tileset" and texture_rel != rel:
        source_meta = f"{base}{stem}.png.meta"
        paths = [f"{texture_rel}.meta" if item == source_meta else item for item in paths]
    body, mode = approval_text(paths, replace)
    list_rel = ""
    if mode == "manifest":
        list_rel = f"{base}{stem}.paths.txt"
        body = ("replace " if replace else "") + list_rel
        mode = "inline" if len(body) <= APPROVAL_LIMIT and "\n" not in body and "`" not in body else "refuse"
    if mode != "inline":
        return _stop(
            "approval line does not fit in one message.",
            "Shorten the path list. Nothing was written.",
            "承認の行が 1 通に収まらない。パスを短くする。まだ書いていない。",
        )
    existing = [item for item in paths if item != rel and (project / item).exists()]
    if list_rel and (project / list_rel).exists():
        existing.append(list_rel)
    if existing and not replace:
        held = replace_decision(True, False)
        held["paths"] = paths
        held["source"] = rel
        return held
    used_names = label_names or [f"frame_{i}" for i in range(len(rects))]
    if kind == "sprite":
        used_names = (used_names + [f"frame_{i}" for i in range(len(rects))])[: len(rects)]
    meta_rects = []
    if kind == "sprite":
        for name, rect in zip(used_names, rects):
            meta_rects.append((name, rect[0], rect[1], rect[2], rect[3]))
    else:
        step_x = cell_w + int(out_spacing[0])
        step_y = cell_h + int(out_spacing[1])
        pad_x = int(out_margin[0])
        pad_y = int(out_margin[1])
        for name in label_names:
            patterns = (tile_peering or {}).get(name) or {}
            if patterns:
                for raw_bit, pair in sorted(patterns.items(), key=lambda item: int(item[0])):
                    base_x = int(pair[0]) * step_x + pad_x
                    base_y = int(pair[1]) * step_y + pad_y
                    meta_rects.append((f"{name}_{int(raw_bit)}", base_x, base_y, cell_w, cell_h))
                continue
            coord = (tile_coords or {})[name]
            base_x = coord[0] * step_x + pad_x
            base_y = coord[1] * step_y + pad_y
            meta_rects.append((name, base_x, base_y, cell_w, cell_h))
            anim = anims.get(name)
            if anim:
                for frame in range(1, int(anim["frames"])):
                    meta_rects.append((f"{name}_{frame}", base_x + frame * step_x, base_y, cell_w, cell_h))
    bounds = []
    if trim:
        for rect in rects if kind == "sprite" else [
            (item[1], item[2], item[3], item[4]) for item in meta_rects if "_" not in item[0]
        ]:
            found = opaque_bounds(raster, rect)
            bounds.append(list(found) if found else None)
    if trim and kind == "sprite":
        adjusted = []
        for index, item in enumerate(meta_rects):
            bound = bounds[index] if index < len(bounds) else None
            if bound:
                min_x, min_y, max_x, max_y = bound
                adjusted.append(
                    (
                        item[0],
                        item[1] + int(min_x),
                        item[2] + int(min_y),
                        int(max_x) - int(min_x) + 1,
                        int(max_y) - int(min_y) + 1,
                    )
                )
            else:
                adjusted.append(item)
        meta_rects = adjusted
    texture_guid = guid or hashlib.md5(rel.encode("utf-8")).hexdigest()
    document = {
        "ok": True,
        "source": rel,
        "as_of": inspected["as_of"],
        "png_text": raster.text,
        "license": license_text,
        "rights": RIGHTS,
        "slicing_creates_rights": False,
        "kind": kind,
        "file": texture_rel,
        "cell_w": cell_w,
        "cell_h": cell_h,
        "margin": [out_margin[0], out_margin[1]],
        "spacing": [out_spacing[0], out_spacing[1]],
        "origin": origin,
        "columns": cols,
        "rows": rows,
        "frames": len(rects),
        "fps": fps,
        "durations": list(durations) if durations is not None else ([1] * len(rects) if kind == "sprite" else []),
        "extrude_px": applied,
        "trim": trim,
        "trim_bounds": bounds,
        "hframes": inspected["hframes"],
        "vframes": inspected["vframes"],
        "names": used_names if kind == "sprite" else label_names,
        "ppu": ppu,
        "paths": paths,
    }
    offsets = []
    if trim:
        for bound in bounds:
            if bound:
                offsets.append([int(bound[0]), int(bound[1])])
            else:
                offsets.append([0, 0])
    pivots = None
    if kind == "sprite":
        document["foot"] = [int(foot[0]), int(foot[1])]
        document["animation"] = animation
        document["animations"] = animation_names(animation, len(rects), cols)
        document["frame_offset"] = offsets
        if trim and offsets:
            pivots = []
            for index, item in enumerate(meta_rects):
                ox, oy = offsets[index] if index < len(offsets) else (0, 0)
                tw = max(1, int(item[3]))
                th = max(1, int(item[4]))
                pivots.append(((int(foot[0]) - ox) / tw, ((oy + th) - int(foot[1])) / th))
    else:
        effective_solid = {name: _is_solid(name, tile_solid) for name in label_names}
        document["animation"] = ""
        document["unity_water"] = "animated_tile" if anims else ""
        document["coords"] = tile_coords or {}
        document["solid"] = effective_solid
        document["tile_animation"] = anims
        document["tile_peering"] = tile_peering or {}
    if list_rel:
        document["paths"] = [list_rel] + list(paths)
    written = ([list_rel] + paths) if list_rel else paths
    inspected["paths"] = written
    inspected["approval"] = body
    inspected["wrote"] = False
    inspected["license"] = document["license"]
    inspected["extrude_px"] = applied
    if kind == "sprite" and not any(margin) and not any(spacing):
        verb = "will be written" if dry_run else "were written"
        tight_next = (
            f"No margin and no spacing. SpriteFrames and a Unity Multiple slice {verb}. "
            f"hframes is {cols} and vframes is {rows}. Set the node's texture filter to Nearest."
        )
        old = f"No margin and no spacing. Set hframes to {cols} and vframes to {rows}."
        prefix = (inspected.get("next") or "").replace(old, " ")
        prefix = prefix.replace("Set the node's texture filter to Nearest.", " ")
        if license_warning:
            prefix = prefix.replace(license_warning, " ")
        prefix = " ".join(prefix.split())
        inspected["next"] = " ".join(part for part in (prefix, tight_next, license_warning) if part)
        old_ja = f"余白も間隔も無い。hframes を {cols}、vframes を {rows} にする。"
        ja = (inspected.get("next_ja") or "").replace(old_ja, "")
        ja = ja.replace("ノードの texture filter を Nearest にする。", "")
        ja_note = _license_ja(license_warning)
        if ja_note:
            ja = ja.replace(ja_note, "")
        done = "書く" if dry_run else "書いた"
        new_ja = (
            f"余白も間隔も無い。SpriteFrames と Unity の Multiple を{done}。"
            f"hframes は {cols}、vframes は {rows}。ノードの texture filter を Nearest にする。"
        )
        if ja_note:
            new_ja += ja_note
        inspected["next_ja"] = ja + new_ja
    if kind == "tileset" and texture_rel != rel:
        meta_rel = f"{texture_rel}.meta"
        meta_image_h = extruded.size[1]
    else:
        meta_rel = f"{base}{stem}.png.meta"
        meta_image_h = raster.size[1]
    if kind == "sprite":
        tres_rel = f"{base}{stem}.spriteframes.tres"
        tres_body = spriteframes_text(
            texture_rel,
            rects,
            document["durations"],
            fps,
            bounds if trim else [],
            animation,
            cols,
            offsets if trim else None,
        )
    else:
        tres_rel = f"{base}{stem}.tileset.tres"
        tres_body = tileset_text(
            texture_rel,
            cell_w,
            cell_h,
            out_margin,
            out_spacing,
            label_names,
            tile_coords or {},
            document["solid"],
            anims,
            tile_peering,
        )
    carried_guid = _carried_guid(project / meta_rel)
    if carried_guid:
        texture_guid = carried_guid
    kept_map, _lost_sprites, _meta_named = _meta_keep(project / meta_rel, [item[0] for item in meta_rects])
    meta_text = unity_meta(
        meta_rects,
        meta_image_h,
        texture_guid,
        ppu,
        0,
        center_pivot=(kind == "tileset"),
        pivots=pivots,
        kept=kept_map,
    )
    planned: list[tuple[str, str | bytes | None]] = []
    if list_rel:
        planned.append((list_rel, "\n".join(paths) + "\n"))  # route: paths_txt
    planned.append((meta_rel, meta_text))  # route: png_meta
    import_rel = f"{rel}.import"
    import_path = project / import_rel
    kept_uid = sidecar_uid(import_path.read_text(encoding="utf-8")) if import_path.is_file() else ""
    planned.append((import_rel, import_sidecar(rel, kept_uid)))  # route: png_import
    if texture_rel != rel:
        extra_rel = f"{texture_rel}.import"
        extra_path = project / extra_rel
        extra_uid = sidecar_uid(extra_path.read_text(encoding="utf-8")) if extra_path.is_file() else ""
        planned.append((extra_rel, import_sidecar(texture_rel, extra_uid)))  # route: extruded_import
    planned.append((f"{base}{stem}.slice.json", json.dumps(document, ensure_ascii=False, indent=2) + "\n"))  # route: slice_json
    if kind == "sprite":
        planned.append((tres_rel, tres_body))  # route: sprite_tres
    else:
        planned.append((tres_rel, tres_body))  # route: tileset_tres
        for name in label_names:
            anim = anims.get(name) or {}
            collider = 2 if document["solid"].get(name) else 0
            asset_rel = f"{base}{stem}.{name}.asset"
            asset_meta_rel = f"{asset_rel}.meta"
            asset_guid = hashlib.md5(f"{texture_guid}:{name}".encode("utf-8")).hexdigest()
            carried_asset = _carried_guid(project / asset_meta_rel)
            if carried_asset:
                asset_guid = carried_asset
            frames = int(anim.get("frames", 1) or 1)
            patterns = (tile_peering or {}).get(name) or {}
            if patterns and len(patterns) > 1:
                rules = []
                for raw_bit in sorted(int(bit) for bit in patterns):
                    _sid, internal = _sprite_identity(f"{texture_guid}:{name}_{raw_bit}")
                    rules.append((raw_bit, internal))
                default_bit = max(int(bit) for bit in patterns)
                _sid, default_internal = _sprite_identity(f"{texture_guid}:{name}_{default_bit}")
                asset, asset_meta = unity_rule_tile(
                    name, texture_guid, rules, default_internal, collider, asset_guid
                )
            elif frames > 1 and not patterns:
                internals = []
                for frame in range(frames):
                    frame_name = name if frame == 0 else f"{name}_{frame}"
                    _sid, internal = _sprite_identity(f"{texture_guid}:{frame_name}")
                    internals.append(internal)
                asset, asset_meta = unity_animated_tile(
                    name, texture_guid, internals, collider, asset_guid, float(anim.get("fps", 1))
                )
            else:
                frame_name = name
                if patterns:
                    frame_name = f"{name}_{max(int(bit) for bit in patterns)}"
                _sid, internal = _sprite_identity(f"{texture_guid}:{frame_name}")
                asset, asset_meta = unity_tile_asset(name, texture_guid, internal, collider, asset_guid)
            planned.append((asset_rel, asset))  # route: tile_asset
            planned.append((asset_meta_rel, asset_meta))  # route: tile_asset_meta
    if extrude_rel:
        planned.append((extrude_rel, encode_png(extruded)))  # route: extruded_png
    if emit_scene and kind == "sprite":
        planned.append((f"{base}{stem}_stage.gd", stage_script(base, stem, tileset_rel, cols, rows, foot, animation, fps)))  # route: stage_gd
        planned.append((f"{base}{stem}_stage.tscn", _stage_tscn(base, stem)))  # route: stage_tscn
    if kind == "tileset" and texture_rel != rel:
        stale_rel = f"{base}{stem}.png.meta"
        if stale_rel != meta_rel and (project / stale_rel).is_file():
            planned.append((stale_rel, None))  # route: stale_meta
    if sink is not None:
        sink.extend(planned)
        inspected["approval"] = body
        inspected["wrote"] = False
        inspected["extrude_px"] = applied
        return _attach_import(inspected)
    clause, blocked = rewrite_files(project, planned, True)
    if blocked:
        return _stop(blocked, "Nothing was written.", "まだ書いていない。", approval="")
    named = _fit_approval(body, clause)
    if named is None:
        return _stop(
            "could not name every value a replace would drop.",
            "Nothing was written.",
            "消える値を名指しできない。まだ書いていない。",
        )
    inspected["approval"] = named
    if dry_run:
        inspected["wrote"] = False
        inspected["extrude_px"] = applied
        return _attach_import(inspected)
    clause, blocked = rewrite_files(project, planned, False)
    if blocked:
        return _stop(blocked, "Nothing was written.", "まだ書いていない。", approval="")
    if clause is None:
        return _stop(
            "could not name every value a replace would drop.",
            "Nothing was written.",
            "消える値を名指しできない。まだ書いていない。",
        )
    inspected["wrote"] = True
    inspected["extrude_px"] = applied
    return _attach_import(inspected)


def _attach_import(reply: dict) -> dict:
    """The write's next names the one import command. It does not say to open a window."""
    if not reply.get("ok"):
        return reply
    nxt = reply.get("next") or ""
    if IMPORT_CMD not in nxt:
        reply["next"] = (nxt + " " + IMPORT_CMD).strip()
    ja = reply.get("next_ja") or ""
    if IMPORT_CMD not in ja:
        reply["next_ja"] = (ja + " 取り込みは " + IMPORT_CMD + "。").strip()
    return reply


_WALK_FILL = (220, 40, 40, 255)
_WALK_CLEAR = (0, 0, 0, 0)


def _mask_fill(mask: set[tuple[int, int]], x0: int, y0: int, x1: int, y1: int) -> None:
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            mask.add((x, y))


def _walk_masks() -> list[set[tuple[int, int]]]:
    """Contact, passing, contact, passing. The support foot stays on y=31. One foot lifts on a passing frame."""
    frames: list[set[tuple[int, int]]] = []
    contact_a: set[tuple[int, int]] = set()
    _mask_fill(contact_a, 5, 2, 10, 7)
    _mask_fill(contact_a, 6, 8, 9, 16)
    _mask_fill(contact_a, 2, 10, 5, 15)
    _mask_fill(contact_a, 10, 9, 13, 14)
    _mask_fill(contact_a, 3, 16, 6, 31)
    _mask_fill(contact_a, 9, 16, 12, 31)
    frames.append(contact_a)
    passing_a: set[tuple[int, int]] = set()
    _mask_fill(passing_a, 5, 3, 10, 8)
    _mask_fill(passing_a, 6, 9, 9, 17)
    _mask_fill(passing_a, 2, 11, 5, 15)
    _mask_fill(passing_a, 10, 11, 13, 15)
    _mask_fill(passing_a, 3, 14, 6, 18)
    _mask_fill(passing_a, 2, 12, 4, 16)
    _mask_fill(passing_a, 6, 17, 9, 31)
    frames.append(passing_a)
    contact_b: set[tuple[int, int]] = set()
    _mask_fill(contact_b, 5, 2, 10, 7)
    _mask_fill(contact_b, 6, 8, 9, 16)
    _mask_fill(contact_b, 10, 10, 13, 15)
    _mask_fill(contact_b, 2, 9, 5, 14)
    _mask_fill(contact_b, 2, 14, 4, 31)
    _mask_fill(contact_b, 11, 15, 13, 31)
    frames.append(contact_b)
    passing_b: set[tuple[int, int]] = set()
    _mask_fill(passing_b, 5, 3, 10, 8)
    _mask_fill(passing_b, 6, 9, 9, 17)
    _mask_fill(passing_b, 10, 11, 13, 15)
    _mask_fill(passing_b, 2, 11, 5, 15)
    _mask_fill(passing_b, 9, 14, 12, 18)
    _mask_fill(passing_b, 11, 12, 13, 16)
    _mask_fill(passing_b, 6, 17, 9, 31)
    frames.append(passing_b)
    return frames


_WALK_BOOT = (42, 36, 52, 255)
_WALK_SKIN = (255, 214, 170, 255)


def _blit_masks(raster: Raster, masks: list[set[tuple[int, int]]], origin: tuple[int, int], step: int) -> None:
    width = raster.size[0]
    raw = raster.pixels
    body = bytes(_WALK_FILL)
    boot = bytes(_WALK_BOOT)
    skin = bytes(_WALK_SKIN)
    for index, mask in enumerate(masks):
        ox = origin[0] + index * step
        oy = origin[1]
        for x, y in mask:
            if y >= 28:
                color = boot
            elif y <= 6 and 6 <= x <= 9:
                color = skin
            else:
                color = body
            px = ox + x
            py = oy + y
            i = (py * width + px) * 4
            raw[i : i + 4] = color


def walk_raster(license_text: str = "CC0") -> Raster:
    """Four local 16x32 walk frames. Nothing is fetched."""
    raster = Raster(64, 32, bytearray(64 * 32 * 4), {"License": license_text, "Source": "local walk cycle"})
    _blit_masks(raster, _walk_masks(), (0, 0), 16)
    return raster


def padded_raster(license_text: str = "CC0") -> Raster:
    """The same walk with a 2px margin and a 2px gap, so a slice has something to cut."""
    raster = Raster(74, 36, bytearray(74 * 36 * 4), {"License": license_text, "Source": "local walk cycle"})
    _blit_masks(raster, _walk_masks(), (2, 2), 18)
    return raster


def _paint_cell(raster: Raster, col: int, row: int, painter) -> None:
    width = raster.size[0]
    raw = raster.pixels
    ox = col * 32
    oy = row * 32
    for y in range(32):
        for x in range(32):
            i = ((oy + y) * width + (ox + x)) * 4
            raw[i : i + 4] = bytes(painter(x, y))


def shore_raster(license_text: str = "CC0") -> Raster:
    """256x96. Grass bits 0-15 are different pictures. Row 2 is water, sand, and path."""
    raster = Raster(256, 96, bytearray(256 * 96 * 4), {"License": license_text, "Source": "local shore tiles"})
    shore = (214, 190, 120, 255)
    for bit in range(16):
        def grass(x, y, bit=bit):
            base = (24, 110, 40, 255) if (x * 3 + y * 5 + bit) % 11 == 0 else (46, 150, 58, 255)
            if bit & 1 == 0 and x >= 28:
                return shore
            if bit & 4 == 0 and x <= 3:
                return shore
            if bit & 8 == 0 and y <= 3:
                return shore
            if bit & 2 == 0 and y >= 28:
                return shore
            return base

        _paint_cell(raster, bit % 8, bit // 8, grass)

    def water(band, frame):
        def painter(x, y, band=band, frame=frame):
            if band <= y <= band + 3:
                return (180, 220, 240, 255)
            if (x + frame) % 9 == 0:
                return (20, 70, 150, 255)
            return (36, 96, 180, 255)

        return painter

    for frame, band in enumerate((10, 16, 22)):
        _paint_cell(raster, frame, 2, water(band, frame))

    def sand(x, y):
        if x % 7 == 0 and y % 5 == 0:
            return (180, 150, 80, 255)
        return (214, 190, 120, 255)

    def path(x, y):
        if 12 <= x <= 19:
            return (168, 124, 78, 255)
        return (120, 82, 48, 255)

    _paint_cell(raster, 3, 2, sand)
    _paint_cell(raster, 4, 2, path)
    return raster


def shore_peering() -> dict:
    """Each grass neighbor bit is its own atlas cell. 15 is the full grass tile."""
    return {"grass": {i: [i % 8, i // 8] for i in range(16)}}


def shore_coords() -> dict:
    return {"grass": [7, 1], "water": [0, 2], "sand": [3, 2], "path": [4, 2]}


def glb_bytes() -> bytes:
    """This plugin does not create a 3D model. Callers get no file."""
    raise RuntimeError("This plugin does not create a 3D model.")


def _output_file(project: Path, rel: str, suffix: str) -> tuple[Path | None, dict | None]:
    """A new project-relative file. It does not have to exist yet."""
    if not rel or rel.startswith("/") or "\\" in rel:
        return None, _refuse(
            "refusing a path outside the project.",
            "Pass a regular png inside the project.",
            "プロジェクトの中の普通の png を渡す。",
            rel,
        )
    parts = Path(rel).parts
    if any(part in ("", ".", "..") for part in parts):
        return None, _refuse(
            "refusing a path outside the project.",
            "Pass a regular png inside the project.",
            "プロジェクトの中の普通の png を渡す。",
            rel,
        )
    if not rel.lower().endswith(suffix):
        return None, _refuse(
            "missing or invalid path.",
            f"Pass a {suffix} path inside the project. Nothing was written.",
            f"{suffix} のパスを渡す。まだ書いていない。",
            rel,
        )
    dest = project / rel
    if any((project.joinpath(*parts[: index + 1])).is_symlink() for index in range(len(parts))):
        return None, _refuse(
            "refusing a symlink.",
            "Pass a regular png inside the project.",
            "シンボリックリンクは拒否した。プロジェクトの中の普通の png を渡す。",
            rel,
        )
    if is_credential_name(dest.name):
        return None, _refuse(
            "refusing a credential file.",
            "Pass the sprite sheet png, not a credential file.",
            "資格情報のファイルは読まない。スプライトシートの png を渡す。",
            rel,
        )
    try:
        dest.resolve().relative_to(project.resolve())
    except ValueError:
        return None, _refuse(
            "refusing a path outside the project.",
            "Pass a regular png inside the project.",
            "プロジェクトの中の普通の png を渡す。",
            rel,
        )
    return dest, None


def project_godot_text(main_scene: str) -> str:
    """A new project only. Pixel snap is on. An existing project.godot is not rewritten."""
    return (
        "; Engine configuration file.\n"
        "config_version=5\n\n"
        "[application]\n\n"
        'config/name="Game"\n'
        f'run/main_scene="res://{main_scene}"\n'
        'config/features=PackedStringArray("4.7", "GL Compatibility")\n\n'
        "[display]\n\n"
        "window/size/viewport_width=320\n"
        "window/size/viewport_height=180\n"
        'window/stretch/mode="viewport"\n'
        'window/stretch/aspect="keep"\n'
        'window/stretch/scale_mode="integer"\n\n'
        "[rendering]\n\n"
        "textures/canvas_textures/default_texture_filter=0\n"
        "2d/snap/snap_2d_transforms_to_pixel=true\n"
        "2d/snap/snap_2d_vertices_to_pixel=true\n"
        'renderer/rendering_method="gl_compatibility"\n'
    )


def place_kit(
    project: Path,
    rel: str,
    kind: str = "walk",
    write: bool = True,
    replace: bool = False,
    dry_run: bool = False,
) -> dict:
    """Draw a walk sheet or shore tiles on this computer and place the files.

    A 3D model and a sound effect are not drawn. Audio is not sent.
    """
    if kind in ("music", "voice"):
        reply = _base_reply(rel, 0, 0, 0, 0, 0)
        reply["error"] = "music and voice are separate."
        reply["next"] = "This plugin does not create music or an NPC voice, and it does not send audio. Nothing was written."
        reply["next_ja"] = "音楽と声はここでは作らない。音声は送らない。まだ書いていない。"
        reply["wrote"] = False
        reply["paths"] = []
        return reply
    if kind == "sfx":
        reply = _base_reply(rel, 0, 0, 0, 0, 0)
        reply["error"] = "This plugin does not create a sound effect."
        reply["next"] = "This plugin does not create a sound effect, and it does not send audio. Nothing was written."
        reply["next_ja"] = "効果音はここでは作らない。音声は送らない。まだ書いていない。"
        reply["wrote"] = False
        reply["paths"] = []
        return reply
    if kind == "glb":
        reply = _base_reply(rel, 0, 0, 0, 0, 0)
        reply["error"] = "This plugin does not create a 3D model."
        reply["next"] = "This plugin does not create a 3D model. Nothing was written."
        reply["next_ja"] = "立体はここでは作らない。まだ書いていない。"
        reply["wrote"] = False
        reply["paths"] = []
        return reply
    if kind not in ("walk", "shore"):
        reply = _base_reply(rel, 0, 0, 0, 0, 0)
        reply["error"] = "missing or invalid kind."
        reply["next"] = "Pass kind walk or shore. Nothing was written."
        reply["next_ja"] = "kind は walk か shore。まだ書いていない。"
        reply["wrote"] = False
        reply["paths"] = []
        return reply
    suffix = ".png"
    dest, refused = _output_file(project, rel, suffix)
    if refused:
        return refused
    include_project = kind == "walk" and not (project / "project.godot").exists()
    if kind == "walk":
        paths = _walk_paths(rel, include_project)
    else:
        paths = [rel] + tileset_written_paths(rel, ["grass", "water", "sand", "path"])
    try:
        body, mode = approval_text(paths, replace)
    except ValueError:
        return _refuse(
            "refusing a path outside the project.",
            "Pass a regular png inside the project.",
            "プロジェクトの中の普通の png を渡す。",
            rel,
        )
    reply = _base_reply(rel, 0, 0, 0, 0, 0)
    reply["ok"] = True
    reply["wrote"] = False
    reply["kind"] = kind
    if not write:
        reply["paths"] = []
        reply["next"] = "write is false. Nothing was written."
        reply["next_ja"] = "write が false。まだ書いていない。"
        return reply
    if mode != "inline":
        reply["ok"] = False
        reply["error"] = "approval line does not fit in one message."
        reply["next"] = "Shorten the path list. Nothing was written."
        reply["next_ja"] = "承認の行が 1 通に収まらない。パスを短くする。まだ書いていない。"
        reply["paths"] = []
        return reply
    existing = [item for item in paths if (project / item).exists()]
    if existing and not replace:
        held = replace_decision(True, False)
        held["paths"] = paths
        held["source"] = rel
        return held
    reply["paths"] = paths
    reply["license"] = "CC0"
    if kind == "walk":
        reply["hframes"] = 4
        reply["vframes"] = 1
        reply["frame_count"] = 4
    assert dest is not None
    planned: list[tuple[str, str | bytes | None]] = []
    lead: dict = reply
    if kind == "walk":
        sheet_bytes = encode_png(walk_raster("CC0"))
        planned.append((rel, sheet_bytes))  # route: walk_png
        base, stem = _prefix(rel)
        shore_rel = _shore_rel(rel)
        if include_project:
            # Absent on purpose. An existing project.godot is not rewritten.
            planned.append(("project.godot", project_godot_text(f"{base}{stem}_stage.tscn")))
        walk_sink: list = []
        sliced = slice_grid(
            project,
            rel,
            16,
            32,
            kind="sprite",
            fps=8,
            names=[f"walk_{i}" for i in range(4)],
            animation="walk",
            write=True,
            emit_scene=True,
            replace=True,
            tileset_rel=f"{_prefix(shore_rel)[0]}{_prefix(shore_rel)[1]}.tileset.tres",
            guid=hashlib.md5(rel.encode("utf-8")).hexdigest(),
            png_bytes=sheet_bytes,
            sink=walk_sink,
            dry_run=True,
        )
        if not sliced.get("ok"):
            reply["ok"] = False
            reply["wrote"] = False
            reply["error"] = sliced.get("error") or "the walk did not write."
            reply["next"] = sliced.get("next") or "Nothing was written."
            reply["next_ja"] = sliced.get("next_ja") or "まだ書いていない。"
            reply["paths"] = []
            return reply
        planned.extend(walk_sink)
        shore_bytes = encode_png(shore_raster("CC0"))
        planned.append((shore_rel, shore_bytes))  # route: walk_shore_png
        shore_sink: list = []
        shore = slice_grid(
            project,
            shore_rel,
            32,
            32,
            kind="tileset",
            tile_names=["grass", "water", "sand", "path"],
            tile_coords=shore_coords(),
            tile_anim={"water": {"frames": 3, "fps": 4}},
            tile_peering=shore_peering(),
            write=True,
            replace=True,
            guid=hashlib.md5(shore_rel.encode("utf-8")).hexdigest(),
            png_bytes=shore_bytes,
            sink=shore_sink,
            dry_run=True,
        )
        if not shore.get("ok"):
            reply["ok"] = False
            reply["wrote"] = False
            reply["error"] = shore.get("error") or "the walk did not write."
            reply["next"] = shore.get("next") or "Nothing was written."
            reply["next_ja"] = shore.get("next_ja") or "まだ書いていない。"
            reply["paths"] = []
            return reply
        planned.extend(shore_sink)
        reply["foot"] = sliced.get("foot")
        lead = shore
    else:
        shore_bytes = encode_png(shore_raster("CC0"))
        planned.append((rel, shore_bytes))  # route: shore_png
        shore_sink = []
        sliced = slice_grid(
            project,
            rel,
            32,
            32,
            kind="tileset",
            tile_names=["grass", "water", "sand", "path"],
            tile_coords=shore_coords(),
            tile_anim={"water": {"frames": 3, "fps": 4}},
            tile_peering=shore_peering(),
            write=True,
            replace=True,
            guid=hashlib.md5(rel.encode("utf-8")).hexdigest(),
            png_bytes=shore_bytes,
            sink=shore_sink,
            dry_run=True,
        )
        if not sliced.get("ok"):
            reply["ok"] = False
            reply["wrote"] = False
            reply["error"] = sliced.get("error", "")
            reply["next"] = sliced.get("next") or "Nothing was written."
            reply["next_ja"] = sliced.get("next_ja") or "まだ書いていない。"
            reply["paths"] = []
            return reply
        planned.extend(shore_sink)
        lead = sliced
    clause, blocked = rewrite_files(project, planned, True)
    if blocked:
        reply["ok"] = False
        reply["wrote"] = False
        reply["error"] = blocked
        reply["next"] = "Nothing was written."
        reply["next_ja"] = "まだ書いていない。"
        reply["paths"] = []
        reply["approval"] = ""
        return reply
    named = _fit_approval(body, clause)
    if named is None:
        reply["ok"] = False
        reply["wrote"] = False
        reply["error"] = "could not name every value a replace would drop."
        reply["next"] = "Nothing was written."
        reply["next_ja"] = "消える値を名指しできない。まだ書いていない。"
        reply["paths"] = []
        return reply
    reply["approval"] = named
    if dry_run:
        reply["wrote"] = False
        reply["next"] = lead.get("next") or IMPORT_CMD
        reply["next_ja"] = lead.get("next_ja") or ""
        return reply
    clause, blocked = rewrite_files(project, planned, False)
    if blocked:
        reply["ok"] = False
        reply["wrote"] = False
        reply["error"] = blocked
        reply["next"] = "Nothing was written."
        reply["next_ja"] = "まだ書いていない。"
        reply["paths"] = []
        reply["approval"] = ""
        return reply
    if clause is None:
        reply["ok"] = False
        reply["wrote"] = False
        reply["error"] = "could not name every value a replace would drop."
        reply["next"] = "Nothing was written."
        reply["next_ja"] = "消える値を名指しできない。まだ書いていない。"
        reply["paths"] = []
        return reply
    reply["wrote"] = True
    reply["ok"] = True
    reply["next"] = lead.get("next") or IMPORT_CMD
    reply["next_ja"] = lead.get("next_ja") or ""
    return reply


def _shore_rel(rel: str) -> str:
    base, stem = _prefix(rel)
    return f"{base}{stem}_tiles.png"


def tileset_written_paths(rel: str, tile_names: list[str] | None) -> list[str]:
    """Spacing 0 with opaque edges writes the gap png and its meta, not the source meta."""
    base, stem = _prefix(rel)
    paths = output_paths(rel, "tileset", False, tile_names)
    extrude_rel = f"{base}{stem}.extruded.png"
    paths = paths + [extrude_rel, f"{extrude_rel}.import"]
    source_meta = f"{base}{stem}.png.meta"
    return [f"{extrude_rel}.meta" if item == source_meta else item for item in paths]


def _walk_paths(rel: str, include_project: bool) -> list[str]:
    shore = _shore_rel(rel)
    paths = ["project.godot"] if include_project else []
    paths.append(rel)
    paths.extend(output_paths(rel, "sprite", emit_scene=True))
    paths.append(shore)
    paths.extend(tileset_written_paths(shore, ["grass", "water", "sand", "path"]))
    return paths
