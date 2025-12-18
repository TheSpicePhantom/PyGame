"""
Procedural Terrain Generator with OpenSimplex Noise
Generates continuous world heightmap, then splits into chunks
Optimized for performance - NO per-tile resource generation
"""
import json
import os
import random
import numpy as np
from opensimplex import OpenSimplex


class TerrainGenerator:
    """Generates continuous procedural terrain using OpenSimplex Noise"""
    
    def __init__(self, config_path="data/worldgen/biomes.json", seed=None):
        self.load_config(config_path)
        
        # Initialize noise generator with seed
        if seed is None:
            seed = self.config["noise_settings"].get("seed")
        if seed is None:
            seed = random.randint(0, 1000000)
        
        self.seed = seed
        self.noise = OpenSimplex(seed=self.seed)
        
        # Performance: Cache for generated tiles
        self._tile_cache = {}

        def set_seed(self, seed: int):
                    """Set new seed and reinitialize noise generator"""
                    self.seed = seed
                    self.noise = OpenSimplex(seed=self.seed)
                    self._tile_cache = {}  # Clear cache when seed changes
                    print(f"[TerrainGen] Seed updated to: {self.seed}")
    
    def load_config(self, path):
        """Load biome configuration from JSON"""
        full_path = os.path.join(os.path.dirname(__file__), "..", path)
        with open(full_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        
        # Sort biomes by height_min for efficient lookup
        self.sorted_biomes = sorted(
            self.config["biomes"].items(),
            key=lambda x: x[1]["height_min"]
        )
    
    def get_noise_value(self, world_x, world_y):
        """Get continuous noise value for any world coordinate
        
        This ensures world continuity across chunks!
        """
        settings = self.config["noise_settings"]
        
        # Adjusted parameters for more diverse terrain
        scale = settings.get("scale", 200.0)  # Larger scale = bigger features
        octaves = settings.get("octaves", 6)
        persistence = settings.get("persistence", 0.5)
        lacunarity = settings.get("lacunarity", 2.0)
        
        amplitude = 1.0
        frequency = 1.0
        noise_value = 0.0
        max_value = 0.0
        
        # Multi-octave noise for natural variation
        for _ in range(octaves):
            sample_x = world_x / scale * frequency
            sample_y = world_y / scale * frequency
            
            noise_value += self.noise.noise2(sample_x, sample_y) * amplitude
            max_value += amplitude
            
            amplitude *= persistence
            frequency *= lacunarity
        
        # Normalize to [0, 1] range (easier for biome thresholds)
        normalized = (noise_value / max_value + 1.0) / 2.0
        return normalized
    
    def get_biome(self, height_value):
        """Determine biome based on normalized height value [0, 1]"""
        for biome_id, biome_data in self.sorted_biomes:
            h_min = biome_data["height_min"]
            h_max = biome_data["height_max"]
            
            # Normalize config values from [-1, 1] to [0, 1]
            h_min_norm = (h_min + 1.0) / 2.0
            h_max_norm = (h_max + 1.0) / 2.0
            
            if h_min_norm <= height_value <= h_max_norm:
                return biome_id, biome_data
        
        # Fallback to last biome
        return self.sorted_biomes[-1]
    
    def generate_tile(self, world_x, world_y):
        """Generate a single tile at world coordinates
        
        PERFORMANCE: Returns minimal tile data (no resources!)
        """
        # Check cache first
        cache_key = (world_x, world_y)
        if cache_key in self._tile_cache:
            return self._tile_cache[cache_key]
        
        # Get continuous noise value
        height = self.get_noise_value(world_x, world_y)
        biome_id, biome_data = self.get_biome(height)
        
        tile = {
            "biome": biome_id,
            "height": float(height),
            "tile_id": biome_data["tile_id"],
            "color": tuple(biome_data["color"]),
            "traversable": biome_data["traversable"]
            # NO "resources" field = massive performance gain!
        }
        
        # Cache result
        self._tile_cache[cache_key] = tile
        return tile
    
    def generate_chunk(self, chunk_x, chunk_y, chunk_size=15):
        """Generate a chunk by sampling the continuous world
        
        This ensures chunks connect seamlessly!
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate  
            chunk_size: Tiles per chunk (default 15 for CHUNK_SIZE constant)
        
        Returns:
            2D list of tile dictionaries
        """
        # Calculate world offset for this chunk
        world_offset_x = chunk_x * chunk_size
        world_offset_y = chunk_y * chunk_size
        
        tiles = []
        for tile_y in range(chunk_size):
            row = []
            for tile_x in range(chunk_size):
                # Calculate absolute world coordinates
                world_x = world_offset_x + tile_x
                world_y = world_offset_y + tile_y
                
                # Generate tile from continuous world function
                tile = self.generate_tile(world_x, world_y)
                row.append(tile)
            
            tiles.append(row)
        
        return tiles
    
    def clear_cache(self):
        """Clear tile cache (useful when changing seeds)"""
        self._tile_cache.clear()
