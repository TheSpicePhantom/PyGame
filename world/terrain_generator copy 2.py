"""
Procedural Terrain Generator with OpenSimplex Noise
Generates continuous world heightmap, then splits into chunks
Optimized for performance - NO per-tile resource generation
"""
import json
import os
import random
import math
import numpy as np
from opensimplex import OpenSimplex
from collections import OrderedDict
from typing import Tuple
from pathlib import Path
from core import settings

# Water overlay threshold: tiles with water_mask > this value become water
# Higher threshold = less water, only in "very wet" mask areas
WATER_THRESHOLD = 0.75  # Higher threshold for less water (only very wet areas)


# ---------- Remapping Functions with Guaranteed Proportions ----------

def remap_height(u):
    """
    Remap uniform noise value u (0..1) to height distribution with guaranteed proportions.
    
    Target distribution:
    - 15% low values (0.0-0.35): Water/Beach range
    - 50% mid values (0.35-0.65): Plains/Forest range
    - 25% high values (0.65-0.85): Mountains range
    - 10% very high values (0.85-1.0): Snow peaks
    
    Args:
        u: Uniform noise value in [0.0, 1.0] range
        
    Returns:
        Remapped height value in [0.0, 1.0] range with guaranteed proportions
    """
    # Clamp input to [0.0, 1.0]
    u = max(0.0, min(1.0, u))
    
    # Define guaranteed proportions
    LOW_PROPORTION = 0.15      # 15% low (water/beach)
    MID_PROPORTION = 0.50      # 50% mid (plains/forest)
    HIGH_PROPORTION = 0.25     # 25% high (mountains)
    PEAK_PROPORTION = 0.10     # 10% very high (snow peaks)
    
    # Map uniform input to these ranges
    if u < LOW_PROPORTION:
        # Low range: [0.0, 0.15) → [0.0, 0.35)
        t = u / LOW_PROPORTION
        return 0.0 + t * 0.35
    elif u < LOW_PROPORTION + MID_PROPORTION:
        # Mid range: [0.15, 0.65) → [0.35, 0.65)
        t = (u - LOW_PROPORTION) / MID_PROPORTION
        return 0.35 + t * 0.30
    elif u < LOW_PROPORTION + MID_PROPORTION + HIGH_PROPORTION:
        # High range: [0.65, 0.90) → [0.65, 0.85)
        t = (u - LOW_PROPORTION - MID_PROPORTION) / HIGH_PROPORTION
        return 0.65 + t * 0.20
    else:
        # Peak range: [0.90, 1.0] → [0.85, 1.0]
        t = (u - LOW_PROPORTION - MID_PROPORTION - HIGH_PROPORTION) / PEAK_PROPORTION
        return 0.85 + t * 0.15


