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
        
        # Step 2: Collect all visible chunks (with frustum culling based on zoom)
        chunks_data = []
        screen_width = self.modern_gl_renderer.screen_width
        screen_height = self.modern_gl_renderer.screen_height
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        
        # Calculate visible area bounds
        visible_world_width = screen_width / self.world_controller.camera_zoom
        visible_world_height = screen_height / self.world_controller.camera_zoom
        
        world_min_x = camera_x - visible_world_width / 2.0
        world_max_x = camera_x + visible_world_width / 2.0
        world_min_y = camera_y - visible_world_height / 2.0
        world_max_y = camera_y + visible_world_height / 2.0
        
        # Process chunks: visible -> rendering -> active -> rendered
        for chunk in self.world_controller.world.chunk_manager.loaded_chunks.values():
            if chunk.render_state == "rendered":
                chunk.render_state = None
        
        # Process all loaded chunks - render all chunks that are in the visible area
        for chunk in self.world_controller.world.chunk_manager.loaded_chunks.values():
            chunk_world_x = chunk.chunk_x * chunk_size_pixels
            chunk_world_y = chunk.chunk_y * chunk_size_pixels
            chunk_world_max_x = chunk_world_x + chunk_size_pixels
            chunk_world_max_y = chunk_world_y + chunk_size_pixels
            
            # Frustum culling
            x_overlaps = (chunk_world_x <= world_max_x) and (chunk_world_max_x >= world_min_x)
            y_overlaps = (chunk_world_y <= world_max_y) and (chunk_world_max_y >= world_min_y)
            chunk_overlaps = x_overlaps and y_overlaps
            
            if not chunk_overlaps:
                if chunk.render_state == "rendering":
                    chunk.render_state = "inactive"
                elif chunk.render_state == "visible":
                    chunk.render_state = "inactive"
                continue
            
            # Chunk passed frustum culling
            if chunk.render_state == "visible":
                chunk.render_state = "rendering"
            if chunk.render_state == "rendering":
                chunk.render_state = "active"
            
            if chunk.tiles:
                chunks_data.append((chunk.chunk_x, chunk.chunk_y, chunk.tiles))
        
        # Step 3: Render all visible chunks
        if chunks_data:
            self.modern_gl_renderer.render_chunks(chunks_data, performance_monitor=self.world_controller.performance_monitor)
            
            # Mark rendered chunks as "rendered"
            for chunk_x, chunk_y, _ in chunks_data:
                chunk_key = (chunk_x, chunk_y)
                if chunk_key in self.world_controller.world.chunk_manager.loaded_chunks:
                    chunk = self.world_controller.world.chunk_manager.loaded_chunks[chunk_key]
                    if chunk.render_state == "active":
                        chunk.render_state = "rendered"
        
        # Step 4: Render player
        if self.world_controller.player:
            self._render_player()
    
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
        
        r, g, b = 1.0, 1.0, 0.0  # Yellow
        
        vertices = np.array([
            [world_x0, world_y0, r, g, b],
            [world_x1, world_y0, r, g, b],
            [world_x1, world_y1, r, g, b],
            [world_x0, world_y0, r, g, b],
            [world_x1, world_y1, r, g, b],
            [world_x0, world_y1, r, g, b],
        ], dtype=np.float32)
        
        vbo = self.modern_gl_renderer.ctx.buffer(vertices.tobytes())
        vao = self.modern_gl_renderer.ctx.vertex_array(
            self.modern_gl_renderer.chunk_program,
            [(vbo, "2f 3f", "in_position", "in_color")]
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


