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
        
                # Draw grid lines - Grid bewegt sich mit der Welt!
        num_tiles_x = len(self.tiles[0]) if self.tiles else 0
        num_tiles_y = len(self.tiles)
        
        # Vertikale Linien (trennt Tiles in X-Richtung)
        for x in range(num_tiles_x + 1):
            world_x = x * settings.TILE_SIZE
            start_world = (world_x, 0)
            end_world = (world_x, num_tiles_y * settings.TILE_SIZE)
            
            start_screen = camera.world_to_screen(*start_world)
            end_screen = camera.world_to_screen(*end_world)
            
            pygame.draw.line(surface, settings.COLOR_GRID, start_screen, end_screen, 1)
        
        # Horizontale Linien (trennt Tiles in Y-Richtung)
        for y in range(num_tiles_y + 1):
            world_y = y * settings.TILE_SIZE
            start_world = (0, world_y)
            end_world = (num_tiles_x * settings.TILE_SIZE, world_y)
            
            start_screen = camera.world_to_screen(*start_world)
            end_screen = camera.world_to_screen(*end_world)
            
            pygame.draw.line(surface, settings.COLOR_GRID, start_screen, end_screen, 1) (0, y), (settings.SCREEN_WIDTH, y))
