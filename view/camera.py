"""
View: Kamera-System für folgende Kamera und Zoom
"""
from typing import Tuple


class Camera:
    """Verwaltet die Kamera-Position und den Zoom"""
    
    def __init__(self, min_zoom: float = 0.1, max_zoom: float = 3.0, initial_zoom: float = 1.0):
        self.x = 0.0
        self.y = 0.0
        self.zoom = initial_zoom
        self.min_zoom = min_zoom
        self.max_zoom = max_zoom
    
    def follow(self, target_x: float, target_y: float):
        """Lässt die Kamera einem Ziel folgen"""
        self.x = target_x
        self.y = target_y
    
    def set_zoom(self, zoom: float):
        """Setzt den Zoom-Wert (mit Begrenzung)"""
        self.zoom = max(self.min_zoom, min(self.max_zoom, zoom))
    
    def adjust_zoom(self, delta: float):
        """Ändert den Zoom um einen Betrag"""
        self.set_zoom(self.zoom + delta)
    
    def get_position(self) -> Tuple[float, float]:
        """Gibt die aktuelle Kamera-Position zurück"""
        return (self.x, self.y)
    
    def get_zoom(self) -> float:
        """Gibt den aktuellen Zoom-Wert zurück"""
        return self.zoom



















