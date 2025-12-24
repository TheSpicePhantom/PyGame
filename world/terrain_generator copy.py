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
        # Support both "noise_settings" and "noisesettings" for compatibility
        noise_settings = self.config.get("noise_settings") or self.config.get("noisesettings", {})
        if seed is None:
            seed = noise_settings.get("seed")
        if seed is None:
            seed = random.randint(0, 1000000)
        
        self.seed = seed
        self.noise = OpenSimplex(seed=self.seed)
        self.temp_noise = OpenSimplex(seed=self.seed + 1)  # Second noise generator for temperature
        
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
        self.temp_noise = OpenSimplex(seed=self.seed + 1)  # Reinitialize temperature noise
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
        
        # Pre-calculate normalized height and temperature ranges for efficient lookup
        # Normalize config values from [-1, 1] to [0, 1] once during config load
        # Support both "height_min"/"heightmax" and "temp_min"/"tempmax" formats for compatibility
        biome_list = []
        for biome_id, biome_data in self.config["biomes"].items():
            # Support both naming conventions: "height_min"/"heightmax" and "temp_min"/"tempmax"
            h_min = biome_data.get("height_min") or biome_data.get("heightmin", -1.0)
            h_max = biome_data.get("height_max") or biome_data.get("heightmax", 1.0)
            t_min = biome_data.get("temp_min") or biome_data.get("tempmin", 0.0)
            t_max = biome_data.get("temp_max") or biome_data.get("tempmax", 1.0)
            
            # Pre-calculate normalized height values (from [-1, 1] to [0, 1])
            h_min_norm = (h_min + 1.0) / 2.0
            h_max_norm = (h_max + 1.0) / 2.0
            
            # Temperature is already in [0, 1] range, but normalize for consistency
            t_min_norm = max(0.0, min(1.0, t_min))
            t_max_norm = max(0.0, min(1.0, t_max))
            
            # Store normalized values in biome_data for fast lookup
            biome_entry = (biome_id, {
                **biome_data,
                "height_min_norm": h_min_norm,
                "height_max_norm": h_max_norm,
                "temp_min_norm": t_min_norm,
                "temp_max_norm": t_max_norm
            })
            biome_list.append(biome_entry)
        
        # Sort biomes by height_min_norm for efficient lookup (and potential binary search)
        self.sorted_biomes = sorted(
            biome_list,
            key=lambda x: x[1]["height_min_norm"]
        )
    
    def update_biome_config(self, biome_config):
        """
        Update biome configuration without reloading from file
        
        Useful for interactive tools that want to modify biome ranges dynamically.
        
        Args:
            biome_config: Dictionary with biome configuration (same format as JSON)
        """
        self.config["biomes"] = biome_config
        
        # Recalculate normalized ranges
        biome_list = []
        for biome_id, biome_data in self.config["biomes"].items():
            # Support both naming conventions
            h_min = biome_data.get("height_min") or biome_data.get("heightmin", -1.0)
            h_max = biome_data.get("height_max") or biome_data.get("heightmax", 1.0)
            t_min = biome_data.get("temp_min") or biome_data.get("tempmin", 0.0)
            t_max = biome_data.get("temp_max") or biome_data.get("tempmax", 1.0)
            
            # Pre-calculate normalized height values (from [-1, 1] to [0, 1])
            h_min_norm = (h_min + 1.0) / 2.0
            h_max_norm = (h_max + 1.0) / 2.0
            
            # Temperature is already in [0, 1] range, but normalize for consistency
            t_min_norm = max(0.0, min(1.0, t_min))
            t_max_norm = max(0.0, min(1.0, t_max))
            
            # Store normalized values
            biome_entry = (biome_id, {
                **biome_data,
                "height_min_norm": h_min_norm,
                "height_max_norm": h_max_norm,
                "temp_min_norm": t_min_norm,
                "temp_max_norm": t_max_norm
            })
            biome_list.append(biome_entry)
        
        # Re-sort biomes
        self.sorted_biomes = sorted(
            biome_list,
            key=lambda x: x[1]["height_min_norm"]
        )
        
        # Clear cache to force regeneration with new biome ranges
        self._tile_cache.clear()
    
    def get_noise_value(self, world_x, world_y):
        """Get continuous noise value for any world coordinate
        
        This ensures world continuity across chunks!
        """
        # Get noise settings (support both "noise_settings" and "noisesettings" for compatibility)
        noise_settings = self.config.get("noise_settings") or self.config.get("noisesettings", {})
        
        # Adjusted parameters for more diverse terrain
        scale = noise_settings.get("scale", 200.0)  # Larger scale = bigger features
        octaves = noise_settings.get("octaves", 6)
        persistence = noise_settings.get("persistence", 0.5)
        lacunarity = noise_settings.get("lacunarity", 2.0)
        
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
        
        # Shift distribution significantly upward to favor land biomes
        # The noise naturally tends toward 0.5, but we need more land than water
        # Strategy: Very strong upward shift, then power curve for variation
        
        # Shift the entire distribution upward: Map [0, 1] to [0.5, 1.0]
        # This ensures most tiles are land (height > 0.5 normalized = height > 0.0 world)
        # Beach starts at 0.5, so we want most values above 0.6 (tundra/plains/desert)
        normalized = 0.5 + normalized * 0.5
        
        # Apply power curve to create variation at extremes
        # Lower values stay low (for water/beach), higher values get pushed up (for mountains)
        if normalized < 0.65:
            # Compress lower values but keep some in water/beach range
            normalized = 0.5 + (normalized - 0.5) * 0.4
        else:
            # Expand higher values upward for mountains/snow
            normalized = 0.65 + pow((normalized - 0.65) / 0.35, 0.55) * 0.35
        
        # Final spread: multiply deviation to increase variation
        # This creates distinct biome zones
        center = 0.7  # High center to favor land biomes (tundra/plains/desert/forest)
        normalized = center + (normalized - center) * 1.1
        
        # Clamp to [0.0, 1.0] range to ensure valid biome lookup
        return max(0.0, min(1.0, normalized))
    
    def get_temperature_value(self, world_x, world_y):
        """
        Get continuous temperature value for any world coordinate.
        
        Temperature is influenced by both noise (base temperature) and height:
        - Higher regions are colder (mountains, snow)
        - Lower regions are warmer (valleys, plains)
        - Base temperature from noise provides regional variation
        
        Returns normalized temperature value [0.0, 1.0] where:
        - 0.0 = cold (tundra, snow)
        - 1.0 = warm (desert, tropical)
        
        This ensures world continuity across chunks!
        
        Args:
            world_x: World X coordinate (tile coordinate)
            world_y: World Y coordinate (tile coordinate)
            
        Returns:
            Normalized temperature value in [0.0, 1.0] range
        """
        # Get noise settings (support both "noise_settings" and "noisesettings" for compatibility)
        noise_settings = self.config.get("noise_settings") or self.config.get("noisesettings", {})
        
        scale = noise_settings.get("temp_scale", 300.0)  # Temperature scale (larger = bigger temperature zones)
        octaves = noise_settings.get("temp_octaves", 4)  # Temperature octaves
        persistence = noise_settings.get("temp_persistence", 0.5)  # Temperature persistence
        lacunarity = noise_settings.get("temp_lacunarity", 2.0)  # Temperature lacunarity
        
        amplitude = 1.0
        frequency = 1.0
        noise_value = 0.0
        max_value = 0.0
        
        # Multi-octave noise for natural temperature variation
        for _ in range(octaves):
            sample_x = world_x / scale * frequency
            sample_y = world_y / scale * frequency
            
            noise_value += self.temp_noise.noise2(sample_x, sample_y) * amplitude
            max_value += amplitude
            
            amplitude *= persistence
            frequency *= lacunarity
        
        # Normalize to [0, 1] range (base temperature from noise)
        base = (noise_value / max_value + 1.0) / 2.0
        
        # Shift temperature distribution to center around 0.5 (moderate)
        # This ensures we get both cold and warm regions
        # Map [0, 1] to approximately [0.2, 0.8] to avoid extremes in base temperature
        base = 0.2 + base * 0.6
        
        # Apply power curve to create more variation at extremes
        # This ensures we get both cold areas (tundra: temp < 0.30) and warm areas (desert: temp > 0.70)
        if base < 0.5:
            # Push colder values even colder (for tundra/snow)
            # Use stronger curve to get values below 0.30
            base = 0.2 + pow((base - 0.2) / 0.3, 0.5) * 0.3
        else:
            # Push warmer values even warmer (for desert)
            base = 0.5 + pow((base - 0.5) / 0.3, 0.5) * 0.3
        
        # Additional spread: multiply deviation to cover full range [0.0, 1.0]
        # This ensures we get temperatures from ~0.0 (cold) to ~1.0 (warm)
        base = 0.5 + (base - 0.5) * 2.0
        
        # Adjust temperature based on height: higher regions are colder
        # Get height value (this ensures consistency with biome determination)
        height = self.get_noise_value(world_x, world_y)
        
        # Cool down with height: subtract (height - 0.5) * 1.0
        # At height 0.5 (middle): no change
        # At height 1.0 (high): subtract 0.5 (much colder)
        # At height 0.0 (low): add 0.5 (much warmer)
        # Increased from 0.8 to 1.0 to make height effect very strong
        # This ensures high mountains are cold enough for snow/tundra
        temp = base - (height - 0.5) * 1.0
        
        # Clamp to [0.0, 1.0] range
        return max(0.0, min(1.0, temp))
    
    def get_biome(self, height_value, temperature_value):
        """
        Determine biome based on normalized height and temperature values [0, 1]
        
        Uses pre-calculated normalized height and temperature ranges for efficient lookup.
        Checks both height and temperature ranges to find matching biome.
        
        Args:
            height_value: Normalized height value in [0, 1] range
            temperature_value: Normalized temperature value in [0, 1] range (0.0 = cold, 1.0 = warm)
        
        Returns:
            Tuple of (biome_id, biome_data)
        """
        # Linear search through biomes (check both height and temperature)
        # For few biomes (<20), linear search is fast enough
        for biome_id, biome_data in self.sorted_biomes:
            # Use pre-calculated normalized values (no recalculation needed!)
            h_min_norm = biome_data["height_min_norm"]
            h_max_norm = biome_data["height_max_norm"]
            t_min_norm = biome_data["temp_min_norm"]
            t_max_norm = biome_data["temp_max_norm"]
            
            # Check if both height and temperature match
            if (h_min_norm <= height_value <= h_max_norm and 
                t_min_norm <= temperature_value <= t_max_norm):
                return biome_id, biome_data
        
        # Fallback: Find best matching biome by height (temperature-agnostic)
        # This ensures we always return a valid biome
        for biome_id, biome_data in self.sorted_biomes:
            h_min_norm = biome_data["height_min_norm"]
            h_max_norm = biome_data["height_max_norm"]
            
            if h_min_norm <= height_value <= h_max_norm:
                return biome_id, biome_data
        
        # Final fallback: last biome (highest elevation)
        return self.sorted_biomes[-1]
    
    def generate_tile(self, world_x, world_y):
        """
        Generate a single tile at world coordinates
        
        PERFORMANCE: Returns minimal tile data (no resources!)
        Uses LRU cache to prevent unbounded memory growth during long play sessions.
        
        IMPORTANT: The returned tile structure (biome, height, temperature, tile_id, color, traversable)
        is binary-compatible with RegionManager.serialize_chunk(). Any changes to this
        structure must be reflected in RegionManager.serialize_chunk() and deserialize_chunk()
        to maintain compatibility.
        
        Args:
            world_x: World X coordinate (tile coordinate)
            world_y: World Y coordinate (tile coordinate)
        
        Returns:
            Dictionary with tile data (biome, height, temperature, tile_id, color, traversable)
        """
        cache_key = (world_x, world_y)
        
        # Check cache first (LRU: move to end if found)
        if cache_key in self._tile_cache:
            # Move to end (mark as recently used)
            tile = self._tile_cache.pop(cache_key)
            self._tile_cache[cache_key] = tile
            return tile
        
        # Get continuous noise values for height and temperature
        height = self.get_noise_value(world_x, world_y)
        temperature = self.get_temperature_value(world_x, world_y)
        
        # Determine biome based on both height and temperature
        biome_id, biome_data = self.get_biome(height, temperature)
        
        # Support both "tile_id" and "tileid" for compatibility
        tile_id = biome_data.get("tile_id") or biome_data.get("tileid", "core:unknown")
        
        tile = {
            "biome": biome_id,
            "height": float(height),
            "temperature": float(temperature),
            "tile_id": tile_id,
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
