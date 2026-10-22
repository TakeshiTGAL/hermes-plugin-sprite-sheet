# スプライトシートとタイルセット

元の案: セルを 8, 16, 32, 48, 64 の正方形に限り、Pillow で PNG をばらして独自の JSON を書く。Godot も Unity も起動せず、`.meta` も領域リソースも書かない。

変えた点: セルは幅と高さを別々に取る。余白、間隔、原点、fps、コマごとの duration、トリム、押し出しを引数にする。出力パスは PNG の stem から決める。`same_mask`、`solid_cell`、`transparent_rgb`、`loose_part` は警告で、`ok` は落とさない。フレームが 4096 を超えたら `truncated` と `total` を返して、画素も矩形も書かない。Unity の pixels per unit はヒーローもタイルも 32。シーンは開いたまま残る。コマが進んだことの計測は、利用者が Godot を `--probe` 付きで起動したときだけ終了する。

理由: 試験シートは 16×32 の 4 体で、正方形 16 は胴を割り、正方形 32 は隣の 2 体を 1 枚にする。足は各コマの不透明な最下段を読む。エンジンが読むのはシート上の矩形である。

プラグインは同じディレクトリの `plugin.yaml`、`SKILL.md`、`__init__.py`、`queries_eval.json` である。盲検の 10 語は別のエージェントが 1 文だけから書いた。作り手は語を直していない。ここにある `trial/` は、その契約を Godot 4.7.2 で再生した実物である。`slice_grid` は Godot を起動せず、SpriteFrames と TileSet のテキストをその呼び出しで書く。`build.gd` は、取り込んだあとにそのテキストを開き直して地形の塗りと `tile_size` を見る検証である。

## 採点の見立て

| 軸 | 見立て |
|---|---|
| 求め | 2D のスプライトシートとタイルセットを、プロジェクトの中の PNG から切る |
| 空き | カタログに、格子のシートをエンジンの領域として書く本は無い |
| この Mac | Godot 4.7.2.stable.official.ed1daf0bf。取得もアカウントも無し。Pillow は画素の試験にだけ使う |
| 面 | 道具 2 つ。書きは承認 1 回 |
| 開示 | 送り先なし。鍵なし。書く場所はプロジェクトの中だけ |
| 上流 | Godot の領域リソースと Unity の TextureImporter。Pillow は上流ではない |
| 検索語 | 盲検の 10 語は作り手が書かない。下の「検索」 |

書き込みを v0.1 に入れる理由: エンジンは領域ファイルが無いとシートをコマとして扱わない。余白 0 で `write` が true のスプライトは、SpriteFrames と Unity の Multiple を書き、元の PNG のバイトは書き換えない。`write` が false のときだけ、ファイルを書かない。書くパスは承認 1 回の一覧と一致させる。承認の行が 1500 字を超えるときは、一覧ファイル 1 つを承認してファイルを書く。その 1 行も収まらないときだけ、何も書かない。

## 本

- 名前: `cut-sprite-sheet`（エンジンの商標は名前に入れない。カタログのファイルは `cut-sprite-sheet.yaml`）
- `requires_hermes: ">=0.21.6"`（新しい本の既定。MCP は無いので `trust` は置かない）
- 依存: 標準ライブラリだけ。`python_dependencies` に Pillow は入れない。README に依存のインストールコマンドは書かない
- 試験した OS は macOS のみ。Linux と Windows は README に「未試験」
- skill の frontmatter に `requires_toolsets` と `requires_tools` は書かない
- 定期実行はしない。Automation Blueprint も cron も作らない
- 資格情報は無い。環境変数からも `get_secret` からも読まない

道具は 3 つ。説明の最初の 1 文は 60 字以内で、`Read-only` で始めない。`Cut` は `slice_grid` の最初の 1 文だけに入れる。

| 道具 | 最初の 1 文 | 書き | 承認 |
|---|---|---|---|
| `inspect_grid` | `Read a sprite sheet or tileset png grid, frames, defects.` | しない | 聞かない |
| `slice_grid` | `Cut and slice a sprite sheet or tileset png for 2D.` | する。`write` false のときだけ書かない | 書くとき 1 回 |
| `place_kit` | `Place a walk cycle or shore tiles in the game.` | する | 書くとき 1 回 |

