"""
Faction: Eroberungs-System
"""
from typing import Optional
from faction.faction import Faction, FactionManager


class CapturePoint:
    """Repräsentiert einen Eroberungspunkt"""
    
    def __init__(self, x: int, y: int, capture_time: float = 5.0):
        self.x = x
        self.y = y
        self.capture_time = capture_time
        self.current_capture_time = 0.0
        self.owner: Optional[Faction] = None
        self.capturing_faction: Optional[Faction] = None
        self.capturing_entities: list = []  # Liste von Entity-IDs die erobern
    
    def start_capture(self, faction: Faction, entity_id: str):
        """Startet die Eroberung durch eine Fraktion"""
        if self.owner == faction:
            return  # Bereits besessen
        
        if self.capturing_faction != faction:
            # Neue Fraktion beginnt Eroberung
            self.capturing_faction = faction
            self.current_capture_time = 0.0
            self.capturing_entities = []
        
        if entity_id not in self.capturing_entities:
            self.capturing_entities.append(entity_id)
    
    def stop_capture(self, entity_id: str):
        """Stoppt die Eroberung durch eine Entität"""
        if entity_id in self.capturing_entities:
            self.capturing_entities.remove(entity_id)
        
        if len(self.capturing_entities) == 0:
            self.capturing_faction = None
            self.current_capture_time = 0.0
    
    def update(self, dt: float):
        """Aktualisiert den Eroberungspunkt"""
        if not self.capturing_faction or len(self.capturing_entities) == 0:
            return
        
        # Prüfe ob gegnerische Entitäten in der Nähe sind
        if self.has_enemy_entities():
            self.current_capture_time = 0.0
            return
        
        self.current_capture_time += dt
        
        if self.current_capture_time >= self.capture_time:
            self.complete_capture()
    
    def has_enemy_entities(self) -> bool:
        """Prüft, ob feindliche Entitäten in der Nähe sind"""
        # Vereinfachte Implementierung
        # In der echten Version würde hier nach feindlichen Entitäten gesucht
        return False
    
    def complete_capture(self):
        """Schließt die Eroberung ab"""
        if self.capturing_faction:
            # Entferne von alter Fraktion
            if self.owner:
                self.owner.remove_territory(self.x, self.y)
            
            # Füge zu neuer Fraktion hinzu
            self.owner = self.capturing_faction
            self.owner.add_territory(self.x, self.y)
            
            # Reset
            self.capturing_faction = None
            self.current_capture_time = 0.0
            self.capturing_entities = []
    
    def get_capture_progress(self) -> float:
        """Gibt den Eroberungsfortschritt zurück (0.0 bis 1.0)"""
        if not self.capturing_faction:
            return 0.0
        return min(1.0, self.current_capture_time / self.capture_time)


class CaptureManager:
    """Verwaltet alle Eroberungspunkte"""
    
    def __init__(self, faction_manager: FactionManager):
        self.faction_manager = faction_manager
        self.capture_points: list[CapturePoint] = []
    
    def add_capture_point(self, capture_point: CapturePoint):
        """Fügt einen Eroberungspunkt hinzu"""
        if capture_point not in self.capture_points:
            self.capture_points.append(capture_point)
    
    def get_capture_point_at(self, x: int, y: int) -> Optional[CapturePoint]:
        """Gibt den Eroberungspunkt an einer Position zurück"""
        for cp in self.capture_points:
            if cp.x == x and cp.y == y:
                return cp
        return None
    
    def update(self, dt: float):
        """Aktualisiert alle Eroberungspunkte"""
        for cp in self.capture_points:
            cp.update(dt)
















