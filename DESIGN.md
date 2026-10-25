# Sprite sheets and tilesets

Original plan: limit cells to the squares 8, 16, 32, 48, and 64, split the PNG apart with Pillow, and write a custom JSON. Do not launch Godot or Unity, and do not write `.meta` or a region resource.

What changed: a cell takes width and height separately. Margin, spacing, origin, fps, per-frame duration, trim, and extrude are arguments. The output path is decided from the PNG stem. `same_mask`, `solid_cell`, `transparent_rgb`, and `loose_part` are warnings, and they do not drop `ok`. When the frame count exceeds 4096, return `truncated` and `total`, and write neither pixels nor rectangles. Unity's pixels per unit is 32 for the hero and for the tiles. The scene stays open. Measuring that the frames advanced exits only when the user launches Godot with `--probe`.

Reason: the trial sheet is 4 bodies of 16×32. A square of 16 cuts the torso, and a square of 32 turns the neighboring 2 bodies into 1 image. The foot reads the opaque bottom row of each frame. What the engine reads is the rectangle on the sheet.

The plugin is `plugin.yaml`, `SKILL.md`, `__init__.py`, and `queries_eval.json` in the same directory. The 10 blind queries were written by a separate agent from one sentence only. The maker did not edit the queries. `trial/` here is the real artifact that replayed that contract on Godot 4.7.2. `slice_grid` does not launch Godot, and writes the SpriteFrames and TileSet text in that call. `build.gd` is the check that reopens that text after import and looks at the terrain paint and `tile_size`.

## Scoring view

| Axis | View |
|---|---|
| Ask | Cut a 2D sprite sheet and tileset from a PNG inside the project |
| Gap | The catalog has no entry that writes a grid sheet as an engine region |
| This Mac | Godot 4.7.2.stable.official.ed1daf0bf. No download and no account. Pillow is used only for pixel tests |
| Surfaces | 2 tools. A write is 1 approval |
| Disclosure | No destination. No key. The place written is only inside the project |
| Upstream | Godot region resources and Unity's TextureImporter. Pillow is not upstream |
| Search terms | The maker does not write the 10 blind queries. See "Search" below |

Why writes go into v0.1: without a region file, the engine does not treat the sheet as frames. A sprite with margin 0 and `write` true writes SpriteFrames and a Unity Multiple, and does not rewrite the original PNG bytes. Files are left unwritten only when `write` is false. The paths written match the list of the single approval. When the approval line exceeds 1500 characters, approve one list file and write the files. Only when that one line also does not fit, write nothing.

## Plugin

- Name: `cut-sprite-sheet` (an engine trademark does not go in the name. The catalog file is `cut-sprite-sheet.yaml`)
- `requires_hermes: ">=0.21.6"` (the default for a new plugin. There is no MCP, so `trust` is not set)
- Dependencies: the standard library only. Pillow is not put in `python_dependencies`. The README does not contain an install command for a dependency
- The tested OS is macOS only. Linux and Windows are "untested" in the README
- The skill frontmatter does not contain `requires_toolsets` or `requires_tools`
- There is no scheduled run. Do not make an Automation Blueprint or a cron
- There are no credentials. Nothing is read from an environment variable or from `get_secret`

There are 3 tools. The first sentence of a description is within 60 characters, and it does not start with `Read-only`. `Cut` goes only in the first sentence of `slice_grid`.

| Tool | First sentence | Writes | Approval |
|---|---|---|---|
| `inspect_grid` | `Read a sprite sheet or tileset png grid, frames, defects.` | no | does not ask |
| `slice_grid` | `Cut and slice a sprite sheet or tileset png for 2D.` | yes. Unwritten only when `write` is false | once when writing |
| `place_kit` | `Place a walk cycle or shore tiles in the game.` | yes | once when writing |

`inspect_grid` continued: Use it when a 2D game needs the width, height, frame count, and defects of a sprite sheet or a tileset.

`slice_grid` continued: Writes Godot SpriteFrames or a TileSet, a Unity .meta, and import sidecars for that png, and asks once.