def remap_temp(u):
    """
    Remap uniform noise value u (0..1) to temperature distribution with guaranteed proportions.
    
    Target distribution:
    - 20% cold (0.0-0.35): Tundra/Snow range
    - 60% moderate (0.35-0.70): Plains/Forest range
    - 20% warm (0.70-1.0): Desert/Savanna range
    
    Args:
        u: Uniform noise value in [0.0, 1.0] range
        
    Returns:
        Remapped temperature value in [0.0, 1.0] range with guaranteed proportions
    """
    # Clamp input to [0.0, 1.0]
    u = max(0.0, min(1.0, u))
    
    # Define guaranteed proportions
    COLD_PROPORTION = 0.20      # 20% cold (tundra/snow)
    MODERATE_PROPORTION = 0.60  # 60% moderate (plains/forest)
    WARM_PROPORTION = 0.20      # 20% warm (desert/savanna)
    
    # Map uniform input to these ranges
    if u < COLD_PROPORTION:
        # Cold range: [0.0, 0.20) → [0.0, 0.35)
        t = u / COLD_PROPORTION
        return 0.0 + t * 0.35
    elif u < COLD_PROPORTION + MODERATE_PROPORTION:
        # Moderate range: [0.20, 0.80) → [0.35, 0.70)
        t = (u - COLD_PROPORTION) / MODERATE_PROPORTION
        return 0.35 + t * 0.35
    else:
        # Warm range: [0.80, 1.0] → [0.70, 1.0]
        t = (u - COLD_PROPORTION - MODERATE_PROPORTION) / WARM_PROPORTION
        return 0.70 + t * 0.30


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
        self.water_noise = OpenSimplex(seed=self.seed + 100)  # Third noise generator for water mask
        self.region_noise = OpenSimplex(seed=self.seed + 200)  # Fourth noise generator for region layer
        self.humidity_noise = OpenSimplex(seed=self.seed + 300)  # Fifth noise generator for humidity
        self.erosion_noise = OpenSimplex(seed=self.seed + 400)  # Sixth noise generator for erosion
        self.cont_noise = OpenSimplex(seed=self.seed + 500)  # Seventh noise generator for continentalness
        
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
        self.water_noise = OpenSimplex(seed=self.seed + 100)  # Reinitialize water noise
        self.region_noise = OpenSimplex(seed=self.seed + 200)  # Reinitialize region noise
        self.humidity_noise = OpenSimplex(seed=self.seed + 300)  # Reinitialize humidity noise
        self.erosion_noise = OpenSimplex(seed=self.seed + 400)  # Reinitialize erosion noise
        self.cont_noise = OpenSimplex(seed=self.seed + 500)  # Reinitialize continentalness noise
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
        
        # Separate biomes into land and water biomes
        # Water biomes are identified by having "water" in their name (e.g., "terrain:water_deep")
        # Beach is excluded from land_biomes - it's only set in the beach overlay pass
        self.land_biomes = {
            k: v for k, v in self.config["biomes"].items()
            if "water" not in k.lower() and k != "terrain:beach"
        }
        self.water_biomes = {
            k: v for k, v in self.config["biomes"].items()
            if "water" in k.lower()
        }
        
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
        # Create separate sorted lists for land and water biomes
        self.sorted_land_biomes = sorted(
            [entry for entry in biome_list if entry[0] in self.land_biomes],
            key=lambda x: x[1]["height_min_norm"]
        )
        self.sorted_water_biomes = sorted(
            [entry for entry in biome_list if entry[0] in self.water_biomes],
            key=lambda x: x[1]["height_min_norm"]
        )
        # Keep sorted_biomes for backward compatibility (contains all biomes)
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
        
        # Re-separate biomes into land and water biomes
        # Beach is excluded from land_biomes - it's only set in the beach overlay pass
        self.land_biomes = {
            k: v for k, v in self.config["biomes"].items()
            if "water" not in k.lower() and k != "terrain:beach"
        }
        self.water_biomes = {
            k: v for k, v in self.config["biomes"].items()
            if "water" in k.lower()
        }
        
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
        
        # Re-sort biomes into separate lists for land and water
        self.sorted_land_biomes = sorted(
            [entry for entry in biome_list if entry[0] in self.land_biomes],
            key=lambda x: x[1]["height_min_norm"]
        )
        self.sorted_water_biomes = sorted(
            [entry for entry in biome_list if entry[0] in self.water_biomes],
            key=lambda x: x[1]["height_min_norm"]
        )
        # Keep sorted_biomes for backward compatibility (contains all biomes)
        self.sorted_biomes = sorted(
            biome_list,
            key=lambda x: x[1]["height_min_norm"]
        )
        
        # Clear cache to force regeneration with new biome ranges
        self._tile_cache.clear()
    
    # ============================================================================
    # LAYER 1: Base Region
    # ============================================================================
    
    def get_base_region(self, world_x, world_y):
        """
        Get base region type for a world coordinate (Layer 1).
        
        Defines large-scale "meta-biomes" using noise:
        - "wet": Forest/taiga/rainforest regions (0-33%)
        - "neutral": Plains, mixed forest regions (33-66%)
        - "dry": Steppe, desert, rocky mountain regions (66-100%)
        
        Uses a large scale (800 tiles) to create continent-sized regions.
        
        Args:
            world_x: World X coordinate (tile coordinate)
            world_y: World Y coordinate (tile coordinate)
            
        Returns:
            str: Region identifier ("wet", "neutral", or "dry")
        """
        # Large-scale noise for continent-sized regions
        scale = 1.0 / 800.0  # Large structures (800 tiles per region feature)
        
        # Sample noise (returns -1.0 to 1.0)
        n = self.region_noise.noise2(world_x * scale, world_y * scale)
        
        # Normalize to [0.0, 1.0] range
        r = (n + 1.0) / 2.0
        
        # Map to region types
        if r < 0.33:
            return "wet"      # Forest/taiga/rainforest regions
        elif r < 0.66:
            return "neutral"  # Plains, mixed forest regions
        else:
            return "dry"      # Steppe, desert, rocky mountain regions
    
    # ============================================================================
    # LAYER 2: Height
    # ============================================================================
    
    def spline_height(self, cont, erosion):
        """
        Calculate base height from continentalness and erosion using spline-like mapping.
        
        Creates consistent continent-sized height patterns:
        - Low continentalness (0.0-0.3) → Below sea level (ocean basins) [0.0-0.3]
        - Medium continentalness (0.3-0.7) → Coast/flatland [0.3-0.6]
        - High continentalness (0.7-1.0) + low erosion (0.0-0.5) → High mountains/plateaus [0.7-0.9]
        - High continentalness (0.7-1.0) + high erosion (0.5-1.0) → Rugged mountains [0.8-1.0]
        
        Args:
            cont: Continentalness value [0.0, 1.0]
            erosion: Erosion value [0.0, 1.0]
            
        Returns:
            Base height value in [0.0, 1.0] range
        """
        # Clamp inputs
        cont = max(0.0, min(1.0, cont))
        erosion = max(0.0, min(1.0, erosion))
        
        # Low continentalness → ocean basins (below sea level)
        if cont < 0.3:
            # Map [0.0, 0.3] to [0.0, 0.3] (below sea level)
            base_height = cont * 1.0  # Linear mapping
        # Medium continentalness → coast/flatland
        elif cont < 0.7:
            # Map [0.3, 0.7] to [0.3, 0.6] (coast to flatland)
            t = (cont - 0.3) / 0.4  # Normalize to [0, 1]
            base_height = 0.3 + t * 0.3  # Linear interpolation
        # High continentalness → mountains (erosion-dependent)
        else:
            # Map [0.7, 1.0] to [0.7, 1.0] with erosion influence
            t = (cont - 0.7) / 0.3  # Normalize to [0, 1]
            
            # Base height from continentalness: [0.7, 0.85]
            base_height = 0.7 + t * 0.15
            
            # Add erosion influence: low erosion → plateaus, high erosion → rugged peaks
            if erosion < 0.5:
                # Low erosion: smooth plateaus/highlands [0.7, 0.9]
                # Plateaus are high but smooth
                erosion_factor = erosion / 0.5  # [0, 1]
                base_height = 0.7 + (base_height - 0.7) * 2.0 + erosion_factor * 0.2  # Boost to plateaus
            else:
                # High erosion: rugged mountains [0.85, 1.0]
                # Rugged peaks are highest
                erosion_factor = (erosion - 0.5) / 0.5  # [0, 1]
                base_height = base_height + erosion_factor * 0.15  # Push towards peaks
        
        return max(0.0, min(1.0, base_height))
    
    def get_height_value(self, world_x, world_y):
        """
        Get normalized height value for any world coordinate (Layer 2).
        
        Height is derived from continentalness and erosion (base height) plus detail noise.
        This creates consistent continent-sized height patterns instead of random noise everywhere.
        
        Returns a continuous height value in [0.0, 1.0] range where:
        - 0.0 = lowest (deep water)
        - 1.0 = highest (snow peaks)
        
        This ensures world continuity across chunks!
        
        Args:
            world_x: World X coordinate (tile coordinate)
            world_y: World Y coordinate (tile coordinate)
            
        Returns:
            Normalized height value in [0.0, 1.0] range
        """
        # Get continentalness and erosion for base height calculation
        cont = self.get_continentalness_value(world_x, world_y)
        erosion = self.get_erosion_value(world_x, world_y)
        
        # Calculate base height from continentalness and erosion
        base_height = self.spline_height(cont, erosion)
        
        # Add detail noise for local variation (use existing height noise)
        noise_settings = self.config.get("noise_settings") or self.config.get("noisesettings", {})
        detail_scale = noise_settings.get("scale", 200.0)  # Detail scale
        detail_octaves = noise_settings.get("detail_octaves", 3)  # Fewer octaves for detail only
        detail_persistence = noise_settings.get("persistence", 0.5)
        detail_lacunarity = noise_settings.get("lacunarity", 2.0)
        detail_amplitude = noise_settings.get("detail_amplitude", 0.15)  # Small amplitude for subtle variation
        
        amplitude = 1.0
        frequency = 1.0
        noise_value = 0.0
        max_value = 0.0
        
        # Multi-octave detail noise
        for _ in range(detail_octaves):
            sample_x = world_x / detail_scale * frequency
            sample_y = world_y / detail_scale * frequency
            
            noise_value += self.noise.noise2(sample_x, sample_y) * amplitude
            max_value += amplitude
            
            amplitude *= detail_persistence
            frequency *= detail_lacunarity
        
        # Normalize detail noise to [-1, 1] range, then scale by amplitude
        detail_noise = ((noise_value / max_value + 1.0) / 2.0 - 0.5) * 2.0  # [-1, 1]
        detail_noise *= detail_amplitude  # Scale to small variation
        
        # Combine base height with detail noise
        height = base_height + detail_noise
        
        # Shift distribution upward to favor land biomes, but keep some variation
        # Goal: 40-50% tiles above 0.4, noticeable portion above 0.6, some above 0.8
        # But also keep some lower values (0.3-0.4) for water/coastal areas
        # Strategy: moderate upward shift with balanced distribution
        
        # First, shift the entire distribution upward moderately
        # Map [0.0, 1.0] to approximately [0.15, 1.0] to allow some low areas for water
        height = 0.15 + height * 0.85
        
        # Then apply a balanced curve to create variation across all ranges
        # This creates a more natural distribution with peaks in mid-to-high ranges
        if height < 0.4:
            # Lower values (water/beach range): [0.15, 0.4] → [0.15, 0.35]
            # Keep some low values for water, but compress slightly
            t = (height - 0.15) / 0.25  # Normalize to [0, 1]
            height = 0.15 + t * 0.20  # Compress to smaller range
        elif height < 0.6:
            # Mid values (plains/coast range): [0.4, 0.6] → [0.35, 0.55]
            # Moderate compression for mid-range
            t = (height - 0.4) / 0.2  # Normalize to [0, 1]
            height = 0.35 + t * 0.20  # Moderate range
        else:
            # Upper values (forest/mountains range): [0.6, 1.0] → [0.55, 1.0]
            # Expand upper values to create mountains, but not too extreme
            t = (height - 0.6) / 0.4  # Normalize to [0, 1]
            # Use moderate power curve to create peaks without overdoing it
            t_powered = t ** 0.8  # Moderate power curve
            height = 0.55 + t_powered * 0.45  # Expand to larger range, reaching up to 1.0
        
        # Clamp to [0.0, 1.0] range
        return max(0.0, min(1.0, height))
    
    def get_noise_value(self, world_x, world_y):
        """
        Get continuous noise value for any world coordinate (DEPRECATED).
        
        DEPRECATED: Use get_height_value() instead. This method is kept for
        backward compatibility and simply calls get_height_value().
        
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
            # Reduced expansion for higher values - less "stone" mountains, more snow peaks
            # Use gentler power curve to favor more moderate heights (Plains/Forest)
            # and push fewer tiles into extreme mountain range
            normalized = 0.65 + pow((normalized - 0.65) / 0.35, 0.65) * 0.35  # Changed from 0.55 to 0.65 (less aggressive)
        
        # Final spread: multiply deviation to increase variation
        # Reduced stretch to favor more moderate heights (Plains/Forest) vs. extreme mountains
        # This creates more tiles in 0.4-0.7 range (Plains/Forest) and fewer in 0.8-0.9 (pure mountains)
        center = 0.7  # High center to favor land biomes (tundra/plains/desert/forest)
        normalized = 0.5 + (normalized - 0.5) * 1.15  # Gentler stretch to favor moderate heights
        
        # Clamp to [0.0, 1.0] range to ensure valid biome lookup
        return max(0.0, min(1.0, normalized))
    
    # ============================================================================
    # LAYER 3: Temperature
    # ============================================================================
    
    def get_latitude_factor(self, world_y, world_height=None):
        """
        Get latitude factor for a world Y coordinate.
        
        Returns normalized latitude position [0.0, 1.0] where:
        - 0.0 = top edge (north pole)
        - 1.0 = bottom edge (south pole)
        
        If world_height is None, uses modulo to create repeating climate zones
        (useful for preview tools that generate small areas).
        
        Args:
            world_y: World Y coordinate (tile coordinate)
            world_height: Total world height in tiles (None = use modulo for repeating zones)
        
        Returns:
            Latitude factor in [0.0, 1.0] range
        """
        if world_height is None:
            # Use modulo to create repeating climate zones
            # This works well for preview tools that generate small areas
            # Creates a repeating pattern every 500 tiles (allows multiple zones in preview)
            zone_size = 500
            relative_y = world_y % zone_size
            return relative_y / float(zone_size - 1) if zone_size > 1 else 0.5
        
        if world_height <= 1:
            return 0.5  # Fallback for single-tile worlds
        return world_y / float(max(1, world_height - 1))
    
    def get_latitude_temperature(self, world_y, world_height=None):
        """
        Get base temperature based on latitude using a smooth curve.
        
        Creates a smooth North-South temperature gradient (cold-warm-cold)
        using a cosine function instead of hard bands.
        
        Args:
            world_y: World Y coordinate (tile coordinate)
            world_height: Total world height in tiles (None = use repeating zones)
        
        Returns:
            Base temperature value in [0.0, 1.0] range (~0.1 to ~0.9)
        """
        lat = self.get_latitude_factor(world_y, world_height)  # 0..1
        
        # Smooth North-South curve: cold-warm-cold
        # cos(0) = 1 (cold at north), cos(pi) = -1 (cold at south), cos(pi/2) = 0 (warm at equator)
        # Map: 0.5 - 0.4 * cos(pi * lat) gives ~0.1 (cold) to ~0.9 (warm)
        return 0.5 - 0.4 * math.cos(math.pi * lat)
    
    def get_temperature_value(self, world_x, world_y, world_height=None):
        """
        Get continuous temperature value for any world coordinate (Layer 3).
        
        Temperature is influenced by:
        1. Smooth latitude gradient (North-South: cold-warm-cold)
        2. Noise (local variation)
        3. Height (higher regions are colder)
        
        Returns normalized temperature value [0.0, 1.0] where:
        - 0.0 = cold (tundra, snow)
        - 1.0 = warm (desert, tropical)
        
        Uses smooth cosine-based latitude curve instead of hard bands.
        This ensures world continuity across chunks!
        
        Args:
            world_x: World X coordinate (tile coordinate)
            world_y: World Y coordinate (tile coordinate)
            world_height: Total world height in tiles (None = use repeating zones for preview tools)
            
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
        
        # 1) Noise temperature (local variation)
        # Normalize noise to [0, 1] range
        noise_temp = (noise_value / max_value + 1.0) / 2.0
        
        # 2) Smooth latitude temperature gradient (North-South: cold-warm-cold)
        lat_temp = self.get_latitude_temperature(world_y, world_height)
        
        # 3) Mix latitude gradient (40%) with noise (60%)
        # Noise dominates more → less "always cold" in large areas, more local variation
        temp = lat_temp * 0.4 + noise_temp * 0.6
        
        # 4) Height cools down less strongly (higher regions are colder, but not as much)
        # Weaker height cooling: medium and high elevations are not automatically tundra/snow
        height = self.get_height_value(world_x, world_y)
        temp -= (height - 0.5) * 0.3  # Reduced from 0.5 to 0.3
        
        # 5) Shift temperature upward to neutral/warm average (~0.6)
        # This makes Desert/Savanna/Plains compete more strongly with Snow/Tundra in distance score
        temp = 0.6 + (temp - 0.5) * 0.7  # Average ~0.6 instead of ~0.55
        
        # 6) Clamp to [0.0, 1.0] range
        return max(0.0, min(1.0, temp))
    
    # ============================================================================
    # CLIMATE VECTOR COMPONENTS
    # ============================================================================
    
    def get_humidity_value(self, world_x, world_y):
        """
        Get humidity value for any world coordinate (Climate Vector Component).
        
        Humidity controls forest vs. steppe/desert distribution.
        Higher humidity = more forests, lower humidity = more steppe/desert.
        
        Returns normalized humidity value [0.0, 1.0] where:
        - 0.0 = dry (desert, steppe)
        - 1.0 = humid (forest, rainforest)
        
        Args:
            world_x: World X coordinate (tile coordinate)
            world_y: World Y coordinate (tile coordinate)
            
        Returns:
            Normalized humidity value in [0.0, 1.0] range
        """
        # Get noise settings
        noise_settings = self.config.get("noise_settings") or self.config.get("noisesettings", {})
        
        # Humidity noise parameters: large scale, few octaves
        humidity_scale = noise_settings.get("humidity_scale", 400.0)  # Large scale for regional humidity zones
        humidity_octaves = noise_settings.get("humidity_octaves", 2)  # Few octaves for smooth transitions
        humidity_persistence = noise_settings.get("humidity_persistence", 0.5)
        humidity_lacunarity = noise_settings.get("humidity_lacunarity", 2.0)
        
        amplitude = 1.0
        frequency = 1.0
        noise_value = 0.0
        max_value = 0.0
        
        # Multi-octave noise for natural humidity variation
        for _ in range(humidity_octaves):
            sample_x = world_x / humidity_scale * frequency
            sample_y = world_y / humidity_scale * frequency
            
            noise_value += self.humidity_noise.noise2(sample_x, sample_y) * amplitude
            max_value += amplitude
            
            amplitude *= humidity_persistence
            frequency *= humidity_lacunarity
        
        # Normalize to [0, 1] range
        humidity = (noise_value / max_value + 1.0) / 2.0
        
        # Optional: Combine with temperature (warmer regions can be more humid)
        # For now, keep it simple - just noise-based
        
        # Clamp to [0.0, 1.0] range
        return max(0.0, min(1.0, humidity))
    
    def get_continentalness_value(self, world_x, world_y):
        """
        Get continentalness value for any world coordinate (Climate Vector Component).
        
        Continentalness represents distance from ocean: ocean ↔ coast ↔ inland.
        Controls ocean/beach distribution.
        
        Returns normalized continentalness value [0.0, 1.0] where:
        - 0.0 = ocean (far from land)
        - 0.5 = coast (transition zone)
        - 1.0 = inland (far from ocean)
        
        Args:
            world_x: World X coordinate (tile coordinate)
            world_y: World Y coordinate (tile coordinate)
            
        Returns:
            Normalized continentalness value in [0.0, 1.0] range
        """
        # Get noise settings
        noise_settings = self.config.get("noise_settings") or self.config.get("noisesettings", {})
        
        # Continentalness noise parameters: very large scale → continents/oceans
        continentalness_scale = noise_settings.get("continentalness_scale", 800.0)  # Very large scale for continent-sized features
        continentalness_octaves = noise_settings.get("continentalness_octaves", 2)  # Very few octaves for smooth continental transitions
        continentalness_persistence = noise_settings.get("continentalness_persistence", 0.5)
        continentalness_lacunarity = noise_settings.get("continentalness_lacunarity", 2.0)
        
        amplitude = 1.0
        frequency = 1.0
        noise_value = 0.0
        max_value = 0.0
        
        # Multi-octave noise for continental distribution
        for _ in range(continentalness_octaves):
            sample_x = world_x / continentalness_scale * frequency
            sample_y = world_y / continentalness_scale * frequency
            
            noise_value += self.cont_noise.noise2(sample_x, sample_y) * amplitude
            max_value += amplitude
            
            amplitude *= continentalness_persistence
            frequency *= continentalness_lacunarity
        
        # Normalize to [0, 1] range
        continentalness = (noise_value / max_value + 1.0) / 2.0
        
        # Clamp to [0.0, 1.0] range
        return max(0.0, min(1.0, continentalness))
    
    def get_erosion_value(self, world_x, world_y):
        """
        Get erosion value for any world coordinate (Climate Vector Component).
        
        Erosion represents terrain roughness: smooth vs. rugged.
        Controls mountains vs. gentle hills.
        
        Returns normalized erosion value [0.0, 1.0] where:
        - 0.0 = smooth (gentle hills, plains)
        - 1.0 = rugged (mountains, cliffs)
        
        Args:
            world_x: World X coordinate (tile coordinate)
            world_y: World Y coordinate (tile coordinate)
            
        Returns:
            Normalized erosion value in [0.0, 1.0] range
        """
        # Get noise settings
        noise_settings = self.config.get("noise_settings") or self.config.get("noisesettings", {})
        
        # Erosion noise parameters: medium scale, somewhat "rougher"
        erosion_scale = noise_settings.get("erosion_scale", 220.0)  # Medium scale for regional variation
        erosion_octaves = noise_settings.get("erosion_octaves", 4)  # More octaves for detail
        erosion_persistence = noise_settings.get("erosion_persistence", 0.6)  # Higher persistence for rougher terrain
        erosion_lacunarity = noise_settings.get("erosion_lacunarity", 2.2)  # Slightly higher lacunarity for more variation
        
        amplitude = 1.0
        frequency = 1.0
        noise_value = 0.0
        max_value = 0.0
        
        # Multi-octave noise for erosion variation
        for _ in range(erosion_octaves):
            sample_x = world_x / erosion_scale * frequency
            sample_y = world_y / erosion_scale * frequency
            
            noise_value += self.erosion_noise.noise2(sample_x, sample_y) * amplitude
            max_value += amplitude
            
            amplitude *= erosion_persistence
            frequency *= erosion_lacunarity
        
        # Normalize to [0, 1] range
        erosion = (noise_value / max_value + 1.0) / 2.0
        
        # Optional: Combine with height (higher regions tend to be more eroded)
        # For now, keep it simple - just noise-based
        
        # Clamp to [0.0, 1.0] range
        return max(0.0, min(1.0, erosion))
    
    # ============================================================================
    # LAYER 4: Water Mask
    # ============================================================================
    
    def get_water_mask(self, world_x, world_y):
        """
        Get water mask value for any world coordinate (Layer 4).
        
        Uses noise-based water distribution. Returns a value in [0.0, 1.0] range where:
        - 0.0 = no water (land)
        - 1.0 = water (ocean/lake)
        
        Water placement is determined separately in should_place_water() based on
        height and mask threshold.
        
        Args:
            world_x: World X coordinate (tile coordinate)
            world_y: World Y coordinate (tile coordinate)
        
        Returns:
            Water mask value in [0.0, 1.0] range
        """
        # Get noise settings (support both "noise_settings" and "noisesettings" for compatibility)
        noise_settings = self.config.get("noise_settings") or self.config.get("noisesettings", {})
        
        # Water noise parameters
        water_scale = noise_settings.get("water_scale", 300.0)  # Water scale (larger = bigger water bodies)
        water_octaves = noise_settings.get("water_octaves", 4)  # Water octaves
        water_persistence = noise_settings.get("water_persistence", 0.5)  # Water persistence
        water_lacunarity = noise_settings.get("water_lacunarity", 2.0)  # Water lacunarity
        
        amplitude = 1.0
        frequency = 1.0
        noise_value = 0.0
        max_value = 0.0
        
        # Multi-octave noise for natural water distribution
        for _ in range(water_octaves):
            sample_x = world_x / water_scale * frequency
            sample_y = world_y / water_scale * frequency
            
            noise_value += self.water_noise.noise2(sample_x, sample_y) * amplitude
            max_value += amplitude
            
            amplitude *= water_persistence
            frequency *= water_lacunarity
        
        # Normalize noise to [0, 1] range
        mask = (noise_value / max_value + 1.0) / 2.0
        
        # Reduce extremes: compress towards center for smoother water distribution
        # This creates less extreme values, leading to more controlled water placement
        mask = 0.5 + (mask - 0.5) * 0.7
        
        # Clamp to [0.0, 1.0] range
        return max(0.0, min(1.0, mask))
    
    # ============================================================================
    # BIOME RESOLVER
    # ============================================================================
    
    def resolve_biome(self, region, height, temp, humid, cont, eros):
        """
        Resolve biome from region, height, and climate vector using distance-based scoring.
        
        This is the central function that determines which biome a tile should have
        based on all layer values. Uses climate distance (weighted euclidean) to find
        the best matching biome, combined with region-based bias.
        
        Process:
        1. Filter candidates by height_min/max (coarse filtering)
        2. Calculate weighted climate distance for each candidate
        3. Convert distance to score: score = 1.0 / (distance + epsilon)
        4. Apply region-based bias
        5. Select biome with highest score
        
        Args:
            region: Region identifier (from Layer 1: get_base_region) - "wet", "neutral", or "dry"
            height: Normalized height value [0.0, 1.0] (from Layer 2: get_height_value)
            temp: Normalized temperature value [0.0, 1.0] (from Layer 3: get_temperature_value)
            humid: Normalized humidity value [0.0, 1.0] (from Climate Vector)
            cont: Normalized continentalness value [0.0, 1.0] (from Climate Vector)
            eros: Normalized erosion value [0.0, 1.0] (from Climate Vector)
            
        Returns:
            Tuple of (biome_id, biome_data) for the resolved biome
        """
        # NOTE: Beach is no longer set here - it's applied in Pass 2 (apply_beach_overlay_to_chunk)
        # where land directly borders shallow water. Deep areas will be handled by water overlay.
        
        # Climate distance weights (can be adjusted for different importance)
        WEIGHT_TEMP = 1.0
        WEIGHT_HUMID = 1.0
        WEIGHT_CONT = 0.8  # Slightly less important
        WEIGHT_EROS = 0.6  # Less important than temp/humidity
        EPSILON = 0.01  # Small value to prevent division by zero
        
        # 1. Filter candidates by height_min/max (coarse filtering)
        # Only consider terrain biomes (exclude water biomes)
        candidates = []
        for biome_id, biome_data in self.sorted_land_biomes:
            # Get pre-calculated normalized height ranges
            h_min_norm = biome_data.get("height_min_norm", 0.0)
            h_max_norm = biome_data.get("height_max_norm", 1.0)
            
            # Coarse filtering: only check height range
            if h_min_norm <= height <= h_max_norm:
                candidates.append((biome_id, biome_data))
        
        # If no candidates found, fallback to get_land_biome
        if not candidates:
            return self.get_land_biome(height, temp)
        
        # 2. Calculate climate distance for each candidate
        scored = []
        for biome_id, biome_data in candidates:
            # Get target climate values from biome config
            target_temp = biome_data.get("target_temp")
            target_humid = biome_data.get("target_humidity")
            target_cont = biome_data.get("target_continentalness")
            target_eros = biome_data.get("target_erosion")
            
            # If target values not available, skip climate distance (use fallback)
            if (target_temp is None or target_humid is None or 
                target_cont is None or target_eros is None):
                # Fallback: use simple region-based scoring
                score = 1.0
                if region == "wet":
                    if "forest" in biome_id.lower() or "plains" in biome_id.lower():
                        score *= 1.3
                    if "desert" in biome_id.lower():
                        score *= 0.3
                elif region == "dry":
                    if "desert" in biome_id.lower() or "mountains" in biome_id.lower():
                        score *= 1.3
                scored.append((score, biome_id, biome_data))
                continue
            
            # Calculate weighted euclidean distance
            # d = sqrt(w_T * (temp - T_b)^2 + w_H * (humid - H_b)^2 + w_C * (cont - C_b)^2 + w_E * (eros - E_b)^2)
            d_temp = (temp - target_temp) ** 2
            d_humid = (humid - target_humid) ** 2
            d_cont = (cont - target_cont) ** 2
            d_eros = (eros - target_eros) ** 2
            
            distance = math.sqrt(
                WEIGHT_TEMP * d_temp +
                WEIGHT_HUMID * d_humid +
                WEIGHT_CONT * d_cont +
                WEIGHT_EROS * d_eros
            )
            
            # Convert distance to score: score = 1.0 / (distance + epsilon)
            # Smaller distance = higher score
            score = 1.0 / (distance + EPSILON)
            
            # 3. Apply region-based bias
            if region == "wet":
                # Wet regions favor: forest, plains, tundra
                if "forest" in biome_id.lower() or "plains" in biome_id.lower() or "tundra" in biome_id.lower():
                    score *= 1.3
                # Wet regions disfavor: desert
                if "desert" in biome_id.lower():
                    score *= 0.3
            
            elif region == "dry":
                # Dry regions favor: desert, mountains
                if "desert" in biome_id.lower() or "mountains" in biome_id.lower():
                    score *= 1.3
                # Dry regions slightly disfavor: tundra, snow
                if "tundra" in biome_id.lower() or "snow" in biome_id.lower():
                    score *= 0.7
            
            # neutral: no bias (score stays as is)
            
            scored.append((score, biome_id, biome_data))
        
        # 4. Sort by score (highest first)
        scored.sort(reverse=True, key=lambda s: s[0])
        
        # 5. Return best matching biome (highest score)
        best_score, best_biome_id, best_biome_data = scored[0]
        return best_biome_id, best_biome_data
    
    def get_land_biome(self, height_value, temperature_value):
        """
        Helper function to determine land biome based on normalized height and temperature values [0, 1].
        
        This is used as a fallback by resolve_biome() when no region-biased candidates are found.
        Only searches through land biomes (excludes water biomes).
        Uses pre-calculated normalized height and temperature ranges for efficient lookup.
        Checks both height and temperature ranges to find matching biome.
        
        Args:
            height_value: Normalized height value in [0, 1] range
            temperature_value: Normalized temperature value in [0, 1] range (0.0 = cold, 1.0 = warm)
        
        Returns:
            Tuple of (biome_id, biome_data)
        """
        # Linear search through land biomes only (check both height and temperature)
        # For few biomes (<20), linear search is fast enough
        for biome_id, biome_data in self.sorted_land_biomes:
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
        for biome_id, biome_data in self.sorted_land_biomes:
            h_min_norm = biome_data["height_min_norm"]
            h_max_norm = biome_data["height_max_norm"]
            
            if h_min_norm <= height_value <= h_max_norm:
                return biome_id, biome_data
        
        # Final fallback: last land biome (highest elevation)
        return self.sorted_land_biomes[-1]
    
    def get_water_biome(self, height_value, temperature_value):
        """
        Determine water biome based on normalized height and temperature values [0, 1]
        
        Only searches through water biomes (excludes land biomes).
        Uses pre-calculated normalized height and temperature ranges for efficient lookup.
        Checks both height and temperature ranges to find matching biome.
        
        Args:
            height_value: Normalized height value in [0, 1] range
            temperature_value: Normalized temperature value in [0, 1] range (0.0 = cold, 1.0 = warm)
        
        Returns:
            Tuple of (biome_id, biome_data)
        """
        # Linear search through water biomes only (check both height and temperature)
        for biome_id, biome_data in self.sorted_water_biomes:
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
        for biome_id, biome_data in self.sorted_water_biomes:
                h_min_norm = biome_data["height_min_norm"]
                h_max_norm = biome_data["height_max_norm"]
                
                if h_min_norm <= height_value <= h_max_norm:
                    return biome_id, biome_data
        
        # Final fallback: last water biome (highest elevation)
        if self.sorted_water_biomes:
            return self.sorted_water_biomes[-1]
        # If no water biomes exist, return None (should not happen in normal operation)
        return None, None
    
    def get_biome(self, height_value, temperature_value):
        """
        Determine biome based on normalized height and temperature values [0, 1]
        
        DEPRECATED: Use get_land_biome() or get_water_biome() instead.
        This method searches through all biomes for backward compatibility.
        
        Args:
            height_value: Normalized height value in [0, 1] range
            temperature_value: Normalized temperature value in [0, 1] range (0.0 = cold, 1.0 = warm)
        
        Returns:
            Tuple of (biome_id, biome_data)
        """
        # Linear search through all biomes (check both height and temperature)
        for biome_id, biome_data in self.sorted_biomes:
            h_min_norm = biome_data["height_min_norm"]
            h_max_norm = biome_data["height_max_norm"]
            t_min_norm = biome_data["temp_min_norm"]
            t_max_norm = biome_data["temp_max_norm"]
            
            if (h_min_norm <= height_value <= h_max_norm and 
                t_min_norm <= temperature_value <= t_max_norm):
                return biome_id, biome_data
        
        # Fallback: Find best matching biome by height
        for biome_id, biome_data in self.sorted_biomes:
            h_min_norm = biome_data["height_min_norm"]
            h_max_norm = biome_data["height_max_norm"]
            
            if h_min_norm <= height_value <= h_max_norm:
                return biome_id, biome_data
        
        # Final fallback: last biome (highest elevation)
        return self.sorted_biomes[-1]
    
    def generate_tile(self, world_x, world_y):
        """
        Generate a single tile at world coordinates using the layer-based architecture.
        
        This method queries all layers and resolves the biome:
        1. Layer 1: Base Region (get_base_region)
        2. Layer 2: Height (get_height_value)
        3. Layer 3: Temperature (get_temperature_value)
        4. Biome Resolution: resolve_biome(region, height, temp)
        
        Water overlay is applied separately in apply_water_overlay_to_chunk().
        
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
        
        # ========================================================================
        # LAYER-BASED GENERATION
        # ========================================================================
        # Query all layers
        region = self.get_base_region(world_x, world_y)  # Layer 1: Base Region
        height = self.get_height_value(world_x, world_y)  # Layer 2: Height
        temperature = self.get_temperature_value(world_x, world_y)  # Layer 3: Temperature
        
        # Climate Vector Components
        temp = self.get_temperature_value(world_x, world_y)  # Climate: Temperature
        humid = self.get_humidity_value(world_x, world_y)  # Climate: Humidity
        cont = self.get_continentalness_value(world_x, world_y)  # Climate: Continentalness
        eros = self.get_erosion_value(world_x, world_y)  # Climate: Erosion
        
        # Resolve biome from layers using central resolver (climate distance-based)
        biome_id, biome_data = self.resolve_biome(region, height, temp, humid, cont, eros)
        
        # Support both "tile_id" and "tileid" for compatibility
        # Always use terrain:* format (never core:*)
        tile_id = biome_data.get("tile_id") or biome_data.get("tileid", "terrain:unknown")
        
        # Ensure tileid is terrain:* format (not core:*)
        # Convert core:* to terrain:* by replacing prefix
        if tile_id.startswith("core:"):
            tile_id = tile_id.replace("core:", "terrain:", 1)
        elif not tile_id.startswith("terrain:"):
            # If it doesn't start with terrain:, add the prefix
            tile_id = f"terrain:{tile_id}"
        
        # ========================================================================
        # TILE STRUCTURE
        # ========================================================================
        # Build tile structure from resolved biome and layer values
        tile = {
            "base_biome": biome_id,
            "biome": biome_id,
            "height": float(height),
            "temperature": float(temp),
            "tileid": tile_id,  # Always terrain:*
            "color": tuple(biome_data["color"]),
            "traversable": biome_data["traversable"],
            # Debug information: store layer values for debugging
            "region": region,  # Layer 1: Base Region (wet/neutral/dry)
            # Climate Vector: v = (temp, humidity, continentalness, erosion)
            "humidity": float(humid),  # Climate: Humidity (0.0 = dry, 1.0 = humid)
            "continentalness": float(cont),  # Climate: Continentalness (0.0 = ocean, 1.0 = inland)
            "erosion": float(eros),  # Climate: Erosion (0.0 = smooth, 1.0 = rugged)
            # Climate vector as tuple for easy access: v = (temp, humid, cont, eros)
            "climate": (float(temp), float(humid), float(cont), float(eros)),
            # height and temperature already stored above
            # NO "resources" field = massive performance gain!
        }
        
        # NOTE: Water overlay is applied separately in apply_water_overlay_to_chunk()
        # This keeps the generation pipeline clean: land first, then water overlay
        
        # Cache result (add to end = most recently used)
        self._tile_cache[cache_key] = tile
        
        # Evict oldest entries if cache exceeds max size
        while len(self._tile_cache) > self._tile_cache_max_size:
            # Remove oldest (first item)
            self._tile_cache.popitem(last=False)
        
        return tile
    
    def _generate_land_chunk(self, chunk_x, chunk_y, chunk_size=None):
        """
        Generate a land chunk (first pass) - only terrain:* biomes, no water.
        
        This is a private helper method that generates the base terrain with land biomes only.
        Water overlay is applied separately in apply_water_overlay_to_chunk().
        
        This ensures chunks connect seamlessly!
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate  
            chunk_size: Tiles per chunk (defaults to settings.CHUNK_SIZE if None)
        
        Returns:
            2D list of tile dictionaries (all terrain:* biomes, no water)
        
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
                
                # Generate tile from continuous world function (only land biomes)
                # generate_tile uses resolve_biome which only returns land biomes
                tile = self.generate_tile(world_x, world_y)
                row.append(tile)
            
            tiles.append(row)
        
        return tiles
    
    def generate_chunk(self, chunk_x, chunk_y, chunk_size=None):
        """
        Generate a complete chunk with land biomes and water overlay (2-Pass Flow).
        
        This is the main entry point for chunk generation. It follows a clear 2-pass flow:
        1. Pass 1: Generate land chunk (terrain:* biomes only, no water, no beach) via _generate_land_chunk()
        2. Pass 2: Apply water overlay (3-step process):
           - Step 1: Set water tiles based on water_mask (all initially shallow)
           - Step 2: Classify water depth (convert inner water to deep)
           - Step 3: Apply beach overlay (beach only at shallow water edges)
        
        This ensures:
        - Beach exists only directly next to water:shallow
        - water:deep can never directly touch land (always shallow water ring)
        - Small "beach patches" inland automatically disappear
        
        This ensures chunks connect seamlessly and water distribution is consistent!
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate  
            chunk_size: Tiles per chunk (defaults to settings.CHUNK_SIZE if None)
        
        Returns:
            2D list of tile dictionaries (terrain:* and water:* biomes)
        
        Raises:
            AssertionError: If chunk_size doesn't match settings.CHUNK_SIZE (prevents mismatches)
        """
        # Pass 1: Generate land chunk (only terrain:* biomes, no water, no beach)
        tiles = self._generate_land_chunk(chunk_x, chunk_y, chunk_size)
        
        # Pass 2: Apply water overlay (3-step process)
        # Step 1: Set water tiles based on water_mask (all initially shallow)
        self.apply_water_overlay_to_chunk(tiles, chunk_x, chunk_y)
        
        # Step 2: Classify water depth (convert inner water to deep)
        self.classify_water_depth_in_chunk(tiles, chunk_x, chunk_y)
        
        # Step 3: Apply beach overlay (beach only at shallow water edges)
        self.apply_beach_overlay_to_chunk(tiles, chunk_x, chunk_y)
        
        return tiles
    
    def clear_cache(self):
        """Clear tile cache (useful when changing seeds)"""
        self._tile_cache.clear()
    
    def should_place_water(self, height, water_mask, continentalness):
        """
        Determine if water should be placed at this location.
        
        Combines water_mask threshold with height and continentalness to decide if tile should become water.
        - Lower heights are more likely to have water
        - Low continentalness (ocean basins) → high water chance, even at higher heights
        - High continentalness (inland) → low water chance, even at lower heights
        
        This creates connected oceans and inland continents like in Minecraft, where continentalness
        defines large-scale ocean/inland structure, while height and water_mask add local variation.
        
        Parameters are tuned to achieve 10-20% water coverage overall.
        
        Args:
            height: Normalized height value [0.0, 1.0]
            water_mask: Water mask value [0.0, 1.0]
            continentalness: Normalized continentalness value [0.0, 1.0] (0.0 = ocean, 1.0 = inland)
        
        Returns:
            True if water should be placed, False otherwise
        """
        # Height factor: lower heights are more likely to have water
        height_factor = 1.0 - height  # 1.0 at height 0.0, 0.0 at height 1.0
        
        # Continentalness factor: low continentalness = ocean basins (high water chance)
        # High continentalness = inland (low water chance)
        # Invert continentalness: low cont (0.0) → high water chance, high cont (1.0) → low water chance
        cont_factor = 1.0 - continentalness  # 1.0 at cont 0.0 (ocean), 0.0 at cont 1.0 (inland)
        
        # Weaker height influence: subtract a small amount from threshold based on height
        # Lower heights reduce threshold slightly (making water more likely)
        # Higher threshold (0.75) means water only in very wet mask areas
        height_adjustment = height_factor * 0.2  # Weaker height influence (was 0.4 in combined_factor)
        
        # Continentalness still influences water placement, but more subtly
        # Low continentalness (ocean basins) can slightly reduce threshold
        cont_adjustment = cont_factor * 0.1  # Subtle continentalness influence
        
        # Calculate adjusted threshold: subtract adjustments from base threshold
        # Higher base threshold (0.75) - small adjustments = water only in very wet areas
        adjusted_threshold = WATER_THRESHOLD - height_adjustment - cont_adjustment
        
        return water_mask > adjusted_threshold
    
    def pick_water_biome(self, height, water_mask):
        """
        Pick appropriate water biome based on height and water mask depth.
        
        Uses depth calculation: depth = water_mask * (1.0 - height)
        - Higher depth → deep water
        - Lower depth → shallow water
        
        This creates shallow fringes around islands and deep cores in oceans.
        
        Args:
            height: Normalized height value [0.0, 1.0]
            water_mask: Water mask value [0.0, 1.0]
        
        Returns:
            Tuple of (water_biome_id, water_biome_data)
        """
        # Calculate depth: combination of water_mask and height
        # Lower height + higher mask = deeper water
        depth = water_mask * (1.0 - height)
        
        # Determine water biome based on depth
        if depth > 0.5:
            # Deep water: high mask + low height
            biome_id = "water:deep"
        else:
            # Shallow water: lower mask or higher height (coastal areas)
            biome_id = "water:shallow"
        
        # Get biome data from config
        if biome_id in self.config.get("biomes", {}):
            return biome_id, self.config["biomes"][biome_id]
        
        # Fallback: use first available water biome
        if self.sorted_water_biomes:
            return self.sorted_water_biomes[0]
        
        return None, None
    
    def is_water(self, tile):
        """
        Check if a tile is water.
        
        Args:
            tile: Tile dictionary
            
        Returns:
            True if tile is water, False otherwise
        """
        biome_id = tile.get("biome", "")
        return biome_id.startswith("water:")
    
    def is_shallow_water(self, tile):
        """
        Check if a tile is shallow water.
        
        Args:
            tile: Tile dictionary
            
        Returns:
            True if tile is shallow water, False otherwise
        """
        biome_id = tile.get("biome", "")
        return biome_id == "water:shallow"
    
    def get_neighbors(self, tiles, x, y, use_8_neighbors=True):
        """
        Get neighboring tiles around position (x, y).
        
        Args:
            tiles: 2D list of tile dictionaries
            x: X coordinate in tiles array
            y: Y coordinate in tiles array
            use_8_neighbors: If True, use 8-neighborhood (including diagonals), else 4-neighborhood
            
        Returns:
            List of neighboring tile dictionaries (empty list if out of bounds)
        """
        neighbors = []
        h = len(tiles)
        w = len(tiles[0]) if h > 0 else 0
        
        # 8-neighborhood offsets (including diagonals)
        offsets = [
            (-1, -1), (-1, 0), (-1, 1),
            (0, -1),           (0, 1),
            (1, -1),  (1, 0),  (1, 1)
        ] if use_8_neighbors else [
            (-1, 0), (0, -1), (0, 1), (1, 0)  # 4-neighborhood (cardinal directions)
        ]
        
        for dx, dy in offsets:
            nx, ny = x + dx, y + dy
            if 0 <= ny < h and 0 <= nx < w:
                neighbors.append(tiles[ny][nx])
        
        return neighbors
    
    def classify_water_depth_in_chunk(self, tiles, chunk_x, chunk_y):
        """
        Classify water depth based on neighborhood and depth indicators.
        
        Converts inner water (completely surrounded by water) to deep, but only if
        the water_mask or height indicates sufficient depth. This makes deep water
        more restrictive, creating wider coastal zones (shallow + beach).
        
        Assumes all water tiles are already marked as shallow.
        
        This ensures that deep water never directly touches land - there's
        always at least one ring of shallow water between land and deep water.
        
        Args:
            tiles: 2D list of tile dictionaries (water tiles should already be shallow)
            chunk_x: Chunk X coordinate (for calculating world coordinates)
            chunk_y: Chunk Y coordinate (for calculating world coordinates)
        """
        h = len(tiles)
        w = len(tiles[0]) if h > 0 else 0
        chunk_size = settings.CHUNK_SIZE
        
        # Depth thresholds: water must meet at least one of these to become deep
        DEEP_WATER_MASK_THRESHOLD = 0.85  # Very high water mask (very wet area)
        DEEP_WATER_HEIGHT_THRESHOLD = 0.25  # Very low height (deep basin)
        
        # Convert inner water (completely surrounded by water) to deep
        # Use 8-neighborhood to ensure deep water is fully surrounded
        for y in range(h):
            for x in range(w):
                tile = tiles[y][x]
                if not self.is_water(tile):
                    continue
                
                # Get all neighbors (8-neighborhood)
                neighbors = self.get_neighbors(tiles, x, y, use_8_neighbors=True)
                
                # Condition 1: All neighbors must be water (surrounded by water)
                if not neighbors or not all(self.is_water(n) for n in neighbors):
                    continue  # Not fully surrounded, keep as shallow
                
                # Condition 2: Must indicate sufficient depth via water_mask or height
                # Calculate world coordinates to get water_mask
                world_x = chunk_x * chunk_size + x
                world_y = chunk_y * chunk_size + y
                
                # Get water mask and height
                water_mask = self.get_water_mask(world_x, world_y)
                height = tile.get("height", 0.5)
                
                # Check if depth indicators show sufficient depth
                # Deep water requires: very high water_mask OR very low height
                is_deep_enough = (
                    water_mask >= DEEP_WATER_MASK_THRESHOLD or
                    height <= DEEP_WATER_HEIGHT_THRESHOLD
                )
                
                # Only convert to deep if both conditions are met:
                # 1. Fully surrounded by water (neighborhood check)
                # 2. Sufficient depth (mask or height check)
                if is_deep_enough:
                    biome_id = "water:deep"
                    if biome_id in self.config.get("biomes", {}):
                        data = self.config["biomes"][biome_id]
                        tile["biome"] = biome_id
                        tile["tileid"] = data.get("tile_id") or data.get("tileid", "core:unknown")
                        tile["color"] = tuple(data["color"])
                        tile["traversable"] = data["traversable"]
    
    def apply_beach_overlay_to_chunk(self, tiles, chunk_x, chunk_y):
        """
        Apply beach biome to land tiles that directly border shallow water.
        
        Beach is only placed where land directly touches shallow water (4-neighborhood).
        Deep water never directly touches land - there's always shallow water in between.
        
        Beach replaces the existing land biome at the coast, but cannot appear
        inland because the neighborhood check requires water:shallow.
        
        Args:
            tiles: 2D list of tile dictionaries
            chunk_x: Chunk X coordinate (unused, kept for API consistency)
            chunk_y: Chunk Y coordinate (unused, kept for API consistency)
        """
        h = len(tiles)
        w = len(tiles[0]) if h > 0 else 0
        
        # Get beach biome config
        if "terrain:beach" not in self.config.get("biomes", {}):
            return  # No beach biome found
        
        beach_data = self.config["biomes"]["terrain:beach"]
        
        # Check each tile
        for y in range(h):
            for x in range(w):
                tile = tiles[y][x]
                
                # Skip if already water (beach only on land)
                if self.is_water(tile):
                    continue
                
                # Check 4-neighbors (cardinal directions only)
                neighbors = self.get_neighbors(tiles, x, y, use_8_neighbors=False)
                
                # Beach placement: only if neighbor is shallow water AND height is low enough
                # This prevents beach from appearing at high elevations (mountains shouldn't have beach)
                if neighbors and any(self.is_shallow_water(n) for n in neighbors):
                    # Only place beach at very low heights (true coastal areas only)
                    # Height threshold: beach should only appear below ~0.38 (very low coastal range)
                    # This makes beach very restrictive - only immediate coastal areas, not plains
                    tile_height = tile.get("height", 0.5)
                    if tile_height < 0.38:  # Only very low coastal elevations get beach (was 0.42, originally 0.5)
                        tile["biome"] = "terrain:beach"
                        tile["base_biome"] = tile.get("base_biome", "terrain:beach")
                        tile["tileid"] = beach_data.get("tile_id") or beach_data.get("tileid", "core:sand")
                        tile["color"] = tuple(beach_data["color"])
                        tile["traversable"] = beach_data["traversable"]
    
    def apply_water_overlay_to_chunk(self, tiles, chunk_x, chunk_y):
        """
        Apply water overlay to a chunk (Step 1: Set water tiles based on water_mask).
        
        Sets water tiles based on water_mask and height threshold.
        All water tiles are initially marked as shallow.
        
        Args:
            tiles: 2D list of tile dictionaries (from _generate_land_chunk)
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
        """
        chunk_size = settings.CHUNK_SIZE
        
        # Set water tiles based on water_mask (all initially shallow)
        for ty, row in enumerate(tiles):
            for tx, tile in enumerate(row):
                # Skip if already water
                if self.is_water(tile):
                    continue
                
                # Calculate world coordinates
                world_x = chunk_x * chunk_size + tx
                world_y = chunk_y * chunk_size + ty
                
                # Get tile height, water mask, and continentalness
                height = tile.get("height", 0.5)  # Normalized height [0, 1]
                mask = self.get_water_mask(world_x, world_y)
                continentalness = tile.get("continentalness", 0.5)  # Normalized continentalness [0, 1]
                
                # Decide if water should be placed here (threshold + height + continentalness)
                if not self.should_place_water(height, mask, continentalness):
                    continue
                
                # Initially set all water as shallow (depth classification happens later)
                biome_id = "water:shallow"
                if biome_id not in self.config.get("biomes", {}):
                    continue  # Skip if biome not found
                
                data = self.config["biomes"][biome_id]
                
                # Update tile with water biome data (overwrites land biome)
                tile["biome"] = biome_id
                # Keep base_biome for reference (original land biome)
                if "base_biome" not in tile:
                    tile["base_biome"] = tile.get("biome", biome_id)
                
                # Get tile_id from water biome
                tile_id = data.get("tile_id") or data.get("tileid", "core:unknown")
                tile["tileid"] = tile_id
                tile["color"] = tuple(data["color"])
                tile["traversable"] = data["traversable"]
