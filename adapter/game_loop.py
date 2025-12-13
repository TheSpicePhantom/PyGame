"""
Adapter: Haupt-Spielloop und Event-Management
"""
import pygame
from model.game import Game
from view.renderer import Renderer
from adapter.input_handler import InputHandler


class GameLoop:
    """Verwaltet die Haupt-Spielloop"""
    
    def __init__(self, config_path: str = "config/game_config.json"):
        pygame.init()
        self.game = Game(config_path)
        self.renderer = Renderer(self.game)
        self.input_handler = InputHandler()
        self.running = True
        self.clock = pygame.time.Clock()
    
    def run(self):
        """Startet die Haupt-Spielloop"""
        while self.running:
            # Event-Verarbeitung
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                else:
                    dx, dy, zoom = self.input_handler.handle_event(event)
                    if zoom is not None:
                        # Zoom anwenden
                        self.renderer.get_camera().adjust_zoom(zoom)
            
            # Bewegung abfragen
            dx, dy = self.input_handler.get_movement()
            
            # Spiel aktualisieren
            if dx != 0 or dy != 0:
                self.game.update(dx, dy)
            
            # Rendern
            self.renderer.render()
            
            # FPS begrenzen
            self.clock.tick(60)
        
        pygame.quit()
    
    def stop(self):
        """Beendet das Spiel"""
        self.running = False