Arguments are finite. `cell_w` and `cell_h` are integers from 1 through 4096, passed separately. They are not an enumeration of squares. `margin_x`, `margin_y`, `spacing_x`, and `spacing_y` are 0 or greater. Margin is the top-left only. Opaque pixels left on the right and the bottom drop `ok` as outside the grid. If they are transparent only, `ok` stays true. The column count is `(width - margin_x + spacing_x) // (cell_w + spacing_x)`, and the row count uses the same formula. `origin` is `top_left` or `bottom_left`. When `columns` is passed, a value larger than the computed column count is a failure. At or below the computed column count, cut only that many columns. When omitted, it becomes the computed column count. `total` is the number of frames cut, and `frame_count` is that same number. Cutting 120×32 at 16×32 makes 7 columns. 72×34, margin 2, spacing 2, cell 16×32, is 4 columns and 1 row.

`slice_grid` also takes `kind` (`sprite` or `tileset`), `fps` (from 1 to 60), per-frame `durations`, `trim`, `extrude_px` (0 or 1), `animation`, `foot_x`, `foot_y`, `replace`, `emit_scene`, and the tile `tile_names` and `tile_coords`. When `fps` is below 1 or above 60, return a failure before writing files. When `tile_coords` for `tile_names` is missing, also return a failure before writing.

The limit of one edge is 4096. When the frame count exceeds 4096, `truncated` is true, `total` is the full count, and `ok` is false. That reply is returned before rectangles are built. 64 frames is not a cutoff. The horizontal column count is not capped at 16 either.

When `trim` is true, write the opaque-pixel range into `trim_bounds` of the slice json, and the `Rect2` of `AtlasTexture` is that range. The range includes both ends, so the width is `max_x - min_x + 1`. The acceptance scene does not trim. When trimmed, Godot's `Rect2` and Unity's rect are the same opaque range, and the foot is placed at the trimmed coordinates of the first frame.

`extrude_px` is 0 or 1. When spacing is 1 or more, copy 1px of the edge pixels into the gap of a separate png. The original PNG bytes do not change. When spacing is 0 and a tileset whose edges are opaque has 2 or more cells, add a 1px gap on a separate png and copy the edges and the corners into the gap. Then the json spacing is 1 and the margin is 0, and the TileSet points at that separate png. A 1-cell tileset does not get a gap. `.meta` `spriteExtrude` is always 0. Unity Extrude Edges is mesh margin, not texel padding. The `.meta` rectangles stay in the original PNG coordinates.

Reply keys are only the following. Pixels, colors, and image bytes are not included.

`ok`, `error`, `next`, `next_ja`, `truncated`, `total`, `source`, `as_of`, `width`, `height`, `cell_w`, `cell_h`, `columns`, `rows`, `frame_count`, `hframes`, `vframes`, `defects`, `width_divisors`, `height_divisors`, `suggest_cell_w`, `suggest_cell_h`, `extrude_px`, `paths`

`source` is a relative path inside the project, and `as_of` is the file modification time. The words that drop `ok` on failure are `indivisible`, `split_line`, `multi_body`, a column count larger than the computation, an invalid origin, an edge over the limit, a frame count over the limit, a broken PNG, and opaque pixels left outside the grid. Warnings are `same_mask`, `solid_cell`, `transparent_rgb`, `loose_part`, `extrude_clamped`, and the tile `tile_edge`. `ok` is true, `error` is empty, and `next` states the next step. The `next` on `ok` adds one sentence that sets the node's texture filter to Nearest. A body that crosses a boundary by even 1 pixel is `split_line`. A cell that is fully opaque is not counted as cut. A tileset may touch at the edges. When `kind` is tileset, edge contact is the warning `tile_edge`, and the next step is to add 1px of spacing or to cut with the current cell. The whole sheet is not made into 1 cell. Edge contact of a sprite stays `split_line`. A silhouette with the same shape and the same color is not treated as a color swap. If there is no transparency and the color is the same, it is not `same_mask`. A suggestion is, among divisor grids that put one body in one cell, the one with less empty space and a larger area. Only when no such grid exists is the suggestion 0×0, and the next step is `Do not use 0x0`. When a cell can be returned to, write that width and height, and do not write 0×0. A 1-pixel gap inside a body can fail to fit one grid and become 0×0.

