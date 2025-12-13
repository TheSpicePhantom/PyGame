"""
World: Welt- und Karten-Logik
"""
from typing import List, Tuple, Optional
from world.entities import Entity


class Tile:
    """Repräsentiert ein einzelnes Tile auf der Karte"""
    
    def __init__(self, x: int, y: int, tile_type: int = 0):
        self.x = x
        self.y = y
        self.tile_type = tile_type
        self.entity: Optional[Entity] = None
        self.building = None
    
    def is_walkable(self) -> bool:
        """Prüft, ob das Tile begehbar ist"""
        return self.tile_type == 0 and self.entity is None and self.building is None


class World:
    """Verwaltet die Spielwelt und Karte"""
    
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.tiles: List[List[Tile]] = []
        self.entities: List[Entity] = []
        
        # Initialisiere Karte
        for y in range(height):
            row = []
            for x in range(width):
                row.append(Tile(x, y, 0))
            self.tiles.append(row)
    
    def get_tile(self, x: int, y: int) -> Optional[Tile]:
        """Gibt das Tile an der Position zurück"""
        if self.is_valid_position(x, y):
            return self.tiles[y][x]
        return None
    
    def is_valid_position(self, x: int, y: int) -> bool:
        """Prüft, ob eine Position auf der Karte gültig ist"""
        return 0 <= x < self.width and 0 <= y < self.height
    
    def add_entity(self, entity: Entity):
        """Fügt eine Entität zur Welt hinzu"""
        if entity not in self.entities:
            self.entities.append(entity)
    
    def remove_entity(self, entity: Entity):
        """Entfernt eine Entität aus der Welt"""
        if entity in self.entities:
            self.entities.remove(entity)
    
    def update(self, dt: float):
        """Aktualisiert die Welt"""
        for entity in self.entities:
            entity.update(dt, self)
    
    def get_entities_at(self, x: int, y: int) -> List[Entity]:
        """Gibt alle Entitäten an einer Position zurück"""
        return [e for e in self.entities if int(e.x) == x and int(e.y) == y]

