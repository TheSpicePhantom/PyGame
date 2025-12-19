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
        self.all_sprites = all_sprites
        self.resource_sprites = resource_sprites
        self.save_slot = save_slot
        
        # Initialize terrain generator
        self.terrain_gen = TerrainGenerator(seed=seed)
        print(f"[World] Terrain generator initialized with seed: {self.terrain_gen.seed}")
        
        # Initialize chunk manager
        self.chunk_manager = ChunkManager(save_slot, self.terrain_gen, performance_monitor=performance_monitor)
        
        # Load or set seed
        existing_seed = self.chunk_manager.get_seed()
        if existing_seed is not None:
            # Load existing world seed
            self.terrain_gen.set_seed(existing_seed)
            print(f"[World] Loaded existing world with seed: {existing_seed}")
        elif seed is not None:
            # Use provided seed for new world
            self.chunk_manager.set_seed(seed)
            print(f"[World] Created new world with seed: {seed}")
        else:
            # Generate random seed for new world
            import random
            new_seed = random.randint(0, 999999)
            self.chunk_manager.set_seed(new_seed)
            self.terrain_gen.set_seed(new_seed)            
            print(f"[World] Created new world with random seed: {new_seed}")
        
        print(f"[World] ChunkManager initialized for save slot {save_slot}")
        self._initial_preload_done = False  # Track initial chunk preload
        self.grid_mode = 0  # 0=Off, 1=Chunks only, 2=Chunks+Tiles (F8 cycles)
        
        # Grid overlay caching
        self.grid_cache = None  # Cached grid surface
        self.grid_cache_player_chunk = None  # Player chunk position when cache was created
        self.grid_cache_mode = None  # Grid mode when cache was created
        
        # Font caching for grid overlay (TODO: Migrate to ModernGL text rendering)
        self.grid_font = None  # No longer using Pygame font
    
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
    
    def draw_grid(self, surface, camera, modern_gl_renderer=None):
        """
        Draw grid and terrain colors for loaded chunks
        
        Args:
            surface: Pygame surface (for fallback rendering)
            camera: Camera instance
            modern_gl_renderer: Optional ModernGL renderer for GPU acceleration
        """
        # Start timing for performance monitoring
        render_start_time = time.perf_counter()
        
        # Use ModernGL if available
        if modern_gl_renderer is not None:
            self._draw_grid_modern_gl(modern_gl_renderer, camera)
        else:
            self._draw_grid_pygame(surface, camera)
        
        # Record chunk rendering time (if performance monitor available)
        render_time = time.perf_counter() - render_start_time
        if hasattr(self.chunk_manager, 'performance_monitor') and self.chunk_manager.performance_monitor:
            self.chunk_manager.performance_monitor.record_chunk_render_time(render_time)
    
    def _draw_grid_modern_gl(self, modern_gl_renderer, camera):
        """Draw chunks using ModernGL (GPU-accelerated)"""
        # View matrix is updated in main.py, don't update here
        # camera_x, camera_y = camera.x, camera.y
        # zoom = getattr(camera, 'zoom', 1.0) if hasattr(camera, 'zoom') else 1.0
        # modern_gl_renderer.update_view(camera_x, camera_y, zoom)
        
        # Get screen bounds for culling
        screen_width = modern_gl_renderer.screen_width
        screen_height = modern_gl_renderer.screen_height
        
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
            modern_gl_renderer.render_chunks(chunks_data)
    
    def _draw_grid_pygame(self, surface, camera):
        """
        Draw chunks using Pygame (fallback)
        NOTE: This method is deprecated - ModernGL is always used now.
        Kept for compatibility but does nothing.
        """
        # Pygame rendering is no longer supported - use ModernGL instead
        pass
    
    def draw_chunk_grid_overlay(self, surface, camera, player_pos):
        """Draw 5x5 chunk grid around player (F8 cycles: Off → Chunks → Chunks+Tiles)
        Grid is snapped to chunk boundaries and only redrawn when player changes chunks
        TODO: Migrate to ModernGL rendering"""
        # Grid overlay temporarily disabled - will be migrated to ModernGL
        pass
    
    def _draw_grid_overlay(self, surface, camera, player_chunk_x, player_chunk_y):
        """Draw grid overlay snapped to chunk boundaries
        TODO: Migrate to ModernGL rendering"""
        # Grid overlay temporarily disabled - will be migrated to ModernGL
        pass

    def refresh_visible_chunks(self, player_pos):
        """Refresh chunk loading after screen size change"""
        self.chunk_manager.refresh_visible_chunks(player_pos)
    
    def cleanup(self):
        """Cleanup resources when world is destroyed"""
        self.chunk_manager.shutdown()
        print("[World] Chunk loading threads stopped")