`inspect_grid` reads only an ordinary PNG inside the project. The implementation that reads it is the standard library. A PNG whose chunk CRC does not match is not read. In addition to `tEXt`, the text of `iTXt` and `zTXt` is read. An absolute path, `..`, a symbolic link, a path that resolves outside the project, and anything other than png are refused before the contents are read. Credentials are checked on the file name and on the name with the extension removed. A name that starts with `.env`, `id_rsa.png`, `credentials.png`, `secrets.json`, and the extensions `.pem` `.key` `.p12` `.pfx` are refused. `secret_door.png` and `secretary.png` are read. A partial match on the name does not refuse.

16-bit and interlaced images return `error` and `next` without printing an exception. Indexed color and gray are unpacked to RGBA before the mask is read.

## Approval and refusal

Write approval is once. Sprites and tiles are not asked separately. The approval text is one line, with no newline and no backtick. The relative paths to write are joined by spaces. On `replace`, `replace` is placed at the start of the line. On a re-cut, alignment, pivot, and border are kept for sprites whose names match in the existing `.meta`. The fileID and guid calculation does not change. Alignment, pivot, and border of sprites whose names do not match, and `.tres` lines that disappear when replaced, are named on that same approval line. When they cannot be named, nothing is written. When no value disappears, a line over 1500 characters approves only one list file that writes the paths one per line, and the files are written. Only when that one line also does not fit, nothing is written. The contract `dry_run` returns that line and does not create files. The plugin shows that line once on the Hermes approval screen. It writes only for `once`. Choosing always covers only the same call (the hook returns a per-plan `rule_key`). There is no `confirm`.

Paths are decided from the stem of the input PNG. A sprite for `sprite_sheet/hero_sheet.png` is `sprite_sheet/hero_sheet.spriteframes.tres`, `hero_sheet.png.meta`, `hero_sheet.png.import`, and `hero_sheet.slice.json`. When `emit_scene` is set, `hero_sheet_stage.gd` and `hero_sheet_stage.tscn` are added. A tileset is `tiles.tileset.tres`, plus a `.asset` and `.asset.meta` for each terrain. This tres is written as text by the call that was approved. A second `npc.png` takes the stem `npc` and does not point at the first file.

The `slice_grid` list does not include the existing `project.godot`, `build.gd`, or the split-apart PNGs. Only when `place_kit`'s `walk` has no `project.godot` does that approval include one minimal `project.godot`. It has integer-multiple stretch, the default filter 0, and both 2D snaps. An existing `project.godot` is not changed. The original PNG bytes are not rewritten by extrude or by adding a gap.

Files are left unwritten only when `write` is false. A sprite with margin 0, spacing 0, and `write` true writes SpriteFrames and a Unity Multiple. The trial hero returns the following.

```
next: No margin and no spacing. SpriteFrames and a Unity Multiple slice were written. hframes is 4 and vframes is 1. Set the node's texture filter to Nearest. License text is not a known free license. It was copied and not rewritten. godot --headless --editor --quit --path <project>
```

A sheet that has margin or spacing returns that `hframes` does not see the margin, so use the slice. The next step for the trial margin 2 and spacing 2 is `Margin is 2,2 and spacing is 2,2. hframes ignores margin, so use the slice. Set the node's texture filter to Nearest. License text is not a known free license. It was copied and not rewritten. godot --headless --editor --quit --path <project>`.

A PNG with no `License`, `license`, `Copyright`, `copyright`, or `SPDX-License-Identifier` is written. `next` says that no rights are attached. An empty Copyright still passes when License is CC0. An empty value, `unknown`, All Rights Reserved, proprietary, non-commercial, CC-BY-NC, CC-BY-ND, and `無断転載禁止` stop at 0 bytes. CC0, CC-BY (neither NC nor ND nor SA), MIT, Unlicense, and public domain are seen at a word boundary and copied. CC-BY-SA is copied, and share-alike is written in `next`. `Smith`, `limited`, `not public domain`, `trial sheet`, and `no third-party` are not treated as a free mark. Any other non-empty text is copied, and `next` says the license is unknown. A boilerplate license text is not invented.

