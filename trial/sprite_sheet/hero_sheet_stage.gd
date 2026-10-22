extends Node2D

var sprite: Node2D
var map: TileMapLayer
var foot_x := 8
var foot_y := 32
var started_ms := 0
var last_frame := -1
var changes := 0
var seen := {}
var failed := false
var probe := false
var anim_name := "walk"
var water_frames := 0
var using_frames := false
var frame_acc := 0.0
var fps := 8

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
	if not FileAccess.file_exists("res://sprite_sheet/hero_sheet.png.import") or not FileAccess.file_exists("res://sprite_sheet/tiles.png.import"):
		_fail("no import sidecar for the png.", "godot --headless --editor --quit --path <project>. Then play res://sprite_sheet/hero_sheet_stage.tscn again.", "png の import が無い。godot --headless --editor --quit --path <project>。そのあと res://sprite_sheet/hero_sheet_stage.tscn を再生する。")
		return
	var tileset_path := "res://sprite_sheet/tiles.tileset.tres"
	if tileset_path != "" and not FileAccess.file_exists(tileset_path):
		_fail("region resource is missing.", "Build the SpriteFrames and the TileSet from the slice json, then play again.", "slice json から SpriteFrames と TileSet を作ってから、再度再生する。")
		return
	var sheet := load("res://sprite_sheet/hero_sheet.png")
	if sheet == null:
		_fail("png did not load.", "godot --headless --editor --quit --path <project>. Then play res://sprite_sheet/hero_sheet_stage.tscn again.", "png を読めなかった。godot --headless --editor --quit --path <project>。そのあと res://sprite_sheet/hero_sheet_stage.tscn を再生する。")
		return
	if FileAccess.file_exists("res://sprite_sheet/hero_sheet.spriteframes.tres"):
		var frames = load("res://sprite_sheet/hero_sheet.spriteframes.tres")
		if frames == null:
			_fail("png did not load.", "godot --headless --editor --quit --path <project>. Then play res://sprite_sheet/hero_sheet_stage.tscn again.", "png を読めなかった。godot --headless --editor --quit --path <project>。そのあと res://sprite_sheet/hero_sheet_stage.tscn を再生する。")
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
		still.hframes = 4
		still.vframes = 1
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
			_fail("png did not load.", "godot --headless --editor --quit --path <project>. Then play res://sprite_sheet/hero_sheet_stage.tscn again.", "png を読めなかった。godot --headless --editor --quit --path <project>。そのあと res://sprite_sheet/hero_sheet_stage.tscn を再生する。")
			return
		var tiles_doc = JSON.parse_string(FileAccess.get_file_as_string("res://sprite_sheet/tiles.slice.json"))
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
	var fw := int(image.get_width() / 4)
	var fh := int(image.get_height() / 1)
	var frame := _frame_index()
	var origin := Vector2i((frame % 4) * fw, int(frame / 4) * fh)
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
	var fw := int(image.get_width() / 4)
	var fh := int(image.get_height() / 1)
	var total := 4 * 1
	for frame in total:
		var origin := Vector2i((frame % 4) * fw, int(frame / 4) * fh)
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
