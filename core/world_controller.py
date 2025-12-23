"""
Core: WorldController - Verwaltung von World, Player und Camera
"""
from typing import Optional, Tuple
import numpy as np
import moderngl
import math
from core import settings
from core.camera import Camera
from core.input_pyglet import InputHandler
from world.world import World
from world.player_data_manager import PlayerDataManager
from world.auto_save import AutoSaveSystem
from combat.player import Player
from analytics.performance_monitor import PerformanceMonitor


class WorldController:
    """Verwaltet World, Player und Camera"""
    
    def __init__(self, input_handler: InputHandler, performance_monitor: PerformanceMonitor,
                 modern_gl_renderer, width: int, height: int, diagnostics=None):
        """
        Args:
            input_handler: InputHandler instance
            performance_monitor: PerformanceMonitor instance
            modern_gl_renderer: ModernGLRenderer instance
            width: Window width
            height: Window height
        """
        self.input_handler = input_handler
        self.performance_monitor = performance_monitor
        self.modern_gl_renderer = modern_gl_renderer
        self.width = width
        self.height = height
        self.diagnostics = diagnostics  # Store diagnostics service for logging
        
        # Game components
        self.world: Optional[World] = None
        self.player: Optional[Player] = None
        self.camera: Optional[Camera] = None
        self.all_sprites = None
        self.resource_sprites = None
        self.building_sprites = None
        self.player_data_manager: Optional[PlayerDataManager] = None
        self.auto_save: Optional[AutoSaveSystem] = None
        
        # Camera zoom
        self.camera_zoom = 1.0
        
        # Mouse position tracking
        self.mouse_x = 0
        self.mouse_y = 0
        
        # Game state
        self.game_initialized = False
        
        # Debug visualization cache
        self._debug_cache = {
            'mode': -1,
            'player_chunk': None,
            'chunks_hash': None,
            'vbo': None,
            'vao': None,
            'line_count': 0
        }
    
    def initialize_game(self, world_name: str, seed: Optional[int] = None):
        """Initialize the game world"""
        from core.sprite import LayeredUpdates, SpriteGroup
        from world.world_utils import sanitize_world_name
        
        # Sprite-Gruppen (ohne Pygame)
        self.all_sprites = LayeredUpdates()
        self.resource_sprites = SpriteGroup()
        self.building_sprites = SpriteGroup()
        
        # Sanitize world name for use as directory name
        sanitized_name = sanitize_world_name(world_name)
        
        # Welt erstellen
        self.world = World(
            self.all_sprites, 
            self.resource_sprites, 
            world_name=sanitized_name, 
            seed=seed,
            performance_monitor=self.performance_monitor,
            diagnostics=self.diagnostics
        )
        
        # Set world name in metadata (use original name, not sanitized)
        self.world.chunk_manager.set_world_name(world_name)
        
        # Initialize PlayerDataManager
        self.player_data_manager = PlayerDataManager(sanitized_name)
        
        # Load player data from save (required - no fallback to default spawn)
        player_data = self.player_data_manager.load_player()
        
        if not player_data:
            # No save exists - create initial save at world center
            if self.diagnostics:
                self.diagnostics.info("WorldController", f"No existing player data found for world '{world_name}', creating initial save...")
            world_size_pixels = settings.WORLD_SIZE_CHUNKS * settings.CHUNK_SIZE * settings.TILE_SIZE
            initial_x = world_size_pixels / 2.0
            initial_y = world_size_pixels / 2.0
            
            # Create initial player data
            self.player_data_manager.save_player(
                position=(initial_x, initial_y),
                inventory={},
                faction_data={'policies': [], 'allies': [], 'enemies': []},
                sprint_multiplier=1.2,
                sneak_multiplier=0.8
            )
            
            # Reload to get the newly created data
            player_data = self.player_data_manager.load_player()
            if not player_data:
                raise RuntimeError(f"Failed to create initial player data for world '{world_name}'")
        
        # Extract player data from save
        spawn_pos = self.player_data_manager.get_spawn_position()
        if not spawn_pos:
            raise RuntimeError(f"Failed to get spawn position from world '{world_name}'")
        
        # Check if spawn position is traversable, if not find nearest traversable position
        start_world_x, start_world_y = self._find_traversable_spawn_position(spawn_pos[0], spawn_pos[1])
        
        # Update spawn position if it was changed
        if (start_world_x, start_world_y) != spawn_pos:
            if self.diagnostics:
                self.diagnostics.info("WorldController", f"Spawn position adjusted from {spawn_pos} to ({start_world_x:.0f}, {start_world_y:.0f}) - original was not traversable")
            # Update saved position to traversable position
            inventory_size = player_data.get('inventory_size', None)
            sprint_multiplier = player_data.get('sprint_multiplier', 1.2)
            sneak_multiplier = player_data.get('sneak_multiplier', 0.8)
            self.player_data_manager.save_player(
                position=(start_world_x, start_world_y),
                inventory=player_data.get('inventory', {}),
                faction_data=player_data.get('faction', {'policies': [], 'allies': [], 'enemies': []}),
                inventory_size=inventory_size,
                sprint_multiplier=sprint_multiplier,
                sneak_multiplier=sneak_multiplier
            )
        
        player_inventory = player_data.get('inventory', {})
        player_faction = player_data.get('faction', {'policies': [], 'allies': [], 'enemies': []})
        
        if self.diagnostics:
            self.diagnostics.info("WorldController", f"Loaded player data from world '{world_name}'")
            self.diagnostics.info("WorldController", f"Player spawn position: ({start_world_x:.0f}, {start_world_y:.0f})")
        
        # Get sprint and sneak multipliers from player data
        sprint_multiplier = player_data.get('sprint_multiplier', 1.2)
        sneak_multiplier = player_data.get('sneak_multiplier', 0.8)
        
        # Player erstellen
        self.player = Player(
            pos=(start_world_x, start_world_y),
            input_handler=self.input_handler,
            performance_monitor=self.performance_monitor,
            terrain_gen=self.world.terrain_gen,
            sprint_multiplier=sprint_multiplier,
            sneak_multiplier=sneak_multiplier
        )
        
        # Set player inventory and faction from save
        self.player.inventory = player_inventory
        self.player.faction = player_faction
        
        self.all_sprites.add(self.player, layer=settings.LAYER_PLAYER)
        
        # Store player reference for auto-save
        self._auto_save_player = self.player
        
        # Kamera initialisieren
        self.camera = Camera(target=self.player, lerp_speed=settings.CAMERA_LERP_SPEED)
        # Set camera position immediately to player position (no lerp delay on start)
        self.camera.x = start_world_x
        self.camera.y = start_world_y
        # Zoom: 1.5 = 150% (nah), 0.75 = 75% (weit weg)
        self.camera_zoom = 1.0  # Start at 100%
        
        # Initialize Auto-Save System
        # AutoSaveSystem saves chunks automatically, but we also need to save player data
        # So we'll extend the save() method to also save player data
        self.auto_save = AutoSaveSystem(
            world=self.world,
            world_name=sanitized_name,
            interval_seconds=300.0,  # 5 minutes default
            diagnostics=self.diagnostics
        )
        
        # Store reference to player_data_manager for saving player data during auto-save
        self._auto_save_player_data_manager = self.player_data_manager
        self._auto_save_player = None  # Will be set after player is created
        
        # Mark game as initialized
        self.game_initialized = True
        
        if self.diagnostics:
            self.diagnostics.info("WorldController", f"Game initialized - Player spawned at ({start_world_x:.0f}, {start_world_y:.0f})")
        
        # Pre-load visible chunks around spawn position
        if self.world and self.world.chunk_manager:
            self.world.chunk_manager.preload_visible_chunks((start_world_x, start_world_y))
    
    def _find_traversable_spawn_position(self, start_x: float, start_y: float) -> Tuple[float, float]:
        """Find nearest traversable position if spawn position is not traversable"""
        if not self.world or not self.world.terrain_gen:
            return (start_x, start_y)
        
        # Check if starting position is traversable
        start_tile_x = int(start_x // settings.TILE_SIZE)
        start_tile_y = int(start_y // settings.TILE_SIZE)
        tile = self.world.terrain_gen.generate_tile(start_tile_x, start_tile_y)
        
        if tile.get('traversable', False):
            return (start_x, start_y)
        
        # Search in spiral pattern for nearest traversable tile
        max_search_radius = 50  # Search up to 50 tiles away
        for radius in range(1, max_search_radius + 1):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    # Only check tiles on the edge of current radius
                    if abs(dx) == radius or abs(dy) == radius:
                        check_tile_x = start_tile_x + dx
                        check_tile_y = start_tile_y + dy
                        tile = self.world.terrain_gen.generate_tile(check_tile_x, check_tile_y)
                        
                        if tile.get('traversable', False):
                            # Found traversable tile - return center position
                            found_x = check_tile_x * settings.TILE_SIZE + settings.TILE_SIZE / 2.0
                            found_y = check_tile_y * settings.TILE_SIZE + settings.TILE_SIZE / 2.0
                            if self.diagnostics:
                                self.diagnostics.info("WorldController", f"Found traversable spawn position at ({found_x:.0f}, {found_y:.0f})")
                            return (found_x, found_y)
        
        # If no traversable tile found, return original position
        if self.diagnostics:
            self.diagnostics.warning("WorldController", f"Could not find traversable spawn position, using original ({start_x:.0f}, {start_y:.0f})")
        return (start_x, start_y)
    
    def update(self, dt: float):
        """Update world, player and camera"""
        if not self.game_initialized:
            return
        
        self.performance_monitor.start_update()
        
        if self.all_sprites:
            self.all_sprites.update(dt)
        if self.camera:
            self.camera.update(dt)
        if self.world:
            self.world.update(self.player.rect.center if self.player else (0, 0))
        
        # Update auto-save system (checks if save is needed)
        if self.auto_save:
            old_save_time = self.auto_save.last_save_time
            self.auto_save.update(dt)
            # Check if auto-save was triggered (last_save_time changed)
            if self.auto_save.last_save_time != old_save_time:
                # Also save player data when auto-save triggers
                if self._auto_save_player_data_manager and self._auto_save_player:
                    try:
                        sprint_multiplier = getattr(self._auto_save_player, 'sprint_multiplier', 1.2)
                        sneak_multiplier = getattr(self._auto_save_player, 'sneak_multiplier', 0.8)
                        self._auto_save_player_data_manager.save_player(
                            position=(self._auto_save_player.rect.x, self._auto_save_player.rect.y),
                            inventory=getattr(self._auto_save_player, 'inventory', {}),
                            faction_data=getattr(self._auto_save_player, 'faction', {'policies': [], 'allies': [], 'enemies': []}),
                            inventory_size=None,
                            sprint_multiplier=sprint_multiplier,
                            sneak_multiplier=sneak_multiplier
                        )
                        if self.diagnostics:
                            self.diagnostics.info("WorldController", "Player data saved during auto-save")
                    except Exception as e:
                        if self.diagnostics:
                            self.diagnostics.error("WorldController", f"Error saving player data during auto-save: {e}")
        
        self.performance_monitor.end_update()
    
    def load_visible_chunks(self, camera_x: float, camera_y: float):
        """Load chunks in visible area + buffer based on zoom"""
        if not self.world or not self.world.chunk_manager:
            return
        
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        screen_width = self.modern_gl_renderer.screen_width
        screen_height = self.modern_gl_renderer.screen_height
        
        # Calculate visible area bounds using zoom
        visible_world_width = screen_width / self.camera_zoom
        visible_world_height = screen_height / self.camera_zoom
        
        # Add buffer (load extra chunks around visible area)
        buffer_chunks = 2
        buffer_pixels = buffer_chunks * chunk_size_pixels
        
        world_min_x = camera_x - visible_world_width / 2.0 - buffer_pixels
        world_max_x = camera_x + visible_world_width / 2.0 + buffer_pixels
        world_min_y = camera_y - visible_world_height / 2.0 - buffer_pixels
        world_max_y = camera_y + visible_world_height / 2.0 + buffer_pixels
        
        # Convert to chunk coordinates
        min_chunk_x = int(world_min_x // chunk_size_pixels)
        max_chunk_x = int(world_max_x // chunk_size_pixels) + 1
        min_chunk_y = int(world_min_y // chunk_size_pixels)
        max_chunk_y = int(world_max_y // chunk_size_pixels) + 1
        
        # Load chunks in range
        for chunk_x in range(min_chunk_x, max_chunk_x + 1):
            for chunk_y in range(min_chunk_y, max_chunk_y + 1):
                # Check world bounds before loading
                if (0 <= chunk_x < settings.WORLD_SIZE_CHUNKS and
                    0 <= chunk_y < settings.WORLD_SIZE_CHUNKS):
                    self.world.chunk_manager.get_or_create_chunk(chunk_x, chunk_y)
    
    def draw(self, debug_visualization_mode: int = 0):
        """Draw world, chunks, player and debug visualization"""
        if not self.game_initialized or not self.world or not self.world.chunk_manager:
            return
        
        # Step 1: Update view matrix based on camera position and zoom
        if self.camera:
            camera_x = self.camera.x
            camera_y = self.camera.y
            self.modern_gl_renderer.update_view(camera_x, camera_y, zoom=self.camera_zoom)
        else:
            camera_x = 0.0
            camera_y = 0.0
            self.modern_gl_renderer.update_view(0.0, 0.0, zoom=self.camera_zoom)
        
        # Step 1.5: Load chunks in visible area + buffer (dynamically based on zoom)
        self.load_visible_chunks(camera_x, camera_y)
        
        # Step 2: Collect all visible chunks (with frustum culling based on zoom)
        chunks_data = []
        screen_width = self.modern_gl_renderer.screen_width
        screen_height = self.modern_gl_renderer.screen_height
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        
        # Calculate visible area bounds
        visible_world_width = screen_width / self.camera_zoom
        visible_world_height = screen_height / self.camera_zoom
        
        world_min_x = camera_x - visible_world_width / 2.0
        world_max_x = camera_x + visible_world_width / 2.0
        world_min_y = camera_y - visible_world_height / 2.0
        world_max_y = camera_y + visible_world_height / 2.0
        
        # Process chunks: visible -> rendering -> active -> rendered
        for chunk in self.world.chunk_manager.loaded_chunks.values():
            if chunk.render_state == "rendered":
                chunk.render_state = None
        
        # Process all loaded chunks - render all chunks that are in the visible area
        for chunk in self.world.chunk_manager.loaded_chunks.values():
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
            self.modern_gl_renderer.render_chunks(chunks_data, performance_monitor=self.performance_monitor)
            
            # Mark rendered chunks as "rendered"
            for chunk_x, chunk_y, _ in chunks_data:
                chunk_key = (chunk_x, chunk_y)
                if chunk_key in self.world.chunk_manager.loaded_chunks:
                    chunk = self.world.chunk_manager.loaded_chunks[chunk_key]
                    if chunk.render_state == "active":
                        chunk.render_state = "rendered"
        
        # Step 4: Render debug visualization
        if debug_visualization_mode > 0:
            self._render_debug_visualization(chunks_data, debug_visualization_mode)
        
        # Step 5: Render player
        if self.player:
            self._render_player()
    
    def _render_player(self):
        """Render player as yellow quad (1 tile wide, 2 tiles tall)"""
        if not self.player:
            return
        
        tile_size = settings.TILE_SIZE
        player_width = tile_size
        player_height = tile_size * 2
        
        player_world_x = self.player.rect.center[0]
        player_world_y = self.player.rect.center[1]
        
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
    
    def _render_debug_visualization(self, chunks_data, debug_visualization_mode: int):
        """Render debug visualization: chunk boundaries and tile grids"""
        if not chunks_data or not self.world or not self.player:
            if debug_visualization_mode == 0 and self._debug_cache['vbo']:
                self._debug_cache['vbo'].release()
                self._debug_cache['vao'].release()
                self._debug_cache['vbo'] = None
                self._debug_cache['vao'] = None
            return
        
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        tile_size_pixels = settings.TILE_SIZE
        
        player_world_x = self.player.rect.center[0]
        player_world_y = self.player.rect.center[1]
        player_chunk_x = int(player_world_x // chunk_size_pixels)
        player_chunk_y = int(player_world_y // chunk_size_pixels)
        player_chunk = (player_chunk_x, player_chunk_y)
        
        chunks_hash = hash(tuple(sorted((x, y) for x, y, _ in chunks_data)))
        
        cache_valid = (
            self._debug_cache['mode'] == debug_visualization_mode and
            self._debug_cache['player_chunk'] == player_chunk and
            self._debug_cache['chunks_hash'] == chunks_hash and
            self._debug_cache['vbo'] is not None
        )
        
        if not cache_valid:
            if self._debug_cache['vbo']:
                self._debug_cache['vbo'].release()
                self._debug_cache['vao'].release()
            
            grid_radius = 2
            grid_min_x = player_chunk_x - grid_radius
            grid_max_x = player_chunk_x + grid_radius
            grid_min_y = player_chunk_y - grid_radius
            grid_max_y = player_chunk_y + grid_radius
            
            lines = []
            
            for chunk_x, chunk_y, _ in chunks_data:
                chunk_world_x = chunk_x * chunk_size_pixels
                chunk_world_y = chunk_y * chunk_size_pixels
                chunk_world_max_x = chunk_world_x + chunk_size_pixels
                chunk_world_max_y = chunk_world_y + chunk_size_pixels
                
                if debug_visualization_mode >= 1:
                    lines.append([chunk_world_x, chunk_world_y, chunk_world_max_x, chunk_world_y, 1.0, 0.0, 0.0])
                    lines.append([chunk_world_x, chunk_world_max_y, chunk_world_max_x, chunk_world_max_y, 1.0, 0.0, 0.0])
                    lines.append([chunk_world_x, chunk_world_y, chunk_world_x, chunk_world_max_y, 1.0, 0.0, 0.0])
                    lines.append([chunk_world_max_x, chunk_world_y, chunk_world_max_x, chunk_world_max_y, 1.0, 0.0, 0.0])
                
                if debug_visualization_mode >= 2 and self.camera_zoom > 1.0:
                    if grid_min_x <= chunk_x <= grid_max_x and grid_min_y <= chunk_y <= grid_max_y:
                        for tile_x in range(1, settings.CHUNK_SIZE):
                            tile_world_x = chunk_world_x + tile_x * tile_size_pixels
                            lines.append([tile_world_x, chunk_world_y, tile_world_x, chunk_world_max_y, 0.0, 0.0, 1.0])
                        
                        for tile_y in range(1, settings.CHUNK_SIZE):
                            tile_world_y = chunk_world_y + tile_y * tile_size_pixels
                            lines.append([chunk_world_x, tile_world_y, chunk_world_max_x, tile_world_y, 0.0, 0.0, 1.0])
            
            if lines:
                vertices = []
                for x1, y1, x2, y2, r, g, b in lines:
                    vertices.extend([
                        [x1, y1, r, g, b],
                        [x2, y2, r, g, b]
                    ])
                
                vertices_array = np.array(vertices, dtype=np.float32)
                
                self._debug_cache['vbo'] = self.modern_gl_renderer.ctx.buffer(vertices_array.tobytes())
                self._debug_cache['vao'] = self.modern_gl_renderer.ctx.vertex_array(
                    self.modern_gl_renderer.chunk_program,
                    [(self._debug_cache['vbo'], "2f 3f", "in_position", "in_color")]
                )
                self._debug_cache['line_count'] = len(lines)
            else:
                self._debug_cache['vbo'] = None
                self._debug_cache['vao'] = None
                self._debug_cache['line_count'] = 0
            
            self._debug_cache['mode'] = debug_visualization_mode
            self._debug_cache['player_chunk'] = player_chunk
            self._debug_cache['chunks_hash'] = chunks_hash
        
        if self._debug_cache['vao']:
            self._debug_cache['vao'].render(moderngl.LINES)
    
    def handle_mouse_press(self, x: int, y: int, button: int, modifiers: int):
        """Handle mouse press for tile interaction"""
        if not self.game_initialized or not self.player or not self.world:
            return
        
        self._handle_tile_click(x, y, button)
    
    def handle_mouse_motion(self, x: int, y: int, dx: int, dy: int):
        """Handle mouse motion"""
        self.mouse_x = x
        self.mouse_y = y
    
    def handle_mouse_scroll(self, x: int, y: int, scroll_x: float, scroll_y: float, modifiers: int):
        """Handle mouse scroll for camera zoom"""
        from pyglet.window import key
        
        # Zoom only when Control is pressed
        if key.LCTRL in modifiers or key.RCTRL in modifiers:
            zoom_speed = 0.1
            self.camera_zoom += scroll_y * zoom_speed
            self.camera_zoom = max(0.5, min(2.0, self.camera_zoom))  # Clamp between 0.5x and 2.0x
    
    def _handle_tile_click(self, mouse_x: int, mouse_y: int, button: int):
        """Handle tile click for debug output"""
        tile_info = self._get_tile_under_mouse(mouse_x, mouse_y)
        if not tile_info:
            return
        
        tile_x, tile_y, tile_data = tile_info
        
        if button == 1:  # Left click
            traversable = tile_data.get('traversable', False)
            if traversable:
                destroyable = self._is_tile_destroyable(tile_data)
                if self.diagnostics:
                    self.diagnostics.info("WorldController", f"Left click on tile ({tile_x}, {tile_y}): destroyable={destroyable}")
            else:
                if self.diagnostics:
                    self.diagnostics.info("WorldController", f"Left click on tile ({tile_x}, {tile_y}): nicht zerstörbar (nicht traversable)")
        elif button == 4:  # Right click
            can_build = self._can_build_on_tile(tile_data)
            if self.diagnostics:
                self.diagnostics.info("WorldController", f"Right click on tile ({tile_x}, {tile_y}): can_build={can_build}")
    
    def _get_tile_under_mouse(self, mouse_x: int, mouse_y: int):
        """Get tile under mouse cursor if within 8 tiles of player"""
        if not self.camera:
            return None
        
        screen_width = self.width
        screen_height = self.height
        
        world_x = self.camera.x + (mouse_x - screen_width / 2.0) / self.camera_zoom
        world_y = self.camera.y + (screen_height / 2.0 - mouse_y) / self.camera_zoom
        
        player_x = self.player.rect.x
        player_y = self.player.rect.y
        
        distance_tiles = math.sqrt(
            ((world_x - player_x) / settings.TILE_SIZE) ** 2 +
            ((world_y - player_y) / settings.TILE_SIZE) ** 2
        )
        
        if distance_tiles > 8.0:
            return None
        
        tile_x = int(world_x // settings.TILE_SIZE)
        tile_y = int(world_y // settings.TILE_SIZE)
        
        if self.world and self.world.terrain_gen:
            tile_data = self.world.terrain_gen.generate_tile(tile_x, tile_y)
            return (tile_x, tile_y, tile_data)
        
        return None
    
    def _is_tile_destroyable(self, tile_data: dict) -> bool:
        """Check if tile can be destroyed"""
        tile_id = tile_data.get('tile_id', '')
        biome = tile_data.get('biome', '')
        
        if 'water' in biome or 'shallow' in tile_id:
            return False
        
        return tile_data.get('traversable', False)
    
    def _can_build_on_tile(self, tile_data: dict) -> bool:
        """Check if tile can be built upon"""
        tile_id = tile_data.get('tile_id', '')
        biome = tile_data.get('biome', '')
        
        if 'water' in biome or 'shallow' in tile_id:
            return False
        
        return True
    
    def cleanup(self):
        """Cleanup resources"""
        if self.auto_save:
            self.auto_save.stop(final_save=False)
        if self.world:
            self.world.cleanup()
