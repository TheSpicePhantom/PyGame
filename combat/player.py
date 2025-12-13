"""
Combat: Spieler-Klasse mit Bewegung und Inventar
"""
import pygame
from core import settings


class Player(pygame.sprite.Sprite):
    """Spieler-Charakter mit Top-Down-Bewegung"""
    
    def __init__(self, pos, input_handler, *groups):
        super().__init__(*groups)
        self.image = pygame.Surface((settings.TILE_SIZE, settings.TILE_SIZE))
        self.image.fill(settings.COLOR_PLAYER)
        self.rect = self.image.get_rect(center=pos)
        self.input_handler = input_handler
        self.speed = settings.PLAYER_SPEED
        self._layer = settings.LAYER_PLAYER
        
        # Inventar-System (für später)
        self.inventory = {}
    
    def update(self, dt):
        """Aktualisiert die Spielerposition basierend auf Input (in Welt-Koordinaten)"""
        move = self.input_handler.move_dir * self.speed * dt
        self.rect.x += move.x
        self.rect.y += move.y
        
        # Keine Begrenzung mehr - Spieler bewegt sich frei in der Welt
        # Die Kamera folgt dem Spieler
    
    def add_item(self, item_id, amount=1):
        """Fügt Items zum Inventar hinzu"""
        if item_id in self.inventory:
            self.inventory[item_id] += amount
        else:
            self.inventory[item_id] = amount
