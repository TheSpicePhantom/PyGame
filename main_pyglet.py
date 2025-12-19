"""
Hauptdatei: Startet das Top-Down Factorio-Style Spiel (pyglet + ModernGL)
"""
import pyglet
from pyglet.window import key, mouse
import moderngl
import os
import time
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
from world.player_data_manager import PlayerDataManager
from world.auto_save import AutoSaveSystem
from analytics.performance_monitor import PerformanceMonitor
from analytics.logger import PerformanceLogger
from view.modern_gl_renderer import ModernGLRenderer
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
        
        # Create window
        super().__init__(width=width, height=height, caption="PyGame - Factorio Style", fullscreen=fullscreen)
        
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
        print(f"[Main] ModernGL context created successfully")
        print(f"[Main] OpenGL version: {self.ctx.info.get('GL_VERSION', 'unknown')}")
        
        # Create ModernGL renderer (with pyglet coordinate system)
        self.modern_gl_renderer = ModernGLRenderer(self.ctx, width, height, use_pyglet=True)
        print("[Main] Using ModernGL for GPU-accelerated rendering (pyglet mode)")
        
        # Initialize game state
        self.performance_monitor = PerformanceMonitor()
        self.performance_logger = PerformanceLogger()
        self.performance_logger.start_log()
        
        # Performance stats display
        self.show_performance_stats = False
        self.stats_update_interval = 0.5  # Update stats every 0.5 seconds
        self.last_stats_update = 0.0
        self.logger = PerformanceLogger()
        self.logger.start_log()
        print("[Main] Performance monitoring enabled")
        
        # Load recipes
        load_recipes()
        print("[Main] Loaded recipes from JSON")
        
        # Game state
        self.game_initialized = False
        self.clock = pyglet.clock.Clock()
        self.dt = 0.0
        
        # Initialize game components (will be set up after save slot selection)
        # TODO: SaveMenu benötigt pygame.font - später migrieren
        self.world = None
        self.player = None
        self.camera = None
        self.all_sprites = None
        self.input_handler = None
        self.pause_menu = None
        self.settings_menu = None
        # self.save_menu = SaveMenu()  # Temporär deaktiviert - benötigt pygame.font
        # self.save_menu.active = True
        # self.save_menu.mode = "select"
        self.selected_slot = None
        self.save_menu = None  # Wird später initialisiert
        
        # Initialize input handler
        self.input_handler = InputHandler(self)
        
        # Initialize game directly (skip save menu for now)
        self._initialize_game(save_slot=1)
        
        # Schedule update loop
        pyglet.clock.schedule_interval(self.update, 1.0 / 60.0)
        
        print(f"[Main] Window created: {width}x{height}, mode: {initial_mode}")
    
    def _initialize_game(self, save_slot=1):
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
            performance_monitor=self.performance_monitor
        )
        
        # Initialize PlayerDataManager
        from world.player_data_manager import PlayerDataManager
        player_data_manager = PlayerDataManager(save_slot)
        
        # Debug: Set everything to (0, 0) for testing (except test quads)
        start_world_x = 0.0
        start_world_y = 0.0
        
        # Player erstellen
        self.player = Player(
            pos=(start_world_x, start_world_y),
            input_handler=self.input_handler,
            performance_monitor=self.performance_monitor
        )
        self.all_sprites.add(self.player, layer=settings.LAYER_PLAYER)
        
        # Kamera initialisieren
        self.camera = Camera(target=self.player, lerp_speed=settings.CAMERA_LERP_SPEED)
        # Zoom: 1.5 = 150% (nah), 0.75 = 75% (weit weg)
        self.camera_zoom = 1.0  # Start at 100%
        
        # Mark game as initialized
        self.game_initialized = True
        print(f"[Main] Game initialized - Player at ({start_world_x}, {start_world_y})")
    
    def update(self, dt):
        """Update game logic"""
        # Update performance stats display periodically
        current_time = time.time()
        if current_time - self.last_stats_update >= self.stats_update_interval:
            self._update_performance_stats()
            self.last_stats_update = current_time
        self.dt = dt
        
        # Always update input handler
        if self.input_handler:
            self.input_handler.update()
            
            # Debug: Print movement if keys are pressed
            if self.input_handler.move_dir_x != 0 or self.input_handler.move_dir_y != 0:
                if not hasattr(self, '_input_debug_printed'):
                    print(f"[Input] Movement detected: ({self.input_handler.move_dir_x:.2f}, {self.input_handler.move_dir_y:.2f})")
                    self._input_debug_printed = True
        
        if self.game_initialized:
            # Update game (only if no menu is active)
            menu_active = (self.pause_menu and self.pause_menu.active) or \
                         (self.settings_menu and self.settings_menu.active) or \
                         (self.save_menu and self.save_menu.active)
            
            if not menu_active:
                self.performance_monitor.start_update()
                if self.all_sprites:
                    self.all_sprites.update(dt)
                if self.camera:
                    self.camera.update(dt)
                if self.world:
                    self.world.update(self.player.rect.center if self.player else (0, 0))
                self.performance_monitor.end_update()
    
    def on_draw(self):
        """Render frame"""
        self.performance_monitor.start_frame()
        self.performance_monitor.start_render()
        
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
                print(f"[Debug] Error setting up clip-space test: {e}")
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
                print(f"[Debug] Error setting up yellow quad: {e}")
                import traceback
                traceback.print_exc()
        
        # TEMPORARILY DISABLED: Render yellow quad every frame (for debugging)
        # if hasattr(self, '_yellow_vao'):
        #     self._yellow_vao.render(moderngl.TRIANGLES)
        
        # Render Chunks: Update View -> Load Visible Chunks -> Collect Visible Chunks -> Render
        if self.game_initialized and self.world and self.world.chunk_manager:
            # Step 1: Update view matrix based on camera position and zoom
            if self.camera:
                camera_x = self.camera.x
                camera_y = self.camera.y
                self.modern_gl_renderer.update_view(camera_x, camera_y, zoom=self.camera_zoom)
            else:
                camera_x = 0.0
                camera_y = 0.0
                self.modern_gl_renderer.update_view(0.0, 0.0, zoom=self.camera_zoom)
            
            # Step 1.5: Load chunks in visible area + 1 chunk buffer (dynamically based on zoom)
            self._load_visible_chunks(camera_x, camera_y)
            
            # Step 2: Collect all visible chunks (with frustum culling)
            chunks_data = []
            screen_width = self.modern_gl_renderer.screen_width
            screen_height = self.modern_gl_renderer.screen_height
            chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
            
            # Process chunks: visible -> rendering -> active -> rendered
            # Reset "rendered" state first (keep "visible" and "inactive" from _load_visible_chunks)
            for chunk in self.world.chunk_manager.loaded_chunks.values():
                if chunk.render_state == "rendered":
                    chunk.render_state = None  # Reset for next frame
            
            # Process all loaded chunks
            for chunk in self.world.chunk_manager.loaded_chunks.values():
                # Mark chunk as being prepared for rendering if it's visible
                if chunk.render_state == "visible":
                    chunk.render_state = "rendering"
                
                # Calculate chunk world position
                chunk_world_x = chunk.chunk_x * chunk_size_pixels
                chunk_world_y = chunk.chunk_y * chunk_size_pixels
                
                # Calculate chunk screen position (world + camera offset)
                chunk_screen_x = chunk_world_x + self.modern_gl_renderer.view_matrix[0, 3]
                chunk_screen_y = chunk_world_y + self.modern_gl_renderer.view_matrix[1, 3]
                
                # Frustum culling: Skip chunk if completely off-screen
                if (chunk_screen_x + chunk_size_pixels < 0 or 
                    chunk_screen_x > screen_width or
                    chunk_screen_y + chunk_size_pixels < 0 or 
                    chunk_screen_y > screen_height):
                    # Chunk is in view field but not visible on screen
                    if chunk.render_state == "rendering":
                        chunk.render_state = "inactive"
                    elif chunk.render_state == "visible":
                        chunk.render_state = "inactive"
                    continue
                
                # Chunk passed frustum culling - mark as active
                if chunk.render_state == "rendering":
                    chunk.render_state = "active"
                
                # Add chunk data for rendering
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
            
            # Debug: Print chunk state summary (only occasionally to avoid spam)
            if not hasattr(self, '_last_chunk_debug') or time.time() - self._last_chunk_debug > 1.0:
                self._print_chunk_state_summary()
                self._last_chunk_debug = time.time()
            
            # Step 4: Render player as yellow quad (1x2 tiles)
            if self.player:
                self._render_player()
            if self.player:
                self._render_player()
            
            # Debug: Render yellow quad directly in clip-space (same as green quad)
            if not hasattr(self, '_yellow_quad_rendered'):
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
                    yellow_program = self.ctx.program(
                        vertex_shader=simple_vertex_shader,
                        fragment_shader=simple_fragment_shader
                    )
                    
                    # Yellow quad in center of screen
                    yellow_vertices = np.array([
                        [-0.3, -0.3, 255.0, 255.0, 0.0],
                        [0.3, -0.3, 255.0, 255.0, 0.0],
                        [0.3, 0.3, 255.0, 255.0, 0.0],
                        [-0.3, -0.3, 255.0, 255.0, 0.0],
                        [0.3, 0.3, 255.0, 255.0, 0.0],
                        [-0.3, 0.3, 255.0, 255.0, 0.0],
                    ], dtype=np.float32)
                    
                    yellow_vbo = self.ctx.buffer(yellow_vertices.tobytes())
                    yellow_vao = self.ctx.simple_vertex_array(
                        yellow_program,
                        yellow_vbo,
                        'in_position', 'in_color'
                    )
                    
                    # TEMPORARILY DISABLED: yellow_vao.render(moderngl.TRIANGLES)
                    yellow_vbo.release()
                    yellow_vao.release()
                    
                    # print(f"[Debug] Rendered yellow quad with simple shader in main_pyglet.py")
                    self._yellow_quad_rendered = True
                except Exception as e:
                    print(f"[Debug] Error rendering yellow quad: {e}")
                    import traceback
                    traceback.print_exc()
        
        self.performance_monitor.end_render()
        
        # Toggle performance stats with F3
        if self.show_performance_stats:
            self._draw_performance_stats()
    
    def _load_visible_chunks(self, camera_x: float, camera_y: float):
        """Load chunks in visible area + 1 chunk buffer based on zoom"""
        if not self.world or not self.world.chunk_manager:
            return
        
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        screen_width = self.modern_gl_renderer.screen_width
        screen_height = self.modern_gl_renderer.screen_height
        
        # Calculate visible area in world coordinates (accounting for zoom)
        # With zoom, we see more/less world: visible_world_size = screen_size / zoom
        visible_world_width = screen_width / self.camera_zoom
        visible_world_height = screen_height / self.camera_zoom
        
        # Calculate visible area bounds in world coordinates
        # Camera is at screen center, so visible area is centered on camera
        world_min_x = camera_x - visible_world_width / 2.0
        world_max_x = camera_x + visible_world_width / 2.0
        world_min_y = camera_y - visible_world_height / 2.0
        world_max_y = camera_y + visible_world_height / 2.0
        
        # Convert to chunk coordinates (+1 buffer in all directions)
        chunk_min_x = int(world_min_x // chunk_size_pixels) - 1  # -1 for buffer
        chunk_max_x = int(world_max_x // chunk_size_pixels) + 1  # +1 for buffer
        chunk_min_y = int(world_min_y // chunk_size_pixels) - 1  # -1 for buffer
        chunk_max_y = int(world_max_y // chunk_size_pixels) + 1  # +1 for buffer
        
        # Calculate visible chunk count (for debug output)
        visible_chunk_count = (chunk_max_x - chunk_min_x + 1) * (chunk_max_y - chunk_min_y + 1)
        
        # Debug output on zoom change
        if not hasattr(self, '_last_zoom_debug') or self._last_zoom_debug != self.camera_zoom:
            print(f"[Chunk Debug] Zoom: {self.camera_zoom:.2f} | Visible area: {visible_world_width:.1f}x{visible_world_height:.1f} px")
            print(f"[Chunk Debug] Chunk range: X[{chunk_min_x}..{chunk_max_x}] Y[{chunk_min_y}..{chunk_max_y}]")
            print(f"[Chunk Debug] Visible chunks: {visible_chunk_count}")
            self._last_zoom_debug = self.camera_zoom
        
        # Load all chunks in visible area + buffer
        chunks_to_load = set()
        for chunk_x in range(chunk_min_x, chunk_max_x + 1):
            for chunk_y in range(chunk_min_y, chunk_max_y + 1):
                # Check world bounds
                if (0 <= chunk_x < settings.WORLD_SIZE_CHUNKS and
                    0 <= chunk_y < settings.WORLD_SIZE_CHUNKS):
                    chunks_to_load.add((chunk_x, chunk_y))
        
        # Load chunks that aren't already loaded
        chunk_manager = self.world.chunk_manager
        for chunk_x, chunk_y in chunks_to_load:
            chunk_key = (chunk_x, chunk_y)
            if chunk_key not in chunk_manager.loaded_chunks:
                chunk_manager.get_or_create_chunk(chunk_x, chunk_y)
        
        # Mark chunks in visible area as "visible" (in view field)
        # First, reset states for chunks not in visible area
        for chunk_key, chunk in list(chunk_manager.loaded_chunks.items()):
            if chunk_key not in chunks_to_load:
                # Chunk is loaded but not in visible area
                if chunk.render_state not in ["rendering", "rendered", "active"]:
                    chunk.render_state = "inactive"
        
        # Mark chunks in visible area as "visible"
        for chunk_x, chunk_y in chunks_to_load:
            chunk_key = (chunk_x, chunk_y)
            if chunk_key in chunk_manager.loaded_chunks:
                chunk = chunk_manager.loaded_chunks[chunk_key]
                # Only set to "visible" if not already in a rendering state
                if chunk.render_state not in ["rendering", "rendered", "active"]:
                    chunk.render_state = "visible"
        
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
    
    def _print_chunk_state_summary(self):
        """Print summary of chunk states for debugging"""
        if not self.world or not self.world.chunk_manager:
            return
        
        chunk_manager = self.world.chunk_manager
        state_counts = {
            "rendering": 0,
            "rendered": 0,
            "visible": 0,
            "active": 0,
            "inactive": 0,
            None: 0
        }
        
        for chunk in chunk_manager.loaded_chunks.values():
            state = chunk.render_state
            if state in state_counts:
                state_counts[state] += 1
            else:
                state_counts[None] += 1
        
        total_loaded = len(chunk_manager.loaded_chunks)
        print(f"[Chunk Debug] Loaded: {total_loaded} | "
              f"Rendering: {state_counts['rendering']} | "
              f"Rendered: {state_counts['rendered']} | "
              f"Visible: {state_counts['visible']} | "
              f"Active: {state_counts['active']} | "
              f"Inactive: {state_counts['inactive']}")
    
    def _update_performance_stats(self):
        """Update performance statistics"""
        stats = self.performance_monitor.get_stats()
        self.performance_logger.log_stats(stats)
    
    def _draw_performance_stats(self):
        """Draw performance statistics on screen"""
        stats = self.performance_monitor.get_stats()
        
        # Create text labels (simple text rendering for now)
        # TODO: Implement proper text rendering with ModernGL
        lines = [
            f"FPS: {stats['fps']['current']:.1f} (min: {stats['fps']['min']:.1f}, max: {stats['fps']['max']:.1f})",
            f"Frame: {stats['frame_times']['avg']:.2f}ms (p95: {stats['frame_times']['p95']:.2f}ms)",
            f"Update: {stats['update_times']['avg']:.2f}ms",
            f"Render: {stats['render_times']['avg']:.2f}ms",
            f"Chunk Render: {stats['chunk_render_times']['avg']:.2f}ms" if stats['chunk_render_times']['avg'] > 0 else "Chunk Render: N/A",
        ]
        
        # For now, just print to console (text rendering will be added later)
        if hasattr(self, '_last_stats_print') and time.time() - self._last_stats_print < 0.5:
            return
        self._last_stats_print = time.time()
        print("\n".join(lines))
    
    def _render_player(self):
        """Render player as yellow quad (1 tile wide, 2 tiles tall) using chunk shader"""
        if not self.player:
            return
        
        # Player size: 1 tile wide, 2 tiles tall
        tile_size = settings.TILE_SIZE
        player_width = tile_size
        player_height = tile_size * 2
        
        # Player world position (center)
        player_world_x = self.player.rect.center[0]
        player_world_y = self.player.rect.center[1]
        
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
    
    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        """Handle mouse wheel for zoom"""
        # Zoom: scroll up = zoom in (150%), scroll down = zoom out (75%)
        zoom_speed = 0.05  # 5% per scroll step
        if scroll_y > 0:  # Scroll up = zoom out (weiter weg)
            self.camera_zoom = max(0.75, self.camera_zoom - zoom_speed)
        elif scroll_y < 0:  # Scroll down = zoom in (näher dran)
            self.camera_zoom = min(1.5, self.camera_zoom + zoom_speed)
    
    def on_key_press(self, symbol, modifiers):
        """Handle keyboard input"""
        if symbol == key.ESCAPE:
            # Save performance log before exit
            self.performance_logger.save_log()
            pyglet.app.exit()
        
        # Toggle performance stats with F3
        if symbol == key.F3:
            self.show_performance_stats = not self.show_performance_stats
            print(f"[Performance] Stats display: {'ON' if self.show_performance_stats else 'OFF'}")
        
        # Store key state for input handler
        if not hasattr(self, '_keys_pressed'):
            self._keys_pressed = set()
        self._keys_pressed.add(symbol)
        
        # Handle input if handler exists
        if self.input_handler:
            self.input_handler._handle_key_down(symbol)
    
    def on_key_release(self, symbol, modifiers):
        """Handle key release"""
        if hasattr(self, '_keys_pressed'):
            self._keys_pressed.discard(symbol)
        
        # Handle input if handler exists
        if self.input_handler:
            self.input_handler._handle_key_up(symbol)
    
    def on_mouse_press(self, x, y, button, modifiers):
        """Handle mouse input"""
        # TODO: Implement mouse handling
        pass
    
    def get_keys_pressed(self):
        """Get set of currently pressed keys"""
        return getattr(self, '_keys_pressed', set())
    
    def on_close(self):
        """Handle window close"""
        pyglet.app.exit()

def main():
    """Hauptfunktion"""
    window = GameWindow()
    print("[Main] Starting pyglet application...")
    pyglet.app.run()
    
    # Cleanup
    if window.modern_gl_renderer:
        window.modern_gl_renderer.cleanup()
    
    print("[Main] Application closed")

if __name__ == "__main__":
    main()

