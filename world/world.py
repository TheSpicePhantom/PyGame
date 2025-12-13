"""
World: Spielwelt mit Chunk-basiertem Grid und Ressourcen
"""
import pygame
from core import settings
from world.entities import ResourceNode
from world.terrain_generator import TerrainGenerator
from world.chunk_manager import ChunkManager


class World:
    """Verwaltet die Spielwelt mit dynamischen Chunks, Ressourcen und prozeduralem Terrain"""

    def __init__(self, all_sprites, resource_sprites, seed=None):
        self.all_sprites = all_sprites
        self.resource_sprites = resource_sprites

        # Initialize terrain generator
        self.terrain_gen = TerrainGenerator(seed=seed)
        print(f"[World] Terrain generator initialized with seed: {self.terrain_gen.seed}")

        # Initialize chunk manager
        self.chunk_manager = ChunkManager(self.terrain_gen)
        print(f"[World] ChunkManager initialized")

        # Track spawned resource nodes
        self.spawned_resources = set()

    def update(self, player_pos):
        """Update world based on player position (load/unload chunks)"""
        self.chunk_manager.update(player_pos)

        # Spawn resources for newly loaded chunks
        self.spawn_resources_for_loaded_chunks()

    def spawn_resources_for_loaded_chunks(self):
        """Spawn resource nodes for all loaded chunks that haven't been processed yet"""
        for chunk_key, chunk in self.chunk_manager.loaded_chunks.items():
            if chunk_key not in self.spawned_resources:
                self._spawn_resources_for_chunk(chunk)
                self.spawned_resources.add(chunk_key)

    def _spawn_resources_for_chunk(self, chunk):
        """Spawn resource nodes for a single chunk"""
        resource_count = 0
        for y, row in enumerate(chunk.tiles):
            for x, tile in enumerate(row):
                # Check if this tile has resources
                if tile["resources"] and tile["traversable"]:
                    # Spawn first resource type for now
                    resource_type = tile["resources"][0]

                    # Calculate world position
                    world_x = (chunk.chunk_x * settings.CHUNK_SIZE + x) * settings.TILE_SIZE
                    world_y = (chunk.chunk_y * settings.CHUNK_SIZE + y) * settings.TILE_SIZE

                    ResourceNode(
                        (world_x, world_y),
                        resource_type,
                        9999,
                        self.all_sprites,
                        self.resource_sprites
                    )
                    resource_count += 1

        if resource_count > 0:
            print(f"[World] Spawned {resource_count} resources for chunk {chunk.chunk_x}, {chunk.chunk_y}")

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
