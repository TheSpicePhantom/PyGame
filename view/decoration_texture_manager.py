"""
Decoration Texture Manager: Loads and manages textures for decorations.
Supports mod folders (e.g., assets/decorations/{mod_id}/sprite.png)
"""
import os
from pathlib import Path
from typing import Dict, Optional
import moderngl
from PIL import Image
from core import settings


class DecorationTextureManager:
    """
    Manages textures for decorations.
    
    Loads textures from assets/decorations/{mod_id}/ based on sprite names:
    - "berry_bush_2" with mod_id="core" -> assets/decorations/core/berry_bush_2.png
    - "oak_tree" with mod_id="mod_name" -> assets/decorations/mod_name/oak_tree.png
    """
    
    def __init__(self, ctx: moderngl.Context, base_path: str = "assets/decorations", diagnostics=None):
        """
        Initialize Decoration Texture Manager.
        
        Args:
            ctx: ModernGL context
            base_path: Base path to decoration textures directory
            diagnostics: Optional DiagnosticsService instance for logging
        """
        self.ctx = ctx
        self.base_path = Path(base_path)
        self.diagnostics = diagnostics
        self.textures: Dict[str, moderngl.Texture] = {}  # sprite_name -> ModernGL Texture
        self.texture_images: Dict[str, Image.Image] = {}  # sprite_name -> PIL Image
        self.missing_texture: Optional[moderngl.Texture] = None  # Missing texture (violet-black checkerboard)
        self._warned_missing: set = set()  # Track already warned missing textures to avoid spam
        self._create_missing_texture()
        self._log("info", f"Initialized DecorationTextureManager with base path: {base_path}")
    
    def _log(self, level: str, message: str):
        """Log message with diagnostics or print fallback."""
        if self.diagnostics:
            getattr(self.diagnostics, level)("DecorationTextureManager", message)
        else:
            print(f"[DecorationTextureManager] {message}")
    
    def _create_missing_texture(self):
        """Create a 32x32 violet-black checkerboard texture (Minecraft-style missing texture)."""
        size = 32
        tile_size = 8  # 8x8 pixels per checkerboard tile (32/4 = 8)
        
        # Create image
        img = Image.new('RGBA', (size, size), (0, 0, 0, 255))
        pixels = img.load()
        
        # Violet color (RGB: 128, 0, 128)
        violet = (128, 0, 128, 255)
        black = (0, 0, 0, 255)
        
        # Create checkerboard pattern
        for y in range(size):
            for x in range(size):
                # Determine which tile we're in
                tile_x = x // tile_size
                tile_y = y // tile_size
                
                # Checkerboard: alternate colors based on tile position
                if (tile_x + tile_y) % 2 == 0:
                    pixels[x, y] = violet
                else:
                    pixels[x, y] = black
        
        # Create ModernGL texture
        img_data = img.tobytes()
        self.missing_texture = self.ctx.texture((size, size), 4, img_data)
        self.missing_texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self.missing_texture.build_mipmaps()
        
        self._log("debug", "Created missing texture (32x32 violet-black checkerboard)")
    
    def load_sprite(self, sprite_name: str, mod_id: str = "core") -> Optional[moderngl.Texture]:
        """
        Load a decoration sprite texture.
        
        Args:
            sprite_name: Sprite name (e.g., "berry_bush_2")
            mod_id: Mod identifier (default: "core")
            
        Returns:
            ModernGL Texture or None if not found
        """
        # Check if already loaded
        cache_key = f"{mod_id}/{sprite_name}"
        if cache_key in self.textures:
            return self.textures[cache_key]
        
        # Try to load from file
        # Priority order:
        # 1. assets/decorations/{mod_id}/{sprite_name}.png (flat structure)
        # 2. assets/decorations/{mod_id}/{season}/{sprite_name}.png (season subfolder, if sprite_name contains season prefix)
        # 3. assets/decorations/{sprite_name}.png (direct in base_path)
        # 4. assets/decorations/{sprite_name}/{sprite_name}.png (fallback)
        
        sprite_path = None
        search_paths = [
            self.base_path / mod_id / f"{sprite_name}.png",  # mod_id folder (flat)
            self.base_path / f"{sprite_name}.png",  # Direct in base_path
            Path("assets/decorations") / f"{sprite_name}.png",  # Absolute fallback
        ]
        
        # Check if sprite_name contains season prefix (e.g., "spring_maple_1")
        # If so, also try season subfolder structure
        season_prefixes = ["spring", "summer", "autumn", "winter"]
        for season in season_prefixes:
            if sprite_name.startswith(f"{season}_"):
                # Try season subfolder: assets/decorations/{mod_id}/{season}/{rest_of_name}.png
                rest_of_name = sprite_name[len(season) + 1:]  # Remove "spring_" prefix
                season_path = self.base_path / mod_id / season / f"{rest_of_name}.png"
                search_paths.insert(1, season_path)  # Insert after flat structure, before direct base_path
                break
        
        for path in search_paths:
            if path.exists():
                sprite_path = path
                break
        
        if not sprite_path:
            # Only warn once per missing texture
            if cache_key not in self._warned_missing:
                self._log("warning", f"Sprite not found: {sprite_name} (mod_id: {mod_id}, searched: {[str(p) for p in search_paths]}) - using missing texture")
                self._warned_missing.add(cache_key)
            # Return missing texture instead of None
            return self.missing_texture
        
        # Load image
        try:
            img = Image.open(sprite_path).convert("RGBA")
            
            # Don't resize - decorations can have custom sizes
            # The rendering system will handle scaling
            
            # Store PIL image
            self.texture_images[cache_key] = img
            
            # Create ModernGL texture
            img_data = img.tobytes()
            texture = self.ctx.texture(img.size, 4, img_data)
            texture.filter = (moderngl.NEAREST, moderngl.NEAREST)  # Pixel-perfect
            texture.build_mipmaps()
            
            # Store texture
            self.textures[cache_key] = texture
            
            self._log("debug", f"Loaded sprite: {cache_key} ({img.size[0]}x{img.size[1]})")
            return texture
            
        except Exception as e:
            self._log("error", f"Error loading sprite {sprite_name}: {e}")
            return None
    
    def get_texture(self, sprite_name: str, mod_id: str = "core") -> Optional[moderngl.Texture]:
        """
        Get texture for sprite (loads if not already loaded).
        
        Args:
            sprite_name: Sprite name
            mod_id: Mod identifier (default: "core")
            
        Returns:
            ModernGL Texture or missing texture if not found
        """
        texture = self.load_sprite(sprite_name, mod_id)
        # load_sprite already returns missing_texture if not found, but ensure we never return None
        return texture if texture is not None else self.missing_texture
    
    def get_texture_size(self, sprite_name: str, mod_id: str = "core") -> Optional[tuple]:
        """
        Get texture size in pixels.
        
        Args:
            sprite_name: Sprite name
            mod_id: Mod identifier (default: "core")
            
        Returns:
            (width, height) tuple or None if not found
        """
        cache_key = f"{mod_id}/{sprite_name}"
        if cache_key in self.texture_images:
            img = self.texture_images[cache_key]
            return img.size
        return None
    
    def preload_decorations(self, decoration_configs: list):
        """
        Preload all sprites for a list of decoration configs.
        
        Args:
            decoration_configs: List of decoration config dictionaries
        """
        loaded_count = 0
        for config in decoration_configs:
            decoration_id = config.get('decoration_id')
            if not decoration_id:
                continue
            
            # Get mod_id from config (default: "core")
            mod_id = config.get('mod_id', 'core')
            
            # Load all sprites from sprites dict
            sprites = config.get('sprites', {})
            for sprite_key, sprite_name in sprites.items():
                if self.load_sprite(sprite_name, mod_id):
                    loaded_count += 1
            
            # Load shadow sprite if enabled
            rendering = config.get('rendering', {})
            shadow = rendering.get('shadow', {})
            if shadow.get('enabled', False):
                shadow_sprite = shadow.get('sprite')
                if shadow_sprite:
                    self.load_sprite(shadow_sprite, mod_id)
        
        self._log("info", f"Preloaded {loaded_count} decoration sprites")
    
    def release_all(self):
        """Release all loaded textures (except missing texture)."""
        for texture in self.textures.values():
            texture.release()
        self.textures.clear()
        self.texture_images.clear()
        # Don't release missing_texture - it's a fallback that should always be available
        self._log("info", "Released all decoration textures")

