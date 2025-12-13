"""
View: Haupt-Rendering-Engine
"""
import pygame
from view.isometric import OrthographicRenderer
from view.camera import Camera
from model.game import Game


class Renderer:
    """Verwaltet das Rendering des Spiels"""
    
    def __init__(self, game: Game):
        self.game = game
        config = game.get_config()
        
        window_config = config["window"]
        self.screen = pygame.display.set_mode(
            (window_config["width"], window_config["height"])
        )
        pygame.display.set_caption(window_config["title"])
        
        iso_config = config["isometric"]
        self.renderer = OrthographicRenderer(
            iso_config["tile_width"],
            iso_config["tile_height"]
        )
        
        self.camera = Camera(min_zoom=0.1, max_zoom=3.0, initial_zoom=1.0)
        self.offset_x = window_config["width"] // 2
        self.offset_y = window_config["height"] // 2
    
    def update_camera(self):
        """Aktualisiert die Kamera-Position, um dem Spieler zu folgen"""
        player_pos = self.game.player.get_position()
        self.camera.follow(player_pos[0], player_pos[1])
    
    def render(self):
        """Rendert den kompletten Bildschirm"""
        # Hintergrund löschen (schwarz)
        self.screen.fill((0, 0, 0))
        
        # Kamera aktualisieren
        self.update_camera()
        
        config = self.game.get_config()
        map_config = config["map"]
        player_config = config["player"]
        
        # Kamera-Position und Zoom
        cam_x, cam_y = self.camera.get_position()
        zoom = self.camera.get_zoom()
        
        # Erstelle temporären Renderer mit Zoom
        temp_tile_width = int(self.renderer.tile_width * zoom)
        temp_tile_height = int(self.renderer.tile_height * zoom)
        temp_renderer = OrthographicRenderer(temp_tile_width, temp_tile_height)
        
        # Berechne Kamera-Offset in Bildschirmkoordinaten
        cam_screen_x, cam_screen_y = temp_renderer.cartesian_to_screen(cam_x, cam_y)
        cam_offset_x = self.offset_x - cam_screen_x
        cam_offset_y = self.offset_y - cam_screen_y
        
        # Berechne sichtbaren Bereich (optimiert für große Karten)
        view_range = int(30 / zoom)  # Mehr Tiles bei kleinerem Zoom
        
        player_grid_x, player_grid_y = self.game.player.get_grid_position()
        min_x = max(0, player_grid_x - view_range)
        max_x = min(self.game.map.width, player_grid_x + view_range)
        min_y = max(0, player_grid_y - view_range)
        max_y = min(self.game.map.height, player_grid_y + view_range)
        
        # Zeichne Karte (nur sichtbarer Bereich)
        for y in range(min_y, max_y):
            for x in range(min_x, max_x):
                # Einfache Boden-Tiles
                tile_color = (100, 150, 100) if (x + y) % 2 == 0 else (120, 170, 120)
                
                # Prüfe ob Tile sichtbar ist
                screen_x, screen_y = temp_renderer.cartesian_to_screen(x, y)
                final_x = screen_x + cam_offset_x
                final_y = screen_y + cam_offset_y
                
                # Zeichne nur wenn sichtbar
                if -200 < final_x < self.screen.get_width() + 200 and -200 < final_y < self.screen.get_height() + 200:
                    temp_renderer.draw_tile(
                        self.screen, x, y, tile_color,
                        cam_offset_x, cam_offset_y
                    )
        
        # Zeichne Spieler
        player_pos = self.game.player.get_position()
        player_color = tuple(player_config["color"])
        
        # Berechne relative Position für Spieler
        rel_x = player_pos[0] - cam_x
        rel_y = player_pos[1] - cam_y
        
        # Skaliere Größe mit Zoom
        scaled_size = max(1, int(player_config["size"] * zoom))
        scaled_height = max(1, int(player_config["height"] * zoom))
        
        temp_renderer.draw_player(
            self.screen,
            rel_x,
            rel_y,
            player_color,
            scaled_size,
            scaled_height,
            self.offset_x,
            self.offset_y
        )
        
        pygame.display.flip()
    
    def get_camera(self) -> Camera:
        """Gibt die Kamera zurück"""
        return self.camera
    
    def get_screen(self) -> pygame.Surface:
        """Gibt den Bildschirm zurück"""
        return self.screen

