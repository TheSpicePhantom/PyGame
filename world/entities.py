"""
World: Basis-Entity-Klassen für Spielobjekte
"""
import pygame
from core import settings


class Entity(pygame.sprite.Sprite):
    """Basis-Klasse für alle Spielobjekte"""
    
    def __init__(self, pos, color=(80, 80, 80), *groups):
        super().__init__(*groups)
        self.image = pygame.Surface((settings.TILE_SIZE, settings.TILE_SIZE))
        self.image.fill(color)
        self.rect = self.image.get_rect(topleft=pos)
        self._layer = settings.LAYER_FLOOR
    
    def update(self, dt):
        """Update-Methode, überschrieben von Unterklassen"""
        pass


class ResourceNode(Entity):
    """Ressourcen-Knoten (Erz, Kohle, etc.)"""
    
    def __init__(self, pos, resource_type, amount, *groups):
        super().__init__(pos, settings.COLOR_RESOURCE, *groups)
        self.resource_type = resource_type
        self.amount = amount
        self._layer = settings.LAYER_FLOOR
        
        # Visuelle Unterscheidung nach Ressourcentyp
        if resource_type == "core:iron_ore":
            self.image.fill((100, 120, 140))
        elif resource_type == "core:copper_ore":
            self.image.fill((180, 100, 60))
        elif resource_type == "core:coal":
            self.image.fill((30, 30, 30))
    
    def mine(self, amount=1):
        """Baut Ressourcen ab und gibt zurück, wie viel tatsächlich abgebaut wurde"""
        mined = min(amount, self.amount)
        self.amount -= mined
        
        if self.amount <= 0:
            self.kill()  # Entfernt Sprite wenn leer
        
        return mined
