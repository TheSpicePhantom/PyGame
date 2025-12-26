"""
Hauptdatei: Startet das Top-Down Factorio-Style Spiel (pyglet + ModernGL)
"""
import pyglet
from pyglet.window import key, mouse
import moderngl
import os
import time
import math
import numpy as np
from core import settings
# from core.input import InputHandler  # Pygame version
from core.input_pyglet import InputHandler  # Pyglet version
from world.world import World
from combat.player import Player
from factory.recipes import load_recipes
from core.camera import Camera
from ui.pause_menu import PauseMenu
from ui.settings_menu import SettingsMenu
from ui.audio_settings import AudioSettings
from ui.graphics_settings import GraphicsSettings
from ui.controls_settings import ControlsSettings
from ui.save_menu import SaveMenu
from ui.world_select_menu import WorldSelectMenu
from ui.create_world_menu import CreateWorldMenu
from ui.inventory_menu import InventoryMenu
from ui.hotbar_overlay import HotbarOverlay
from world.player_data_manager import PlayerDataManager
from world.auto_save import AutoSaveSystem
from analytics.diagnostics_service import DiagnosticsService
from view.modern_gl_renderer import ModernGLRenderer
from core.game_app import GameApp
from core.game_state import GameState
from core.world_controller import WorldController
from core.ui_controller import UIController
from view.world_renderer import WorldRenderer
from view.ui_renderer import UIRenderer
from view.debug_renderer import DebugRenderer
import moderngl

def get_desktop_resolution():
    """Get desktop resolution using OS-specific method"""
    if os.name == 'nt':  # Windows
        try:
            import ctypes
            user32 = ctypes.windll.user32
            return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        except:
            pass
    
    # Fallback: Use default resolution
    return 1920, 1080

