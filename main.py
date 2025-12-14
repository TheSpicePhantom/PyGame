"""
Hauptdatei: Startet das Top-Down Factorio-Style Spiel
"""
import pygame
import os
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


def get_desktop_resolution():
    """Get desktop resolution using OS-specific method"""
    if os.name == 'nt':  # Windows
        try:
            import ctypes
            user32 = ctypes.windll.user32
            return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        except:
            pass
    # Fallback to pygame
    pygame.display.init()
    display_info = pygame.display.Info()
    return display_info.current_w, display_info.current_h


def apply_display_mode(mode, is_initial=False):
    """Apply display mode change and return new screen surface
    
    Args:
        mode: Display mode ('windowed', 'fullscreen_window', 'fullscreen')
        is_initial: If True, this is the first window creation (pygame not yet initialized)
    """
    # Save default windowed size
    default_width = 1920
    default_height = 1080
    
    # Set SDL environment variables BEFORE creating the window
    if mode == "fullscreen_window":
        # For borderless, position at top-left (0,0)
        os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'
        os.environ['SDL_VIDEO_CENTERED'] = '0'
    elif mode == "windowed":
        # For windowed, center the window
        if 'SDL_VIDEO_WINDOW_POS' in os.environ:
            del os.environ['SDL_VIDEO_WINDOW_POS']
        os.environ['SDL_VIDEO_CENTERED'] = '1'
    
    # Now create the window
    if mode == "fullscreen":
        # True fullscreen with native resolution
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        print(f"[Display] Fullscreen mode: {screen.get_width()}x{screen.get_height()}")
    elif mode == "fullscreen_window":
        # Borderless windowed fullscreen - get desktop resolution
        desktop_width, desktop_height = get_desktop_resolution()
        print(f"[Display] Desktop resolution: {desktop_width}x{desktop_height}")
        screen = pygame.display.set_mode((desktop_width, desktop_height), pygame.NOFRAME)
        print(f"[Display] Borderless mode: {screen.get_width()}x{screen.get_height()} at (0,0)")
    else:  # windowed
        # Regular windowed mode with default resolution
        screen = pygame.display.set_mode((default_width, default_height))
        print(f"[Display] Windowed mode: {default_width}x{default_height} (centered)")
    
    # Update settings module with actual screen size
    actual_width, actual_height = screen.get_size()
    settings.SCREEN_WIDTH = actual_width
    settings.SCREEN_HEIGHT = actual_height
    
    return screen


def main():
    """Hauptfunktion"""
    pygame.init()
    
    # Load display mode from settings
    from config.settings_manager import settings_manager
    settings_manager.load_settings()
    initial_mode = settings_manager.graphics.get('display_mode', 'windowed')
    
    screen = apply_display_mode(initial_mode, is_initial=True)
    pygame.display.set_caption("PyGame - Factorio Style")
    clock = pygame.time.Clock()
    
    # Update settings to reflect actual screen size
    actual_width, actual_height = screen.get_size()
    print(f"[Main] Screen initialized: {actual_width}x{actual_height}")

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
    save_menu = SaveMenu()

    # Menü-Referenzen setzen (wichtig für Option 3 und UI refresh)
    pause_menu.set_settings_menu(settings_menu)
    pause_menu.set_save_menu(save_menu)
    
    # Set references for UI refresh when scale changes
    settings_menu.pause_menu = pause_menu
    settings_menu.save_menu = save_menu
    
    # Use the submenu instances from settings_menu (they're already created)
    audio_settings = settings_menu.audio_menu
    graphics_settings = settings_menu.graphics_menu
    controls_settings = settings_menu.controls_menu

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
                    # Wenn Settings-Menü aktiv ist (inkl. aller Submenüs), zurück zum Pause-Menü
                    elif settings_menu.active:
                        settings_menu.active = False
                        # Close any open submenus
                        settings_menu.current_submenu = None
                        settings_menu.graphics_menu.active = False
                        settings_menu.audio_menu.active = False
                        settings_menu.controls_menu.active = False
                        pause_menu.active = True
                    # Sonst Pause-Menü togglen
                    else:
                        pause_menu.toggle()
                    continue  # Überspringe weitere Event-Verarbeitung für ESC
                
                # F11 für Vollbild-Toggle (zwischen Borderless und Windowed)
                elif event.key == pygame.K_F11:
                    if graphics_settings.display_mode == "windowed":
                        graphics_settings.display_mode = "fullscreen_window"
                    else:
                        graphics_settings.display_mode = "windowed"
                    graphics_settings.save_settings()
                    screen = apply_display_mode(graphics_settings.display_mode)
                    # Reinitialize all UI elements with new screen size
                    pause_menu._init_ui()
                    settings_menu.refresh_all_ui()
                    # Update camera offsets for new screen size
                    camera.update_screen_size()
                    continue

            # Save-Menü Events (höchste Priorität)
            if save_menu.active:
                result = save_menu.handle_event(event)
                if result == "Back":
                    save_menu.active = False
                    pause_menu.active = True
                elif result and result.startswith("slot_"):
                    # TODO: Implement save logic
                    print(f"[Main] Save to {result}")
            # Settings-Menü Events (verwaltet Submenüs intern)
            elif settings_menu.active:
                result = settings_menu.handle_event(event)
                if result == "back":
                    settings_menu.active = False
                    pause_menu.active = True
                elif result == "display_mode_changed":
                    # Apply display mode change
                    screen = apply_display_mode(graphics_settings.display_mode)
                    # Reinitialize all UI elements with new screen size
                    pause_menu._init_ui()
                    settings_menu.refresh_all_ui()
                    # Update camera offsets for new screen size
                    camera.update_screen_size()
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
        if not (pause_menu.active or settings_menu.active or save_menu.active):
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
        if not (pause_menu.active or settings_menu.active or save_menu.active):
            font = pygame.font.Font(None, 24)
            fps_text = font.render(f"FPS: {int(clock.get_fps())}", True, (255, 255, 255))
            pos_text = font.render(f"Pos: ({player.rect.x}, {player.rect.y})", True, (255, 255, 255))
            screen.blit(fps_text, (10, 10))
            screen.blit(pos_text, (10, 35))

        # Menüs zeichnen (Prioritätsreihenfolge: Settings > Save > Pause)
        # Settings-Menü zeichnet seine Submenüs automatisch intern
        if settings_menu.active:
            settings_menu.draw(screen)
        elif save_menu.active:
            save_menu.draw(screen)
        elif pause_menu.active:
            pause_menu.draw(screen)

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
