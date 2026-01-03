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


def get_viewport_bounds(screen_width: int, screen_height: int,
                        camera_x: float, camera_y: float, zoom: float):
    """
    Liefert Welt-Viewport-Grenzen, konsistent mit calculate_visible_world_size.
    
    Args:
        screen_width: Screen width in pixels
        screen_height: Screen height in pixels
        camera_x: Camera X position in world coordinates
        camera_y: Camera Y position in world coordinates
        zoom: Zoom factor (1.0 = 100%)
    
    Returns:
        Tuple of (viewport_min_x, viewport_max_x, viewport_min_y, viewport_max_y) in world coordinates
    """
    visible_world_width, visible_world_height = calculate_visible_world_size(
        screen_width, screen_height, zoom
    )
    
    viewport_min_x = camera_x - visible_world_width / 2.0
    viewport_max_x = camera_x + visible_world_width / 2.0
    viewport_min_y = camera_y - visible_world_height / 2.0
    viewport_max_y = camera_y + visible_world_height / 2.0
    
    return viewport_min_x, viewport_max_x, viewport_min_y, viewport_max_y