A writing `slice_grid` / `place_kit` returns `{"action": "approve", "message": <1 line>}` from `pre_tool_call`. Hermes shows the approval screen for CLI, the gateway, and Desktop. yolo and approvals off skip that approval on the spot (`tools/approval.py` `_run_approval_gate`). cron, `-q`, and unattended sessions default to deny (`approvals.cron_mode` and the rest). Any other non-interactive session with no person is fail-closed. The plugin does not read Hermes's private internals. Choosing always covers only the same call (the hook returns a per-plan `rule_key`). If the file changed after the preview, it is not written. `plugins.isolation: host` is not required. Do not write that it runs only under host isolation.

It is enabled on every surface by default. A person who is in a gateway room can call the tools the agent can call. The way to stop them is `hermes tools`. No cron remains after it is removed. Project files written after approval remain after the plugin is removed.

Overwrite is off by default. It writes only when `replace: true`. The approval line starts with `replace` and the target path, and names a disappearing value on that line when one exists.

## One sequence with the engine

The plugin launches neither Godot nor Unity. An existing `project.godot` is not changed. `@tool` is not added. Opening the scene alone does not run the scene script.

1. The user or `place_kit` places a PNG inside the project. The picture is drawn on the spot, with nothing fetched. The hero is 64×32. The frames are 4 images of 16×32, in the order contact, pass, contact, pass. The 4 bodies have different shapes, and each frame is one connected component. The opaque bottom row of all 4 frames is y=31, and the supporting foot does not move from there. The passing frame lifts the other foot. The foot measures `(8, 32)`. Even with margin 0 and spacing 0, SpriteFrames and a Unity Multiple are written, and the original PNG bytes remain. A solid model and a sound effect are not made. Generated 3D and sound effects are another plugin's work. `walk`, in the same approval, writes the shore tiles under the foot and a `project.godot` only when it is missing. The tiles are 256×96. Each of the 16 grass bits is a different picture, lined up in columns 0 through 7 and in rows 0 and 1. Full grass is bit 15 at `(7, 1)`. Row 2 is 3 water frames, sand, and a path. Water has no collision. The Unity side of the grass is a RuleTile of 16 rules. Music and voice are not made, and audio is not sent.
2. `inspect_grid` returns the dimensions, the count, and the defect codes. 16×32 on this sheet is `ok: true`, 4 frames, `hframes` 4, `vframes` 1. A square of 16 is `split_line`, and the next step names `cell_w 16` and `cell_h 32` separately. 24×24 cuts a body, so it suggests 16×32 and does not return the divisor list. 48×40 does not divide, and it returns the divisor list. It is not rounded to a square of 16 or of 32. 32×32 has 2 bodies in 1 cell, so it is `multi_body`, and no file is written. A sheet where the left and right bodies touch by only 1 pixel is also `split_line`, and it suggests a cell that covers that body. A 64×64 with 8 bodies in 2 rows, read at 16×16, suggests 16×32.
3. Even with margin 0, spacing 0, and `write` true, `slice_grid` writes the slice json and Godot SpriteFrames. A sheet that has margin or spacing does the same. Tiles write `tiles.tileset.tres`. The tile json count is the number of grid rectangles, and the trial sheet is 24. `animation` is empty, `foot` is not placed, `durations` is empty, and `unity_water` is `animated_tile`. The json of a sprite that has margin has `foot` and the animation name that was passed. It is not copied into default. Multiple rows get a different name per row. `Rect2` is the opaque range only when trimmed, and that offset is put back at the cell position by the AtlasTexture margin. `texture_region_size` and `TileSet.tile_size` are both the cell, and the trial tile is `Vector2i(32, 32)`. The terrain mode is `MATCH_SIDES` (2). A terrain that was given a shore mapping is placed at a separate atlas coordinate per bit. A terrain that was not given one is 1 cell, and 16 copies are not made. This is not a copy of an autotile. Painting a 3×3 with grass becomes 9 cells, and the picture coordinates are 2 or more kinds. Collision is a polygon of half the cell on the four sides, and water has 0 polygons. The water sequence is frames 3 and fps 4, and omitting columns makes columns the same as frames. duration keeps the length of each frame.
4. The same write writes Unity's `.meta`. `serializedVersion: 11`, `spriteMode: 2`, `filterMode: 0`, `spriteMeshType: 0` (Full Rect), `spriteExtrude: 0`, `spritePixelsToUnits: 32`, `alphaIsTransparency: 0`, `spriteID`, `internalID`, `nameFileIdTable`, class 213 of `internalIDToNameTable`, `platformSettings`, `spriteBorder`, `textureCompression: 0`, `enableMipMap: 0`. The hero alignment is 7, and the pivot is bottom center. The tile alignment is 0, and the pivot is the cell center. y is 0 at the bottom edge of the image. A terrain with 2 or more shore mappings is a RuleTile, one rule per bit, and grass is 16 rules. Right is (1, 0), down is (0, -1), left is (-1, 0), and up is (0, 1). The default collision is 2 for ground and 0 for water. A terrain with 1 mapping or fewer is a Tile, and the script reference is `fileID: 13312`. Water is an Animated Tile and points at 3 frames. The package is com.unity.2d.tilemap.extras. Godot's TileSet also keeps the 3 water frames. `maxTextureSize` is 4096. Unity 6000.6.6f1 on macOS kept the walk sheet's internalID after it was closed and opened again.
5. `.import` is `compress/mode=0`, `mipmaps/generate=false`, `process/fix_alpha_border=false`. The path puts `md5("res://"+relative path)` into dest. A new sidecar does not write a uid. On a re-cut, only the `uid://` line that Godot left is kept. The value Godot 4.7 writes first when there is no sidecar is `fix_alpha_border=true`, so false is written first. After import, the bytes of a PNG that was not extruded, and `project.godot`, are unchanged.
6. The trial scene is `sprite_sheet/hero_sheet_stage.gd` and `hero_sheet_stage.tscn`. The text that `slice_grid`'s `emit_scene` writes and the text used for measurement are the same. References are `res://sprite_sheet/`. No audio file is referenced. `TEXTURE_FILTER_NEAREST` is assigned on the AnimatedSprite2D and the TileMapLayer that were created. Even when the project default is Linear, this assignment does not blur. If they differ, it fails before `PLAY`, and the next step is that one line. The passing line does not show `filter=` or `snap=`. The trial `project.godot` is 320×180, with integer-multiple stretch and 2D snap.
7. The default scene stays open. On this Godot 4.7.2, `OS.has_feature("headless")` is false even with `--headless`, so it is read from `DisplayServer.get_name()`. In a window, the whole tree is not quit. The tile under the foot is read with `local_to_map`. If it is empty on the boundary, look 1px lower. If it is still empty, fail before `PLAY`. The foot is at the center of the screen, `(160, 90)` on 320×180. Because the walk is seen from the side, the foot sits on the top edge of the tile. The map is placed so the top edge of the grass cell meets the foot, and the map is added as a child first. The sprite is in front of the map at `z_index` 1. A floating frame prints `warn: a frame does not meet the ground.`, leaves the scene, and does not stop before `PLAY`. next is `The scene still plays. A floating frame is allowed.` The bottom row of the 4 frames drawn here stays y=31. A frame in contact is `foot_px=31`. When SpriteFrames is missing, frames advance on the fps interval. They do not advance on every process frame. Only with `--probe` or the environment variable `SPRITE_SHEET_PROBE=1`, frames are watched for about 0.8 seconds, and if `frames_seen` is under 2, exit code 2 is returned without printing `PLAY`. Only when it passes, `PLAY` is printed and the process exits with code 0. The line includes `foot=160,90`, `foot_px=31`, `cell=0`, `tile=grass`, `nearest=true`, and `water_frames=3`. `frame` at exit is not fixed. `changes` is the number of times the frame changed.
8. Play is a separate process, `godot --headless --path`. The Godot plugin's `run_game` is not_live unless the editor helper is alive, and headless does not count as having played. Do not write that it was played while disconnected. The `PLAY` above is printed even if the text tres is imported without deleting it and `build.gd` is not run. `build.gd` does not overwrite the text tileset. A grass 3×3 is 9, the picture coordinates are 2 or more kinds, and the center is `(7, 1)`. Water is 1 cell with 3 frames and collision 0. The right edge of the grass faces grass. `tile_size` is 32×32.

