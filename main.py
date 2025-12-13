"""
Hauptdatei: Startet das Top-Down Factorio-Style Spiel
"""
import pygame
from core import settings
from core.input import InputHandler
from core.camera import Camera
from world.world import World
from combat.player import Player
from factory.recipes import load_recipes


def main():
    """Hauptfunktion"""
    pygame.init()
    screen = pygame.display.set_mode((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    pygame.display.set_caption("PyGame - Factorio Style")
    clock = pygame.time.Clock()
    
    # Lade Rezepte beim Start
    load_recipes()
    
    # Sprite-Gruppen
    all_sprites = pygame.sprite.LayeredUpdates()
    resource_sprites = pygame.sprite.Group()
    building_sprites = pygame.sprite.Group()
    
    # Welt erstellen
    world = World(all_sprites, resource_sprites)
    
    # Input & Player
    input_handler = InputHandler()
    camera = Camera()
    
    # Player startet in der Mitte der Welt
    player = Player(
        pos=(settings.SCREEN_WIDTH // 2, settings.SCREEN_HEIGHT // 2),
        input_handler=input_handler,
    )
    all_sprites.add(player, layer=settings.LAYER_PLAYER)
    
    # Kamera auf Spieler ausrichten
    camera.follow(player.rect.centerx, player.rect.centery)
    
    # Game loop
    running = True
    while running:
        dt = clock.tick(settings.FPS) / 1000.0
        
        # Event handling
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            input_handler.handle_event(event)
        
        # Update
        input_handler.update()
        all_sprites.update(dt)
        
        # Kamera folgt Spieler
        camera.follow(player.rect.centerx, player.rect.centery)
        
        # Render
        screen.fill(settings.COLOR_BG)
        
        # Zeichne Grid mit Kamera-Offset und 60° Neigung
        world.draw_grid_with_camera(screen, camera)
        
        # Zeichne Sprites mit Kamera-Offset und 60° Neigung
        # Sortiere nach Layer für korrektes Rendering
        sorted_sprites = sorted(all_sprites.sprites(), key=lambda s: getattr(s, '_layer', 0))
        
        for sprite in sorted_sprites:
            # Konvertiere Welt-Koordinaten zu Bildschirm-Koordinaten
            screen_x, screen_y = camera.world_to_screen(sprite.rect.centerx, sprite.rect.centery)
            
            # Erstelle temporäres Rect für Rendering
            render_rect = sprite.image.get_rect(center=(screen_x, screen_y))
            
            # Zeichne Sprite
            screen.blit(sprite.image, render_rect)
        
        # Debug info
        font = pygame.font.Font(None, 24)
        fps_text = font.render(f"FPS: {int(clock.get_fps())}", True, (255, 255, 255))
        world_pos = camera.screen_to_world(player.rect.centerx, player.rect.centery)
        pos_text = font.render(f"World Pos: ({int(world_pos[0])}, {int(world_pos[1])})", True, (255, 255, 255))
        screen.blit(fps_text, (10, 10))
        screen.blit(pos_text, (10, 35))
        
        pygame.display.flip()
    
    pygame.quit()


if __name__ == "__main__":
    main()