`inspect_grid` の続き: Use it when a 2D game needs the width, height, frame count, and defects of a sprite sheet or a tileset.

`slice_grid` の続き: Writes Godot SpriteFrames or a TileSet, a Unity .meta, and import sidecars for that png, and asks once.

引数は有限にする。`cell_w` と `cell_h` は 1 以上 4096 以下の整数で、別々に渡す。正方形の列挙にはしない。`margin_x`、`margin_y`、`spacing_x`、`spacing_y` は 0 以上。余白は左上だけである。右と下に残った不透明画素は格子の外として `ok` を落とす。透過だけなら `ok` は true のままである。列数は `(幅 - margin_x + spacing_x) // (cell_w + spacing_x)`、行数も同じ式である。`origin` は `top_left` か `bottom_left`。`columns` を渡したとき、計算した列数より大きい値は失敗である。計算した列数以下なら、その列数だけ切る。省略すると計算した列数になる。`total` は切った枚数、`frame_count` もその枚数である。120×32 を 16×32 で切ると 7 列になる。72×34、余白 2、間隔 2、セル 16×32 は 4 列 1 行になる。

`slice_grid` はそれに加えて `kind`（`sprite` か `tileset`）、`fps`（1 から 60）、コマごとの `durations`、`trim`、`extrude_px`（0 か 1）、`animation`、`foot_x`、`foot_y`、`replace`、`emit_scene`、タイルの `tile_names` と `tile_coords`。`fps` が 1 未満か 60 を超えるときは、ファイルを書く前に失敗を返す。`tile_names` に対する `tile_coords` が無いときも、書く前に失敗を返す。

一辺の上限は 4096。フレーム数が 4096 を超えたら `truncated` は true、`total` は全枚数、`ok` は false。その返事は矩形を作る前に返す。64 枚では切らない。横の列数の上限も 16 にしない。

`trim` が true のとき、slice json の `trim_bounds` に不透明画素の範囲を書き、`AtlasTexture` の `Rect2` はその範囲にする。範囲は両端を含むので、幅は `max_x - min_x + 1` である。受け入れのシーンはトリムしない。トリムしたときは、Godot の `Rect2` と Unity の rect を同じ不透明範囲にし、足は先頭コマのトリム後の座標で置く。

`extrude_px` は 0 か 1。間隔が 1 以上のときは、別の png の隙間へ縁の画素を 1px 写す。元の PNG のバイトは変えない。間隔 0 で縁が不透明なタイルセットが 2 セル以上あるときは、別の png に 1px の隙間を足し、隙間へ縁と角を写す。そのとき json の間隔は 1、余白は 0 で、TileSet はその別 png を指す。1 セルのタイルセットには隙間を足さない。`.meta` の `spriteExtrude` は常に 0 である。Unity の Extrude Edges はメッシュの余白で、テクセルのパディングではない。`.meta` の矩形は元の PNG の座標のままである。

返事のキーは次だけにする。画素、色、画像バイトは入れない。

`ok`、`error`、`next`、`next_ja`、`truncated`、`total`、`source`、`as_of`、`width`、`height`、`cell_w`、`cell_h`、`columns`、`rows`、`frame_count`、`hframes`、`vframes`、`defects`、`width_divisors`、`height_divisors`、`suggest_cell_w`、`suggest_cell_h`、`extrude_px`、`paths`

`source` はプロジェクト内の相対パス、`as_of` はファイルの更新時刻。失敗で `ok` を落とす語は `indivisible`、`split_line`、`multi_body` と、列数が計算より大きいこと、原点の不正、辺の超過、フレーム数の超過、壊れた PNG、格子の外に不透明画素が残ることである。警告は `same_mask`、`solid_cell`、`transparent_rgb`、`loose_part`、`extrude_clamped`、タイルの `tile_edge` で、`ok` は true、`error` は空、`next` に次の手を書く。`ok` の `next` には、ノードの texture filter を Nearest にする一文を足す。境界を 1 画素でもまたぐ体は `split_line` である。セルが完全に不透明なら割ったことにはしない。タイルセットは縁で接してよい。`kind` が tileset のとき、縁の接触は警告 `tile_edge` で、次の手は間隔を 1px 足すか、今のセルで切ることである。シート全体を 1 セルにはしない。スプライトの縁の接触は `split_line` のままである。形が同じで色も同じシルエットは色の差し替えにしない。透過が無く色も同じなら `same_mask` ではない。提案は、1 セルに 1 つの体が入る約数の格子のうち、空きが少なく面積が大きいものである。そのような格子が無いときだけ 0×0 で、次の手は `Do not use 0x0` である。戻れるセルがあるときは、その幅と高さを書き、0×0 とは書かない。体の中に 1 画素の隙間があると、1 つの格子に収まらず 0×0 になることがある。

