"""
Core: Zoom Utilities - Zentrale Zoom-Berechnungen für konsistente Verwendung
"""
from typing import Tuple


def calculate_visible_world_size(screen_width: int, screen_height: int, zoom: float) -> Tuple[float, float]:
    """
    Calculate visible world size in pixels based on screen size and zoom.
    
    Args:
        screen_width: Screen width in pixels
        screen_height: Screen height in pixels
        zoom: Zoom factor (1.0 = 100%, 1.5 = 150% nah, 0.75 = 75% weit weg)
    
    Returns:
        Tuple of (visible_world_width, visible_world_height) in pixels
    
    Logic:
        Shader: screen_pos = (world_pos - center) * zoom + center
        Inverse: visible_world = screen_size / zoom
        - Zoom 1.5 (nah): 1920 / 1.5 = 1280 pixels Welt sichtbar (weniger)
        - Zoom 0.75 (weit): 1920 / 0.75 = 2560 pixels Welt sichtbar (mehr)
    """
    visible_world_width = screen_width / zoom
    visible_world_height = screen_height / zoom
    return (visible_world_width, visible_world_height)

