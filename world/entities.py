"""
World: Entitäten-System
"""
from typing import Optional
from abc import ABC, abstractmethod


class Entity:
    """Basisklasse für alle Entitäten in der Welt"""
    
    def __init__(self, x: float, y: float, entity_id: str = ""):
        self.x = float(x)
        self.y = float(y)
        self.entity_id = entity_id
        self.active = True
        self.world: Optional['World'] = None
    
    def update(self, dt: float, world: 'World'):
        """Aktualisiert die Entität"""
        if not self.active:
            return
        self.world = world
        self.on_update(dt)
    
    @abstractmethod
    def on_update(self, dt: float):
        """Wird bei jedem Update aufgerufen"""
        pass
    
    def get_position(self) -> tuple[float, float]:
        """Gibt die Position zurück"""
        return (self.x, self.y)
    
    def set_position(self, x: float, y: float):
        """Setzt die Position"""
        self.x = float(x)
        self.y = float(y)
    
    def destroy(self):
        """Zerstört die Entität"""
        self.active = False
        if self.world:
            self.world.remove_entity(self)


class MovableEntity(Entity):
    """Entität, die sich bewegen kann"""
    
    def __init__(self, x: float, y: float, speed: float = 1.0, entity_id: str = ""):
        super().__init__(x, y, entity_id)
        self.speed = speed
        self.velocity_x = 0.0
        self.velocity_y = 0.0
    
    def move(self, dx: float, dy: float, world: 'World'):
        """Bewegt die Entität"""
        new_x = self.x + dx * self.speed
        new_y = self.y + dy * self.speed
        
        # Begrenze auf Weltbereich
        if world:
            new_x = max(0, min(new_x, world.width - 1))
            new_y = max(0, min(new_y, world.height - 1))
        
        self.x = new_x
        self.y = new_y
    
    def on_update(self, dt: float):
        """Bewegt die Entität basierend auf Geschwindigkeit"""
        if self.velocity_x != 0 or self.velocity_y != 0:
            if self.world:
                self.move(self.velocity_x * dt, self.velocity_y * dt, self.world)
            self.velocity_x = 0.0
            self.velocity_y = 0.0

