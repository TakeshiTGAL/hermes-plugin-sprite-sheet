# Sprite sheet and tileset

Read a sprite sheet or tileset png grid, frames, defects. Cut and slice a sprite sheet or tileset png for 2D. Place a walk cycle or shore tiles in the game.

## When to use

Use this skill when a 2D game needs a sprite sheet or a tileset, or a walk cycle with shore tiles. This plugin does not create a 3D model or a sound effect. Pixel art stays on this computer.

`tool_search` matches English words only. Search for `sprite sheet`, `tileset`, `cut png`, `slice`, `pixel art`, `2D game`, `godot`, `unity`, `walk cycle`, or `shore`. A Japanese request such as スプライトシートを切って still searches those English words. Do not search in Japanese.

If you already know the name, call `tool_describe` for `inspect_grid`, `slice_grid`, or `place_kit`, then call that tool. Do not open the png with the built-in file tools. The tools do not launch Godot or Unity. After the files exist, run `godot --headless --editor --quit --path <project>` once, then play the stage. Do not ask the user to open the Godot window. Unity Editor 6000.6.6f1 on macOS kept the walk-sheet fileIDs after a reopen. Read README.md for that order.

## Procedure

1. If the user has a png, cut that png. Ask for the project directory and the path inside it, such as `sprite_sheet/hero.png`. This is the first procedure. Do not start with `place_kit`.
2. Call `inspect_grid` without `cell_w` and `cell_h` to read `suggest_cell_w` and `suggest_cell_h`. That call does not cut. Then pass both sizes to `slice_grid`.
3. Call `slice_grid` once. Hermes shows the project-relative paths on one line from the `pre_tool_call` hook. That is the one approval. Do not echo the line back as a second argument.
4. A tight sheet, margin 0 and spacing 0, still gets SpriteFrames and a Unity Multiple slice when `write` is true. The png bytes stay. `write` false writes nothing.
5. A tileset needs `kind` `tileset`, `tile_names`, and `tile_coords`. Water animation is `tile_anim` with `frames` and `fps`. `columns` is optional. A shore map is `tile_peering`: each neighbor bit is a different column and row. Without that map the terrain is one tile. When the cells touch, the tileset uses a separate png with a 1px gap. The slice json names that gapped png. The source png bytes stay.
6. `emit_scene` defaults to true and writes a stage. The foot sits on the top edge of the tile, and the sprite is drawn in front of the map. A floating frame warns and the scene still plays. The sprite and the tile map are Nearest. The project default can stay Linear. Set both pixel-snap flags yourself when `project.godot` already exists.
7. `names`, `guid`, and `ppu` are optional. Omit `foot_x` and `foot_y` to measure the foot. `write` false writes nothing.
8. Only when the user has no png, call `place_kit`. `kind` `walk` writes a 4-frame sheet, shore tiles, and the stage. `kind` `shore` writes shore tiles. This plugin does not create a 3D model or a sound effect. Music and voice are not created here, and audio is not sent.

`write` false returns the grid and writes nothing.

## Approval

One write, one line, from the `pre_tool_call` hook. Hermes puts that line on the approval screen. The line lists the paths the call will create. A long list is a count and the first paths. No backticks and no line break. `replace` true starts the line with `replace`. A replace keeps each sprite's alignment, pivot, and border when the name still matches. fileID and guid stay on the same calculation. A sprite name that will not match, and any `.tres` line the new text will not keep, is named on that same line. If those values cannot be named, nothing is written. When nothing would be dropped, a line that would not fit is one list file, and the files are still written. If even that one line does not fit, nothing is written.

`inspect_grid` and `write` false do not ask. After a yes, the handler checks the preview again and writes nothing if the files changed. Choosing always covers only the same call (the same arguments) on later turns. Hermes yolo and approvals off skip the prompt. Cron, `-q`, and unattended sessions default to deny.

## When a call fails

