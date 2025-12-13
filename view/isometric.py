"""
View: Orthografische Projektion mit schräger Kamera
"""
import pygame
import math
from typing import Tuple


class OrthographicRenderer:
    """Rendert Objekte in orthografischer Projektion mit schräger Kamera"""
    
    def __init__(self, tile_width: int, tile_height: int):
        self.tile_width = tile_width
        self.tile_height = tile_height
        # Für quadratische Tiles: tile_size sollte gleich sein
        self.tile_size = tile_width  # Verwende tile_width als Basis
        # Kamera-Neigung: 60 Grad für schräge Draufsicht
        self.camera_angle = math.radians(60)
        # Skalierung basierend auf Kamera-Winkel (cos für Y-Stauchung)
        self.y_scale = math.cos(self.camera_angle)
    
    def cartesian_to_screen(self, x: float, y: float) -> Tuple[int, int]:
        """Konvertiert kartesische Koordinaten in Bildschirmkoordinaten mit 60° Kamera-Neigung"""
        # Orthografische Projektion mit 60° Neigung
        # X bleibt unverändert, Y wird gestaucht durch cos(60°)
        screen_x = x * self.tile_size
        screen_y = y * self.tile_size * self.y_scale
        return (int(screen_x), int(screen_y))
    
    def draw_tile(self, surface: pygame.Surface, x: int, y: int, 
                  color: Tuple[int, int, int], offset_x: int = 0, offset_y: int = 0):
        """Zeichnet ein quadratisches Tile mit 60° Kamera-Neigung"""
        # Berechne die Position des Tiles
        base_x = x * self.tile_size
        base_y = y * self.tile_size * self.y_scale
        
        # Zeichne ein Quadrat (X-Breite bleibt gleich, Y-Höhe wird gestaucht)
        rect = pygame.Rect(
            base_x + offset_x,
            base_y + offset_y,
            self.tile_size,
            int(self.tile_size * self.y_scale)
        )
        pygame.draw.rect(surface, color, rect)
        pygame.draw.rect(surface, (0, 0, 0), rect, 1)  # Umrandung
    
    def cartesian_to_screen_3d(self, x: float, y: float, z: float) -> Tuple[int, int]:
        """Konvertiert 3D kartesische Koordinaten in Bildschirmkoordinaten mit 60° Neigung"""
        # Orthografische Projektion mit 60° Neigung
        # X bleibt unverändert, Y wird gestaucht, Z wird sichtbar
        screen_x = x * self.tile_size
        screen_y = y * self.tile_size * self.y_scale - z * self.tile_size * math.sin(self.camera_angle)
        return (int(screen_x), int(screen_y))
    
    def draw_player(self, surface: pygame.Surface, x: float, y: float,
                    color: Tuple[int, int, int], size: int, height: int,
                    offset_x: int = 0, offset_y: int = 0):
        """Zeichnet den Spieler als 3D-Würfel mit schräger Kamera"""
        # Zentrum des Würfels
        center_x = x
        center_y = y
        center_z = 0
        
        # Berechne die Ecken des Würfels in 3D
        half_size = size / 2
        
        # Ecken der Basis (z = 0)
        base_corners_3d = [
            (center_x - half_size, center_y - half_size, 0),  # Vorne links
            (center_x + half_size, center_y - half_size, 0),  # Vorne rechts
            (center_x + half_size, center_y + half_size, 0),  # Hinten rechts
            (center_x - half_size, center_y + half_size, 0),  # Hinten links
        ]
        
        # Ecken der Oberseite (z = height)
        top_corners_3d = [
            (center_x - half_size, center_y - half_size, height),  # Vorne links
            (center_x + half_size, center_y - half_size, height),  # Vorne rechts
            (center_x + half_size, center_y + half_size, height),  # Hinten rechts
            (center_x - half_size, center_y + half_size, height),  # Hinten links
        ]
        
        # Konvertiere zu Bildschirmkoordinaten
        base_corners = [self.cartesian_to_screen_3d(cx, cy, cz) 
                       for cx, cy, cz in base_corners_3d]
        top_corners = [self.cartesian_to_screen_3d(cx, cy, cz) 
                      for cx, cy, cz in top_corners_3d]
        
        # Verschiebe um Offset
        base_corners = [(px + offset_x, py + offset_y) for px, py in base_corners]
        top_corners = [(px + offset_x, py + offset_y) for px, py in top_corners]
        
        # Farben für 3D-Effekt
        top_color = color  # Oberseite - hellste
        right_color = tuple(max(0, c - 60) for c in color)  # Rechte Seite - mittel
        left_color = tuple(max(0, c - 100) for c in color)  # Linke Seite - dunkelste
        
        # Zeichne die drei sichtbaren Seiten des Würfels
        
        # 1. Rechte Seite (rechts sichtbar)
        right_side = [
            base_corners[1],  # Unten vorne rechts
            top_corners[1],   # Oben vorne rechts
            top_corners[2],   # Oben hinten rechts
            base_corners[2]   # Unten hinten rechts
        ]
        pygame.draw.polygon(surface, right_color, right_side)
        pygame.draw.polygon(surface, (0, 0, 0), right_side, 1)
        
        # 2. Linke Seite (links sichtbar)
        left_side = [
            base_corners[0],  # Unten vorne links
            top_corners[0],   # Oben vorne links
            top_corners[3],   # Oben hinten links
            base_corners[3]   # Unten hinten links
        ]
        pygame.draw.polygon(surface, left_color, left_side)
        pygame.draw.polygon(surface, (0, 0, 0), left_side, 1)
        
        # 3. Oberseite (Top-Face) - zuletzt gezeichnet, damit sie oben liegt
        top_face = [
            top_corners[0],   # Vorne links
            top_corners[1],   # Vorne rechts
            top_corners[2],   # Hinten rechts
            top_corners[3]    # Hinten links
        ]
        pygame.draw.polygon(surface, top_color, top_face)
        pygame.draw.polygon(surface, (0, 0, 0), top_face, 1)

