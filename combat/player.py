"""
Combat: Spieler-Klasse mit Bewegung und Inventar
"""
import pygame
from core import settings


class Player(pygame.sprite.Sprite):
    """Spieler-Charakter mit Top-Down-Bewegung"""
    
    def __init__(self, pos, input_handler, *groups, performance_monitor=None):
        super().__init__(*groups)
        self.image = pygame.Surface((settings.TILE_SIZE, settings.TILE_SIZE))
        self.image.fill(settings.COLOR_PLAYER)
        self.image = self.image.convert()  # Optimize for blitting
        self.rect = self.image.get_rect(center=pos)
        self.input_handler = input_handler
        self.speed = settings.PLAYER_SPEED
        self._layer = settings.LAYER_PLAYER
        self.performance_monitor = performance_monitor
        
        # Inventar-System (für später)
        self.inventory = {}
    
    def update(self, dt):
        """Aktualisiert die Spielerposition basierend auf Input"""
        move = self.input_handler.move_dir * self.speed * dt
        
        # Record movement for performance metrics
        if self.performance_monitor and move.length_squared() > 0:
            # Determine direction
            if abs(move.x) > abs(move.y):
                direction = "right" if move.x > 0 else "left"
            else:
                direction = "down" if move.y > 0 else "up"
            self.performance_monitor.record_movement(direction)
        
        self.rect.x += move.x
        self.rect.y += move.y
    
    def add_item(self, item_id, amount=1):
        """Fügt Items zum Inventar hinzu"""
        if item_id in self.inventory:
            self.inventory[item_id] += amount
        else:
            self.inventory[item_id] = amount
