"""
Baut Texture-Atlas aus gesammelten Texturen.
"""
import json
import math
from pathlib import Path
from typing import Dict, Tuple, Optional
from PIL import Image
import logging

logger = logging.getLogger(__name__)

# Fallback logging if logger not configured
def _log(level: str, message: str):
    """Log message with fallback to print."""
    if logger.handlers:
        getattr(logger, level)(message)
    else:
        print(f"[TextureAtlasBuilder] {message}")

class TextureAtlasBuilder:
    """Baut Texture-Atlas aus Texture-Referenzen."""
    
    FALLBACK_COLOR = (255, 0, 255, 255)  # Pink für fehlende Texturen
    
    def __init__(self, assets_path: str = "assets", tile_size: int = 16):
        self.assets_path = Path(assets_path)
        self.tile_size = tile_size
        self.texture_images = {}  # texture_id -> PIL.Image
        self.uv_map = {}  # texture_id -> (u0, v0, u1, v1)
        self.atlas_image = None
        self.atlas_size = 0
        self.failed_textures = set()
    
    def build_atlas(self, texture_references: Dict[str, list]) -> bool:
        """
        Baut Atlas aus Texture-Referenzen.
        
        Args:
            texture_references: Dictionary mit Kategorien und Texture-Listen
        
        Returns:
            True wenn erfolgreich
        """
        _log("info", "[TextureAtlasBuilder] Building texture atlas...")
        
        # 1. Load all textures (but preserve any textures already in texture_images, e.g., colorized textures)
        existing_textures = set(self.texture_images.keys())
        self._load_textures(texture_references)
        # Note: _load_textures() may overwrite existing textures, but colorized textures should be added after this
        new_textures = len(self.texture_images) - len(existing_textures)
        _log("info", f"After _load_textures: {len(self.texture_images)} textures total "
                f"(had {len(existing_textures)} before, added {new_textures} new)")
        
        if not self.texture_images:
            _log("warning", "[TextureAtlasBuilder] No textures loaded, cannot build atlas")
            return False
        
        # 2. Calculate atlas size (AFTER loading all textures, including colorized ones)
        texture_count = len(self.texture_images)
        # Calculate grid size needed
        max_texture_size = max(
            max(img.size[0], img.size[1]) for img in self.texture_images.values()
        )
        
        # Estimate grid size (assume square textures for simplicity)
        grid_size = math.ceil(math.sqrt(texture_count))
        # Atlas size should be power-of-2 and large enough for all textures
        estimated_size = grid_size * max_texture_size
        # Round up to next power of 2
        self.atlas_size = 2 ** math.ceil(math.log2(max(estimated_size, 256)))
        
        _log("info", f"  Atlas size: {self.atlas_size}x{self.atlas_size} "
                   f"(grid: {grid_size}x{grid_size}, {texture_count} textures, max size: {max_texture_size})")
        
        # 3. Create atlas image
        self.atlas_image = Image.new('RGBA', (self.atlas_size, self.atlas_size), (0, 0, 0, 0))
        
        # 4. Place textures in atlas
        self._pack_textures()
        
        # 5. Validate UV coordinates
        self._validate_uv_coordinates()
        
        _log("info", f"[TextureAtlasBuilder] ✓ Atlas built: {len(self.uv_map)} textures, "
                   f"{len(self.failed_textures)} failed")
        
        return True
    
    def _load_textures(self, texture_references: Dict[str, list]):
        """Lädt alle referenzierten Texturen."""
        total_textures = sum(len(textures) for textures in texture_references.values())
        _log("info", f"[TextureAtlasBuilder] Loading {total_textures} textures...")
        
        loaded_count = 0
        
        for category, texture_list in texture_references.items():
            for texture_ref in texture_list:
                # Parse texture reference: "category/mod_id/sprite_name"
                parts = texture_ref.split('/')
                if len(parts) < 3:
                    _log("warning", f"Invalid texture reference format: {texture_ref}")
                    continue
                
                category_part = parts[0]
                mod_id = parts[1]
                sprite_name = '/'.join(parts[2:])  # Handle nested paths like "apple/spring/apple_1"
                
                # Remove .png extension if already present (e.g., "iron_ore.png" -> "iron_ore")
                if sprite_name.endswith('.png'):
                    sprite_name = sprite_name[:-4]
                
                # Determine asset path based on category
                if category_part == "decoration":
                    # Try multiple paths for decorations
                    sprite_paths = [
                        self.assets_path / "decorations" / mod_id / f"{sprite_name}.png",
                        self.assets_path / "decorations" / f"{sprite_name}.png",
                    ]
                elif category_part == "item":
                    # Try multiple paths for items
                    sprite_paths = [
                        self.assets_path / "items" / mod_id / f"{sprite_name}.png",
                        self.assets_path / "items" / f"{sprite_name}.png",
                        self.assets_path / "food" / mod_id / f"{sprite_name}.png",
                        self.assets_path / "food" / f"{sprite_name}.png",
                    ]
                elif category_part == "tool":
                    sprite_paths = [
                        self.assets_path / "items" / mod_id / f"{sprite_name}.png",
                        self.assets_path / "items" / f"{sprite_name}.png",
                    ]
                elif category_part == "tile":
                    # Try multiple path variations for tiles
                    # Note: Textures are in assets/tile/core/ (singular "tile", not "tiles")
                    sprite_paths = [
                        # Correct path: assets/tile/core/{sprite_name}.png (singular "tile")
                        self.assets_path / "tile" / "core" / f"{sprite_name}.png",
                        self.assets_path / "tile" / "core" / sprite_name,
                        # Absolute path fallback
                        Path("assets/tile/core") / f"{sprite_name}.png",
                        Path("assets/tile/core") / sprite_name,
                        # Also try plural "tiles" for backwards compatibility
                        self.assets_path / "tiles" / "core" / f"{sprite_name}.png",
                        self.assets_path / "tiles" / "core" / sprite_name,
                        Path("assets/tiles/core") / f"{sprite_name}.png",
                        Path("assets/tiles/core") / sprite_name,
                    ]
                else:
                    _log("warning", f"Unknown texture category: {category_part}")
                    continue
                
                # Try to load texture
                img = None
                tried_paths = []
                for path in sprite_paths:
                    tried_paths.append(str(path))
                    if path.exists():
                        try:
                            img = Image.open(path).convert("RGBA")
                            # Don't resize decorations (variable sizes), but resize tiles to tile_size
                            if category_part == "tile" and (img.size[0] != self.tile_size or img.size[1] != self.tile_size):
                                img = img.resize((self.tile_size, self.tile_size), Image.Resampling.LANCZOS)
                            _log("info", f"Loaded texture: {texture_ref} from {path}")
                            break
                        except Exception as e:
                            _log("debug", f"Error loading texture {path}: {e}")
                            continue
                
                if img:
                    # Store with full reference as key (only if not already exists, to preserve colorized textures)
                    if texture_ref not in self.texture_images:
                        self.texture_images[texture_ref] = img
                        loaded_count += 1
                    else:
                        # Texture already exists (probably colorized), skip
                        _log("debug", f"Skipping {texture_ref} - already in texture_images (colorized texture?)")
                else:
                    # Create fallback texture
                    fallback_size = self.tile_size if category_part == "tile" else 32
                    fallback_img = Image.new('RGBA', (fallback_size, fallback_size), self.FALLBACK_COLOR)
                    self.texture_images[texture_ref] = fallback_img
                    self.failed_textures.add(texture_ref)
                    _log("warning", f"Created fallback texture for: {texture_ref} (tried paths: {', '.join(tried_paths[:3])}...)")
        
        _log("info", f"[TextureAtlasBuilder] Loaded {loaded_count} textures, "
                   f"{len(self.failed_textures)} fallbacks created")
    
    def _pack_textures(self):
        """Packt Texturen in Grid-Layout."""
        if not self.texture_images:
            return
        
        # Sort textures by size (largest first) for better packing
        sorted_textures = sorted(
            self.texture_images.items(),
            key=lambda x: max(x[1].size[0], x[1].size[1]),
            reverse=True
        )
        
        # Calculate grid layout
        texture_count = len(sorted_textures)
        grid_size = math.ceil(math.sqrt(texture_count))
        
        # Calculate cell size (largest texture size + padding to prevent edge bleeding)
        padding = 1  # 1 pixel padding between textures
        max_size = max(max(img.size[0], img.size[1]) for img in self.texture_images.values())
        cell_size = max_size + padding
        
        # Place textures in grid (start with padding from edge)
        x = padding
        y = padding
        current_row_height = 0
        
        for texture_id, img in sorted_textures:
            img_width, img_height = img.size
            
            # Check if texture fits in current row
            if x + cell_size > self.atlas_size - padding:
                # Move to next row
                y += current_row_height + padding
                x = padding
                current_row_height = 0
            
            # Check if we need more space
            if y + cell_size > self.atlas_size - padding:
                _log("error", f"[TextureAtlasBuilder] Atlas too small! Need at least {y + cell_size + padding}x{self.atlas_size}")
                # Resize atlas (shouldn't happen with proper size calculation)
                new_size = 2 ** math.ceil(math.log2(y + cell_size + padding))
                _log("warning", f"[TextureAtlasBuilder] Resizing atlas to {new_size}x{new_size}")
                old_atlas = self.atlas_image
                self.atlas_size = new_size
                self.atlas_image = Image.new('RGBA', (self.atlas_size, self.atlas_size), (0, 0, 0, 0))
                if old_atlas:
                    self.atlas_image.paste(old_atlas, (0, 0))
            
            # Paste texture into atlas (centered in cell, with padding)
            paste_x = x + (cell_size - img_width - padding) // 2
            paste_y = y + (cell_size - img_height - padding) // 2
            self.atlas_image.paste(img, (paste_x, paste_y), img if img.mode == 'RGBA' else None)
            
            # Calculate UV coordinates with half-pixel offset to prevent edge bleeding
            # Add 0.5 pixel offset to stay away from texture edges
            half_pixel = 0.5 / self.atlas_size
            u0 = (paste_x + half_pixel) / self.atlas_size
            v0 = (paste_y + half_pixel) / self.atlas_size
            u1 = (paste_x + img_width - half_pixel) / self.atlas_size
            v1 = (paste_y + img_height - half_pixel) / self.atlas_size
            
            self.uv_map[texture_id] = (u0, v0, u1, v1)
            
            # Update position (with padding)
            x += cell_size
            current_row_height = max(current_row_height, cell_size)
        
        _log("info", f"[TextureAtlasBuilder] Packed {len(self.uv_map)} textures into atlas")
    
    def _validate_uv_coordinates(self):
        """Validiert UV-Koordinaten."""
        invalid = []
        for texture_id, (u0, v0, u1, v1) in self.uv_map.items():
            if not (0.0 <= u0 <= 1.0 and 0.0 <= v0 <= 1.0 and 0.0 <= u1 <= 1.0 and 0.0 <= v1 <= 1.0):
                invalid.append(texture_id)
            if u0 >= u1 or v0 >= v1:
                invalid.append(texture_id)
        
        if invalid:
            _log("error", f"[TextureAtlasBuilder] Invalid UV coordinates: {invalid[:5]}...")
        else:
            _log("debug", "[TextureAtlasBuilder] All UV coordinates valid")
        
        # Log statistics
        _log("info", f"[TextureAtlasBuilder] Atlas validation: {len(self.uv_map)} textures, "
                   f"{len(invalid)} invalid, {len(self.failed_textures)} failed loads")
    
    def save_atlas(self, output_path: str = "data/atlas.png", uv_map_path: str = "data/atlas_uv_map.json"):
        """Optional - Exportiert Atlas als PNG + UV-Map als JSON."""
        if not self.atlas_image:
            _log("warning", "[TextureAtlasBuilder] No atlas to save")
            return
        
        # Save atlas image
        atlas_path = Path(output_path)
        atlas_path.parent.mkdir(parents=True, exist_ok=True)
        self.atlas_image.save(atlas_path)
        _log("info", f"[TextureAtlasBuilder] Saved atlas to: {output_path}")
        
        # Save UV map
        uv_path = Path(uv_map_path)
        uv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(uv_path, 'w', encoding='utf-8') as f:
            json.dump(self.uv_map, f, indent=2)
        _log("info", f"[TextureAtlasBuilder] Saved UV map to: {uv_map_path}")
