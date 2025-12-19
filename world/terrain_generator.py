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
from collections import OrderedDict
from typing import Tuple
from pathlib import Path
from core import settings


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
        
        # Performance: LRU Cache for generated tiles (prevents unbounded memory growth)
        # Max size: 100k tiles ≈ 444 chunks (100k / 225 tiles per chunk)
        # This covers a large area around the player while preventing memory issues
        self._tile_cache_max_size = 100000  # Max 100k tiles in cache
        self._tile_cache: OrderedDict[Tuple[int, int], dict] = OrderedDict()
    
    def set_seed(self, seed: int):
        """
        Set new seed and reinitialize noise generator
        
        Also updates the seed in noise_settings for consistency (useful if seed is saved to savegame).
        
        Args:
            seed: New seed value for terrain generation
        """
        self.seed = seed
        self.noise = OpenSimplex(seed=self.seed)
        self._tile_cache.clear()  # Clear cache when seed changes
        
        # Update seed in config for consistency (useful if seed is saved to savegame)
        if "noise_settings" in self.config:
            self.config["noise_settings"]["seed"] = seed
        
        print(f"[TerrainGen] Seed updated to: {self.seed}")
    
    def load_config(self, path):
        """
        Load biome configuration from JSON and pre-calculate normalized height ranges
        
        Uses Path for robust path handling, especially useful for tools/tests.
        
        Args:
            path: Relative path to config file (e.g., "data/worldgen/biomes.json")
        """
        # Use Path for robust path handling (works better for tools/tests)
        full_path = Path(__file__).parent / ".." / path
        full_path = full_path.resolve()  # Resolve to absolute path
        
        with open(full_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        
        # Pre-calculate normalized height ranges for efficient lookup
        # Normalize config values from [-1, 1] to [0, 1] once during config load
        biome_list = []
        for biome_id, biome_data in self.config["biomes"].items():
            h_min = biome_data["height_min"]
            h_max = biome_data["height_max"]
            
            # Pre-calculate normalized values (from [-1, 1] to [0, 1])
            h_min_norm = (h_min + 1.0) / 2.0
            h_max_norm = (h_max + 1.0) / 2.0
            
            # Store normalized values in biome_data for fast lookup
            biome_entry = (biome_id, {
                **biome_data,
                "height_min_norm": h_min_norm,
                "height_max_norm": h_max_norm
            })
            biome_list.append(biome_entry)
        
        # Sort biomes by height_min_norm for efficient lookup (and potential binary search)
        self.sorted_biomes = sorted(
            biome_list,
            key=lambda x: x[1]["height_min_norm"]
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
        """
        Determine biome based on normalized height value [0, 1]
        
        Uses pre-calculated normalized height ranges for efficient lookup.
        For many biomes (>10), consider using binary search instead of linear search.
        
        Args:
            height_value: Normalized height value in [0, 1] range
        
        Returns:
            Tuple of (biome_id, biome_data)
        """
        # Use binary search if we have many biomes (more efficient)
        # Otherwise linear search is fine (current: 7 biomes)
        if len(self.sorted_biomes) > 10:
            # Binary search for many biomes
            left, right = 0, len(self.sorted_biomes) - 1
            while left <= right:
                mid = (left + right) // 2
                biome_id, biome_data = self.sorted_biomes[mid]
                h_min_norm = biome_data["height_min_norm"]
                h_max_norm = biome_data["height_max_norm"]
                
                if height_value < h_min_norm:
                    right = mid - 1
                elif height_value > h_max_norm:
                    left = mid + 1
                else:
                    # Found matching biome
                    return biome_id, biome_data
        else:
            # Linear search for few biomes (simpler, fast enough)
            for biome_id, biome_data in self.sorted_biomes:
                # Use pre-calculated normalized values (no recalculation needed!)
                h_min_norm = biome_data["height_min_norm"]
                h_max_norm = biome_data["height_max_norm"]
                
                if h_min_norm <= height_value <= h_max_norm:
                    return biome_id, biome_data
        
        # Fallback to last biome (highest elevation)
        return self.sorted_biomes[-1]
    
    def generate_tile(self, world_x, world_y):
        """
        Generate a single tile at world coordinates
        
        PERFORMANCE: Returns minimal tile data (no resources!)
        Uses LRU cache to prevent unbounded memory growth during long play sessions.
        
        IMPORTANT: The returned tile structure (biome, height, tile_id, color, traversable)
        is binary-compatible with RegionManager.serialize_chunk(). Any changes to this
        structure must be reflected in RegionManager.serialize_chunk() and deserialize_chunk()
        to maintain compatibility.
        
        Args:
            world_x: World X coordinate (tile coordinate)
            world_y: World Y coordinate (tile coordinate)
        
        Returns:
            Dictionary with tile data (biome, height, tile_id, color, traversable)
        """
        cache_key = (world_x, world_y)
        
        # Check cache first (LRU: move to end if found)
        if cache_key in self._tile_cache:
            # Move to end (mark as recently used)
            tile = self._tile_cache.pop(cache_key)
            self._tile_cache[cache_key] = tile
            return tile
        
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
        
        # Cache result (add to end = most recently used)
        self._tile_cache[cache_key] = tile
        
        # Evict oldest entries if cache exceeds max size
        while len(self._tile_cache) > self._tile_cache_max_size:
            # Remove oldest (first item)
            self._tile_cache.popitem(last=False)
        
        return tile
    
    def generate_chunk(self, chunk_x, chunk_y, chunk_size=None):
        """
        Generate a chunk by sampling the continuous world
        
        This ensures chunks connect seamlessly!
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate  
            chunk_size: Tiles per chunk (defaults to settings.CHUNK_SIZE if None)
        
        Returns:
            2D list of tile dictionaries
        
        Raises:
            AssertionError: If chunk_size doesn't match settings.CHUNK_SIZE (prevents mismatches)
        """
        # Use settings.CHUNK_SIZE as default to avoid hardcoded values
        if chunk_size is None:
            chunk_size = settings.CHUNK_SIZE
        
        # Assert to catch mismatches early (prevents silent bugs)
        assert chunk_size == settings.CHUNK_SIZE, (
            f"chunk_size mismatch: got {chunk_size}, expected {settings.CHUNK_SIZE}. "
            f"This would cause save/load inconsistencies!"
        )
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
