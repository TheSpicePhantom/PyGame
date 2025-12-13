"""
Chunk Manager: Minecraft-Style Chunk Loading/Unloading System
"""
import math
from typing import Dict, Tuple, Set
from core import settings


class Chunk:
    """Represents a single 15x15 tile chunk"""
    
    def __init__(self, chunk_x, chunk_y, tiles):
        self.chunk_x = chunk_x
        self.chunk_y = chunk_y
        self.tiles = tiles  # 15x15 array of tile data
        self.entities = []  # Entities in this chunk
        self.is_loaded = True
    
    def get_world_position(self):
        """Get top-left world position in pixels"""
        return (
            self.chunk_x * settings.CHUNK_SIZE * settings.TILE_SIZE,
            self.chunk_y * settings.CHUNK_SIZE * settings.TILE_SIZE
        )
    
    def get_bounds(self):
        """Get chunk bounds (x, y, width, height) in pixels"""
        world_pos = self.get_world_position()
        size = settings.CHUNK_SIZE * settings.TILE_SIZE
        return (world_pos[0], world_pos[1], size, size)


class ChunkManager:
    """Manages chunk loading/unloading based on player position"""
    
    def __init__(self, terrain_gen):
        self.terrain_gen = terrain_gen
        self.loaded_chunks: Dict[Tuple[int, int], Chunk] = {}
        self.player_chunk_pos = (0, 0)
    
    def world_to_chunk(self, world_x, world_y):
        """Convert world pixel coordinates to chunk coordinates"""
        chunk_x = math.floor(world_x / (settings.CHUNK_SIZE * settings.TILE_SIZE))
        chunk_y = math.floor(world_y / (settings.CHUNK_SIZE * settings.TILE_SIZE))
        return (chunk_x, chunk_y)
    
    def get_or_create_chunk(self, chunk_x, chunk_y):
        """Get existing chunk or generate new one"""
        key = (chunk_x, chunk_y)
        
        # Check world bounds
        if (chunk_x < 0 or chunk_x >= settings.WORLD_SIZE_CHUNKS or
            chunk_y < 0 or chunk_y >= settings.WORLD_SIZE_CHUNKS):
            return None
        
        if key not in self.loaded_chunks:
            # Generate new chunk
            tiles = self.terrain_gen.generate_chunk(chunk_x, chunk_y, settings.CHUNK_SIZE)
            self.loaded_chunks[key] = Chunk(chunk_x, chunk_y, tiles)
            print(f"[ChunkManager] Generated chunk ({chunk_x}, {chunk_y})")
        
        return self.loaded_chunks[key]

      
    def update(self, player_pos):
        """Update chunks based on player position"""
        # Calculate player chunk position
        self.player_chunk_pos = self.world_to_chunk(player_pos[0], player_pos[1])
        
        # Load chunks around player
        chunks_to_load = self._get_chunks_in_range(
            self.player_chunk_pos, 
            settings.CHUNK_LOAD_DISTANCE
        )
        
        for chunk_pos in chunks_to_load:
            self.get_or_create_chunk(*chunk_pos)
        
        # Unload distant chunks
        self._unload_distant_chunks()
    
    def _get_chunks_in_range(self, center_chunk, distance):
        """Get all chunk positions within distance of center"""
        chunks = set()
        for dx in range(-distance, distance + 1):
            for dy in range(-distance, distance + 1):
                chunk_x = center_chunk[0] + dx
                chunk_y = center_chunk[1] + dy
                chunks.add((chunk_x, chunk_y))
        return chunks
    
    def _unload_distant_chunks(self):
        """Unload chunks farther than CHUNK_UNLOAD_DISTANCE"""
        to_unload = []
        
        for chunk_pos in self.loaded_chunks.keys():
            distance = max(
                abs(chunk_pos[0] - self.player_chunk_pos[0]),
                abs(chunk_pos[1] - self.player_chunk_pos[1])
            )
            
            if distance > settings.CHUNK_UNLOAD_DISTANCE:
                to_unload.append(chunk_pos)
        
        for chunk_pos in to_unload:
            del self.loaded_chunks[chunk_pos]
            print(f"[ChunkManager] Unloaded chunk {chunk_pos}")
    
    def get_chunk_count(self):
        """Get number of currently loaded chunks"""
        return len(self.loaded_chunks)