class GameWindow(pyglet.window.Window):
    """Haupt-Fenster-Klasse mit ModernGL"""
    
    def __init__(self):
        # Load display mode from settings
        from config.settings_manager import settings_manager
        settings_manager.load_settings()
        initial_mode = settings_manager.graphics.get('display_mode', 'windowed')
        
        # Get screen size
        desktop_width, desktop_height = get_desktop_resolution()
        default_width = 1920
        default_height = 1080
        
        # Set window size based on mode
        if initial_mode == "fullscreen":
            width, height = desktop_width, desktop_height
            fullscreen = True
        elif initial_mode == "fullscreen_window":
            width, height = desktop_width, desktop_height
            fullscreen = False
            # TODO: Implement borderless fullscreen
        else:  # windowed
            width, height = default_width, default_height
            fullscreen = False
        
        # Create window with V-Sync enabled for consistent frame rate
        super().__init__(width=width, height=height, caption="PyGame - Factorio Style", fullscreen=fullscreen, vsync=True)
        
        # Center window if windowed
        if not fullscreen:
            self.set_location(
                (desktop_width - width) // 2,
                (desktop_height - height) // 2
            )
        
        # Update settings
        settings.SCREEN_WIDTH = width
        settings.SCREEN_HEIGHT = height
        
        # Initialize ModernGL context
        self.ctx = moderngl.create_context()
        
        # Initialize diagnostics service (performance monitoring + logging) early for logging
        self.diagnostics = DiagnosticsService(enable_logging=True, log_to_file=True)
        self.diagnostics.info("Main", f"ModernGL context created successfully")
        self.diagnostics.info("Main", f"OpenGL version: {self.ctx.info.get('GL_VERSION', 'unknown')}")
        
        # Create ModernGL renderer (with pyglet coordinate system)
        self.modern_gl_renderer = ModernGLRenderer(self.ctx, width, height, use_pyglet=True, diagnostics=self.diagnostics)
        self.diagnostics.info("Main", "Using ModernGL for GPU-accelerated rendering (pyglet mode)")
        self.diagnostics.info("Main", "Performance monitoring enabled")
        
        # Load recipes
        load_recipes()
        self.diagnostics.info("Main", "Loaded recipes from JSON")
        
        # Initialize input handler
        self.input_handler = InputHandler(self)
        
        # Initialize controllers
        self.world_controller = WorldController(
            input_handler=self.input_handler,
            performance_monitor=self.diagnostics.get_performance_monitor(),
            modern_gl_renderer=self.modern_gl_renderer,
            width=width,
            height=height,
            diagnostics=self.diagnostics
        )
        
        self.ui_controller = UIController(
            width=width,
            height=height,
            modern_gl_renderer=self.modern_gl_renderer,
            performance_monitor=self.diagnostics.get_performance_monitor()
        )
        
        # Initialize game app (state machine)
        self.game_app = GameApp(
            world_controller=self.world_controller,
            ui_controller=self.ui_controller,
            find_next_available_slot_func=self._find_next_available_slot,
            diagnostics=self.diagnostics
        )
        
        # Initialize renderers
        self.world_renderer = WorldRenderer(
            world_controller=self.world_controller,
            modern_gl_renderer=self.modern_gl_renderer
        )
        
        self.ui_renderer = UIRenderer(
            ui_controller=self.ui_controller
        )
        
        self.debug_renderer = DebugRenderer(
            world_controller=self.world_controller,
            ui_controller=self.ui_controller,
            performance_monitor=self.diagnostics.get_performance_monitor(),
            modern_gl_renderer=self.modern_gl_renderer,
            width=width,
            height=height
        )
        
        # FPS limiting flag
        self._update_called = False
        
        # Schedule update loop at 120 FPS (8.33ms per frame)
        pyglet.clock.schedule_interval(self.update, 1.0 / 120.0)
        
        self.diagnostics.info("Main", f"Window created: {width}x{height}, mode: {initial_mode}")
    
    def _find_next_available_slot(self) -> int:
        """Find next available save slot number"""
        from pathlib import Path
        saves_dir = Path("saves")
        if not saves_dir.exists():
            return 1
        
        # Find highest slot number
        max_slot = 0
        for save_dir in saves_dir.iterdir():
            if save_dir.is_dir() and save_dir.name.startswith("slot_"):
                try:
                    slot_num = int(save_dir.name.split("_")[1])
                    max_slot = max(max_slot, slot_num)
                except (ValueError, IndexError):
                    pass
        
        return max_slot + 1
    
    def _convert_inventory_format(self, inventory: dict) -> dict:
        """
        Convert old inventory format (dict) to new slot-based format
        
        Args:
            inventory: Old format dict or new format dict
            
        Returns:
            New format dict with 'slots' and 'size_rows'
        """
        # If already in new format, return as-is
        if isinstance(inventory, dict) and 'slots' in inventory:
            return inventory
        
        # Convert old format to new format
        slots = [[None for _ in range(9)] for _ in range(6)]
        
        if isinstance(inventory, dict):
            # Old format: {'item_id': amount, ...}
            slot_index = 0
            for item_id, amount in inventory.items():
                if slot_index < 54:  # 9 * 6 = 54 slots
                    row = slot_index // 9
                    col = slot_index % 9
                    slots[row][col] = {'item_id': item_id, 'amount': amount}
                    slot_index += 1
        
        return {
            'slots': slots,
            'size_rows': 5  # Default inventory size
        }
    
    def _find_traversable_spawn_position(self, start_x: float, start_y: float) -> tuple:
        """
        Find nearest traversable position starting from given coordinates.
        Uses spiral search pattern to find closest traversable tile.
        
        Args:
            start_x: Starting X coordinate in pixels
            start_y: Starting Y coordinate in pixels
            
        Returns:
            (x, y) tuple of traversable position in pixels
        """
        from core import settings
        
        # Convert pixel coordinates to tile coordinates
        start_tile_x = int(start_x // settings.TILE_SIZE)
        start_tile_y = int(start_y // settings.TILE_SIZE)
        
        # Check if starting position is traversable
        tile = self.world.terrain_gen.generate_tile(start_tile_x, start_tile_y)
        if tile.get('traversable', True):
            return (start_x, start_y)
        
        # Spiral search for nearest traversable tile
        max_search_radius = 50  # Maximum tiles to search in each direction
        for radius in range(1, max_search_radius + 1):
            # Check all tiles in a square around the start position
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    # Only check tiles on the edge of the current radius
                    if abs(dx) == radius or abs(dy) == radius:
                        check_tile_x = start_tile_x + dx
                        check_tile_y = start_tile_y + dy
                        
                        tile = self.world.terrain_gen.generate_tile(check_tile_x, check_tile_y)
                        if tile.get('traversable', True):
                            # Found traversable tile - convert back to pixel coordinates
                            found_x = check_tile_x * settings.TILE_SIZE + settings.TILE_SIZE / 2.0
                            found_y = check_tile_y * settings.TILE_SIZE + settings.TILE_SIZE / 2.0
                            return (found_x, found_y)
        
        # Fallback: return original position if no traversable tile found
        if self.diagnostics:
            self.diagnostics.warning("Main", f"Could not find traversable position near ({start_x:.0f}, {start_y:.0f}), using original position")
        return (start_x, start_y)
    
    def _initialize_game(self, save_slot=1, world_name=None, seed=None):
        """Initialize game components"""
        # Sprite-Gruppen (ohne Pygame)
        from core.sprite import LayeredUpdates, SpriteGroup
        self.all_sprites = LayeredUpdates()
        self.resource_sprites = SpriteGroup()
        self.building_sprites = SpriteGroup()
        
        # Welt erstellen
        self.world = World(
            self.all_sprites, 
            self.resource_sprites, 
            save_slot=save_slot, 
            seed=seed,
            performance_monitor=self.performance_monitor
        )
        
        # Set world name if provided
        if world_name:
            self.world.chunk_manager.set_world_name(world_name)
        
        # Initialize PlayerDataManager
        self.player_data_manager = PlayerDataManager(save_slot)
        
        # Load player data from save (required - no fallback to default spawn)
        player_data = self.player_data_manager.load_player()
        
        if not player_data:
            # No save exists - create initial save at world center
            if self.diagnostics:
                self.diagnostics.info("Main", f"No existing player data found for slot {save_slot}, creating initial save...")
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
                raise RuntimeError(f"Failed to create initial player data for slot {save_slot}")
        
        # Extract player data from save
        spawn_pos = self.player_data_manager.get_spawn_position()
        if not spawn_pos:
            raise RuntimeError(f"Failed to get spawn position from save slot {save_slot}")
        
        # Check if spawn position is traversable, if not find nearest traversable position
        start_world_x, start_world_y = self._find_traversable_spawn_position(spawn_pos[0], spawn_pos[1])
        
        # Update spawn position if it was changed
        if (start_world_x, start_world_y) != spawn_pos:
            if self.diagnostics:
                self.diagnostics.info("Main", f"Spawn position adjusted from {spawn_pos} to ({start_world_x:.0f}, {start_world_y:.0f}) - original was not traversable")
            # Update saved position to traversable position
            # Preserve inventory_size and multipliers from existing data
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
            self.diagnostics.info("Main", f"Loaded player data from save slot {save_slot}")
            self.diagnostics.info("Main", f"Player spawn position: ({start_world_x:.0f}, {start_world_y:.0f})")
            if isinstance(player_inventory, dict) and 'slots' in player_inventory:
                # Count items in slots
                item_count = sum(1 for row in player_inventory.get('slots', []) for slot in row if slot is not None)
                self.diagnostics.info("Main", f"Player inventory: {item_count} items in slots")
            else:
                self.diagnostics.info("Main", f"Player inventory: {len(player_inventory)} items (old format)")
            self.diagnostics.info("Main", f"Player faction: {len(player_faction.get('policies', []))} policies")
        
        # Get sprint and sneak multipliers from player data
        sprint_multiplier = player_data.get('sprint_multiplier', 1.2)
        sneak_multiplier = player_data.get('sneak_multiplier', 0.8)
        
        # Player erstellen mit Daten aus PlayerDataManager
        self.player = Player(
            pos=(start_world_x, start_world_y),
            input_handler=self.input_handler,
            performance_monitor=self.performance_monitor,
            terrain_gen=self.world.terrain_gen,  # Pass terrain generator for traversability checks
            sprint_multiplier=sprint_multiplier,
            sneak_multiplier=sneak_multiplier
        )
        
        # Set player inventory and faction from save
        self.player.inventory = player_inventory
        self.player.faction = player_faction
        
        # Initialize inventory menu with player inventory data
        if hasattr(self, 'inventory_menu'):
            # Convert old inventory format to new slot-based format if needed
            inventory_data = self._convert_inventory_format(player_inventory)
            # Get inventory_size from top-level player data (not from inventory dict)
            inventory_size = player_data.get('inventory_size', 45)
            inventory_data['inventory_size'] = inventory_size
            self.inventory_menu.set_inventory(inventory_data)
        
        self.all_sprites.add(self.player, layer=settings.LAYER_PLAYER)
        
        # Kamera initialisieren
        self.camera = Camera(target=self.player, lerp_speed=settings.CAMERA_LERP_SPEED)
        # Set camera position immediately to player position (no lerp delay on start)
        self.camera.x = start_world_x
        self.camera.y = start_world_y
        # Zoom: 1.5 = 150% (nah), 0.75 = 75% (weit weg)
        self.camera_zoom = 1.0  # Start at 100%
        
        # Mouse position tracking for tile highlight
        self.mouse_x = 0
        self.mouse_y = 0
        
        # Initialize Auto-Save System
        def get_player_position():
            """Get current player position for auto-save"""
            if self.player:
                return (self.player.rect.x, self.player.rect.y)
            return (0, 0)
        
        def get_game_state():
            """Get current game state for auto-save"""
            return {
                'can_save': self.game_initialized and not self._is_menu_active(),
                'is_paused': self.pause_menu and self.pause_menu.active if self.pause_menu else False,
                'menu_active': self._is_menu_active()
            }
        
        def save_game():
            """Save game callback for auto-save"""
            if not self.game_initialized or not self.world or not self.player:
                return
            
            try:
                # Save world (chunks are saved automatically by ChunkManager)
                # Save player data using the instance variable
                if hasattr(self, 'player_data_manager') and self.player_data_manager:
                    # Get inventory_size from inventory menu if available
                    inventory_size = None
                    if hasattr(self, 'inventory_menu') and self.inventory_menu:
                        inventory_size = self.inventory_menu.inventory_size
                    # Get sprint and sneak multipliers from player
                    sprint_multiplier = getattr(self.player, 'sprint_multiplier', 1.2)
                    sneak_multiplier = getattr(self.player, 'sneak_multiplier', 0.8)
                    self.player_data_manager.save_player(
                        position=(self.player.rect.x, self.player.rect.y),
                        inventory=getattr(self.player, 'inventory', {}),
                        faction_data=getattr(self.player, 'faction', {'policies': [], 'allies': [], 'enemies': []}),
                        inventory_size=inventory_size,
                        sprint_multiplier=sprint_multiplier,
                        sneak_multiplier=sneak_multiplier
                    )
                    if self.diagnostics:
                        self.diagnostics.info("Main", f"Game saved (slot {save_slot})")
                else:
                    if self.diagnostics:
                        self.diagnostics.warning("Main", "PlayerDataManager not available for saving")
            except Exception as e:
                if self.diagnostics:
                    self.diagnostics.error("Main", f"Error saving game: {e}")
                raise
        
        self.auto_save = AutoSaveSystem(
            save_callback=save_game,
            get_player_pos=get_player_position,
            get_game_state=get_game_state
        )
        self.auto_save.start()
        
        # Mark game as initialized
        self.game_initialized = True
        
        # Log spawn information
        if self.diagnostics:
            self.diagnostics.info("Main", f"Game initialized - Player spawned at position ({start_world_x:.0f}, {start_world_y:.0f})")
            
            # Log spawn chunk for debugging
            spawn_chunk = self.player_data_manager.get_spawn_chunk()
            if spawn_chunk:
                self.diagnostics.info("Main", f"Player spawn chunk: {spawn_chunk}")
    
    def update(self, dt):
        """Update game logic"""
        # Mark that update was called (for FPS limiting)
        self._update_called = True
        
        # Update input handler
        if self.input_handler:
            self.input_handler.update()
        
        # Delegate update to game app
        self.game_app.update(dt)
    
    def on_draw(self):
        """Render frame"""
        # FPS limiting: Only render if update was called (limits to 120 FPS)
        # schedule_interval calls update() at 120 FPS, so we only render when update runs
        if not self._update_called:
            return
        
        self._update_called = False  # Reset flag for next frame
        
        self.diagnostics.start_frame()
        self.diagnostics.start_render()
        
        # Set viewport (important!)
        self.ctx.viewport = (0, 0, self.width, self.height)
        
        # Clear screen with normal background color
        bg_color = settings.COLOR_BG
        self.ctx.clear(bg_color[0]/255.0, bg_color[1]/255.0, bg_color[2]/255.0)
        
        # Enable blending and disable depth test (like proof-of-concept)
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.ctx.disable(moderngl.DEPTH_TEST)
        
        # Debug: Render a hardcoded quad directly in clip space (no transformations)
        if not hasattr(self, '_clip_space_test_setup'):
            # Simple shader that outputs clip space directly
            simple_vertex_shader = """
            #version 330 core
            in vec2 in_position;
            in vec3 in_color;
            out vec3 frag_color;
            void main() {
                gl_Position = vec4(in_position, 0.0, 1.0);
                frag_color = in_color;
            }
            """
            
            simple_fragment_shader = """
            #version 330 core
            in vec3 frag_color;
            out vec4 out_color;
            void main() {
                out_color = vec4(frag_color / 255.0, 1.0);
            }
            """
            
            try:
                self._clip_test_program = self.ctx.program(
                    vertex_shader=simple_vertex_shader,
                    fragment_shader=simple_fragment_shader
                )
                
                # Hardcoded quad in clip space (-1 to 1)
                # Green quad left of center: from (-0.2, -0.1) to (0.0, 0.1)
                # NDC: (-1,-1) bottom-left, (1,1) top-right
                # Center is at (0, 0)
                clip_vertices = np.array([
                    [-0.2, -0.1, 0.0, 255.0, 0.0],  # Green - bottom-left
                    [0.0, -0.1, 0.0, 255.0, 0.0],   # Green - bottom-right
                    [0.0, 0.1, 0.0, 255.0, 0.0],    # Green - top-right
                    [-0.2, -0.1, 0.0, 255.0, 0.0],  # Green - bottom-left
                    [0.0, 0.1, 0.0, 255.0, 0.0],    # Green - top-right
                    [-0.2, 0.1, 0.0, 255.0, 0.0],   # Green - top-left
                ], dtype=np.float32)
                
                self._clip_test_vbo = self.ctx.buffer(clip_vertices.tobytes())
                self._clip_test_vao = self.ctx.simple_vertex_array(
                    self._clip_test_program,
                    self._clip_test_vbo,
                    'in_position', 'in_color'
                )
                
                # Clip-space test quad setup complete
                self._clip_space_test_setup = True
            except Exception as e:
                if self.diagnostics:
                    self.diagnostics.error("Main", f"Error setting up clip-space test: {e}")
                else:
                    import traceback
                    traceback.print_exc()
        
        # Render clip-space test quad every frame (DISABLED to see chunks)
        # if hasattr(self, '_clip_test_vao'):
        #     self._clip_test_vao.render(moderngl.TRIANGLES)
        
        # Debug: Render yellow quad directly in clip-space (same as green quad) - EVERY FRAME
        if not hasattr(self, '_yellow_quad_setup'):
            # Use the same simple shader as the green quad
            simple_vertex_shader = """
            #version 330 core
            in vec2 in_position;
            in vec3 in_color;
            out vec3 frag_color;
            void main() {
                gl_Position = vec4(in_position, 0.0, 1.0);
                frag_color = in_color;
            }
            """
            
            simple_fragment_shader = """
            #version 330 core
            in vec3 frag_color;
            out vec4 out_color;
            void main() {
                out_color = vec4(frag_color / 255.0, 1.0);
            }
            """
            
            try:
                self._yellow_program = self.ctx.program(
                    vertex_shader=simple_vertex_shader,
                    fragment_shader=simple_fragment_shader
                )
                
                # Yellow quad right of center: from (0.0, -0.1) to (0.2, 0.1)
                # NDC: (-1,-1) bottom-left, (1,1) top-right
                # Center is at (0, 0)
                yellow_vertices = np.array([
                    [0.0, -0.1, 255.0, 255.0, 0.0],  # Yellow - bottom-left
                    [0.2, -0.1, 255.0, 255.0, 0.0],  # Yellow - bottom-right
                    [0.2, 0.1, 255.0, 255.0, 0.0],   # Yellow - top-right
                    [0.0, -0.1, 255.0, 255.0, 0.0],  # Yellow - bottom-left
                    [0.2, 0.1, 255.0, 255.0, 0.0],   # Yellow - top-right
                    [0.0, 0.1, 255.0, 255.0, 0.0],   # Yellow - top-left
                ], dtype=np.float32)
                
                self._yellow_vbo = self.ctx.buffer(yellow_vertices.tobytes())
                self._yellow_vao = self.ctx.simple_vertex_array(
                    self._yellow_program,
                    self._yellow_vbo,
                    'in_position', 'in_color'
                )
                
                # Yellow quad setup complete
                self._yellow_quad_setup = True
            except Exception as e:
                if self.diagnostics:
                    self.diagnostics.error("Main", f"Error setting up yellow quad: {e}")
                else:
                    import traceback
                    traceback.print_exc()
        
        # Rendering-Pipeline: World -> Debug -> UI -> Performance Stats
        current_state = self.game_app.current_state
        
        # 1. Render world (chunks, player) - only if in game
        if current_state == GameState.INGAME or current_state == GameState.PAUSED:
            self.world_renderer.draw(debug_visualization_mode=0)  # Debug handled separately
            
            # Render tile highlight if in game
            if current_state == GameState.INGAME and self.world_controller.player:
                self.world_renderer.draw_tile_highlight(
                    mouse_x=self.world_controller.mouse_x,
                    mouse_y=self.world_controller.mouse_y,
                    screen_width=self.width,
                    screen_height=self.height
                )
        
        # 2. Render debug visualization (chunk boundaries, tile grids)
        if current_state == GameState.INGAME or current_state == GameState.PAUSED:
            debug_mode = self.ui_controller.debug_visualization_mode
            if debug_mode > 0:
                chunks_data = self.world_renderer.get_chunks_data()
                self.debug_renderer.draw_debug_visualization(chunks_data, debug_mode)
        
        # 3. Render UI (menus, hotbar, overlays)
        self.ui_renderer.draw(current_state)
        
        # 4. Render performance stats overlay
        self.debug_renderer.draw_performance_stats(current_state)
        
        self.diagnostics.end_render()
    
    def _load_visible_chunks(self, camera_x: float, camera_y: float):
        """Load chunks in visible area + buffer based on zoom
        
        This ensures that all chunks visible on screen (accounting for zoom) are loaded.
        - Zoom 0.75 (herausgezoomt): Mehr Welt sichtbar -> mehr Chunks geladen
        - Zoom 1.5 (herangezoomt): Weniger Welt sichtbar -> weniger Chunks geladen
        """
        if not self.world_controller.world or not self.world_controller.world.chunk_manager:
            return
        
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        screen_width = self.modern_gl_renderer.screen_width
        screen_height = self.modern_gl_renderer.screen_height
        
        # Calculate visible area in world coordinates (accounting for zoom)
        # With zoom, we see more/less world: visible_world_size = screen_size / zoom
        # Zoom < 1.0 = rauszoomen = mehr Welt sichtbar = größere visible_world_size
        # Zoom > 1.0 = reinzoomen = weniger Welt sichtbar = kleinere visible_world_size
        visible_world_width = screen_width / self.world_controller.camera_zoom
        visible_world_height = screen_height / self.world_controller.camera_zoom
        
        # Calculate visible area bounds in world coordinates
        # Camera is at screen center, so visible area is centered on camera
        world_min_x = camera_x - visible_world_width / 2.0
        world_max_x = camera_x + visible_world_width / 2.0
        world_min_y = camera_y - visible_world_height / 2.0
        world_max_y = camera_y + visible_world_height / 2.0
        
        # Add buffer to ensure edge chunks are loaded (reduced buffer for aggressiveres culling)
        buffer_pixels = chunk_size_pixels * 1.0  # 1.0 chunks buffer (reduced from 1.5)
        world_min_x -= buffer_pixels
        world_max_x += buffer_pixels
        world_min_y -= buffer_pixels
        world_max_y += buffer_pixels
        
        # Convert to chunk coordinates
        # Use floor for min to include chunks that start before world_min
        # Use ceil for max to include chunks that extend beyond world_max
        chunk_min_x = int(math.floor(world_min_x / chunk_size_pixels))
        chunk_max_x = int(math.ceil(world_max_x / chunk_size_pixels))
        chunk_min_y = int(math.floor(world_min_y / chunk_size_pixels))
        chunk_max_y = int(math.ceil(world_max_y / chunk_size_pixels))
        
        
        # Load all chunks in visible area + buffer
        chunks_to_load = set()
        chunks_out_of_bounds = 0
        for chunk_x in range(chunk_min_x, chunk_max_x + 1):
            for chunk_y in range(chunk_min_y, chunk_max_y + 1):
                # Check world bounds
                if (0 <= chunk_x < settings.WORLD_SIZE_CHUNKS and
                    0 <= chunk_y < settings.WORLD_SIZE_CHUNKS):
                    chunks_to_load.add((chunk_x, chunk_y))
                else:
                    chunks_out_of_bounds += 1
        
        # Request async loading for chunks that aren't already loaded
        # Chunks will be processed via process_loaded_chunks in update loop
        chunk_manager = self.world_controller.world.chunk_manager
        camera_chunk_x = int(camera_x // chunk_size_pixels)
        camera_chunk_y = int(camera_y // chunk_size_pixels)
        
        newly_requested = 0
        already_loaded = 0
        for chunk_x, chunk_y in chunks_to_load:
            chunk_key = (chunk_x, chunk_y)
            if chunk_key not in chunk_manager.loaded_chunks:
                if chunk_key not in chunk_manager.pending_chunks:
                    # Calculate priority based on distance from camera
                    dx = abs(chunk_x - camera_chunk_x)
                    dy = abs(chunk_y - camera_chunk_y)
                    distance = dx + dy
                    chunk_manager.request_chunk_load(chunk_x, chunk_y, priority=distance)
                    newly_requested += 1
            else:
                already_loaded += 1
        
        # Mark chunks in visible area as "visible" (in view field)
        # First, reset states for chunks not in visible area
        for chunk_key, chunk in list(chunk_manager.loaded_chunks.items()):
            if chunk_key not in chunks_to_load:
                # Chunk is loaded but not in visible area
                if chunk.render_state not in ["rendering", "rendered", "active"]:
                    chunk.render_state = "inactive"
        
        # Mark chunks in visible area as "visible"
        visible_marked = 0
        for chunk_x, chunk_y in chunks_to_load:
            chunk_key = (chunk_x, chunk_y)
            if chunk_key in chunk_manager.loaded_chunks:
                chunk = chunk_manager.loaded_chunks[chunk_key]
                # Only set to "visible" if not already in a rendering state
                if chunk.render_state not in ["rendering", "rendered", "active"]:
                    chunk.render_state = "visible"
                    visible_marked += 1
        
        # Unload chunks that are too far away (optional, for memory management)
        # Keep a larger buffer to avoid frequent loading/unloading
        unload_distance = max(chunk_max_x - chunk_min_x, chunk_max_y - chunk_min_y) + 3
        player_chunk_x = int(camera_x // chunk_size_pixels)
        player_chunk_y = int(camera_y // chunk_size_pixels)
        
        chunks_to_unload = []
        for chunk_key, chunk in list(chunk_manager.loaded_chunks.items()):
            chunk_x, chunk_y = chunk_key
            distance = max(abs(chunk_x - player_chunk_x), abs(chunk_y - player_chunk_y))
            if distance > unload_distance:
                chunks_to_unload.append(chunk_key)
        
        for chunk_key in chunks_to_unload:
            chunk_manager.unload_chunk(chunk_key[0], chunk_key[1])
    
    def _update_performance_stats(self):
        """Update performance statistics"""
        # Stats are automatically logged by DiagnosticsService
        pass
    
    def _draw_performance_stats(self):
        """Draw performance statistics on screen (F3 menu) - top left corner"""
        stats = self.diagnostics.get_stats()
        
        # Position: top left corner
        # In pyglet, Y=0 is bottom, Y=height is top
        # We render from top to bottom, so start at height and decrease
        y_start = self.height - 5  # Start 5px from top (closer to corner)
        line_height = 28  # Increased line spacing to prevent overlap (20pt font + 8pt spacing)
        x_pos = 5  # 5px from left edge (closer to corner)
        font_size = 20  # 20pt font
        text_color = (0, 0, 0)  # Black text
        
        # === PERFORMANCE ===
        # FPS
        fps_current = stats['fps']['current']
        self.modern_gl_renderer.render_text(
            f"FPS: {fps_current:.1f}",
            x=x_pos,
            y=y_start,
            size=font_size,
            color=text_color
        )
        y_start -= line_height
        
        # CPU Usage
        cpu_current = stats['cpu_usage']['current']
        self.modern_gl_renderer.render_text(
            f"CPU: {cpu_current:.1f}%",
            x=x_pos,
            y=y_start,
            size=font_size,
            color=text_color
        )
        y_start -= line_height
        
        # GPU Usage
        gpu_current = stats['gpu_usage']['current']
        self.modern_gl_renderer.render_text(
            f"GPU: {gpu_current:.1f}%",
            x=x_pos,
            y=y_start,
            size=font_size,
            color=text_color
        )
        y_start -= line_height
        
        # === WORLD INFO ===
        # Seed
        if self.world_controller.world and self.world_controller.world.chunk_manager:
            seed = self.world_controller.world.chunk_manager.get_seed()
            if seed is None and hasattr(self.world_controller.world, 'terrain_gen'):
                seed = self.world_controller.world.terrain_gen.seed
            seed_text = f"Seed: {seed}" if seed is not None else "Seed: N/A"
            self.modern_gl_renderer.render_text(
                seed_text,
                x=x_pos,
                y=y_start,
                size=font_size,
                color=text_color
            )
            y_start -= line_height
        
        # Visible Chunks
        if self.world_controller.world and self.world_controller.world.chunk_manager:
            total_loaded = len(self.world_controller.world.chunk_manager.loaded_chunks)
            
            # Count visible chunks (chunks that are on screen)
            visible_chunks = 0
            if self.world_controller.camera:
                chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
                # Calculate visible area in world coordinates
                screen_width = self.width
                screen_height = self.height
                
                # World coordinates of screen corners (accounting for zoom)
                world_min_x = self.world_controller.camera.x - (screen_width / 2.0) / self.world_controller.camera_zoom
                world_max_x = self.world_controller.camera.x + (screen_width / 2.0) / self.world_controller.camera_zoom
                world_min_y = self.world_controller.camera.y - (screen_height / 2.0) / self.world_controller.camera_zoom
                world_max_y = self.world_controller.camera.y + (screen_height / 2.0) / self.world_controller.camera_zoom
                
                # Count chunks in visible area
                for chunk in self.world_controller.world.chunk_manager.loaded_chunks.values():
                    chunk_world_x = chunk.chunk_x * chunk_size_pixels
                    chunk_world_y = chunk.chunk_y * chunk_size_pixels
                    chunk_world_x2 = chunk_world_x + chunk_size_pixels
                    chunk_world_y2 = chunk_world_y + chunk_size_pixels
                    
                    # Check if chunk overlaps with visible area
                    if not (chunk_world_x2 < world_min_x or chunk_world_x > world_max_x or
                            chunk_world_y2 < world_min_y or chunk_world_y > world_max_y):
                        visible_chunks += 1
            
            self.modern_gl_renderer.render_text(
                f"Chunks: {visible_chunks}/{total_loaded} visible",
                x=x_pos,
                y=y_start,
                size=font_size,
                color=text_color
            )
            y_start -= line_height
            
            # Open Regions
            if hasattr(self.world_controller.world.chunk_manager, 'region_manager'):
                open_regions = len(self.world_controller.world.chunk_manager.region_manager.region_files)
                self.modern_gl_renderer.render_text(
                    f"Regions: {open_regions} open",
                    x=x_pos,
                    y=y_start,
                    size=font_size,
                    color=text_color
                )
                y_start -= line_height
        
        # === SAVE/LOAD STATS ===
        # Chunk Loads
        chunk_loads = stats.get('chunk_load_count', 0)
        chunk_generations = stats.get('chunk_generation_count', 0)
        chunk_saves = stats.get('chunk_save_count', 0)
        self.modern_gl_renderer.render_text(
            f"Loads: {chunk_loads} | Gen: {chunk_generations} | Saves: {chunk_saves}",
            x=x_pos,
            y=y_start,
            size=font_size,
            color=text_color
        )
        y_start -= line_height
        
        # === AUTO-SAVE STATUS ===
        if self.world_controller.auto_save:
            auto_save_enabled = self.world_controller.auto_save.is_enabled()
            auto_save_running = self.world_controller.auto_save.running
            auto_save_interval = self.world_controller.auto_save.get_interval()
            
            # Calculate time until next save
            time_until_save = "N/A"
            if auto_save_running and hasattr(self.world_controller.auto_save, 'last_save_time'):
                elapsed = time.time() - self.world_controller.auto_save.last_save_time
                remaining = max(0, auto_save_interval - elapsed)
                time_until_save = f"{remaining:.0f}s"
            
            status_text = "ON" if (auto_save_enabled and auto_save_running) else "OFF"
            self.modern_gl_renderer.render_text(
                f"Auto-Save: {status_text} ({auto_save_interval:.0f}s, next: {time_until_save})",
                x=x_pos,
                y=y_start,
                size=font_size,
                color=text_color
            )
            y_start -= line_height
        
        # === CAMERA ===
        # Player Position
        if self.world_controller.player:
            self.modern_gl_renderer.render_text(
                f"Pos: ({self.world_controller.player.rect.x:.0f}, {self.world_controller.player.rect.y:.0f})",
                x=x_pos,
                y=y_start,
                size=font_size,
                color=text_color
            )
            y_start -= line_height
        
        # Camera Position
        if self.world_controller.camera:
            self.modern_gl_renderer.render_text(
                f"Camera: ({self.world_controller.camera.x:.0f}, {self.world_controller.camera.y:.0f})",
                x=x_pos,
                y=y_start,
                size=font_size,
                color=text_color
            )
            y_start -= line_height
        
        # Zoom Level
        self.modern_gl_renderer.render_text(
            f"Zoom: {self.world_controller.camera_zoom:.2f}",
            x=x_pos,
            y=y_start,
            size=font_size,
            color=text_color
        )
    
    def _render_player(self):
        """Render player as yellow quad (1 tile wide, 2 tiles tall) using chunk shader"""
        if not self.world_controller.player:
            return
        
        # Player size: 1 tile wide, 2 tiles tall
        tile_size = settings.TILE_SIZE
        player_width = tile_size
        player_height = tile_size * 2
        
        # Player world position (center)
        player_world_x = self.world_controller.player.rect.center[0]
        player_world_y = self.world_controller.player.rect.center[1]
        
        # Calculate quad corners (top-left origin, like tiles) in world coordinates
        world_x0 = player_world_x - player_width / 2.0
        world_y0 = player_world_y - player_height / 2.0
        world_x1 = world_x0 + player_width
        world_y1 = world_y0 + player_height
        
        # Yellow color (normalized)
        r, g, b = 1.0, 1.0, 0.0  # Yellow
        
        # Create vertices (2 triangles = 6 vertices)
        # Format: [in_position (world coordinates in pixels), in_color (normalized)]
        # Transformation happens in shader (same as chunks)
        vertices = np.array([
            [world_x0, world_y0, r, g, b],  # Bottom-left
            [world_x1, world_y0, r, g, b],  # Bottom-right
            [world_x1, world_y1, r, g, b],  # Top-right
            [world_x0, world_y0, r, g, b],  # Bottom-left
            [world_x1, world_y1, r, g, b],  # Top-right
            [world_x0, world_y1, r, g, b],  # Top-left
        ], dtype=np.float32)
        
        # Create buffer and VAO (use chunk shader for transformation)
        vbo = self.modern_gl_renderer.ctx.buffer(vertices.tobytes())
        vao = self.modern_gl_renderer.ctx.vertex_array(
            self.modern_gl_renderer.chunk_program,
            [(vbo, "2f 3f", "in_position", "in_color")]
        )
        
        # Render (shader applies view matrix and zoom)
        vao.render(moderngl.TRIANGLES)
        
        # Cleanup
        vao.release()
        vbo.release()
    
    def _render_debug_visualization(self, chunks_data):
        """Render debug visualization: chunk boundaries and tile grids (optimized with caching)"""
        if not chunks_data or not self.world_controller.world or not self.world_controller.player:
            # Cleanup cache if visualization is disabled
            if self.ui_controller.debug_visualization_mode == 0 and self._debug_cache['vbo']:
                self._debug_cache['vbo'].release()
                self._debug_cache['vao'].release()
                self._debug_cache['vbo'] = None
                self._debug_cache['vao'] = None
            return
        
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        tile_size_pixels = settings.TILE_SIZE
        
        # Calculate player's chunk position
        player_world_x = self.world_controller.player.rect.center[0]
        player_world_y = self.world_controller.player.rect.center[1]
        player_chunk_x = int(player_world_x // chunk_size_pixels)
        player_chunk_y = int(player_world_y // chunk_size_pixels)
        player_chunk = (player_chunk_x, player_chunk_y)
        
        # Create hash of visible chunks for cache invalidation
        chunks_hash = hash(tuple(sorted((x, y) for x, y, _ in chunks_data)))
        
        # Check if cache is still valid
        cache_valid = (
            self._debug_cache['mode'] == self.ui_controller.debug_visualization_mode and
            self._debug_cache['player_chunk'] == player_chunk and
            self._debug_cache['chunks_hash'] == chunks_hash and
            self._debug_cache['vbo'] is not None
        )
        
        if not cache_valid:
            # Release old buffers if they exist
            if self._debug_cache['vbo']:
                self._debug_cache['vbo'].release()
                self._debug_cache['vao'].release()
            
            # Calculate 5x5 area centered on player's chunk
            grid_radius = 2  # 5x5 = radius 2 (2 chunks in each direction from center)
            grid_min_x = player_chunk_x - grid_radius
            grid_max_x = player_chunk_x + grid_radius
            grid_min_y = player_chunk_y - grid_radius
            grid_max_y = player_chunk_y + grid_radius
            
            # Collect all lines to render
            lines = []
            
            for chunk_x, chunk_y, _ in chunks_data:
                # Calculate chunk world position
                chunk_world_x = chunk_x * chunk_size_pixels
                chunk_world_y = chunk_y * chunk_size_pixels
                chunk_world_max_x = chunk_world_x + chunk_size_pixels
                chunk_world_max_y = chunk_world_y + chunk_size_pixels
                
                # Mode 1 or 2: Render chunk boundaries (red lines) for all visible chunks
                if self.ui_controller.debug_visualization_mode >= 1:
                    # Top edge
                    lines.append([chunk_world_x, chunk_world_y, chunk_world_max_x, chunk_world_y, 1.0, 0.0, 0.0])
                    # Bottom edge
                    lines.append([chunk_world_x, chunk_world_max_y, chunk_world_max_x, chunk_world_max_y, 1.0, 0.0, 0.0])
                    # Left edge
                    lines.append([chunk_world_x, chunk_world_y, chunk_world_x, chunk_world_max_y, 1.0, 0.0, 0.0])
                    # Right edge
                    lines.append([chunk_world_max_x, chunk_world_y, chunk_world_max_x, chunk_world_max_y, 1.0, 0.0, 0.0])
                
                # Mode 2: Render tile grids (blue lines) for 5x5 area around player
                # Only render when zoomed in (zoom > 1.0) to avoid performance issues when zoomed out
                if self.ui_controller.debug_visualization_mode >= 2 and self.world_controller.camera_zoom > 1.0:
                    # Check if chunk is in the 5x5 grid area
                    if grid_min_x <= chunk_x <= grid_max_x and grid_min_y <= chunk_y <= grid_max_y:
                        # Vertical tile lines
                        for tile_x in range(1, settings.CHUNK_SIZE):
                            tile_world_x = chunk_world_x + tile_x * tile_size_pixels
                            lines.append([tile_world_x, chunk_world_y, tile_world_x, chunk_world_max_y, 0.0, 0.0, 1.0])
                        
                        # Horizontal tile lines
                        for tile_y in range(1, settings.CHUNK_SIZE):
                            tile_world_y = chunk_world_y + tile_y * tile_size_pixels
                            lines.append([chunk_world_x, tile_world_y, chunk_world_max_x, tile_world_y, 0.0, 0.0, 1.0])
            
            if lines:
                # Create vertices for all lines (each line = 2 vertices)
                vertices = []
                for x1, y1, x2, y2, r, g, b in lines:
                    vertices.extend([
                        [x1, y1, r, g, b],
                        [x2, y2, r, g, b]
                    ])
                
                vertices_array = np.array(vertices, dtype=np.float32)
                
                # Create buffer and VAO (use chunk shader for transformation)
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
            
            # Update cache metadata
            self._debug_cache['mode'] = self.ui_controller.debug_visualization_mode
            self._debug_cache['player_chunk'] = player_chunk
            self._debug_cache['chunks_hash'] = chunks_hash
        
        # Render cached lines if available
        if self._debug_cache['vao']:
            self._debug_cache['vao'].render(moderngl.LINES)
    
    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        """Handle mouse wheel for zoom (with Control) or hotbar selection (without Control)"""
        from pyglet.window import key
        
        # Get modifiers
        modifiers = self.get_keys_pressed()
        
        # Delegate to game app
        self.game_app.handle_mouse_scroll(x, y, scroll_x, scroll_y, modifiers)
    
    def on_key_press(self, symbol, modifiers):
        """Handle keyboard input - delegates to GameApp state machine"""
        # Store key state for input handler (needed for InputHandler)
        if not hasattr(self, '_keys_pressed'):
            self._keys_pressed = set()
        self._keys_pressed.add(symbol)
        
        # Handle input handler (for movement keys)
        if self.input_handler:
            self.input_handler._handle_key_down(symbol)
        
        # Delegate to game app (state machine handles everything)
        self.game_app.handle_key_press(symbol, modifiers)
    
    def on_key_release(self, symbol, modifiers):
        """Handle key release"""
        if hasattr(self, '_keys_pressed'):
            self._keys_pressed.discard(symbol)
        
        # Handle input if handler exists
        if self.input_handler:
            self.input_handler._handle_key_up(symbol)
    
    def on_mouse_press(self, x, y, button, modifiers):
        """Handle mouse input - delegates to GameApp state machine"""
        # Delegate to game app (state machine handles everything)
        self.game_app.handle_mouse_press(x, y, button, modifiers)
    
    def on_mouse_motion(self, x, y, dx, dy):
        """Handle mouse motion"""
        # Delegate to game app
        self.game_app.handle_mouse_motion(x, y, dx, dy)
    
    def get_keys_pressed(self):
        """Get set of currently pressed keys"""
        return getattr(self, '_keys_pressed', set())
    
    def _render_tile_highlight(self):
        """Render highlight for tile under mouse cursor if within 8 tiles of player"""
        if not self.world_controller.camera or not self.world_controller.player:
            return
        
        # Convert mouse screen coordinates to world coordinates
        screen_width = self.width
        screen_height = self.height
        
        # In pyglet, (0,0) is bottom-left, so we need to invert Y
        # World coordinates: center is at camera position
        world_x = self.world_controller.camera.x + (self.world_controller.mouse_x - screen_width / 2.0) / self.world_controller.camera_zoom
        world_y = self.world_controller.camera.y + (screen_height / 2.0 - self.world_controller.mouse_y) / self.world_controller.camera_zoom
        
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
        import pyglet.shapes
        highlight = pyglet.shapes.Rectangle(
            screen_tile_x,
            screen_tile_y - settings.TILE_SIZE * self.world_controller.camera_zoom,  # Adjust for bottom-left origin
            settings.TILE_SIZE * self.world_controller.camera_zoom,
            settings.TILE_SIZE * self.world_controller.camera_zoom,
            color=(255, 255, 255)
        )
        highlight.opacity = 80  # Semi-transparent white overlay
        highlight.draw()
        
        # Draw border around highlighted tile (using separate rectangles for each edge)
        tile_size_scaled = settings.TILE_SIZE * self.world_controller.camera_zoom
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
    
    def _get_tile_under_mouse(self, mouse_x: int, mouse_y: int):
        """
        Get tile coordinates and data under mouse cursor if within 8 tiles of player
        
        Returns:
            Tuple of (tile_x, tile_y, tile_data) or None if not within range
        """
        if not self.world_controller.camera:
            return None
        
        # Convert mouse screen coordinates to world coordinates
        screen_width = self.width
        screen_height = self.height
        
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
        
        # Only process if within 8 tiles
        if distance_tiles > 8.0:
            return None
        
        # Get tile coordinates
        tile_x = int(world_x // settings.TILE_SIZE)
        tile_y = int(world_y // settings.TILE_SIZE)
        
        # Get tile data from terrain generator
        if self.world_controller.world and self.world_controller.world.terrain_gen:
            tile_data = self.world_controller.world.terrain_gen.generate_tile(tile_x, tile_y)
            return (tile_x, tile_y, tile_data)
        
        return None
    
    def _handle_tile_click(self, mouse_x: int, mouse_y: int, button: int):
        """
        Handle mouse click on tile (left or right button)
        
        Args:
            mouse_x: Mouse X coordinate
            mouse_y: Mouse Y coordinate
            button: Mouse button (mouse.LEFT or mouse.RIGHT)
        """
        tile_info = self._get_tile_under_mouse(mouse_x, mouse_y)
        if not tile_info:
            return
        
        tile_x, tile_y, tile_data = tile_info
        traversable = tile_data.get('traversable', False)
        tile_id = tile_data.get('tileid', '') or tile_data.get('tile_id', 'unknown')
        biome = tile_data.get('biome', 'unknown')
        
        if button == mouse.LEFT:
            # Left click: Check if destroyable
            if traversable:
                # Check if tile is destroyable (placeholder logic)
                is_destroyable = self._is_tile_destroyable(tile_data)
                if self.diagnostics:
                    if is_destroyable:
                        self.diagnostics.debug("Main", f"Linksklick auf Tile ({tile_x}, {tile_y}): zerstörbar (Biome: {biome}, Tile-ID: {tile_id})")
                    else:
                        self.diagnostics.debug("Main", f"Linksklick auf Tile ({tile_x}, {tile_y}): nicht zerstörbar (Biome: {biome}, Tile-ID: {tile_id})")
            else:
                if self.diagnostics:
                    self.diagnostics.debug("Main", f"Linksklick auf Tile ({tile_x}, {tile_y}): nicht zerstörbar (nicht traversable, Biome: {biome}, Tile-ID: {tile_id})")
        
        elif button == mouse.RIGHT:
            # Right click: Check if buildable (traversable check is irrelevant)
            can_build = self._can_build_on_tile(tile_data)
            if self.diagnostics:
                if can_build:
                    self.diagnostics.debug("Main", f"Rechtsklick auf Tile ({tile_x}, {tile_y}): darauf kann gebaut werden (Biome: {biome}, Tile-ID: {tile_id})")
                else:
                    self.diagnostics.debug("Main", f"Rechtsklick auf Tile ({tile_x}, {tile_y}): darauf kann nicht gebaut werden (Biome: {biome}, Tile-ID: {tile_id})")
    
    def _is_tile_destroyable(self, tile_data: dict) -> bool:
        """
        Check if a tile can be destroyed
        
        Args:
            tile_data: Tile data dictionary from terrain generator
            
        Returns:
            True if tile is destroyable, False otherwise
        """
        # Placeholder logic: Most tiles are destroyable except water
        tile_id = tile_data.get('tile_id', '')
        if 'water' in tile_id.lower():
            return False
        # TODO: Implement actual destroyability logic based on tile properties
        return True
    
    def _can_build_on_tile(self, tile_data: dict) -> bool:
        """
        Check if a building can be placed on this tile
        
        Args:
            tile_data: Tile data dictionary from terrain generator
            
        Returns:
            True if building can be placed, False otherwise
        """
        # Placeholder logic: Can build on traversable tiles (grass, sand, etc.)
        # Cannot build on water or mountains
        tile_id = tile_data.get('tile_id', '')
        traversable = tile_data.get('traversable', False)
        
        if 'water' in tile_id.lower():
            return False
        if 'mountain' in tile_id.lower() or 'stone' in tile_id.lower():
            return False
        # TODO: Implement actual buildability logic based on tile properties
        return traversable
    
    def _is_menu_active(self):
        """Check if any menu is currently active"""
        return (hasattr(self, 'world_select_menu') and self.world_select_menu.active) or \
               (self.pause_menu and self.pause_menu.active) or \
               (self.settings_menu and self.settings_menu.active) or \
               (self.save_menu and self.save_menu.active)
    
    def on_close(self):
        """Handle window close - perform cleanup before exiting"""
        self.diagnostics.info("Main", "Window closing, performing cleanup...")
        
        # Mark that cleanup is in progress to prevent double cleanup
        if hasattr(self, '_cleanup_done'):
            return  # Already cleaning up
        self._cleanup_done = True
        
        # Shutdown app (handles world shutdown, final save, cleanup)
        self.game_app.shutdown_app()
        
        # Cleanup ModernGL renderer
        if hasattr(self, 'modern_gl_renderer') and self.modern_gl_renderer:
            self.modern_gl_renderer.cleanup()
        
        # Exit application
        pyglet.app.exit()

def main():
    """Hauptfunktion"""
    window = GameWindow()
    if window.diagnostics:
        window.diagnostics.info("Main", "Starting pyglet application...")
    pyglet.app.run()
    
    # Additional cleanup (in case on_close wasn't called)
    # Check if cleanup was already done in on_close() to prevent double cleanup
    if not hasattr(window, '_cleanup_done') or not window._cleanup_done:
        window.diagnostics.info("Main", "Performing fallback cleanup (on_close was not called)...")
        # Shutdown app (handles world shutdown, final save, cleanup)
        if hasattr(window, 'game_app') and window.game_app:
            window.game_app.shutdown_app()
        
        # Cleanup ModernGL renderer
        if hasattr(window, 'modern_gl_renderer') and window.modern_gl_renderer:
            window.modern_gl_renderer.cleanup()
    else:
        window.diagnostics.info("Main", "Cleanup already performed in on_close()")
    
    window.diagnostics.info("Main", "Application closed")

if __name__ == "__main__":
    main()

