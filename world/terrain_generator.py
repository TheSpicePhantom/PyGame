"""
Procedural Terrain Generator with OpenSimplex Noise
Generates continuous world heightmap, then splits into chunks
Based on: https://loady.one/blog/terrain_mesh.html
Optimized for performance - NO per-tile resource generation
"""
import json
import math
import random
from opensimplex import OpenSimplex
from pathlib import Path
from core import settings

class BiomeStatistics:
    """Sammelt Statistiken über generierte Biome-Werte."""
    
    def __init__(self):
        # Dictionary: biome_id -> Liste von (height, temp, humidity) Tupeln
        self.biome_data = {}
    
    def add_sample(self, biome_id: str, height: float, temp: float, humidity: float):
        """Fügt eine Probe für ein Biome hinzu."""
        if biome_id not in self.biome_data:
            self.biome_data[biome_id] = []
        self.biome_data[biome_id].append((height, temp, humidity))
    
    def get_statistics(self):
        """
        Berechnet Statistiken für jedes Biome.
        
        Returns:
            Dictionary: biome_id -> {
                'count': Anzahl Proben,
                'height': {'min': ..., 'max': ..., 'mean': ...},
                'temp': {'min': ..., 'max': ..., 'mean': ...},
                'humidity': {'min': ..., 'max': ..., 'mean': ...}
            }
        """
        stats = {}
        
        for biome_id, samples in self.biome_data.items():
            if not samples:
                continue
            
            heights = [s[0] for s in samples]
            temps = [s[1] for s in samples]
            humidities = [s[2] for s in samples]
            
            stats[biome_id] = {
                'count': len(samples),
                'height': {
                    'min': min(heights),
                    'max': max(heights),
                    'mean': sum(heights) / len(heights)
                },
                'temp': {
                    'min': min(temps),
                    'max': max(temps),
                    'mean': sum(temps) / len(temps)
                },
                'humidity': {
                    'min': min(humidities),
                    'max': max(humidities),
                    'mean': sum(humidities) / len(humidities)
                }
            }
        
        return stats
    
    def print_statistics(self):
        """Gibt die Statistiken formatiert aus."""
        stats = self.get_statistics()
        
        if not stats:
            print("No biome statistics available.")
            return
        
        print("\n" + "=" * 100)
        print("BIOME STATISTIKEN - Tatsächlich generierte Wertebereiche")
        print("=" * 100)
        print(f"{'Biome':<20} | {'Count':>8} | {'Height Range':>20} | {'Temp Range':>20} | {'Humidity Range':>20}")
        print("-" * 100)
        
        # Sortiere Biome nach Name für bessere Lesbarkeit
        sorted_biomes = sorted(stats.items())
        
        for biome_id, data in sorted_biomes:
            count = data['count']
            h = data['height']
            t = data['temp']
            hum = data['humidity']
            
            height_range = f"[{h['min']:.3f}, {h['max']:.3f}]"
            temp_range = f"[{t['min']:.3f}, {t['max']:.3f}]"
            humidity_range = f"[{hum['min']:.3f}, {hum['max']:.3f}]"
            
            print(f"{biome_id:<20} | {count:>8} | {height_range:>20} | {temp_range:>20} | {humidity_range:>20}")
        
        print("\n" + "=" * 100)
        print("Detaillierte Statistiken (Mittelwerte):")
        print("=" * 100)
        print(f"{'Biome':<20} | {'Height Mean':>12} | {'Temp Mean':>12} | {'Humidity Mean':>14}")
        print("-" * 100)
        
        for biome_id, data in sorted_biomes:
            h = data['height']
            t = data['temp']
            hum = data['humidity']
            
            print(f"{biome_id:<20} | {h['mean']:>12.3f} | {t['mean']:>12.3f} | {hum['mean']:>14.3f}")
        
        print("=" * 100 + "\n")


