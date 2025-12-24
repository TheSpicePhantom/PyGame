"""
World: Spielwelt mit Chunk-basiertem Grid und Ressourcen
"""
import time
from core import settings
from world.terrain_generator import TerrainGenerator
from world.chunk_manager import ChunkManager


class World:
    """Verwaltet die Spielwelt mit dynamischen Chunks und prozeduralem Terrain"""
    
    def __init__(self, all_sprites, resource_sprites, world_name: str = "Unnamed World", seed=None, performance_monitor=None, diagnostics=None): 
        self.all_sprites = all_sprites
        self.resource_sprites = resource_sprites
        self.world_name = world_name
        self.diagnostics = diagnostics  # Store diagnostics service for logging
        
        # Initialize chunk manager first (to check if world already exists)
        # We'll create a temporary terrain generator, then update it with the correct seed
        temp_terrain_gen = TerrainGenerator(seed=None)  # Temporary, will be replaced
        self.chunk_manager = ChunkManager(world_name, temp_terrain_gen, performance_monitor=performance_monitor, diagnostics=diagnostics)
        
        # Initialize seed (load existing or create new)
        # This will set the correct seed in both chunk_manager and terrain_gen
        final_seed = self._init_seed(seed)
        
        # Now create the actual terrain generator with the correct seed
        self.terrain_gen = TerrainGenerator(seed=final_seed)
        # Update chunk manager to use the correct terrain generator
        self.chunk_manager.terrain_gen = self.terrain_gen
        if self.diagnostics:
            self.diagnostics.info("World", f"Terrain generator initialized with seed: {self.terrain_gen.seed}")
            self.diagnostics.info("World", f"ChunkManager initialized for world '{world_name}'")
        else:
            print(f"[World] Terrain generator initialized with seed: {self.terrain_gen.seed}")
            print(f"[World] ChunkManager initialized for world '{world_name}'")
        self._initial_preload_done = False  # Track initial chunk preload
        self.grid_mode = 0  # 0=Off, 1=Chunks only, 2=Chunks+Tiles (F8 cycles)
    
    def _init_seed(self, seed=None):
        """
        Initialize world seed (load existing or create new)
        
        Args:
            seed: Optional seed value. If None, loads existing seed.
                  NOTE: For new worlds created via CreateWorldMenu, seed should always be provided.
                  Random seed generation is handled exclusively by CreateWorldMenu.get_seed().
        
        Returns:
            int: The seed that will be used (for terrain generator initialization)
        
        Raises:
            ValueError: If no seed is provided and no existing world seed exists.
        """
        existing_seed = self.chunk_manager.get_seed()
        if existing_seed is not None:
            # Load existing world seed (world already exists)
            if self.diagnostics:
                self.diagnostics.debug("World", f"Loaded existing world seed: {existing_seed}", world_name=self.world_name)
            else:
                print(f"[World] DEBUG: Loaded existing world seed: {existing_seed} (world='{self.world_name}')")
            return existing_seed
        elif seed is not None:
            # Use provided seed for new world (from menu)
            if self.diagnostics:
                self.diagnostics.debug("World", f"Using seed from menu: {seed}", world_name=self.world_name)
                self.diagnostics.info("World", f"Created new world with seed: {seed}")
            else:
                print(f"[World] DEBUG: Using seed from menu: {seed} (world='{self.world_name}')")
                print(f"[World] Created new world with seed: {seed}")
            self.chunk_manager.set_seed(seed)
            return seed
        else:
            # ERROR: No seed provided and no existing world
            # This should not happen when creating a world via CreateWorldMenu
            error_msg = (
                f"No seed provided for new world (world='{self.world_name}'). "
                "CreateWorldMenu.get_seed() should always return a valid seed. "
                "This indicates a bug in the world creation flow - seed generation must happen in CreateWorldMenu."
            )
            if self.diagnostics:
                self.diagnostics.error("World", error_msg, world_name=self.world_name)
            else:
                print(f"[World] ERROR: {error_msg}")
            raise ValueError(error_msg)
    
    def update(self, player_pos, camera_pos=None, screen_width=None, screen_height=None, zoom=1.0):
        """
        Update world based on player and camera position (load/unload chunks)
        
        Args:
            player_pos: Player position (x, y) in world coordinates (pixels)
            camera_pos: Camera position (x, y) in world coordinates (pixels). If None, uses player_pos
            screen_width: Screen width in pixels. If None, uses settings.SCREEN_WIDTH
            screen_height: Screen height in pixels. If None, uses settings.SCREEN_HEIGHT
            zoom: Camera zoom factor (default: 1.0)
        """
        # Pre-load visible chunks on first update to prevent stuttering
        if not self._initial_preload_done:
            self.chunk_manager.preload_visible_chunks(player_pos)
            self._initial_preload_done = True
            if self.diagnostics:
                self.diagnostics.info("World", "Pre-loaded visible chunks around player position")
            else:
                print(f"[World] Pre-loaded visible chunks around player position")
        
        # Use preload radius for initial load (optional, can be None to skip)
        preload_radius = settings.get_chunk_load_distance() if not self._initial_preload_done else None
        
        # Update chunk manager with camera-based loading
        self.chunk_manager.update(
            player_pos=player_pos,
            camera_pos=camera_pos,
            screen_width=screen_width,
            screen_height=screen_height,
            zoom=zoom,
            preload_radius=preload_radius
        )
        
        # Process chunks that finished loading in background threads
        self.chunk_manager.process_loaded_chunks(self.all_sprites, self.resource_sprites)
    
    def draw(self, camera, renderer):
        """
        Draw grid and terrain colors for loaded chunks using ModernGL
        
        Args:
            camera: Camera instance
            renderer: ModernGL renderer for GPU acceleration (required)
        """
        # Start timing for performance monitoring
        render_start_time = time.perf_counter()
        
        # Render chunks using ModernGL
        self._draw_chunks(renderer, camera)
        
        # Record chunk rendering time (if performance monitor available)
        render_time = time.perf_counter() - render_start_time
        if hasattr(self.chunk_manager, 'performance_monitor') and self.chunk_manager.performance_monitor:
            self.chunk_manager.performance_monitor.record_chunk_render_time(render_time)
    
    def _draw_chunks(self, renderer, camera):
        """Draw chunks using ModernGL (GPU-accelerated)"""
        # View matrix is updated in main.py, don't update here
        # camera_x, camera_y = camera.x, camera.y
        # zoom = getattr(camera, 'zoom', 1.0) if hasattr(camera, 'zoom') else 1.0
        # renderer.update_view(camera_x, camera_y, zoom)
        
        # Get screen bounds for culling
        screen_width = renderer.screen_width
        screen_height = renderer.screen_height
        
        # Collect visible chunks with their tile data
        chunks_data = []
        for chunk in self.chunk_manager.loaded_chunks.values():
            # Quick chunk visibility check
            chunk_world_x = chunk.chunk_x * settings.CHUNK_SIZE * settings.TILE_SIZE
            chunk_world_y = chunk.chunk_y * settings.CHUNK_SIZE * settings.TILE_SIZE
            chunk_screen_pos = camera.world_to_screen(chunk_world_x, chunk_world_y)
            chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
            
            # Skip chunk if completely off-screen
            if (chunk_screen_pos[0] + chunk_size_pixels < 0 or 
                chunk_screen_pos[0] > screen_width or
                chunk_screen_pos[1] + chunk_size_pixels < 0 or 
                chunk_screen_pos[1] > screen_height):
                continue
            
            # Add chunk data for rendering
            chunks_data.append((chunk.chunk_x, chunk.chunk_y, chunk.tiles))
        
        # Render all chunks at once
        if chunks_data:
            renderer.render_chunks(chunks_data)
    

    def refresh_visible_chunks(self, player_pos):
        """Refresh chunk loading after screen size change"""
        self.chunk_manager.refresh_visible_chunks(player_pos)
    
    def cleanup(self):
        """
        Cleanup resources when world is destroyed
        
        IMPORTANT: This method MUST be called during game shutdown (e.g., from main.on_close).
        It properly shuts down worker threads and closes region file handles, preventing resource
        leaks and ensuring all pending chunk saves are completed.
        
        Lifecycle: This marks the end of the world lifecycle. After cleanup(), the World instance
        should not be used anymore.
        
        Note: This method is idempotent - calling it multiple times is safe and will only
        perform cleanup once.
        """
        if hasattr(self, '_cleaned_up') and self._cleaned_up:
            return  # Already cleaned up
        
        self._cleaned_up = True
        self.chunk_manager.shutdown()
        print("[World] Chunk loading threads stopped")
