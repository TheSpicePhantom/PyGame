"""
Model: Karten-Logik für das isometrische Spiel
"""
import json
from typing import Tuple


class Map:
    """Repräsentiert die Spielkarte"""
    
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.tiles = [[0 for _ in range(width)] for _ in range(height)]
    
    def is_valid_position(self, x: int, y: int) -> bool:
        """Prüft, ob eine Position auf der Karte gültig ist"""
        return 0 <= x < self.width and 0 <= y < self.height
    
    def get_tile(self, x: int, y: int) -> int:
        """Gibt den Tile-Wert an der Position zurück"""
        if self.is_valid_position(x, y):
            return self.tiles[y][x]
        return -1
    
    def set_tile(self, x: int, y: int, value: int):
        """Setzt den Tile-Wert an der Position"""
        if self.is_valid_position(x, y):
            self.tiles[y][x] = value
    
    def to_dict(self) -> dict:
        """Konvertiert die Karte in ein Dictionary"""
        return {
            "width": self.width,
            "height": self.height,
            "tiles": self.tiles
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Map':
        """Erstellt eine Karte aus einem Dictionary"""
        map_obj = cls(data["width"], data["height"])
        map_obj.tiles = data.get("tiles", map_obj.tiles)
        return map_obj

