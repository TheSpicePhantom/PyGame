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
                "core:iron_ore",
                9999,
                self.all_sprites,
                self.resource_sprites
            )
        
        # Copper ore patches
        for _ in range(3):
            x = random.randint(3, 15) * settings.TILE_SIZE
            y = random.randint(10, 20) * settings.TILE_SIZE
            ResourceNode(
                (x, y),
                "core:copper_ore",
                9999,
                self.all_sprites,
                self.resource_sprites
            )
        
        # Coal patches
        for _ in range(4):
            x = random.randint(10, 25) * settings.TILE_SIZE
            y = random.randint(5, 15) * settings.TILE_SIZE
            ResourceNode(
                (x, y),
                "core:coal",
                9999,
                self.all_sprites,
                self.resource_sprites
            )
    
    def draw_grid(self, surface):
        """Zeichnet das Grid auf die Oberfläche (ohne Kamera)"""
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
    
    def draw_grid_with_camera(self, surface, camera):
        """Zeichnet das Grid mit Kamera-Offset und 60° Neigung"""
        from core import settings
        
        # Berechne sichtbaren Bereich in Welt-Koordinaten
        cam_x, cam_y = camera.x, camera.y
        view_range_pixels = max(settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT) * 2
        
        # Berechne Tile-Bereich
        tile_start_x = int((cam_x - view_range_pixels) // settings.TILE_SIZE) - 1
        tile_end_x = int((cam_x + view_range_pixels) // settings.TILE_SIZE) + 1
        tile_start_y = int((cam_y - view_range_pixels) // settings.TILE_SIZE) - 1
        tile_end_y = int((cam_y + view_range_pixels) // settings.TILE_SIZE) + 1
        
        # Zeichne vertikale Linien (parallel zur Y-Achse)
        for tile_x in range(tile_start_x, tile_end_x + 1):
            world_x = tile_x * settings.TILE_SIZE
            
            # Berechne Endpunkte der Linie in Welt-Koordinaten
            top_world_y = cam_y - view_range_pixels
            bottom_world_y = cam_y + view_range_pixels
            
            # Konvertiere zu Bildschirm-Koordinaten
            top_screen_x, top_screen_y = camera.world_to_screen(world_x, top_world_y)
            bottom_screen_x, bottom_screen_y = camera.world_to_screen(world_x, bottom_world_y)
            
            # Zeichne nur wenn sichtbar
            if (top_screen_x > -100 and top_screen_x < settings.SCREEN_WIDTH + 100) or \
               (bottom_screen_x > -100 and bottom_screen_x < settings.SCREEN_WIDTH + 100):
                pygame.draw.line(
                    surface,
                    settings.COLOR_GRID,
                    (top_screen_x, top_screen_y),
                    (bottom_screen_x, bottom_screen_y)
                )
        
        # Zeichne horizontale Linien (parallel zur X-Achse)
        for tile_y in range(tile_start_y, tile_end_y + 1):
            world_y = tile_y * settings.TILE_SIZE
            
            # Berechne Endpunkte der Linie in Welt-Koordinaten
            left_world_x = cam_x - view_range_pixels
            right_world_x = cam_x + view_range_pixels
            
            # Konvertiere zu Bildschirm-Koordinaten
            left_screen_x, left_screen_y = camera.world_to_screen(left_world_x, world_y)
            right_screen_x, right_screen_y = camera.world_to_screen(right_world_x, world_y)
            
            # Zeichne nur wenn sichtbar
            if (left_screen_y > -100 and left_screen_y < settings.SCREEN_HEIGHT + 100) or \
               (right_screen_y > -100 and right_screen_y < settings.SCREEN_HEIGHT + 100):
                pygame.draw.line(
                    surface,
                    settings.COLOR_GRID,
                    (left_screen_x, left_screen_y),
                    (right_screen_x, right_screen_y)
                )
