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
from ui.pause_menu import PauseMenu
from ui.settings_menu import SettingsMenu
from ui.audio_settings import AudioSettings
from ui.graphics_settings import GraphicsSettings
from ui.controls_settings import ControlsSettings
from ui.save_menu import SaveMenu


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

    # Pause-Menü und Settings-Menüs
    pause_menu = PauseMenu()
    settings_menu = SettingsMenu()
    audio_settings = AudioSettings()
    graphics_settings = GraphicsSettings()
    controls_settings = ControlsSettings()
    save_menu = SaveMenu()

    # Menü-Referenzen setzen (wichtig für Option 3)
    pause_menu.set_settings_menu(settings_menu)
    pause_menu.set_save_menu(save_menu)

    # Game loop
    running = True
    while running:
        dt = clock.tick(settings.FPS) / 1000.0

        # Event handling
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue

            # ESC-Handling (hat Priorität)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    # Wenn Save-Menü aktiv ist, zurück zum Pause-Menü
                    if save_menu.active:
                        save_menu.active = False
                        pause_menu.active = True
                    # Wenn Sub-Menü aktiv ist, zurück zum Settings-Menü
                    elif audio_settings.active:
                        audio_settings.active = False
                        settings_menu.active = True
                    elif graphics_settings.active:
                        graphics_settings.active = False
                        settings_menu.active = True
                    elif controls_settings.active:
                        controls_settings.active = False
                        settings_menu.active = True
                    # Wenn Settings-Menü aktiv ist, zurück zum Pause-Menü
                    elif settings_menu.active:
                        settings_menu.active = False
                        pause_menu.active = True
                    # Sonst Pause-Menü togglen
                    else:
                        pause_menu.toggle()
                    continue  # Überspringe weitere Event-Verarbeitung für ESC

            # Save-Menü Events (höchste Priorität)
            if save_menu.active:
                result = save_menu.handle_event(event)
                if result == "Back":
                    save_menu.active = False
                    pause_menu.active = True
                elif result and result.startswith("slot_"):
                    # TODO: Implement save logic
                    print(f"[Main] Save to {result}")
            # Sub-Menü Events
            elif audio_settings.active:
                result = audio_settings.handle_event(event)
                if result == "back":
                    audio_settings.active = False
                    settings_menu.active = True
            elif graphics_settings.active:
                result = graphics_settings.handle_event(event)
                if result == "back":
                    graphics_settings.active = False
                    settings_menu.active = True
            elif controls_settings.active:
                result = controls_settings.handle_event(event)
                if result == "back":
                    controls_settings.active = False
                    settings_menu.active = True
            # Settings-Menü Events
            elif settings_menu.active:
                result = settings_menu.handle_event(event)
                if result == "back":
                    settings_menu.active = False
                    pause_menu.active = True
                elif result == "audio":
                    settings_menu.active = False
                    audio_settings.active = True
                elif result == "graphics":
                    settings_menu.active = False
                    graphics_settings.active = True
                elif result == "controls":
                    settings_menu.active = False
                    controls_settings.active = True
            # Pause-Menü Events (Option 3 behandelt self.active bereits intern)
            elif pause_menu.active:
                result = pause_menu.handle_event(event)
                if result == "Quit":
                    running = False
                elif result == "Continue":
                    pass  # Menü wurde bereits durch toggle() geschlossen
                elif result == "Settings":
                    pass  # settings_menu.active wurde bereits in pause_menu gesetzt
                elif result == "Save":
                    pass  # save_menu.active wurde bereits in pause_menu gesetzt
            else:
                # Normale Input-Events nur wenn nicht pausiert
                input_handler.handle_event(event)

        # Update (nur wenn kein Menü aktiv ist)
        if not (pause_menu.active or settings_menu.active or save_menu.active or
                audio_settings.active or graphics_settings.active or controls_settings.active):
            input_handler.update()
            all_sprites.update(dt)
            camera.update(dt)
            world.update(player.rect.center)

        # Render
        screen.fill(settings.COLOR_BG)
        world.draw_grid(screen, camera)
        for sprite in all_sprites:
            screen.blit(sprite.image, camera.apply(sprite))

        # Debug info (nur wenn kein Menü aktiv ist)
        if not (pause_menu.active or settings_menu.active or save_menu.active or
                audio_settings.active or graphics_settings.active or controls_settings.active):
            font = pygame.font.Font(None, 24)
            fps_text = font.render(f"FPS: {int(clock.get_fps())}", True, (255, 255, 255))
            pos_text = font.render(f"Pos: ({player.rect.x}, {player.rect.y})", True, (255, 255, 255))
            screen.blit(fps_text, (10, 10))
            screen.blit(pos_text, (10, 35))

        # Menüs zeichnen (Prioritätsreihenfolge: Sub-Menüs > Settings > Save > Pause)
        if audio_settings.active:
            audio_settings.draw(screen)
        elif graphics_settings.active:
            graphics_settings.draw(screen)
        elif controls_settings.active:
            controls_settings.draw(screen)
        elif settings_menu.active:
            settings_menu.draw(screen)
        elif save_menu.active:
            save_menu.draw(screen)
        elif pause_menu.active:
            pause_menu.draw(screen)

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