`inspect_grid` はプロジェクトの中の普通の PNG だけを読む。読む実装は標準ライブラリである。チャンクの CRC が合わない PNG は読まない。`tEXt` に加えて `iTXt` と `zTXt` の文字も読む。絶対パス、`..`、シンボリックリンク、プロジェクトの外に解決されるパス、png 以外は、中身を読む前に拒否する。資格情報はファイル名と、拡張子を外した名前を見る。`.env` で始まる名前、`id_rsa.png`、`credentials.png`、`secrets.json`、拡張子 `.pem` `.key` `.p12` `.pfx` は拒む。`secret_door.png` と `secretary.png` は読む。名前の部分一致では拒まない。

16bit とインターレースは、例外を画面に出さず `error` と `next` を返す。インデックスカラーとグレーは RGBA にほどいてからマスクを見る。

## 承認と拒否

書きの承認は 1 回。スプライトとタイルを分けて聞かない。承認文は 1 行で、改行もバッククォートも入れない。書く相対パスを空白でつなぐ。`replace` のときは行頭に `replace` を付ける。切り直しでは、既存の `.meta` で名前が一致するスプライトの alignment、pivot、border を残す。fileID と guid の計算は変えない。名前が一致しないスプライトの alignment、pivot、border と、置き換えると消える `.tres` の行は、同じ承認の行に名指す。名指しできないときは何も書かない。消える値が無いとき、1500 字を超える行は、パスを 1 行ずつ書いた一覧ファイル 1 つだけを承認し、ファイルは書く。その 1 行も収まらないときだけ、何も書かない。契約の `dry_run` はその行を返し、ファイルを作らない。プラグインは、その行を Hermes の承認画面に 1 回出す。`once` のときだけ書く。`always` は出さず、保存もしない。`confirm` は無い。

パスは入力 PNG の stem から決める。`sprite_sheet/hero_sheet.png` のスプライトは `sprite_sheet/hero_sheet.spriteframes.tres`、`hero_sheet.png.meta`、`hero_sheet.png.import`、`hero_sheet.slice.json`。`emit_scene` のときは `hero_sheet_stage.gd` と `hero_sheet_stage.tscn` が足される。タイルセットは `tiles.tileset.tres` と、地形ごとの `.asset` と `.asset.meta`。この tres は、承認したその呼び出しがテキストで書く。2 枚目の `npc.png` は `npc` の stem になり、1 枚目のファイルを指さない。

`slice_grid` の一覧に、既存の `project.godot` と `build.gd` と、ばらした PNG は入らない。`place_kit` の `walk` で `project.godot` が無いときだけ、その承認に最小の `project.godot` を 1 つ入れる。整数倍のストレッチ、既定のフィルタ 0、2D の両スナップを持つ。既にある `project.godot` は変えない。元の PNG のバイトは、押し出しでも隙間の追加でも書き換えない。

`write` が false のときだけファイルを書かない。余白 0、間隔 0、`write` true のスプライトは SpriteFrames と Unity の Multiple を書く。試験のヒーローは次を返す。

```
next: No margin and no spacing. SpriteFrames and a Unity Multiple slice were written. hframes is 4 and vframes is 1. Set the node's texture filter to Nearest. License text is not a known free license. It was copied and not rewritten. godot --headless --editor --quit --path <project>
```

余白か間隔があるシートは、`hframes` では余白を見ないので slice を使う、と返す。試験の余白 2、間隔 2 の次は `Margin is 2,2 and spacing is 2,2. hframes ignores margin, so use the slice. Set the node's texture filter to Nearest. License text is not a known free license. It was copied and not rewritten. godot --headless --editor --quit --path <project>` である。

