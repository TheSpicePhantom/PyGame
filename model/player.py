"""
Model: Spieler-Logik
"""
from typing import Tuple


class Player:
    """Repräsentiert den Spieler"""
    
    def __init__(self, x: int, y: int, speed: float = 2.0):
        self.x = float(x)
        self.y = float(y)
        self.speed = speed
        self.target_x = float(x)
        self.target_y = float(y)
    
    def move(self, dx: float, dy: float, map_width: int, map_height: int):
        """Bewegt den Spieler in eine Richtung"""
        new_x = self.x + dx * self.speed
        new_y = self.y + dy * self.speed
        
        # Begrenze auf Kartenbereich
        new_x = max(0, min(new_x, map_width - 1))
        new_y = max(0, min(new_y, map_height - 1))
        
        self.x = new_x
        self.y = new_y
    
    def get_position(self) -> Tuple[float, float]:
        """Gibt die aktuelle Position zurück"""
        return (self.x, self.y)
    
    def get_grid_position(self) -> Tuple[int, int]:
        """Gibt die Position als Gitter-Koordinaten zurück"""
        return (int(self.x), int(self.y))
    
    def to_dict(self) -> dict:
        """Konvertiert den Spieler in ein Dictionary"""
        return {
            "position": {
                "x": self.x,
                "y": self.y
            }
        }
    
    @classmethod
    def from_dict(cls, data: dict, speed: float = 2.0) -> 'Player':
        """Erstellt einen Spieler aus einem Dictionary"""
        pos = data.get("position", {"x": 0, "y": 0})
        return cls(pos["x"], pos["y"], speed)












