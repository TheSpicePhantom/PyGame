"""
Procedural Terrain Generator with OpenSimplex Noise
Generates heightmap-based biomes for Factorio-style world
"""
import json
import os
import random
import numpy as np
from opensimplex import OpenSimplex


class TerrainGenerator:
    """Generates procedural terrain using OpenSimplex Noise and JSON config"""
    
    def __init__(self, config_path="data/worldgen/biomes.json", seed=None):
        self.load_config(config_path)
        
        # Initialize noise generator with seed
        if seed is None:
            seed = self.config["noise_settings"].get("seed")
        if seed is None:
            seed = random.randint(0, 1000000)
        
        self.seed = seed
        self.noise = OpenSimplex(seed=self.seed)
    
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
    
    def generate_heightmap(self, width, height, offset_x=0, offset_y=0):
        """Generate 2D heightmap using multi-octave OpenSimplex noise"""
        settings = self.config["noise_settings"]
        scale = settings["scale"]
        octaves = settings["octaves"]
        persistence = settings["persistence"]
        lacunarity = settings["lacunarity"]
        
        heightmap = np.zeros((height, width))
        
        for y in range(height):
            for x in range(width):
                amplitude = 1.0
                frequency = 1.0
                noise_value = 0.0
                
                # Multi-octave (Fractal) noise for natural variation
                for _ in range(octaves):
                    sample_x = (x + offset_x) / scale * frequency
                    sample_y = (y + offset_y) / scale * frequency
                    
                    noise_value += self.noise.noise2(sample_x, sample_y) * amplitude
                    
                    amplitude *= persistence
                    frequency *= lacunarity
                
                # Normalize to [-1, 1] range
                heightmap[y, x] = noise_value / sum(
                    persistence ** i for i in range(octaves)
                )
        
        return heightmap
    
    def get_biome(self, height_value):
        """Determine biome based on height value"""
        for biome_id, biome_data in self.sorted_biomes:
            if biome_data["height_min"] <= height_value <= biome_data["height_max"]:
                return biome_id, biome_data
        
        # Fallback to last biome if out of range
        return self.sorted_biomes[-1]
    
    def generate_chunk(self, chunk_x, chunk_y, chunk_size=32):
        """Generate a chunk of tiles with biome information"""
        offset_x = chunk_x * chunk_size
        offset_y = chunk_y * chunk_size
        
        heightmap = self.generate_heightmap(
            chunk_size, chunk_size, offset_x, offset_y
        )
        
        tiles = []
        for y in range(chunk_size):
            row = []
            for x in range(chunk_size):
                height = heightmap[y, x]
                biome_id, biome_data = self.get_biome(height)
                
                row.append({
                    "biome": biome_id,
                    "height": float(height),
                    "tile_id": biome_data["tile_id"],
                    "color": tuple(biome_data["color"]),
                    "traversable": biome_data["traversable"],
                    "resources": biome_data.get("resources", [])
                })
            tiles.append(row)
        
        return tiles
