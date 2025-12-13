"""
World: Spiel-Welt mit Grid und Ressourcen
"""
import pygame
import random
from core import settings
from world.entities import ResourceNode


class World:
    """Verwaltet die Spielwelt mit Grid und Ressourcen"""
    
    def __init__(self, all_sprites, resource_sprites):
        self.all_sprites = all_sprites
        self.resource_sprites = resource_sprites
        self.generate_resources()
    
    def generate_resources(self):
        """Generiert Ressourcen-Knoten in der Welt"""
        # Iron ore patches
        for _ in range(5):
            x = random.randint(3, 15) * settings.TILE_SIZE
            y = random.randint(3, 15) * settings.TILE_SIZE
            ResourceNode(
                (x, y),
                resource_type="core:iron_ore",
                amount=9999,
                self.all_sprites,
                self.resource_sprites
            )
        
        # Copper ore patches
        for _ in range(3):
            x = random.randint(3, 15) * settings.TILE_SIZE
            y = random.randint(10, 20) * settings.TILE_SIZE
            ResourceNode(
                (x, y),
                resource_type="core:copper_ore",
                amount=9999,
                self.all_sprites,
                self.resource_sprites
            )
        
        # Coal patches
        for _ in range(4):
            x = random.randint(10, 25) * settings.TILE_SIZE
            y = random.randint(5, 15) * settings.TILE_SIZE
            ResourceNode(
                (x, y),
                resource_type="core:coal",
                amount=9999,
                self.all_sprites,
                self.resource_sprites
            )
    
    def draw_grid(self, surface):
        """Zeichnet das Grid auf die Oberfläche"""
        for x in range(0, settings.SCREEN_WIDTH, settings.TILE_SIZE):
            pygame.draw.line(
                surface,
                settings.COLOR_GRID,
                (x, 0),
                (x, settings.SCREEN_HEIGHT)
            )
        for y in range(0, settings.SCREEN_HEIGHT, settings.TILE_SIZE):
            pygame.draw.line(
                surface,
                settings.COLOR_GRID,
                (0, y),
                (settings.SCREEN_WIDTH, y)
            )
