"""
Core: Kamera-System mit Follow-Funktion
"""
import pygame
import math
from core import settings


class Camera:
    """Kamera, die dem Spieler folgt mit 60° Neigung"""
    
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.target_x = 0.0
        self.target_y = 0.0
        # 60 Grad Kamera-Neigung
        self.camera_angle = math.radians(60)
        self.y_scale = math.cos(self.camera_angle)  # cos(60°) ≈ 0.5
    
    def follow(self, target_x: float, target_y: float):
        """Setzt das Ziel, dem die Kamera folgen soll"""
        self.target_x = target_x
        self.target_y = target_y
        # Sofortige Position (kann später für Smooth-Following angepasst werden)
        self.x = target_x
        self.y = target_y
    
    def world_to_screen(self, world_x: float, world_y: float) -> tuple[float, float]:
        """Konvertiert Welt-Koordinaten zu Bildschirm-Koordinaten mit Kamera-Offset und 60° Neigung"""
        # Relative Position zur Kamera
        rel_x = world_x - self.x
        rel_y = world_y - self.y
        
        # Orthografische Projektion mit 60° Neigung
        # X bleibt unverändert, Y wird gestaucht
        screen_x = settings.SCREEN_WIDTH // 2 + rel_x
        screen_y = settings.SCREEN_HEIGHT // 2 + rel_y * self.y_scale
        
        return (screen_x, screen_y)
    
    def screen_to_world(self, screen_x: float, screen_y: float) -> tuple[float, float]:
        """Konvertiert Bildschirm-Koordinaten zu Welt-Koordinaten"""
        # Relative Position vom Bildschirmzentrum
        rel_x = screen_x - settings.SCREEN_WIDTH // 2
        rel_y = (screen_y - settings.SCREEN_HEIGHT // 2) / self.y_scale
        
        # Welt-Koordinaten
        world_x = self.x + rel_x
        world_y = self.y + rel_y
        
        return (world_x, world_y)
    
    def get_offset(self) -> tuple[float, float]:
        """Gibt den Kamera-Offset zurück"""
        return (self.x - settings.SCREEN_WIDTH // 2, 
                self.y - settings.SCREEN_HEIGHT // 2)

