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
    
    Lädt Texturen aus assets/core/tiles/ basierend auf tile_id:
    - core:rainforest -> assets/core/tiles/rainforest.png
    - terrain:plains -> assets/core/tiles/grass.png (oder plains.png falls vorhanden)
    """
    
    def __init__(self, ctx: moderngl.Context, base_path: str = "assets/core/tiles", mapping_file: str = "data/textures/texture_mapping.json"):
        """
        Initialize Texture Manager with dynamic texture atlas and variant support
        
        Args:
            ctx: ModernGL context
            base_path: Base path to tile textures directory (fallback)
            mapping_file: Path to texture mapping JSON file
        """
        self.ctx = ctx
        self.base_path = Path(base_path)
        self.mapping_file = Path(mapping_file)
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
        
        # Load texture mapping configuration
        self.texture_mapping: Dict[str, dict] = {}
        self._load_texture_mapping()
        
        # Load all textures (including variants and overlays)
        self._load_all_textures()
        self._build_texture_atlas()
    
    def _load_texture_mapping(self):
        """Load texture mapping configuration from JSON file"""
        if not self.mapping_file.exists():
            print(f"Warning: Texture mapping file {self.mapping_file} does not exist, using defaults")
            return
        
        try:
            with open(self.mapping_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.texture_mapping = data.get("texture_mappings", {})
                print(f"Loaded texture mapping for {len(self.texture_mapping)} biomes")
        except Exception as e:
            print(f"Error loading texture mapping: {e}")
    
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
            print(f"Error loading texture {texture_path}: {e}")
            return None
    
    def _load_all_textures(self):
        """Load all available textures including variants from mapping file"""
        loaded_textures = set()  # Track loaded texture names to avoid duplicates
        
        # Load textures from mapping file
        for tile_id, mapping in self.texture_mapping.items():
            base_path_str = mapping.get("base_path", "assets/core/tiles")
            base_path_obj = Path(base_path_str)
            variants = mapping.get("variants", [])
            
            if not variants:
                # Fallback to base_texture if no variants
                base_texture = mapping.get("base_texture", "")
                if base_texture:
                    variants = [base_texture]
            
            # Load each variant
            for variant_name in variants:
                if variant_name in loaded_textures:
                    continue  # Already loaded
                
                # Try different possible paths
                texture_paths = [
                    base_path_obj / f"{variant_name}.png",
                    base_path_obj / f"{variant_name}",
                    Path("assets/tiles") / f"{variant_name}.png",
                    Path("assets/core/tiles") / f"{variant_name}.png",
                ]
                
                img = None
                for texture_path in texture_paths:
                    img = self._load_texture_from_path(texture_path)
                    if img:
                        break
                
                if img:
                    self.texture_images[variant_name] = img
                    loaded_textures.add(variant_name)
                    print(f"Loaded texture variant: {variant_name} from {base_path_str}")
            
            # Load overlay textures
            overlays = mapping.get("overlays", [])
            for overlay_config in overlays:
                overlay_texture = overlay_config.get("texture")
                if overlay_texture and overlay_texture not in loaded_textures:
                    # Try different possible paths for overlay
                    overlay_paths = [
                        base_path_obj / f"{overlay_texture}.png",
                        base_path_obj / f"{overlay_texture}",
                        Path("assets/tiles") / f"{overlay_texture}.png",
                        Path("assets/core/tiles") / f"{overlay_texture}.png",
                    ]
                    
                    img = None
                    for overlay_path in overlay_paths:
                        img = self._load_texture_from_path(overlay_path)
                        if img:
                            break
                    
                    if img:
                        self.texture_images[overlay_texture] = img
                        loaded_textures.add(overlay_texture)
                        print(f"Loaded overlay texture: {overlay_texture} from {base_path_str}")
        
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
                        print(f"Loaded texture: {tile_name} ({img.size[0]}x{img.size[1]})")
        
        # Also check assets/tiles for additional textures
        tiles_path = Path("assets/tiles")
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
                        print(f"Loaded texture: {tile_name} from assets/tiles")
    
    def _build_texture_atlas(self):
        """Build a dynamic texture atlas from all loaded textures"""
        if not self.texture_images:
            print("No textures to build atlas from")
            return
        
        # Use unique textures only (without prefixes)
        unique_textures = {}
        for name, img in self.texture_images.items():
            if ':' not in name:  # Only base names
                unique_textures[name] = img
        
        num_textures = len(unique_textures)
        if num_textures == 0:
            print("No unique textures found for atlas")
            return
        
        # Calculate grid dimensions (square grid, rounded up)
        import math
        grid_size = math.ceil(math.sqrt(num_textures))
        atlas_width = grid_size * self.tile_size
        atlas_height = grid_size * self.tile_size
        
        # Round up to nearest power of 2 for better GPU performance
        def next_power_of_2(n):
            return 2 ** math.ceil(math.log2(n))
        
        atlas_width = next_power_of_2(atlas_width)
        atlas_height = next_power_of_2(atlas_height)
        
        self.atlas_size = max(atlas_width, atlas_height)
        
        # Create atlas image
        atlas_img = Image.new("RGBA", (self.atlas_size, self.atlas_size), (0, 0, 0, 0))
        
        # Pack textures into atlas and calculate UV coordinates
        texture_list = list(unique_textures.items())
        for idx, (tile_name, img) in enumerate(texture_list):
            # Calculate grid position
            grid_x = idx % grid_size
            grid_y = idx // grid_size
            
            # Calculate pixel position in atlas
            atlas_x = grid_x * self.tile_size
            atlas_y = grid_y * self.tile_size
            
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
        
        # Build variant mappings: for each tile_id, store list of variant UV coordinates
        for tile_id, mapping in self.texture_mapping.items():
            variants = mapping.get("variants", [])
            if not variants:
                base_texture = mapping.get("base_texture", "")
                if base_texture:
                    variants = [base_texture]
            
            variant_coords_list = []
            for variant_name in variants:
                if variant_name in self.texture_coords:
                    variant_coords_list.append(self.texture_coords[variant_name])
            
            if variant_coords_list:
                self.variant_coords[tile_id] = variant_coords_list
        
        # Create ModernGL texture from atlas
        atlas_data = np.array(atlas_img, dtype=np.uint8)
        self.texture_atlas = self.ctx.texture((self.atlas_size, self.atlas_size), 4, atlas_data.tobytes())
        # Use NEAREST filtering for sharp pixel-perfect transitions between tiles
        # No mipmaps to avoid blurry transitions
        self.texture_atlas.filter = (moderngl.NEAREST, moderngl.NEAREST)
        
        print(f"Built texture atlas: {self.atlas_size}x{self.atlas_size} with {num_textures} textures")
        print(f"Variant mappings: {len(self.variant_coords)} biomes with variants")
    
    def get_texture_coords(self, tile_id: str, world_x: int = None, world_y: int = None) -> Optional[tuple]:
        """
        Get UV coordinates for a tile_id in the texture atlas, with variant support.
        If multiple variants exist, selects one deterministically based on world position.
        
        Args:
            tile_id: Tile ID (e.g., "core:rainforest", "terrain:plains")
            world_x: World X coordinate for deterministic variant selection (optional)
            world_y: World Y coordinate for deterministic variant selection (optional)
        
        Returns:
            (u0, v0, u1, v1) tuple or None if not found
        """
        # Check if tile_id has variants
        if tile_id in self.variant_coords:
            variants = self.variant_coords[tile_id]
            if len(variants) > 1 and world_x is not None and world_y is not None:
                # Check if there's a default variant specified
                mapping = self.texture_mapping.get(tile_id, {})
                default_variant_name = mapping.get("default_variant")
                
                if default_variant_name:
                    # Find the default variant in the variants list
                    variant_names = mapping.get("variants", [])
                    try:
                        default_index = variant_names.index(default_variant_name)
                        if default_index < len(variants):
                            # Check if overlays are configured - if so, use overlay logic to replace base texture
                            overlays = mapping.get("overlays", [])
                            if overlays:
                                # Use overlay system to determine if a variant should replace the base texture
                                # This allows variants 2-6 to replace plains_grass_1 instead of overlaying it
                                for overlay_config in overlays:
                                    overlay_texture_name = overlay_config.get("texture")
                                    if overlay_texture_name not in variant_names:
                                        continue
                                    
                                    chance = overlay_config.get("chance", 0.1)
                                    noise_scale = overlay_config.get("noise_scale", 0.1)
                                    noise_threshold = overlay_config.get("noise_threshold", 0.5)
                                    
                                    # Calculate noise value for this position
                                    overlay_seed_offset = hash(overlay_texture_name) % 10000
                                    noise_x = world_x * noise_scale + overlay_seed_offset
                                    noise_y = world_y * noise_scale + overlay_seed_offset
                                    
                                    # Get noise value (-1 to 1)
                                    noise_value = self.overlay_noise.noise2(noise_x, noise_y)
                                    
                                    # Normalize to 0-1
                                    normalized_noise = (noise_value + 1.0) / 2.0
                                    
                                    # Check if noise exceeds threshold
                                    if normalized_noise < noise_threshold:
                                        continue
                                    
                                    # Apply chance factor
                                    if normalized_noise < (noise_threshold + (1.0 - noise_threshold) * chance):
                                        continue
                                    
                                    # This variant should replace the base texture
                                    variant_index = variant_names.index(overlay_texture_name)
                                    if variant_index < len(variants):
                                        return variants[variant_index]
                                
                                # No overlay matched, use default variant
                                return variants[default_index]
                            else:
                                # No overlays configured, use default variant with small variation chance
                                hash_input = f"{tile_id}_{world_x}_{world_y}"
                                hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
                                if (hash_value % 100) < 10:  # 10% chance for variation
                                    variant_index = hash_value % len(variants)
                                else:
                                    variant_index = default_index
                                return variants[variant_index]
                    except ValueError:
                        pass  # Default variant not found, fall through to normal selection
                
                # Select variant deterministically based on world position
                # Use hash of position to ensure same tile always gets same variant
                hash_input = f"{tile_id}_{world_x}_{world_y}"
                hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
                variant_index = hash_value % len(variants)
                return variants[variant_index]
            elif variants:
                # Single variant or no position provided, use first variant
                return variants[0]
        
        # Try direct lookup
        if tile_id in self.texture_coords:
            return self.texture_coords[tile_id]
        
        # Try to extract name and map it
        parts = tile_id.split(":")
        if len(parts) == 2:
            name = parts[1]
            
            # Try direct name match
            if name in self.texture_coords:
                return self.texture_coords[name]
            
            # Try common mappings (fallback for unmapped biomes)
            name_mappings = {
                "deepwater": "deep",
                "shallowwater": "shallow",
                "plains": "grass",
                "desert": "sand",
                "beach": "sand",
                "mountains": "stone",
            }
            
            mapped_name = name_mappings.get(name.lower(), name.lower())
            if mapped_name in self.texture_coords:
                return self.texture_coords[mapped_name]
        
        return None
    
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
            if texture_name in self.texture_coords:
                return self.texture_coords[texture_name]
        
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
        return self.get_texture_coords(tile_id) is not None
    
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