class TerrainGenerator:
    """Generates continuous procedural terrain using OpenSimplex Noise"""
    
    def __init__(self, config_path="data/worldgen/biomes.json", seed=None, collect_statistics=False):
        """
        Initialize terrain generator.
        
        Args:
            config_path: Path to biome configuration JSON file
            seed: Random seed for terrain generation (None = random seed)
            collect_statistics: If True, collect biome statistics during generation
        """
        self.load_config(config_path)
        
        # Initialize noise generator with seed
        noise_settings = self.config.get("noise_settings") or self.config.get("noisesettings", {})
        if seed is None:
            seed = noise_settings.get("seed")
        if seed is None:
            seed = random.randint(0, 1000000)
        
        self.seed = seed
        self.collect_statistics = collect_statistics
        
        if collect_statistics:
            self.statistics = BiomeStatistics()
        else:
            self.statistics = None
        
        self.noise = OpenSimplex(seed=self.seed)
        self.temp_noise = OpenSimplex(seed=self.seed + 1)  # Separate noise for temperature
        self.cont_noise = OpenSimplex(seed=self.seed + 2)  # Separate noise for continentalness
        self.humidity_noise = OpenSimplex(seed=self.seed + 3)  # Separate noise for humidity
        self.ridge_noise = OpenSimplex(seed=self.seed + 4)  # Separate noise for mountain ridges/spikes
        self.river_noise = OpenSimplex(seed=self.seed + 5)  # Separate noise for river paths
        
        # Get noise parameters from config
        self.scale = noise_settings.get("scale", 200.0)
        self.octaves = noise_settings.get("octaves", 6)
        self.persistence = noise_settings.get("persistence", 0.5)
        self.lacunarity = noise_settings.get("lacunarity", 2.0)
        
        # Temperature noise parameters (can be different from height noise)
        self.temp_scale = noise_settings.get("temp_scale", 400.0)  # Larger scale = bigger temperature zones
        self.temp_octaves = noise_settings.get("temp_octaves", 4)  # Number of octaves for temperature
        self.temp_persistence = noise_settings.get("temp_persistence", 0.5)  # Temperature persistence
        self.temp_lacunarity = noise_settings.get("temp_lacunarity", 2.0)  # Temperature lacunarity
        
        # Temperature gradient parameters
        self.latitude_effect = noise_settings.get("latitude_effect", 0.3)  # Strength of latitude gradient (0.0-1.0)
        self.continentalness_effect = noise_settings.get("continentalness_effect", 0.2)  # Strength of continentalness effect
        self.height_cooling = noise_settings.get("height_cooling", 0.4)  # How much height cools temperature (0.0-1.0)
        
        # Continentalness noise for temperature (separate from height)
        self.cont_noise = OpenSimplex(seed=self.seed + 2)  # Separate noise for continentalness
        self.cont_scale = noise_settings.get("continentalness_scale", 600.0)  # Large scale for continental patterns
        
        # Humidity noise parameters
        self.humidity_scale = noise_settings.get("humidity_scale", 500.0)  # Scale for humidity noise
        self.humidity_base = noise_settings.get("humidity_base", 0.5)  # Base humidity level
        self.coastal_humidity_boost = noise_settings.get("coastal_humidity_boost", 0.3)  # Humidity boost near coast
        self.orographic_effect = noise_settings.get("orographic_effect", 0.4)  # Strength of windward/leeward effect
        
        # Ridge/Spikes noise parameters (for mountain chains)
        self.ridge_scale = noise_settings.get("ridge_scale", 300.0)  # Scale for ridge noise
        self.ridge_threshold = noise_settings.get("ridge_threshold", 0.6)  # Base height threshold for spikes
        self.ridge_strength = noise_settings.get("ridge_strength", 0.15)  # Maximum height addition from spikes
        self.spike_cooling = noise_settings.get("spike_cooling", 0.2)  # Additional temperature cooling in spikes
        
        # River noise parameters
        self.river_scale = noise_settings.get("river_scale", 800.0)  # Large scale for river networks
        self.river_threshold = noise_settings.get("river_threshold", 0.65)  # Noise threshold for river placement
        self.river_width = noise_settings.get("river_width", 3.0)  # River width in tiles (affects influence radius)
        self.river_depth_reduction = noise_settings.get("river_depth_reduction", 0.08)  # Height reduction along rivers
        self.river_cooling = noise_settings.get("river_cooling", 0.1)  # Temperature reduction along rivers
        self.river_humidity_boost = noise_settings.get("river_humidity_boost", 0.25)  # Humidity boost along rivers
        
        # Height exponent for terrain shaping (1.0 = normal, >1.0 = more peaks, <1.0 = more plateaus)
        self.height_exponent = noise_settings.get("height_exponent", 1.0)
        
        # Sea level threshold (water:shallow height_max)
        self.water_level = 0.24
        
        # World height for latitude calculation (None = use modulo-based zones)
        self.world_height = None
        
        # Pre-process biome data for efficient lookup
        self._process_biomes()
    
    def set_seed(self, seed: int):
        """
        Set new seed and reinitialize noise generator.
        
        Args:
            seed: New seed value for terrain generation
        """
        self.seed = seed
        self.noise = OpenSimplex(seed=self.seed)
        self.temp_noise = OpenSimplex(seed=self.seed + 1)  # Reinitialize temperature noise
        self.cont_noise = OpenSimplex(seed=self.seed + 2)  # Reinitialize continentalness noise
        self.humidity_noise = OpenSimplex(seed=self.seed + 3)  # Reinitialize humidity noise
        self.ridge_noise = OpenSimplex(seed=self.seed + 4)  # Reinitialize ridge noise
        self.river_noise = OpenSimplex(seed=self.seed + 5)  # Reinitialize river noise
        print(f"[TerrainGen] Seed updated to: {self.seed}")
    
    def load_config(self, path):
        """
        Load biome configuration from JSON.
        
        Args:
            path: Relative path to config file (e.g., "data/worldgen/biomes.json")
        """
        # Use Path for robust path handling (works better for tools/tests)
        full_path = Path(__file__).parent / ".." / path
        full_path = full_path.resolve()  # Resolve to absolute path
        
        with open(full_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        
    def _process_biomes(self):
        """Pre-process biome data for efficient lookup by height, temperature, and humidity."""
        # Normalize height ranges from [-1, 1] to [0, 1] for easier comparison
        self.biomes_by_height = []
        
        for biome_id, biome_data in self.config.get("biomes", {}).items():
            h_min = biome_data.get("height_min", -1.0)
            h_max = biome_data.get("height_max", 1.0)
            t_min = biome_data.get("temp_min", 0.0)
            t_max = biome_data.get("temp_max", 1.0)
            hum_min = biome_data.get("humidity_min", 0.0)  # Optional humidity range
            hum_max = biome_data.get("humidity_max", 1.0)
            
            # Normalize height from [-1, 1] to [0, 1]
            h_min_norm = (h_min + 1.0) / 2.0
            h_max_norm = (h_max + 1.0) / 2.0
            
            # Temperature is already in [0, 1] range
            t_min_norm = max(0.0, min(1.0, t_min))
            t_max_norm = max(0.0, min(1.0, t_max))
            
            # Humidity is already in [0, 1] range (default to full range if not specified)
            hum_min_norm = max(0.0, min(1.0, hum_min)) if hum_min is not None else 0.0
            hum_max_norm = max(0.0, min(1.0, hum_max)) if hum_max is not None else 1.0
            
            # Get target values for distance-based matching
            target_height = biome_data.get("target_height")
            target_temp = biome_data.get("target_temp")
            target_humidity = biome_data.get("target_humidity")
            
            # If target_height not specified, use midpoint of height range
            if target_height is None:
                target_height = (h_min_norm + h_max_norm) / 2.0
            
            # Normalize target_height from [-1, 1] to [0, 1] if needed
            if target_height is not None and target_height < 0:
                target_height = (target_height + 1.0) / 2.0
            
            self.biomes_by_height.append({
                "id": biome_id,
                "data": biome_data,
                "height_min": h_min_norm,
                "height_max": h_max_norm,
                "temp_min": t_min_norm,
                "temp_max": t_max_norm,
                "humidity_min": hum_min_norm,
                "humidity_max": hum_max_norm,
                "target_height": target_height if target_height is not None else 0.5,
                "target_temp": target_temp if target_temp is not None else 0.5,
                "target_humidity": target_humidity if target_humidity is not None else 0.5
            })
        
        # Sort by height_min for efficient lookup
        self.biomes_by_height.sort(key=lambda x: x["height_min"])
    
    def _get_noise_value(self, x: float, y: float) -> float:
        """
        Get multi-octave noise value at world coordinates.
        
        Based on: https://loady.one/blog/terrain_mesh.html
        
        Args:
            x: World X coordinate
            y: World Y coordinate
            
        Returns:
            Noise value in [-1, 1] range
        """
        amplitude = 1.0
        frequency = 1.0
        noise_value = 0.0
        max_value = 0.0
        
        # Multi-octave noise for natural variation
        for _ in range(self.octaves):
            sample_x = x / self.scale * frequency
            sample_y = y / self.scale * frequency
            
            noise_value += self.noise.noise2(sample_x, sample_y) * amplitude
            max_value += amplitude
            
            amplitude *= self.persistence
            frequency *= self.lacunarity
        
        # Normalize to [-1, 1] range
        return noise_value / max_value if max_value > 0 else 0.0
    
    def _normalize_heightmap(self, heightmap, min_val=None, max_val=None):
        """
        Normalize heightmap to [0, 1] range.
        
        Args:
            heightmap: 2D list or array of height values
            min_val: Minimum value (None = calculate from heightmap)
            max_val: Maximum value (None = calculate from heightmap)
            
        Returns:
            Normalized heightmap in [0, 1] range
        """
        # Find min/max if not provided
        if min_val is None or max_val is None:
            flat_values = [h for row in heightmap for h in row]
            if not flat_values:
                return heightmap
            min_val = min(flat_values)
            max_val = max(flat_values)
        
        # Avoid division by zero
        if max_val == min_val:
            return [[0.5 for _ in row] for row in heightmap]
        
        # Normalize each value
        normalized = []
        for row in heightmap:
            normalized_row = []
            for h in row:
                normalized_value = (h - min_val) / (max_val - min_val)
                normalized_row.append(max(0.0, min(1.0, normalized_value)))
            normalized.append(normalized_row)
        
        return normalized
    
    def _apply_height_exponent(self, heightmap):
        """
        Apply exponential function to heightmap for terrain shaping.
        
        Exponent > 1.0 creates more peaks, < 1.0 creates more plateaus.
        Based on: https://loady.one/blog/terrain_mesh.html
        
        Args:
            heightmap: 2D list of normalized height values [0, 1]
            
        Returns:
            Modified heightmap with exponential curve applied
        """
        if self.height_exponent == 1.0:
            return heightmap
        
        result = []
        for row in heightmap:
            result_row = []
            for h in row:
                # Apply exponent and re-normalize
                result_row.append(h ** self.height_exponent)
            result.append(result_row)
        
        # Re-normalize after exponent
        return self._normalize_heightmap(result)
    
    def _get_spikes_at(self, world_x: int, world_y: int, base_height: float) -> float:
        """
        Get additional height from ridge/spikes noise.
        
        Only adds height where base height is already above threshold (ridge_threshold).
        This creates clear mountain chains instead of random spikes everywhere.
        
        Args:
            world_x: World X coordinate (tile coordinate)
            world_y: World Y coordinate (tile coordinate)
            base_height: Base height value (before spikes)
            
        Returns:
            Additional height value in [0.0, ridge_strength] range
        """
        # Only add spikes where base height is already elevated
        if base_height < self.ridge_threshold:
            return 0.0
        
        # Get ridge noise value
        noise_value = self.ridge_noise.noise2(
            world_x / self.ridge_scale,
            world_y / self.ridge_scale
        )
        
        # Normalize from [-1, 1] to [0, 1]
        ridge_factor = (noise_value + 1.0) / 2.0
        
        # Scale by how much base height exceeds threshold
        # More elevated areas get stronger spikes
        threshold_excess = (base_height - self.ridge_threshold) / (1.0 - self.ridge_threshold)
        
        # Calculate spike height: stronger in more elevated areas
        spike_height = ridge_factor * self.ridge_strength * threshold_excess
        
        return max(0.0, min(self.ridge_strength, spike_height))
    
    def _get_height_at(self, world_x: int, world_y: int) -> float:
        """
        Get normalized height value at world coordinates.
        
        Uses natural noise distribution without remapping for organic variation.
        Adds ridge/spikes noise for mountain chains.
        Reduces height along rivers to create valleys.
        
        Args:
            world_x: World X coordinate (tile coordinate)
            world_y: World Y coordinate (tile coordinate)
        
        Returns:
            Normalized height value in [0.0, 1.0] range
        """
        # Get base height from noise
        noise_value = self._get_noise_value(world_x, world_y)
        
        # Normalize from [-1, 1] to [0, 1]
        base_height = (noise_value + 1.0) / 2.0
        
        # Apply exponential shaping if configured
        if self.height_exponent != 1.0:
            base_height = base_height ** self.height_exponent
        
        # Add ridge/spikes for mountain chains (only on elevated terrain)
        spikes = self._get_spikes_at(world_x, world_y, base_height)
        height = base_height + spikes
        
        # Reduce height along rivers to create valleys
        river_influence = self._get_river_influence_at(world_x, world_y)
        if river_influence > 0.0:
            # Only reduce height on land (not below sea level)
            if height > self.water_level:
                height_reduction = river_influence * self.river_depth_reduction
                height -= height_reduction
        
        return max(0.0, min(1.0, height))
    
    def _get_river_influence_at(self, world_x: int, world_y: int) -> float:
        """
        Get river influence value at world coordinates.
        
        Uses noise to create river paths, then calculates influence based on distance
        to nearest river. Higher values indicate proximity to rivers.
        
        Args:
            world_x: World X coordinate (tile coordinate)
            world_y: World Y coordinate (tile coordinate)
            
        Returns:
            River influence value in [0.0, 1.0] range (1.0 = on river, 0.0 = far from river)
        """
        # Get river noise value (large scale for river networks)
        noise_value = self.river_noise.noise2(
            world_x / self.river_scale,
            world_y / self.river_scale
        )
        
        # Normalize from [-1, 1] to [0, 1]
        river_noise = (noise_value + 1.0) / 2.0
        
        # Check if this location is on a river path (noise above threshold)
        # Use a smooth falloff around the threshold for gradual influence
        if river_noise > self.river_threshold:
            # Calculate distance from threshold (0.0 at threshold, 1.0 at max)
            distance_from_threshold = (river_noise - self.river_threshold) / (1.0 - self.river_threshold)
            
            # Smooth falloff: stronger influence closer to river center
            # Use exponential falloff for natural river valley shape
            influence = 1.0 - (distance_from_threshold ** 0.5)
            
            # Scale by river width (wider rivers have more influence)
            influence *= (1.0 / self.river_width)
            
            return max(0.0, min(1.0, influence))
        
        return 0.0
    
    def _get_continentalness_at(self, world_x: int, world_y: int) -> float:
        """
        Get continentalness value at world coordinates.
        
        Continentalness represents distance from ocean: low = coastal (warmer),
        high = inland (colder). Used for temperature gradient.
        
        Args:
            world_x: World X coordinate (tile coordinate)
            world_y: World Y coordinate (tile coordinate)
        
        Returns:
            Continentalness value in [0.0, 1.0] range (0.0 = coastal, 1.0 = inland)
        """
        # Large-scale noise for continental patterns
        noise_value = self.cont_noise.noise2(
            world_x / self.cont_scale,
            world_y / self.cont_scale
        )
        
        # Normalize from [-1, 1] to [0, 1]
        cont = (noise_value + 1.0) / 2.0
        
        return max(0.0, min(1.0, cont))
    
    def _get_temperature_at(self, world_x: int, world_y: int, height: float = None) -> float:
        """
        Get normalized temperature value at world coordinates.
        
        Combines large-scale gradients (latitude, continentalness) with height falloff
        and local noise variation to create natural climate zones.
        
        Temperature factors:
        1. Latitude gradient: North (cold) → South (warm)
        2. Continentalness: Coastal (warmer) → Inland (colder)
        3. Height falloff: Higher elevations are colder
        4. Local noise: Small-scale variation
        
        Args:
            world_x: World X coordinate (tile coordinate)
            world_y: World Y coordinate (tile coordinate)
            height: Optional height value (if None, will be calculated)
            
        Returns:
            Normalized temperature value in [0.0, 1.0] range
        """
        # 1. Latitude gradient (North-South: cold-warm-cold)
        # Use world_height if set, otherwise use modulo-based repeating zones
        if self.world_height is not None and self.world_height > 1:
            # Use actual world height for smooth latitude calculation
            latitude_factor = world_y / max(1.0, self.world_height - 1.0)
            latitude_factor = max(0.0, min(1.0, latitude_factor))  # Clamp to [0, 1]
        else:
            # Fallback: Use modulo for repeating zones (useful for infinite worlds)
            zone_size = 500  # Repeating climate zones every 500 tiles
            relative_y = world_y % zone_size
            latitude_factor = relative_y / float(zone_size - 1) if zone_size > 1 else 0.5
        
        # Cosine-based latitude: cold at poles (0.0 and 1.0), warm at equator (0.5)
        # cos(0) = 1 (cold), cos(pi) = -1 (cold), cos(pi/2) = 0 (warm)
        # Smooth continuous function - no hard cuts or jumps
        lat_temp = 0.5 - 0.4 * math.cos(math.pi * latitude_factor)  # ~0.1 (cold) to ~0.9 (warm)
        
        # 2. Continentalness gradient (coastal warmer, inland colder)
        continentalness = self._get_continentalness_at(world_x, world_y)
        # Invert: low continentalness (coastal) = warmer, high (inland) = colder
        cont_temp = 1.0 - continentalness * 0.3  # Coastal: +0.3, Inland: -0.0
        
        # 3. Height falloff (higher elevations are colder)
        if height is None:
            height = self._get_height_at(world_x, world_y)
        # Height cooling: subtract up to height_cooling based on height
        height_cooling_factor = (height - 0.5) * self.height_cooling  # Higher = more cooling
        
        # 4. Local noise variation (small-scale temperature variation)
        noise_value = self.temp_noise.noise2(
            world_x / self.temp_scale,
            world_y / self.temp_scale
        )
        noise_temp = (noise_value + 1.0) / 2.0  # Normalize to [0, 1]
        
        # Combine all factors
        # Base temperature from latitude and continentalness
        base_temp = lat_temp * self.latitude_effect + cont_temp * self.continentalness_effect
        
        # Add local noise variation (remaining weight)
        noise_weight = 1.0 - self.latitude_effect - self.continentalness_effect
        temp = base_temp + noise_temp * noise_weight
        
        # Apply height cooling
        temp -= height_cooling_factor
        
        # 5. Additional cooling in spikes/mountain ridges (for snow peaks)
        # Check if this location has spikes (elevated terrain with ridge noise)
        if height is None:
            height = self._get_height_at(world_x, world_y)
        
        # Get base height (without spikes) to check for spikes
        noise_value = self._get_noise_value(world_x, world_y)
        base_height = (noise_value + 1.0) / 2.0
        if self.height_exponent != 1.0:
            base_height = base_height ** self.height_exponent
        
        # If base height is above threshold, check for spikes
        if base_height >= self.ridge_threshold:
            spikes = self._get_spikes_at(world_x, world_y, base_height)
            # Additional cooling proportional to spike height
            spike_cooling_factor = spikes / self.ridge_strength * self.spike_cooling
            temp -= spike_cooling_factor
        
        # Clamp to [0, 1] range
        temp = max(0.0, min(1.0, temp))
        
        # 6. Additional cooling along rivers (for river valleys and oases)
        river_influence = self._get_river_influence_at(world_x, world_y)
        if river_influence > 0.0:
            # Slight cooling along rivers (creates cooler valleys)
            river_cooling_factor = river_influence * self.river_cooling
            temp -= river_cooling_factor
        
        # Final clamp to [0, 1] range
        return max(0.0, min(1.0, temp))
    
    def _get_humidity_at(self, world_x: int, world_y: int, height: float = None) -> float:
        """
        Get normalized humidity value at world coordinates.
        
        Combines base noise with modifications from:
        1. Distance to sea (continentalness): Coastal areas are more humid
        2. Orography (windward/leeward): Windward side of mountains is more humid
        
        Args:
            world_x: World X coordinate (tile coordinate)
            world_y: World Y coordinate (tile coordinate)
            height: Optional height value (if None, will be calculated)
            
        Returns:
            Normalized humidity value in [0.0, 1.0] range
        """
        # 1. Base humidity from noise
        noise_value = self.humidity_noise.noise2(
            world_x / self.humidity_scale,
            world_y / self.humidity_scale
        )
        humidity = (noise_value + 1.0) / 2.0  # Normalize to [0, 1]
        
        # 2. Coastal humidity boost (coastal areas are more humid)
        continentalness = self._get_continentalness_at(world_x, world_y)
        # Invert: low continentalness (coastal) = more humid
        coastal_boost = (1.0 - continentalness) * self.coastal_humidity_boost
        humidity += coastal_boost
        
        # 3. Orographic effect (windward/leeward sides of mountains)
        if height is None:
            height = self._get_height_at(world_x, world_y)
        
        # Calculate height gradient (approximate windward/leeward)
        # Sample neighbors to detect slopes
        # For simplicity, use a directional gradient based on noise
        # In real implementation, you'd check actual neighbors
        # Here we approximate by checking if we're on a slope facing a certain direction
        
        # Get height at nearby points to estimate slope direction
        # East-West gradient (simplified: assume prevailing winds from west)
        height_west = self._get_height_at(world_x - 5, world_y)
        height_east = self._get_height_at(world_x + 5, world_y)
        height_north = self._get_height_at(world_x, world_y - 5)
        height_south = self._get_height_at(world_x, world_y + 5)
        
        # Calculate gradients
        gradient_x = height_east - height_west  # Positive = slope facing east (leeward)
        gradient_y = height_south - height_north  # Positive = slope facing south
        
        # Windward side (west-facing slopes) = more humid
        # Leeward side (east-facing slopes) = less humid
        # Use X gradient as primary (assuming west winds)
        if height > 0.5:  # Only apply to elevated areas (mountains/hills)
            orographic_modifier = -gradient_x * self.orographic_effect
            # Windward (negative gradient_x) = positive modifier = more humid
            # Leeward (positive gradient_x) = negative modifier = less humid
            humidity += orographic_modifier
        
        # Clamp to [0, 1] range
        humidity = max(0.0, min(1.0, humidity))
        
        # 4. Humidity boost along rivers (for green river valleys even in dry zones)
        river_influence = self._get_river_influence_at(world_x, world_y)
        if river_influence > 0.0:
            # Boost humidity along rivers (creates green oases in deserts)
            river_humidity_boost = river_influence * self.river_humidity_boost
            humidity += river_humidity_boost
        
        # Final clamp to [0, 1] range
        return max(0.0, min(1.0, humidity))
    
    def _get_biome_for_height_temp_humidity(self, height: float, temperature: float, humidity: float):
        """
        Find appropriate biome using distance-based matching in 3D climate space.
        
        Uses weighted Euclidean distance to find the biome with the smallest distance
        to its target vector (target_height, target_temp, target_humidity).
        This creates smooth transitions like "Plains → Savanna → Desert" or
        "Plains → Forest → Rainforest" based on climate gradients instead of hard thresholds.
        
        Args:
            height: Normalized height value [0.0, 1.0]
            temperature: Normalized temperature value [0.0, 1.0]
            humidity: Normalized humidity value [0.0, 1.0]
            
        Returns:
            Tuple of (biome_id, biome_data)
        """
        # Distance weights (can be adjusted for different importance)
        WEIGHT_HEIGHT = 1.0
        WEIGHT_TEMP = 1.0
        WEIGHT_HUMIDITY = 1.0
        
        best_biome = None
        best_distance = float('inf')
        
        # Calculate distance to each biome's target vector
        for biome in self.biomes_by_height:
            # Get target values
            target_h = biome.get("target_height", 0.5)
            target_t = biome.get("target_temp", 0.5)
            target_hum = biome.get("target_humidity", 0.5)
            
            # Calculate weighted Euclidean distance in 3D climate space
            d_height = (height - target_h) ** 2
            d_temp = (temperature - target_t) ** 2
            d_humidity = (humidity - target_hum) ** 2
            
            distance = math.sqrt(
                WEIGHT_HEIGHT * d_height +
                WEIGHT_TEMP * d_temp +
                WEIGHT_HUMIDITY * d_humidity
            )
            
            # Optional: Apply soft filtering by height range (biomes outside range get penalty)
            # This prevents water biomes from appearing on mountains, but allows smooth transitions
            if height < biome["height_min"] or height > biome["height_max"]:
                # Add penalty for being outside height range (but don't exclude completely)
                height_penalty = 0.0
                if height < biome["height_min"]:
                    height_penalty = (biome["height_min"] - height) * 2.0
                elif height > biome["height_max"]:
                    height_penalty = (height - biome["height_max"]) * 2.0
                distance += height_penalty
            
            # Keep track of best matching biome (smallest distance)
            if distance < best_distance:
                best_distance = distance
                best_biome = biome
        
        # Return best matching biome
        if best_biome:
            return best_biome["id"], best_biome["data"]
        
        # Fallback: If height is at or below water level, use water:shallow
        if height <= self.water_level:
            if "water:shallow" in self.config.get("biomes", {}):
                return "water:shallow", self.config["biomes"]["water:shallow"]
        
        # Otherwise, fallback to neutral land biome (plains)
        if "terrain:plains" in self.config.get("biomes", {}):
            return "terrain:plains", self.config["biomes"]["terrain:plains"]
        
        # Ultimate fallback: return first available biome
        if self.config.get("biomes"):
            first_id = list(self.config["biomes"].keys())[0]
            return first_id, self.config["biomes"][first_id]
        
        # Should never happen
        return "terrain:unknown", {"color": [128, 128, 128], "tile_id": "core:unknown", "traversable": True}
    
    def generate_chunk(self, chunk_x, chunk_y, chunk_size=None, world_height=None):
        """
        Generate a complete chunk with heightmap-based terrain.
        
        Based on: https://loady.one/blog/terrain_mesh.html
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate  
            chunk_size: Tiles per chunk (defaults to settings.CHUNK_SIZE if None)
            world_height: World height in tiles for latitude calculation (None = use modulo zones)
        
        Returns:
            2D list of tile dictionaries
        """
        if chunk_size is None:
            chunk_size = settings.CHUNK_SIZE
        
        # Set world_height for this generation (temporary, for latitude calculation)
        old_world_height = self.world_height
        if world_height is not None:
            self.world_height = float(world_height)
        
        # Calculate world offset for this chunk
        world_offset_x = chunk_x * chunk_size
        world_offset_y = chunk_y * chunk_size
        
        # Generate heightmap for this chunk
        heightmap = []
        for tile_y in range(chunk_size):
            row = []
            for tile_x in range(chunk_size):
                world_x = world_offset_x + tile_x
                world_y = world_offset_y + tile_y
                height = self._get_height_at(world_x, world_y)
                row.append(height)
            heightmap.append(row)
        
        # No normalization needed: _get_height_at already returns clamped [0.0, 1.0] values
        # Normalizing with fixed min/max (0.0, 1.0) would create hard cuts by clamping
        # all values to exact boundaries, causing visible bands in the heatmap
        
        # Generate tiles from heightmap
        tiles = []
        for tile_y in range(chunk_size):
            row = []
            for tile_x in range(chunk_size):
                world_x = world_offset_x + tile_x
                world_y = world_offset_y + tile_y
                height = heightmap[tile_y][tile_x]
                
                # Get temperature at this location (pass height for height-based cooling)
                temperature = self._get_temperature_at(world_x, world_y, height)
                
                # Get humidity at this location (pass height for orographic effects)
                humidity = self._get_humidity_at(world_x, world_y, height)
                
                # Get biome based on height, temperature, AND humidity
                biome_id, biome_data = self._get_biome_for_height_temp_humidity(height, temperature, humidity)
                
                # Sammle Statistiken wenn aktiviert
                if self.statistics is not None:
                    self.statistics.add_sample(biome_id, height, temperature, humidity)
                
                # Support both "tile_id" and "tileid" for compatibility
                tile_id = biome_data.get("tile_id") or biome_data.get("tileid", "terrain:unknown")
                
                # Ensure tileid is terrain:* format (not core:*)
                if tile_id.startswith("core:"):
                    tile_id = tile_id.replace("core:", "terrain:", 1)
                elif not tile_id.startswith("terrain:") and not tile_id.startswith("water:"):
                    tile_id = f"terrain:{tile_id}"
                
                # Build tile dictionary
                tile = {
                    "biome": biome_id,
                    "base_biome": biome_id,
                    "height": float(height),
                    "temperature": float(temperature),
                    "humidity": float(humidity),
                    "tileid": tile_id,
                    "color": tuple(biome_data.get("color", [128, 128, 128])),
                    "traversable": biome_data.get("traversable", True),
                }
                
                row.append(tile)
            tiles.append(row)
        
        # Restore original world_height
        self.world_height = old_world_height
        
        # Generate decorations for this chunk
        self.generate_decorations(tiles, chunk_x, chunk_y, chunk_size)
        
        return tiles
    
    def generate_tile(self, world_x: int, world_y: int, world_height: float = None) -> dict:
        """
        Generate a single tile at world coordinates.
        
        This method is used for individual tile lookups (e.g., spawn position finding,
        tile inspection) without generating entire chunks.
        
        Args:
            world_x: World X coordinate (tile coordinate)
            world_y: World Y coordinate (tile coordinate)
            world_height: World height in tiles for latitude calculation (None = use self.world_height or modulo zones)
        
        Returns:
            Tile dictionary with biome, height, temperature, humidity, etc.
        """
        # Use provided world_height, or fall back to instance world_height, or None (modulo zones)
        # No need to temporarily set it since we're not modifying instance state
        # The _get_temperature_at method will use self.world_height if set
        
        # Get height at this location
        height = self._get_height_at(world_x, world_y)
        
        # Get temperature at this location (pass height for height-based cooling)
        temperature = self._get_temperature_at(world_x, world_y, height)
        
        # Get humidity at this location (pass height for orographic effects)
        humidity = self._get_humidity_at(world_x, world_y, height)
        
        # Get biome based on height, temperature, AND humidity
        biome_id, biome_data = self._get_biome_for_height_temp_humidity(height, temperature, humidity)
        
        # Support both "tile_id" and "tileid" for compatibility
        tile_id = biome_data.get("tile_id") or biome_data.get("tileid", "terrain:unknown")
        
        # Ensure tileid is terrain:* format (not core:*)
        if tile_id.startswith("core:"):
            tile_id = tile_id.replace("core:", "terrain:", 1)
        elif not tile_id.startswith("terrain:") and not tile_id.startswith("water:"):
            tile_id = f"terrain:{tile_id}"
        
        # Build tile dictionary
        tile = {
            "biome": biome_id,
            "base_biome": biome_id,
            "height": float(height),
            "temperature": float(temperature),
            "humidity": float(humidity),
            "tileid": tile_id,
            "color": tuple(biome_data.get("color", [128, 128, 128])),
            "traversable": biome_data.get("traversable", True),
        }
        
        return tile
    
    def print_biome_statistics(self):
        """Gibt die gesammelten Biome-Statistiken aus."""
        if self.statistics is not None:
            self.statistics.print_statistics()
        else:
            print("Statistics collection is disabled. Initialize with collect_statistics=True.")
    
    def generate_decorations(self, tiles, chunk_x, chunk_y, chunk_size=None):
        """
        Generate decorations for a chunk based on biome and noise.
        
        Args:
            tiles: 2D list of tile dictionaries (already generated)
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
            chunk_size: Tiles per chunk (defaults to settings.CHUNK_SIZE if None)
        """
        if chunk_size is None:
            chunk_size = settings.CHUNK_SIZE
        
        try:
            from world.decoration_registry import DecorationRegistry
        except ImportError:
            # DecorationRegistry not available, skip decoration generation
            return
        
        # Debug: Check if DecorationRegistry has biome extensions loaded
        if not hasattr(self, '_deco_registry_checked'):
            self._deco_registry_checked = True
            biome_count = len(DecorationRegistry._biomes) if hasattr(DecorationRegistry, '_biomes') else 0
            print(f"[TerrainGen] DecorationRegistry has {biome_count} biome extensions loaded")
        
        # Calculate world offset for this chunk
        try:
            world_offset_x = chunk_x * chunk_size
            world_offset_y = chunk_y * chunk_size
            
            # Track biome decorations for weighted spawn rules
            biome_decorations = {}  # biome_id -> list of decoration configs
            
            # First pass: Collect all decorations for each biome in this chunk
            for tile_y in range(chunk_size):
                if tile_y >= len(tiles):
                    continue
                for tile_x in range(chunk_size):
                    if tile_x >= len(tiles[tile_y]):
                        continue
                    
                    tile = tiles[tile_y][tile_x]
                    if not tile:
                        continue
                    
                    biome_id = tile.get('biome', '')
                    if not biome_id or biome_id.startswith('water:'):
                        continue  # Skip water biomes
                    
                    # Get biome extension config
                    if biome_id not in biome_decorations:
                        biome_ext = DecorationRegistry.get_biome_extensions(biome_id)
                        if biome_ext:
                            biome_decorations[biome_id] = biome_ext.get('decorations', [])
                        else:
                            biome_decorations[biome_id] = []
            
            # Second pass: Spawn decorations based on weighted spawn rules
            for tile_y in range(chunk_size):
                if tile_y >= len(tiles):
                    continue
                for tile_x in range(chunk_size):
                    if tile_x >= len(tiles[tile_y]):
                        continue
                    
                    tile = tiles[tile_y][tile_x]
                    if not tile:
                        continue
                    
                    # Skip if tile already has decoration
                    if tile.get('decoration'):
                        continue
                    
                    biome_id = tile.get('biome', '')
                    if not biome_id or biome_id.startswith('water:'):
                        continue  # Skip water biomes
                    
                    # Skip if not traversable (e.g., water, mountains)
                    if not tile.get('traversable', True):
                        continue
                    
                    # Get decorations for this biome
                    deco_configs = biome_decorations.get(biome_id, [])
                    if not deco_configs:
                        continue
                    
                    # Calculate world coordinates for noise
                    world_x = world_offset_x + tile_x
                    world_y = world_offset_y + tile_y
                    
                    # Get noise value for this position (use height noise for consistency)
                    # _get_noise_value returns [-1, 1], normalize to [0, 1] for spawn_rules
                    raw_noise = self._get_noise_value(world_x, world_y)
                    noise_value = (raw_noise + 1.0) / 2.0  # Normalize from [-1, 1] to [0, 1]
                    
                    # Try each decoration config for this biome
                    for deco_config in deco_configs:
                        decoration_id = deco_config.get('decoration_id')
                        if not decoration_id:
                            continue
                        
                        spawn_rules = deco_config.get('spawn_rules', [])
                        if not spawn_rules:
                            continue
                        
                        # Check weighted spawn rules
                        for rule in spawn_rules:
                            noise_min = rule.get('noise_range', [0.0, 1.0])[0]
                            noise_max = rule.get('noise_range', [0.0, 1.0])[1]
                            
                            # Check if noise value is in range
                            if not (noise_min <= noise_value <= noise_max):
                                continue
                            
                            density = rule.get('density', 0.1)
                            spawn_chance = rule.get('spawn_chance', 0.5)
                            
                            # Density check
                            if random.random() > density:
                                continue
                            
                            # Spawn chance check
                            if random.random() > spawn_chance:
                                continue
                            
                            # Check clustering if enabled
                            clustering = deco_config.get('clustering', {})
                            if clustering.get('enabled', False):
                                # Simple clustering: check nearby tiles
                                cluster_radius = clustering.get('cluster_radius', 3)
                                nearby_count = 0
                                for dy in range(-cluster_radius, cluster_radius + 1):
                                    for dx in range(-cluster_radius, cluster_radius + 1):
                                        if dx == 0 and dy == 0:
                                            continue
                                        check_x = tile_x + dx
                                        check_y = tile_y + dy
                                        if 0 <= check_x < chunk_size and 0 <= check_y < chunk_size:
                                            if check_y < len(tiles) and check_x < len(tiles[check_y]):
                                                check_tile = tiles[check_y][check_x]
                                                if check_tile and check_tile.get('decoration', {}).get('decoration_id') == decoration_id:
                                                    nearby_count += 1
                                
                                # Clustering logic: prefer spawning near other decorations, but allow isolated spawns
                                # If no nearby decorations, use a higher chance to spawn isolated (70% instead of 30%)
                                # This allows initial clusters to form while still preferring clustering
                                if nearby_count == 0:
                                    isolated_spawn_chance = clustering.get('isolated_spawn_chance', 0.7)  # Default 70% chance
                                    if random.random() > isolated_spawn_chance:
                                        continue
                                # If nearby decorations exist, always allow spawn (clustering preference)
                            
                            # Spawn decoration
                            decoration_data = {
                                'decoration_id': decoration_id,
                                'data': {
                                    'growth_timer': 0.0,
                                    'has_fruit': True,  # Default for harvestable items
                                    'damage': 0.0,
                                    'last_interaction': 0.0
                                }
                            }
                            
                            # Initialize harvestable-specific data
                            deco_registry_config = DecorationRegistry.get(decoration_id)
                            if deco_registry_config:
                                # Initialize harvestable data
                                if deco_registry_config.get('harvest', {}).get('enabled'):
                                    decoration_data['data']['has_fruit'] = True
                                    decoration_data['data']['growth_timer'] = 0.0
                                
                                # Initialize growth stage if growth is enabled
                                growth_config = deco_registry_config.get('growth', {})
                                if growth_config.get('enabled', False):
                                    placement_config = deco_registry_config.get('placement', {})
                                    spawn_stage_mode = placement_config.get('spawn_stage', 'default')
                                    
                                    if spawn_stage_mode == 'random':
                                        # Use weighted random selection
                                        spawn_weights = placement_config.get('spawn_stage_weights', {})
                                        if spawn_weights:
                                            # Convert weights to list for random.choices
                                            stages = []
                                            weights = []
                                            for stage_str, weight in spawn_weights.items():
                                                try:
                                                    stage = int(stage_str)
                                                    stages.append(stage)
                                                    weights.append(weight)
                                                except ValueError:
                                                    continue
                                            
                                            if stages and weights:
                                                import random
                                                selected_stage = random.choices(stages, weights=weights)[0]
                                                decoration_data['data']['current_stage'] = selected_stage
                                                
                                                # Initialize health based on stage
                                                stages_list = growth_config.get('stages', [])
                                                for stage_config in stages_list:
                                                    if stage_config.get('stage') == selected_stage:
                                                        decoration_data['data']['health'] = stage_config.get('health', 100)
                                                        decoration_data['data']['max_health'] = stage_config.get('health', 100)
                                                        decoration_data['data']['growth_progress'] = 0.0
                                                        break
                                    else:
                                        # Use default_stage
                                        default_stage = growth_config.get('default_stage', 4)
                                        decoration_data['data']['current_stage'] = default_stage
                                        
                                        # Initialize health based on stage
                                        stages_list = growth_config.get('stages', [])
                                        for stage_config in stages_list:
                                            if stage_config.get('stage') == default_stage:
                                                decoration_data['data']['health'] = stage_config.get('health', 100)
                                                decoration_data['data']['max_health'] = stage_config.get('health', 100)
                                                decoration_data['data']['growth_progress'] = 0.0
                                                break
                            
                            tile['decoration'] = decoration_data
                            break  # Only spawn one decoration per tile
                        
                        if tile.get('decoration'):
                            break  # Already spawned, move to next tile
        except Exception:
            # Silently fail if decoration generation has issues (e.g., missing registry)
            pass
