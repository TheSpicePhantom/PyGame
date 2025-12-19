"""
World: Spielwelt mit Chunk-basiertem Grid und Ressourcen
"""
import time
from core import settings
from world.terrain_generator import TerrainGenerator
from world.chunk_manager import ChunkManager

class World:
    """Verwaltet die Spielwelt mit dynamischen Chunks und prozeduralem Terrain"""
    
    def __init__(self, all_sprites, resource_sprites, save_slot=1, seed=None, performance_monitor=None): 
        self.all_sprites = all_sprites
        self.resource_sprites = resource_sprites
        self.save_slot = save_slot
        
        # Initialize terrain generator
        self.terrain_gen = TerrainGenerator(seed=seed)
        print(f"[World] Terrain generator initialized with seed: {self.terrain_gen.seed}")
        
        # Initialize chunk manager
        self.chunk_manager = ChunkManager(save_slot, self.terrain_gen, performance_monitor=performance_monitor)
        
        # Initialize seed (load existing or create new)
        self._init_seed(seed)
        
        print(f"[World] ChunkManager initialized for save slot {save_slot}")
        self._initial_preload_done = False  # Track initial chunk preload
        self.grid_mode = 0  # 0=Off, 1=Chunks only, 2=Chunks+Tiles (F8 cycles)
    
    def _init_seed(self, seed=None):
        """
        Initialize world seed (load existing or create new)
        
        Args:
            seed: Optional seed value. If None, loads existing seed or generates random one.
        """
        existing_seed = self.chunk_manager.get_seed()
        if existing_seed is not None:
            # Load existing world seed
            self.terrain_gen.set_seed(existing_seed)
            print(f"[World] Loaded existing world with seed: {existing_seed}")
        elif seed is not None:
            # Use provided seed for new world
            self.chunk_manager.set_seed(seed)
            self.terrain_gen.set_seed(seed)
            print(f"[World] Created new world with seed: {seed}")
        else:
            # Generate random seed for new world
            import random
            new_seed = random.randint(0, 999999)
            self.chunk_manager.set_seed(new_seed)
            self.terrain_gen.set_seed(new_seed)            
            print(f"[World] Created new world with random seed: {new_seed}")
    
    def update(self, player_pos):
        """Update world based on player position (load/unload chunks)"""
        # Pre-load visible chunks on first update to prevent stuttering
        if not self._initial_preload_done:
            self.chunk_manager.preload_visible_chunks(player_pos)
            self._initial_preload_done = True
            print(f"[World] Pre-loaded visible chunks around player position")
        
        self.chunk_manager.update(player_pos)
        
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
