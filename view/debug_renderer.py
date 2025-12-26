"""
View: DebugRenderer - Rendering von Debug-Visualisierung und Performance-Overlay
"""
from typing import Optional
import numpy as np
import moderngl
from core import settings
from core.game_state import GameState
from core.world_controller import WorldController
from core.ui_controller import UIController
from analytics.performance_monitor import PerformanceMonitor


class DebugRenderer:
    """Rendert Debug-Visualisierung und Performance-Overlay"""
    
    def __init__(self, world_controller: WorldController, ui_controller: UIController,
                 performance_monitor: PerformanceMonitor, modern_gl_renderer, width: int, height: int):
        """
        Args:
            world_controller: WorldController instance
            ui_controller: UIController instance
            performance_monitor: PerformanceMonitor instance
            modern_gl_renderer: ModernGLRenderer instance
            width: Window width
            height: Window height
        """
        self.world_controller = world_controller
        self.ui_controller = ui_controller
        self.performance_monitor = performance_monitor
        self.modern_gl_renderer = modern_gl_renderer
        self.width = width
        self.height = height
        
        # Debug visualization cache
        self._debug_cache = {
            'mode': -1,
            'player_chunk': None,
            'chunks_hash': None,
            'vbo': None,
            'vao': None,
            'line_count': 0,
            'chunk_overlay_vbo': None,
            'chunk_overlay_vao': None
        }
    
    def draw_debug_visualization(self, chunks_data: list, debug_visualization_mode: int):
        """Render debug visualization: chunk boundaries (red), region boundaries (blue), and tile grids"""
        if not chunks_data or not self.world_controller.world or not self.world_controller.player:
            if debug_visualization_mode == 0 and self._debug_cache['vbo']:
                self._debug_cache['vbo'].release()
                self._debug_cache['vao'].release()
                self._debug_cache['vbo'] = None
                self._debug_cache['vao'] = None
            return
        
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        tile_size_pixels = settings.TILE_SIZE
        
        # Region size: 5x5 chunks per region
        REGION_SIZE_CHUNKS = 5
        region_size_pixels = REGION_SIZE_CHUNKS * chunk_size_pixels
        
        player_world_x = self.world_controller.player.rect.center[0]
        player_world_y = self.world_controller.player.rect.center[1]
        player_chunk_x = int(player_world_x // chunk_size_pixels)
        player_chunk_y = int(player_world_y // chunk_size_pixels)
        player_chunk = (player_chunk_x, player_chunk_y)
        
        chunks_hash = hash(tuple(sorted((x, y) for x, y, _ in chunks_data)))
        zoom = self.world_controller.camera_zoom
        
        cache_valid = (
            self._debug_cache['mode'] == debug_visualization_mode and
            self._debug_cache['player_chunk'] == player_chunk and
            self._debug_cache['chunks_hash'] == chunks_hash and
            self._debug_cache.get('zoom') == zoom and
            self._debug_cache['vbo'] is not None
        )
        
        if not cache_valid:
            if self._debug_cache['vbo']:
                self._debug_cache['vbo'].release()
                self._debug_cache['vao'].release()
            
            lines = []
            
            # Collect unique chunks and regions
            chunks_set = set((x, y) for x, y, _ in chunks_data)
            regions_set = set()
            
            for chunk_x, chunk_y in chunks_set:
                # Calculate region coordinates (5x5 chunks per region)
                region_x = chunk_x // REGION_SIZE_CHUNKS
                region_y = chunk_y // REGION_SIZE_CHUNKS
                regions_set.add((region_x, region_y))
            
            # Draw chunk boundaries in red (mode >= 1)
            if debug_visualization_mode >= 1:
                for chunk_x, chunk_y in chunks_set:
                    chunk_world_x = chunk_x * chunk_size_pixels
                    chunk_world_y = chunk_y * chunk_size_pixels
                    chunk_world_max_x = chunk_world_x + chunk_size_pixels
                    chunk_world_max_y = chunk_world_y + chunk_size_pixels
                    
                    # Red lines for chunk boundaries
                    lines.append([chunk_world_x, chunk_world_y, chunk_world_max_x, chunk_world_y, 1.0, 0.0, 0.0])  # Bottom
                    lines.append([chunk_world_x, chunk_world_max_y, chunk_world_max_x, chunk_world_max_y, 1.0, 0.0, 0.0])  # Top
                    lines.append([chunk_world_x, chunk_world_y, chunk_world_x, chunk_world_max_y, 1.0, 0.0, 0.0])  # Left
                    lines.append([chunk_world_max_x, chunk_world_y, chunk_world_max_x, chunk_world_max_y, 1.0, 0.0, 0.0])  # Right
            
            # Draw region boundaries in blue (mode >= 1)
            if debug_visualization_mode >= 1:
                # Draw all region boundaries (including internal ones)
                for region_x, region_y in regions_set:
                    region_world_x = region_x * region_size_pixels
                    region_world_y = region_y * region_size_pixels
                    region_world_max_x = region_world_x + region_size_pixels
                    region_world_max_y = region_world_y + region_size_pixels
                    
                    # Blue lines for region boundaries (all edges)
                    # Top edge
                    lines.append([region_world_x, region_world_max_y, region_world_max_x, region_world_max_y, 0.0, 0.0, 1.0])
                    # Bottom edge
                    lines.append([region_world_x, region_world_y, region_world_max_x, region_world_y, 0.0, 0.0, 1.0])
                    # Left edge
                    lines.append([region_world_x, region_world_y, region_world_x, region_world_max_y, 0.0, 0.0, 1.0])
                    # Right edge
                    lines.append([region_world_max_x, region_world_y, region_world_max_x, region_world_max_y, 0.0, 0.0, 1.0])
            
            # Draw tile grids (mode >= 2, only when zoom < 1.0)
            if debug_visualization_mode >= 2 and zoom < 1.0:
                # Calculate 5x5 chunks area centered on player's chunk
                grid_radius = 2  # 5x5 = radius 2 (2 chunks in each direction from center)
                grid_min_x = player_chunk_x - grid_radius
                grid_max_x = player_chunk_x + grid_radius
                grid_min_y = player_chunk_y - grid_radius
                grid_max_y = player_chunk_y + grid_radius
                
                # Draw tile grids only for chunks in the 5x5 area around player
                for chunk_x, chunk_y in chunks_set:
                    if grid_min_x <= chunk_x <= grid_max_x and grid_min_y <= chunk_y <= grid_max_y:
                        chunk_world_x = chunk_x * chunk_size_pixels
                        chunk_world_y = chunk_y * chunk_size_pixels
                        chunk_world_max_x = chunk_world_x + chunk_size_pixels
                        chunk_world_max_y = chunk_world_y + chunk_size_pixels
                        
                        # Black lines for tile grid
                        # Vertical tile lines
                        for tile_x in range(1, settings.CHUNK_SIZE):
                            tile_world_x = chunk_world_x + tile_x * tile_size_pixels
                            lines.append([tile_world_x, chunk_world_y, tile_world_x, chunk_world_max_y, 0.0, 0.0, 0.0])
                        
                        # Horizontal tile lines
                        for tile_y in range(1, settings.CHUNK_SIZE):
                            tile_world_y = chunk_world_y + tile_y * tile_size_pixels
                            lines.append([chunk_world_x, tile_world_y, chunk_world_max_x, tile_world_y, 0.0, 0.0, 0.0])
            
            if lines:
                vertices = []
                for x1, y1, x2, y2, r, g, b in lines:
                    # Convert RGB to color index
                    rgb_color = (int(r * 255), int(g * 255), int(b * 255))
                    color_index = float(self.modern_gl_renderer.tile_color_palette.get_color_index(rgb_color))
                    
                    # If color not in palette, add it
                    if color_index == 0 and rgb_color not in self.modern_gl_renderer.tile_color_palette.color_to_index:
                        color_index = float(self.modern_gl_renderer.tile_color_palette.add_color(rgb_color))
                        # Update palette uniform in shader
                        self.modern_gl_renderer._update_palette_uniform()
                    
                    vertices.extend([
                        [x1, y1, color_index],
                        [x2, y2, color_index]
                    ])
                
                vertices_array = np.array(vertices, dtype=np.float32)
                
                self._debug_cache['vbo'] = self.modern_gl_renderer.ctx.buffer(vertices_array.tobytes())
                self._debug_cache['vao'] = self.modern_gl_renderer.ctx.vertex_array(
                    self.modern_gl_renderer.chunk_program,
                    [(self._debug_cache['vbo'], "2f 1f", "in_position", "in_color_index")]
                )
                self._debug_cache['line_count'] = len(lines)
            else:
                self._debug_cache['vbo'] = None
                self._debug_cache['vao'] = None
                self._debug_cache['line_count'] = 0
            
            self._debug_cache['mode'] = debug_visualization_mode
            self._debug_cache['player_chunk'] = player_chunk
            self._debug_cache['chunks_hash'] = chunks_hash
            self._debug_cache['zoom'] = zoom
        
        if self._debug_cache['vao']:
            self._debug_cache['vao'].render(moderngl.LINES)
        
        # Draw chunk overlays (colored backgrounds) and text labels
        if debug_visualization_mode >= 1:
            self._draw_chunk_overlays(chunks_data)
            self._draw_chunk_labels(chunks_data)
    
    def draw_performance_stats(self, current_state: GameState):
        """Draw performance statistics overlay"""
        if not self.ui_controller.show_performance_stats or current_state == GameState.PAUSED:
            return
        
        import pyglet.text
        import time
        
        stats = self.performance_monitor.get_stats()
        
        # Get world info
        seed = None
        if self.world_controller.world and self.world_controller.world.chunk_manager:
            seed = self.world_controller.world.chunk_manager.get_seed()
            if seed is None and hasattr(self.world_controller.world, 'terrain_gen'):
                seed = self.world_controller.world.terrain_gen.seed
        
        # Build stats text
        lines = []
        lines.append(f"FPS: {stats.get('fps', 0):.1f}")
        
        if self.world_controller.world and self.world_controller.world.chunk_manager:
            total_loaded = len(self.world_controller.world.chunk_manager.loaded_chunks)
            lines.append(f"Loaded Chunks: {total_loaded}")
            
            if self.world_controller.camera:
                screen_width = self.modern_gl_renderer.screen_width
                screen_height = self.modern_gl_renderer.screen_height
                world_min_x = self.world_controller.camera.x - (screen_width / 2.0) / self.world_controller.camera_zoom
                world_max_x = self.world_controller.camera.x + (screen_width / 2.0) / self.world_controller.camera_zoom
                world_min_y = self.world_controller.camera.y - (screen_height / 2.0) / self.world_controller.camera_zoom
                world_max_y = self.world_controller.camera.y + (screen_height / 2.0) / self.world_controller.camera_zoom
                
                visible_chunks = 0
                chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
                for chunk in self.world_controller.world.chunk_manager.loaded_chunks.values():
                    chunk_world_x = chunk.chunk_x * chunk_size_pixels
                    chunk_world_y = chunk.chunk_y * chunk_size_pixels
                    chunk_world_max_x = chunk_world_x + chunk_size_pixels
                    chunk_world_max_y = chunk_world_y + chunk_size_pixels
                    
                    if (chunk_world_x <= world_max_x and chunk_world_max_x >= world_min_x and
                        chunk_world_y <= world_max_y and chunk_world_max_y >= world_min_y):
                        visible_chunks += 1
                
                lines.append(f"Visible Chunks: {visible_chunks}")
        
        if seed is not None:
            lines.append(f"Seed: {seed}")
        
        if self.world_controller.player:
            lines.append(f"Pos: ({self.world_controller.player.rect.x:.0f}, {self.world_controller.player.rect.y:.0f})")
        
        if self.world_controller.camera:
            lines.append(f"Camera: ({self.world_controller.camera.x:.0f}, {self.world_controller.camera.y:.0f})")
        
        lines.append(f"Zoom: {self.world_controller.camera_zoom:.2f}")
        
        # VBO Pool info
        if self.world_controller.modern_gl_renderer and hasattr(self.world_controller.modern_gl_renderer, 'chunk_vbo_pool'):
            vbo_stats = self.world_controller.modern_gl_renderer.chunk_vbo_pool.get_stats()
            lines.append(f"VBO Pool: {vbo_stats['in_use']}/{vbo_stats['pool_size']} (peak: {vbo_stats['peak_usage']})")
        
        # Auto-save info
        if self.world_controller.auto_save:
            auto_save_enabled = self.world_controller.auto_save.is_enabled()
            auto_save_running = self.world_controller.auto_save.running
            auto_save_interval = self.world_controller.auto_save.get_interval()
            lines.append(f"Auto-Save: {'ON' if auto_save_enabled else 'OFF'}")
            if auto_save_running:
                lines.append(f"Auto-Save Interval: {auto_save_interval:.1f}s")
                if hasattr(self.world_controller.auto_save, 'last_save_time'):
                    elapsed = time.time() - self.world_controller.auto_save.last_save_time
                    lines.append(f"Time since last save: {elapsed:.1f}s")
        
        # Draw stats text
        y_offset = self.height - 30
        text_color = (255, 255, 255, 255)
        
        for i, line in enumerate(lines):
            label = pyglet.text.Label(
                line,
                font_name='Courier New',
                font_size=14,
                x=10,
                y=y_offset - i * 20,
                anchor_x='left',
                anchor_y='top',
                color=text_color
            )
            label.draw()
    
    def _draw_chunk_overlays(self, chunks_data: list):
        """Draw colored overlays for chunks (green for load/render, red for unload)"""
        if not chunks_data or not self.world_controller.world or not self.world_controller.camera:
            return
        
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        camera_x = self.world_controller.camera.x
        camera_y = self.world_controller.camera.y
        
        # Get chunk ranges
        ranges = self.world_controller.get_chunk_ranges(camera_x, camera_y)
        if not ranges['load_range']:
            return
        
        load_range = ranges['load_range']
        render_range = ranges['render_range']
        unload_range = ranges['unload_range']
        
        # Collect all loaded chunks
        all_chunks = set()
        if self.world_controller.world.chunk_manager:
            for chunk in self.world_controller.world.chunk_manager.loaded_chunks.values():
                all_chunks.add((chunk.chunk_x, chunk.chunk_y))
        
        # Also include chunks from chunks_data
        for chunk_x, chunk_y, _ in chunks_data:
            all_chunks.add((chunk_x, chunk_y))
        
        # Create quads for overlays
        quads = []
        
        load_min_x, load_max_x, load_min_y, load_max_y = load_range
        render_min_x, render_max_x, render_min_y, render_max_y = render_range
        unload_min_x, unload_max_x, unload_min_y, unload_max_y = unload_range
        
        for chunk_x, chunk_y in all_chunks:
            chunk_world_x = chunk_x * chunk_size_pixels
            chunk_world_y = chunk_y * chunk_size_pixels
            chunk_world_max_x = chunk_world_x + chunk_size_pixels
            chunk_world_max_y = chunk_world_y + chunk_size_pixels
            
            # Determine chunk category
            is_in_unload_range = (unload_min_x <= chunk_x < unload_max_x and
                                  unload_min_y <= chunk_y < unload_max_y)
            is_in_load_range = (load_min_x <= chunk_x < load_max_x and
                               load_min_y <= chunk_y < load_max_y)
            is_in_render_range = (render_min_x <= chunk_x < render_max_x and
                                   render_min_y <= chunk_y < render_max_y)
            
            # Red for unload range (outside unload range)
            if not is_in_unload_range:
                # Red with alpha 30 (30/255 ≈ 0.12)
                color = (255, 0, 0, 30)
            # Green for load/render range
            elif is_in_load_range or is_in_render_range:
                # Green with alpha 30
                color = (0, 255, 0, 30)
            else:
                # Skip chunks that are in unload range but not in load/render range
                continue
            
            # Create quad vertices (2 triangles = 6 vertices)
            # Format: [x, y, r, g, b, a]
            quads.extend([
                [chunk_world_x, chunk_world_y, color[0], color[1], color[2], color[3]],  # Bottom-left
                [chunk_world_max_x, chunk_world_y, color[0], color[1], color[2], color[3]],  # Bottom-right
                [chunk_world_max_x, chunk_world_max_y, color[0], color[1], color[2], color[3]],  # Top-right
                [chunk_world_x, chunk_world_y, color[0], color[1], color[2], color[3]],  # Bottom-left
                [chunk_world_max_x, chunk_world_max_y, color[0], color[1], color[2], color[3]],  # Top-right
                [chunk_world_x, chunk_world_max_y, color[0], color[1], color[2], color[3]],  # Top-left
            ])
        
        if quads:
            # Create a simple shader for alpha quads
            try:
                # Check if we need to create the shader
                if not hasattr(self, '_overlay_shader') or self._overlay_shader is None:
                    vertex_shader = """
                    #version 330 core
                    in vec2 in_position;
                    in vec4 in_color;
                    uniform vec2 screen_size;
                    uniform vec2 view_translation;
                    uniform float zoom;
                    out vec4 frag_color;
                    void main() {
                        vec2 screen_center = screen_size * 0.5;
                        vec2 screen_pos = (in_position - view_translation);
                        screen_pos = (screen_pos - screen_center) * zoom + screen_center;
                        vec2 ndc = (screen_pos / screen_size) * 2.0 - 1.0;
                        ndc.y = -ndc.y;  // Flip Y for OpenGL
                        gl_Position = vec4(ndc, 0.0, 1.0);
                        frag_color = in_color / 255.0;
                    }
                    """
                    fragment_shader = """
                    #version 330 core
                    in vec4 frag_color;
                    out vec4 out_color;
                    void main() {
                        out_color = frag_color;
                    }
                    """
                    self._overlay_shader = self.modern_gl_renderer.ctx.program(
                        vertex_shader=vertex_shader,
                        fragment_shader=fragment_shader
                    )
                
                # Create buffer and VAO
                quads_array = np.array(quads, dtype=np.float32)
                
                if self._debug_cache['chunk_overlay_vbo']:
                    self._debug_cache['chunk_overlay_vbo'].release()
                if self._debug_cache['chunk_overlay_vao']:
                    self._debug_cache['chunk_overlay_vao'].release()
                
                self._debug_cache['chunk_overlay_vbo'] = self.modern_gl_renderer.ctx.buffer(quads_array.tobytes())
                self._debug_cache['chunk_overlay_vao'] = self.modern_gl_renderer.ctx.vertex_array(
                    self._overlay_shader,
                    [(self._debug_cache['chunk_overlay_vbo'], "2f 4f", "in_position", "in_color")]
                )
                
                # Set uniforms
                screen_width = float(self.modern_gl_renderer.screen_width)
                screen_height = float(self.modern_gl_renderer.screen_height)
                self._overlay_shader['screen_size'].value = (screen_width, screen_height)
                self._overlay_shader['view_translation'].value = (float(camera_x), float(camera_y))
                self._overlay_shader['zoom'].value = float(self.world_controller.camera_zoom)
                
                # Enable blending for alpha
                self.modern_gl_renderer.ctx.enable(moderngl.BLEND)
                self.modern_gl_renderer.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
                
                # Render
                self._debug_cache['chunk_overlay_vao'].render(moderngl.TRIANGLES)
            except Exception as e:
                # Fallback: if shader creation fails, skip overlay rendering
                if hasattr(self, '_overlay_shader'):
                    self._overlay_shader = None
    
    def _draw_chunk_labels(self, chunks_data: list):
        """Draw chunk coordinates as text labels in chunks"""
        if not chunks_data or not self.world_controller.world or not self.world_controller.camera:
            return
        
        import pyglet.text
        from core.zoom_utils import calculate_visible_world_size
        
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        camera_x = self.world_controller.camera.x
        camera_y = self.world_controller.camera.y
        zoom = self.world_controller.camera_zoom
        
        screen_width = self.modern_gl_renderer.screen_width
        screen_height = self.modern_gl_renderer.screen_height
        
        # Calculate visible area
        visible_world_width, visible_world_height = calculate_visible_world_size(
            screen_width, screen_height, zoom
        )
        
        world_min_x = camera_x - visible_world_width / 2.0
        world_max_x = camera_x + visible_world_width / 2.0
        world_min_y = camera_y - visible_world_height / 2.0
        world_max_y = camera_y + visible_world_height / 2.0
        
        # Draw labels for visible chunks
        for chunk_x, chunk_y, _ in chunks_data:
            chunk_world_x = chunk_x * chunk_size_pixels
            chunk_world_y = chunk_y * chunk_size_pixels
            chunk_center_x = chunk_world_x + chunk_size_pixels / 2.0
            chunk_center_y = chunk_world_y + chunk_size_pixels / 2.0
            
            # Check if chunk center is in visible area
            if (world_min_x <= chunk_center_x <= world_max_x and
                world_min_y <= chunk_center_y <= world_max_y):
                
                # Convert world coordinates to screen coordinates
                screen_center_x = screen_width / 2.0
                screen_center_y = screen_height / 2.0
                
                # Apply view transformation and zoom
                screen_x = (chunk_center_x - camera_x) * zoom + screen_center_x
                screen_y = (chunk_center_y - camera_y) * zoom + screen_center_y
                
                # Only draw if on screen
                if 0 <= screen_x <= screen_width and 0 <= screen_y <= screen_height:
                    label_text = f"({chunk_x},{chunk_y})"
                    label = pyglet.text.Label(
                        label_text,
                        font_name='Courier New',
                        font_size=10,
                        x=int(screen_x),
                        y=int(screen_y),
                        anchor_x='center',
                        anchor_y='center',
                        color=(255, 255, 255, 255)
                    )
                    label.draw()