Quote `error` and do the `next` once. When the user wrote in Japanese, say `next_ja`. Do not invent a license, a uid, or a passing `ok`.

- `cell 48x40 does not divide image 64x32.` → Width divisors: 1, 2, 4, 8, 16, 32, 64. Height divisors: 1, 2, 4, 8, 16, 32.
- `cell 16x16 cuts a sprite body.` → Cover each body with cell_w 16 and cell_h 32.
- `cell 32x32 holds more than one body.` → Cover each body with cell_w 16 and cell_h 32.
- `cell 16x16 leaves 4 opaque pixels outside the grid.` → Crop the sheet or pick a cell that covers those pixels. Width divisors: 1, 2, 4, 5, 10, 20.
- `columns 8 does not match the sheet (4).` → Pass columns 4, or omit columns.
- `frame count exceeds 4096.` → Use a larger cell. total is the full frame count. Nothing was written.
- `png did not parse.` → Pass a png file. The bytes were not read as an image.
- `refusing a symlink.` → Pass a regular png inside the project.
- `refusing a path outside the project.` → Pass a regular png inside the project.
- `refusing a credential file.` → Pass the sprite sheet png, not a credential file. `secret_door.png` and `secretary.png` are ordinary names.
- `output already exists.` → Pass replace true to overwrite that path. Nothing was written.
- `fps must be from 1 to 60.` → Pass fps from 1 to 60. Nothing was written.
- `png license text is empty or restricted.` → That sheet is not written.
- `approval line does not fit in one message.` → Shorten the path list. Nothing was written.
- `could not name every value a replace would drop.` → Nothing was written.
- `tile_coords is missing.` → Pass tile_coords for every tile name. Nothing was written.
- `missing or invalid frames.` → Pass frames as described. columns is optional. Nothing was written.
- `no import sidecar for the png.` → Run `godot --headless --editor --quit --path <project>`, then play the stage again.
- `png did not load.` → Run `godot --headless --editor --quit --path <project>`, then play the stage again.
- `region resource is missing.` → Build the SpriteFrames and the TileSet from the slice json, then play again.
- `texture filter is not nearest.` → Set texture_filter = TEXTURE_FILTER_NEAREST on the AnimatedSprite2D. The project default is not enough.
- `tile_edge` in the reply, with `ok` still true → Edge contact is normal for a tileset. Add 1px spacing, or cut at the current cell. Do not suggest one cell for the whole sheet.
- `The write was not approved, or a newer call replaced its preview. Nothing was written.` → Call the tool again and approve it on the Hermes approval screen.
- `The approval is too old. Nothing was written.` → Call the tool again and approve it.
- `The files changed after the preview. Nothing was written.` → Call the tool again so the approval line matches the files.
- `music and voice are separate.` → This plugin does not create music or an NPC voice, and it does not send audio. Nothing was written.
- `This plugin does not create a sound effect.` → Nothing was written. Audio is not sent.
- `This plugin does not create a 3D model.` → Nothing was written. Cut a png instead.
- `warn: a frame does not meet the ground.` → The scene still plays. A floating frame is allowed. The sheet this tool drew keeps its own feet on y=31.

Warnings that keep `ok` true (`same_mask`, `solid_cell`, `transparent_rgb`, `loose_part`) still cut the frames. Say the `next` line, including the Nearest filter.

## 日本語

利用者の文が日本語でも、`tool_search` は英語で探す。例: sprite sheet, tileset, cut png, slice, pixel art, 2D game, godot, unity, walk cycle, shore.

返事の `next_ja` を、利用者の言葉でそのまま伝える。ファイルを書くのは、Hermes の承認画面の 1 行に答えたときだけである。yolo と approvals off では Hermes がその場で承認を飛ばす。余白も間隔も 0 のスプライトシートも、SpriteFrames と Unity の Multiple を書く。元の png のバイトは残る。`write` が false のときだけ、ファイルは書かない。