Measurement on this Mac:

```
godot --headless --path <project> -- --probe
```

```
PLAY frame=1 frames_seen=4 changes=6 anim=walk foot=160,90 foot_px=31 cell=0 tile=grass nearest=true water_frames=3
```

The same scene, with SpriteFrames removed and put back on a Sprite2D, is `PLAY frame=2 frames_seen=4 changes=7 anim=walk foot=160,90 foot_px=31 cell=0 tile=grass nearest=true water_frames=3`. Playback after `place_kit`'s `walk` is written into an empty folder is that same latter line, because every duration is 1.

A sheet with margin is cut by the same formula. The trial `padded_sheet.png` is 74×36, margin 2, spacing 2, cell 16×32, becomes 4 frames, and is `ok: true`.

The license copies the PNG text into the slice json. A boilerplate is not invented as a license. Cutting out frames does not create a new right. The source is a relative path. The trial tEXt is `Trial sheet drawn for this design. No third-party artwork.`

The Unity editor has not been launched, because that touches the license and the account. The contents of `.meta` are checked as text. The rectangles after the editor opens them again have not been looked at.

## Disclosure draft (catalog)

```
pixel art sprite sheet cutter. png to tileset splitter. cut pixel art into game tiles. sprite sheet from pixel png. 2d walk cycle sprite sheet. tileset cutter for pixel art. split png into sprite sheet. shore tiles tileset tool. pixel art walk cycle sheet. png sprite and shore tiles. Cuts a pixel-art png into frames. Tools: inspect_grid, slice_grid, place_kit for a 2D game. Disclosure — The png stays on this computer. Nothing is sent. No API key. No daily cap. A gateway room can call the tools. Stop them with hermes tools. One approval on one line via pre_tool_call. Choosing always covers only the same call. An oversized line writes one list file. A failed check writes nothing. Hermes yolo and approvals off skip that prompt. cron, -q, and unattended sessions default to deny. Empty, unknown, or a restrictive license is not written. Unknown text is copied and next warns. CC-BY-SA is copied and next names share-alike. No license chunk still writes and next says no rights are attached. Import once or play fails: godot --headless --editor --quit --path <project>. No solid-color box and no sound effect. Does not launch Godot or Unity. Play may write app-userdata. Uninstall leaves no cron job. Linux is untested. Unity editor 6000.6.6f1 on macOS kept the walk-sheet fileIDs after a reopen. スプライトシートとタイルセットを切る。
```

