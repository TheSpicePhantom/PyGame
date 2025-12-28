"""
Item Texture Manager: Loads and manages textures for items.
"""
import os
from pathlib import Path
from typing import Dict, Optional
import moderngl
from PIL import Image
from PIL.Image import FLIP_TOP_BOTTOM
from core import settings


class ItemTextureManager:
    """
    Manages textures for items.
    Supports mod folders (e.g., assets/items/{mod_id}/sprite.png)
    
    Loads textures from assets/items/{mod_id}/ based on sprite names:
    - "wood" with mod_id="core" -> assets/items/core/wood.png
    - "berries" with mod_id="core" -> assets/items/core/berries.png
    """
    
    def __init__(self, ctx: moderngl.Context, base_path: str = "assets/items", diagnostics=None):
        """
        Initialize Item Texture Manager.
        
        Args:
            ctx: ModernGL context
            base_path: Base path to item textures directory
            diagnostics: Optional DiagnosticsService instance for logging
        """
        self.ctx = ctx
        self.base_path = Path(base_path)
        self.diagnostics = diagnostics
        self.textures: Dict[str, moderngl.Texture] = {}  # item_id -> ModernGL Texture
        self.texture_images: Dict[str, Image.Image] = {}  # item_id -> PIL Image
        self.missing_texture: Optional[moderngl.Texture] = None  # Missing texture (violet-black checkerboard)
        self._warned_missing: set = set()  # Track already warned missing textures to avoid spam
        self._create_missing_texture()
        self._log("info", f"Initialized ItemTextureManager with base path: {base_path}")
    
    def _log(self, level: str, message: str):
        """Log message with diagnostics or print fallback."""
        if self.diagnostics:
            getattr(self.diagnostics, level)("ItemTextureManager", message)
        else:
            print(f"[ItemTextureManager] {message}")
    
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
    
    def load_item_sprite(self, item_id: str) -> Optional[moderngl.Texture]:
        """
        Load an item sprite texture.
        
        Args:
            item_id: Item identifier (e.g., "wood")
            
        Returns:
            ModernGL Texture or None if not found
        """
        # Check if already loaded
        if item_id in self.textures:
            return self.textures[item_id]
        
        # Get sprite path from ItemRegistry (includes mod_id)
        from world.item_registry import ItemRegistry
        sprite_path_str = ItemRegistry.get_sprite_path(item_id)
        
        if not sprite_path_str:
            # Only warn once per missing texture
            if item_id not in self._warned_missing:
                self._log("warning", f"Item sprite path not found for item_id: {item_id} - using missing texture")
                self._warned_missing.add(item_id)
            return self.missing_texture
        
        sprite_path = Path(sprite_path_str)
        
        # Ensure .png extension is added if not present
        if not sprite_path.suffix:
            sprite_path = sprite_path.with_suffix('.png')
        
        # Fallback: try to construct path from item config if path doesn't exist
        if not sprite_path.exists():
            item_config = ItemRegistry.get(item_id)
            if item_config:
                sprite_name = item_config.get('sprite')
                mod_id = item_config.get('mod_id', 'core')
                
                # Remove .png from sprite_name if present (we'll add it)
                if sprite_name.endswith('.png'):
                    sprite_name = sprite_name[:-4]
                
                # Try alternative paths with .png extension
                search_paths = [
                    self.base_path / mod_id / f"{sprite_name}.png",  # assets/items/{mod_id}/{sprite}.png
                    self.base_path / mod_id / sprite_name,  # assets/items/{mod_id}/{sprite} (without extension)
                    self.base_path / f"{sprite_name}.png",  # assets/items/{sprite}.png (fallback)
                    Path("assets/items") / mod_id / f"{sprite_name}.png",  # Absolute path
                ]
                for path in search_paths:
                    if path.exists():
                        sprite_path = path
                        break
        
        if not sprite_path.exists():
            # Only warn once per missing texture
            if item_id not in self._warned_missing:
                self._log("warning", f"Sprite file not found: {sprite_path} for item {item_id} - using missing texture")
                self._warned_missing.add(item_id)
            return self.missing_texture
        
        # Load image
        try:
            img = Image.open(sprite_path).convert("RGBA")
            
            # Store PIL image
            self.texture_images[item_id] = img
            
            # Create ModernGL texture
            img_data = img.tobytes()
            texture = self.ctx.texture(img.size, 4, img_data)
            texture.filter = (moderngl.NEAREST, moderngl.NEAREST)  # Pixel-perfect
            texture.build_mipmaps()
            
            # Store texture
            self.textures[item_id] = texture
            
            self._log("debug", f"Loaded item sprite: {item_id} ({img.size[0]}x{img.size[1]})")
            return texture
            
        except Exception as e:
            self._log("error", f"Error loading sprite for item {item_id}: {e}")
            return self.missing_texture
    
    def get_texture(self, item_id: str) -> Optional[moderngl.Texture]:
        """
        Get texture for item (loads if not already loaded).
        
        Args:
            item_id: Item identifier
            
        Returns:
            ModernGL Texture or missing texture if not found
        """
        texture = self.load_item_sprite(item_id)
        # load_item_sprite already returns missing_texture if not found, but ensure we never return None
        return texture if texture is not None else self.missing_texture
    
    def get_pyglet_image(self, item_id: str):
        """
        Get pyglet Image for item (for UI rendering).
        Uses NEAREST filtering for pixel-perfect scaling (pixel art).
        
        Args:
            item_id: Item identifier
            
        Returns:
            pyglet.image.AbstractImage or None if not found
        """
        import pyglet
        import pyglet.gl as gl
        
        # Check if already loaded
        if item_id in self.texture_images:
            img = self.texture_images[item_id]
            # Convert PIL Image to pyglet ImageData
            # PIL images are top-to-bottom, pyglet expects bottom-to-top
            # So we need to flip vertically
            # Flip image vertically (PIL top-to-bottom -> pyglet bottom-to-top)
            flipped_img = img.transpose(FLIP_TOP_BOTTOM)
            # PIL image is RGBA, convert to bytes
            img_data = flipped_img.tobytes()
            image_data = pyglet.image.ImageData(
                img.width, img.height,
                'RGBA', img_data,
                pitch=img.width * 4
            )
            # Get texture and set NEAREST filtering for pixel-perfect scaling
            texture = image_data.get_texture()
            if texture:
                texture.min_filter = gl.GL_NEAREST
                texture.mag_filter = gl.GL_NEAREST
            return image_data
        
        # Try to load
        self.load_item_sprite(item_id)
        if item_id in self.texture_images:
            img = self.texture_images[item_id]
            # Flip image vertically (PIL top-to-bottom -> pyglet bottom-to-top)
            flipped_img = img.transpose(FLIP_TOP_BOTTOM)
            img_data = flipped_img.tobytes()
            image_data = pyglet.image.ImageData(
                img.width, img.height,
                'RGBA', img_data,
                pitch=img.width * 4
            )
            # Get texture and set NEAREST filtering for pixel-perfect scaling
            texture = image_data.get_texture()
            if texture:
                texture.min_filter = gl.GL_NEAREST
                texture.mag_filter = gl.GL_NEAREST
            return image_data
        
        # Return None if not found (caller should handle fallback)
        return None
    
    def get_texture_size(self, item_id: str) -> Optional[tuple]:
        """
        Get texture size in pixels.
        
        Args:
            item_id: Item identifier
            
        Returns:
            (width, height) tuple or None if not found
        """
        if item_id in self.texture_images:
            img = self.texture_images[item_id]
            return img.size
        return None
    
    def preload_items(self, item_ids: list):
        """
        Preload all sprites for a list of item IDs.
        
        Args:
            item_ids: List of item identifiers
        """
        loaded_count = 0
        for item_id in item_ids:
            if self.load_item_sprite(item_id):
                loaded_count += 1
        
        self._log("info", f"Preloaded {loaded_count} item sprites")
    
    def release_all(self):
        """Release all loaded textures (except missing texture)."""
        for texture in self.textures.values():
            texture.release()
        self.textures.clear()
        self.texture_images.clear()
        # Don't release missing_texture - it's a fallback that should always be available
        self._log("info", "Released all item textures")

