# Sprite sheet

Cut a png grid into a sprite sheet or a tileset, or place a walk cycle or shore tiles, for a 2D game in Godot or Unity.

## Install

Point Hermes at this directory and enable `cut-sprite-sheet`. The manifest asks for Hermes `>=0.21.6`. There is no pip install. The tools do not read an API key and they do not send the png.

## First picture

1. Cut the user's png. Omit `cell_w` and `cell_h` on `inspect_grid` when you want a suggested cell. The call does not cut. Then call `slice_grid` with both sizes.
2. A tight sheet (margin 0 and spacing 0) still writes SpriteFrames and a Unity Multiple slice. The png bytes stay. `write` false writes nothing.
3. Run `godot --headless --editor --quit --path <project>` once. Headless play cannot load the png before that import. Then play the stage. Do not open the Godot window.
4. The tools do not launch Godot or Unity. An existing `project.godot` is not changed. Set `snap_2d_transforms_to_pixel` and `snap_2d_vertices_to_pixel` yourself when the project already exists.
5. `place_kit` is only for a folder with no png. `walk` writes a colored 4-frame sheet and shore tiles. This plugin does not create a 3D model or a sound effect.

`--probe` checks playback and prints one `PLAY` line. The scene script is not an `@tool` script.

## What stays out of the catalog

`process/fix_alpha_border=false` is written before Godot imports the png. A new sidecar has no `uid` line. A later slice keeps a `uid://` line Godot already wrote. `spriteExtrude` stays 0. That field is mesh padding, not the spacing copy. The spacing copy is a separate png. Pixels per unit defaults to the cell height. The trial cells are 32. `spriteMeshType` 0 is Full Rect. `spriteID` ends with `0800000000000000` and is not the MD4 hex of the sprite name. `internalIDToNameTable` lists class 213. A gapped tileset names `tiles.extruded.png` in the slice json, and the Unity rects use that image. Unity Editor 6000.6.6f1 on macOS kept the walk-sheet fileIDs after a reopen, and the animation and prefab references stayed. Trial png guids are not shared. A shore map (`peering` in the tileset) puts each neighbor bit on its own atlas cell. Without that map the terrain is one tile. Unity water is an Animated Tile with three frames. Linux and Windows were not tested.

Music and an NPC voice are not created here. Audio is not sent.

## Approval

`slice_grid` and `place_kit` register a `pre_tool_call` hook. A write (default `write` true) dry-runs first and returns `{"action": "approve", "message": <one line of project-relative paths>}`. `inspect_grid`, `write` false, and a dry-run that would not write return nothing, so Hermes does not ask.

Hermes then runs the same human gate as a dangerous shell command (`hermes_cli/plugins.py` `_resolve_block_from_details` → `tools/approval.py` `request_tool_approval`). CLI, gateway, and Desktop show that line. Choosing always covers only the same call (the same arguments) on later turns when a person is present. Hermes checks a saved always line before its own unattended refusal, so this plugin writes nothing in cron, `hermes -q`, webhook, and the plugin host, even after always. After a yes, the handler dry-runs again and writes only when the plan still matches. If the files changed, it writes nothing.

This plugin does not read Hermes private internals. What Hermes does with the approve directive is already in v0.21.6. Checked on v0.22.2:

- yolo (`--yolo` / `/yolo`) and `approvals.mode: off` skip the prompt and treat the call as approved when a person is present (`tools/approval.py` `_run_approval_gate`). They do not write from cron, `hermes -q`, webhook, or the plugin host.
- cron, `-q`, and unattended platforms follow `approvals.cron_mode` / `single_query_mode` / `unattended_mode`. The defaults are deny (`hermes_cli/config_defaults.py`). After always, those defaults do not run, so this plugin refuses the write itself.
- Any other non-interactive context with no person and no gateway writes nothing, even after always. The plugin refuses that turn. Hermes checks a saved always line before its own fail-closed branch, so the plugin does not wait for that branch. A person is an interactive CLI, a gateway session, or an ask bridge (`HERMES_INTERACTIVE`, `HERMES_GATEWAY_SESSION`, `HERMES_EXEC_ASK`, or a gateway platform). An interactive CLI may bind that flag on the turn, under the context name `hermes_interactive`. The process environment is not required.
- The tools are enabled on every surface, including the gateway. Stop a surface with `hermes tools`. While the plugin is enabled, its skill adds one line to the skills index of every session, including surfaces where the tools are turned off.
- Files are written only inside the project directory the call names. Nothing is sent.

The install scanner, with an empty `HERMES_HOME`, on both Hermes v0.22.2 and current main: `Verdict: SAFE`, 11 findings, `Decision: ALLOWED — Allowed (community source, safe verdict)`. `should_allow_plugin_install` is `Allowed (clean scan)`. The findings are tests that spawn Godot/`lsof`/`grep`, PNG byte fixtures, and path-refusal cases. They were not rewritten to hide from the scanner. `--force` is not required.

## 日本語

入れるのは、このディレクトリを Hermes に置いて `cut-sprite-sheet` を有効にするだけである。最初の成功は、利用者の png を `inspect_grid` してから `slice_grid` で切ることである。承認は 1 回で、`pre_tool_call` の 1 行が書くパスである。人がいるとき、yolo と approvals off では Hermes がその場で承認を飛ばす。cron と `-q` と無人は既定で断る。always のあとでも、cron と hermes -q と webhook とプラグインのホストは書かない。人もゲートウェイも無い非対話は、always のあとでも書かない。ファイルを消す計画は、呼ぶたびに聞き、always を残さない。切り直しでは、名前が一致するスプライトの pivot と border を残す。消える値は、その行に名指す。取り込みは `godot --headless --editor --quit --path <project>` の 1 回で、ウィンドウは開かない。そのあとステージを再生する。道具は Godot も Unity も起動しない。既にある `project.godot` は変えない。`place_kit` は png が無いときだけ使う。効果音は無い。
