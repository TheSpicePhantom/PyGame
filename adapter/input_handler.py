"""
Adapter: Input-Handling für Tastatureingaben und Maus
"""
import pygame
from typing import Tuple, Optional


class InputHandler:
    """Verarbeitet Tastatureingaben und Maus-Events"""
    
    def __init__(self):
        self.keys_pressed = {}
        self.zoom_delta = 0.0
    
    def handle_event(self, event: pygame.event.Event) -> Tuple[float, float, Optional[float]]:
        """Verarbeitet ein Event und gibt Bewegungsvektor und Zoom-Delta zurück"""
        dx, dy = 0.0, 0.0
        zoom = None
        
        if event.type == pygame.KEYDOWN:
            self.keys_pressed[event.key] = True
        elif event.type == pygame.KEYUP:
            self.keys_pressed[event.key] = False
        elif event.type == pygame.MOUSEWHEEL:
            # Mausrad für Zoom
            zoom = event.y * 0.1  # Zoom-Geschwindigkeit
        
        # WASD-Steuerung
        if self.keys_pressed.get(pygame.K_w, False):
            dy -= 1.0
        if self.keys_pressed.get(pygame.K_s, False):
            dy += 1.0
        if self.keys_pressed.get(pygame.K_a, False):
            dx -= 1.0
        if self.keys_pressed.get(pygame.K_d, False):
            dx += 1.0
        
        return (dx, dy, zoom)
    
    def get_movement(self) -> Tuple[float, float]:
        """Gibt den aktuellen Bewegungsvektor basierend auf gedrückten Tasten zurück"""
        dx, dy = 0.0, 0.0
        
        keys = pygame.key.get_pressed()
        if keys[pygame.K_w]:
            dy -= 1.0
        if keys[pygame.K_s]:
            dy += 1.0
        if keys[pygame.K_a]:
            dx -= 1.0
        if keys[pygame.K_d]:
            dx += 1.0
        
        return (dx, dy)

