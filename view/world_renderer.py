"""
View: WorldRenderer - Rendering von Welt, Chunks, Player und Tile-Highlight
"""
from typing import Optional, List, Tuple
import math
import pyglet.shapes
from pathlib import Path
from datetime import datetime
from core import settings
from core.world_controller import WorldController
from view.render_layer_manager import RenderLayerManager


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
        
        # Initialize render layer manager
        self.layer_manager = RenderLayerManager()
        
        # Sprite name cache (key: (decoration_id, tile_data_hash), value: sprite_name)
        self._sprite_name_cache = {}
        
        # Decoration object cache (key: decoration_id, value: Decoration instance)
        self._decoration_cache = {}
        
        # Rendering config cache (key: decoration_id, value: rendering_config)
        self._rendering_config_cache = {}
        
        # Decoration cache per chunk (key: (chunk_x, chunk_y), value: List[(tile_x, tile_y, decoration_data)])
        self._decoration_cache_per_chunk = {}
        self._decoration_cache_dirty = set()  # Set[(chunk_x, chunk_y)] - Chunks mit geänderten Decorations
        
        # Optional: Cache hit-rate statistics for debugging
        self._decoration_cache_stats = {'hits': 0, 'misses': 0}
        
        # Decoration VBO cache per chunk (key: (chunk_x, chunk_y), value: (vbo, vao, vertex_count))
        self._chunk_decoration_vbos = {}
        self._decoration_dirty_chunks = set()  # Chunks that need VBO rebuild
        
        # Reusable VBO/VAO for decorations (reused each frame to avoid allocation overhead)
        self._decoration_vbo = None
        self._decoration_vao = None
        self._decoration_vbo_size = 0  # Current size in bytes
        
        # Debug lookup counter for rendering texture lookups
        self._debug_lookup_count = 0
        
        # Debug logging file
        self._debug_log_file = None
        self._decoration_debug_log_file = None
        self._debug_log_enabled = True  # Set to False to disable debug logging
        self._init_debug_log()
        
        # Connect decoration debug logger to tile_texture_manager
        if hasattr(self.modern_gl_renderer, 'tile_texture_manager') and self.modern_gl_renderer.tile_texture_manager:
            self.modern_gl_renderer.tile_texture_manager.decoration_debug_logger = self._decoration_debug_log
    
    def _init_debug_log(self):
        """Initialize debug log file for decoration rendering debugging."""
        if not self._debug_log_enabled:
            return
        
        try:
            log_dir = Path("debug-logs")
            log_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Separate log file for decorations
            decoration_log_file = log_dir / f"decoration_debug_{timestamp}.log"
            self._decoration_debug_log_file = open(decoration_log_file, 'w', encoding='utf-8')
            
            # Keep existing general debug log
            log_file = log_dir / f"decoration_debug_{timestamp}.log"
            self._debug_log_file = open(log_file, 'w', encoding='utf-8')
            
            self._decoration_debug_log(f"=== Decoration Debug Log Started at {datetime.now().isoformat()} ===")
            self._decoration_debug_log(f"Log file: {decoration_log_file}")
            self._debug_log(f"=== Debug Log Started at {datetime.now().isoformat()} ===")
        except Exception as e:
            print(f"[WorldRenderer] Failed to initialize decoration debug log: {e}")
            self._decoration_debug_log_file = None
            self._debug_log_enabled = False
    
    def _debug_log(self, message: str):
        """Write debug message to log file."""
        if not self._debug_log_enabled or not self._debug_log_file:
            return
        
        try:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self._debug_log_file.write(f"[{timestamp}] {message}\n")
            self._debug_log_file.flush()  # Ensure immediate write
        except Exception:
            pass  # Silently fail if logging fails
    
    def _decoration_debug_log(self, message: str):
        """Write decoration debug message to log file."""
        if not self._debug_log_enabled or not hasattr(self, '_decoration_debug_log_file') or not self._decoration_debug_log_file:
            return
        
        try:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self._decoration_debug_log_file.write(f"[{timestamp}] {message}\n")
            self._decoration_debug_log_file.flush()  # Ensure immediate write
        except Exception:
            pass  # Silently fail if logging fails
    
    def close_debug_log(self):
        """Close debug log file (call on shutdown)."""
        if self._debug_log_file:
            try:
                self._debug_log_file.write(f"=== Debug Log Ended at {datetime.now().isoformat()} ===\n")
                self._debug_log_file.close()
                self._debug_log_file = None
            except Exception:
                pass
        
        # Close decoration debug log
        if hasattr(self, '_decoration_debug_log_file') and self._decoration_debug_log_file:
            try:
                self._decoration_debug_log_file.write(f"=== Decoration Debug Log Ended at {datetime.now().isoformat()} ===\n")
                self._decoration_debug_log_file.close()
                self._decoration_debug_log_file = None
            except Exception:
                pass
    
    def draw(self, debug_visualization_mode: int = 0):
        """Draw world using layer-based rendering system"""
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
        
        # Clear layer manager for this frame
        self.layer_manager.clear_all()
        
        # Step 3: Queue all renderables into layers
        if visible_chunks:
            # Layer 0: Terrain
            self._queue_terrain(visible_chunks)
            
            # Layer 5: Shadows
            self._queue_shadows(visible_chunks, camera_x, camera_y)
            
            # Layer 10: Decorations
            self._queue_decorations(visible_chunks, camera_x, camera_y)
            
            # Layer 20: Entities (Player)
            self._queue_entities(camera_x, camera_y)
            
            # Layer 25: Particles (future)
            # self._queue_particles(visible_chunks, camera_x, camera_y)
            
            # Layer 30: Effects (future)
            # self._queue_effects(visible_chunks, camera_x, camera_y)
            
            # Layer 40: Projectiles (future)
            # self._queue_projectiles(visible_chunks, camera_x, camera_y)
            
            # Layer 50: UI World (future)
            # self._queue_ui_world(visible_chunks, camera_x, camera_y)
        
        # Step 4: Render all layers in order
        self.layer_manager.render_all()
        
        # Step 5: Validate rendering (debug mode)
        if visible_chunks and hasattr(self, '_debug_log_enabled') and self._debug_log_enabled:
            self._validate_rendering(visible_chunks)
        
        # Store chunks_data for debug visualization
        self._last_chunks_data = visible_chunks if visible_chunks else []
    
    def _validate_rendering(self, visible_chunks):
        """Validate that all visible chunks and decorations are being rendered."""
        # Count chunks that should be rendered
        expected_chunks = len(visible_chunks)
        
        # Count decorations that should be rendered
        expected_decorations = 0
        for chunk_x, chunk_y, tiles in visible_chunks:
            if tiles:
                cached_decorations = self._get_cached_decorations(chunk_x, chunk_y, tiles)
                expected_decorations += len(cached_decorations)
        
        # Log validation (only if there are decorations to validate)
        if expected_decorations > 0:
            self._debug_log(f"[RENDERING VALIDATION] Expected: {expected_chunks} chunks, {expected_decorations} decorations")
            
            # Check if decoration cache is being used correctly
            cache_hits = self._decoration_cache_stats.get('hits', 0)
            cache_misses = self._decoration_cache_stats.get('misses', 0)
            total_cache_requests = cache_hits + cache_misses
            if total_cache_requests > 0:
                cache_hit_rate = cache_hits / total_cache_requests * 100
                self._debug_log(f"[RENDERING VALIDATION] Decoration cache: {cache_hits} hits, {cache_misses} misses ({cache_hit_rate:.1f}% hit rate)")
    
    def get_chunks_data(self):
        """Get the last rendered chunks data for debug visualization"""
        return getattr(self, '_last_chunks_data', [])
    
    def _queue_terrain(self, visible_chunks):
        """Queue terrain tiles for rendering (Layer 0)."""
        if not visible_chunks:
            return
        
        # Queue chunk rendering
        self.layer_manager.add_renderable(
            RenderLayerManager.LAYER_TERRAIN,
            self.modern_gl_renderer.render_chunks,
            z_index=0.0,
            chunks_data=visible_chunks,
            performance_monitor=self.world_controller.performance_monitor
        )
    
    def _queue_shadows(self, visible_chunks, camera_x: float, camera_y: float):
        """Queue decoration shadows for rendering (Layer 5)."""
        # Shadows are handled within _queue_decorations for now
        # This method is a placeholder for future shadow-only rendering
        pass
    
    def _queue_decorations(self, visible_chunks, camera_x: float, camera_y: float):
        """Queue decorations for rendering (Layer 10) with Y-sorting."""
        if not visible_chunks:
            return
        
        # Use existing _render_decorations_and_player method but queue it
        # We'll refactor this to queue individual decorations later
        self.layer_manager.add_renderable(
            RenderLayerManager.LAYER_DECORATIONS,
            self._render_decorations_and_player,
            z_index=0.0,
            visible_chunks=visible_chunks,
            camera_x=camera_x,
            camera_y=camera_y
        )
    
    def _queue_entities(self, camera_x: float, camera_y: float):
        """Queue entities (player, enemies) for rendering (Layer 20)."""
        if not self.world_controller.player:
            return
        
        # Player is rendered within _render_decorations_and_player for Y-sorting
        # This method is a placeholder for future entity-only rendering
        pass
    
    def _render_player(self):
        """Render player as yellow quad (1 tile wide, 2 tiles tall) - legacy method"""
        if not self.world_controller.player:
            return
        
        tile_size = settings.TILE_SIZE
        player_width = tile_size
        player_height = tile_size * 2
        
        player_world_x = self.world_controller.player.rect.center[0]
        player_world_y = self.world_controller.player.rect.center[1]
        
        world_x0 = player_world_x - player_width / 2.0
        world_y0 = player_world_y - player_height / 2.0
        
        yellow_color = (255, 255, 0)
        self._render_player_at_position(world_x0, world_y0, player_width, player_height, yellow_color)
    
    def _render_player_at_position(self, x: float, y: float, width: float, height: float, color: tuple):
        """Render player at specific position (used for depth-sorted rendering)"""
        import numpy as np
        import moderngl
        
        world_x0 = x
        world_y0 = y
        world_x1 = world_x0 + width
        world_y1 = world_y0 + height
        
        # Get color index for yellow (255, 255, 0) from palette
        color_index = float(self.modern_gl_renderer.tile_color_palette.get_color_index(color))
        
        # If color not in palette, add it
        if color_index == 0 and color not in self.modern_gl_renderer.tile_color_palette.color_to_index:
            color_index = float(self.modern_gl_renderer.tile_color_palette.add_color(color))
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
    
    def _get_cached_decorations(self, chunk_x: int, chunk_y: int, tiles: List[List[dict]]) -> List[Tuple[int, int, dict]]:
        """
        Get decorations from chunk (cached).
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
            tiles: 15x15 array of tile dictionaries
        
        Returns:
            List of (tile_x, tile_y, decoration_data) tuples
        """
        from typing import List, Tuple
        from world.metadata_utils import get_metadata
        
        chunk_key = (chunk_x, chunk_y)
        
        # Only rebuild cache if dirty or missing (not every frame)
        if chunk_key in self._decoration_cache_per_chunk and chunk_key not in self._decoration_cache_dirty:
            self._decoration_cache_stats['hits'] += 1
        else:
            self._decoration_cache_stats['misses'] += 1
            decorations = []
            maple_count = 0
            for tile_y, row in enumerate(tiles):
                if not row:
                    continue
                for tile_x, tile in enumerate(row):
                    if tile:
                        # Use new metadata format
                        decoration_data = get_metadata(tile, 'decoration')
                        if decoration_data:
                            decoration_id = decoration_data.get('decoration_id')
                            if decoration_id == 'maple_tree':
                                maple_count += 1
                                self._debug_log(f"[DEBUG MAPLE_TREE CACHE] Found maple_tree at tile ({tile_x}, {tile_y}) in chunk ({chunk_x}, {chunk_y})")
                            decorations.append((tile_x, tile_y, decoration_data))
            
            if maple_count > 0:
                self._debug_log(f"[DEBUG MAPLE_TREE CACHE] Chunk ({chunk_x}, {chunk_y}) has {maple_count} maple_tree(s)")
            
            self._decoration_cache_per_chunk[chunk_key] = decorations
            self._decoration_cache_dirty.discard(chunk_key)
        
        return self._decoration_cache_per_chunk[chunk_key]
    
    def invalidate_decoration_cache(self, chunk_x: int, chunk_y: int):
        """
        Mark chunk's decoration cache as dirty.
        
        This invalidates:
        - Decoration cache per chunk (_decoration_cache_per_chunk)
        - Decoration VBO cache (_chunk_decoration_vbos)
        - Sprite name cache (if needed)
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
        """
        chunk_key = (chunk_x, chunk_y)
        self._decoration_cache_dirty.add(chunk_key)
        # Also mark VBO cache as dirty (new decorations might have been added)
        self._decoration_dirty_chunks.add(chunk_key)
        
        # Remove from cache if exists (forces rebuild on next access)
        if chunk_key in self._decoration_cache_per_chunk:
            del self._decoration_cache_per_chunk[chunk_key]
        
        # Release VBO if exists (will be rebuilt on next render)
        if chunk_key in self._chunk_decoration_vbos:
            vbo, vao, vertex_count = self._chunk_decoration_vbos[chunk_key]
            vao.release()
            vbo.release()
            del self._chunk_decoration_vbos[chunk_key]
        
        self._debug_log(f"[CACHE] Invalidated decoration cache for chunk ({chunk_x}, {chunk_y})")
    
    def mark_decoration_chunk_dirty(self, chunk_x: int, chunk_y: int):
        """
        Mark chunk's decoration VBO as dirty (call when: mining, growth, season change).
        
        This invalidates:
        - Decoration VBO cache (_chunk_decoration_vbos)
        - Decoration cache per chunk (_decoration_cache_per_chunk)
        - Sprite name cache (for season changes)
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
        """
        chunk_key = (chunk_x, chunk_y)
        self._decoration_dirty_chunks.add(chunk_key)
        # Also invalidate decoration cache
        self._decoration_cache_dirty.add(chunk_key)
        
        # Remove from cache if exists (forces rebuild on next access)
        if chunk_key in self._decoration_cache_per_chunk:
            del self._decoration_cache_per_chunk[chunk_key]
        
        # Release VBO if exists (will be rebuilt on next render)
        if chunk_key in self._chunk_decoration_vbos:
            vbo, vao, vertex_count = self._chunk_decoration_vbos[chunk_key]
            vao.release()
            vbo.release()
            del self._chunk_decoration_vbos[chunk_key]
        
        self._debug_log(f"[CACHE] Marked decoration chunk ({chunk_x}, {chunk_y}) as dirty")
    
    def mark_chunks_dirty_in_range(self, min_chunk_x: int, max_chunk_x: int, min_chunk_y: int, max_chunk_y: int):
        """
        Mark all chunks in a range as dirty (forces full redraw).
        Useful after preloading to ensure all decorations are rendered correctly.
        
        Args:
            min_chunk_x: Minimum chunk X coordinate
            max_chunk_x: Maximum chunk X coordinate (inclusive)
            min_chunk_y: Minimum chunk Y coordinate
            max_chunk_y: Maximum chunk Y coordinate (inclusive)
        """
        for chunk_x in range(min_chunk_x, max_chunk_x + 1):
            for chunk_y in range(min_chunk_y, max_chunk_y + 1):
                self._decoration_dirty_chunks.add((chunk_x, chunk_y))
                self._decoration_cache_dirty.add((chunk_x, chunk_y))
    
    def mark_all_decoration_chunks_dirty(self):
        """
        Mark all decoration chunks as dirty (call when: season change, global updates).
        
        This invalidates:
        - All decoration VBO caches
        - All decoration caches per chunk
        - Sprite name cache (season change affects sprite selection)
        """
        # Mark all cached chunks as dirty
        for chunk_key in list(self._chunk_decoration_vbos.keys()):
            self._decoration_dirty_chunks.add(chunk_key)
            self._decoration_cache_dirty.add(chunk_key)
            
            # Release VBO
            vbo, vao, vertex_count = self._chunk_decoration_vbos[chunk_key]
            vao.release()
            vbo.release()
            del self._chunk_decoration_vbos[chunk_key]
        
        # Clear all caches
        self._decoration_cache_per_chunk.clear()
        self._sprite_name_cache.clear()
        
        self._debug_log(f"[CACHE] Marked all decoration chunks as dirty ({len(self._decoration_dirty_chunks)} chunks)")
    
    def invalidate_all_caches(self):
        """Debug: Invalidiere alle Decoration-Caches."""
        self._decoration_cache_per_chunk.clear()
        self._decoration_cache_dirty.clear()
        self._sprite_name_cache.clear()
        # Mark all VBO chunks as dirty
        for chunk_key in self._chunk_decoration_vbos.keys():
            self._decoration_dirty_chunks.add(chunk_key)
        print("[DEBUG] All decoration caches invalidated!")
    
    # Helper methods for sprite determination (moved from Decoration class)
    def _get_current_stage(self, deco_config: dict, tile_data: dict) -> int:
        """
        Get current growth stage from config and tile_data.
        
        Args:
            deco_config: Decoration configuration dictionary
            tile_data: Tile decoration data dictionary
            
        Returns:
            Current growth stage (1-4) or default_stage if not set
        """
        growth_config = deco_config.get('growth', {})
        if not growth_config.get('enabled', False):
            return growth_config.get('default_stage', 4)
        
        return tile_data.get('current_stage', growth_config.get('default_stage', 4))
    
    def _get_health_percentage(self, deco_config: dict, tile_data: dict) -> float:
        """
        Calculate health percentage from config and tile_data.
        
        Args:
            deco_config: Decoration configuration dictionary
            tile_data: Tile decoration data dictionary
            
        Returns:
            Health percentage (0.0-1.0)
        """
        # Check if explicit health is stored
        if 'health' in tile_data and 'max_health' in tile_data:
            max_health = tile_data.get('max_health', 100)
            if max_health > 0:
                return min(tile_data.get('health', max_health) / max_health, 1.0)
        
        # Calculate from mining progress
        mining_config = deco_config.get('mining', {})
        if not mining_config:
            return 1.0
        
        elapsed_time = tile_data.get('elapsed_time', 0.0)
        mining_time = mining_config.get('mining_time', 3.0)
        hardness_multiplier = mining_config.get('hardness_multiplier', 1.0)
        
        # Calculate time_to_mine (simplified, actual calculation uses tool speed)
        time_to_mine = mining_time * hardness_multiplier
        
        if time_to_mine <= 0:
            return 1.0
        
        health_percent = 1.0 - (elapsed_time / time_to_mine)
        return max(0.0, min(1.0, health_percent))
    
    def _is_harvestable(self, deco_config: dict) -> bool:
        """
        Check if decoration is harvestable.
        
        Args:
            deco_config: Decoration configuration dictionary
            
        Returns:
            True if harvestable, False otherwise
        """
        return 'harvest' in deco_config and deco_config['harvest'].get('enabled', False)
    
    def _get_fallback_sprite(self, deco_config: dict, health_percent: float, tile_data: dict = None) -> str:
        """
        Get fallback sprite using old system (for decorations without seasons).
        
        Args:
            deco_config: Decoration configuration dictionary
            health_percent: Health percentage (1.0 = full, 0.0 = destroyed)
            tile_data: Optional tile decoration data dictionary (for harvestable items)
            
        Returns:
            Sprite name
        """
        sprites = deco_config.get('sprites', {})
        
        # Check if this is a harvestable decoration (like berry bushes)
        if self._is_harvestable(deco_config) and tile_data is not None:
            has_fruit = tile_data.get('has_fruit', True)
            if has_fruit:
                sprite_name = sprites.get('with_fruit')
            else:
                sprite_name = sprites.get('without_fruit')
            
            # If sprite found, return it (unless damaged)
            if sprite_name and health_percent > 0.1:
                return sprite_name
            # If damaged, fall through to damage sprites
        
        # Standard damage-based sprite selection
        if health_percent > 0.5:
            return sprites.get('default', 'default')
        elif health_percent > 0.1:
            return sprites.get('damaged_50', sprites.get('default', 'default'))
        else:
            return sprites.get('stump', sprites.get('default', 'default'))
    
    def _determine_sprite_name(self, deco_config: dict, deco_data_dict: dict, season_manager=None) -> str:
        """
        Determine sprite name based on Season + Stage + Damage + Snow.
        (Moved from Decoration.get_current_sprite() for centralization)
        
        Args:
            deco_config: Decoration configuration dictionary
            deco_data_dict: Tile decoration data dictionary
            season_manager: Optional SeasonManager class (for get_current_season, is_snowing)
            
        Returns:
            Sprite name string
        """
        # Check if seasons are enabled
        seasons_config = deco_config.get('seasons', {})
        if not seasons_config.get('enabled', False) or season_manager is None:
            # Fallback to old system
            health_percent = self._get_health_percentage(deco_config, deco_data_dict)
            return self._get_fallback_sprite(deco_config, health_percent, deco_data_dict)
        
        # Get current season and stage
        current_season = season_manager.get_current_season()
        current_stage = self._get_current_stage(deco_config, deco_data_dict)
        health_percent = self._get_health_percentage(deco_config, deco_data_dict)
        is_snowy = season_manager.is_snowing() and current_season == "winter"
        
        # Get season config
        season_config = seasons_config.get(current_season, {})
        
        # Check if harvestable and has fruit state
        has_fruit = True  # Default to having fruit
        if self._is_harvestable(deco_config) and deco_data_dict is not None:
            has_fruit = deco_data_dict.get('has_fruit', True)
        
        # Choose growth stages based on fruit state, snowy state, and season
        growth_stages = None
        
        if is_snowy:
            # Snowy variants
            if has_fruit and 'growth_stages_snowy_with_fruit' in season_config:
                growth_stages = season_config.get('growth_stages_snowy_with_fruit', {})
            elif not has_fruit and 'growth_stages_snowy_without_fruit' in season_config:
                growth_stages = season_config.get('growth_stages_snowy_without_fruit', {})
            elif 'growth_stages_snowy' in season_config:
                growth_stages = season_config.get('growth_stages_snowy', {})
        else:
            # Normal variants
            if has_fruit and 'growth_stages_with_fruit' in season_config:
                growth_stages = season_config.get('growth_stages_with_fruit', {})
            elif not has_fruit and 'growth_stages_without_fruit' in season_config:
                growth_stages = season_config.get('growth_stages_without_fruit', {})
        
        # Fallback to standard growth_stages if fruit variants not found
        if not growth_stages:
            if is_snowy and 'growth_stages_snowy' in season_config:
                growth_stages = season_config.get('growth_stages_snowy', {})
            else:
                growth_stages = season_config.get('growth_stages', {})
        
        # Get sprite for current stage
        sprite_name = None
        if growth_stages:
            # Try both string and int keys
            stage_key = str(current_stage)
            sprite_name = growth_stages.get(stage_key)
            if not sprite_name:
                # Fallback: try int key
                sprite_name = growth_stages.get(current_stage)
        
        # DEBUG: Log für Maple/Apple-Trees
        decoration_id = deco_config.get('id', 'unknown')
        if decoration_id in ['maple_tree', 'apple_tree']:
            self._debug_log(f"[DEBUG {decoration_id.upper()}] Season: {current_season}, Stage: {current_stage}, Snowy: {is_snowy}, HasFruit: {has_fruit}")
            self._debug_log(f"[DEBUG {decoration_id.upper()}] Growth stages keys: {list(growth_stages.keys()) if growth_stages else 'None'}")
            self._debug_log(f"[DEBUG {decoration_id.upper()}] Looking for stage '{str(current_stage)}' in growth_stages")
            self._debug_log(f"[DEBUG {decoration_id.upper()}] Found sprite_name: {sprite_name}")
        
        # Override with damage sprite if damaged
        if health_percent < 0.5:
            if health_percent < 0.1:
                # Stump
                if is_snowy and 'stump_snowy' in season_config:
                    sprite_name = season_config.get('stump_snowy', sprite_name)
                else:
                    sprite_name = season_config.get('stump', sprite_name)
            else:
                # Damaged (50%)
                if is_snowy and 'damaged_sprites_snowy' in season_config:
                    damaged_sprites = season_config.get('damaged_sprites_snowy', {})
                    sprite_name = damaged_sprites.get('damaged_50', sprite_name)
                else:
                    damaged_sprites = season_config.get('damaged_sprites', {})
                    sprite_name = damaged_sprites.get('damaged_50', sprite_name)
            
            # DEBUG: Log after damage override
            if decoration_id in ['maple_tree', 'apple_tree']:
                self._debug_log(f"[DEBUG {decoration_id.upper()}] After damage override: sprite_name = {sprite_name}")
        
        # Fallback to default sprite if not found
        if not sprite_name:
            # Versuche alle möglichen Fallback-Sprites
            sprites = deco_config.get('sprites', {})
            sprite_name = sprites.get('default') or sprites.get('with_fruit') or sprites.get('without_fruit')
            
            # DEBUG: Log fallback attempt
            if decoration_id in ['maple_tree', 'apple_tree']:
                self._debug_log(f"[DEBUG {decoration_id.upper()}] Fallback attempt: sprite_name = {sprite_name}")
                self._debug_log(f"[DEBUG {decoration_id.upper()}] Available fallback sprites: {list(sprites.keys())}")
            
            # Wenn immer noch kein Sprite, return None (wird zu Farb-Rendering führen)
            if not sprite_name:
                # Log warning
                if hasattr(self, 'world_controller') and self.world_controller and hasattr(self.world_controller, 'diagnostics') and self.world_controller.diagnostics:
                    self.world_controller.diagnostics.warning("WorldRenderer",
                        f"No sprite found for decoration {decoration_id}, will use color fallback")
                # DEBUG: Log final None
                if decoration_id in ['maple_tree', 'apple_tree']:
                    self._debug_log(f"[DEBUG {decoration_id.upper()}] FINAL: sprite_name is None, will use color fallback")
                return None  # None = use color rendering
        
        # DEBUG: Log final sprite_name
        if decoration_id in ['maple_tree', 'apple_tree']:
            self._debug_log(f"[DEBUG {decoration_id.upper()}] FINAL: Returning sprite_name = {sprite_name}")
        
        return sprite_name
    
    def _render_decorations_and_player(self, visible_chunks, camera_x: float, camera_y: float):
        """
        Render decorations and player, sorted by Y-position for proper depth ordering.
        Objects with higher Y (further down on screen) are rendered first.
        
        Args:
            visible_chunks: List of (chunk_x, chunk_y, tiles) tuples
            camera_x: Camera X position
            camera_y: Camera Y position
        """
        import time
        
        try:
            from world.decoration_registry import DecorationRegistry
            from world.decoration import Decoration
        except ImportError:
            # If decoration system not available, just render player
            if self.world_controller.player:
                self._render_player()
            return
        
        import numpy as np
        import moderngl
        from core.zoom_utils import calculate_visible_world_size
        
        # Performance tracking
        performance_monitor = getattr(self.world_controller, 'performance_monitor', None)
        collect_start = time.perf_counter()
        
        tile_size = settings.TILE_SIZE
        # List of (y_position, is_player, layer, x, y, width, height, color, decoration_data, sprite_name, mod_id)
        renderable_objects = []
        
        # Calculate viewport bounds for frustum culling
        screen_width = self.modern_gl_renderer.screen_width
        screen_height = self.modern_gl_renderer.screen_height
        zoom = self.world_controller.camera_zoom
        visible_world_width, visible_world_height = calculate_visible_world_size(screen_width, screen_height, zoom)
        
        # Viewport bounds in world coordinates (with dynamic margin for large decorations)
        # Use larger margin to ensure large decorations (like trees) are not culled incorrectly
        # Maximum decoration size is typically 64-128px, so we use 128px + tile_size as margin
        max_decoration_size = 128  # Maximum expected decoration size in pixels
        margin = max(tile_size * 2, max_decoration_size + tile_size)  # At least 2 tiles, but more for large decorations
        viewport_min_x = camera_x - visible_world_width / 2.0 - margin
        viewport_max_x = camera_x + visible_world_width / 2.0 + margin
        viewport_min_y = camera_y - visible_world_height / 2.0 - margin
        viewport_max_y = camera_y + visible_world_height / 2.0 + margin
        
        # Collect all decorations from visible chunks
        # Cache decoration configs per chunk to reduce lookups
        decoration_config_cache = {}
        
        # Track sprite determination time
        sprite_time_total = 0.0
        sprite_count = 0
        
        # Pre-import Season/Growth managers (avoid repeated imports in loop)
        try:
            from world.season_manager import SeasonManager
            from world.growth_manager import GrowthManager
            season_growth_available = True
        except (ImportError, AttributeError):
            SeasonManager = None
            GrowthManager = None
            season_growth_available = False
        
        # Cache frequently used values
        tile_size_half = tile_size / 2.0
        
        for chunk_x, chunk_y, tiles in visible_chunks:
            if not tiles:
                continue
            
            chunk_world_x = chunk_x * settings.CHUNK_SIZE * tile_size
            chunk_world_y = chunk_y * settings.CHUNK_SIZE * tile_size
            
            # OPTIMIZATION: Use cached decorations instead of iterating all tiles
            # This avoids iterating over tiles without decorations
            cached_decorations = self._get_cached_decorations(chunk_x, chunk_y, tiles)
            
            for tile_x, tile_y, decoration_data in cached_decorations:
                decoration_id = decoration_data.get('decoration_id')
                if not decoration_id:
                    continue
                
                # DEBUG: Log decoration found with full path
                tile_world_x = chunk_world_x + tile_x * tile_size
                tile_world_y = chunk_world_y + tile_y * tile_size
                decoration_path = f"chunk({chunk_x},{chunk_y})/tile({tile_x},{tile_y})/world({tile_world_x:.0f},{tile_world_y:.0f})"
                
                self._decoration_debug_log(f"[FOUND] decoration_id={decoration_id}, path={decoration_path}")
                
                # Get decoration config (cached per decoration_id)
                if decoration_id not in decoration_config_cache:
                    deco_config = DecorationRegistry.get(decoration_id)
                    if not deco_config:
                        decoration_config_cache[decoration_id] = None
                        self._decoration_debug_log(f"[ERROR] No config found for decoration_id={decoration_id}, path={decoration_path}")
                        continue
                    decoration_config_cache[decoration_id] = deco_config
                else:
                    deco_config = decoration_config_cache[decoration_id]
                    if not deco_config:
                        self._decoration_debug_log(f"[ERROR] Cached config is None for decoration_id={decoration_id}, path={decoration_path}")
                        continue
                
                mod_id = deco_config.get('mod_id', 'core')
                self._decoration_debug_log(f"[CONFIG] decoration_id={decoration_id}, mod_id={mod_id}, path={decoration_path}")
                
                # Cache Decoration objects and rendering configs (don't recreate each frame)
                if decoration_id not in self._decoration_cache:
                    decoration = Decoration(deco_config)
                    self._decoration_cache[decoration_id] = decoration
                    self._rendering_config_cache[decoration_id] = decoration.get_rendering_config()
                else:
                    decoration = self._decoration_cache[decoration_id]
                
                rendering_config = self._rendering_config_cache[decoration_id]
                
                # Calculate tile world position (optimized: avoid repeated multiplication)
                tile_world_x = chunk_world_x + tile_x * tile_size
                tile_world_y = chunk_world_y + tile_y * tile_size
                
                # Get rendering size and offset (cache these lookups)
                size = rendering_config.get('size', [tile_size, tile_size])
                offset = rendering_config.get('offset', [0, 0])
                layer = rendering_config.get('layer', 10)
                
                # Calculate decoration position (centered on tile + offset)
                # OPTIMIZATION: Early frustum culling before expensive sprite name determination
                deco_x = tile_world_x + tile_size_half + offset[0] - size[0] * 0.5
                deco_y = tile_world_y + tile_size_half + offset[1] - size[1] * 0.5
                
                # Early frustum culling: Skip decorations outside viewport BEFORE sprite determination
                deco_max_x = deco_x + size[0]
                deco_max_y = deco_y + size[1]
                if (deco_max_x < viewport_min_x or deco_x > viewport_max_x or
                    deco_max_y < viewport_min_y or deco_y > viewport_max_y):
                    continue
                
                # Get sprite name and mod_id
                mod_id = deco_config.get('mod_id', 'core')
                deco_data_dict = decoration_data.get('data', {})
                
                # Get current season (for logging)
                current_season = "unknown"
                if season_growth_available and SeasonManager:
                    try:
                        current_season = SeasonManager.get_current_season()
                    except:
                        pass
                
                # Calculate hash of tile_data for caching (optimized: use tuple hash instead of MD5)
                tile_data_key = (
                    decoration_id,
                    deco_data_dict.get('has_fruit', True),
                    deco_data_dict.get('current_stage', None),
                    deco_data_dict.get('sprite_state', None),
                    deco_data_dict.get('health', None),
                    deco_data_dict.get('max_health', None),
                )
                # Use built-in hash() instead of MD5 (much faster, sufficient for caching)
                tile_data_hash = hash(tile_data_key)
                cache_key = (decoration_id, tile_data_hash)
                
                # Check cache first
                sprite_start = time.perf_counter()
                if cache_key in self._sprite_name_cache:
                    sprite_name = self._sprite_name_cache[cache_key]
                else:
                    # Determine current sprite based on state (with Season/Growth support)
                    sprite_name = None
                    
                    # Use Season/Growth system if available (pre-imported)
                    if season_growth_available and SeasonManager:
                        try:
                            # Use centralized _determine_sprite_name() method
                            sprite_name = self._determine_sprite_name(deco_config, deco_data_dict, SeasonManager)
                        except (AttributeError, TypeError, Exception) as e:
                            # Fallback if method fails
                            sprite_name = None
                    
                    # DEBUG: Log für Maple/Apple-Trees wenn sprite_name None ist
                    if sprite_name is None:
                        if decoration_id in ['maple_tree', 'apple_tree']:
                            self._debug_log(f"[DEBUG {decoration_id.upper()} RENDER] sprite_name is None! deco_data: {deco_data_dict}")
                        # Kein Sprite verfügbar - rendere mit Farbe
                        renderable_objects.append((deco_y + size[1], False, layer, deco_x, deco_y, size[0], size[1], color, decoration_data, None, None))
                        continue
                    
                    # Fallback to old system if SeasonManager not available or failed
                    if not sprite_name:
                        # Check for sprite_state (set during mining or stump phase)
                        sprite_state = deco_data_dict.get('sprite_state')
                        if sprite_state:
                            # Use sprite_state if available (default, damaged_50, stump)
                            sprite_name = deco_config['sprites'].get(sprite_state)
                        
                        # Fallback to harvestable state or default
                        if not sprite_name:
                            if self._is_harvestable(deco_config):
                                has_fruit = deco_data_dict.get('has_fruit', True)
                                sprite_name = deco_config['sprites'].get('with_fruit' if has_fruit else 'without_fruit')
                            else:
                                sprite_name = deco_config['sprites'].get('default')
                    
                    # Fallback to default if texture not available
                    if not sprite_name:
                        sprite_name = 'default'
                    
                    # Cache sprite name (limit cache size)
                    if len(self._sprite_name_cache) > 200:
                        # Remove oldest 50 entries (simple FIFO)
                        keys_to_remove = list(self._sprite_name_cache.keys())[:50]
                        for key in keys_to_remove:
                            del self._sprite_name_cache[key]
                    
                    self._sprite_name_cache[cache_key] = sprite_name
                
                # DEBUG: Log sprite determination (after cache check, so we log the final sprite_name)
                self._decoration_debug_log(
                    f"[SPRITE] decoration_id={decoration_id}, "
                    f"sprite_name={sprite_name}, "
                    f"season={current_season}, "
                    f"stage={deco_data_dict.get('current_stage', 'N/A')}, "
                    f"has_fruit={deco_data_dict.get('has_fruit', True)}, "
                    f"path={decoration_path}"
                )
                
                sprite_time_total += time.perf_counter() - sprite_start
                sprite_count += 1
                
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
                    # Use bottom Y position for sorting (shadow_y + shadow_size[1])
                    renderable_objects.append((shadow_y + shadow_size[1], False, 5, shadow_x, shadow_y, shadow_size[0], shadow_size[1], (0, 0, 0), None, shadow_sprite_name, mod_id))
                
                # Add decoration (Layer 10 or from config) with sprite info
                # Use bottom Y position for sorting (deco_y + size[1])
                renderable_objects.append((deco_y + size[1], False, layer, deco_x, deco_y, size[0], size[1], color, decoration_data, sprite_name, mod_id))
        
        # Add player to renderable objects
        if self.world_controller.player:
            player_world_x = self.world_controller.player.rect.center[0]
            player_world_y = self.world_controller.player.rect.center[1]
            player_width = tile_size
            player_height = tile_size * 2
            player_x = player_world_x - player_width / 2.0
            player_y = player_world_y - player_height / 2.0
            # Use bottom Y position for sorting (player_y + player_height)
            # Player uses layer 20, but sorting by Y takes precedence
            yellow_color = (255, 255, 0)
            renderable_objects.append((player_y + player_height, True, 20, player_x, player_y, player_width, player_height, yellow_color, None, None, None))
        
        # Record collection time
        collect_time = time.perf_counter() - collect_start
        if performance_monitor:
            performance_monitor.record_decoration_collect_time(collect_time)
            if sprite_count > 0:
                performance_monitor.record_decoration_sprite_time(sprite_time_total)
        
        # Sort by Y-position (bottom Y coordinate) - higher Y = rendered first (behind)
        # Then by layer as secondary sort key
        renderable_objects.sort(key=lambda x: (x[0], x[2]))
        
        # Render objects in sorted order (depth-sorted rendering)
        # Separate into batches: decorations (textured) and player (colored)
        # We need to render them in order, so we'll collect decorations and render player when needed
        decoration_batch = []
        
        for y_pos, is_player, layer, x, y, width, height, color, deco_data, sprite_name, mod_id in renderable_objects:
            if is_player:
                # Render accumulated decorations before player
                if decoration_batch:
                    if self.modern_gl_renderer.tile_texture_manager and self.modern_gl_renderer.tile_texture_manager.texture_atlas:
                        self._render_decorations_with_textures(decoration_batch, camera_x, camera_y)
                    else:
                        self._render_decorations_with_colors(decoration_batch)
                    decoration_batch = []
                
                # Render player at this depth position
                self._render_player_at_position(x, y, width, height, color)
            else:
                # Add decoration to batch
                decoration_batch.append((layer, x, y, width, height, color, deco_data, sprite_name, mod_id))
        
        # Render remaining decorations after player
        if decoration_batch:
            if self.modern_gl_renderer.tile_texture_manager and self.modern_gl_renderer.tile_texture_manager.texture_atlas:
                self._render_decorations_with_textures(decoration_batch, camera_x, camera_y)
            else:
                self._render_decorations_with_colors(decoration_batch)
    
    def _render_decorations_with_textures(self, decoration_sprites, camera_x: float, camera_y: float):
        """Render decorations using texture atlas (batched rendering for performance with VBO caching per chunk)."""
        import time
        import numpy as np
        import moderngl
        from core import settings
        
        if not decoration_sprites:
            return
        
        # Color batch for decorations without textures (fallback rendering)
        color_batch = []  # Decorations ohne Textur (mit Farbe rendern)
        
        # Performance tracking
        performance_monitor = getattr(self.world_controller, 'performance_monitor', None)
        
        # Use texture atlas from tile_texture_manager (includes decoration textures)
        tile_texture_manager = self.modern_gl_renderer.tile_texture_manager
        if not tile_texture_manager or not tile_texture_manager.texture_atlas:
            # Fallback to old method if atlas not available
            self._render_decorations_with_textures_legacy(decoration_sprites, camera_x, camera_y)
            return
        
        # Enable blending
        self.modern_gl_renderer.ctx.enable(moderngl.BLEND)
        self.modern_gl_renderer.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        
        # Group decorations by chunk
        decorations_by_chunk = {}  # (chunk_x, chunk_y) -> list of sprite_data
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        
        for sprite_data in decoration_sprites:
            # Extract chunk coordinates from decoration position
            if len(sprite_data) >= 9:
                layer, x, y, width, height, color, deco_data, sprite_name, mod_id = sprite_data[:9]
            else:
                # Fallback for old format
                layer, x, y, width, height, color, deco_data = sprite_data[:7]
                sprite_name = None
                mod_id = 'core'
            
            # Skip decorations without sprite_name (they won't render anyway)
            if not sprite_name:
                continue
            
            # Calculate chunk coordinates from world position
            chunk_x = int(x // chunk_size_pixels)
            chunk_y = int(y // chunk_size_pixels)
            chunk_key = (chunk_x, chunk_y)
            
            if chunk_key not in decorations_by_chunk:
                decorations_by_chunk[chunk_key] = []
            decorations_by_chunk[chunk_key].append(sprite_data)
        
        # Render each chunk's decorations (with VBO caching)
        all_progress_bars = []
        total_vertex_time = 0.0
        total_vbo_time = 0.0
        total_render_time = 0.0
        total_decoration_count = 0
        
        for chunk_key, chunk_decorations in decorations_by_chunk.items():
            chunk_x, chunk_y = chunk_key
            
            # Skip empty chunks
            if not chunk_decorations:
                continue
            
            # Check if VBO exists and is not dirty
            if chunk_key in self._chunk_decoration_vbos and chunk_key not in self._decoration_dirty_chunks:
                # CACHED! Render immediately (no vertex creation)
                vbo, vao, vertex_count = self._chunk_decoration_vbos[chunk_key]
                
                # Only render if we have vertices (safety check)
                if vertex_count > 0:
                    # Bind texture atlas
                    tile_texture_manager.texture_atlas.use(0)
                    if 'tile_texture' in self.modern_gl_renderer.chunk_program:
                        self.modern_gl_renderer.chunk_program['tile_texture'].value = 0
                    
                    # Render cached VBO
                    render_start = time.perf_counter()
                    vao.render(moderngl.TRIANGLES, vertices=vertex_count)
                    total_render_time += time.perf_counter() - render_start
                    total_decoration_count += len(chunk_decorations)
                else:
                    # Empty VBO in cache - remove it and rebuild
                    vbo.release()
                    vao.release()
                    del self._chunk_decoration_vbos[chunk_key]
                    self._decoration_dirty_chunks.add(chunk_key)
            else:
                # Rebuild VBO (only for dirty chunks or new chunks)
                # This includes chunks that are visible for the first time (e.g., after zooming out)
                vertices, progress_bars, vertex_time, chunk_color_batch = self._create_decoration_vertices(chunk_decorations, camera_x, camera_y)
                # Add chunk's color batch to main color_batch
                if chunk_color_batch:
                    color_batch.extend(chunk_color_batch)
                all_progress_bars.extend(progress_bars)
                total_vertex_time += vertex_time
                
                if vertices:
                    vbo, vao, vertex_count, vbo_time = self._upload_decoration_vbo(vertices)
                    total_vbo_time += vbo_time
                    
                    # Only cache VBO if we have vertices (safety check)
                    if vertex_count > 0:
                        self._chunk_decoration_vbos[chunk_key] = (vbo, vao, vertex_count)
                        self._decoration_dirty_chunks.discard(chunk_key)
                        # Also ensure decoration cache is not dirty for this chunk
                        self._decoration_cache_dirty.discard(chunk_key)
                        
                        # Bind texture atlas
                        tile_texture_manager.texture_atlas.use(0)
                        if 'tile_texture' in self.modern_gl_renderer.chunk_program:
                            self.modern_gl_renderer.chunk_program['tile_texture'].value = 0
                        
                        # Render
                        render_start = time.perf_counter()
                        vao.render(moderngl.TRIANGLES, vertices=vertex_count)
                        total_render_time += time.perf_counter() - render_start
                        total_decoration_count += len(chunk_decorations)
                    else:
                        # Empty vertices - release VBO and don't cache
                        vbo.release()
                        vao.release()
                elif chunk_decorations:
                    # If we have decorations but no vertices, it means textures are missing
                    # Log this for debugging
                    if hasattr(self.world_controller, 'diagnostics') and self.world_controller.diagnostics:
                        missing_textures = []
                        for sprite_data in chunk_decorations:
                            if len(sprite_data) >= 9:
                                _, _, _, _, _, _, _, sprite_name, mod_id = sprite_data[:9]
                                if sprite_name:
                                    missing_textures.append(f"{mod_id}/{sprite_name}")
                        if missing_textures:
                            self.world_controller.diagnostics.warning("WorldRenderer", 
                                f"Chunk ({chunk_x}, {chunk_y}) has {len(chunk_decorations)} decorations but no vertices created. Missing textures: {set(missing_textures[:5])}")
                    vao.render(moderngl.TRIANGLES, vertices=vertex_count)
                    total_render_time += time.perf_counter() - render_start
                    total_decoration_count += len(chunk_decorations)
        
        # Render color fallback decorations (those without textures)
        if color_batch:
            self._render_decorations_with_colors(color_batch)
        
        # Record performance metrics
        if performance_monitor:
            performance_monitor.record_decoration_vertex_time(total_vertex_time)
            performance_monitor.record_decoration_vbo_time(total_vbo_time)
            performance_monitor.record_decoration_render_time(total_render_time)
            performance_monitor.record_decoration_count(total_decoration_count)
        
        # Render progress bars after ModernGL rendering (using pyglet.shapes)
        if all_progress_bars:
            for bar_type, x, y, width, height, progress in all_progress_bars:
                if bar_type == 'regrowth':
                    self._render_regrowth_progress_bar(x, y, width, height, progress, camera_x, camera_y)
                elif bar_type == 'mining':
                    self._render_mining_progress_bar(x, y, width, height, progress, camera_x, camera_y)
    
    def _create_decoration_vertices(self, decoration_sprites, camera_x: float, camera_y: float):
        """Create vertex data for decorations (extracted from _render_decorations_with_textures)."""
        import time
        from core import settings
        
        vertex_start = time.perf_counter()
        all_vertices = []
        progress_bars = []
        
        # Create a new list for color batch entries from this chunk (don't modify the passed list)
        new_color_batch = []
        
        # Use texture atlas from tile_texture_manager
        tile_texture_manager = self.modern_gl_renderer.tile_texture_manager
        if not tile_texture_manager:
            return [], [], 0.0, new_color_batch
        
        # Cache texture coordinates to reduce lookups
        texture_coords_cache = {}
        
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
            
            # Get UV coordinates from atlas (cached)
            atlas_name = f"decoration:{mod_id}/{sprite_name}"
            cache_key = (sprite_name, mod_id)
            
            # DEBUG: Log texture lookup
            if sprite_name:
                self._decoration_debug_log(
                    f"[TEXTURE_LOOKUP] sprite_name={sprite_name}, "
                    f"mod_id={mod_id}, "
                    f"atlas_name={atlas_name}"
                )
            
            if cache_key not in texture_coords_cache:
                uv_coords = tile_texture_manager.get_decoration_texture_coords(sprite_name, mod_id)
                
                # Debug: Log first 5 lookups
                if self._debug_lookup_count < 5:
                    self._debug_lookup_count += 1
                    
                    if uv_coords:
                        self._decoration_debug_log(f"RENDERING ✓ Found UV for: decoration/{mod_id}/{sprite_name}")
                        self._decoration_debug_log(f"           UV: {uv_coords}")
                    else:
                        self._decoration_debug_log(f"RENDERING ✗ Missing UV for: decoration/{mod_id}/{sprite_name}")
                        self._decoration_debug_log(f"           Atlas name tried: decoration:{mod_id}/{sprite_name}")
                        
                        # Show available keys
                        available = [k for k in tile_texture_manager.texture_coords.keys() if 'decoration' in k]
                        self._decoration_debug_log(f"           Available decoration keys (first 5): {available[:5]}")
                
                if not uv_coords:
                    # Fallback: try direct lookup
                    if atlas_name in tile_texture_manager.texture_coords:
                        uv_coords = tile_texture_manager.texture_coords[atlas_name]
                        self._decoration_debug_log(f"[TEXTURE_FOUND] Direct lookup: {atlas_name}")
                    else:
                        # Textur fehlt - Log detailliert
                        self._decoration_debug_log(
                            f"[TEXTURE_MISSING] atlas_name={atlas_name}, "
                            f"sprite_name={sprite_name}, "
                            f"mod_id={mod_id}"
                        )
                        
                        # Log available decoration textures (first 20)
                        available_decorations = [
                            k for k in tile_texture_manager.texture_coords.keys() 
                            if k.startswith('decoration:')
                        ]
                        self._decoration_debug_log(
                            f"[TEXTURE_MISSING] Available decoration textures ({len(available_decorations)}): "
                            f"{available_decorations[:20]}"
                        )
                        
                        # Textur fehlt - Use fallback texture (pink 16x16) instead of color rendering
                        fallback_uv = tile_texture_manager.get_decoration_texture_coords("fallback", "fallback")
                        if fallback_uv:
                            uv_coords = fallback_uv
                            self._decoration_debug_log(f"[TEXTURE_FALLBACK] Using fallback texture for {atlas_name}")
                            texture_coords_cache[cache_key] = uv_coords
                        else:
                            # Fallback texture not available - use color rendering
                            texture_coords_cache[cache_key] = None
                            if not sprite_name.startswith('shadow'):
                                if hasattr(self.world_controller, 'diagnostics') and self.world_controller.diagnostics:
                                    self.world_controller.diagnostics.warning("WorldRenderer", 
                                        f"Missing decoration texture: {atlas_name} (sprite: {sprite_name}, mod: {mod_id}), using color fallback")
                            # RENDERE MIT FARBE STATT ZU ÜBERSPRINGEN
                            if len(sprite_data) >= 7:
                                layer, x, y, width, height, color, deco_data = sprite_data[:7]
                                new_color_batch.append((layer, x, y, width, height, color))
                            continue
                texture_coords_cache[cache_key] = uv_coords
            else:
                uv_coords = texture_coords_cache[cache_key]
                if not uv_coords:
                    # Textur fehlt im Cache - Fallback auf Farb-Rendering
                    if len(sprite_data) >= 7:
                        layer, x, y, width, height, color, deco_data = sprite_data[:7]
                        new_color_batch.append((layer, x, y, width, height, color))
                    continue
            
            u0, v0, u1, v1 = uv_coords
            
            # DEBUG: Log successful texture usage
            self._decoration_debug_log(
                f"[TEXTURE_USED] atlas_name={atlas_name}, "
                f"UV=({u0:.4f},{v0:.4f},{u1:.4f},{v1:.4f}), "
                f"position=({x:.0f},{y:.0f}), "
                f"size=({width:.0f},{height:.0f})"
            )
            
            # Get regrowth progress for progress bar (only if needed - optimization)
            regrowth_progress = None
            mining_progress = None
            if deco_data:
                deco_data_dict = deco_data.get('data', {})
                
                # Only calculate regrowth progress if decoration is harvested (optimization)
                has_fruit = deco_data_dict.get('has_fruit', True)
                if not has_fruit:
                    growth_timer = deco_data_dict.get('growth_timer', 0.0)
                    initial_growth_time = deco_data_dict.get('initial_growth_time', 0.0)
                    
                    # Only calculate if regrowth is in progress (optimization)
                    if initial_growth_time > 0 and growth_timer >= 0 and growth_timer < initial_growth_time:
                        elapsed = initial_growth_time - growth_timer
                        regrowth_progress = max(0.0, min(1.0, elapsed / initial_growth_time))
                
                # Only calculate mining progress if actively being mined (optimization)
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
            # Regrowth progress bar only shows on hover (to reduce rendering load)
            is_hovered = False
            if regrowth_progress is not None and regrowth_progress < 1.0:
                # Check if mouse is hovering over this decoration
                mouse_x = self.world_controller.mouse_x
                mouse_y = self.world_controller.mouse_y
                screen_width = self.modern_gl_renderer.screen_width
                screen_height = self.modern_gl_renderer.screen_height
                zoom = self.world_controller.camera_zoom
                
                # Convert decoration world position to screen coordinates
                screen_deco_x = (x - camera_x) * zoom + screen_width / 2.0
                screen_deco_y = (y - camera_y) * zoom + screen_height / 2.0
                screen_deco_y = screen_height - screen_deco_y  # Flip Y for pyglet
                
                # Scale decoration size by zoom
                screen_deco_width = width * zoom
                screen_deco_height = height * zoom
                
                # Check if mouse is within decoration bounds
                is_hovered = (screen_deco_x <= mouse_x <= screen_deco_x + screen_deco_width and
                            screen_deco_y - screen_deco_height <= mouse_y <= screen_deco_y)
                
                # Only add regrowth progress bar if hovered
                if is_hovered:
                    progress_bars.append(('regrowth', x, y, width, height, regrowth_progress))
            
            # Mining progress bar always shows (active mining is visible)
            if mining_progress is not None and mining_progress < 1.0:
                progress_bars.append(('mining', x, y, width, height, mining_progress))
        
        vertex_time = time.perf_counter() - vertex_start
        
        return all_vertices, progress_bars, vertex_time, new_color_batch
    
    def _upload_decoration_vbo(self, vertices):
        """Upload vertices to GPU and create VBO/VAO."""
        import time
        import numpy as np
        import moderngl
        import math
        
        vbo_start = time.perf_counter()
        
        vertices_array = np.array(vertices, dtype=np.float32)
        vertices_bytes = vertices_array.tobytes()
        vertices_size = len(vertices_bytes)
        
        # Create new VBO with enough space (round up to next power of 2 for efficiency)
        target_size = max(vertices_size, 1024)  # Minimum 1KB
        target_size = 2 ** math.ceil(math.log2(target_size))  # Round up to power of 2
        
        vbo = self.modern_gl_renderer.ctx.buffer(vertices_bytes)
        vao = self.modern_gl_renderer.ctx.vertex_array(
            self.modern_gl_renderer.chunk_program,
            [(vbo, "2f 1f 2f 1f", "in_position", "in_color_index", "in_texcoord", "in_use_texture")]
        )
        
        vbo_time = time.perf_counter() - vbo_start
        
        return vbo, vao, len(vertices), vbo_time
    
    def _render_decorations_with_textures_legacy(self, decoration_sprites, camera_x: float, camera_y: float):
        """Legacy rendering method using separate textures (fallback if atlas not available)."""
        import numpy as np
        import moderngl
        
        if not decoration_sprites:
            return
        
        # Use tile_texture_manager instead of decoration_texture_manager
        texture_manager = self.modern_gl_renderer.tile_texture_manager
        if not texture_manager or not texture_manager.texture_atlas:
            # If no atlas available, fall back to color rendering
            self._render_decorations_with_colors(decoration_sprites)
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


