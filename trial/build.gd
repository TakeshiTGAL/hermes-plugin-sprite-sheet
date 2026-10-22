extends SceneTree

func _fail(error_en: String, next_en: String, next_ja: String) -> void:
	print("error: ", error_en)
	print("next: ", next_en)
	print("次: ", next_ja)
	quit(2)

func _init() -> void:
	var dir := DirAccess.open("res://sprite_sheet")
	if dir == null:
		_fail(
			"no import sidecar for the png.",
			"godot --headless --editor --quit --path <project>. Then play res://sprite_sheet/hero_sheet_stage.tscn again.",
			"png の import が無い。godot --headless --editor --quit --path <project>。そのあと res://sprite_sheet/hero_sheet_stage.tscn を再生する。"
		)
		return
	var docs: Array = []
	dir.list_dir_begin()
	var entry := dir.get_next()
	while entry != "":
		if entry.ends_with(".slice.json"):
			var parsed = JSON.parse_string(FileAccess.get_file_as_string("res://sprite_sheet/" + entry))
			if typeof(parsed) == TYPE_DICTIONARY:
				docs.append(parsed)
		entry = dir.get_next()
	dir.list_dir_end()
	if docs.is_empty():
		_fail(
			"manifest did not parse.",
			"Rewrite the slice json with cell_w and cell_h.",
			"slice json を読み直す。"
		)
		return
	var sprites: Array = []
	var tiles_doc = {}
	for doc in docs:
		var rel := str(doc["file"])
		if not FileAccess.file_exists("res://" + rel + ".import"):
			_fail(
				"no import sidecar for the png.",
				"godot --headless --editor --quit --path <project>. Then play res://sprite_sheet/hero_sheet_stage.tscn again.",
				"png の import が無い。godot --headless --editor --quit --path <project>。そのあと res://sprite_sheet/hero_sheet_stage.tscn を再生する。"
			)
			return
		if str(doc.get("kind", "")) == "sprite":
			sprites.append(doc)
		elif str(doc.get("kind", "")) == "tileset":
			tiles_doc = doc
	var hero = {}
	for doc in sprites:
		var edge: Array = doc["margin"]
		if int(edge[0]) != 0 or int(edge[1]) != 0:
			hero = doc
	if hero.is_empty() and sprites.size() > 0:
		hero = sprites[0]
	if hero.is_empty() or tiles_doc.is_empty():
		_fail(
			"manifest did not parse.",
			"Rewrite the slice json with cell_w and cell_h.",
			"slice json を読み直す。"
		)
		return
	var hero_tex = load("res://" + str(hero["file"]))
	var tiles_tex = load("res://" + str(tiles_doc["file"]))
	if hero_tex == null or tiles_tex == null:
		_fail(
			"png did not load.",
			"godot --headless --editor --quit --path <project>. Then play res://sprite_sheet/hero_sheet_stage.tscn again.",
			"png を読めなかった。godot --headless --editor --quit --path <project>。そのあと res://sprite_sheet/hero_sheet_stage.tscn を再生する。"
		)
		return
	var cell_w := int(hero["cell_w"])
	var cell_h := int(hero["cell_h"])
	var margin: Array = hero["margin"]
	var spacing: Array = hero["spacing"]
	var count := int(hero["frames"])
	var columns := int(hero["columns"])
	var fps := float(hero["fps"])
	var durations: Array = hero["durations"]
	var anim_name := str(hero.get("animation", "walk"))
	var frames := SpriteFrames.new()
	frames.add_animation(anim_name)
	frames.set_animation_loop(anim_name, true)
	frames.set_animation_speed(anim_name, fps)
	for i in range(count):
		var col := i % columns
		var row := int(i / columns)
		var x := int(margin[0]) + col * (cell_w + int(spacing[0]))
		var y := int(margin[1]) + row * (cell_h + int(spacing[1]))
		var atlas := AtlasTexture.new()
		atlas.atlas = hero_tex
		atlas.region = Rect2(x, y, cell_w, cell_h)
		var duration := float(durations[i])
		frames.add_frame(anim_name, atlas, duration)
		print("REGION ", i, " ", x, " ", y, " ", cell_w, " ", cell_h, " duration=", duration)
	var tiles_stem := str(tiles_doc.get("source", tiles_doc["file"])).get_basename()
	var text_path := "res://" + tiles_stem + ".tileset.tres"
	var text_tiles = load(text_path)
	if text_tiles == null:
		_fail(
			"tileset text did not load.",
			"Write each terrain on its own atlas cell, then paint again.",
			"各地形を別の絵のセルに書いてから、塗り直す。"
		)
		return
	var text_layer := TileMapLayer.new()
	get_root().add_child(text_layer)
	text_layer.tile_set = text_tiles
	var block: Array[Vector2i] = []
	for y in 3:
		for x in 3:
			block.append(Vector2i(x, y))
	text_layer.set_cells_terrain_connect(block, 0, 0)
	var text_grass := 0
	var distinct := {}
	var center := ""
	for c in block:
		if text_layer.get_cell_source_id(c) != -1:
			text_grass += 1
			var atlas_name := str(text_layer.get_cell_atlas_coords(c))
			distinct[atlas_name] = true
			if c == Vector2i(1, 1):
				center = atlas_name
	var one: Array[Vector2i] = [Vector2i(0, 0)]
	text_layer.clear()
	text_layer.set_cells_terrain_connect(one, 0, 0)
	var one_filled := 0
	if text_layer.get_cell_source_id(Vector2i(0, 0)) != -1:
		one_filled = 1
	text_layer.clear()
	text_layer.set_cells_terrain_connect(block, 0, 0)
	var filled := 0
	for c in block:
		if text_layer.get_cell_source_id(c) != -1:
			filled += 1
	var source = text_tiles.get_source(0)
	var water_pair: Array = tiles_doc["coords"]["water"]
	var water_atlas := Vector2i(int(water_pair[0]), int(water_pair[1]))
	var water_data = source.get_tile_data(water_atlas, 0)
	var water_polys: int = water_data.get_collision_polygons_count(0)
	var anim_cols: int = source.get_tile_animation_columns(water_atlas)
	var water_frames: int = source.get_tile_animation_frames_count(water_atlas)
	var edge = source.get_tile_data(Vector2i(1, 0), 0)
	var peering_grass: int = edge.get_terrain_peering_bit(TileSet.CELL_NEIGHBOR_RIGHT_SIDE)
	print("TEXT_GRASS %d distinct=%d center=%s" % [text_grass, distinct.size(), center])
	print("TEXT_WATER atlas=%s frames=%d" % [str(water_atlas), water_frames])
	print("TERRAIN_ONE ", one_filled, " TERRAIN_FILL ", filled)
	print("TILE_SIZE ", text_tiles.tile_size)
	print(
		"RELOAD walk_frames=", frames.get_frame_count(anim_name),
		" speed=", frames.get_animation_speed(anim_name),
		" tiles=", source.get_tiles_count(),
		" region=", source.texture_region_size,
		" peering_grass=", peering_grass,
		" anim_cols=", anim_cols,
		" water_polys=", water_polys,
		" duration0=", frames.get_frame_duration(anim_name, 0)
	)
	if text_grass != 9 or distinct.size() < 2 or center != "(7, 1)":
		_fail(
			"terrain paint used one atlas for every terrain.",
			"Give each shore a different atlas cell. One picture copied 16 times is not a shore.",
			"岸は別のセルにする。同じ絵を 16 個重ねない。"
		)
		return
	if one_filled != 1 or filled != 9:
		_fail(
			"terrain paint left cells empty.",
			"Give each terrain a full tile and a shore cell, then paint again.",
			"各地形の内側と岸のセルを入れて、塗り直す。"
		)
		return
	if water_polys != 0 or anim_cols != 3 or water_frames != 3 or peering_grass != 0:
		_fail(
			"water or shore data does not match the sheet.",
			"Water has no collision and three frames. The grass edge peers to grass.",
			"水は当たり無しで 3 コマ。草の縁は草を向く。"
		)
		return
	quit(0)
