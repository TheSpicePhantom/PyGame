"""
World: Spielwelt mit Chunk-basiertem Grid und Ressourcen
"""
import pygame
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
        
        # Font caching for grid overlay
        self.grid_font = pygame.font.Font(None, 20)
    
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
    
    def draw_grid(self, surface, camera):
        """Draw grid and terrain colors for loaded chunks (optimized with surface caching)"""
        # Get screen bounds for culling
        screen_rect = surface.get_rect()
        
        # Draw terrain using pre-rendered chunk surfaces
        for chunk in self.chunk_manager.loaded_chunks.values():
            # Quick chunk visibility check
            chunk_world_x = chunk.chunk_x * settings.CHUNK_SIZE * settings.TILE_SIZE
            chunk_world_y = chunk.chunk_y * settings.CHUNK_SIZE * settings.TILE_SIZE
            chunk_screen_pos = camera.world_to_screen(chunk_world_x, chunk_world_y)
            chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
            
            # Skip chunk if completely off-screen
            if (chunk_screen_pos[0] + chunk_size_pixels < 0 or 
                chunk_screen_pos[0] > screen_rect.width or
                chunk_screen_pos[1] + chunk_size_pixels < 0 or 
                chunk_screen_pos[1] > screen_rect.height):
                continue
            
            # Use pre-rendered surface if available
            if chunk.surface is not None:
                # Fast blit of entire chunk surface (1 draw call instead of 225!)
                surface.blit(chunk.surface, chunk_screen_pos)
            else:
                # Fallback: render on-the-fly if surface not ready yet
                # This should rarely happen after initial load
                chunk.render_to_surface()
                if chunk.surface:
                    surface.blit(chunk.surface, chunk_screen_pos)
    
    def draw_chunk_grid_overlay(self, surface, camera, player_pos):
        """Draw 5x5 chunk grid around player (F8 cycles: Off → Chunks → Chunks+Tiles)
        Grid is snapped to chunk boundaries and only redrawn when player changes chunks"""
        if self.grid_mode == 0:
            return
        
        # Calculate player's chunk position
        player_chunk_x = int(player_pos[0] // (settings.CHUNK_SIZE * settings.TILE_SIZE))
        player_chunk_y = int(player_pos[1] // (settings.CHUNK_SIZE * settings.TILE_SIZE))
        
        # Check if player changed chunks or mode changed
        if (self.grid_cache_player_chunk != (player_chunk_x, player_chunk_y) or
            self.grid_cache_mode != self.grid_mode):
            # Update cache metadata (grid will be redrawn this frame)
            self.grid_cache_player_chunk = (player_chunk_x, player_chunk_y)
            self.grid_cache_mode = self.grid_mode
        
        # Draw grid directly (no caching needed - it's fast enough with chunk snapping)
        self._draw_grid_overlay(surface, camera, player_chunk_x, player_chunk_y)
    
    def _draw_grid_overlay(self, surface, camera, player_chunk_x, player_chunk_y):
        """Draw grid overlay snapped to chunk boundaries"""
        # Draw 5x5 grid centered on player's chunk
        grid_radius = 2  # 2 chunks in each direction = 5x5 total
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        
        for dy in range(-grid_radius, grid_radius + 1):
            for dx in range(-grid_radius, grid_radius + 1):
                chunk_x = player_chunk_x + dx
                chunk_y = player_chunk_y + dy
                
                # Calculate world position of chunk (top-left corner)
                world_x = chunk_x * chunk_size_pixels
                world_y = chunk_y * chunk_size_pixels
                
                # Convert chunk corners to screen coordinates
                top_left = camera.world_to_screen(world_x, world_y)
                top_right = camera.world_to_screen(world_x + chunk_size_pixels, world_y)
                bottom_left = camera.world_to_screen(world_x, world_y + chunk_size_pixels)
                bottom_right = camera.world_to_screen(world_x + chunk_size_pixels, world_y + chunk_size_pixels)
                
                # Draw chunk border using lines (snapped to world coordinates)
                is_player_chunk = (dx == 0 and dy == 0)
                color = (255, 255, 0) if is_player_chunk else (100, 255, 100)
                width = 3 if is_player_chunk else 2
                
                # Draw rectangle using 4 lines
                pygame.draw.line(surface, color, top_left, top_right, width)  # Top
                pygame.draw.line(surface, color, top_right, bottom_right, width)  # Right
                pygame.draw.line(surface, color, bottom_right, bottom_left, width)  # Bottom
                pygame.draw.line(surface, color, bottom_left, top_left, width)  # Left
                
                # Draw chunk coordinates at top-left (using cached font)
                coord_text = self.grid_font.render(f"({chunk_x},{chunk_y})", True, (255, 255, 255))
                surface.blit(coord_text, (top_left[0] + 5, top_left[1] + 5))
                
                # Mode 2: Draw tile grid within each chunk
                if self.grid_mode == 2:
                    tile_color = (80, 80, 80) if is_player_chunk else (60, 60, 60)
                    
                    # Draw vertical tile lines
                    for x in range(settings.CHUNK_SIZE + 1):
                        tile_world_x = world_x + x * settings.TILE_SIZE
                        start_screen = camera.world_to_screen(tile_world_x, world_y)
                        end_screen = camera.world_to_screen(tile_world_x, world_y + chunk_size_pixels)
                        pygame.draw.line(surface, tile_color, start_screen, end_screen, 1)
                    
                    # Draw horizontal tile lines
                    for y in range(settings.CHUNK_SIZE + 1):
                        tile_world_y = world_y + y * settings.TILE_SIZE
                        start_screen = camera.world_to_screen(world_x, tile_world_y)
                        end_screen = camera.world_to_screen(world_x + chunk_size_pixels, tile_world_y)
                        pygame.draw.line(surface, tile_color, start_screen, end_screen, 1)

    def refresh_visible_chunks(self, player_pos):
        """Refresh chunk loading after screen size change"""
        self.chunk_manager.refresh_visible_chunks(player_pos)
    
    def cleanup(self):
        """Cleanup resources when world is destroyed"""
        self.chunk_manager.shutdown()
        print("[World] Chunk loading threads stopped")