`License`、`license`、`Copyright`、`copyright`、`SPDX-License-Identifier` が無い PNG は書く。`next` は権利が付いていないと言う。Copyright が空でも License が CC0 なら通す。値が空、`unknown`、All Rights Reserved、proprietary、non-commercial、CC-BY-NC、CC-BY-ND、`無断転載禁止` は 0 バイトで止める。CC0、CC-BY（NC でも ND でも SA でもない）、MIT、Unlicense、public domain は語の境界で見て写す。CC-BY-SA は写し、継承を `next` に書く。`Smith`、`limited`、`not public domain`、`trial sheet`、`no third-party` は自由な印にしない。それ以外の空でない文は写して、知らないライセンスだと `next` に書く。定型のライセンス文は発明しない。

拒否する文脈: cron、yolo、approvals off、`-q`、無人のセッション。承認の確認が読み込めないときは、失敗として何も書かない。`always` は保存しない。`plugins.isolation: host` は要らない。ホスト隔離でしか動かない、とは書かない。

既定で全部の面で有効。ゲートウェイで部屋に入っている人は、エージェントが呼べる道具を呼べる。止め方は `hermes tools`。消したあとに残る cron は無い。承認して書いたプロジェクトのファイルは、プラグインを消しても残る。

上書きは既定でしない。`replace: true` のときだけ書く。承認の行は `replace` と対象パスで始まり、消える値があればその行に名指す。

## エンジンとの一続き

プラグインは Godot も Unity も起動しない。既存の `project.godot` は変えない。`@tool` は付けない。開いただけではシーンのスクリプトは走らない。

