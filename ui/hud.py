"""
UI: Heads-Up Display (HUD)
"""
import pygame
from typing import Optional
from combat.player import Player


class HUD:
    """Heads-Up Display für Spielinformationen"""
    
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.font = pygame.font.Font(None, 24)
        self.small_font = pygame.font.Font(None, 18)
        self.show_fps = True
        self.fps = 0
    
    def set_fps(self, fps: float):
        """Setzt die aktuelle FPS-Anzeige"""
        self.fps = fps
    
    def render(self, player: Optional[Player] = None):
        """Rendert das HUD"""
        if self.show_fps:
            self.render_fps()
        
        if player:
            self.render_player_info(player)
    
    def render_fps(self):
        """Rendert die FPS-Anzeige"""
        fps_text = self.small_font.render(f"FPS: {int(self.fps)}", True, (255, 255, 255))
        self.screen.blit(fps_text, (10, 10))
    
    def render_player_info(self, player: Player):
        """Rendert Spielerinformationen"""
        # Gesundheitsbalken
        bar_width = 200
        bar_height = 20
        bar_x = 10
        bar_y = 40
        
        # Hintergrund
        pygame.draw.rect(self.screen, (100, 0, 0), 
                        (bar_x, bar_y, bar_width, bar_height))
        
        # Gesundheitsbalken
        health_width = int(bar_width * (player.health / player.max_health))
        pygame.draw.rect(self.screen, (0, 255, 0), 
                        (bar_x, bar_y, health_width, bar_height))
        
        # Umrandung
        pygame.draw.rect(self.screen, (255, 255, 255), 
                        (bar_x, bar_y, bar_width, bar_height), 2)
        
        # Text
        health_text = self.small_font.render(
            f"HP: {int(player.health)}/{player.max_health}", 
            True, (255, 255, 255)
        )
        self.screen.blit(health_text, (bar_x + 5, bar_y + 2))
        
        # Level und Erfahrung
        level_text = self.font.render(
            f"Level: {player.level} | XP: {player.experience}", 
            True, (255, 255, 255)
        )
        self.screen.blit(level_text, (10, 70))
        
        # Waffe
        if player.weapon:
            weapon_text = self.small_font.render(
                f"Weapon: {player.weapon.name}", 
                True, (255, 255, 255)
            )
            self.screen.blit(weapon_text, (10, 100))


class Minimap:
    """Minimap für die Kartenansicht"""
    
    def __init__(self, screen: pygame.Surface, world_width: int, world_height: int):
        self.screen = screen
        self.world_width = world_width
        self.world_height = world_height
        self.size = 150  # Größe der Minimap
        self.x = screen.get_width() - self.size - 10
        self.y = 10
    
    def render(self, player_x: float, player_y: float, entities: list = None):
        """Rendert die Minimap"""
        # Hintergrund
        pygame.draw.rect(self.screen, (50, 50, 50), 
                        (self.x, self.y, self.size, self.size))
        pygame.draw.rect(self.screen, (255, 255, 255), 
                        (self.x, self.y, self.size, self.size), 2)
        
        # Skalierung
        scale_x = self.size / self.world_width
        scale_y = self.size / self.world_height
        
        # Spieler
        player_screen_x = self.x + int(player_x * scale_x)
        player_screen_y = self.y + int(player_y * scale_y)
        pygame.draw.circle(self.screen, (0, 255, 0), 
                         (player_screen_x, player_screen_y), 3)
        
        # Entitäten
        if entities:
            for entity in entities:
                if hasattr(entity, 'x') and hasattr(entity, 'y'):
                    entity_x = self.x + int(entity.x * scale_x)
                    entity_y = self.y + int(entity.y * scale_y)
                    color = (255, 0, 0) if hasattr(entity, 'enemy_type') else (255, 255, 0)
                    pygame.draw.circle(self.screen, color, (entity_x, entity_y), 2)

