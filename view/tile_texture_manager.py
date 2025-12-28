"""
View: TileTextureManager - Lädt und verwaltet Texturen für Tiles
"""
import os
import json
import hashlib
from pathlib import Path
from typing import Dict, Optional, List, Tuple
import moderngl
from PIL import Image
from core import settings
import numpy as np
from opensimplex import OpenSimplex


class TileTextureManager:
    """
    Verwaltet Texturen für Tiles basierend auf tile_id.
    
    Lädt Texturen aus assets/tiles/core/ basierend auf tile_id:
    - core:rainforest -> assets/tiles/core/rainforest.png
    - terrain:plains -> assets/tiles/core/grass.png (oder plains.png falls vorhanden)
    """
    
    def __init__(self, ctx: moderngl.Context, base_path: str = "assets/tiles/core", mapping_file: str = "data/textures/texture_mapping.json", diagnostics=None):
        """
        Initialize Texture Manager with dynamic texture atlas and variant support
        
        Args:
            ctx: ModernGL context
            base_path: Base path to tile textures directory (fallback)
            mapping_file: Path to texture mapping JSON file
            diagnostics: Optional DiagnosticsService instance for logging
        """
        self.ctx = ctx
        self.base_path = Path(base_path)
        self.mapping_file = Path(mapping_file)
        self.diagnostics = diagnostics
        self.textures: Dict[str, moderngl.Texture] = {}  # Keep for compatibility, but will use atlas
        self.texture_images: Dict[str, Image.Image] = {}  # Store PIL images for atlas building
        self.texture_atlas: Optional[moderngl.Texture] = None
        self.texture_coords: Dict[str, tuple] = {}  # texture_name -> (u0, v0, u1, v1) in atlas
        self.variant_coords: Dict[str, List[tuple]] = {}  # tile_id -> list of (u0, v0, u1, v1) for variants
        self.atlas_size = 0  # Atlas size (will be calculated)
        self.tile_size = settings.TILE_SIZE
        
        # Overlay noise generator for deterministic placement
        # Use a fixed seed offset to ensure consistency across game sessions
        self.overlay_noise = OpenSimplex(seed=12345)
        
        # Multi-octave noise generators for organic growth patterns
        # Different seeds for each octave to ensure independence
        self.octave_noises = [
            OpenSimplex(seed=12345 + i * 1000) for i in range(4)  # Support up to 4 octaves
        ]
        
        # Load texture mapping configuration
        self.texture_mapping: Dict[str, dict] = {}
        self._load_texture_mapping()
        
        # Load all textures (including variants and overlays)
        self._load_all_textures()
        
        # Generate colorized textures for all biomes
        self.add_colorized_biome_textures()
        
        # Load decoration textures into atlas (if decoration system available)
        self._load_decoration_textures()
        
        # Build texture atlas (includes original, colorized, and decoration textures)
        self._build_texture_atlas()
    
    def _log(self, level: str, message: str, **kwargs):
        """
        Zentrale Logging-Methode mit Fallback auf print().
        
        Args:
            level: Log-Level ("debug", "info", "warning", "error", "critical")
            message: Log-Nachricht
            **kwargs: Zusätzliche Kontext-Daten
        """
        if self.diagnostics:
            getattr(self.diagnostics, level)("TileTextureManager", message, **kwargs)
        else:
            print(f"[TileTextureManager] {message}")
    
    def _load_texture_mapping(self):
        """Load texture mapping configuration from JSON file"""
        if not self.mapping_file.exists():
            self._log("warning", f"Texture mapping file {self.mapping_file} does not exist, using defaults")
            return
        
        try:
            with open(self.mapping_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.texture_mapping = data.get("texture_mappings", {})
                self._log("info", f"Loaded texture mapping for {len(self.texture_mapping)} biomes")
        except Exception as e:
            self._log("error", f"Error loading texture mapping: {e}")
    
    def _load_texture_from_path(self, texture_path: Path) -> Optional[Image.Image]:
        """Load a single texture from file path"""
        if not texture_path.exists():
            return None
        
        try:
            img = Image.open(texture_path).convert("RGBA")
            
            # Resize to tile size (TILE_SIZE x TILE_SIZE)
            if img.size[0] != self.tile_size or img.size[1] != self.tile_size:
                img = img.resize((self.tile_size, self.tile_size), Image.Resampling.LANCZOS)
            
            return img
        except Exception as e:
            self._log("error", f"Error loading texture {texture_path}: {e}")
            return None
    
    def _colorize_texture(self, source_img: Image.Image, target_rgb: List[int]) -> Image.Image:
        """
        Färbt eine Textur um, behält aber Helligkeit bei.
        
        Args:
            source_img: PIL Image (RGBA)
            target_rgb: [R, G, B] Zielfarbe (0-255)
        
        Returns:
            Colorized PIL Image (RGBA)
        """
        # Konvertiere zu numpy array (0.0-1.0)
        img_array = np.array(source_img, dtype=np.float32) / 255.0
        
        # Berechne Luminanz pro Pixel (gewichtete Summe)
        # Nur RGB-Kanäle verwenden, Alpha bleibt unverändert
        luminance = 0.299 * img_array[:,:,0] + 0.587 * img_array[:,:,1] + 0.114 * img_array[:,:,2]
        
        # Normalisiere Zielfarbe
        target_normalized = np.array(target_rgb, dtype=np.float32) / 255.0
        target_luminance = 0.299 * target_normalized[0] + 0.587 * target_normalized[1] + 0.114 * target_normalized[2]
        
        # Vermeide Division durch Null
        if target_luminance < 0.001:
            target_luminance = 0.001
        
        # Erstelle neues Bild: Zielfarbe * relative Helligkeit
        result = np.zeros_like(img_array)
        for channel in range(3):  # RGB-Kanäle
            result[:,:,channel] = target_normalized[channel] * (luminance / target_luminance)
        
        # Alpha-Kanal bleibt unverändert
        result[:,:,3] = img_array[:,:,3]
        
        # Clip und zurück zu 0-255
        result = np.clip(result * 255, 0, 255).astype(np.uint8)
        
        return Image.fromarray(result, mode='RGBA')
    
    def _colorize_texture_preserve_accents(self, source_img: Image.Image, target_rgb: List[int], accent_threshold: float = 1.5) -> Image.Image:
        """
        Färbt eine Textur um, behält aber Akzente (z.B. Blumen) bei.
        Identifiziert Pixel mit großem Farbabstand vom Durchschnitt und behält deren Original-Farbe.
        
        Args:
            source_img: PIL Image (RGBA)
            target_rgb: [R, G, B] Zielfarbe (0-255)
            accent_threshold: Schwellenwert für Akzent-Erkennung (Standard: 1.5 Standardabweichungen)
        
        Returns:
            Colorized PIL Image (RGBA) mit erhaltenen Akzenten
        """
        # Konvertiere zu numpy array (0.0-1.0)
        img_array = np.array(source_img, dtype=np.float32) / 255.0
        
        # Berechne Durchschnitts-Farbe aller Pixel (Basis-Farbe = Gras)
        # Nur RGB-Kanäle, ignoriere Alpha
        mean_color = np.mean(img_array[:,:,:3], axis=(0, 1))
        
        # Berechne Farbabstand jedes Pixels vom Durchschnitt (Euklidische Distanz im RGB-Raum)
        rgb_diff = img_array[:,:,:3] - mean_color
        distances = np.sqrt(np.sum(rgb_diff ** 2, axis=2))
        
        # Berechne Standardabweichung der Farbabstände
        mean_dist = np.mean(distances)
        std_dist = np.std(distances)
        
        # Erstelle Maske für Akzent-Pixel (Blumen): distance > mean_distance + accent_threshold * std_dev
        accent_mask = distances > (mean_dist + accent_threshold * std_dist)
        
        # Berechne Luminanz pro Pixel (für Colorization)
        luminance = 0.299 * img_array[:,:,0] + 0.587 * img_array[:,:,1] + 0.114 * img_array[:,:,2]
        
        # Normalisiere Zielfarbe
        target_normalized = np.array(target_rgb, dtype=np.float32) / 255.0
        target_luminance = 0.299 * target_normalized[0] + 0.587 * target_normalized[1] + 0.114 * target_normalized[2]
        
        # Vermeide Division durch Null
        if target_luminance < 0.001:
            target_luminance = 0.001
        
        # Erstelle neues Bild: Zielfarbe * relative Helligkeit (für alle Pixel)
        result = np.zeros_like(img_array)
        for channel in range(3):  # RGB-Kanäle
            result[:,:,channel] = target_normalized[channel] * (luminance / target_luminance)
        
        # Selektive Colorization: Nur Gras-Pixel colorisieren, Akzent-Pixel behalten Original-Farbe
        # result ist bereits mit colorisierten Werten gefüllt, überschreibe nur Akzent-Pixel
        for channel in range(3):
            result[:,:,channel][accent_mask] = img_array[:,:,channel][accent_mask]  # Original-Farbe für Akzente
        
        # Alpha-Kanal bleibt unverändert
        result[:,:,3] = img_array[:,:,3]
        
        # Clip und zurück zu 0-255
        result = np.clip(result * 255, 0, 255).astype(np.uint8)
        
        return Image.fromarray(result, mode='RGBA')
    
    def _generate_rotations(self, base_name: str, img: Image.Image) -> None:
        """
        Generiert 4 Rotationen (0°, 90°, 180°, 270°) für eine Textur.
        Speichert als {base_name}_r{degrees} in self.texture_images.
        
        Args:
            base_name: Basis-Name der Textur (ohne Rotation)
            img: PIL Image (RGBA)
        """
        for rotation_deg in [0, 90, 180, 270]:
            rotated_img = self._rotate_texture(img, rotation_deg)
            rotation_key = f"{base_name}_r{rotation_deg}"
            self.texture_images[rotation_key] = rotated_img
    
    def _rotate_texture(self, img: Image.Image, degrees: int) -> Image.Image:
        """
        Rotiert ein PIL Image um angegebene Grad (0, 90, 180, 270).
        
        Args:
            img: PIL Image (RGBA)
            degrees: Rotationswinkel in Grad (0, 90, 180, 270)
        
        Returns:
            Rotiertes PIL Image (RGBA)
        """
        if degrees == 0:
            return img.copy()
        elif degrees == 90:
            return img.transpose(Image.ROTATE_90)
        elif degrees == 180:
            return img.transpose(Image.ROTATE_180)
        elif degrees == 270:
            return img.transpose(Image.ROTATE_270)
        else:
            # Fallback: Verwende rotate() für andere Winkel
            return img.rotate(-degrees, expand=False, fillcolor=(0, 0, 0, 0))
    
    def _extract_overlay_names(self, mapping: dict) -> List[str]:
        """
        Extrahiert alle Overlay-Namen aus variance_system.growth_patterns[].overlay.
        Fallback: Wenn kein variance_system, gibt [base_texture] zurück.
        
        Args:
            mapping: Texture mapping dictionary aus texture_mapping.json
        
        Returns:
            Liste von Overlay-Namen: ["plains_grass_2", "plains_grass_3", ...]
        """
        variance_system = mapping.get("variance_system", {})
        growth_patterns = variance_system.get("growth_patterns", [])
        
        if growth_patterns:
            # Extrahiere overlay-Namen aus growth_patterns
            overlay_names = []
            for pattern in growth_patterns:
                overlay_name = pattern.get("overlay")
                if overlay_name and overlay_name not in overlay_names:
                    overlay_names.append(overlay_name)
            return overlay_names
        
        # Fallback: Nur base_texture
        base_texture = mapping.get("base_texture", "")
        if base_texture:
            return [base_texture]
        
        return []
    
    def _load_overlay_textures(self, biome_name: str, overlay_names: List[str], base_path: Path, target_color: List[int]) -> None:
        """
        Lädt und colorisiert alle Overlay-Texturen für ein Biom.
        Unterscheidet zwischen Basis (_1) und Overlays (selektive Colorization).
        Ruft _generate_rotations() für jede colorisierte Textur auf.
        
        Args:
            biome_name: Name des Bioms (z.B. "terrain:plains")
            overlay_names: Liste von Overlay-Namen (z.B. ["plains_grass_2", "plains_grass_3"])
            base_path: Base path für Texturen
            target_color: [R, G, B] Zielfarbe für Colorization
        """
        for overlay_name in overlay_names:
            # Lade Source-Textur
            texture_paths = [
                base_path / f"{overlay_name}.png",
                base_path / f"{overlay_name}",
                Path("assets/tiles/core") / f"{overlay_name}.png",
            ]
            
            source_img = None
            for texture_path in texture_paths:
                source_img = self._load_texture_from_path(texture_path)
                if source_img:
                    break
            
            if not source_img:
                self._log("warning", f"Could not load source texture for overlay {overlay_name}, skipping colorization")
                continue
            
            # Unterscheide zwischen Basis und Overlay
            if overlay_name.endswith('_1') or overlay_name == 'plains_grass_1':
                # Basis: Standard-Colorization
                colorized_img = self._colorize_texture(source_img, target_color)
            else:
                # Overlay: Blumen erhalten (plains_grass_2-6)
                colorized_img = self._colorize_texture_preserve_accents(source_img, target_color)
            
            # Benenne um: {biome_name}:{overlay_name}
            colorized_name = f"{biome_name}:{overlay_name}"
            
            # Füge zu texture_images hinzu
            self.texture_images[colorized_name] = colorized_img
            
            # Generiere 4 Rotations-Varianten
            self._generate_rotations(colorized_name, colorized_img)
    
    def _multi_octave_noise(self, x: float, y: float, octaves: int = 3, seed_offset: int = 0) -> float:
        """
        Kombiniert mehrere Noise-Oktaven für natürlichere Muster.
        Amplitude nimmt ab, Frequenz verdoppelt sich pro Oktave.
        
        Args:
            x: X-Koordinate
            y: Y-Koordinate
            octaves: Anzahl der Oktaven (Standard: 3)
            seed_offset: Offset für Seed-Variation (für verschiedene Overlay-Typen)
        
        Returns:
            Normalisierter Wert (0.0-1.0)
        """
        result = 0.0
        amplitude_sum = 0.0
        frequency = 1.0
        amplitude = 1.0
        
        for i in range(octaves):
            # Verwende unterschiedliche Noise-Generatoren für jede Oktave
            noise_gen = self.octave_noises[i % len(self.octave_noises)]
            
            # Berechne Noise-Wert für diese Oktave
            noise_value = noise_gen.noise2(x * frequency + seed_offset, y * frequency + seed_offset)
            
            # Addiere zur Gesamtsumme
            result += amplitude * noise_value
            amplitude_sum += amplitude
            
            # Nächste Oktave: Frequenz verdoppeln, Amplitude halbieren
            frequency *= 2.0
            amplitude *= 0.5
        
        # Normalisiere auf 0.0-1.0
        if amplitude_sum > 0:
            normalized = (result / amplitude_sum + 1.0) / 2.0
            return max(0.0, min(1.0, normalized))  # Clip auf [0, 1]
        else:
            return 0.5
    
    def _calculate_cluster_value(self, world_x: int, world_y: int, pattern: dict) -> float:
        """
        Berechnet Cluster-Wert basierend auf growth_patterns Konfiguration.
        Unterstützt verschiedene spread_bias Modi: radial, directional, uniform.
        
        Args:
            world_x: World X-Koordinate
            world_y: World Y-Koordinate
            pattern: Growth pattern Konfiguration aus texture_mapping.json
        
        Returns:
            Cluster-Wert (0.0-1.0) für diese Position
        """
        import math
        
        cluster_size = pattern.get("cluster_size", 3.5)
        cluster_density = pattern.get("cluster_density", 0.15)
        noise_scale = pattern.get("noise_scale", 0.08)
        spread_bias = pattern.get("spread_bias", "uniform")
        
        # Seed-Offset für diesen Overlay-Typ
        overlay_name = pattern.get("overlay", "")
        seed_offset = hash(overlay_name) % 10000 if overlay_name else 0
        
        if spread_bias == "radial":
            # Kreisförmige Cluster mit Abfall vom Zentrum
            # Finde Cluster-Zentrum (gerundete Position)
            center_x = round(world_x / cluster_size) * cluster_size
            center_y = round(world_y / cluster_size) * cluster_size
            
            # Berechne Distanz vom Zentrum
            dx = world_x - center_x
            dy = world_y - center_y
            distance = math.sqrt(dx * dx + dy * dy)
            
            # Multi-Octave Noise am Zentrum
            center_noise = self._multi_octave_noise(
                center_x * noise_scale, 
                center_y * noise_scale, 
                octaves=3,
                seed_offset=seed_offset
            )
            
            # Radialer Abfall (exponentiell, aber weniger aggressiv)
            # Verwende cluster_size * 2.0 für langsameren Abfall
            radial_factor = math.exp(-distance / (cluster_size * 2.0))
            
            # Kombiniere: center_noise * radial_factor * cluster_density
            # Multiplikator so anpassen, dass der maximale Wert (bei center_noise=1.0, radial_factor=1.0) 
            # mindestens 1.0 ist, damit Thresholds bis 0.75 erreicht werden können
            # Bei cluster_density=0.05: 1.0 * 1.0 * 0.05 * 20.0 = 1.0
            cluster_value = center_noise * radial_factor * cluster_density * 10.0
            
        elif spread_bias == "directional":
            # Gerichtetes Wachstum mit spread_direction [x, y]
            spread_direction = pattern.get("spread_direction", [1, 0])
            if len(spread_direction) != 2:
                spread_direction = [1, 0]
            
            # Normalisiere Richtungs-Vektor
            dir_length = math.sqrt(spread_direction[0]**2 + spread_direction[1]**2)
            if dir_length > 0:
                spread_direction = [spread_direction[0] / dir_length, spread_direction[1] / dir_length]
            
            # Projiziere Position auf Richtung
            projection = world_x * spread_direction[0] + world_y * spread_direction[1]
            
            # Multi-Octave Noise entlang der Projektion
            noise_value = self._multi_octave_noise(
                projection * noise_scale,
                (world_x + world_y) * noise_scale * 0.5,  # Perpendikuläre Komponente für Variation
                octaves=3,
                seed_offset=seed_offset
            )
            
            # Cluster-Dichte anwenden
            # Multiplikator so anpassen, dass der maximale Wert (bei noise_value=1.0) 
            # mindestens 1.0 ist, damit Thresholds bis 0.75 erreicht werden können
            cluster_value = noise_value * cluster_density * 10.0
            
        else:  # uniform
            # Gleichmäßige Verteilung (wie bisher)
            noise_x = world_x * noise_scale + seed_offset
            noise_y = world_y * noise_scale + seed_offset
            
            noise_value = self.overlay_noise.noise2(noise_x, noise_y)
            normalized_noise = (noise_value + 1.0) / 2.0
            
            # Multiplikator so anpassen, dass der maximale Wert (bei normalized_noise=1.0) 
            # mindestens 1.0 ist, damit Thresholds bis 0.75 erreicht werden können
            cluster_value = normalized_noise * cluster_density * 10.0
        
        return max(0.0, min(1.0, cluster_value))  # Clip auf [0, 1]
    
    def _load_decoration_textures(self):
        """Load all decoration textures and add them to texture_images for atlas building."""
        try:
            from world.decoration_registry import DecorationRegistry
        except ImportError:
            self._log("debug", "DecorationRegistry not available, skipping decoration texture loading")
            return
        
        # Get all decoration configs
        decorations = DecorationRegistry.get_all()
        if not decorations:
            return
        
        decoration_base_path = Path("assets/decorations")
        loaded_count = 0
        
        for decoration_id, deco_config in decorations.items():
            mod_id = deco_config.get('mod_id', 'core')
            sprites = deco_config.get('sprites', {})
            
            # Load all sprites from this decoration
            for sprite_key, sprite_name in sprites.items():
                if not sprite_name:
                    continue
                
                # Try to load sprite image
                sprite_paths = [
                    decoration_base_path / mod_id / f"{sprite_name}.png",
                    decoration_base_path / f"{sprite_name}.png",
                    Path("assets/decorations") / mod_id / f"{sprite_name}.png",
                    Path("assets/decorations") / f"{sprite_name}.png",
                ]
                
                sprite_img = None
                for path in sprite_paths:
                    if path.exists():
                        try:
                            sprite_img = Image.open(path).convert("RGBA")
                            # Don't resize - decorations can have custom sizes
                            break
                        except Exception as e:
                            self._log("debug", f"Error loading decoration texture {path}: {e}")
                            continue
                
                if sprite_img:
                    # Store with decoration prefix: "decoration:{mod_id}/{sprite_name}"
                    atlas_name = f"decoration:{mod_id}/{sprite_name}"
                    self.texture_images[atlas_name] = sprite_img
                    loaded_count += 1
                    self._log("debug", f"Loaded decoration texture: {atlas_name} ({sprite_img.size[0]}x{sprite_img.size[1]})")
            
            # Load shadow sprite if enabled
            rendering = deco_config.get('rendering', {})
            shadow = rendering.get('shadow', {})
            if shadow.get('enabled', False):
                shadow_sprite = shadow.get('sprite')
                if shadow_sprite:
                    shadow_paths = [
                        decoration_base_path / mod_id / f"{shadow_sprite}.png",
                        decoration_base_path / f"{shadow_sprite}.png",
                    ]
                    
                    shadow_img = None
                    for path in shadow_paths:
                        if path.exists():
                            try:
                                shadow_img = Image.open(path).convert("RGBA")
                                # Don't resize - shadows can have custom sizes
                                break
                            except Exception as e:
                                self._log("debug", f"Error loading shadow texture {path}: {e}")
                                continue
                    
                    if shadow_img:
                        atlas_name = f"decoration:{mod_id}/{shadow_sprite}"
                        self.texture_images[atlas_name] = shadow_img
                        loaded_count += 1
        
        if loaded_count > 0:
            self._log("info", f"Loaded {loaded_count} decoration textures for atlas")
    
    def reload_decoration_textures_and_rebuild_atlas(self):
        """
        Reload decoration textures and rebuild atlas.
        This should be called after DecorationRegistry is loaded.
        """
        # Load decoration textures
        self._load_decoration_textures()
        
        # Release old atlas if it exists
        if self.texture_atlas:
            self.texture_atlas.release()
            self.texture_atlas = None
        
        # Clear texture_coords and variant_coords to force rebuild
        # (They will be rebuilt in _build_texture_atlas)
        self.texture_coords.clear()
        self.variant_coords.clear()
        
        # Rebuild atlas with decoration textures
        self._build_texture_atlas()
    
    def get_decoration_texture_coords(self, sprite_name: str, mod_id: str = "core") -> Optional[tuple]:
        """
        Get UV coordinates for a decoration sprite in the texture atlas.
        
        Args:
            sprite_name: Sprite name (e.g., "berry_bush_2")
            mod_id: Mod identifier (default: "core")
            
        Returns:
            (u0, v0, u1, v1) tuple or None if not found
        """
        atlas_name = f"decoration:{mod_id}/{sprite_name}"
        if atlas_name in self.texture_coords:
            return self.texture_coords[atlas_name]
        return None
    
    def _get_rotated_texture_coords(self, base_name: str, world_x: int, world_y: int, rotation_enabled: bool = True) -> Optional[tuple]:
        """
        Holt Texture-Koordinaten mit Rotation, falls aktiviert.
        
        Args:
            base_name: Basis-Texture-Name (ohne Rotation)
            world_x: World X-Koordinate für deterministische Rotation
            world_y: World Y-Koordinate für deterministische Rotation
            rotation_enabled: Ob Rotation aktiviert ist
        
        Returns:
            (u0, v0, u1, v1) tuple oder None
        """
        # First, try to find base texture (always check this first)
        if base_name in self.texture_coords:
            base_coords = self.texture_coords[base_name]
        else:
            base_coords = None
        
        # If rotation is disabled or world coordinates are None, return base texture
        if not rotation_enabled or world_x is None or world_y is None:
            return base_coords
        
        # Calculate rotation: rotation = (world_x * 374761393 + world_y * 668265263) % 4
        rotation = (world_x * 374761393 + world_y * 668265263) % 4
        rotation_degrees = rotation * 90
        
        # Try to find rotated variant
        rotation_key = f"{base_name}_r{rotation_degrees}"
        if rotation_key in self.texture_coords:
            return self.texture_coords[rotation_key]
        
        # Fallback to base texture (0° rotation)
        if base_name in self.texture_coords:
            return self.texture_coords[base_name]
        
        # Final fallback: try r0 rotation key
        r0_key = f"{base_name}_r0"
        if r0_key in self.texture_coords:
            return self.texture_coords[r0_key]
        
        return None
    
    def _load_biome_colorization(self, biomes_json_path: str) -> Dict[str, List[int]]:
        """
        Lade Biom-Farben aus biomes.json
        
        Args:
            biomes_json_path: Pfad zur biomes.json Datei
        
        Returns:
            Dictionary: {biome_name: [R, G, B]}
        """
        biome_colors = {}
        biomes_path = Path(biomes_json_path)
        
        if not biomes_path.exists():
            self._log("warning", f"Biomes file {biomes_path} does not exist")
            return biome_colors
        
        try:
            with open(biomes_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                biomes = data.get("biomes", {})
                
                for biome_name, biome_data in biomes.items():
                    color = biome_data.get("color")
                    if color and isinstance(color, list) and len(color) >= 3:
                        biome_colors[biome_name] = color[:3]  # Nur RGB, ignoriere Alpha falls vorhanden
                
                self._log("info", f"Loaded {len(biome_colors)} biome colors from {biomes_json_path}")
        except Exception as e:
            self._log("error", f"Error loading biome colors: {e}")
        
        return biome_colors
    
    def add_colorized_biome_textures(self, biomes_json_path: str = "data/worldgen/biomes.json"):
        """
        Generiere colorisierte Texturen für alle Biome aus biomes.json.
        
        Für jedes Biom:
        - Lade base_texture und colorisiere
        - Extrahiere Overlay-Namen aus variance_system
        - Lade und colorisiere alle Overlays
        - Generiere Rotationen für alle Texturen
        
        Args:
            biomes_json_path: Pfad zur biomes.json Datei
        """
        # Lade Biom-Farben
        biome_colors = self._load_biome_colorization(biomes_json_path)
        
        if not biome_colors:
            self._log("warning", "No biome colors loaded, skipping colorization")
            return
        
        colorized_count = 0
        
        # Iteriere über alle Biome
        for biome_name, target_color in biome_colors.items():
            # Prüfe ob Biom in texture_mapping.json existiert
            if biome_name not in self.texture_mapping:
                continue
            
            mapping = self.texture_mapping[biome_name]
            base_path_str = mapping.get("base_path", "assets/tiles/core")
            base_path_obj = Path(base_path_str)
            base_texture = mapping.get("base_texture", "")
            
            if not base_texture:
                continue
            
            # Lade und colorisiere base_texture
            texture_paths = [
                base_path_obj / f"{base_texture}.png",
                base_path_obj / f"{base_texture}",
                Path("assets/tiles/core") / f"{base_texture}.png",
            ]
            
            source_img = None
            for texture_path in texture_paths:
                source_img = self._load_texture_from_path(texture_path)
                if source_img:
                    break
            
            if source_img:
                # Base texture: Standard-Colorization
                colorized_img = self._colorize_texture(source_img, target_color)
                colorized_name = f"{biome_name}:{base_texture}"
                self.texture_images[colorized_name] = colorized_img
                colorized_count += 1
                self._log("info", f"Colorized base texture: {colorized_name} with color {target_color}")
                
                # Generiere 4 Rotations-Varianten
                self._generate_rotations(colorized_name, colorized_img)
            
            # Extrahiere Overlay-Namen aus variance_system
            overlay_names = self._extract_overlay_names(mapping)
            
            # Entferne base_texture aus overlay_names (wurde bereits verarbeitet)
            if base_texture in overlay_names:
                overlay_names.remove(base_texture)
            
            # Lade und colorisiere alle Overlays
            if overlay_names:
                self._load_overlay_textures(biome_name, overlay_names, base_path_obj, target_color)
                # Zähle: Jede Overlay-Textur + 4 Rotationen = 5 Texturen pro Overlay
                colorized_count += len(overlay_names) * 5
        
        self._log("info", f"Generated {colorized_count} colorized textures for biomes")
    
    def _load_all_textures(self):
        """Load all base textures from mapping file"""
        loaded_textures = set()  # Track loaded texture names to avoid duplicates
        
        # Load base textures from mapping file
        for tile_id, mapping in self.texture_mapping.items():
            base_path_str = mapping.get("base_path", "assets/tiles/core")
            base_path_obj = Path(base_path_str)
            base_texture = mapping.get("base_texture", "")
            
            if not base_texture:
                continue
            
            if base_texture in loaded_textures:
                continue  # Already loaded
            
            # Try different possible paths
            texture_paths = [
                base_path_obj / f"{base_texture}.png",
                base_path_obj / f"{base_texture}",
                Path("assets/tiles/core") / f"{base_texture}.png",
            ]
            
            img = None
            for texture_path in texture_paths:
                img = self._load_texture_from_path(texture_path)
                if img:
                    break
            
            if img:
                self.texture_images[base_texture] = img
                loaded_textures.add(base_texture)
                self._log("info", f"Loaded base texture: {base_texture} from {base_path_str}")
                
                # Generiere 4 Rotations-Varianten
                self._generate_rotations(base_texture, img)
        
        # Also load textures from default base_path (fallback for unmapped textures)
        if self.base_path.exists():
            for texture_file in self.base_path.glob("*.png"):
                if "_scaled" in texture_file.name:
                    continue
                
                tile_name = texture_file.stem
                if tile_name not in loaded_textures:
                    img = self._load_texture_from_path(texture_file)
                    if img:
                        self.texture_images[tile_name] = img
                        loaded_textures.add(tile_name)
                        self._log("info", f"Loaded texture: {tile_name} ({img.size[0]}x{img.size[1]})")
                        
                        # Generiere 4 Rotations-Varianten
                        self._generate_rotations(tile_name, img)
        
        # Also check assets/tiles for additional textures
        tiles_path = Path("assets/tiles/core")
        if tiles_path.exists():
            for texture_file in tiles_path.glob("*.png"):
                if "_scaled" in texture_file.name:
                    continue
                
                tile_name = texture_file.stem
                if tile_name not in loaded_textures:
                    img = self._load_texture_from_path(texture_file)
                    if img:
                        self.texture_images[tile_name] = img
                        loaded_textures.add(tile_name)
                        self._log("info", f"Loaded texture: {tile_name} from assets/tiles")
                        
                        # Generiere 4 Rotations-Varianten
                        self._generate_rotations(tile_name, img)
    
    def _build_texture_atlas(self):
        """Build a dynamic texture atlas from all loaded textures (including colorized textures and decorations)"""
        if not self.texture_images:
            self._log("warning", "No textures to build atlas from")
            return
        
        # Separate tiles and decorations (decorations can have variable sizes)
        tile_textures = {}  # Standard tile textures (16x16)
        decoration_textures = {}  # Decoration textures (variable sizes)
        
        for name, img in self.texture_images.items():
            if name.startswith("decoration:"):
                decoration_textures[name] = img
            else:
                tile_textures[name] = img
        
        # Build atlas: first pack tiles, then decorations
        import math
        
        # Calculate tile section size
        num_tiles = len(tile_textures)
        if num_tiles > 0:
            tile_grid_size = math.ceil(math.sqrt(num_tiles))
            tile_section_width = tile_grid_size * self.tile_size
            tile_section_height = tile_grid_size * self.tile_size
        else:
            tile_grid_size = 0
            tile_section_width = 0
            tile_section_height = 0
        
        # Calculate decoration section size (use max decoration size, default 64x64)
        max_decoration_size = 64  # Maximum expected decoration size
        num_decorations = len(decoration_textures)
        if num_decorations > 0:
            decoration_grid_size = math.ceil(math.sqrt(num_decorations))
            decoration_section_width = decoration_grid_size * max_decoration_size
            decoration_section_height = decoration_grid_size * max_decoration_size
        else:
            decoration_grid_size = 0
            decoration_section_width = 0
            decoration_section_height = 0
        
        # Calculate total atlas size
        total_width = max(tile_section_width, decoration_section_width)
        total_height = tile_section_height + decoration_section_height
        
        # Round up to nearest power of 2 for better GPU performance
        def next_power_of_2(n):
            if n <= 0:
                return 1
            return 2 ** math.ceil(math.log2(n))
        
        atlas_width = next_power_of_2(total_width) if total_width > 0 else 256
        atlas_height = next_power_of_2(total_height) if total_height > 0 else 256
        
        self.atlas_size = max(atlas_width, atlas_height)
        
        # Create atlas image
        atlas_img = Image.new("RGBA", (self.atlas_size, self.atlas_size), (0, 0, 0, 0))
        
        # Pack tile textures (top section)
        texture_list = list(tile_textures.items())
        for idx, (tile_name, img) in enumerate(texture_list):
            # Calculate grid position
            grid_x = idx % tile_grid_size if tile_grid_size > 0 else 0
            grid_y = idx // tile_grid_size if tile_grid_size > 0 else 0
            
            # Calculate pixel position in atlas
            atlas_x = grid_x * self.tile_size
            atlas_y = grid_y * self.tile_size
            
            # Resize if needed (shouldn't happen for tiles, but just in case)
            if img.size != (self.tile_size, self.tile_size):
                img = img.resize((self.tile_size, self.tile_size), Image.Resampling.NEAREST)
            
            # Paste texture into atlas
            atlas_img.paste(img, (atlas_x, atlas_y))
            
            # Calculate UV coordinates (normalized 0.0-1.0)
            # Add small offset to avoid edge bleeding
            offset = 0.5 / self.atlas_size
            u0 = (atlas_x + offset) / self.atlas_size
            v0 = (atlas_y + offset) / self.atlas_size
            u1 = (atlas_x + self.tile_size - offset) / self.atlas_size
            v1 = (atlas_y + self.tile_size - offset) / self.atlas_size
            
            # Store UV coordinates for this texture
            self.texture_coords[tile_name] = (u0, v0, u1, v1)
        
        # Pack decoration textures (bottom section)
        decoration_list = list(decoration_textures.items())
        decoration_start_y = tile_section_height  # Start decorations after tiles
        
        for idx, (decoration_name, img) in enumerate(decoration_list):
            # Calculate grid position
            grid_x = idx % decoration_grid_size if decoration_grid_size > 0 else 0
            grid_y = idx // decoration_grid_size if decoration_grid_size > 0 else 0
            
            # Calculate pixel position in atlas (in decoration section)
            atlas_x = grid_x * max_decoration_size
            atlas_y = decoration_start_y + grid_y * max_decoration_size
            
            # Resize decoration to fit in slot (center it if smaller)
            img_width, img_height = img.size
            if img_width > max_decoration_size or img_height > max_decoration_size:
                # Scale down if too large
                scale = min(max_decoration_size / img_width, max_decoration_size / img_height)
                new_width = int(img_width * scale)
                new_height = int(img_height * scale)
                img = img.resize((new_width, new_height), Image.Resampling.NEAREST)
                img_width, img_height = img.size
            
            # Center decoration in slot
            offset_x = (max_decoration_size - img_width) // 2
            offset_y = (max_decoration_size - img_height) // 2
            
            # Paste texture into atlas (centered in slot)
            atlas_img.paste(img, (atlas_x + offset_x, atlas_y + offset_y), img if img.mode == 'RGBA' else None)
            
            # Calculate UV coordinates (normalized 0.0-1.0) for actual image bounds
            # Note: V coordinates are NOT flipped here - they are flipped in world_renderer.py
            # when creating the vertex data (similar to how tiles are handled)
            offset = 0.5 / self.atlas_size
            u0 = (atlas_x + offset_x + offset) / self.atlas_size
            v0 = (atlas_y + offset_y + offset) / self.atlas_size
            u1 = (atlas_x + offset_x + img_width - offset) / self.atlas_size
            v1 = (atlas_y + offset_y + img_height - offset) / self.atlas_size
            
            # Store UV coordinates for this decoration (V will be flipped in renderer)
            self.texture_coords[decoration_name] = (u0, v0, u1, v1)
        
        # Build variant mappings: extract from variance_system.growth_patterns
        for tile_id, mapping in self.texture_mapping.items():
            overlay_names = self._extract_overlay_names(mapping)
            
            if not overlay_names:
                continue  # No variants for this biome
            
            variant_coords_list = []
            for overlay_name in overlay_names:
                # Check for colorized variant first (biome_name:overlay_name)
                colorized_name = f"{tile_id}:{overlay_name}"
                if colorized_name in self.texture_coords:
                    variant_coords_list.append(self.texture_coords[colorized_name])
                # Fallback to original variant if colorized not available
                elif overlay_name in self.texture_coords:
                    variant_coords_list.append(self.texture_coords[overlay_name])
            
            if variant_coords_list:
                self.variant_coords[tile_id] = variant_coords_list
        
        # Create ModernGL texture from atlas
        atlas_data = np.array(atlas_img, dtype=np.uint8)
        self.texture_atlas = self.ctx.texture((self.atlas_size, self.atlas_size), 4, atlas_data.tobytes())
        # Use NEAREST filtering for sharp pixel-perfect transitions between tiles
        # No mipmaps to avoid blurry transitions
        self.texture_atlas.filter = (moderngl.NEAREST, moderngl.NEAREST)
        
        # Count total textures in atlas
        num_textures = len(self.texture_coords)
        self._log("info", f"Built texture atlas: {self.atlas_size}x{self.atlas_size} with {num_textures} textures")
        self._log("info", f"Variant mappings: {len(self.variant_coords)} biomes with variants")
    
    def get_texture_coords(self, tile_id: str, world_x: int = None, world_y: int = None) -> Optional[tuple]:
        """
        Get UV coordinates for a tile_id in the texture atlas.
        Uses Organic Growth system if variance_system is configured.
        
        Args:
            tile_id: Tile ID (e.g., "terrain:plains")
            world_x: World X coordinate for deterministic selection (optional)
            world_y: World Y coordinate for deterministic selection (optional)
        
        Returns:
            (u0, v0, u1, v1) tuple or None if not found
        """
        if tile_id not in self.texture_mapping:
            return None
        
        mapping = self.texture_mapping[tile_id]
        base_texture = mapping.get("base_texture", "")
        variance_system = mapping.get("variance_system", {})
        rotation_enabled = variance_system.get("rotation_enabled", True)
        growth_patterns = variance_system.get("growth_patterns", [])
        variance_mode = variance_system.get("mode", "")
        use_organic_growth = variance_mode == "organic_growth" and len(growth_patterns) > 0
        
        # Check if organic growth should be used
        if not use_organic_growth:
            # No organic growth configured, use base texture
            colorized_name = f"{tile_id}:{base_texture}"
            coords = self._get_rotated_texture_coords(colorized_name, world_x, world_y, rotation_enabled)
            if coords is None:
                # Debug: Log missing texture
                self._log("warning", f"Texture not found for {colorized_name} (tile_id={tile_id}, base_texture={base_texture})")
                # Try fallback to non-colorized base texture
                if base_texture in self.texture_coords:
                    self._log("debug", f"Using fallback non-colorized texture: {base_texture}")
                    return self._get_rotated_texture_coords(base_texture, world_x, world_y, rotation_enabled)
            return coords
        
        # Organic growth requires world coordinates
        if world_x is None or world_y is None:
            # Fallback: base_texture mit Rotation (no world coords available)
            colorized_name = f"{tile_id}:{base_texture}"
            coords = self._get_rotated_texture_coords(colorized_name, world_x, world_y, rotation_enabled)
            if coords is None:
                # Debug: Log missing texture
                self._log("warning", f"Texture not found for {colorized_name} (tile_id={tile_id}, base_texture={base_texture}, world_x={world_x}, world_y={world_y})")
                # Try fallback to non-colorized base texture
                if base_texture in self.texture_coords:
                    self._log("debug", f"Using fallback non-colorized texture: {base_texture}")
                    return self._get_rotated_texture_coords(base_texture, world_x, world_y, rotation_enabled)
            return coords
        
        # Organic Growth System: Prüfe jedes Pattern
        # Sortiere Patterns nach noise_threshold absteigend, damit seltene Patterns zuerst geprüft werden
        sorted_patterns = sorted(
            growth_patterns, 
            key=lambda p: p.get("noise_threshold", 0.6), 
            reverse=True
        )
        
        for pattern in sorted_patterns:
            overlay_texture_name = pattern.get("overlay")
            if not overlay_texture_name:
                continue
            
            # Berechne Cluster-Wert
            cluster_value = self._calculate_cluster_value(world_x, world_y, pattern)
            noise_threshold = pattern.get("noise_threshold", 0.6)
            
            if cluster_value >= noise_threshold:
                # Verwende diese Overlay-Variante mit Rotation
                colorized_name = f"{tile_id}:{overlay_texture_name}"
                coords = self._get_rotated_texture_coords(colorized_name, world_x, world_y, rotation_enabled)
                if coords:
                    return coords
                else:
                    # Variant texture not found in atlas - try direct lookup without rotation
                    if colorized_name in self.texture_coords:
                        # Found base variant without rotation, use it
                        return self.texture_coords[colorized_name]
                    elif overlay_texture_name in self.texture_coords:
                        # Found non-colorized variant, use it
                        return self.texture_coords[overlay_texture_name]
                    else:
                        # Variant texture not found in atlas
                        if not hasattr(self, '_variant_missing_counter'):
                            self._variant_missing_counter = 0
                        self._variant_missing_counter += 1
                        
                        if self._variant_missing_counter % 100 == 0:
                            self._log("warning", f"Variant texture {colorized_name} not found in atlas for {tile_id} at ({world_x}, {world_y})")
        
        # Kein Pattern matched: Verwende base_texture mit Rotation
        colorized_name = f"{tile_id}:{base_texture}"
        return self._get_rotated_texture_coords(colorized_name, world_x, world_y, rotation_enabled)
    
    def get_overlay_texture(self, tile_id: str, world_x: int, world_y: int) -> Optional[tuple]:
        """
        Get overlay texture for a tile based on noise-based placement rules.
        
        Args:
            tile_id: Tile ID (e.g., "terrain:plains")
            world_x: World X coordinate
            world_y: World Y coordinate
        
        Returns:
            (u0, v0, u1, v1) tuple for overlay texture, or None if no overlay should be placed
        """
        # Check if tile_id has overlay configuration
        if tile_id not in self.texture_mapping:
            return None
        
        mapping = self.texture_mapping[tile_id]
        
        # Check if variance_system is configured
        variance_system = mapping.get("variance_system", {})
        growth_patterns = variance_system.get("growth_patterns", [])
        use_organic_growth = variance_system.get("mode") == "organic_growth" and growth_patterns
        rotation_enabled = variance_system.get("rotation_enabled", True)
        
        if use_organic_growth:
            # Use organic growth system
            for pattern in growth_patterns:
                texture_name = pattern.get("overlay")
                if not texture_name:
                    continue
                
                # Calculate cluster value
                cluster_value = self._calculate_cluster_value(world_x, world_y, pattern)
                noise_threshold = pattern.get("noise_threshold", 0.6)
                
                if cluster_value >= noise_threshold:
                    # This overlay should be placed
                    # Try colorized variant first
                    colorized_name = f"{tile_id}:{texture_name}"
                    coords = self._get_rotated_texture_coords(colorized_name, world_x, world_y, rotation_enabled)
                    if coords:
                        return coords
                    
                    # Fallback to original texture with rotation
                    coords = self._get_rotated_texture_coords(texture_name, world_x, world_y, rotation_enabled)
                    if coords:
                        return coords
        
        # Fallback to old overlay system (backward compatible)
        overlays = mapping.get("overlays", [])
        
        if not overlays:
            return None
        
        # Check each overlay configuration
        for overlay_config in overlays:
            texture_name = overlay_config.get("texture")
            chance = overlay_config.get("chance", 0.1)
            noise_scale = overlay_config.get("noise_scale", 0.1)
            noise_threshold = overlay_config.get("noise_threshold", 0.5)
            
            if not texture_name:
                continue
            
            # Calculate noise value for this position
            # Use different noise offsets for each overlay type to avoid correlation
            overlay_seed_offset = hash(texture_name) % 10000
            noise_x = world_x * noise_scale + overlay_seed_offset
            noise_y = world_y * noise_scale + overlay_seed_offset
            
            # Get noise value (-1 to 1)
            noise_value = self.overlay_noise.noise2(noise_x, noise_y)
            
            # Normalize to 0-1
            normalized_noise = (noise_value + 1.0) / 2.0
            
            # Check if noise exceeds threshold (higher = more sparse)
            if normalized_noise < noise_threshold:
                continue
            
            # Apply chance factor (further reduces placement)
            if normalized_noise < (noise_threshold + (1.0 - noise_threshold) * chance):
                continue
            
            # This overlay should be placed
            # Try colorized variant first
            colorized_name = f"{tile_id}:{texture_name}"
            coords = self._get_rotated_texture_coords(colorized_name, world_x, world_y, rotation_enabled)
            if coords:
                return coords
            
            # Fallback to original texture with rotation
            coords = self._get_rotated_texture_coords(texture_name, world_x, world_y, rotation_enabled)
            if coords:
                return coords
        
        return None
    
    def get_texture(self, tile_id: str) -> Optional[moderngl.Texture]:
        """
        Get texture atlas (all textures are in one atlas)
        
        Args:
            tile_id: Tile ID (ignored, returns atlas)
        
        Returns:
            ModernGL Texture Atlas or None if not found
        """
        return self.texture_atlas
    
    def has_texture(self, tile_id: str) -> bool:
        """Check if texture exists for tile_id"""
        if tile_id not in self.texture_mapping:
            return False
        
        mapping = self.texture_mapping[tile_id]
        base_texture = mapping.get("base_texture", "")
        if not base_texture:
            return False
        
        # Check if colorized texture exists in atlas
        colorized_name = f"{tile_id}:{base_texture}"
        if colorized_name in self.texture_coords:
            return True
        
        # Fallback: check if base texture exists
        if base_texture in self.texture_coords:
            return True
        
        return False
    
    def cleanup(self):
        """Release all textures"""
        for texture in self.textures.values():
            if hasattr(texture, 'release'):
                texture.release()
        self.textures.clear()
        self.texture_images.clear()
        if self.texture_atlas:
            self.texture_atlas.release()
            self.texture_atlas = None
        self.texture_coords.clear()

