"""
Faction: Fraktions-System
"""
from typing import List, Dict, Optional
from enum import Enum


class FactionType(Enum):
    """Typen von Fraktionen"""
    PLAYER = "player"
    ENEMY = "enemy"
    NEUTRAL = "neutral"
    ALLY = "ally"


class Faction:
    """Repräsentiert eine Fraktion"""
    
    def __init__(self, faction_id: str, name: str, faction_type: FactionType):
        self.faction_id = faction_id
        self.name = name
        self.faction_type = faction_type
        self.members: List[str] = []  # Entity-IDs
        self.territory: List[tuple[int, int]] = []  # (x, y) Koordinaten
        self.resources: Dict[str, int] = {}
        self.relations: Dict[str, int] = {}  # {faction_id: relation_value}
    
    def add_member(self, entity_id: str):
        """Fügt ein Mitglied zur Fraktion hinzu"""
        if entity_id not in self.members:
            self.members.append(entity_id)
    
    def remove_member(self, entity_id: str):
        """Entfernt ein Mitglied aus der Fraktion"""
        if entity_id in self.members:
            self.members.remove(entity_id)
    
    def add_territory(self, x: int, y: int):
        """Fügt Territorium hinzu"""
        if (x, y) not in self.territory:
            self.territory.append((x, y))
    
    def remove_territory(self, x: int, y: int):
        """Entfernt Territorium"""
        if (x, y) in self.territory:
            self.territory.remove((x, y))
    
    def owns_territory(self, x: int, y: int) -> bool:
        """Prüft, ob die Fraktion dieses Territorium besitzt"""
        return (x, y) in self.territory
    
    def set_relation(self, faction_id: str, value: int):
        """Setzt die Beziehung zu einer anderen Fraktion (-100 bis 100)"""
        self.relations[faction_id] = max(-100, min(100, value))
    
    def get_relation(self, faction_id: str) -> int:
        """Gibt die Beziehung zu einer anderen Fraktion zurück"""
        return self.relations.get(faction_id, 0)
    
    def is_hostile_to(self, faction_id: str) -> bool:
        """Prüft, ob die Fraktion feindlich zu einer anderen ist"""
        return self.get_relation(faction_id) < -50
    
    def is_friendly_to(self, faction_id: str) -> bool:
        """Prüft, ob die Fraktion freundlich zu einer anderen ist"""
        return self.get_relation(faction_id) > 50


class FactionManager:
    """Verwaltet alle Fraktionen"""
    
    def __init__(self):
        self.factions: Dict[str, Faction] = {}
        self.create_default_factions()
    
    def create_default_factions(self):
        """Erstellt Standard-Fraktionen"""
        player_faction = Faction("player", "Spieler", FactionType.PLAYER)
        enemy_faction = Faction("enemy", "Feinde", FactionType.ENEMY)
        neutral_faction = Faction("neutral", "Neutral", FactionType.NEUTRAL)
        
        self.add_faction(player_faction)
        self.add_faction(enemy_faction)
        self.add_faction(neutral_faction)
        
        # Setze Beziehungen
        player_faction.set_relation("enemy", -100)
        enemy_faction.set_relation("player", -100)
    
    def add_faction(self, faction: Faction):
        """Fügt eine Fraktion hinzu"""
        self.factions[faction.faction_id] = faction
    
    def get_faction(self, faction_id: str) -> Optional[Faction]:
        """Gibt eine Fraktion zurück"""
        return self.factions.get(faction_id)
    
    def get_faction_for_entity(self, entity_id: str) -> Optional[Faction]:
        """Gibt die Fraktion für eine Entität zurück"""
        for faction in self.factions.values():
            if entity_id in faction.members:
                return faction
        return None
    
    def can_attack(self, attacker_id: str, target_id: str) -> bool:
        """Prüft, ob eine Entität eine andere angreifen kann"""
        attacker_faction = self.get_faction_for_entity(attacker_id)
        target_faction = self.get_faction_for_entity(target_id)
        
        if not attacker_faction or not target_faction:
            return True  # Wenn keine Fraktion, kann angegriffen werden
        
        if attacker_faction.faction_id == target_faction.faction_id:
            return False  # Gleiche Fraktion
        
        return attacker_faction.is_hostile_to(target_faction.faction_id)