## Failure examples (verbatim on this Mac)

Does not divide:

```
error: cell 48x40 does not divide image 64x32.
next: Width divisors: 1, 2, 4, 8, 16, 32, 64. Height divisors: 1, 2, 4, 8, 16, 32. 次: 幅の約数は 1, 2, 4, 8, 16, 32, 64。高さの約数は 1, 2, 4, 8, 16, 32。
```

A square that cuts a body:

```
error: cell 16x16 cuts a sprite body.
next: Cover each body with cell_w 16 and cell_h 32. 次: 体を割らないセルは幅 16、高さ 32。
```

Two bodies in one cell:

```
error: cell 32x32 holds more than one body.
next: Cover each body with cell_w 16 and cell_h 32.
```

Column count larger than the computation:

```
error: columns 8 does not match the sheet (4).
next: Pass columns 4, or omit columns.
```

Frame count over the limit:

```
error: frame count exceeds 4096.
next: Use a larger cell. total is the full frame count. Nothing was written.
```

A broken PNG (including one whose CRC does not match):

```
error: png did not parse.
next: Pass a png file. The bytes were not read as an image.
```

Same shape with a different color (warning. `ok` is true. `error` is empty):

```
next: Masks match, so this is a color swap. The frames are still cut. Set the node's texture filter to Nearest. 次: 形が同じなので色の差し替え。コマはそのまま切る。ノードの texture filter を Nearest にする。
```

