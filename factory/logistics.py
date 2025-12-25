"""
Factory: Logistik-System für Transport und Lagerung
"""
from typing import Dict, List, Optional
from world.entities import Entity


class Storage(Entity):
    """Lagergebäude für Ressourcen"""
    
    def __init__(self, x: float, y: float, capacity: int = 1000):
        super().__init__(x, y, "storage")
        self.capacity = capacity
        self.inventory: Dict[str, int] = {}
    
    def on_update(self, dt: float):
        """Aktualisiert das Lager"""
        pass
    
    def get_total_items(self) -> int:
        """Gibt die Gesamtanzahl der gelagerten Items zurück"""
        return sum(self.inventory.values())
    
    def can_store(self, resource: str, amount: int) -> bool:
        """Prüft, ob Ressourcen gelagert werden können"""
        return self.get_total_items() + amount <= self.capacity
    
    def store(self, resource: str, amount: int) -> int:
        """Lagert Ressourcen (gibt tatsächlich gelagerte Menge zurück)"""
        if not self.can_store(resource, amount):
            amount = max(0, self.capacity - self.get_total_items())
        
        self.inventory[resource] = self.inventory.get(resource, 0) + amount
        return amount
    
    def retrieve(self, resource: str, amount: int) -> int:
        """Holt Ressourcen aus dem Lager (gibt tatsächlich geholte Menge zurück)"""
        available = self.inventory.get(resource, 0)
        retrieved = min(amount, available)
        self.inventory[resource] = available - retrieved
        return retrieved
    
    def has_resource(self, resource: str, amount: int) -> bool:
        """Prüft, ob genug Ressourcen vorhanden sind"""
        return self.inventory.get(resource, 0) >= amount


class ConveyorBelt(Entity):
    """Förderband für Transport"""
    
    def __init__(self, x: float, y: float, direction: str = "right"):
        super().__init__(x, y, "conveyor_belt")
        self.direction = direction  # "up", "down", "left", "right"
        self.speed = 1.0
        self.items: List[Dict] = []  # Liste von Items auf dem Band
    
    def on_update(self, dt: float):
        """Bewegt Items auf dem Förderband"""
        for item in self.items:
            self.move_item(item, dt)
    
    def move_item(self, item: Dict, dt: float):
        """Bewegt ein Item auf dem Band"""
        # Item-Position wird basierend auf Richtung aktualisiert
        # Vereinfachte Implementierung
        pass
    
    def add_item(self, item: Dict):
        """Fügt ein Item zum Förderband hinzu"""
        if len(self.items) < 10:  # Maximale Anzahl Items
            self.items.append(item)
    
    def remove_item(self, item: Dict):
        """Entfernt ein Item vom Förderband"""
        if item in self.items:
            self.items.remove(item)


class LogisticsNetwork:
    """Verwaltet das gesamte Logistik-Netzwerk"""
    
    def __init__(self):
        self.storages: List[Storage] = []
        self.conveyors: List[ConveyorBelt] = []
        self.transport_routes: List[Dict] = []
    
    def add_storage(self, storage: Storage):
        """Fügt ein Lager hinzu"""
        if storage not in self.storages:
            self.storages.append(storage)
    
    def add_conveyor(self, conveyor: ConveyorBelt):
        """Fügt ein Förderband hinzu"""
        if conveyor not in self.conveyors:
            self.conveyors.append(conveyor)
    
    def find_nearest_storage(self, x: float, y: float, resource: str, amount: int) -> Optional[Storage]:
        """Findet das nächste Lager mit verfügbaren Ressourcen"""
        best_storage = None
        best_distance = float('inf')
        
        for storage in self.storages:
            if storage.has_resource(resource, amount):
                distance = ((storage.x - x) ** 2 + (storage.y - y) ** 2) ** 0.5
                if distance < best_distance:
                    best_distance = distance
                    best_storage = storage
        
        return best_storage
    
    def update(self, dt: float):
        """Aktualisiert das Logistik-Netzwerk"""
        for conveyor in self.conveyors:
            conveyor.update(dt)





