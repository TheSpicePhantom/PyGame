"""
Core: WorldController - Verwaltung von World, Player und Camera
"""
from typing import Optional, Tuple, List
import numpy as np
import moderngl
import math
from core import settings
from core.camera import Camera
from core.input_pyglet import InputHandler
from core.zoom_utils import calculate_visible_world_size
from world.world import World
from world.player_data_manager import PlayerDataManager
from world.auto_save import AutoSaveSystem
from combat.player import Player
from analytics.performance_monitor import PerformanceMonitor

# Default mining values for decorations without mining config
DEFAULT_MINING_DURABILITY = 50
DEFAULT_MINING_TOOL_REQUIRED = None  # Can be mined with hand
DEFAULT_MINING_SPEED = 10.0  # Increased for faster mining (was 1.0)


class WorldController:
    """Verwaltet World, Player und Camera"""
    
    def __init__(self, input_handler: InputHandler, performance_monitor: PerformanceMonitor,
                 modern_gl_renderer, width: int, height: int, diagnostics=None, game_app=None):
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
        self.game_app = game_app  # Store reference to game_app for accessing UI controller
        
        # Debug output control
        self.enable_debug_output = True  # Set to True to enable debug logging
        
        # Game components
        self.world: Optional[World] = None
        self.player: Optional[Player] = None
        self.camera: Optional[Camera] = None
        self.all_sprites = None
        self.resource_sprites = None
        self.building_sprites = None
        self.player_data_manager: Optional[PlayerDataManager] = None
        self.auto_save: Optional[AutoSaveSystem] = None
        self.world_renderer = None  # Set by main_pyglet.py after WorldRenderer creation
        
        # Camera zoom
        self.camera_zoom = 1.0
        
        # Mouse position tracking
        self.mouse_x = 0
        self.mouse_y = 0
        
        # Mining state (for continuous mining on decoration)
        self._mining_decoration = None  # (tile_x, tile_y) of decoration being mined
        self._mining_start_time = 0.0  # Time when mining started
        
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
        
        # Reload decoration textures and rebuild atlas (DecorationRegistry is now loaded)
        # This must happen BEFORE World creation so texture_manager is available for chunk generation
        texture_manager = None
        if self.modern_gl_renderer and self.modern_gl_renderer.tile_texture_manager:
            try:
                self.modern_gl_renderer.tile_texture_manager.reload_decoration_textures_and_rebuild_atlas()
                # CRITICAL: Invalidate all decoration VBOs after atlas rebuild
                # VBOs contain UV coordinates that are now invalid after atlas rebuild
                if self.world_renderer:
                    self.world_renderer.mark_all_decoration_chunks_dirty()
                if self.diagnostics:
                    self.diagnostics.info("WorldController", "Reloaded decoration textures and rebuilt atlas, invalidated all decoration VBOs")
                texture_manager = self.modern_gl_renderer.tile_texture_manager
            except Exception as e:
                if self.diagnostics:
                    self.diagnostics.warning("WorldController", f"Failed to reload decoration textures: {e}")
        
        # Welt erstellen - texture_manager wird direkt übergeben, damit texture_tags beim Generieren gesetzt werden
        self.world = World(
            self.all_sprites, 
            self.resource_sprites, 
            world_name=sanitized_name, 
            seed=seed,
            performance_monitor=self.performance_monitor,
            diagnostics=self.diagnostics,
            texture_manager=texture_manager  # Pass texture_manager directly so chunks get texture_tags during generation
        )
        
        # Note: set_texture_manager() is no longer needed since texture_manager is passed directly
        # But keep it for backward compatibility and in case texture_manager wasn't available during World creation
        if self.modern_gl_renderer and self.modern_gl_renderer.tile_texture_manager and not texture_manager:
            self.world.set_texture_manager(self.modern_gl_renderer.tile_texture_manager)
        
        # Set renderer for chunk manager (required for vertex preparation)
        if self.modern_gl_renderer:
            self.world.chunk_manager.set_renderer(self.modern_gl_renderer)
            if self.diagnostics:
                self.diagnostics.info("WorldController", "Renderer set for chunk manager")
        
        # Set world name in metadata (use original name, not sanitized)
        self.world.chunk_manager.set_world_name(world_name)
        
        # Set world_controller reference in chunk_manager for SeasonManager cache invalidation
        if hasattr(self.world.chunk_manager, 'world_controller'):
            self.world.chunk_manager.world_controller = self
        
        # Set world_controller reference in GrowthManager for cache invalidation
        try:
            from world.growth_manager import GrowthManager
            GrowthManager.set_world_controller(self)
        except ImportError:
            pass  # GrowthManager not available
        
        # Initialize PlayerDataManager
        self.player_data_manager = PlayerDataManager(sanitized_name)
        
        # Load player data from save (required - no fallback to default spawn)
        player_data = self.player_data_manager.load_player()
        
        if not player_data:
            # No save exists - create initial save at world center
            if self.diagnostics and self.enable_debug_output:
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
            if self.diagnostics and self.enable_debug_output:
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
        
        if self.diagnostics and self.enable_debug_output:
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
            world_controller=self,  # Add reference for decoration collision checking
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
        
        if self.diagnostics and self.enable_debug_output:
            self.diagnostics.info("WorldController", f"Game initialized - Player spawned at ({start_world_x:.0f}, {start_world_y:.0f})")
        
        # Pre-load visible chunks around spawn position
        # Mark as done to prevent duplicate pre-load in World.update()
        if self.world and self.world.chunk_manager:
            # Use new preload_visible_area method with camera position and screen size
            screen_width = self.modern_gl_renderer.screen_width if self.modern_gl_renderer else 1920
            screen_height = self.modern_gl_renderer.screen_height if self.modern_gl_renderer else 1080
            zoom = self.camera_zoom
            
            # Pre-load visible chunks
            min_chunk_x, max_chunk_x, min_chunk_y, max_chunk_y = self.world.chunk_manager.get_visible_chunk_range(
                start_world_x, start_world_y, screen_width, screen_height, zoom, padding_chunks=2
            )
            self.world.chunk_manager.preload_visible_area(
                start_world_x, start_world_y, screen_width, screen_height, zoom, padding_chunks=2
            )
            
            # Force redraw of all preloaded chunks to ensure all decorations are rendered correctly
            if self.world_renderer:
                self.world_renderer.mark_chunks_dirty_in_range(
                    min_chunk_x, max_chunk_x, min_chunk_y, max_chunk_y
                )
            
            # Mark initial preload as done to prevent duplicate in World.update()
            self.world._initial_preload_done = True
    
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
                            if self.diagnostics and self.enable_debug_output:
                                self.diagnostics.info("WorldController", f"Found traversable spawn position at ({found_x:.0f}, {found_y:.0f})")
                            return (found_x, found_y)
        
        # If no traversable tile found, return original position
        if self.diagnostics and self.enable_debug_output:
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
            # Get camera position and screen dimensions for chunk loading
            camera_pos = (self.camera.x, self.camera.y) if self.camera else None
            screen_width = self.modern_gl_renderer.screen_width if self.modern_gl_renderer else None
            screen_height = self.modern_gl_renderer.screen_height if self.modern_gl_renderer else None
            
            # Get movement direction from input handler (if available) for asymmetric chunk loading
            movement_dir = None
            if hasattr(self, 'input_handler') and self.input_handler:
                movement_dir = self.input_handler.move_dir
            
            self.world.update(
                player_pos=self.player.rect.center if self.player else (0, 0),
                camera_pos=camera_pos,
                screen_width=screen_width,
                screen_height=screen_height,
                zoom=self.camera_zoom,
                movement_dir=movement_dir,
                dt=dt
            )
        
        # Handle continuous mining if mouse is held down on decoration
        if self._mining_decoration:
            tile_x, tile_y = self._mining_decoration
            # Verify decoration still exists and is still mineable
            tile_info = self._get_tile_under_mouse(self.mouse_x, self.mouse_y)
            if not tile_info or len(tile_info) < 4:
                # Decoration no longer exists or mouse moved away
                self._reset_mining_timer(tile_x, tile_y)
                self._mining_decoration = None
                self._mining_start_time = 0.0
            else:
                current_tile_x, current_tile_y, tile_data, clicked_decoration = tile_info
                if current_tile_x != tile_x or current_tile_y != tile_y or not clicked_decoration:
                    # Mouse moved to different tile or decoration
                    self._reset_mining_timer(tile_x, tile_y)
                    self._mining_decoration = None
                    self._mining_start_time = 0.0
                else:
                    # Continue mining
                    mining_completed = self.mine_decoration(tile_x, tile_y, dt)
                    if mining_completed:
                        # Mining finished, stop mining
                        self._mining_decoration = None
                        self._mining_start_time = 0.0
        
        # Process chunks that finished loading asynchronously
        if self.world and self.world.chunk_manager:
            self.world.chunk_manager.process_loaded_chunks(
                self.all_sprites if hasattr(self, 'all_sprites') else None,
                self.resource_sprites if hasattr(self, 'resource_sprites') else None
            )
        
        # Update tile decorations (growth timers, regrowth, etc.)
        if self.world and self.world.chunk_manager:
            self.update_tile_decorations(dt)
        
        # Update auto-save system (checks if save is needed)
        if self.auto_save:
            old_save_time = self.auto_save.last_save_time
            self.auto_save.update(dt)
            # Check if auto-save was triggered (last_save_time changed)
            if self.auto_save.last_save_time != old_save_time:
                # Also save player data when auto-save triggers
                if self._auto_save_player_data_manager and self._auto_save_player:
                    try:
                        # Get inventory from inventory menu if available (new slot-based format)
                        inventory = {}
                        inventory_size = None
                        if self.game_app and self.game_app.ui_controller:
                            if self.game_app.ui_controller.inventory_menu:
                                inventory_data = self.game_app.ui_controller.inventory_menu.get_inventory_data()
                                inventory = inventory_data  # Pass full dict with 'slots' and 'inventory_size'
                                inventory_size = inventory_data.get('inventory_size', 45)
                        # Fallback to old player.inventory format if inventory menu not available
                        if not inventory or (isinstance(inventory, dict) and 'slots' not in inventory):
                            old_inventory = getattr(self._auto_save_player, 'inventory', {})
                            if old_inventory:
                                inventory = old_inventory
                        sprint_multiplier = getattr(self._auto_save_player, 'sprint_multiplier', 1.2)
                        sneak_multiplier = getattr(self._auto_save_player, 'sneak_multiplier', 0.8)
                        self._auto_save_player_data_manager.save_player(
                            position=(self._auto_save_player.rect.x, self._auto_save_player.rect.y),
                            inventory=inventory,
                            faction_data=getattr(self._auto_save_player, 'faction', {'policies': [], 'allies': [], 'enemies': []}),
                            inventory_size=inventory_size,
                            sprint_multiplier=sprint_multiplier,
                            sneak_multiplier=sneak_multiplier
                        )
                        if self.diagnostics and self.enable_debug_output:
                            self.diagnostics.info("WorldController", "Player data saved during auto-save")
                    except Exception as e:
                        if self.diagnostics and self.enable_debug_output:
                            self.diagnostics.error("WorldController", f"Error saving player data during auto-save: {e}")
        
        self.performance_monitor.end_update()
    
    def get_chunks_to_unload(self, visible_chunks: set, loaded_chunks: set, 
                             camera_x: float, camera_y: float, 
                             hysteresis_factor: float = 1.5) -> List[Tuple[int, int]]:
        """
        Unload chunks that are far outside visible area (with hysteresis to avoid thrashing)
        
        Args:
            visible_chunks: Set of (chunk_x, chunk_y) tuples that are currently visible
            loaded_chunks: Set of (chunk_x, chunk_y) tuples that are currently loaded
            camera_x: Camera X position in world coordinates
            camera_y: Camera Y position in world coordinates
            hysteresis_factor: Factor to multiply padding for unload threshold (default: 1.5)
        
        Returns:
            List of (chunk_x, chunk_y) tuples to unload
        """
        from core import settings
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        padding_chunks = 2
        unload_threshold = chunk_size_pixels * padding_chunks * hysteresis_factor
        
        chunks_to_unload = []
        for chunk_key in loaded_chunks:
            if chunk_key not in visible_chunks:
                # Berechne Distanz vom Chunk-Zentrum zur Kamera
                chunk_center_x = chunk_key[0] * chunk_size_pixels + chunk_size_pixels / 2
                chunk_center_y = chunk_key[1] * chunk_size_pixels + chunk_size_pixels / 2
                
                # Squared distance (ohne sqrt für Performance)
                distance_squared = (chunk_center_x - camera_x)**2 + (chunk_center_y - camera_y)**2
                unload_threshold_squared = unload_threshold**2
                
                if distance_squared > unload_threshold_squared:
                    chunks_to_unload.append(chunk_key)
        
        return chunks_to_unload
    
    def get_visible_chunks(self, camera_x: float, camera_y: float) -> List[Tuple[int, int, List[List[dict]]]]:
        """
        Get list of chunks that are currently visible (frustum culling).
        
        Args:
            camera_x: Camera X position in world coordinates (pixels)
            camera_y: Camera Y position in world coordinates (pixels)
        
        Returns:
            List of (chunk_x, chunk_y, tiles) tuples for visible chunks
        """
        if not self.world or not self.world.chunk_manager:
            return []
        
        if not self.modern_gl_renderer:
            return []
        
        from core.zoom_utils import get_viewport_bounds
        from core import settings
        
        # Use same viewport bounds calculation as renderer
        screen_width = self.modern_gl_renderer.screen_width
        screen_height = self.modern_gl_renderer.screen_height
        viewport_min_x, viewport_max_x, viewport_min_y, viewport_max_y = get_viewport_bounds(
            screen_width, screen_height, camera_x, camera_y, self.camera_zoom
        )
        
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        
        # Add padding to viewport bounds to ensure chunks extend beyond visible area
        # This prevents cuts where decorations are visible but terrain chunks are missing
        padding_chunks = 4  # Chunks of padding on each side
        padding_pixels = padding_chunks * chunk_size_pixels
        
        # Expand world bounds with padding
        world_min_x = viewport_min_x - padding_pixels
        world_max_x = viewport_max_x + padding_pixels
        world_min_y = viewport_min_y - padding_pixels
        world_max_y = viewport_max_y + padding_pixels
        
        visible_chunks = []
        
        # Frustum culling - check which loaded chunks overlap with visible area
        for chunk in self.world.chunk_manager.loaded_chunks.values():
            if not chunk.tiles:
                continue
            
            chunk_world_x = chunk.chunk_x * chunk_size_pixels
            chunk_world_y = chunk.chunk_y * chunk_size_pixels
            chunk_world_max_x = chunk_world_x + chunk_size_pixels
            chunk_world_max_y = chunk_world_y + chunk_size_pixels
            
            # Check overlap
            x_overlaps = (chunk_world_x <= world_max_x) and (chunk_world_max_x >= world_min_x)
            y_overlaps = (chunk_world_y <= world_max_y) and (chunk_world_max_y >= world_min_y)
            
            if x_overlaps and y_overlaps:
                visible_chunks.append((chunk.chunk_x, chunk.chunk_y, chunk.tiles))
        
        return visible_chunks
    
    def get_chunk_ranges(self, camera_x: float, camera_y: float) -> dict:
        """
        Get chunk ranges for load/unload areas (for debug visualization).
        
        Args:
            camera_x: Camera X position in world coordinates (pixels)
            camera_y: Camera Y position in world coordinates (pixels)
        
        Returns:
            Dictionary with 'load_range' and 'unload_range' containing (min_x, max_x, min_y, max_y) tuples
        """
        if not self.world or not self.world.chunk_manager or not self.modern_gl_renderer:
            return {'load_range': None, 'unload_range': None, 'render_range': None}
        
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        screen_width = self.modern_gl_renderer.screen_width
        screen_height = self.modern_gl_renderer.screen_height
        
        # Calculate visible area bounds using central zoom utility
        visible_world_width, visible_world_height = calculate_visible_world_size(
            screen_width, screen_height, self.camera_zoom
        )
        
        import math
        
        # LOAD RANGE - sichtbarer Bereich + kleiner Buffer
        load_buffer_chunks = 2  # Fester Buffer für Load-Bereich
        load_buffer_pixels = load_buffer_chunks * chunk_size_pixels
        
        world_min_x = camera_x - visible_world_width / 2.0 - load_buffer_pixels
        world_max_x = camera_x + visible_world_width / 2.0 + load_buffer_pixels
        world_min_y = camera_y - visible_world_height / 2.0 - load_buffer_pixels
        world_max_y = camera_y + visible_world_height / 2.0 + load_buffer_pixels
        
        # Convert to chunk coordinates (use floor for min, ceil for max)
        min_chunk_x = int(math.floor(world_min_x / chunk_size_pixels))
        max_chunk_x = int(math.ceil(world_max_x / chunk_size_pixels))
        min_chunk_y = int(math.floor(world_min_y / chunk_size_pixels))
        max_chunk_y = int(math.ceil(world_max_y / chunk_size_pixels))
        
        # RENDER RANGE - sichtbarer Bereich ohne Buffer (nur was gerendert wird)
        render_world_min_x = camera_x - visible_world_width / 2.0
        render_world_max_x = camera_x + visible_world_width / 2.0
        render_world_min_y = camera_y - visible_world_height / 2.0
        render_world_max_y = camera_y + visible_world_height / 2.0
        
        render_min_chunk_x = int(math.floor(render_world_min_x / chunk_size_pixels))
        render_max_chunk_x = int(math.ceil(render_world_max_x / chunk_size_pixels))
        render_min_chunk_y = int(math.floor(render_world_min_y / chunk_size_pixels))
        render_max_chunk_y = int(math.ceil(render_world_max_y / chunk_size_pixels))
        
        # UNLOAD RANGE - größerer Buffer als Load Range (Hysterese)
        unload_buffer_chunks = load_buffer_chunks + 5  # 5 zusätzliche Chunks bevor Unload
        unload_buffer_pixels = unload_buffer_chunks * chunk_size_pixels
        
        unload_min_x = camera_x - visible_world_width / 2.0 - unload_buffer_pixels
        unload_max_x = camera_x + visible_world_width / 2.0 + unload_buffer_pixels
        unload_min_y = camera_y - visible_world_height / 2.0 - unload_buffer_pixels
        unload_max_y = camera_y + visible_world_height / 2.0 + unload_buffer_pixels
        
        unload_min_chunk_x = int(math.floor(unload_min_x / chunk_size_pixels))
        unload_max_chunk_x = int(math.ceil(unload_max_x / chunk_size_pixels))
        unload_min_chunk_y = int(math.floor(unload_min_y / chunk_size_pixels))
        unload_max_chunk_y = int(math.ceil(unload_max_y / chunk_size_pixels))
        
        return {
            'load_range': (min_chunk_x, max_chunk_x, min_chunk_y, max_chunk_y),
            'render_range': (render_min_chunk_x, render_max_chunk_x, render_min_chunk_y, render_max_chunk_y),
            'unload_range': (unload_min_chunk_x, unload_max_chunk_x, unload_min_chunk_y, unload_max_chunk_y)
        }
    
    def load_visible_chunks(self, camera_x: float, camera_y: float):
        """Load chunks in visible area + buffer based on zoom, unload chunks outside visible area"""
        if not self.world or not self.world.chunk_manager:
            return
        
        # Check if renderer is available
        if not self.modern_gl_renderer:
            return
        
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        screen_width = self.modern_gl_renderer.screen_width
        screen_height = self.modern_gl_renderer.screen_height
        
        # Calculate visible area bounds using central zoom utility
        visible_world_width, visible_world_height = calculate_visible_world_size(
            screen_width, screen_height, self.camera_zoom
        )
        
        import math
        
        # LOAD RANGE - sichtbarer Bereich + kleiner Buffer
        load_buffer_chunks = 2  # Fester Buffer für Load-Bereich
        load_buffer_pixels = load_buffer_chunks * chunk_size_pixels
        
        world_min_x = camera_x - visible_world_width / 2.0 - load_buffer_pixels
        world_max_x = camera_x + visible_world_width / 2.0 + load_buffer_pixels
        world_min_y = camera_y - visible_world_height / 2.0 - load_buffer_pixels
        world_max_y = camera_y + visible_world_height / 2.0 + load_buffer_pixels
        
        # Convert to chunk coordinates (use floor for min, ceil for max)
        min_chunk_x = int(math.floor(world_min_x / chunk_size_pixels))
        max_chunk_x = int(math.ceil(world_max_x / chunk_size_pixels))
        min_chunk_y = int(math.floor(world_min_y / chunk_size_pixels))
        max_chunk_y = int(math.ceil(world_max_y / chunk_size_pixels))
        
        # UNLOAD RANGE - größerer Buffer als Load Range (Hysterese)
        unload_buffer_chunks = load_buffer_chunks + 5  # 5 zusätzliche Chunks bevor Unload
        unload_buffer_pixels = unload_buffer_chunks * chunk_size_pixels
        
        unload_min_x = camera_x - visible_world_width / 2.0 - unload_buffer_pixels
        unload_max_x = camera_x + visible_world_width / 2.0 + unload_buffer_pixels
        unload_min_y = camera_y - visible_world_height / 2.0 - unload_buffer_pixels
        unload_max_y = camera_y + visible_world_height / 2.0 + unload_buffer_pixels
        
        unload_min_chunk_x = int(math.floor(unload_min_x / chunk_size_pixels))
        unload_max_chunk_x = int(math.ceil(unload_max_x / chunk_size_pixels))
        unload_min_chunk_y = int(math.floor(unload_min_y / chunk_size_pixels))
        unload_max_chunk_y = int(math.ceil(unload_max_y / chunk_size_pixels))
        
        # Track chunks that should be loaded with priorities based on distance from camera
        chunks_to_load = []
        camera_chunk_x = int(math.floor(camera_x / chunk_size_pixels))
        camera_chunk_y = int(math.floor(camera_y / chunk_size_pixels))
        
        for chunk_x in range(min_chunk_x, max_chunk_x):
            for chunk_y in range(min_chunk_y, max_chunk_y):
                # Check world bounds before loading
                if (0 <= chunk_x < settings.WORLD_SIZE_CHUNKS and
                    0 <= chunk_y < settings.WORLD_SIZE_CHUNKS):
                    chunk_key = (chunk_x, chunk_y)
                    
                    # Skip if already loaded or pending
                    if chunk_key in self.world.chunk_manager.loaded_chunks:
                        continue
                    if chunk_key in self.world.chunk_manager.pending_chunks:
                        continue
                    
                    # Calculate priority based on distance from camera (closer = higher priority)
                    dx = abs(chunk_x - camera_chunk_x)
                    dy = abs(chunk_y - camera_chunk_y)
                    distance = dx + dy  # Manhattan distance
                    priority = distance
                    
                    chunks_to_load.append((priority, chunk_x, chunk_y))
        
        # Request async loading for chunks (sorted by priority)
        # Limit number of chunks requested per frame to prevent overload
        chunks_to_load.sort()  # Sort by priority (lower = higher priority)
        max_loads_per_frame = 20  # Limit to 20 chunk load requests per frame
        for priority, chunk_x, chunk_y in chunks_to_load[:max_loads_per_frame]:
            self.world.chunk_manager.request_chunk_load(chunk_x, chunk_y, priority=priority)
        
        # Get visible chunks for VBO release
        # Use the unload range (unload_min_chunk_x, etc.) that was already calculated above
        # This range is larger than the load range (buffer_chunks + 6), so chunks within this
        # range should keep their VBOs loaded
        visible_chunks_for_vbo = set()
        for chunk_x in range(unload_min_chunk_x, unload_max_chunk_x):
            for chunk_y in range(unload_min_chunk_y, unload_max_chunk_y):
                if (0 <= chunk_x < settings.WORLD_SIZE_CHUNKS and
                    0 <= chunk_y < settings.WORLD_SIZE_CHUNKS):
                    visible_chunks_for_vbo.add((chunk_x, chunk_y))
        
        # Find chunks to unload VBOs for (only those outside the unload range)
        # This uses the same range as the chunk manager's unload logic for consistency
        loaded_chunks = set(self.world.chunk_manager.loaded_chunks.keys())
        chunks_to_unload_vbo = []
        for chunk_key in loaded_chunks:
            # Only unload VBO if chunk is outside the unload range
            # This matches the chunk manager's unload logic - chunks within unload range
            # should keep their VBOs loaded
            if chunk_key not in visible_chunks_for_vbo:
                chunks_to_unload_vbo.append(chunk_key)
        
        # Release VBOs for chunks that are far outside visible area
        # Only release if there are chunks to unload (avoid unnecessary operations)
        # IMPORTANT: Only release VBOs for chunks that are actually loaded and have VBOs
        if chunks_to_unload_vbo and self.modern_gl_renderer:
            # Filter: Only unload VBOs for chunks that are actually in the renderer's buffer cache
            chunks_with_vbos = [
                chunk_key for chunk_key in chunks_to_unload_vbo
                if chunk_key in self.modern_gl_renderer.chunk_buffers
            ]
            if chunks_with_vbos:
                self.modern_gl_renderer.release_chunk_buffers(chunks_with_vbos)
                if self.modern_gl_renderer.diagnostics and self.enable_debug_output:
                    self.modern_gl_renderer.diagnostics.debug("WorldController", 
                        f"Released {len(chunks_with_vbos)} VBOs for chunks outside unload range "
                        f"(unload_range: {unload_min_chunk_x}-{unload_max_chunk_x}, "
                        f"{unload_min_chunk_y}-{unload_max_chunk_y}, "
                        f"visible_chunks: {len(visible_chunks_for_vbo)}, "
                        f"loaded_chunks: {len(loaded_chunks)})")
        
        # Unload chunks that are outside the unload area (with cooldown to prevent thrashing)
        import time
        current_time = time.time()
        chunks_to_unload = []
        
        # Debug: Log unload range (only occasionally to avoid spam)
        if not hasattr(self, '_unload_debug_counter'):
            self._unload_debug_counter = 0
        self._unload_debug_counter += 1
        
        # Debug output disabled
        # if self._unload_debug_counter % 60 == 0 and self.modern_gl_renderer and self.modern_gl_renderer.diagnostics and self.enable_debug_output:
        #     # Verify that camera chunk is within load range
        #     camera_in_load_range = (min_chunk_x <= camera_chunk_x < max_chunk_x and 
        #                            min_chunk_y <= camera_chunk_y < max_chunk_y)
        #     camera_in_unload_range = (unload_min_chunk_x <= camera_chunk_x < unload_max_chunk_x and 
        #                              unload_min_chunk_y <= camera_chunk_y < unload_max_chunk_y)
        #     
        #     self.modern_gl_renderer.diagnostics.debug("WorldController", 
        #         f"Unload range: X=[{unload_min_chunk_x}..{unload_max_chunk_x}], "
        #         f"Y=[{unload_min_chunk_y}..{unload_max_chunk_y}], "
        #         f"Load range: X=[{min_chunk_x}..{max_chunk_x}], Y=[{min_chunk_y}..{max_chunk_y}], "
        #         f"Camera chunk: ({camera_chunk_x}, {camera_chunk_y}), "
        #         f"camera_in_load_range: {camera_in_load_range}, "
        #         f"camera_in_unload_range: {camera_in_unload_range}")
        #     
        #     if not camera_in_load_range:
        #         self.modern_gl_renderer.diagnostics.warning("WorldController", 
        #             f"WARNING: Camera chunk ({camera_chunk_x}, {camera_chunk_y}) is OUTSIDE load range "
        #             f"X=[{min_chunk_x}..{max_chunk_x}], Y=[{min_chunk_y}..{max_chunk_y}]")
        
        for chunk_key, chunk in list(self.world.chunk_manager.loaded_chunks.items()):
            chunk_x, chunk_y = chunk_key
            
            # Check if chunk is INSIDE the unload bounds (should be KEPT)
            # Chunks inside: unload_min_chunk_x <= chunk_x < unload_max_chunk_x
            # Chunks outside: chunk_x < unload_min_chunk_x OR chunk_x >= unload_max_chunk_x
            is_inside_unload_range = (unload_min_chunk_x <= chunk_x < unload_max_chunk_x and
                                      unload_min_chunk_y <= chunk_y < unload_max_chunk_y)
            
            # Only unload chunks that are OUTSIDE the unload range
            if not is_inside_unload_range:
                # Check cooldown: chunk must be outside visible area for at least cooldown seconds
                load_time = self.world.chunk_manager.chunk_load_times.get(chunk_key, current_time)
                time_since_load = current_time - load_time
                
                # Only unload if chunk has been loaded for at least cooldown seconds
                # This prevents rapid load/unload cycles
                if time_since_load >= self.world.chunk_manager.chunk_unload_cooldown:
                    chunks_to_unload.append(chunk_key)
                    
                    # Debug output disabled
                    # if self.modern_gl_renderer and self.modern_gl_renderer.diagnostics and self.enable_debug_output:
                    #     distance_from_camera = ((chunk_x - camera_chunk_x)**2 + (chunk_y - camera_chunk_y)**2)**0.5
                    #     self.modern_gl_renderer.diagnostics.warning("WorldController", 
                    #         f"UNLOADING chunk ({chunk_x}, {chunk_y}) - "
                    #         f"distance from camera: {distance_from_camera:.1f} chunks, "
                    #         f"camera_chunk: ({camera_chunk_x}, {camera_chunk_y}), "
                    #         f"unload_range: X=[{unload_min_chunk_x}..{unload_max_chunk_x}], Y=[{unload_min_chunk_y}..{unload_max_chunk_y}], "
                    #         f"is_inside: {is_inside_unload_range}")
        
        # Unload chunks (limit to avoid frame drops - reduced from 10 to 3 per frame)
        # Debug output disabled
        # if chunks_to_unload and self.modern_gl_renderer and self.modern_gl_renderer.diagnostics and self.enable_debug_output:
        #     # Log which chunks are being unloaded (only occasionally)
        #     if self._unload_debug_counter % 60 == 0:
        #         chunks_to_unload_sorted = sorted(chunks_to_unload, 
        #             key=lambda k: ((k[0] - camera_chunk_x)**2 + (k[1] - camera_chunk_y)**2)**0.5)
        #         closest_unload = chunks_to_unload_sorted[:5]  # Show 5 closest chunks being unloaded
        #         self.modern_gl_renderer.diagnostics.debug("WorldController", 
        #             f"Unloading {len(chunks_to_unload)} chunks. Closest 5: {closest_unload}")
        
        for chunk_key in chunks_to_unload[:3]:  # Unload max 3 chunks per frame
            chunk_x, chunk_y = chunk_key
            # Clear prepared vertices when chunk is unloaded
            if hasattr(self.modern_gl_renderer, 'clear_prepared_chunk'):
                self.modern_gl_renderer.clear_prepared_chunk(chunk_x, chunk_y)
            self.world.chunk_manager.unload_chunk(chunk_x, chunk_y)
    
    def draw(self, debug_visualization_mode: int = 0):
        """Draw world, chunks, player and debug visualization"""
        if not self.game_initialized or not self.world or not self.world.chunk_manager:
            return
        
        # Check if renderer is available
        if not self.modern_gl_renderer:
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
        
        # Step 2: Collect all loaded chunks for rendering (stable list from loaded_chunks)
        chunks_data = []
        screen_width = self.modern_gl_renderer.screen_width
        screen_height = self.modern_gl_renderer.screen_height
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        
        # Calculate visible area bounds using central zoom utility
        visible_world_width, visible_world_height = calculate_visible_world_size(
            screen_width, screen_height, self.camera_zoom
        )
        
        world_min_x = camera_x - visible_world_width / 2.0
        world_max_x = camera_x + visible_world_width / 2.0
        world_min_y = camera_y - visible_world_height / 2.0
        world_max_y = camera_y + visible_world_height / 2.0
        
        # Collect all loaded chunks for rendering (stable list from loaded_chunks)
        # Optional: Simple frustum culling to skip chunks far outside screen
        enable_frustum_cull = True  # Set to False to render all loaded chunks without culling
        
        for chunk in self.world.chunk_manager.loaded_chunks.values():
            if not chunk.tiles:
                continue
            
            # Optional frustum culling: Skip chunks that are clearly outside visible area
            if enable_frustum_cull:
                chunk_world_x = chunk.chunk_x * chunk_size_pixels
                chunk_world_y = chunk.chunk_y * chunk_size_pixels
                chunk_world_max_x = chunk_world_x + chunk_size_pixels
                chunk_world_max_y = chunk_world_y + chunk_size_pixels
                
                # Simple frustum check: chunk overlaps with visible area
                x_overlaps = (chunk_world_x <= world_max_x) and (chunk_world_max_x >= world_min_x)
                y_overlaps = (chunk_world_y <= world_max_y) and (chunk_world_max_y >= world_min_y)
                chunk_overlaps = x_overlaps and y_overlaps
                
                if not chunk_overlaps:
                    continue  # Skip chunks outside visible area
            
            # Add chunk to render list
            chunks_data.append((chunk.chunk_x, chunk.chunk_y, chunk.tiles))
        
        # Step 2.5: Process texture assignment for loaded chunks (separate phase after loading)
        # This ensures textures are assigned AFTER chunks are fully loaded, before rendering
        if self.world and self.world.chunk_manager:
            chunk_manager = self.world.chunk_manager
            camera_x = self.camera.x if self.camera else None
            camera_y = self.camera.y if self.camera else None
            
            # Force texture assignment for all chunks when:
            # 1. Loading is complete (no chunks in queue and no pending chunks), OR
            # 2. Many chunks are waiting (beim Rauszoomen), OR
            # 3. Many chunks are loaded (indicates zoom out scenario where many chunks are visible)
            queue_size = chunk_manager.chunk_load_queue.qsize()
            pending_size = len(chunk_manager.pending_chunks)
            loaded_size = len(chunk_manager.loaded_chunks)
            
            # force_all if: loading complete OR many chunks waiting OR many chunks loaded (zoom out)
            # When zooming out, many chunks become visible at once, so we need to process them all
            force_all = (
                (queue_size == 0 and pending_size == 0) or  # Loading complete
                (loaded_size > 50 and queue_size + pending_size > 10) or  # Many chunks waiting
                (loaded_size > 80)  # Many chunks loaded (zoom out scenario - process all immediately)
            )
            
            chunk_manager.process_texture_assignment(
                camera_x=camera_x,
                camera_y=camera_y,
                max_chunks_per_frame=10,
                force_all=force_all
            )
            
            # Pre-bake chunks in larger radius (asynchronous, non-blocking)
            # This prepares chunks before they become visible, preventing texture delays
            chunk_manager.pre_bake_chunks_around_camera(camera_x, camera_y, pre_bake_radius_chunks=3)
        
        # Step 3: Render all chunks from stable loaded_chunks list
        # Note: render_chunks() will only render chunks with prepared_chunk_vertices (textures assigned)
        if chunks_data:
            self.modern_gl_renderer.render_chunks(chunks_data, performance_monitor=self.performance_monitor)
        
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
        
        import time
        self._handle_tile_click(x, y, button)
        
        # If left-click on decoration, start mining
        if button == 1:  # Left click
            tile_info = self._get_tile_under_mouse(x, y)
            if tile_info and len(tile_info) == 4:
                tile_x, tile_y, tile_data, clicked_decoration = tile_info
                if clicked_decoration:
                    decoration_data = tile_data.get('decoration')
                    if decoration_data:
                        try:
                            from world.decoration_registry import DecorationRegistry
                            from world.decoration import Decoration
                            
                            decoration_id = decoration_data.get('decoration_id')
                            if decoration_id:
                                deco_config = DecorationRegistry.get(decoration_id)
                                if deco_config:
                                    decoration = Decoration(deco_config)
                                    if decoration.is_mineable():
                                        # Start mining
                                        self._mining_decoration = (tile_x, tile_y)
                                        self._mining_start_time = time.time()
                                    elif self.diagnostics and self.enable_debug_output:
                                        self.diagnostics.warning("WorldController", f"Decoration {decoration_id} is not mineable")
                                elif self.diagnostics and self.enable_debug_output:
                                    self.diagnostics.warning("WorldController", f"Decoration config not found for {decoration_id}")
                        except ImportError:
                            pass
    
    def handle_mouse_release(self, x: int, y: int, button: int, modifiers: int):
        """Handle mouse release - stop mining if left button released"""
        if button == 1:  # Left click released
            # Reset mining timer when mouse button is released
            if self._mining_decoration:
                tile_x, tile_y = self._mining_decoration
                self._reset_mining_timer(tile_x, tile_y)
            self._mining_decoration = None
            self._mining_start_time = 0.0
    
    def handle_mouse_motion(self, x: int, y: int, dx: int, dy: int):
        """Handle mouse motion"""
        self.mouse_x = x
        self.mouse_y = y
        
        # If mining, check if mouse is still over the same decoration
        if self._mining_decoration:
            tile_x, tile_y = self._mining_decoration
            tile_info = self._get_tile_under_mouse(x, y)
            
            # Stop mining if:
            # 1. No tile under mouse
            # 2. Different tile
            # 3. Not on decoration anymore
            if not tile_info or len(tile_info) < 4:
                # Reset mining timer when leaving decoration
                self._reset_mining_timer(tile_x, tile_y)
                self._mining_decoration = None
                self._mining_start_time = 0.0
            else:
                current_tile_x, current_tile_y, tile_data, clicked_decoration = tile_info
                if current_tile_x != tile_x or current_tile_y != tile_y or not clicked_decoration:
                    # Reset mining timer when leaving decoration
                    self._reset_mining_timer(tile_x, tile_y)
                    self._mining_decoration = None
                    self._mining_start_time = 0.0
    
    def handle_mouse_scroll(self, x: int, y: int, scroll_x: float, scroll_y: float, modifiers: int):
        """Handle mouse scroll for camera zoom"""
        from pyglet.window import key
        
        # Zoom only when Control is pressed
        if key.LCTRL in modifiers or key.RCTRL in modifiers:
            zoom_speed = 0.1
            old_zoom = self.camera_zoom
            self.camera_zoom += scroll_y * zoom_speed
            self.camera_zoom = max(0.5, min(2.0, self.camera_zoom))  # Clamp between 0.5x and 2.0x
            
            # Refresh visible chunks if zoom actually changed
            if self.camera_zoom != old_zoom and self.game_initialized and self.world and self.world.chunk_manager:
                if self.camera:
                    camera_pos = (self.camera.x, self.camera.y)
                else:
                    camera_pos = (0.0, 0.0)
                
                screen_width = self.modern_gl_renderer.screen_width
                screen_height = self.modern_gl_renderer.screen_height
                
                self.world.chunk_manager.refresh_visible_chunks_for_zoom(
                    camera_pos, 
                    self.camera_zoom,
                    screen_width,
                    screen_height
                )
                
                # CRITICAL: Invalidate all decoration VBOs after zoom change
                # When zooming out, new chunks become visible and their VBOs may have been created
                # before textures were available. Force rebuild to ensure textures are assigned.
                if self.world_renderer:
                    # Mark all chunks as dirty and release all VBOs
                    self.world_renderer.mark_all_decoration_chunks_dirty()
                    
                    # CRITICAL: Also explicitly invalidate all cached VBOs to force rebuild
                    # This ensures VBOs created with fallback textures are rebuilt with real textures
                    if hasattr(self.world_renderer, '_chunk_decoration_vbos'):
                        vbo_count = len(self.world_renderer._chunk_decoration_vbos)
                        for chunk_key in list(self.world_renderer._chunk_decoration_vbos.keys()):
                            self.world_renderer._decoration_dirty_chunks.add(chunk_key)
                        if self.diagnostics:
                            self.diagnostics.debug("WorldController", 
                                f"Zoom changed from {old_zoom:.2f} to {self.camera_zoom:.2f}, invalidated {vbo_count} cached decoration VBOs")
                    
                    # CRITICAL: Also invalidate all VBOs to force rebuild with correct textures
                    # This ensures VBOs created with fallback textures are rebuilt with real textures
                    if hasattr(self.world_renderer, '_chunk_decoration_vbos'):
                        for chunk_key in list(self.world_renderer._chunk_decoration_vbos.keys()):
                            self.world_renderer._decoration_dirty_chunks.add(chunk_key)
                        if self.diagnostics:
                            self.diagnostics.debug("WorldController", 
                                f"Invalidated {len(self.world_renderer._chunk_decoration_vbos)} cached decoration VBOs to force rebuild")
                
                # CRITICAL: Force texture assignment for all chunks when zoom changes
                # This ensures all newly visible chunks get textures assigned immediately
                chunk_manager = self.world.chunk_manager
                camera_x = self.camera.x if self.camera else None
                camera_y = self.camera.y if self.camera else None
                
                # Force ALL chunks to be processed immediately (no budget limit)
                chunk_manager.process_texture_assignment(
                    camera_x=camera_x,
                    camera_y=camera_y,
                    max_chunks_per_frame=999,  # Very high limit
                    force_all=True  # CRITICAL: Process all chunks without budget limit
                )
                
                if self.diagnostics:
                    self.diagnostics.debug("WorldController", 
                        f"Forced texture assignment for all chunks after zoom change")
    
    def _handle_tile_click(self, mouse_x: int, mouse_y: int, button: int):
        """Handle tile click for interactions (harvest, mining) and debug output"""
        tile_info = self._get_tile_under_mouse(mouse_x, mouse_y)
        if not tile_info:
            return
        
        # Unpack tile info (now includes clicked_decoration flag)
        if len(tile_info) == 4:
            tile_x, tile_y, tile_data, clicked_decoration = tile_info
        else:
            # Backward compatibility
            tile_x, tile_y, tile_data = tile_info[:3]
            clicked_decoration = False
        
        biome = tile_data.get('biome', 'unknown')
        tile_id = tile_data.get('tileid', '') or tile_data.get('tile_id', 'unknown')
        
        # Check for decoration interactions (only if mouse is on decoration bounding box)
        decoration_data = tile_data.get('decoration')
        if decoration_data and clicked_decoration:
            if button == 4:  # Right click - Harvest
                if self.diagnostics and self.enable_debug_output:
                    self.diagnostics.info("WorldController", f"Attempting to harvest decoration at ({tile_x}, {tile_y})")
                success = self.harvest_decoration(tile_x, tile_y)
                if success:
                    if self.diagnostics and self.enable_debug_output:
                        self.diagnostics.info("WorldController", f"Successfully harvested decoration at ({tile_x}, {tile_y})")
                else:
                    if self.diagnostics and self.enable_debug_output:
                        self.diagnostics.warning("WorldController", f"Failed to harvest decoration at ({tile_x}, {tile_y})")
                return
            elif button == 1:  # Left click - Start mining (handled in handle_mouse_press for continuous mining)
                # Mining is started in handle_mouse_press and continues in update() while mouse is held
                # Just return here to prevent tile interaction
                return
        
        # Fallback to tile interactions (mouse is on tile, not decoration)
        if button == 1:  # Left click
            traversable = tile_data.get('traversable', False)
            if traversable:
                destroyable = self._is_tile_destroyable(tile_data)
                if self.diagnostics and self.enable_debug_output:
                    self.diagnostics.info("WorldController", f"Left click on tile ({tile_x}, {tile_y}): destroyable={destroyable} (Biome: {biome}, Tile-ID: {tile_id})")
            else:
                if self.diagnostics and self.enable_debug_output:
                    self.diagnostics.info("WorldController", f"Left click on tile ({tile_x}, {tile_y}): nicht zerstörbar (nicht traversable, Biome: {biome}, Tile-ID: {tile_id})")
        elif button == 4:  # Right click
            can_build = self._can_build_on_tile(tile_data)
            if self.diagnostics and self.enable_debug_output:
                if can_build:
                    self.diagnostics.info("WorldController", f"Right click on tile ({tile_x}, {tile_y}): can_build={can_build} (Biome: {biome}, Tile-ID: {tile_id})")
                else:
                    self.diagnostics.info("WorldController", f"Right click on tile ({tile_x}, {tile_y}): can_build={can_build} - darauf kann nicht gebaut werden (Biome: {biome}, Tile-ID: {tile_id})")
    
    def harvest_decoration(self, tile_x: int, tile_y: int) -> bool:
        """
        Harvest decoration at tile position (right-click action).
        
        Args:
            tile_x: Tile X coordinate
            tile_y: Tile Y coordinate
            
        Returns:
            True if harvest was successful, False otherwise
        """
        if not self.world or not self.world.chunk_manager or not self.player:
            return False
        
        try:
            from world.decoration_registry import DecorationRegistry
            from world.decoration import Decoration
        except ImportError:
            return False
        
        # Get chunk coordinates
        chunk_x = tile_x // settings.CHUNK_SIZE
        chunk_y = tile_y // settings.CHUNK_SIZE
        
        # Get tile coordinates within chunk
        tile_x_in_chunk = tile_x % settings.CHUNK_SIZE
        tile_y_in_chunk = tile_y % settings.CHUNK_SIZE
        
        # Check if chunk is loaded
        chunk_key = (chunk_x, chunk_y)
        if chunk_key not in self.world.chunk_manager.loaded_chunks:
            return False
        
        chunk = self.world.chunk_manager.loaded_chunks[chunk_key]
        
        # Get tile directly to ensure we're working with the actual tile data
        tile = chunk.tiles[tile_y_in_chunk][tile_x_in_chunk]
        if not tile:
            return False
        
        # Get decoration from tile directly
        decoration_data = tile.get('decoration')
        if not decoration_data:
            return False
        
        decoration_id = decoration_data.get('decoration_id')
        if not decoration_id:
            return False
        
        # Get decoration config
        deco_config = DecorationRegistry.get(decoration_id)
        if not deco_config:
            return False
        
        decoration = Decoration(deco_config)
        
        # Check if harvestable
        if not decoration.is_harvestable():
            return False
        
        # Get decoration data - ensure 'data' key exists
        if 'data' not in decoration_data:
            decoration_data['data'] = {}
        deco_data = decoration_data['data']
        
        # Check if has fruit (for harvestable items)
        has_fruit = deco_data.get('has_fruit', True)
        if self.diagnostics and self.enable_debug_output:
            self.diagnostics.debug("WorldController", f"Decoration {decoration_id} at ({tile_x}, {tile_y}) has_fruit={has_fruit}")
        if not has_fruit:
            if self.diagnostics and self.enable_debug_output:
                self.diagnostics.info("WorldController", f"Decoration {decoration_id} at ({tile_x}, {tile_y}) already harvested, not regrown yet")
            return False  # Already harvested, not regrown yet
        
        # Roll loot table
        loot = decoration.get_loot()
        
        if self.diagnostics and self.enable_debug_output:
            self.diagnostics.info("WorldController", f"Harvest loot: {loot}")
        
        # Add items to inventory menu (if available) or fallback to player.add_item
        if self.game_app and self.game_app.ui_controller and self.game_app.ui_controller.inventory_menu:
            for item_id, quantity in loot.items():
                if self.diagnostics and self.enable_debug_output:
                    self.diagnostics.info("WorldController", f"Adding {quantity} of {item_id} to inventory")
                remaining = self.game_app.ui_controller.inventory_menu.add_item(item_id, quantity)
                if remaining > 0:
                    if self.diagnostics:
                        self.diagnostics.warning("WorldController", f"Inventory full: {remaining} items of {item_id} could not be added")
                elif self.diagnostics and self.enable_debug_output:
                    self.diagnostics.info("WorldController", f"Successfully added {quantity} of {item_id} to inventory")
        else:
            # Fallback to old player.add_item method
            if self.diagnostics:
                self.diagnostics.warning("WorldController", f"InventoryMenu not available, using fallback player.add_item. game_app={self.game_app is not None}")
            for item_id, quantity in loot.items():
                self.player.add_item(item_id, quantity)
        
        # Set regrowth timer
        harvest_config = deco_config.get('harvest', {})
        regrowth_config = harvest_config.get('regrowth', {})
        import random
        regrowth_time = random.uniform(
            regrowth_config.get('min_time', 30.0),
            regrowth_config.get('max_time', 180.0)
        )
        
        # Update decoration data in tile (directly modify the tile's decoration data)
        deco_data['growth_timer'] = regrowth_time
        deco_data['initial_growth_time'] = regrowth_time  # Store initial time for progress calculation
        deco_data['has_fruit'] = False
        deco_data['last_interaction'] = 0.0  # Will be updated in update_tile_decorations
        
        # Ensure the updated decoration_data is stored in the tile
        tile['decoration'] = decoration_data
        
        # Update decoration lookup
        chunk._rebuild_decoration_lookup()
        
        # Trigger event
        decoration.on_harvest(self.player, tile)
        
        if self.diagnostics and self.enable_debug_output:
            self.diagnostics.info("WorldController", f"Harvested {decoration_id} at ({tile_x}, {tile_y}), got {loot}")
        
        return True
    
    def mine_decoration(self, tile_x: int, tile_y: int, dt: float) -> bool:
        """
        Mine decoration at tile position (left-click hold action).
        
        Args:
            tile_x: Tile X coordinate
            tile_y: Tile Y coordinate
            dt: Delta time for mining progress
            
        Returns:
            True if mining was completed (decoration destroyed), False otherwise
        """
        if not self.world or not self.world.chunk_manager or not self.player:
            return False
        
        try:
            from world.decoration_registry import DecorationRegistry
            from world.decoration import Decoration
        except ImportError:
            return False
        
        # Get chunk coordinates
        chunk_x = tile_x // settings.CHUNK_SIZE
        chunk_y = tile_y // settings.CHUNK_SIZE
        
        # Get tile coordinates within chunk
        tile_x_in_chunk = tile_x % settings.CHUNK_SIZE
        tile_y_in_chunk = tile_y % settings.CHUNK_SIZE
        
        # Check if chunk is loaded
        chunk_key = (chunk_x, chunk_y)
        if chunk_key not in self.world.chunk_manager.loaded_chunks:
            return False
        
        chunk = self.world.chunk_manager.loaded_chunks[chunk_key]
        
        # Get decoration at this tile position
        decoration_data = chunk.get_decoration_at(tile_x_in_chunk, tile_y_in_chunk)
        if not decoration_data:
            if self.diagnostics and self.enable_debug_output:
                self.diagnostics.warning("WorldController", f"No decoration found at ({tile_x}, {tile_y}) in chunk ({chunk_x}, {chunk_y})")
            return False
        
        decoration_id = decoration_data.get('decoration_id')
        if not decoration_id:
            return False
        
        # Get decoration config
        deco_config = DecorationRegistry.get(decoration_id)
        if not deco_config:
            return False
        
        decoration = Decoration(deco_config)
        
        # Check if mineable (now always returns True, but keep check for consistency)
        if not decoration.is_mineable():
            return False
        
        # Get tool (placeholder)
        tool = self.get_equipped_tool()
        mining_config = deco_config.get('mining', {})
        
        # Use default values if no mining config exists
        if not mining_config:
            # Create temporary mining config with defaults
            mining_config = {
                'hardness': 'wood',
                'mining_time': 3.0,
                'hardness_multiplier': 1.0,
                'tool_required': DEFAULT_MINING_TOOL_REQUIRED,
                'loot_table': None  # No loot by default
            }
        
        # Get resource hardness (default: wood)
        resource_hardness = mining_config.get('hardness', 'wood')
        
        # Get tool ID for hardness checking
        tool_id = tool.get('tool_id') if tool else None
        
        # Check if tool can mine this resource (using ToolMappingRegistry)
        from world.tool_mapping_registry import ToolMappingRegistry
        if tool_id and not ToolMappingRegistry.can_mine(tool_id, resource_hardness):
            if self.diagnostics and self.enable_debug_output:
                tool_level = ToolMappingRegistry.get_tool_level(tool_id)
                self.diagnostics.warning("WorldController", f"Tool {tool_id} (tier: {tool_level}) cannot mine {decoration_id} (hardness: {resource_hardness})")
            return False  # Tool too weak
        
        # Legacy tool_required check (for backwards compatibility)
        required_tool = mining_config.get('tool_required')
        if required_tool:
            tool_type = tool.get('tool_type') if tool else None
            if tool_type != required_tool:
                if self.diagnostics and self.enable_debug_output:
                    self.diagnostics.warning("WorldController", f"Wrong tool for {decoration_id}: required {required_tool}, got {tool_type}")
                return False  # Wrong tool
        
        # Get decoration data - ensure 'data' key exists
        if 'data' not in decoration_data:
            decoration_data['data'] = {}
        deco_data = decoration_data['data']
        
        # Initialize elapsed_time if not present (new system)
        if 'elapsed_time' not in deco_data:
            deco_data['elapsed_time'] = 0.0
        
        # Get mining time configuration
        mining_time = mining_config.get('mining_time', 3.0)
        hardness_multiplier = mining_config.get('hardness_multiplier', 1.0)
        
        # Get mining speed multiplier from tool
        if tool_id:
            mining_speed_multiplier = ToolMappingRegistry.get_mining_speed_multiplier(tool_id)
        else:
            # Default to hand speed if no tool
            mining_speed_multiplier = ToolMappingRegistry.get_mining_speed_multiplier('hand')
        
        # Calculate time to mine
        time_to_mine = (mining_time * hardness_multiplier) / mining_speed_multiplier
        
        # Accumulate elapsed time
        elapsed_time = deco_data.get('elapsed_time', 0.0)
        elapsed_time += dt
        deco_data['elapsed_time'] = elapsed_time
        deco_data['last_interaction'] = 0.0  # Will be updated in update_tile_decorations
        
        # Check if mined (elapsed_time >= time_to_mine)
        if elapsed_time >= time_to_mine:
            # Roll loot table
            loot = decoration.get_loot()
            
            # Add items to inventory menu (if available) or fallback to player.add_item
            if self.game_app and self.game_app.ui_controller and self.game_app.ui_controller.inventory_menu:
                for item_id, quantity in loot.items():
                    if self.diagnostics and self.enable_debug_output:
                        self.diagnostics.info("WorldController", f"Adding {quantity} of {item_id} to inventory")
                    remaining = self.game_app.ui_controller.inventory_menu.add_item(item_id, quantity)
                    if remaining > 0:
                        if self.diagnostics:
                            self.diagnostics.warning("WorldController", f"Inventory full: {remaining} items of {item_id} could not be added")
                    elif self.diagnostics and self.enable_debug_output:
                        self.diagnostics.info("WorldController", f"Successfully added {quantity} of {item_id} to inventory")
            else:
                # Fallback to old player.add_item method
                if self.diagnostics:
                    self.diagnostics.warning("WorldController", f"InventoryMenu not available, using fallback player.add_item. game_app={self.game_app is not None}")
                for item_id, quantity in loot.items():
                    self.player.add_item(item_id, quantity)
            
            # Get tile reference before removing decoration
            tile = chunk.tiles[tile_y_in_chunk][tile_x_in_chunk]
            
            # Set stump sprite and start removal timer (2-3 seconds)
            import random
            stump_duration = random.uniform(2.0, 3.0)  # 2-3 seconds
            deco_data['sprite_state'] = 'stump'
            deco_data['stump_timer'] = stump_duration
            deco_data['is_stump'] = True  # Flag to indicate this is a stump waiting for removal
            
            # Trigger event (before removing decoration, so tile is still valid)
            decoration.on_mine_complete(self.player, tile)
            
            # Don't remove decoration yet - let stump timer handle it
            # The decoration will be removed in update_tile_decorations() when stump_timer expires
            
            # Mark chunk's decoration VBO as dirty (sprite changed to stump)
            if self.world_renderer:
                self.world_renderer.mark_decoration_chunk_dirty(chunk_x, chunk_y)
            
            return True
        
        # Update damage sprite (for visual feedback during mining)
        # Calculate health percent based on elapsed time
        health_percent = 1.0 - (elapsed_time / time_to_mine) if time_to_mine > 0 else 1.0
        if health_percent < 1.0:  # Only update if mining in progress
            # Store sprite state in deco_data for rendering
            if health_percent > 0.5:
                deco_data['sprite_state'] = 'default'
            elif health_percent > 0.1:
                deco_data['sprite_state'] = 'damaged_50'
            else:
                deco_data['sprite_state'] = 'stump'
        
        return False  # Mining in progress
    
    def get_equipped_tool(self) -> dict:
        """
        Get currently equipped tool (placeholder implementation).
        
        Returns:
            Tool dictionary with tool_type, tool_id, and mining_speed
        """
        # Placeholder: Return default tool (hand)
        # In future, this should check player's equipped tool from inventory
        return {
            'tool_type': 'hand',  # Default tool type
            'tool_id': None,  # No tool equipped (hand mining)
            'mining_speed': 10.0  # Legacy field, not used in new system
        }
    
    def update_tile_decorations(self, dt: float):
        """
        Update tile decorations (growth timers, regrowth, etc.).
        
        Args:
            dt: Delta time in seconds
        """
        if not self.world or not self.world.chunk_manager:
            return
        
        try:
            from world.decoration_registry import DecorationRegistry
            from world.decoration import Decoration
        except ImportError:
            return
        
        import time
        current_time = time.time()
        
        # Update decorations in all loaded chunks
        for chunk in self.world.chunk_manager.loaded_chunks.values():
            if not chunk.tiles:
                continue
            
            for tile_y in range(len(chunk.tiles)):
                if not chunk.tiles[tile_y]:
                    continue
                for tile_x in range(len(chunk.tiles[tile_y])):
                    tile = chunk.tiles[tile_y][tile_x]
                    if not tile:
                        continue
                    
                    decoration_data = tile.get('decoration')
                    if not decoration_data:
                        continue
                    
                    decoration_id = decoration_data.get('decoration_id')
                    if not decoration_id:
                        continue
                    
                    deco_config = DecorationRegistry.get(decoration_id)
                    if not deco_config:
                        continue
                    
                    decoration = Decoration(deco_config)
                    deco_data = decoration_data.get('data', {})
                    
                    # Update last_interaction timestamp
                    if 'last_interaction' in deco_data:
                        deco_data['last_interaction'] = current_time
                    
                    # Handle harvestable items (regrowth)
                    if decoration.is_harvestable():
                        growth_timer = deco_data.get('growth_timer', 0.0)
                        has_fruit = deco_data.get('has_fruit', True)
                        initial_growth_time = deco_data.get('initial_growth_time', 0.0)
                        
                        # Fallback: if initial_growth_time is missing but timer is running,
                        # set it to current growth_timer (for old save files)
                        if not has_fruit and growth_timer > 0.0 and initial_growth_time == 0.0:
                            deco_data['initial_growth_time'] = growth_timer
                            initial_growth_time = growth_timer
                        
                        if not has_fruit and growth_timer > 0.0:
                            # Decrease growth timer
                            growth_timer -= dt
                            deco_data['growth_timer'] = growth_timer
                            
                            # Check if regrown
                            if growth_timer <= 0.0:
                                deco_data['has_fruit'] = True
                                deco_data['growth_timer'] = 0.0
                                deco_data['initial_growth_time'] = 0.0
                                decoration.update_sprite('with_fruit')
                                # Mark chunk's decoration VBO as dirty (sprite changed)
                                if self.world_renderer:
                                    self.world_renderer.mark_decoration_chunk_dirty(chunk.chunk_x, chunk.chunk_y)
                    
                    # Handle stump removal timer (after mining complete)
                    if deco_data.get('is_stump', False):
                        stump_timer = deco_data.get('stump_timer', 0.0)
                        if stump_timer > 0.0:
                            stump_timer -= dt
                            deco_data['stump_timer'] = stump_timer
                            
                            # Remove decoration when timer expires
                            if stump_timer <= 0.0:
                                # Remove decoration
                                chunk.set_decoration_at(tile_x, tile_y, None, world_renderer=self.world_renderer)
                                if 'decoration' in tile:
                                    del tile['decoration']
                                # Rebuild decoration lookup after removal
                                chunk._rebuild_decoration_lookup()
                                # Mark chunk's decoration VBO as dirty (decoration removed)
                                if self.world_renderer:
                                    self.world_renderer.mark_decoration_chunk_dirty(chunk.chunk_x, chunk.chunk_y)
                                continue  # Skip to next tile
                    
                    # Handle animation updates (placeholder for Phase 6)
                    animation_config = decoration.get_animation_config()
                    if animation_config.get('enabled', False):
                        # Animation updates would go here (sway, pulse, glow, etc.)
                        pass
    
    def check_decoration_collision(self, x: float, y: float) -> bool:
        """
        Check if a position collides with any decoration.
        
        Args:
            x: World X coordinate in pixels
            y: World Y coordinate in pixels
            
        Returns:
            True if collision, False otherwise
        """
        if not self.world or not self.world.chunk_manager:
            return False
        
        try:
            from world.decoration_registry import DecorationRegistry
            from world.decoration import Decoration
        except ImportError:
            return False  # Decoration system not available
        
        # Convert pixel coordinates to tile coordinates
        tile_x = int(x // settings.TILE_SIZE)
        tile_y = int(y // settings.TILE_SIZE)
        
        # Get chunk coordinates
        chunk_x = tile_x // settings.CHUNK_SIZE
        chunk_y = tile_y // settings.CHUNK_SIZE
        
        # Get tile coordinates within chunk
        tile_x_in_chunk = tile_x % settings.CHUNK_SIZE
        tile_y_in_chunk = tile_y % settings.CHUNK_SIZE
        
        # Check if chunk is loaded
        chunk_key = (chunk_x, chunk_y)
        if chunk_key not in self.world.chunk_manager.loaded_chunks:
            return False
        
        chunk = self.world.chunk_manager.loaded_chunks[chunk_key]
        
        # Check decoration at this tile position
        decoration_data = chunk.get_decoration_at(tile_x_in_chunk, tile_y_in_chunk)
        if not decoration_data:
            return False
        
        decoration_id = decoration_data.get('decoration_id')
        if not decoration_id:
            return False
        
        # Get decoration config
        deco_config = DecorationRegistry.get(decoration_id)
        if not deco_config:
            return False
        
        decoration = Decoration(deco_config)
        
        # Check collision
        return decoration.check_collision(x, y, tile_x, tile_y)
    
    def _get_tile_under_mouse(self, mouse_x: int, mouse_y: int):
        """
        Get tile under mouse cursor if within 8 tiles of player.
        Returns tuple with flag indicating if decoration was clicked.
        
        Returns:
            Tuple of (tile_x, tile_y, tile_data, clicked_decoration) or None
            clicked_decoration: True if mouse is on decoration bounding box, False if on tile
        """
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
        
        if not self.world or not self.world.terrain_gen:
            return None
        
        tile_data = self.world.terrain_gen.generate_tile(tile_x, tile_y)
        
        # Load decoration data from chunk if available (generate_tile doesn't include decorations)
        if self.world and self.world.chunk_manager:
            chunk_x = tile_x // settings.CHUNK_SIZE
            chunk_y = tile_y // settings.CHUNK_SIZE
            chunk_key = (chunk_x, chunk_y)
            
            if chunk_key in self.world.chunk_manager.loaded_chunks:
                chunk = self.world.chunk_manager.loaded_chunks[chunk_key]
                tile_x_in_chunk = tile_x % settings.CHUNK_SIZE
                tile_y_in_chunk = tile_y % settings.CHUNK_SIZE
                
                # Get actual tile from chunk (includes decoration data)
                if (tile_y_in_chunk < len(chunk.tiles) and 
                    tile_x_in_chunk < len(chunk.tiles[tile_y_in_chunk])):
                    chunk_tile = chunk.tiles[tile_y_in_chunk][tile_x_in_chunk]
                    if chunk_tile:
                        # Merge decoration data from chunk into tile_data
                        if 'decoration' in chunk_tile:
                            tile_data['decoration'] = chunk_tile['decoration']
        
        # Check if mouse is on decoration bounding box
        clicked_decoration = self._is_point_on_decoration(world_x, world_y, tile_x, tile_y, tile_data)
        
        # Debug logging
        if self.diagnostics and self.enable_debug_output and tile_data.get('decoration'):
            decoration_id = tile_data.get('decoration', {}).get('decoration_id', 'unknown')
            self.diagnostics.debug("WorldController", 
                f"Mouse at ({mouse_x}, {mouse_y}) -> world ({world_x:.1f}, {world_y:.1f}) -> tile ({tile_x}, {tile_y}), "
                f"decoration={decoration_id}, clicked_decoration={clicked_decoration}")
        
        return (tile_x, tile_y, tile_data, clicked_decoration)
    
    def _is_point_on_decoration(self, world_x: float, world_y: float, tile_x: int, tile_y: int, tile_data: dict) -> bool:
        """
        Check if a world point is within a decoration's bounding box.
        
        Args:
            world_x: World X coordinate
            world_y: World Y coordinate
            tile_x: Tile X coordinate
            tile_y: Tile Y coordinate
            tile_data: Tile data dictionary
            
        Returns:
            True if point is on decoration bounding box, False otherwise
        """
        decoration_data = tile_data.get('decoration')
        if not decoration_data:
            return False
        
        try:
            from world.decoration_registry import DecorationRegistry
            from world.decoration import Decoration
        except ImportError:
            return False
        
        decoration_id = decoration_data.get('decoration_id')
        if not decoration_id:
            return False
        
        deco_config = DecorationRegistry.get(decoration_id)
        if not deco_config:
            return False
        
        decoration = Decoration(deco_config)
        rendering_config = decoration.get_rendering_config()
        
        # Get custom bounding box if available, otherwise use rendering size
        bounding_box = rendering_config.get('bounding_box')
        if bounding_box:
            # Custom bounding box: [width, height] in pixels
            bbox_width, bbox_height = bounding_box[0], bounding_box[1]
        else:
            # Fallback to rendering size
            size = rendering_config.get('size', [settings.TILE_SIZE, settings.TILE_SIZE])
            bbox_width, bbox_height = size[0], size[1]
        
        offset = rendering_config.get('offset', [0, 0])
        
        # Calculate tile center in world coordinates
        tile_world_x = tile_x * settings.TILE_SIZE
        tile_world_y = tile_y * settings.TILE_SIZE
        tile_center_x = tile_world_x + settings.TILE_SIZE / 2.0
        tile_center_y = tile_world_y + settings.TILE_SIZE / 2.0
        
        # Calculate decoration bounding box
        # Bounding box is centered on tile + offset
        deco_x = tile_center_x + offset[0] - bbox_width / 2.0
        deco_y = tile_center_y + offset[1] - bbox_height / 2.0
        deco_max_x = deco_x + bbox_width
        deco_max_y = deco_y + bbox_height
        
        # Check if point is within decoration bounding box
        return (deco_x <= world_x <= deco_max_x and deco_y <= world_y <= deco_max_y)
    
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
    
    def _reset_mining_timer(self, tile_x: int, tile_y: int):
        """
        Reset mining timer for a decoration at the given tile position.
        Called when mining is aborted (mouse moved away, button released, etc.).
        
        Args:
            tile_x: Tile X coordinate
            tile_y: Tile Y coordinate
        """
        if not self.world or not self.world.chunk_manager:
            return
        
        try:
            # Get chunk coordinates
            chunk_x = tile_x // settings.CHUNK_SIZE
            chunk_y = tile_y // settings.CHUNK_SIZE
            
            # Get tile coordinates within chunk
            tile_x_in_chunk = tile_x % settings.CHUNK_SIZE
            tile_y_in_chunk = tile_y % settings.CHUNK_SIZE
            
            # Check if chunk is loaded
            chunk_key = (chunk_x, chunk_y)
            if chunk_key not in self.world.chunk_manager.loaded_chunks:
                return
            
            chunk = self.world.chunk_manager.loaded_chunks[chunk_key]
            
            # Get decoration at this tile position
            decoration_data = chunk.get_decoration_at(tile_x_in_chunk, tile_y_in_chunk)
            if not decoration_data:
                return
            
            # Reset elapsed_time in decoration data
            if 'data' not in decoration_data:
                decoration_data['data'] = {}
            deco_data = decoration_data['data']
            
            # Reset mining progress
            if 'elapsed_time' in deco_data:
                deco_data['elapsed_time'] = 0.0
            
            # Reset sprite state if it was set during mining
            if 'sprite_state' in deco_data and deco_data.get('sprite_state') in ['damaged_50', 'stump']:
                # Only reset if not a stump (stumps should remain until timer expires)
                if not deco_data.get('is_stump', False):
                    deco_data['sprite_state'] = None
                    # Remove sprite_state key if it's None
                    if deco_data.get('sprite_state') is None:
                        deco_data.pop('sprite_state', None)
        except Exception as e:
            if self.diagnostics and self.enable_debug_output:
                self.diagnostics.warning("WorldController", f"Error resetting mining timer at ({tile_x}, {tile_y}): {e}")
    
    def cleanup(self):
        """Cleanup resources"""
        if self.auto_save:
            self.auto_save.stop(final_save=False)
        if self.world:
            self.world.cleanup()
