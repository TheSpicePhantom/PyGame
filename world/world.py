"""
World: Spielwelt mit Grid und Ressourcen (mit TerrainGenerator)
"""
import pygame
from core import settings
from world.entities import ResourceNode
from world.terrain_generator import TerrainGenerator


class World:
    """Verwaltet die Spielwelt mit Grid, Ressourcen und prozeduralem Terrain"""

    def __init__(self, all_sprites, resource_sprites, seed=None):
        self.all_sprites = all_sprites
        self.resource_sprites = resource_sprites
        
        # Initialize terrain generator
        self.terrain_gen = TerrainGenerator(seed=seed)
        print(f"[World] Terrain generator initialized with seed: {self.terrain_gen.seed}")
        
        # Generate initial world (viewport-sized chunk)
        self.tiles = self.terrain_gen.generate_chunk(0, 0, chunk_size=90)
        print(f"[World] Generated {len(self.tiles)}x{len(self.tiles[0])} terrain chunk")
        
        # Spawn resources based on generated terrain
        self.spawn_resources_from_terrain()
    
    def spawn_resources_from_terrain(self):
        """Spawn resource nodes based on terrain data"""
        resource_count = 0
        for y, row in enumerate(self.tiles):
            for x, tile in enumerate(row):
                # Check if this tile has resources
                if tile["resources"] and tile["traversable"]:
                    # Spawn first resource type for now
                    resource_type = tile["resources"][0]
                    
                    ResourceNode(
                        (x * settings.TILE_SIZE, y * settings.TILE_SIZE),
                        resource_type,
                        9999,
                        self.all_sprites,
                        self.resource_sprites
                    )
                    resource_count += 1
        
        print(f"[World] Spawned {resource_count} resource nodes")
    
    def draw_grid(self, surface, camera):
        """Draw grid and terrain colors with camera offset"""
        # Draw terrain tiles
        for y, row in enumerate(self.tiles):
            for x, tile in enumerate(row):
                world_x = x * settings.TILE_SIZE
                world_y = y * settings.TILE_SIZE
                screen_pos = camera.world_to_screen(world_x, world_y)
                
                rect = pygame.Rect(
                    screen_pos[0],
                    screen_pos[1],
                    settings.TILE_SIZE,
                    settings.TILE_SIZE
                )
                pygame.draw.rect(surface, tile["color"], rect)
        
        # Draw grid lines (optional, für besser Übersicht)
        for x in range(0, settings.SCREEN_WIDTH, settings.TILE_SIZE):
            pygame.draw.line(surface, settings.COLOR_GRID, (x, 0), (x, settings.SCREEN_HEIGHT))
        for y in range(0, settings.SCREEN_HEIGHT, settings.TILE_SIZE):
            pygame.draw.line(surface, settings.COLOR_GRID, (0, y), (settings.SCREEN_WIDTH, y))
