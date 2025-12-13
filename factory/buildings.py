"""
Factory: Gebäude-System
"""
from typing import Dict, List, Optional
from world.entities import Entity


class Building(Entity):
    """Basisklasse für alle Gebäude"""
    
    def __init__(self, x: float, y: float, building_type: str, building_id: str = ""):
        super().__init__(x, y, building_id)
        self.building_type = building_type
        self.health = 100
        self.max_health = 100
        self.production_active = False
    
    def on_update(self, dt: float):
        """Aktualisiert das Gebäude"""
        if self.production_active:
            self.on_produce(dt)
    
    def on_produce(self, dt: float):
        """Wird während der Produktion aufgerufen"""
        pass
    
    def can_build_at(self, world: 'World', x: int, y: int) -> bool:
        """Prüft, ob an dieser Position gebaut werden kann"""
        tile = world.get_tile(x, y)
        return tile is not None and tile.is_walkable()
    
    def take_damage(self, amount: float):
        """Fügt dem Gebäude Schaden zu"""
        self.health = max(0, self.health - amount)
        if self.health <= 0:
            self.destroy()
    
    def repair(self, amount: float):
        """Repariert das Gebäude"""
        self.health = min(self.max_health, self.health + amount)


class ProductionBuilding(Building):
    """Gebäude, das Ressourcen produziert"""
    
    def __init__(self, x: float, y: float, building_type: str, recipe: Optional['Recipe'] = None):
        super().__init__(x, y, building_type)
        self.recipe = recipe
        self.production_timer = 0.0
        self.inventory: Dict[str, int] = {}
    
    def set_recipe(self, recipe: 'Recipe'):
        """Setzt das Produktionsrezept"""
        self.recipe = recipe
        self.production_timer = 0.0
    
    def on_produce(self, dt: float):
        """Produziert basierend auf dem Rezept"""
        if not self.recipe:
            return
        
        # Prüfe ob genug Ressourcen vorhanden
        if not self.has_required_resources():
            return
        
        self.production_timer += dt
        
        if self.production_timer >= self.recipe.production_time:
            self.produce_items()
            self.production_timer = 0.0
    
    def has_required_resources(self) -> bool:
        """Prüft, ob genug Ressourcen für die Produktion vorhanden sind"""
        if not self.recipe:
            return False
        
        for resource, amount in self.recipe.inputs.items():
            if self.inventory.get(resource, 0) < amount:
                return False
        return True
    
    def produce_items(self):
        """Produziert die Items basierend auf dem Rezept"""
        if not self.recipe:
            return
        
        # Verbrauche Input-Ressourcen
        for resource, amount in self.recipe.inputs.items():
            self.inventory[resource] = self.inventory.get(resource, 0) - amount
        
        # Produziere Output-Ressourcen
        for resource, amount in self.recipe.outputs.items():
            self.inventory[resource] = self.inventory.get(resource, 0) + amount

