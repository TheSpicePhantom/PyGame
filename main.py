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
from world.player_data_manager import PlayerDataManager

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
    
    # Show save menu first for slot selection
    save_menu = SaveMenu()
    save_menu.active = True
    save_menu.mode = "select"  # Start in select mode (not save mode)
    
    selected_slot = None
    world = None
    player = None
    camera = None
    all_sprites = None
    resource_sprites = None
    building_sprites = None
    input_handler = None
    pause_menu = None
    settings_menu = None
    audio_settings = None
    graphics_settings = None
    controls_settings = None
    
    # Game state
    game_initialized = False
    
    # Main menu loop (save slot selection)
    running = True
    while running:
        dt = clock.tick(settings.FPS) / 1000.0
        
        # Event handling
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue
            
            # Save menu slot selection
            if not game_initialized and save_menu.active:
                result = save_menu.handle_event(event)
                if result and result.startswith("slot_"):
                    # Extract slot number
                    selected_slot = int(result.split("_")[1])
                    print(f"[Main] Selected save slot: {selected_slot}")
                    
                    # Initialize game with selected slot
                    # Sprite-Gruppen
                    all_sprites = pygame.sprite.LayeredUpdates()
                    resource_sprites = pygame.sprite.Group()
                    building_sprites = pygame.sprite.Group()
                    
                    # Welt erstellen mit save_slot Parameter
                    world = World(all_sprites, resource_sprites, save_slot=selected_slot)
                    
                    # Initialize PlayerDataManager for save/load
                    player_data_manager = PlayerDataManager(selected_slot)
                    
                    # Input & Player
                    input_handler = InputHandler()
                    
                    # Get player spawn position from save or use default
                    start_world_x, start_world_y = player_data_manager.get_spawn_position()
                    player = Player(
                        pos=(start_world_x, start_world_y),
                        input_handler=input_handler,
                    )
                    all_sprites.add(player, layer=settings.LAYER_PLAYER)
                    
                    # Kamera initialisieren und sofort auf Spielerposition setzen
                    camera = Camera(target=player, lerp_speed=settings.CAMERA_LERP_SPEED)
                    camera.x = player.rect.centerx
                    camera.y = player.rect.centery
                    
                    # Pause-Menü und Settings-Menüs
                    pause_menu = PauseMenu()
                    settings_menu = SettingsMenu()
                    
                    # Menü-Referenzen setzen
                    pause_menu.set_settings_menu(settings_menu)
                    pause_menu.set_save_menu(save_menu)
                    
                    # Set references for UI refresh
                    settings_menu.pause_menu = pause_menu
                    settings_menu.save_menu = save_menu
                    
                    # Use submenu instances
                    audio_settings = settings_menu.audio_menu
                    graphics_settings = settings_menu.graphics_menu
                    controls_settings = settings_menu.controls_menu
                    
                    # Deactivate save menu and start game
                    save_menu.active = False
                    game_initialized = True
                    print(f"[Main] Game initialized with slot {selected_slot}")
                continue
            
            # Game is initialized - handle normal game events
            if game_initialized:
                # ESC-Handling (hat Priorität)
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        # Wenn Save-Menü aktiv ist, zurück zum Pause-Menü
                        if save_menu.active:
                            save_menu.active = False
                            pause_menu.active = True
                        # Wenn Settings-Menü aktiv ist, zurück zum Pause-Menü
                        elif settings_menu.active:
                            settings_menu.active = False
                            settings_menu.current_submenu = None
                            settings_menu.graphics_menu.active = False
                            settings_menu.audio_menu.active = False
                            settings_menu.controls_menu.active = False
                            pause_menu.active = True
                        # Sonst Pause-Menü togglen
                        else:
                            pause_menu.toggle()
                        continue
                    
                    # F11 für Vollbild-Toggle
                    elif event.key == pygame.K_F11:
                        if graphics_settings.display_mode == "windowed":
                            graphics_settings.display_mode = "fullscreen_window"
                        else:
                            graphics_settings.display_mode = "windowed"
                        graphics_settings.save_settings()
                        screen = apply_display_mode(graphics_settings.display_mode)
                        pause_menu._init_ui()
                        settings_menu.refresh_all_ui()
                        camera.update_screen_size()
                        continue
                
                # Save-Menü Events
                if save_menu.active:
                    result = save_menu.handle_event(event)
                    if result == "Back":
                        save_menu.active = False
                        pause_menu.active = True
                    elif result and result.startswith("slot_"):
                        # Save to selected slot
                        slot_num = int(result.split("_")[1])
                        world.save_slot = slot_num
                        world.chunk_manager.save_slot = slot_num
                        
                        # Update player position in world metadata
                        world.chunk_manager.update_player_position(player.rect.centerx, player.rect.centery)
                        
                        # Save all chunks
                        world.chunk_manager.save_all_chunks()
                        
                        # Save player data
                        player_save_manager = PlayerDataManager(slot_num)
                        player_save_manager.save_player(
                            position=(player.rect.centerx, player.rect.centery),
                            inventory={},  # TODO: Implement inventory
                            faction_data={'policies': [], 'allies': [], 'enemies': []}  # TODO: Implement faction
                        )
                        
                        print(f"[Main] Game saved to slot {slot_num} at position ({player.rect.centerx}, {player.rect.centery})")
                        save_menu.active = False
                        pause_menu.active = True
                
                # Settings-Menü Events
                elif settings_menu.active:
                    result = settings_menu.handle_event(event)
                    if result == "back":
                        settings_menu.active = False
                        pause_menu.active = True
                    elif result == "display_mode_changed":
                        screen = apply_display_mode(graphics_settings.display_mode)
                        pause_menu._init_ui()
                        settings_menu.refresh_all_ui()
                        camera.update_screen_size()
                
                # Pause-Menü Events
                elif pause_menu.active:
                    result = pause_menu.handle_event(event)
                    if result == "Quit":
                        running = False
                    elif result == "Continue":
                        pass
                    elif result == "Settings":
                        pass
                    elif result == "Save":
                        save_menu.mode = "save"  # Switch to save mode
                else:
                    # Normale Input-Events
                    input_handler.handle_event(event)
        
        # Update and Render (outside event loop)
        if game_initialized:
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
            
            # Debug info
            if not (pause_menu.active or settings_menu.active or save_menu.active):
                font = pygame.font.Font(None, 24)
                fps_text = font.render(f"FPS: {int(clock.get_fps())}", True, (255, 255, 255))
                pos_text = font.render(f"Pos: ({player.rect.x}, {player.rect.y})", True, (255, 255, 255))
                screen.blit(fps_text, (10, 10))
                screen.blit(pos_text, (10, 35))
            
            # Menüs zeichnen
            if settings_menu.active:
                settings_menu.draw(screen)
            elif save_menu.active:
                save_menu.draw(screen)
            elif pause_menu.active:
                pause_menu.draw(screen)
        else:
            # Still in save slot selection
            screen.fill(settings.COLOR_BG)
            save_menu.draw(screen)
        
        pygame.display.flip()
    
    pygame.quit()

if __name__ == "__main__":
    main()