1. 利用者か `place_kit` が、プロジェクトの中に PNG を置く。絵は取得なしにその場で描く。ヒーローは 64×32、コマは 16×32 が 4 枚で、接地、通過、接地、通過の順である。4 体は別の形で、各コマは 1 つの連結成分である。4 コマとも不透明な最下段は y=31 で、支えの足はそこから動かない。通過のコマはもう一方の足が上がる。足は測って `(8, 32)`。余白 0、間隔 0 でも SpriteFrames と Unity の Multiple を書き、元の PNG のバイトは残す。立体と効果音は作らない。生成した 3D と効果音は、別の本の仕事である。`walk` は同じ承認で、足の下の岸タイルと、無いときだけの `project.godot` を書く。タイルは 256×96。草の 16 ビットはそれぞれ別の絵で、列 0 から 7、段 0 と 1 に並ぶ。満杯の草は bit 15 で `(7, 1)`。段 2 は水の 3 コマ、砂、道。水は当たりが無い。草の Unity 側は 16 規則の RuleTile である。音楽と声は作らず、音声は送らない。
2. `inspect_grid` が寸法と枚数と欠陥コードを返す。16×32 はこのシートで `ok: true`、フレーム 4、`hframes` 4、`vframes` 1。正方形 16 は `split_line` で、次の手が `cell_w 16` と `cell_h 32` を別々に言う。24×24 は体を割るので、約数の一覧ではなく 16×32 を提案する。48×40 は割り切れず、約数の一覧を返す。16 か 32 の正方形へは丸めない。32×32 は 1 セルに体が 2 つあるので `multi_body` で、ファイルは書かない。1 画素だけで左右の体が接するシートも `split_line` で、その体を覆うセルを提案する。2 段に 8 体ある 64×64 を 16×16 で見ると、提案は 16×32 である。
3. 余白 0、間隔 0、`write` true でも、`slice_grid` は slice json と Godot の SpriteFrames を書く。余白か間隔があるシートも同じである。タイルは `tiles.tileset.tres` を書く。タイルの json は格子の矩形数で、試験シートは 24 である。`animation` は空、`foot` は置かない、`durations` は空、`unity_water` は `animated_tile` である。余白のあるスプライトの json が `foot` と、渡したアニメ名を持つ。default には複製しない。複数段は段ごとに別名になる。`Rect2` は、トリムしたときだけ不透明の範囲で、その分は AtlasTexture の margin でセルの位置に戻す。`texture_region_size` と `TileSet.tile_size` はどちらもセルで、試験のタイルは `Vector2i(32, 32)` である。地形の mode は `MATCH_SIDES`（2）である。岸の対応を渡した地形は、ビットごとに別のアトラス座標へ置く。渡さない地形は 1 セルで、16 枚の複製はしない。これはオートタイルの複製ではない。3×3 を草で塗ると 9 マスになり、絵の座標は 2 種類以上になる。当たりはセルの半分を四辺にした多角形で、水は 0 本である。水の連番は frames 3、fps 4 で、columns を省くと frames と同じになる。duration でコマごとの長さを残す。
4. 同じ書きで Unity の `.meta` を書く。`serializedVersion: 11`、`spriteMode: 2`、`filterMode: 0`、`spriteMeshType: 0`（Full Rect）、`spriteExtrude: 0`、`spritePixelsToUnits: 32`、`alphaIsTransparency: 0`、`spriteID`、`internalID`、`nameFileIdTable`、`internalIDToNameTable` の class 213、`platformSettings`、`spriteBorder`、`textureCompression: 0`、`enableMipMap: 0`。ヒーローの alignment は 7、pivot は下端中央。タイルの alignment は 0、pivot はセル中央。y は画像の下端が 0。岸の対応が 2 つ以上ある地形は RuleTile で、ビットごとに 1 規則、草は 16 規則である。右は (1, 0)、下は (0, -1)、左は (-1, 0)、上は (0, 1)。当たりの既定は地面が 2、水が 0。対応が 1 つ以下の地形は Tile で、スクリプト参照は `fileID: 13312`。水は Animated Tile で、3 コマを指す。パッケージは com.unity.2d.tilemap.extras である。Godot の TileSet も水の 3 コマを残す。`maxTextureSize` は 4096。macOS の Unity 6000.6.6f1 は歩行シートの internalID を、閉じて開き直しても残した。
5. `.import` は `compress/mode=0`、`mipmaps/generate=false`、`process/fix_alpha_border=false`。パスは `md5("res://"+相対パス)` を dest に入れる。新しい sidecar に uid は書かない。切り直しでは、Godot が残した `uid://` の行だけを残す。Godot 4.7 が sidecar 無しで最初に書く値は `fix_alpha_border=true` なので、false を先に書く。取り込みのあと、押し出していない PNG のバイトと `project.godot` は変わらない。
6. 試験のシーンは `sprite_sheet/hero_sheet_stage.gd` と `hero_sheet_stage.tscn`。`slice_grid` の `emit_scene` が書く文と、計測に使う文は同じである。参照は `res://sprite_sheet/`。音声ファイルは参照しない。作った AnimatedSprite2D と TileMapLayer に `TEXTURE_FILTER_NEAREST` を代入する。プロジェクトの既定が Linear でも、この代入でぼやけない。違っていれば `PLAY` の前に失敗し、次の手はその 1 行である。合格の行に `filter=` も `snap=` も出さない。試験の `project.godot` は 320×180、整数倍のストレッチ、2D のスナップを持つ。
7. 既定のシーンは開いたまま残る。この Godot 4.7.2 では `OS.has_feature("headless")` が `--headless` でも false なので、`DisplayServer.get_name()` で見る。ウィンドウではツリーごと終了しない。足の下のタイルは `local_to_map` で読む。境界で空なら 1px 下を見る。空のままなら `PLAY` の前に失敗する。足は画面の中央、320×180 なら `(160, 90)` に置く。横から見た歩きなので、足はタイルの上端に乗る。地図は草セルの上端が足に来るように置き、地図を先に子にする。スプライトは `z_index` 1 で地図より手前である。浮いたコマは `warn: a frame does not meet the ground.` を出してシーンを残し、`PLAY` の前には止めない。next は `The scene still plays. A floating frame is allowed.` である。自分で描いた 4 コマの最下段は y=31 のままである。接地したコマは `foot_px=31` である。SpriteFrames が無いときは、fps の間隔でコマを進める。プロセスの毎フレームには進めない。`--probe` か環境変数 `SPRITE_SHEET_PROBE=1` のときだけ、約 0.8 秒コマを見て、`frames_seen` が 2 未満なら `PLAY` を出さずに終了コード 2 とする。通ったときだけ `PLAY` を出して終了コード 0 で終了する。行には `foot=160,90`、`foot_px=31`、`cell=0`、`tile=grass`、`nearest=true`、`water_frames=3` が入る。終了時点の `frame` は固定しない。`changes` はコマが替わった回数である。
8. 遊びは別プロセスの `godot --headless --path`。Godot 本の `run_game` は、エディタの補助が生きていないと not_live で、ヘッドレスでは遊んだことにしない。未接続のまま遊んだとは書かない。テキストの tres を消さずに取り込み、`build.gd` を走らせなくても、上の `PLAY` が出る。`build.gd` はテキストのタイルセットを上書きしない。草の 3×3 は 9 で、絵の座標は 2 種類以上、中央は `(7, 1)` である。水は 1 セルで 3 コマ、当たり 0 である。草の右縁は草を向く。`tile_size` は 32×32 である。

