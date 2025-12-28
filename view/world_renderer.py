"""
View: WorldRenderer - Rendering von Welt, Chunks, Player und Tile-Highlight
"""
from typing import Optional
import math
import pyglet.shapes
from core import settings
from core.world_controller import WorldController


class WorldRenderer:
    """Rendert die Spielwelt: Chunks, Player und Tile-Highlight"""
    
    def __init__(self, world_controller: WorldController, modern_gl_renderer):
        """
        Args:
            world_controller: WorldController instance
            modern_gl_renderer: ModernGLRenderer instance
        """
        self.world_controller = world_controller
        self.modern_gl_renderer = modern_gl_renderer
    
    def draw(self, debug_visualization_mode: int = 0):
        """Draw world, chunks, player"""
        if not self.world_controller.game_initialized or not self.world_controller.world or not self.world_controller.world.chunk_manager:
            return
        
        # Step 1: Update view matrix based on camera position and zoom
        if self.world_controller.camera:
            camera_x = self.world_controller.camera.x
            camera_y = self.world_controller.camera.y
            self.modern_gl_renderer.update_view(camera_x, camera_y, zoom=self.world_controller.camera_zoom)
        else:
            camera_x = 0.0
            camera_y = 0.0
            self.modern_gl_renderer.update_view(0.0, 0.0, zoom=self.world_controller.camera_zoom)
        
        # Step 1.5: Load chunks in visible area + buffer (dynamically based on zoom)
        self.world_controller.load_visible_chunks(camera_x, camera_y)
        
        # Step 2: Get visible chunks from controller (includes frustum culling)
        visible_chunks = self.world_controller.get_visible_chunks(camera_x, camera_y)
        
        # Step 2.5: Inform renderer which chunks are visible (enables smart pool management)
        if visible_chunks:
            visible_chunk_keys = set((cx, cy) for cx, cy, _ in visible_chunks)
            self.modern_gl_renderer.set_visible_chunks(visible_chunk_keys)
        
        # Step 3: Render visible chunks
        if visible_chunks:
            self.modern_gl_renderer.render_chunks(visible_chunks, performance_monitor=self.world_controller.performance_monitor)
        
        # Step 3.5: Render decorations (Layer 5: Shadows, Layer 10: Decorations)
        if visible_chunks:
            self._render_decorations(visible_chunks, camera_x, camera_y)
        
        # Step 4: Render player (Layer 20)
        if self.world_controller.player:
            self._render_player()
        
        # Store chunks_data for debug visualization
        self._last_chunks_data = visible_chunks if visible_chunks else []
    
    def get_chunks_data(self):
        """Get the last rendered chunks data for debug visualization"""
        return getattr(self, '_last_chunks_data', [])
    
    def _render_player(self):
        """Render player as yellow quad (1 tile wide, 2 tiles tall)"""
        if not self.world_controller.player:
            return
        
        import numpy as np
        import moderngl
        
        tile_size = settings.TILE_SIZE
        player_width = tile_size
        player_height = tile_size * 2
        
        player_world_x = self.world_controller.player.rect.center[0]
        player_world_y = self.world_controller.player.rect.center[1]
        
        world_x0 = player_world_x - player_width / 2.0
        world_y0 = player_world_y - player_height / 2.0
        world_x1 = world_x0 + player_width
        world_y1 = world_y0 + player_height
        
        # Get color index for yellow (255, 255, 0) from palette
        yellow_color = (255, 255, 0)
        color_index = float(self.modern_gl_renderer.tile_color_palette.get_color_index(yellow_color))
        
        # If yellow not in palette, add it
        if color_index == 0 and yellow_color not in self.modern_gl_renderer.tile_color_palette.color_to_index:
            color_index = float(self.modern_gl_renderer.tile_color_palette.add_color(yellow_color))
            # Update palette uniform in shader
            self.modern_gl_renderer._update_palette_uniform()
        
        vertices = np.array([
            [world_x0, world_y0, color_index],
            [world_x1, world_y0, color_index],
            [world_x1, world_y1, color_index],
            [world_x0, world_y0, color_index],
            [world_x1, world_y1, color_index],
            [world_x0, world_y1, color_index],
        ], dtype=np.float32)
        
        vbo = self.modern_gl_renderer.ctx.buffer(vertices.tobytes())
        vao = self.modern_gl_renderer.ctx.vertex_array(
            self.modern_gl_renderer.chunk_program,
            [(vbo, "2f 1f", "in_position", "in_color_index")]
        )
        
        vao.render(moderngl.TRIANGLES)
        
        vao.release()
        vbo.release()
    
    def draw_tile_highlight(self, mouse_x: int, mouse_y: int, screen_width: int, screen_height: int):
        """
        Render highlight for tile or decoration under mouse cursor if within 8 tiles of player.
        Differentiates visually between tile and decoration selection.
        """
        if not self.world_controller.camera or not self.world_controller.player:
            return
        
        # Convert mouse screen coordinates to world coordinates
        world_x = self.world_controller.camera.x + (mouse_x - screen_width / 2.0) / self.world_controller.camera_zoom
        world_y = self.world_controller.camera.y + (screen_height / 2.0 - mouse_y) / self.world_controller.camera_zoom
        
        # Get player position
        player_x = self.world_controller.player.rect.x
        player_y = self.world_controller.player.rect.y
        
        # Calculate distance in tiles
        distance_tiles = math.sqrt(
            ((world_x - player_x) / settings.TILE_SIZE) ** 2 +
            ((world_y - player_y) / settings.TILE_SIZE) ** 2
        )
        
        # Only highlight if within 8 tiles
        if distance_tiles > 8.0:
            return
        
        # Get tile coordinates
        tile_x = int(world_x // settings.TILE_SIZE)
        tile_y = int(world_y // settings.TILE_SIZE)
        
        # Get tile data
        if not self.world_controller.world or not self.world_controller.world.terrain_gen:
            return
        
        tile_data = self.world_controller.world.terrain_gen.generate_tile(tile_x, tile_y)
        
        # Check if mouse is on decoration bounding box
        clicked_decoration = self.world_controller._is_point_on_decoration(world_x, world_y, tile_x, tile_y, tile_data)
        
        if clicked_decoration:
            # Highlight decoration bounding box
            self._draw_decoration_highlight(world_x, world_y, tile_x, tile_y, tile_data, screen_width, screen_height)
        else:
            # Highlight tile
            self._draw_tile_highlight(tile_x, tile_y, screen_width, screen_height)
    
    def _draw_tile_highlight(self, tile_x: int, tile_y: int, screen_width: int, screen_height: int):
        """Draw highlight for tile (white border)."""
        # Get tile world position (top-left corner of tile)
        tile_world_x = tile_x * settings.TILE_SIZE
        tile_world_y = tile_y * settings.TILE_SIZE
        
        # Convert tile world position to screen coordinates for rendering
        screen_tile_x = (tile_world_x - self.world_controller.camera.x) * self.world_controller.camera_zoom + screen_width / 2.0
        screen_tile_y = (tile_world_y - self.world_controller.camera.y) * self.world_controller.camera_zoom + screen_height / 2.0
        
        # In pyglet, Y=0 is at bottom, so we need to adjust
        screen_tile_y = screen_height - screen_tile_y
        
        # Draw highlight rectangle (brighter overlay)
        tile_size_scaled = settings.TILE_SIZE * self.world_controller.camera_zoom
        highlight = pyglet.shapes.Rectangle(
            screen_tile_x,
            screen_tile_y - tile_size_scaled,
            tile_size_scaled,
            tile_size_scaled,
            color=(255, 255, 255)
        )
        highlight.opacity = 80  # Semi-transparent white overlay
        highlight.draw()
        
        # Draw border around highlighted tile (white, 2px)
        border_width = 2
        border_color = (255, 255, 255)
        border_opacity = 200
        
        # Top border
        top_border = pyglet.shapes.Rectangle(
            screen_tile_x,
            screen_tile_y - border_width,
            tile_size_scaled,
            border_width,
            color=border_color
        )
        top_border.opacity = border_opacity
        top_border.draw()
        
        # Bottom border
        bottom_border = pyglet.shapes.Rectangle(
            screen_tile_x,
            screen_tile_y - tile_size_scaled,
            tile_size_scaled,
            border_width,
            color=border_color
        )
        bottom_border.opacity = border_opacity
        bottom_border.draw()
        
        # Left border
        left_border = pyglet.shapes.Rectangle(
            screen_tile_x,
            screen_tile_y - tile_size_scaled,
            border_width,
            tile_size_scaled,
            color=border_color
        )
        left_border.opacity = border_opacity
        left_border.draw()
        
        # Right border
        right_border = pyglet.shapes.Rectangle(
            screen_tile_x + tile_size_scaled - border_width,
            screen_tile_y - tile_size_scaled,
            border_width,
            tile_size_scaled,
            color=border_color
        )
        right_border.opacity = border_opacity
        right_border.draw()
    
    def _draw_decoration_highlight(self, world_x: float, world_y: float, tile_x: int, tile_y: int, 
                                   tile_data: dict, screen_width: int, screen_height: int):
        """Draw highlight for decoration bounding box (cyan border, thicker)."""
        try:
            from world.decoration_registry import DecorationRegistry
            from world.decoration import Decoration
        except ImportError:
            # Fallback to tile highlight if decoration system not available
            self._draw_tile_highlight(tile_x, tile_y, screen_width, screen_height)
            return
        
        decoration_data = tile_data.get('decoration')
        if not decoration_data:
            # Fallback to tile highlight
            self._draw_tile_highlight(tile_x, tile_y, screen_width, screen_height)
            return
        
        decoration_id = decoration_data.get('decoration_id')
        if not decoration_id:
            return
        
        deco_config = DecorationRegistry.get(decoration_id)
        if not deco_config:
            return
        
        decoration = Decoration(deco_config)
        rendering_config = decoration.get_rendering_config()
        
        # Get custom bounding box if available, otherwise use rendering size
        bounding_box = rendering_config.get('bounding_box')
        if bounding_box:
            # Custom bounding box: [width, height] in pixels
            deco_width, deco_height = bounding_box[0], bounding_box[1]
        else:
            # Fallback to rendering size
            size = rendering_config.get('size', [settings.TILE_SIZE, settings.TILE_SIZE])
            deco_width, deco_height = size[0], size[1]
        
        offset = rendering_config.get('offset', [0, 0])
        
        # Calculate decoration bounding box in world coordinates
        tile_world_x = tile_x * settings.TILE_SIZE
        tile_world_y = tile_y * settings.TILE_SIZE
        tile_center_x = tile_world_x + settings.TILE_SIZE / 2.0
        tile_center_y = tile_world_y + settings.TILE_SIZE / 2.0
        
        # Decoration position (centered on tile + offset)
        deco_x = tile_center_x + offset[0] - deco_width / 2.0
        deco_y = tile_center_y + offset[1] - deco_height / 2.0
        
        # Convert decoration world position to screen coordinates
        screen_deco_x = (deco_x - self.world_controller.camera.x) * self.world_controller.camera_zoom + screen_width / 2.0
        screen_deco_y = (deco_y - self.world_controller.camera.y) * self.world_controller.camera_zoom + screen_height / 2.0
        
        # In pyglet, Y=0 is at bottom, so we need to adjust
        screen_deco_y = screen_height - screen_deco_y
        
        # Scale decoration size by zoom
        deco_width_scaled = deco_width * self.world_controller.camera_zoom
        deco_height_scaled = deco_height * self.world_controller.camera_zoom
        
        # Draw highlight rectangle (cyan overlay for decoration)
        highlight = pyglet.shapes.Rectangle(
            screen_deco_x,
            screen_deco_y - deco_height_scaled,
            deco_width_scaled,
            deco_height_scaled,
            color=(0, 255, 255)  # Cyan
        )
        highlight.opacity = 60  # Semi-transparent cyan overlay
        highlight.draw()
        
        # Draw border around decoration (cyan, thicker than tile border)
        border_width = 3  # Thicker border for decoration
        border_color = (0, 255, 255)  # Cyan
        border_opacity = 255  # Fully opaque
        
        # Top border
        top_border = pyglet.shapes.Rectangle(
            screen_deco_x,
            screen_deco_y - border_width,
            deco_width_scaled,
            border_width,
            color=border_color
        )
        top_border.opacity = border_opacity
        top_border.draw()
        
        # Bottom border
        bottom_border = pyglet.shapes.Rectangle(
            screen_deco_x,
            screen_deco_y - deco_height_scaled,
            deco_width_scaled,
            border_width,
            color=border_color
        )
        bottom_border.opacity = border_opacity
        bottom_border.draw()
        
        # Left border
        left_border = pyglet.shapes.Rectangle(
            screen_deco_x,
            screen_deco_y - deco_height_scaled,
            border_width,
            deco_height_scaled,
            color=border_color
        )
        left_border.opacity = border_opacity
        left_border.draw()
        
        # Right border
        right_border = pyglet.shapes.Rectangle(
            screen_deco_x + deco_width_scaled - border_width,
            screen_deco_y - deco_height_scaled,
            border_width,
            deco_height_scaled,
            color=border_color
        )
        right_border.opacity = border_opacity
        right_border.draw()
    
    def _render_decorations(self, visible_chunks, camera_x: float, camera_y: float):
        """
        Render decorations from visible chunks with proper layering.
        
        Args:
            visible_chunks: List of (chunk_x, chunk_y, tiles) tuples
            camera_x: Camera X position
            camera_y: Camera Y position
        """
        try:
            from world.decoration_registry import DecorationRegistry
            from world.decoration import Decoration
        except ImportError:
            return  # Decoration system not available
        
        import numpy as np
        import moderngl
        
        tile_size = settings.TILE_SIZE
        decoration_sprites = []  # List of (layer, x, y, width, height, color, decoration_data)
        
        # Collect all decorations from visible chunks
        for chunk_x, chunk_y, tiles in visible_chunks:
            if not tiles:
                continue
            
            chunk_world_x = chunk_x * settings.CHUNK_SIZE * tile_size
            chunk_world_y = chunk_y * settings.CHUNK_SIZE * tile_size
            
            for tile_y in range(len(tiles)):
                if not tiles[tile_y]:
                    continue
                for tile_x in range(len(tiles[tile_y])):
                    tile = tiles[tile_y][tile_x]
                    if not tile:
                        continue
                    
                    decoration_data = tile.get('decoration')
                    if not decoration_data:
                        continue
                    
                    decoration_id = decoration_data.get('decoration_id')
                    if not decoration_id:
                        continue
                    
                    # Get decoration config
                    deco_config = DecorationRegistry.get(decoration_id)
                    if not deco_config:
                        continue
                    
                    decoration = Decoration(deco_config)
                    rendering_config = decoration.get_rendering_config()
                    
                    # Calculate tile world position
                    tile_world_x = chunk_world_x + tile_x * tile_size
                    tile_world_y = chunk_world_y + tile_y * tile_size
                    
                    # Get rendering size and offset
                    size = rendering_config.get('size', [tile_size, tile_size])
                    offset = rendering_config.get('offset', [0, 0])
                    layer = rendering_config.get('layer', 10)
                    
                    # Calculate decoration position (centered on tile + offset)
                    deco_x = tile_world_x + tile_size / 2.0 + offset[0] - size[0] / 2.0
                    deco_y = tile_world_y + tile_size / 2.0 + offset[1] - size[1] / 2.0
                    
                    # Get sprite name and mod_id
                    mod_id = deco_config.get('mod_id', 'core')
                    deco_data_dict = decoration_data.get('data', {})
                    
                    # Determine current sprite based on state
                    sprite_name = None
                    
                    # Check for sprite_state (set during mining or stump phase)
                    sprite_state = deco_data_dict.get('sprite_state')
                    if sprite_state:
                        # Use sprite_state if available (default, damaged_50, stump)
                        sprite_name = deco_config['sprites'].get(sprite_state)
                    
                    # Fallback to harvestable state or default
                    if not sprite_name:
                        if decoration.is_harvestable():
                            has_fruit = deco_data_dict.get('has_fruit', True)
                            sprite_name = deco_config['sprites'].get('with_fruit' if has_fruit else 'without_fruit')
                        else:
                            sprite_name = deco_config['sprites'].get('default')
                    
                    # Fallback to color if texture not available
                    if not sprite_name:
                        sprite_name = 'default'
                    
                    # Get sprite color (fallback if texture not found)
                    if decoration_id == 'oak_tree':
                        color = (34, 139, 34)  # Forest green
                    elif decoration_id == 'berry_bush':
                        color = (0, 100, 0)  # Dark green
                    elif decoration_id == 'stone_rock':
                        color = (128, 128, 128)  # Gray
                    else:
                        color = (100, 100, 100)  # Default gray
                    
                    # Add shadow if enabled (Layer 5)
                    shadow_config = rendering_config.get('shadow', {})
                    if shadow_config.get('enabled', False):
                        shadow_offset = shadow_config.get('offset', [0, 0])
                        shadow_x = tile_world_x + tile_size / 2.0 + shadow_offset[0] - size[0] / 2.0
                        shadow_y = tile_world_y + tile_size / 2.0 + shadow_offset[1] - size[1] / 2.0
                        shadow_size = [size[0] * 0.8, size[1] * 0.3]  # Shadow is wider but shorter
                        shadow_sprite_name = shadow_config.get('sprite', 'shadow_small')
                        decoration_sprites.append((5, shadow_x, shadow_y, shadow_size[0], shadow_size[1], (0, 0, 0), None, shadow_sprite_name, mod_id))  # Black shadow
                    
                    # Add decoration (Layer 10 or from config) with sprite info
                    decoration_sprites.append((layer, deco_x, deco_y, size[0], size[1], color, decoration_data, sprite_name, mod_id))
        
        # Sort by layer for proper rendering order
        decoration_sprites.sort(key=lambda x: x[0])
        
        # Render decorations with textures
        if self.modern_gl_renderer.decoration_texture_manager:
            self._render_decorations_with_textures(decoration_sprites, camera_x, camera_y)
        else:
            # Fallback to color rendering
            self._render_decorations_with_colors(decoration_sprites)
    
    def _render_decorations_with_textures(self, decoration_sprites, camera_x: float, camera_y: float):
        """Render decorations using texture atlas (batched rendering for performance)."""
        import numpy as np
        import moderngl
        
        if not decoration_sprites:
            return
        
        # Use texture atlas from tile_texture_manager (includes decoration textures)
        tile_texture_manager = self.modern_gl_renderer.tile_texture_manager
        if not tile_texture_manager or not tile_texture_manager.texture_atlas:
            # Fallback to old method if atlas not available
            self._render_decorations_with_textures_legacy(decoration_sprites, camera_x, camera_y)
            return
        
        # Enable blending
        self.modern_gl_renderer.ctx.enable(moderngl.BLEND)
        self.modern_gl_renderer.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        
        # Collect all decorations with their atlas coordinates
        all_vertices = []  # All decorations in one batch
        progress_bars = []  # Collect progress bars to render after ModernGL
        
        for sprite_data in decoration_sprites:
            if len(sprite_data) >= 9:
                layer, x, y, width, height, color, deco_data, sprite_name, mod_id = sprite_data[:9]
            else:
                # Fallback for old format
                layer, x, y, width, height, color, deco_data = sprite_data[:7]
                sprite_name = None
                mod_id = 'core'
            
            if not sprite_name:
                continue
            
            # Get UV coordinates from atlas
            atlas_name = f"decoration:{mod_id}/{sprite_name}"
            uv_coords = tile_texture_manager.get_decoration_texture_coords(sprite_name, mod_id)
            
            if not uv_coords:
                # Fallback: try direct lookup
                if atlas_name in tile_texture_manager.texture_coords:
                    uv_coords = tile_texture_manager.texture_coords[atlas_name]
                else:
                    # Skip if not in atlas
                    continue
            
            u0, v0, u1, v1 = uv_coords
            
            # Get regrowth progress for progress bar (if harvestable and harvested)
            regrowth_progress = None
            mining_progress = None
            if deco_data:
                deco_data_dict = deco_data.get('data', {})
                has_fruit = deco_data_dict.get('has_fruit', True)
                if not has_fruit:
                    # Calculate regrowth progress
                    growth_timer = deco_data_dict.get('growth_timer', 0.0)
                    initial_growth_time = deco_data_dict.get('initial_growth_time', 0.0)
                    
                    # Calculate progress: elapsed time / total regrowth time
                    # growth_timer starts at initial_growth_time and counts down to 0
                    # So elapsed = initial_growth_time - growth_timer
                    if initial_growth_time > 0 and growth_timer >= 0:
                        elapsed = initial_growth_time - growth_timer
                        regrowth_progress = max(0.0, min(1.0, elapsed / initial_growth_time))
                
                # Calculate mining progress (if being mined)
                elapsed_time = deco_data_dict.get('elapsed_time', 0.0)
                if elapsed_time > 0.0:
                    from world.decoration_registry import DecorationRegistry
                    decoration_id = deco_data.get('decoration_id')
                    if decoration_id:
                        deco_config = DecorationRegistry.get(decoration_id)
                        if deco_config:
                            mining_config = deco_config.get('mining', {})
                            if mining_config:
                                mining_time = mining_config.get('mining_time', 3.0)
                                hardness_multiplier = mining_config.get('hardness_multiplier', 1.0)
                                resource_hardness = mining_config.get('hardness', 'wood')
                                
                                # Get tool for mining speed multiplier
                                tool = self.world_controller.get_equipped_tool()
                                tool_id = tool.get('tool_id') if tool else None
                                
                                # Get mining speed multiplier from ToolMappingRegistry
                                try:
                                    from world.tool_mapping_registry import ToolMappingRegistry
                                    if tool_id:
                                        mining_speed_multiplier = ToolMappingRegistry.get_mining_speed_multiplier(tool_id)
                                    else:
                                        mining_speed_multiplier = ToolMappingRegistry.get_mining_speed_multiplier('hand')
                                except ImportError:
                                    mining_speed_multiplier = 0.3  # Hand speed
                                
                                # Calculate time to mine
                                time_to_mine = (mining_time * hardness_multiplier) / mining_speed_multiplier
                                if time_to_mine > 0:
                                    mining_progress = min(elapsed_time / time_to_mine, 1.0)
            
            # Create quad vertices with atlas UV coordinates
            # Format: position (2f), color_index (1f), texcoord (2f), use_texture (1f)
            # OpenGL: (0,0) bottom-left, but PIL/our coords are top-left, so flip V
            # Note: In our coordinate system, y increases downward, so y is top and y+height is bottom
            # But we want the texture to render correctly, so we use v0 for top and v1 for bottom
            all_vertices.extend([
                [x, y + height, 0.0, u0, v1, 1.0],  # Bottom-left (world: y+height, tex: v1)
                [x + width, y + height, 0.0, u1, v1, 1.0],  # Bottom-right (world: y+height, tex: v1)
                [x + width, y, 0.0, u1, v0, 1.0],  # Top-right (world: y, tex: v0)
                [x, y + height, 0.0, u0, v1, 1.0],  # Bottom-left (world: y+height, tex: v1)
                [x + width, y, 0.0, u1, v0, 1.0],  # Top-right (world: y, tex: v0)
                [x, y, 0.0, u0, v0, 1.0],  # Top-left (world: y, tex: v0)
            ])
            
            # Collect regrowth and mining progress bar data to render after ModernGL
            if regrowth_progress is not None and regrowth_progress < 1.0:
                progress_bars.append(('regrowth', x, y, width, height, regrowth_progress))
            if mining_progress is not None and mining_progress < 1.0:
                progress_bars.append(('mining', x, y, width, height, mining_progress))
        
        # Render all decorations in one batch using atlas
        if all_vertices:
            vertices_array = np.array(all_vertices, dtype=np.float32)
            vbo = self.modern_gl_renderer.ctx.buffer(vertices_array.tobytes())
            vao = self.modern_gl_renderer.ctx.vertex_array(
                self.modern_gl_renderer.chunk_program,
                [(vbo, "2f 1f 2f 1f", "in_position", "in_color_index", "in_texcoord", "in_use_texture")]
            )
            
            # Bind texture atlas to unit 0
            tile_texture_manager.texture_atlas.use(0)
            
            # Update shader to use texture
            if 'tile_texture' in self.modern_gl_renderer.chunk_program:
                self.modern_gl_renderer.chunk_program['tile_texture'].value = 0
            
            # Render all decorations in one draw call
            vao.render(moderngl.TRIANGLES)
            
            # Cleanup
            vao.release()
            vbo.release()
        
        # Render progress bars after ModernGL rendering (using pyglet.shapes)
        if progress_bars:
            for bar_type, x, y, width, height, progress in progress_bars:
                if bar_type == 'regrowth':
                    self._render_regrowth_progress_bar(x, y, width, height, progress, camera_x, camera_y)
                elif bar_type == 'mining':
                    self._render_mining_progress_bar(x, y, width, height, progress, camera_x, camera_y)
    
    def _render_decorations_with_textures_legacy(self, decoration_sprites, camera_x: float, camera_y: float):
        """Legacy rendering method using separate textures (fallback if atlas not available)."""
        import numpy as np
        import moderngl
        
        if not decoration_sprites:
            return
        
        texture_manager = self.modern_gl_renderer.decoration_texture_manager
        if not texture_manager:
            return
        
        # Enable blending
        self.modern_gl_renderer.ctx.enable(moderngl.BLEND)
        self.modern_gl_renderer.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        
        # Group by texture for batching
        texture_batches = {}  # (texture, mod_id) -> list of sprites
        
        for sprite_data in decoration_sprites:
            if len(sprite_data) >= 9:
                layer, x, y, width, height, color, deco_data, sprite_name, mod_id = sprite_data[:9]
            else:
                # Fallback for old format
                layer, x, y, width, height, color, deco_data = sprite_data[:7]
                sprite_name = None
                mod_id = 'core'
            
            if not sprite_name:
                continue
            
            # Load texture (will return missing texture if not found)
            texture = texture_manager.get_texture(sprite_name, mod_id)
            if not texture:
                continue
            
            batch_key = (texture, mod_id)
            if batch_key not in texture_batches:
                texture_batches[batch_key] = []
            texture_batches[batch_key].append((x, y, width, height))
        
        # Render each texture batch
        for (texture, mod_id), sprites in texture_batches.items():
            complete_vertices = []
            for x, y, width, height in sprites:
                # Quad with all required attributes: position, color_index, texcoord, use_texture
                complete_vertices.extend([
                    [x, y, 0.0, 0.0, 0.0, 1.0],  # position, color_index, texcoord, use_texture
                    [x + width, y, 0.0, 1.0, 0.0, 1.0],
                    [x + width, y + height, 0.0, 1.0, 1.0, 1.0],
                    [x, y, 0.0, 0.0, 0.0, 1.0],
                    [x + width, y + height, 0.0, 1.0, 1.0, 1.0],
                    [x, y + height, 0.0, 0.0, 1.0, 1.0],
                ])
            
            if complete_vertices:
                complete_array = np.array(complete_vertices, dtype=np.float32)
                vbo = self.modern_gl_renderer.ctx.buffer(complete_array.tobytes())
                vao = self.modern_gl_renderer.ctx.vertex_array(
                    self.modern_gl_renderer.chunk_program,
                    [(vbo, "2f 1f 2f 1f", "in_position", "in_color_index", "in_texcoord", "in_use_texture")]
                )
                
                # Bind texture to unit 0
                texture.use(0)
                
                # Update shader to use texture
                if 'tile_texture' in self.modern_gl_renderer.chunk_program:
                    self.modern_gl_renderer.chunk_program['tile_texture'].value = 0
                
                # Render
                vao.render(moderngl.TRIANGLES)
                
                # Cleanup
                vao.release()
                vbo.release()
    
    def _render_regrowth_progress_bar(self, deco_x: float, deco_y: float, deco_width: float, deco_height: float, 
                                      progress: float, camera_x: float, camera_y: float):
        """Render a small progress bar above decoration showing regrowth progress."""
        import pyglet.shapes
        
        if not self.world_controller.camera:
            return
        
        # Calculate screen position
        screen_width = self.modern_gl_renderer.screen_width
        screen_height = self.modern_gl_renderer.screen_height
        zoom = self.world_controller.camera_zoom
        
        # Progress bar position: above decoration, centered
        bar_width = deco_width * 0.8  # 80% of decoration width
        bar_height = 3  # 3 pixels high
        bar_x = deco_x + (deco_width - bar_width) / 2.0
        bar_y = deco_y + deco_height + 2  # 2 pixels above decoration
        
        # Convert to screen coordinates (same transformation as tile highlight)
        screen_bar_x = (bar_x - camera_x) * zoom + screen_width / 2.0
        screen_bar_y = (bar_y - camera_y) * zoom + screen_height / 2.0
        
        # In pyglet, Y=0 is at bottom, so we need to adjust
        screen_bar_y = screen_height - screen_bar_y
        
        # Scale by zoom
        bar_width_scaled = bar_width * zoom
        bar_height_scaled = bar_height * zoom
        
        # Ensure minimum size for visibility
        if bar_width_scaled < 1:
            bar_width_scaled = 1
        if bar_height_scaled < 1:
            bar_height_scaled = 1
        
        # Draw background (dark gray)
        bg_bar = pyglet.shapes.Rectangle(
            int(screen_bar_x),
            int(screen_bar_y - bar_height_scaled),
            int(bar_width_scaled),
            int(bar_height_scaled),
            color=(40, 40, 40)  # Dark gray background
        )
        bg_bar.opacity = 200
        bg_bar.draw()
        
        # Draw progress (green, transitioning to yellow when near completion)
        progress_width = bar_width_scaled * progress
        if progress > 0 and progress_width >= 1:
            # Color: green -> yellow -> green (smooth transition)
            if progress < 0.5:
                # Green to yellow
                r = int(0 + (255 - 0) * (progress * 2))
                g = 255
                b = 0
            else:
                # Yellow to green
                r = 255
                g = int(255 - (255 - 0) * ((progress - 0.5) * 2))
                b = 0
            
            progress_bar = pyglet.shapes.Rectangle(
                int(screen_bar_x),
                int(screen_bar_y - bar_height_scaled),
                int(progress_width),
                int(bar_height_scaled),
                color=(r, g, b)
            )
            progress_bar.opacity = 255
            progress_bar.draw()
    
    def _render_decorations_with_colors(self, decoration_sprites):
        """Render decorations using colors (fallback)."""
        current_layer = None
        batch_vertices = []
        
        for sprite_data in decoration_sprites:
            if len(sprite_data) >= 7:
                layer, x, y, width, height, color, deco_data = sprite_data[:7]
            else:
                continue
            
            if layer != current_layer:
                # Render previous batch
                if batch_vertices:
                    self._render_decoration_batch(batch_vertices)
                    batch_vertices = []
                current_layer = layer
            
            # Create vertices for decoration quad
            r, g, b = color[:3] if len(color) >= 3 else (100, 100, 100)
            color_index = float(self.modern_gl_renderer.tile_color_palette.get_color_index(color))
            if color_index == 0 and color not in self.modern_gl_renderer.tile_color_palette.color_to_index:
                color_index = float(self.modern_gl_renderer.tile_color_palette.add_color(color))
                self.modern_gl_renderer._update_palette_uniform()
            
            # Add vertices for this decoration
            batch_vertices.extend([
                [x, y, color_index],
                [x + width, y, color_index],
                [x + width, y + height, color_index],
                [x, y, color_index],
                [x + width, y + height, color_index],
                [x, y + height, color_index],
            ])
        
        # Render final batch
        if batch_vertices:
            self._render_decoration_batch(batch_vertices)
            if layer != current_layer:
                # Render previous batch
                if batch_vertices:
                    self._render_decoration_batch(batch_vertices)
                    batch_vertices = []
                current_layer = layer
            
            # Create vertices for decoration quad
            r, g, b = color[:3] if len(color) >= 3 else (100, 100, 100)
            color_index = float(self.modern_gl_renderer.tile_color_palette.get_color_index(color))
            if color_index == 0 and color not in self.modern_gl_renderer.tile_color_palette.color_to_index:
                color_index = float(self.modern_gl_renderer.tile_color_palette.add_color(color))
                self.modern_gl_renderer._update_palette_uniform()
            
            # Add vertices for this decoration
            batch_vertices.extend([
                [x, y, color_index],
                [x + width, y, color_index],
                [x + width, y + height, color_index],
                [x, y, color_index],
                [x + width, y + height, color_index],
                [x, y + height, color_index],
            ])
        
        # Render final batch
        if batch_vertices:
            self._render_decoration_batch(batch_vertices)
    
    def _render_decoration_batch(self, vertices_list):
        """Render a batch of decoration vertices."""
        import numpy as np
        import moderngl
        
        if not vertices_list:
            return
        
        vertices = np.array(vertices_list, dtype=np.float32)
        vbo = self.modern_gl_renderer.ctx.buffer(vertices.tobytes())
        vao = self.modern_gl_renderer.ctx.vertex_array(
            self.modern_gl_renderer.chunk_program,
            [(vbo, "2f 1f", "in_position", "in_color_index")]
        )
        
        vao.render(moderngl.TRIANGLES)
        
        vao.release()
        vbo.release()
    
    def _render_mining_progress_bar(self, deco_x: float, deco_y: float, deco_width: float, deco_height: float,
                                    progress: float, camera_x: float, camera_y: float):
        """Render a small progress bar above decoration showing mining progress."""
        import pyglet.shapes
        
        if not self.world_controller.camera:
            return
        
        # Calculate screen position
        screen_width = self.modern_gl_renderer.screen_width
        screen_height = self.modern_gl_renderer.screen_height
        zoom = self.world_controller.camera_zoom
        
        # Progress bar position: above decoration, centered
        bar_width = deco_width * 0.8  # 80% of decoration width
        bar_height = 3  # 3 pixels high
        bar_x = deco_x + (deco_width - bar_width) / 2.0
        bar_y = deco_y + deco_height + 2  # 2 pixels above decoration
        
        # Convert to screen coordinates (same transformation as regrowth timer)
        screen_bar_x = (bar_x - camera_x) * zoom + screen_width / 2.0
        screen_bar_y = (bar_y - camera_y) * zoom + screen_height / 2.0
        
        # In pyglet, Y=0 is at bottom, so we need to adjust
        screen_bar_y = screen_height - screen_bar_y
        
        # Scale by zoom
        bar_width_scaled = bar_width * zoom
        bar_height_scaled = bar_height * zoom
        
        # Ensure minimum size for visibility
        if bar_width_scaled < 1:
            bar_width_scaled = 1
        if bar_height_scaled < 1:
            bar_height_scaled = 1
        
        # Draw background (dark gray)
        bg_bar = pyglet.shapes.Rectangle(
            int(screen_bar_x),
            int(screen_bar_y - bar_height_scaled),
            int(bar_width_scaled),
            int(bar_height_scaled),
            color=(40, 40, 40)  # Dark gray background
        )
        bg_bar.opacity = 200
        bg_bar.draw()
        
        # Draw progress (red, from 100% to 0%)
        progress_width = bar_width_scaled * progress
        if progress > 0 and progress_width >= 1:
            progress_bar = pyglet.shapes.Rectangle(
                int(screen_bar_x),
                int(screen_bar_y - bar_height_scaled),
                int(progress_width),
                int(bar_height_scaled),
                color=(255, 0, 0)  # Red
            )
            progress_bar.opacity = 255
            progress_bar.draw()


