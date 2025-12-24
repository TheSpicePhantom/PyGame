"""
View: TileColorPalette - Farbpalette für Tile-Rendering
"""
from typing import Dict, Tuple, List
import numpy as np


class TileColorPalette:
    """
    Farbpalette für Tile-Rendering.
    
    Statt RGB-Werte direkt in Vertices zu speichern, verwenden wir einen Farbindex,
    der auf eine Palette verweist. Dies reduziert die Vertex-Daten um 40% (von 5 auf 3 floats).
    """
    
    def __init__(self):
        """Initialize color palette with biome colors"""
        # Define color palette based on biomes.json
        # Index 0 is reserved for default/unknown color
        self.palette: List[Tuple[int, int, int]] = [
            (100, 100, 100),  # 0: Default/Gray (fallback)
            (20, 60, 120),    # 1: Deep Water
            (40, 100, 180),   # 2: Shallow Water
            (220, 200, 160),  # 3: Beach/Sand
            (100, 180, 80),   # 4: Plains/Grass
            (40, 100, 40),    # 5: Forest
            (120, 120, 100),  # 6: Mountains/Stone
            (240, 240, 250),  # 7: Snow
        ]
        
        # Create lookup dictionary: RGB -> index
        self.color_to_index: Dict[Tuple[int, int, int], int] = {}
        for index, color in enumerate(self.palette):
            self.color_to_index[color] = index
        
        # Normalized palette for shader (0.0-1.0 range)
        self.palette_normalized = np.array([
            [r / 255.0, g / 255.0, b / 255.0]
            for r, g, b in self.palette
        ], dtype=np.float32)
    
    def get_color_index(self, color: Tuple[int, int, int]) -> int:
        """
        Get color index for a given RGB color
        
        Args:
            color: RGB color tuple (r, g, b) in range [0, 255]
        
        Returns:
            Color index (0-255). If color not in palette, returns 0 (default).
        """
        # Normalize color tuple (handle list/tuple conversion)
        if isinstance(color, list):
            color = tuple(color)
        
        # Ensure we have 3 components
        if len(color) >= 3:
            color = (int(color[0]), int(color[1]), int(color[2]))
        else:
            return 0  # Default color
        
        # Look up in dictionary
        if color in self.color_to_index:
            return self.color_to_index[color]
        
        # Color not in palette - find closest match or add to palette
        # For now, return default (0) - could be extended to find closest match
        return 0
    
    def get_palette_size(self) -> int:
        """Get number of colors in palette"""
        return len(self.palette)
    
    def get_palette_normalized(self) -> np.ndarray:
        """Get normalized palette array for shader (shape: [N, 3])"""
        return self.palette_normalized
    
    def add_color(self, color: Tuple[int, int, int]) -> int:
        """
        Add a new color to the palette
        
        Args:
            color: RGB color tuple (r, g, b) in range [0, 255]
        
        Returns:
            Index of the added color
        """
        if color in self.color_to_index:
            return self.color_to_index[color]
        
        # Add to palette
        index = len(self.palette)
        self.palette.append(color)
        self.color_to_index[color] = index
        
        # Update normalized palette
        normalized = np.array([color[0] / 255.0, color[1] / 255.0, color[2] / 255.0], dtype=np.float32)
        self.palette_normalized = np.vstack([self.palette_normalized, normalized])
        
        return index

