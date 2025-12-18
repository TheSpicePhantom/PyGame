"""
Core: Input-Handler für Spielersteuerung
"""
import pygame
from core import settings


class InputHandler:
    """Verarbeitet Tastatur- und Maus-Eingaben"""
    
    def __init__(self):
        self.move_dir = pygame.Vector2()
        self.build_mode = False
        self.rotate_pressed = False
    
    def update(self):
        """Aktualisiert den Bewegungsvektor basierend auf Tasteneingaben"""
        keys = pygame.key.get_pressed()
        self.move_dir.x = 0
        self.move_dir.y = 0
        
        if keys[settings.KEY_MOVE_LEFT]:
            self.move_dir.x = -1
        if keys[settings.KEY_MOVE_RIGHT]:
            self.move_dir.x = 1
        if keys[settings.KEY_MOVE_UP]:
            self.move_dir.y = -1
        if keys[settings.KEY_MOVE_DOWN]:
            self.move_dir.y = 1
        
        # Normalisiere Bewegung bei diagonaler Bewegung
        if self.move_dir.length_squared() > 0:
            self.move_dir = self.move_dir.normalize()
    
    def handle_event(self, event):
        """Verarbeitet einzelne Events"""
        if event.type == pygame.KEYDOWN:
            if event.key == settings.KEY_BUILD_MODE:
                self.build_mode = not self.build_mode
            elif event.key == settings.KEY_ROTATE:
                self.rotate_pressed = True
        elif event.type == pygame.KEYUP:
            if event.key == settings.KEY_ROTATE:
                self.rotate_pressed = False