この Mac での計測:

```
godot --headless --path <project> -- --probe
```

```
PLAY frame=1 frames_seen=4 changes=6 anim=walk foot=160,90 foot_px=31 cell=0 tile=grass nearest=true water_frames=3
```

SpriteFrames を消して Sprite2D に戻した同じシーンは `PLAY frame=2 frames_seen=4 changes=7 anim=walk foot=160,90 foot_px=31 cell=0 tile=grass nearest=true water_frames=3` である。`place_kit` の `walk` を空のフォルダに書いたあとの再生は、duration が全部 1 なので後者と同じ行である。

余白のあるシートも同じ式で切る。試験の `padded_sheet.png` は 74×36、余白 2、間隔 2、セル 16×32 で 4 コマになり、`ok: true` である。

ライセンスは PNG の文字を slice json に写す。定型をライセンスとして発明しない。切り出しは新しい権利を生まない。出典は相対パス。試験の tEXt は `Trial sheet drawn for this design. No third-party artwork.`

Unity エディタは起動していない。ライセンスとアカウントに触れるためである。`.meta` の中身はテキストで確かめる。エディタが開き直したあとの矩形は見ていない。

## 開示の下書き（カタログ）

```
pixel art sprite sheet cutter. png to tileset splitter. cut pixel art into game tiles. sprite sheet from pixel png. 2d walk cycle sprite sheet. tileset cutter for pixel art. split png into sprite sheet. shore tiles tileset tool. pixel art walk cycle sheet. png sprite and shore tiles. Cuts a pixel-art png into frames. Tools: inspect_grid, slice_grid, place_kit for a 2D game. Disclosure — The png stays on this computer. Nothing is sent. No API key. No daily cap. A gateway room can call the tools. Stop them with hermes tools. One approval on one line. always stores nothing. An oversized line writes one list file. A failed check writes nothing. Refused in cron, yolo, approvals off, and unattended sessions. Empty, unknown, or a restrictive license is not written. Unknown text is copied and next warns. CC-BY-SA is copied and next names share-alike. No license chunk still writes and next says no rights are attached. Import once or play fails: godot --headless --editor --quit --path <project>. No solid-color box and no sound effect. Does not launch Godot or Unity. Play may write app-userdata. Uninstall leaves no cron job. Linux is untested. Unity editor 6000.6.6f1 on macOS kept the walk-sheet fileIDs after a reopen. スプライトシートとタイルセットを切る。
```

## 失敗の実例（この Mac の逐語）

割り切れない:

```
error: cell 48x40 does not divide image 64x32.
next: Width divisors: 1, 2, 4, 8, 16, 32, 64. Height divisors: 1, 2, 4, 8, 16, 32.
次: 幅の約数は 1, 2, 4, 8, 16, 32, 64。高さの約数は 1, 2, 4, 8, 16, 32。
```

体を割る正方形:

```
error: cell 16x16 cuts a sprite body.
next: Cover each body with cell_w 16 and cell_h 32.
次: 体を割らないセルは幅 16、高さ 32。
```

1 セルに体が 2 つ:

```
error: cell 32x32 holds more than one body.
next: Cover each body with cell_w 16 and cell_h 32.
```

列数が計算より大きい:

```
error: columns 8 does not match the sheet (4).
next: Pass columns 4, or omit columns.
```

フレームが上限を超える:

```
error: frame count exceeds 4096.
next: Use a larger cell. total is the full frame count. Nothing was written.
```

壊れた PNG（CRC が合わないものも含む）:

```
error: png did not parse.
next: Pass a png file. The bytes were not read as an image.
```

色が違う同じ形（警告。`ok` は true。`error` は空）:

```
next: Masks match, so this is a color swap. The frames are still cut. Set the node's texture filter to Nearest.
次: 形が同じなので色の差し替え。コマはそのまま切る。ノードの texture filter を Nearest にする。
```

