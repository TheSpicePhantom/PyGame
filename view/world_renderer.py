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
        """Render highlight for tile under mouse cursor if within 8 tiles of player"""
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
        
        # Draw border around highlighted tile (using separate rectangles for each edge)
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
                    
                    # Get sprite color (placeholder - will use texture later)
                    # For now, use a color based on decoration type
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
                        decoration_sprites.append((5, shadow_x, shadow_y, shadow_size[0], shadow_size[1], (0, 0, 0), None))  # Black shadow
                    
                    # Add decoration (Layer 10 or from config)
                    decoration_sprites.append((layer, deco_x, deco_y, size[0], size[1], color, decoration_data))
        
        # Sort by layer for proper rendering order
        decoration_sprites.sort(key=lambda x: x[0])
        
        # Render decorations in batches by layer
        current_layer = None
        batch_vertices = []
        
        for layer, x, y, width, height, color, deco_data in decoration_sprites:
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
        
        # Render mining progress bars if any decorations are being mined
        self._render_mining_progress_bars(visible_chunks, camera_x, camera_y)
    
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
    
    def _render_mining_progress_bars(self, visible_chunks, camera_x: float, camera_y: float):
        """
        Render mining progress bars over decorations being mined.
        
        Args:
            visible_chunks: List of (chunk_x, chunk_y, tiles) tuples
            camera_x: Camera X position
            camera_y: Camera Y position
        """
        try:
            from world.decoration_registry import DecorationRegistry
            from world.decoration import Decoration
        except ImportError:
            return
        
        import pyglet.shapes
        
        tile_size = settings.TILE_SIZE
        
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
                    
                    deco_data = decoration_data.get('data', {})
                    damage = deco_data.get('damage', 0.0)
                    
                    if damage <= 0.0:
                        continue  # Not being mined
                    
                    decoration_id = decoration_data.get('decoration_id')
                    deco_config = DecorationRegistry.get(decoration_id)
                    if not deco_config:
                        continue
                    
                    mining_config = deco_config.get('mining', {})
                    durability = mining_config.get('durability', 100)
                    
                    if durability <= 0:
                        continue
                    
                    progress = min(damage / durability, 1.0)
                    
                    # Calculate tile world position
                    tile_world_x = chunk_world_x + tile_x * tile_size
                    tile_world_y = chunk_world_y + tile_y * tile_size
                    
                    # Convert to screen coordinates
                    screen_x = (tile_world_x - camera_x) * self.world_controller.camera_zoom + self.modern_gl_renderer.screen_width / 2.0
                    screen_y = (tile_world_y - camera_y) * self.world_controller.camera_zoom + self.modern_gl_renderer.screen_height / 2.0
                    screen_y = self.modern_gl_renderer.screen_height - screen_y  # Flip Y
                    
                    # Draw progress bar
                    bar_width = tile_size * self.world_controller.camera_zoom * 0.8
                    bar_height = 4 * self.world_controller.camera_zoom
                    bar_x = screen_x + (tile_size * self.world_controller.camera_zoom - bar_width) / 2.0
                    bar_y = screen_y - tile_size * self.world_controller.camera_zoom - 8
                    
                    # Background (black)
                    bg = pyglet.shapes.Rectangle(bar_x, bar_y, bar_width, bar_height, color=(0, 0, 0))
                    bg.opacity = 200
                    bg.draw()
                    
                    # Progress (yellow)
                    progress_width = bar_width * progress
                    if progress_width > 0:
                        progress_bar = pyglet.shapes.Rectangle(bar_x, bar_y, progress_width, bar_height, color=(255, 255, 0))
                        progress_bar.opacity = 255
                        progress_bar.draw()