One flat color (warning. `ok` is true. `error` is empty):

```
next: A cell is one flat color. The cell is still cut. Set the node's texture filter to Nearest. 次: セルが単色。セルはそのまま切る。ノードの texture filter を Nearest にする。
```

Color on a transparent pixel (warning. `ok` is true. `error` is empty):

```
next: Zero the RGB of transparent pixels, or write the sheet with this defect. Keep fix_alpha_border off. Set the node's texture filter to Nearest. 次: 透過画素の RGB を 0 にするか、この欠陥のまま書く。fix_alpha_border はオフのままにする。ノードの texture filter を Nearest にする。
```

A small separate part (warning. `ok` is true. `error` is empty):

```
next: A small separate part is in the cell. The frame is still cut. Set the node's texture filter to Nearest.
```

Symbolic link:

```
error: refusing a symlink.
next: Pass a regular png inside the project. 次: シンボリックリンクは拒否した。プロジェクトの中の普通の png を渡す。
```

Outside the project:

```
error: refusing a path outside the project.
next: Pass a regular png inside the project. 次: プロジェクトの中の普通の png を渡す。
```

Overwrite:

```
error: output already exists.
next: Pass replace true to overwrite that path. Nothing was written. 次: 出力が既にある。置き換えるなら replace を true にする。まだ書いていない。
```

No import (exit code 2):

```
error: no import sidecar for the png.
next: godot --headless --editor --quit --path <project>. Then play res://sprite_sheet/hero_sheet_stage.tscn again. 次: png の import が無い。Godot でプロジェクトを取り込んでから、res://sprite_sheet/hero_sheet_stage.tscn を再度再生する。
```

A sidecar only, with no import result (exit code 2):

```
error: png did not load.
next: godot --headless --editor --quit --path <project>. Then play res://sprite_sheet/hero_sheet_stage.tscn again. 次: png を読めなかった。Godot でプロジェクトを取り込んでから、res://sprite_sheet/hero_sheet_stage.tscn を再度再生する。
```

No region resource (exit code 2):

```
error: region resource is missing.
next: Build the SpriteFrames and the TileSet from the slice json, then play again.
```

fps out of range (no file is written):

```
error: fps must be from 1 to 60.
next: Pass fps from 1 to 60. Nothing was written.
```

An empty or restricted license (no file is written):

```
error: png license text is empty or restricted.
next: That sheet is not written.
```

No water frames (no file is written):

```
error: missing or invalid frames.
next: Pass frames as described. columns is optional. Nothing was written.
```

Opaque pixels left outside the grid (no file is written):

```
error: cell 16x16 leaves 4 opaque pixels outside the grid.
next: Crop the sheet or pick a cell that covers those pixels. Width divisors: 1, 2, 4, 5, 10, 20. 次: 格子の外に不透明画素が 4 ある。シートを切るか、画素を覆うセルにする。幅の約数は 1, 2, 4, 5, 10, 20。
```

Neither the one approval line nor the list file fits (no file is written):

```
error: approval line does not fit in one message.
next: Shorten the path list. Nothing was written.
```

A re-cut cannot name every value that would be dropped (no file is written):

```
error: could not name every value a replace would drop.
next: Nothing was written.
```

No terrain coordinates (no file is written):

```
error: tile_coords is missing.
next: Pass tile_coords for every tile name. Nothing was written.
```

A floating frame (exit code 0. The scene remains):

```
warn: a frame does not meet the ground.
next: The scene still plays. A floating frame is allowed. 次: シーンは残す。浮いたコマも再生する。
```

The skill's `## When a call fails` writes each marker above and the next step, one line each. Do not compose `ok: false` to pass a test. The same sentences are in `failure_samples.json`.

## Search

Tool Search picks up English only. Write this in the skill, with the English sentence first. Even a Japanese request is searched in English by tool_search. Example: sprite sheet, tileset, cut png, slice, pixel art, 2D game. 日本語の頼みでも tool_search は英語で探す。例: sprite sheet, tileset, cut png, slice, pixel art, 2D game