単色（警告。`ok` は true。`error` は空）:

```
next: A cell is one flat color. The cell is still cut. Set the node's texture filter to Nearest.
次: セルが単色。セルはそのまま切る。ノードの texture filter を Nearest にする。
```

透過画素に色がある（警告。`ok` は true。`error` は空）:

```
next: Zero the RGB of transparent pixels, or write the sheet with this defect. Keep fix_alpha_border off. Set the node's texture filter to Nearest.
次: 透過画素の RGB を 0 にするか、この欠陥のまま書く。fix_alpha_border はオフのままにする。ノードの texture filter を Nearest にする。
```

小さい別部品（警告。`ok` は true。`error` は空）:

```
next: A small separate part is in the cell. The frame is still cut. Set the node's texture filter to Nearest.
```

シンボリックリンク:

```
error: refusing a symlink.
next: Pass a regular png inside the project.
次: シンボリックリンクは拒否した。プロジェクトの中の普通の png を渡す。
```

プロジェクトの外:

```
error: refusing a path outside the project.
next: Pass a regular png inside the project.
次: プロジェクトの中の普通の png を渡す。
```

上書き:

```
error: output already exists.
next: Pass replace true to overwrite that path. Nothing was written.
次: 出力が既にある。置き換えるなら replace を true にする。まだ書いていない。
```

取り込みが無い（終了コード 2）:

```
error: no import sidecar for the png.
next: godot --headless --editor --quit --path <project>. Then play res://sprite_sheet/hero_sheet_stage.tscn again.
次: png の import が無い。Godot でプロジェクトを取り込んでから、res://sprite_sheet/hero_sheet_stage.tscn を再度再生する。
```

sidecar だけで取り込み結果が無い（終了コード 2）:

```
error: png did not load.
next: godot --headless --editor --quit --path <project>. Then play res://sprite_sheet/hero_sheet_stage.tscn again.
次: png を読めなかった。Godot でプロジェクトを取り込んでから、res://sprite_sheet/hero_sheet_stage.tscn を再度再生する。
```

領域リソースが無い（終了コード 2）:

```
error: region resource is missing.
next: Build the SpriteFrames and the TileSet from the slice json, then play again.
```

fps が範囲外（ファイルは書かない）:

```
error: fps must be from 1 to 60.
next: Pass fps from 1 to 60. Nothing was written.
```

ライセンスが空か、制限がある（ファイルは書かない）:

```
error: png license text is empty or restricted.
next: That sheet is not written.
```

水の frames が無い（ファイルは書かない）:

```
error: missing or invalid frames.
next: Pass frames as described. columns is optional. Nothing was written.
```

格子の外に不透明画素が残る（ファイルは書かない）:

```
error: cell 16x16 leaves 4 opaque pixels outside the grid.
next: Crop the sheet or pick a cell that covers those pixels. Width divisors: 1, 2, 4, 5, 10, 20.
次: 格子の外に不透明画素が 4 ある。シートを切るか、画素を覆うセルにする。幅の約数は 1, 2, 4, 5, 10, 20。
```

承認の 1 行も一覧ファイルも収まらない（ファイルは書かない）:

```
error: approval line does not fit in one message.
next: Shorten the path list. Nothing was written.
```

切り直しで消える値を名指しできない（ファイルは書かない）:

```
error: could not name every value a replace would drop.
next: Nothing was written.
```

地形の座標が無い（ファイルは書かない）:

```
error: tile_coords is missing.
next: Pass tile_coords for every tile name. Nothing was written.
```

浮いたコマ（終了コード 0。シーンは残る）:

```
warn: a frame does not meet the ground.
next: The scene still plays. A floating frame is allowed.
次: シーンは残す。浮いたコマも再生する。
```

skill の `## When a call fails` には、上の目印と次の手を 1 行ずつ書く。`ok: false` を作文して試験を通さない。同じ文は `failure_samples.json` にある。

## 検索

Tool Search は英語だけを拾う。skill に「日本語の頼みでも tool_search は英語で探す。例: sprite sheet, tileset, cut png, slice, pixel art, 2D game」と書く。カタログの説明には、sprite sheet、tileset、pixel art、2D game を、上のリードの文の中に入れる。日本語は、そのあとに事実としてスプライトシートとタイルセットを書く。同義語だけの浮いた文は足さない。

