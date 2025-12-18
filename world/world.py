"""
World: Spielwelt mit Chunk-basiertem Grid und Ressourcen
"""
import pygame
from core import settings
from world.terrain_generator import TerrainGenerator
from world.chunk_manager import ChunkManager

class World:
    """Verwaltet die Spielwelt mit dynamischen Chunks und prozeduralem Terrain"""
    
    def __init__(self, all_sprites, resource_sprites, save_slot=1, seed=None): 
        self.all_sprites = all_sprites
        self.all_sprites = all_sprites
        self.resource_sprites = resource_sprites
        self.save_slot = save_slot
        
        # Initialize terrain generator
        self.terrain_gen = TerrainGenerator(seed=seed)
        print(f"[World] Terrain generator initialized with seed: {self.terrain_gen.seed}")
        
        # Initialize chunk manager
        self.chunk_manager = ChunkManager(save_slot, self.terrain_gen)
        
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
    
    def update(self, player_pos):
        """Update world based on player position (load/unload chunks)"""

                # Pre-load visible chunks on first update to prevent stuttering
                if not self._initial_preload_done:
                                self.chunk_manager.preload_visible_chunks(player_pos)
                                self._initial_preload_done = True
                                print(f"[World] Pre-loaded visible chunks around player position")
        self.chunk_manager.update(player_pos)
    
    def draw_grid(self, surface, camera):
        """Draw grid and terrain colors for loaded chunks"""
        # Draw terrain tiles for all loaded chunks
        for chunk in self.chunk_manager.loaded_chunks.values():
            for y, row in enumerate(chunk.tiles):
                for x, tile in enumerate(row):
                    # Calculate world position
                    world_x = (chunk.chunk_x * settings.CHUNK_SIZE + x) * settings.TILE_SIZE
                    world_y = (chunk.chunk_y * settings.CHUNK_SIZE + y) * settings.TILE_SIZE
                    
                    screen_pos = camera.world_to_screen(world_x, world_y)
                    rect = pygame.Rect(
                        screen_pos[0],
                        screen_pos[1],
                        settings.TILE_SIZE,
                        settings.TILE_SIZE
                    )
                    
                    pygame.draw.rect(surface, tile["color"], rect)
        
        # Draw grid lines for all loaded chunks
        for chunk in self.chunk_manager.loaded_chunks.values():
            self._draw_chunk_grid(surface, camera, chunk)
    
    def _draw_chunk_grid(self, surface, camera, chunk):
        """Draw grid lines for a single chunk"""
        # Chunk boundaries in world coordinates
        chunk_world_x = chunk.chunk_x * settings.CHUNK_SIZE * settings.TILE_SIZE
        chunk_world_y = chunk.chunk_y * settings.CHUNK_SIZE * settings.TILE_SIZE
        
        # Vertical lines
        for x in range(settings.CHUNK_SIZE + 1):
            world_x = chunk_world_x + x * settings.TILE_SIZE
            start_world = (world_x, chunk_world_y)
            end_world = (world_x, chunk_world_y + settings.CHUNK_SIZE * settings.TILE_SIZE)
            
            start_screen = camera.world_to_screen(*start_world)
            end_screen = camera.world_to_screen(*end_world)
            pygame.draw.line(surface, settings.COLOR_GRID, start_screen, end_screen, 1)
        
        # Horizontal lines
        for y in range(settings.CHUNK_SIZE + 1):
            world_y = chunk_world_y + y * settings.TILE_SIZE
            start_world = (chunk_world_x, world_y)
            end_world = (chunk_world_x + settings.CHUNK_SIZE * settings.TILE_SIZE, world_y)
            
            start_screen = camera.world_to_screen(*start_world)
            end_screen = camera.world_to_screen(*end_world)
            pygame.draw.line(surface, settings.COLOR_GRID, start_screen, end_screen, 1)