The catalog description places sprite sheet, tileset, pixel art, and 2D game inside the lead sentences above. Japanese after that states the fact. スプライトシートとタイルセット Do not add a dangling sentence made only of synonyms.

The 10 blind queries were written by giving a separate agent, not the maker, only the following one line. The maker did not read that file and did not edit the queries.

```
Cut a grid png into a sprite sheet and a tileset for a 2D game.
```

Those 10 queries are placed in `queries_eval.json` as they are.

## Manifest

The slice json writes the relative path of the original file, the license copied from the PNG text, that cutting does not create a new right, `trim_bounds`, `durations`, `foot` for a sprite only, and `extrude_px`. The trial picture is not a third party's material. `place_kit` places the walk and the shore on this computer. It does not make a solid model or a sound effect. It does not make music or voice, and it does not send audio. It does not write `manifest.json`.

## What goes in the README

Linux and Windows are untested. Unity 6000.6.6f1 on macOS kept the walk sheet's fileID after it was closed and opened again, and the Animation and Prefab references did not break. On Godot 4.7.2 on macOS, the test covered headless import and `--probe` playback. Screen pixels were not looked at, because the run is headless. The foot is seen from the opaque bottom row of each frame and from the coordinates the probe prints. The scene does not exit by itself. Only with `--probe` does it watch the frames and exit.

Write `process/fix_alpha_border=false` before import. A new sidecar does not get a uid line. On a re-cut, only the uid that Godot left in the file after import is kept. `spriteExtrude` stays 0. This is mesh margin, not texel padding. Extrude when spacing is 1 or more keeps the original PNG and copies into the gap of a separate png. pixels per unit is the cell height, and the trial cell is 32. `spriteMeshType` is 0 (Full Rect). The end of `spriteID` is `0800000000000000`, and it is not the MD4 of the sprite name. Write class 213 of `internalIDToNameTable`. A terrain peering bit is written to a separate atlas coordinate for each bit. A terrain with no shore mapping is 1 cell. The Unity side of water is 3 frames of an Animated Tile. `maxTextureSize` is 4096. The procedure is also written in README.md.

## Build-stage gates

- Install into a temporary HERMES_HOME, and count the steps and the time until the first request. The install destination is the directory that contains `plugin.yaml`
- Write approval is once, and the paths on the screen match the files that are actually created. Paths are decided from the PNG stem. A list over 1500 characters approves one list file and writes. A PNG with no license chunk is written. An empty license and a restricted license are not written
- Hit overwrite refusal, a path outside the project, a symbolic link, and a credential file name, on the real files. `secret_door.png` is not refused
- The 4 frames of 16×32 have different masks. A square of 16 is refused because it cuts a body, and the next single call can return to 16×32. 24×24 also cuts a body. 48×40 is the only one that does not divide. The divisor next step does not round to a square. 32×32 is not written
- Reopen the `.tres` written as text. The `Rect2` of a sheet that has margin, `tile_size` and `texture_region_size` of 32×32, separate shore cells, water collision 0, and the water animation columns remain. The terrain paint is a grass 3×3 of 9, and the picture coordinates are 2 or more kinds
- An existing `project.godot` is not rewritten by the plugin. On a project that does not have one, the `walk` approval includes one minimal file. With `--probe`, `frames_seen` is 4, the foot is the center of 320×180, `foot=160,90`, `foot_px=31`, `cell=0`, `tile=grass`, `nearest=true`, `water_frames=3`, and the exit code is 0. The foot sits on the top edge of the tile, and the sprite is in front of the map. The exit code is 0 even when the project default is Linear. If even one frame does not meet the ground, warn and exit with code 0
- Before import, the exit code is 2. An exit code of 0 with no `PLAY` line does not count as success
- The 10 blind queries are in `queries_eval.json`. The maker did not edit the queries
- Do not put an in-house path, or an internal name that points at the plugin, into a published file
- The stage that checks on stable Hermes comes after the plugin is installed. A run of a real model is done only with an empty HOME and inside the cage
