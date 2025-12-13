"""
Hauptdatei: Startet das Top-Down Factorio-Style Spiel
"""
import pygame
from core import settings
from core.input import InputHandler
from world.world import World
from combat.player import Player
from factory.recipes import load_recipes
from core.camera import Camera


def main():
    """Hauptfunktion"""
    pygame.init()
    screen = pygame.display.set_mode((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    pygame.display.set_caption("PyGame - Factorio Style")
    clock = pygame.time.Clock()
    
    # Lade Rezepte beim Start
    load_recipes()
    print("[Main] Loaded recipes from JSON")
    
    # Sprite-Gruppen
    all_sprites = pygame.sprite.LayeredUpdates()
    resource_sprites = pygame.sprite.Group()
    building_sprites = pygame.sprite.Group()
    
    # Welt erstellen
    world = World(all_sprites, resource_sprites, seed=None)  # Optional: seed=12345 für reproduzierbare Welt
    
    # Input & Player
    input_handler = InputHandler()
    
    # Player startet in der Mitte der Welt (nicht oben links)
    # Berechne Startposition in der Mitte der Welt
    start_world_x = settings.WORLD_SIZE_TILES * settings.TILE_SIZE // 2
    start_world_y = settings.WORLD_SIZE_TILES * settings.TILE_SIZE // 2
    
    player = Player(
        pos=(start_world_x, start_world_y),
        input_handler=input_handler,
    )
    all_sprites.add(player, layer=settings.LAYER_PLAYER)
    
    # Kamera initialisieren und sofort auf Spielerposition setzen
    camera = Camera(target=player, lerp_speed=settings.CAMERA_LERP_SPEED)
    # Kamera sofort auf Spielerposition setzen (ohne Lerp beim Start)
    camera.x = player.rect.centerx
    camera.y = player.rect.centery
    
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
        camera.update(dt)
        world.update(player.rect.center)
        
        # Render
        screen.fill(settings.COLOR_BG)
        world.draw_grid(screen, camera)
        for sprite in all_sprites:
            screen.blit(sprite.image, camera.apply(sprite))
        
        # Debug info
        font = pygame.font.Font(None, 24)
        fps_text = font.render(f"FPS: {int(clock.get_fps())}", True, (255, 255, 255))
        pos_text = font.render(f"Pos: ({player.rect.x}, {player.rect.y})", True, (255, 255, 255))
        screen.blit(fps_text, (10, 10))
        screen.blit(pos_text, (10, 35))
        
        pygame.display.flip()
    
    pygame.quit()


if __name__ == "__main__":
    main()
