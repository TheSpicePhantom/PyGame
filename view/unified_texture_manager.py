"""
Unified Texture Manager - Ersetzt TileTextureManager.
Kombiniert TextureCollector + TextureAtlasBuilder für deklaratives Texture-Management.
"""
import moderngl
import json
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from PIL import Image
import numpy as np
from core import settings
from opensimplex import OpenSimplex

from view.texture_collector import TextureCollector
from view.texture_atlas_builder import TextureAtlasBuilder


class UnifiedTextureManager:
    """
    Unified Texture Manager - Ersetzt TileTextureManager.
    
    Bietet kompatible API zu TileTextureManager:
    - get_texture_coords(tile_id) - für Tiles
    - get_decoration_texture_coords(sprite_name, mod_id) - für Decorations
    - texture_atlas - ModernGL Texture
    - texture_coords - UV-Map Dictionary
    """
    
    FALLBACK_COLOR = (255, 0, 255, 255)  # Pink für fehlende Texturen
    
    def __init__(self, ctx: moderngl.Context, base_path: str = "assets/tiles/core", 
                 mapping_file: str = "data/textures/texture_mapping.json", diagnostics=None):
        """
        Initialize Unified Texture Manager.
        
        Args:
            ctx: ModernGL context
            base_path: Base path to tile textures directory (legacy, kept for compatibility)
            mapping_file: Path to texture mapping JSON file (legacy, kept for compatibility)
            diagnostics: Optional DiagnosticsService instance for logging
        """
        self.ctx = ctx
        self.base_path = Path(base_path)
        self.mapping_file = Path(mapping_file)
        self.diagnostics = diagnostics
        self.tile_size = settings.TILE_SIZE
        
        # Texture management
        self.texture_atlas: Optional[moderngl.Texture] = None
        self.texture_coords: Dict[str, tuple] = {}  # texture_id -> (u0, v0, u1, v1)
        self.variant_coords: Dict[str, List[tuple]] = {}  # tile_id -> list of (u0, v0, u1, v1) for variants
        self.atlas_size = 0
        self.failed_textures = set()
        
        # Texture mapping for variance system
        self.texture_mapping: Dict[str, dict] = {}
        self.mapping_file = Path("data/textures/texture_mapping.json")
        
        # Overlay noise generator for deterministic placement
        # Use a fixed seed offset to ensure consistency across game sessions
        self.overlay_noise = OpenSimplex(seed=12345)
        
        # Multi-octave noise generators for organic growth patterns
        # Different seeds for each octave to ensure independence
        self.octave_noises = [
            OpenSimplex(seed=12345 + i * 1000) for i in range(4)  # Support up to 4 octaves
        ]
        
        # Load texture mapping configuration
        self._load_texture_mapping()
        
        # Build tile_id to texture_mapping key mapping (from biomes.json)
        self._build_tile_id_mapping()
        
        # Initialize collector and builder
        self.collector = TextureCollector()
        self.builder = TextureAtlasBuilder(tile_size=self.tile_size)
        
        # Build atlas
        self._build_atlas()
    
    def _load_texture_mapping(self):
        """Load texture mapping configuration from JSON file."""
        if not self.mapping_file.exists():
            return
        
        try:
            with open(self.mapping_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.texture_mapping = data.get("texture_mappings", {})
        except Exception as e:
            pass
    
    def _build_tile_id_mapping(self):
        """Build mapping from tile_id (from biomes.json) to texture_mapping key."""
        # Map tile_id -> texture_mapping key
        # e.g., "core:grass" -> "terrain:plains"
        self.tile_id_to_mapping_key = {}
        
        biomes_file = Path("data/worldgen/biomes.json")
        if not biomes_file.exists():
            return
        
        try:
            with open(biomes_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                biomes = data.get("biomes", {})
                
                for biome_name, biome_data in biomes.items():
                    tile_id = biome_data.get("tile_id")
                    if tile_id:
                        # Try direct match first
                        if biome_name in self.texture_mapping:
                            self.tile_id_to_mapping_key[tile_id] = biome_name
                        else:
                            # Try to find matching texture_mapping key
                            # Some biomes might use different naming (e.g., "water:deep" vs "terrain:water")
                            found_mapping = False
                            for mapping_key in self.texture_mapping.keys():
                                # Check if biome_name matches mapping_key or if they're similar
                                if biome_name == mapping_key or (':' in biome_name and biome_name.split(':')[1] in mapping_key):
                                    self.tile_id_to_mapping_key[tile_id] = mapping_key
                                    found_mapping = True
                                    break
        except Exception as e:
            pass
    
    def _build_atlas(self):
        """Baut Atlas aus gesammelten Texture-Referenzen oder lädt Pre-Built Atlas."""
        # Check if pre-built atlas exists
        atlas_path = Path("data/atlas.png")
        uv_map_path = Path("data/atlas_uv_map.json")
        
        # Force runtime build for testing (set to False to enable pre-built loading)
        FORCE_RUNTIME_BUILD = True  # TODO: Set to False for production
        
        if not FORCE_RUNTIME_BUILD and atlas_path.exists() and uv_map_path.exists():
            if self._load_prebuilt_atlas():
                return
        
        # 1. Collect texture references (use cache if available)
        texture_references = self.collector.load_texture_list()
        if not texture_references:
            # Cache not found or invalid, collect from scratch
            texture_references = self.collector.collect_all_textures()
            # Save cache for next time
            self.collector.save_texture_list()
        
        # 2. Add fallback textures
        self._add_fallback_textures(texture_references)
        
        # 3. Generate colorized textures and rotations (before building atlas)
        # This adds textures to builder.texture_images
        self._generate_colorized_textures()
        
        # 4. Build atlas (includes base textures, colorized textures, and rotations)
        if not self.builder.build_atlas(texture_references):
            return
        
        # 5. Convert UV map to texture_coords (with proper key format)
        self._convert_uv_map()
        
        # 6. Create ModernGL texture from atlas image
        self._create_modern_gl_texture()
        
        # 7. Save atlas to disk for debugging/inspection
        self.builder.save_atlas()
        
        # 8. Validate UV map
        self._validate_uv_map()
        
    def _load_prebuilt_atlas(self) -> bool:
        """
        Lädt Pre-Built Atlas von Disk.
        
        Returns:
            True wenn erfolgreich, False bei Fehler
        """
        try:
            atlas_path = Path("data/atlas.png")
            uv_map_path = Path("data/atlas_uv_map.json")
            
            # Load atlas image
            from PIL import Image
            atlas_image = Image.open(atlas_path)
            self.atlas_size = atlas_image.size[0]  # Should be square
            
            # Load UV map
            import json
            with open(uv_map_path, 'r', encoding='utf-8') as f:
                builder_uv_map = json.load(f)
            
            
            # Convert UV map to texture_coords (with proper key format)
            converted_count = 0
            skipped_count = 0
            
            for texture_ref, uv_coords in builder_uv_map.items():
                # Check if this is a direct name (colorized texture or rotation variant)
                if ':' in texture_ref and texture_ref.count(':') >= 2:
                    # Direct name format - use as-is
                    self.texture_coords[texture_ref] = tuple(uv_coords)
                    converted_count += 1
                    continue
                
                parts = texture_ref.split('/')
                if len(parts) < 3:
                    skipped_count += 1
                    continue
                
                category = parts[0]
                mod_id = parts[1]
                # Join all remaining parts to handle nested paths
                sprite_name = '/'.join(parts[2:])
                
                if category == "decoration":
                    # Format: "decoration:mod_id/sprite_name" (unterstützt verschachtelte Pfade)
                    key = f"decoration:{mod_id}/{sprite_name}"
                    self.texture_coords[key] = tuple(uv_coords)
                    converted_count += 1
                elif category == "tile":
                    # Format: "tile_name"
                    key = sprite_name
                    self.texture_coords[key] = tuple(uv_coords)
                    converted_count += 1
                elif category == "item":
                    # Format: "item:mod_id/sprite_name" (for future use)
                    key = f"item:{mod_id}/{sprite_name}"
                    self.texture_coords[key] = tuple(uv_coords)
                    converted_count += 1
                elif category == "tool":
                    # Format: "tool:mod_id/sprite_name" (for future use)
                    key = f"tool:{mod_id}/{sprite_name}"
                    self.texture_coords[key] = tuple(uv_coords)
                    converted_count += 1
                else:
                    skipped_count += 1
            
            # Create ModernGL texture from atlas image
            img_data = atlas_image.tobytes()
            self.texture_atlas = self.ctx.texture((self.atlas_size, self.atlas_size), 4, img_data)
            self.texture_atlas.filter = (moderngl.NEAREST, moderngl.NEAREST)
            self.texture_atlas.build_mipmaps()
            
            # Validate loaded atlas
            self._validate_uv_map()
            
            return True
            
        except Exception as e:
            return False
    
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
            center_x = round(world_x / cluster_size) * cluster_size
            center_y = round(world_y / cluster_size) * cluster_size
            
            dx = world_x - center_x
            dy = world_y - center_y
            distance = math.sqrt(dx * dx + dy * dy)
            
            center_noise = self._multi_octave_noise(
                center_x * noise_scale, 
                center_y * noise_scale, 
                octaves=3,
                seed_offset=seed_offset
            )
            
            radial_factor = math.exp(-distance / (cluster_size * 2.0))
            cluster_value = center_noise * radial_factor * cluster_density * 10.0
            
        elif spread_bias == "directional":
            spread_direction = pattern.get("spread_direction", [1, 0])
            if len(spread_direction) != 2:
                spread_direction = [1, 0]
            
            dir_length = math.sqrt(spread_direction[0]**2 + spread_direction[1]**2)
            if dir_length > 0:
                spread_direction = [spread_direction[0] / dir_length, spread_direction[1] / dir_length]
            
            projection = world_x * spread_direction[0] + world_y * spread_direction[1]
            
            noise_value = self._multi_octave_noise(
                projection * noise_scale,
                (world_x + world_y) * noise_scale * 0.5,
                octaves=3,
                seed_offset=seed_offset
            )
            
            cluster_value = noise_value * cluster_density * 10.0
            
        else:  # uniform
            noise_x = world_x * noise_scale + seed_offset
            noise_y = world_y * noise_scale + seed_offset
            
            noise_value = self.overlay_noise.noise2(noise_x, noise_y)
            normalized_noise = (noise_value + 1.0) / 2.0
            
            cluster_value = normalized_noise * cluster_density * 10.0
        
        return max(0.0, min(1.0, cluster_value))  # Clip auf [0, 1]
    
    def _load_biome_colors(self, biomes_json_path: str = "data/worldgen/biomes.json") -> Dict[str, List[int]]:
        """
        Lädt Biome-Farben aus biomes.json.
        
        Args:
            biomes_json_path: Pfad zur biomes.json Datei
        
        Returns:
            Dictionary: {biome_name: [R, G, B]}
        """
        biome_colors = {}
        biomes_path = Path(biomes_json_path)
        
        if not biomes_path.exists():
            return biome_colors
        
        try:
            with open(biomes_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                biomes = data.get("biomes", {})
                
                for biome_name, biome_data in biomes.items():
                    color = biome_data.get("color")
                    if color and isinstance(color, list) and len(color) >= 3:
                        biome_colors[biome_name] = color[:3]  # Nur RGB, ignoriere Alpha falls vorhanden
        except Exception as e:
            pass
        
        return biome_colors
    
    def _generate_colorized_textures(self):
        """Generiert colorized Varianten für Biome-Tiles."""
        if not self.texture_mapping:
            return
        
        # Load biome colors from biomes.json
        biome_colors = self._load_biome_colors()
        
        if not biome_colors:
            return
        
        colorized_count = 0
        
        for tile_id, mapping in self.texture_mapping.items():
            base_texture = mapping.get("base_texture", '')
            if not base_texture:
                continue
            
            # Get biome color from biomes.json
            target_color = biome_colors.get(tile_id)
            if not target_color:
                # Try to find color by matching tile_id with biome names
                # Some biomes might use different naming (e.g., "core:grass" vs "terrain:plains")
                # Try direct match first, then check if tile_id contains the biome name
                for biome_name, color in biome_colors.items():
                    if tile_id == biome_name or (':' in tile_id and tile_id.split(':')[1] in biome_name):
                        target_color = color
                        break
                
                # Fallback to default gray if still not found
                if not target_color:
                    target_color = [128, 128, 128]  # Default gray
            
            # Load base texture
            base_path = mapping.get('base_path', 'assets')
            # Construct full path: base_path is "assets", so we need assets/tile/core/{base_texture}.png
            if base_path == "assets":
                texture_path = Path("assets/tile/core") / f"{base_texture}.png"
            else:
                texture_path = Path(base_path) / f"{base_texture}.png"
            
            if not texture_path.exists():
                continue
            
            try:
                source_img = Image.open(texture_path).convert("RGBA")
                if source_img.size[0] != self.tile_size or source_img.size[1] != self.tile_size:
                    source_img = source_img.resize((self.tile_size, self.tile_size), Image.Resampling.LANCZOS)
            except Exception as e:
                continue
            
            # Colorize base texture
            colorized_name = f"{tile_id}:{base_texture}"
            colorized_img = self._colorize_texture(source_img, target_color)
            self.builder.texture_images[colorized_name] = colorized_img
            colorized_count += 1
            
            # Generate rotations for colorized texture
            variance_system = mapping.get('variance_system', {})
            rotation_enabled = variance_system.get('rotation_enabled', True)
            if rotation_enabled:
                self._generate_rotations(colorized_name, colorized_img)
                colorized_count += 3  # 3 rotations (90, 180, 270)
            
            # Process overlay textures
            growth_patterns = variance_system.get('growth_patterns', [])
            for pattern in growth_patterns:
                overlay = pattern.get('overlay')
                if not overlay:
                    continue
                
                # Construct overlay path
                if base_path == "assets":
                    overlay_path = Path("assets/tile/core") / f"{overlay}.png"
                else:
                    overlay_path = Path(base_path) / f"{overlay}.png"
                
                if not overlay_path.exists():
                    continue
                
                try:
                    overlay_img = Image.open(overlay_path).convert("RGBA")
                    if overlay_img.size[0] != self.tile_size or overlay_img.size[1] != self.tile_size:
                        overlay_img = overlay_img.resize((self.tile_size, self.tile_size), Image.Resampling.LANCZOS)
                except Exception as e:
                    continue
                
                # Colorize overlay (preserve accents for overlays)
                overlay_colorized_name = f"{tile_id}:{overlay}"
                if overlay.endswith('_1') or overlay == 'plains_grass_1':
                    overlay_colorized = self._colorize_texture(overlay_img, target_color)
                else:
                    overlay_colorized = self._colorize_texture_preserve_accents(overlay_img, target_color)
                
                self.builder.texture_images[overlay_colorized_name] = overlay_colorized
                colorized_count += 1
                
                # Generate rotations for overlay
                if rotation_enabled:
                    self._generate_rotations(overlay_colorized_name, overlay_colorized)
                    colorized_count += 3  # 3 rotations
    
    def _generate_rotations(self, base_name: str, img: Image.Image) -> None:
        """
        Generiert 4 Rotationen (0°, 90°, 180°, 270°) für eine Textur.
        Speichert als {base_name}_r{degrees} in builder.texture_images.
        
        Args:
            base_name: Basis-Name der Textur (ohne Rotation)
            img: PIL Image (RGBA)
        """
        for rotation_deg in [90, 180, 270]:  # Skip 0° (original already in texture_images)
            rotated_img = self._rotate_texture(img, rotation_deg)
            rotation_key = f"{base_name}_r{rotation_deg}"
            self.builder.texture_images[rotation_key] = rotated_img
    
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
        
        # Berechne Luminanz pro Pixel (gewichtete Summe)
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
        
        # Erhalte Akzent-Pixel (Original-Farbe)
        result[:,:,:3][accent_mask] = img_array[:,:,:3][accent_mask]
        
        # Alpha-Kanal bleibt unverändert
        result[:,:,3] = img_array[:,:,3]
        
        # Clip und zurück zu 0-255
        result = np.clip(result * 255, 0, 255).astype(np.uint8)
        
        return Image.fromarray(result, mode='RGBA')
    
    def _rotate_texture(self, img: Image.Image, degrees: int) -> Image.Image:
        """
        Rotiert ein PIL Image um angegebene Grad (90, 180, 270).
        
        Args:
            img: PIL Image (RGBA)
            degrees: Rotationswinkel in Grad (90, 180, 270)
        
        Returns:
            Rotiertes PIL Image (RGBA)
        """
        if degrees == 90:
            return img.transpose(Image.ROTATE_90)
        elif degrees == 180:
            return img.transpose(Image.ROTATE_180)
        elif degrees == 270:
            return img.transpose(Image.ROTATE_270)
        else:
            # Fallback: Verwende rotate() für andere Winkel
            return img.rotate(-degrees, expand=False, fillcolor=(0, 0, 0, 0))
    
    def _add_fallback_textures(self, texture_references: Dict[str, list]):
        """Fügt Fallback-Texturen hinzu."""
        # Add decoration fallback
        if 'decorations' not in texture_references:
            texture_references['decorations'] = []
        texture_references['decorations'].append('decoration/fallback/fallback')
    
    def _convert_uv_map(self):
        """Konvertiert UV-Map vom Builder-Format zum TileTextureManager-Format."""
        # Builder uses format: "category/mod_id/sprite_name" for collected textures
        # But also stores direct names like "terrain:plains:plains_grass_1" for colorized textures
        # TileTextureManager uses format: "tile_name" or "decoration:mod_id/sprite_name" or "tile_id:base_texture"
        
        converted_count = 0
        skipped_count = 0
        
        for texture_ref, uv_coords in self.builder.uv_map.items():
            # Check if this is a direct name (colorized texture or rotation variant)
            # Format: "terrain:plains:plains_grass_1" or "terrain:plains:plains_grass_1_r90"
            if ':' in texture_ref and texture_ref.count(':') >= 2:
                # Direct name format - use as-is (already in correct format)
                self.texture_coords[texture_ref] = tuple(uv_coords)
                converted_count += 1
                continue
            
            # Standard format: "category/mod_id/sprite_name" (kann verschachtelte Pfade enthalten)
            parts = texture_ref.split('/')
            if len(parts) < 3:
                # Might be a direct tile name without category/mod_id
                if texture_ref in self.builder.texture_images:
                    self.texture_coords[texture_ref] = tuple(uv_coords)
                    converted_count += 1
                else:
                    skipped_count += 1
                continue
            
            category = parts[0]
            mod_id = parts[1]
            # Join all remaining parts to handle nested paths (e.g., "apple/autumn/apple_1")
            sprite_name = '/'.join(parts[2:])
            
            if category == "decoration":
                # Format: "decoration:mod_id/sprite_name" (unterstützt verschachtelte Pfade)
                key = f"decoration:{mod_id}/{sprite_name}"
                self.texture_coords[key] = tuple(uv_coords)
                converted_count += 1
            elif category == "tile":
                # Format: "tile_name"
                key = sprite_name
                self.texture_coords[key] = tuple(uv_coords)
                converted_count += 1
            elif category == "item":
                # Format: "item:mod_id/sprite_name" (for future use)
                key = f"item:{mod_id}/{sprite_name}"
                self.texture_coords[key] = tuple(uv_coords)
                converted_count += 1
            elif category == "tool":
                # Format: "tool:mod_id/sprite_name" (for future use)
                key = f"tool:{mod_id}/{sprite_name}"
                self.texture_coords[key] = tuple(uv_coords)
                converted_count += 1
            else:
                skipped_count += 1
    
    def _create_modern_gl_texture(self):
        """Erstellt ModernGL Texture aus Atlas-Image."""
        if not self.builder.atlas_image:
            return
        
        # Get image data
        img = self.builder.atlas_image
        self.atlas_size = img.size[0]  # Should be square
        
        # Convert to bytes
        img_data = img.tobytes()
        
        # Create ModernGL texture
        self.texture_atlas = self.ctx.texture((self.atlas_size, self.atlas_size), 4, img_data)
        # Use NEAREST filtering for pixel-perfect rendering
        # Don't build mipmaps with NEAREST - causes black lines between tiles
        self.texture_atlas.filter = (moderngl.NEAREST, moderngl.NEAREST)
        # Set wrap mode to CLAMP_TO_EDGE to prevent sampling outside texture bounds
        self.texture_atlas.repeat_x = False
        self.texture_atlas.repeat_y = False
    
    def _get_rotated_texture_coords(self, base_name: str, world_x: int = None, world_y: int = None, rotation_enabled: bool = True) -> Optional[tuple]:
        """
        Holt Texture-Koordinaten mit Rotation, falls aktiviert.
        
        Args:
            base_name: Basis-Name der Textur (z.B. "terrain:plains:plains_grass_1")
            world_x: World X-Koordinate für deterministische Rotation
            world_y: World Y-Koordinate für deterministische Rotation
            rotation_enabled: Ob Rotation aktiviert ist
        
        Returns:
            (u0, v0, u1, v1) tuple oder None
        """
        if not rotation_enabled:
            # Rotation deaktiviert: Direkter Lookup
            if base_name in self.texture_coords:
                return self.texture_coords[base_name]
            return None
        
        # Rotation aktiviert: Wähle Variante basierend auf Welt-Koordinaten
        if world_x is not None and world_y is not None:
            # Deterministische Rotation basierend auf Position
            rotation_index = (world_x + world_y * 3) % 4
        else:
            # Fallback: Zufällige Rotation (nicht deterministisch)
            import random
            rotation_index = random.randint(0, 3)
        
        # Rotation-Varianten: 0° (original), 90°, 180°, 270°
        rotation_suffixes = ["", "_r90", "_r180", "_r270"]
        rotation_suffix = rotation_suffixes[rotation_index]
        
        # Versuche rotierte Variante
        rotated_name = f"{base_name}{rotation_suffix}"
        if rotated_name in self.texture_coords:
            return self.texture_coords[rotated_name]
        
        # Fallback: Original ohne Rotation
        if base_name in self.texture_coords:
            return self.texture_coords[base_name]
        
        return None
    
    def _get_rotated_texture_id_and_coords(self, base_name: str, world_x: int = None, world_y: int = None, rotation_enabled: bool = True) -> Tuple[Optional[str], Optional[tuple]]:
        """
        Holt Texture-ID und Koordinaten mit Rotation, falls aktiviert.
        
        Args:
            base_name: Basis-Name der Textur (z.B. "terrain:plains:plains_grass_1")
            world_x: World X-Koordinate für deterministische Rotation
            world_y: World Y-Koordinate für deterministische Rotation
            rotation_enabled: Ob Rotation aktiviert ist
        
        Returns:
            (texture_id, (u0, v0, u1, v1)) tuple oder (None, None)
        """
        if not rotation_enabled:
            # Rotation deaktiviert: Direkter Lookup
            if base_name in self.texture_coords:
                return base_name, self.texture_coords[base_name]
            return None, None
        
        # Rotation aktiviert: Wähle Variante basierend auf Welt-Koordinaten
        if world_x is not None and world_y is not None:
            # Deterministische Rotation basierend auf Position
            rotation_index = (world_x + world_y * 3) % 4
        else:
            # Fallback: Zufällige Rotation (nicht deterministisch)
            import random
            rotation_index = random.randint(0, 3)
        
        # Rotation-Varianten: 0° (original), 90°, 180°, 270°
        rotation_suffixes = ["", "_r90", "_r180", "_r270"]
        rotation_suffix = rotation_suffixes[rotation_index]
        
        # Versuche rotierte Variante
        rotated_name = f"{base_name}{rotation_suffix}"
        if rotated_name in self.texture_coords:
            return rotated_name, self.texture_coords[rotated_name]
        
        # Fallback: Original ohne Rotation
        if base_name in self.texture_coords:
            return base_name, self.texture_coords[base_name]
        
        return None, None
    
    def get_texture_coords(self, tile_id: str, world_x: int = None, world_y: int = None) -> Optional[tuple]:
        """
        Get UV coordinates for a tile_id in the texture atlas.
        Uses Organic Growth system if variance_system is configured.
        
        Args:
            tile_id: Tile ID (e.g., "core:grass" or "terrain:plains")
            world_x: World X coordinate for deterministic selection (optional)
            world_y: World Y coordinate for deterministic selection (optional)
            
        Returns:
            (u0, v0, u1, v1) tuple or None if not found
        """
        # First, try to map tile_id to texture_mapping key (e.g., "core:grass" -> "terrain:plains")
        mapping_key = tile_id
        if tile_id not in self.texture_mapping:
            # Try tile_id mapping (from biomes.json)
            if hasattr(self, 'tile_id_to_mapping_key') and tile_id in self.tile_id_to_mapping_key:
                mapping_key = self.tile_id_to_mapping_key[tile_id]
            else:
                # Try direct lookup for non-mapped tiles
                if tile_id in self.texture_coords:
                    return self.texture_coords[tile_id]
                
                # Try extracting from "core:grass" format -> "grass"
                if ':' in tile_id:
                    _, tile_name = tile_id.split(':', 1)
                    if tile_name in self.texture_coords:
                        return self.texture_coords[tile_name]
                
                # Not found
                return None
        
        mapping = self.texture_mapping[mapping_key]
        base_texture = mapping.get("base_texture", "")
        variance_system = mapping.get("variance_system", {})
        rotation_enabled = variance_system.get("rotation_enabled", True)
        growth_patterns = variance_system.get("growth_patterns", [])
        variance_mode = variance_system.get("mode", "")
        use_organic_growth = variance_mode == "organic_growth" and len(growth_patterns) > 0
        
        # Check if organic growth should be used
        if not use_organic_growth:
            # No organic growth configured, use base texture
            colorized_name = f"{mapping_key}:{base_texture}"
            coords = self._get_rotated_texture_coords(colorized_name, world_x, world_y, rotation_enabled)
            if coords is None:
                # Try fallback to non-colorized base texture
                if base_texture in self.texture_coords:
                    return self._get_rotated_texture_coords(base_texture, world_x, world_y, rotation_enabled)
            return coords
        
        # Organic growth requires world coordinates
        if world_x is None or world_y is None:
            # Fallback: base_texture mit Rotation (no world coords available)
            colorized_name = f"{mapping_key}:{base_texture}"
            coords = self._get_rotated_texture_coords(colorized_name, world_x, world_y, rotation_enabled)
            if coords is None:
                # Try fallback to non-colorized base texture
                if base_texture in self.texture_coords:
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
                colorized_name = f"{mapping_key}:{overlay_texture_name}"
                coords = self._get_rotated_texture_coords(colorized_name, world_x, world_y, rotation_enabled)
                if coords:
                    return coords
                else:
                    # Variant texture not found - try direct lookup without rotation
                    if colorized_name in self.texture_coords:
                        return self.texture_coords[colorized_name]
                    elif overlay_texture_name in self.texture_coords:
                        return self.texture_coords[overlay_texture_name]
        
        # Kein Pattern matched: Verwende base_texture mit Rotation
        colorized_name = f"{mapping_key}:{base_texture}"
        coords = self._get_rotated_texture_coords(colorized_name, world_x, world_y, rotation_enabled)
        if coords is None:
            # Fallback: Try non-colorized base texture
            if base_texture in self.texture_coords:
                return self._get_rotated_texture_coords(base_texture, world_x, world_y, rotation_enabled)
        return coords
    
    def get_texture_id_and_coords(self, tile_id: str, world_x: int = None, world_y: int = None) -> Tuple[Optional[str], Optional[tuple]]:
        """
        Get texture ID and UV coordinates for a tile_id in the texture atlas.
        Uses Organic Growth system if variance_system is configured.
        
        This method is similar to get_texture_coords(), but returns both the
        full atlas texture ID (e.g., "terrain:plains:plains_grass_1_r90") and
        the UV coordinates, which is needed for storing texture tags during
        world generation.
        
        Args:
            tile_id: Tile ID (e.g., "core:grass" or "terrain:plains")
            world_x: World X coordinate for deterministic selection (optional)
            world_y: World Y coordinate for deterministic selection (optional)
            
        Returns:
            Tuple of (texture_id, uv_coords) where:
            - texture_id: Full atlas texture ID (e.g., "terrain:plains:plains_grass_1_r90") or None
            - uv_coords: (u0, v0, u1, v1) tuple or None
        """
        # First, try to map tile_id to texture_mapping key (e.g., "core:grass" -> "terrain:plains")
        mapping_key = tile_id
        if tile_id not in self.texture_mapping:
            # Try tile_id mapping (from biomes.json)
            if hasattr(self, 'tile_id_to_mapping_key') and tile_id in self.tile_id_to_mapping_key:
                mapping_key = self.tile_id_to_mapping_key[tile_id]
            else:
                # Try direct lookup for non-mapped tiles
                if tile_id in self.texture_coords:
                    return tile_id, self.texture_coords[tile_id]
                
                # Try extracting from "core:grass" format -> "grass"
                if ':' in tile_id:
                    _, tile_name = tile_id.split(':', 1)
                    if tile_name in self.texture_coords:
                        return tile_name, self.texture_coords[tile_name]
                
                # Not found
                return None, None
        
        mapping = self.texture_mapping[mapping_key]
        base_texture = mapping.get("base_texture", "")
        variance_system = mapping.get("variance_system", {})
        rotation_enabled = variance_system.get("rotation_enabled", True)
        growth_patterns = variance_system.get("growth_patterns", [])
        variance_mode = variance_system.get("mode", "")
        use_organic_growth = variance_mode == "organic_growth" and len(growth_patterns) > 0
        
        # Check if organic growth should be used
        if not use_organic_growth:
            # No organic growth configured, use base texture
            colorized_name = f"{mapping_key}:{base_texture}"
            texture_id, coords = self._get_rotated_texture_id_and_coords(colorized_name, world_x, world_y, rotation_enabled)
            if coords is None:
                # Try fallback to non-colorized base texture
                if base_texture in self.texture_coords:
                    return self._get_rotated_texture_id_and_coords(base_texture, world_x, world_y, rotation_enabled)
            return texture_id, coords
        
        # Organic growth requires world coordinates
        if world_x is None or world_y is None:
            # Fallback: base_texture mit Rotation (no world coords available)
            colorized_name = f"{mapping_key}:{base_texture}"
            texture_id, coords = self._get_rotated_texture_id_and_coords(colorized_name, world_x, world_y, rotation_enabled)
            if coords is None:
                # Try fallback to non-colorized base texture
                if base_texture in self.texture_coords:
                    return self._get_rotated_texture_id_and_coords(base_texture, world_x, world_y, rotation_enabled)
            return texture_id, coords
        
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
                colorized_name = f"{mapping_key}:{overlay_texture_name}"
                texture_id, coords = self._get_rotated_texture_id_and_coords(colorized_name, world_x, world_y, rotation_enabled)
                if coords:
                    return texture_id, coords
                else:
                    # Variant texture not found - try direct lookup without rotation
                    if colorized_name in self.texture_coords:
                        return colorized_name, self.texture_coords[colorized_name]
                    elif overlay_texture_name in self.texture_coords:
                        return overlay_texture_name, self.texture_coords[overlay_texture_name]
        
        # Kein Pattern matched: Verwende base_texture mit Rotation
        colorized_name = f"{mapping_key}:{base_texture}"
        texture_id, coords = self._get_rotated_texture_id_and_coords(colorized_name, world_x, world_y, rotation_enabled)
        if coords is None:
            # Fallback: Try non-colorized base texture
            if base_texture in self.texture_coords:
                return self._get_rotated_texture_id_and_coords(base_texture, world_x, world_y, rotation_enabled)
        return texture_id, coords
    
    def get_decoration_texture_coords(self, sprite_name: str, mod_id: str = "core") -> Optional[tuple]:
        """
        Get UV coordinates for a decoration sprite in the texture atlas.
        Returns fallback texture coordinates if sprite not found.
        
        Args:
            sprite_name: Sprite name (e.g., "berry_bush_2" or "apple/autumn/apple_1" for nested paths)
            mod_id: Mod identifier (default: "core")
            
        Returns:
            (u0, v0, u1, v1) tuple or fallback texture coordinates if not found
        """
        # Try multiple formats to handle different naming conventions
        # Format 1: "decoration:mod_id/sprite_name" (standard format, supports nested paths)
        atlas_name = f"decoration:{mod_id}/{sprite_name}"
        
        if atlas_name in self.texture_coords:
            return self.texture_coords[atlas_name]
        
        # Format 2: Direct lookup in builder format "decoration/mod_id/sprite_name" (for debugging/migration)
        builder_name = f"decoration/{mod_id}/{sprite_name}"
        
        if builder_name in self.builder.uv_map:
            # Convert on-the-fly and cache
            uv_coords = self.builder.uv_map[builder_name]
            self.texture_coords[atlas_name] = tuple(uv_coords)
            return tuple(uv_coords)
        
        # Format 3: Try without mod_id (fallback for old format)
        simple_name = f"decoration:core/{sprite_name}" if mod_id != "core" else None
        if simple_name and simple_name in self.texture_coords:
            return self.texture_coords[simple_name]
        
        # Format 4: Try just sprite_name (for very old format)
        if sprite_name in self.texture_coords:
            return self.texture_coords[sprite_name]
        
        # Return fallback texture coordinates (pink 16x16)
        fallback_name = "decoration:fallback/fallback"
        if fallback_name in self.texture_coords:
            return self.texture_coords[fallback_name]
        
        return None
    
    def _validate_uv_map(self):
        """
        Validate UV map.
        Checks for missing textures and validates UV coordinates.
        """
        # Validate UV coordinates are in range [0.0, 1.0]
        for texture_id, uv_coords in self.texture_coords.items():
            if len(uv_coords) != 4:
                continue
            u0, v0, u1, v1 = uv_coords
            if not (0.0 <= u0 <= 1.0 and 0.0 <= v0 <= 1.0 and 0.0 <= u1 <= 1.0 and 0.0 <= v1 <= 1.0):
                pass  # Invalid UV, but no logging
    
    def reload_textures(self):
        """Rebuild Atlas (z.B. nach Mod-Installation)."""
        # Clear existing
        if self.texture_atlas:
            self.texture_atlas.release()
            self.texture_atlas = None
        
        self.texture_coords.clear()
        self.variant_coords.clear()
        
        # Rebuild
        self._build_atlas()
    
    def reload_decoration_textures_and_rebuild_atlas(self):
        """
        Reload decoration textures and rebuild atlas.
        This should be called after DecorationRegistry is loaded.
        """
        # OPTIMIZATION: Skip rebuild if atlas already exists and contains decoration textures
        # This prevents duplicate texture collection (atlas was already built in __init__)
        if self.texture_atlas is not None and len(self.texture_coords) > 0:
            # Check if decoration textures are already in atlas
            has_decorations = any(key.startswith("decoration:") for key in self.texture_coords.keys())
            if has_decorations:
                return
        
        # Delete texture cache file to force re-collection
        # This ensures DecorationRegistry changes are picked up
        cache_file = Path("data/texture_references.json")
        if cache_file.exists():
            try:
                cache_file.unlink()
            except Exception as e:
                pass
        
        # Release old atlas if it exists
        if self.texture_atlas:
            self.texture_atlas.release()
            self.texture_atlas = None
        
        # Clear texture_coords and variant_coords to force rebuild
        self.texture_coords.clear()
        self.variant_coords.clear()
        
        # Clear builder state to force rebuild
        if hasattr(self.builder, 'atlas_image'):
            self.builder.atlas_image = None
        if hasattr(self.builder, 'uv_map'):
            self.builder.uv_map.clear()
        if hasattr(self.builder, 'texture_images'):
            # Keep non-decoration textures, only clear decoration textures
            # Actually, better to clear all and rebuild - ensures consistency
            self.builder.texture_images.clear()
        
        # Rebuild atlas (will re-collect all textures including decorations)
        self._build_atlas()
    
    def has_texture(self, tile_id: str) -> bool:
        """
        Check if texture exists for tile_id.
        
        Args:
            tile_id: Tile identifier (e.g., "grass", "dirt", "terrain:plains", "core:grass")
            
        Returns:
            True if texture exists in atlas, False otherwise
        """
        # Try direct lookup
        if tile_id in self.texture_coords:
            return True
        
        # Try with "core:" prefix
        if ':' not in tile_id:
            core_tile_id = f"core:{tile_id}"
            if core_tile_id in self.texture_coords:
                return True
        
        # Try mapping lookup (tile_id -> texture_mapping key)
        mapping_key = tile_id
        if tile_id not in self.texture_mapping:
            # Try tile_id mapping (from biomes.json)
            if hasattr(self, 'tile_id_to_mapping_key') and tile_id in self.tile_id_to_mapping_key:
                mapping_key = self.tile_id_to_mapping_key[tile_id]
            else:
                # Try extracting from "core:grass" format -> "grass"
                if ':' in tile_id:
                    _, tile_name = tile_id.split(':', 1)
                    if tile_name in self.texture_coords:
                        return True
                # No mapping found
                return False
        
        # If we have a mapping_key (either direct or mapped), check if any colorized texture exists for it
        if mapping_key in self.texture_mapping:
            mapping = self.texture_mapping[mapping_key]
            base_texture = mapping.get("base_texture", "")
            if base_texture:
                # Check if colorized texture exists (format: "mapping_key:base_texture")
                colorized_name = f"{mapping_key}:{base_texture}"
                if colorized_name in self.texture_coords:
                    return True
                # Check rotated variants (r90, r180, r270)
                for rotation in ['_r90', '_r180', '_r270']:
                    if f"{colorized_name}{rotation}" in self.texture_coords:
                        return True
                # Check if base texture exists
                if base_texture in self.texture_coords:
                    return True
        
        # Try extracting from "terrain:plains" format
        if ':' in tile_id:
            _, tile_name = tile_id.split(':', 1)
            if tile_name in self.texture_coords:
                return True
        
        return False
    
    def bind_texture(self, unit: int = 0):
        """Bind texture atlas to texture unit."""
        if self.texture_atlas:
            self.texture_atlas.use(unit)