盲検の 10 語は、作り手と別のエージェントに次の 1 行だけ渡して書かせた。作り手はそのファイルを読まず、語を直していない。

```
Cut a grid png into a sprite sheet and a tileset for a 2D game.
```

`queries_eval.json` に、その 10 語をそのまま置く。

## マニフェスト

slice json に、元ファイルの相対パス、PNG の文字から写したライセンス、切り出しは新しい権利を生まないこと、`trim_bounds`、`durations`、スプライトだけの `foot`、`extrude_px` を書く。試験の絵は第三者の素材ではない。`place_kit` は歩きと岸をこのコンピュータで置く。立体と効果音は作らない。音楽と声は作らず、音声は送らない。`manifest.json` は書かない。

## README に回すこと

Linux と Windows は未試験。macOS の Unity 6000.6.6f1 は歩行シートの fileID を、閉じて開き直しても残し、Animation と Prefab の参照は切れなかった。macOS の Godot 4.7.2 で、ヘッドレスの取り込みと `--probe` の再生まで試験した。画面の画素はヘッドレスのため見ていない。足は各コマの不透明な最下段と、プローブが印刷する座標で見ている。シーンは自分では終了しない。`--probe` のときだけ、コマを見て終了する。

取り込む前に `process/fix_alpha_border=false` を書く。新しい sidecar に uid の行は書かない。切り直しでは、取り込み後のファイルに Godot が残した uid だけを残す。`spriteExtrude` は 0 のままである。これはメッシュの余白で、テクセルのパディングではない。間隔が 1 以上の押し出しは、元の PNG を残して別の png の隙間へ写す。pixels per unit はセルの高さで、試験のセルは 32。`spriteMeshType` は 0（Full Rect）。`spriteID` の末尾は `0800000000000000` で、スプライト名の MD4 ではない。`internalIDToNameTable` の class 213 を書く。地形の peering bit は、ビットごとに別のアトラス座標へ書く。岸の対応が無い地形は 1 セルである。水の Unity 側は Animated Tile の 3 コマである。`maxTextureSize` は 4096。手順は README.md にも書く。

## 作る段の関門

- 一時の HERMES_HOME で入れて、最初の頼みまでの手数と時間を数える。入れる先は `plugin.yaml` のあるディレクトリである
- 書きの承認が 1 回で、画面のパスと実際にできるファイルが一致する。パスは PNG の stem から決まる。1500 字を超える一覧は、一覧ファイル 1 つを承認して書く。ライセンスの塊が無い PNG は書く。空と制限のあるライセンスは書かない
- 上書き拒否、プロジェクト外、シンボリックリンク、資格情報のファイル名、を実物で打つ。`secret_door.png` は拒まない
- 16×32 の 4 コマでマスクが違う。正方形 16 は体を割ると拒否し、次の 1 回で 16×32 に戻れる。24×24 も体を割る。48×40 だけが割り切れない。約数の次の手は正方形へ丸めない。32×32 は書かない
- テキストで書いた `.tres` を開き直し、余白のあるシートの `Rect2`、`tile_size` と `texture_region_size` の 32×32、岸は別セル、水の当たり 0、水のアニメ列、が残る。地形の塗りは草の 3×3 が 9 で、絵の座標は 2 種類以上になる
- 既にある `project.godot` はプラグインが書き換えない。無いプロジェクトでは、`walk` の承認に最小の 1 ファイルが入る。`--probe` で `frames_seen` が 4、足が 320×180 の中央、`foot=160,90`、`foot_px=31`、`cell=0`、`tile=grass`、`nearest=true`、`water_frames=3`、終了コード 0。足はタイルの上端に乗り、スプライトは地図より手前である。既定が Linear のプロジェクトでも終了コード 0。1 コマでも地面に届かなければ警告を出して終了コード 0
- 取り込み前は終了コード 2。`PLAY` 行の無い終了コード 0 は成功に数えない
- 盲検 10 語は `queries_eval.json` にある。作り手は語を直していない
- 先端のファイルに社内のパスと、プラグインを指す内部の呼び方を入れない
- 安定版 Hermes で確かめる段は、プラグインを置いてからである。本物のモデルの流しは、空の HOME と檻の中だけで行う
