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
from world.auto_save import AutoSaveSystem
from analytics.performance_monitor import PerformanceMonitor
from analytics.logger import PerformanceLogger
from view.modern_gl_renderer import ModernGLRenderer
import moderngl
import time

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

def apply_display_mode(mode, is_initial=False, use_opengl=True):
    """Apply display mode change and return new screen surface
    
    Args:
        mode: Display mode ('windowed', 'fullscreen_window', 'fullscreen')
        is_initial: If True, this is the first window creation (pygame not yet initialized)
        use_opengl: If True, create OpenGL context for ModernGL
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
    
    # OpenGL flags for ModernGL
    opengl_flags = pygame.DOUBLEBUF | pygame.OPENGL if use_opengl else 0
    
    # Now create the window
    if mode == "fullscreen":
        # True fullscreen with native resolution
        flags = pygame.FULLSCREEN | opengl_flags if use_opengl else pygame.FULLSCREEN
        screen = pygame.display.set_mode((0, 0), flags)
        print(f"[Display] Fullscreen mode: {screen.get_width()}x{screen.get_height()}")
    elif mode == "fullscreen_window":
        # Borderless windowed fullscreen - get desktop resolution
        desktop_width, desktop_height = get_desktop_resolution()
        print(f"[Display] Desktop resolution: {desktop_width}x{desktop_height}")
        flags = pygame.NOFRAME | opengl_flags if use_opengl else pygame.NOFRAME
        screen = pygame.display.set_mode((desktop_width, desktop_height), flags)
        print(f"[Display] Borderless mode: {screen.get_width()}x{screen.get_height()} at (0,0)")
    else:  # windowed
        # Regular windowed mode with default resolution
        screen = pygame.display.set_mode((default_width, default_height), opengl_flags)
        print(f"[Display] Windowed mode: {default_width}x{default_height} (centered)")
    
    # Update settings module with actual screen size
    actual_width, actual_height = screen.get_size()
    settings.SCREEN_WIDTH = actual_width
    settings.SCREEN_HEIGHT = actual_height
    
    return screen

def main():
    """Hauptfunktion"""
    pygame.init()
    
    # Initialize performance monitoring (always enabled)
    performance_monitor = PerformanceMonitor()
    logger = PerformanceLogger()
    logger.start_log()
    print("[Main] Performance monitoring enabled")
    
    # Load display mode from settings
    from config.settings_manager import settings_manager
    settings_manager.load_settings()
    initial_mode = settings_manager.graphics.get('display_mode', 'windowed')
    
    # Create window WITHOUT OpenGL (ModernGL deaktiviert)
    screen = apply_display_mode(initial_mode, is_initial=True, use_opengl=False)
    pygame.display.set_caption("PyGame - Factorio Style")
    clock = pygame.time.Clock()
    
    # Initialize ModernGL context
    use_modern_gl = False
    modern_gl_renderer = None
    
    # ModernGL temporär deaktiviert - Rendering funktioniert nicht mit Pygame
    # TODO: Framebuffer-Ansatz implementieren oder ModernGL komplett migrieren
    use_modern_gl = False
    modern_gl_renderer = None
    print("[Main] ModernGL temporär deaktiviert - Rendering-Problem mit Pygame")
    print("[Main] Verwende Pygame Rendering (funktioniert)")
    
    # ModernGL Code (deaktiviert):
    # try:
    #     ctx = moderngl.create_context()
    #     print(f"[Main] ModernGL context created successfully")
    #     modern_gl_renderer = ModernGLRenderer(ctx, settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT)
    #     use_modern_gl = True
    #     print("[Main] Using ModernGL for GPU-accelerated rendering")
    # except Exception as e:
    #     import traceback
    #     print(f"[Main] Failed to create ModernGL context: {e}")
    #     traceback.print_exc()
    #     print("[Main] Falling back to Pygame rendering")
    #     modern_gl_renderer = None
    #     use_modern_gl = False
    #     screen = apply_display_mode(initial_mode, is_initial=False, use_opengl=False)
    
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
    
    # Font caching (create once, reuse every frame)
    debug_font = None
    
    # Main menu loop (save slot selection)
    running = True
    while running:
        dt = clock.tick(settings.FPS) / 1000.0
        performance_monitor.start_frame()  # Start frame timing
        
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
                    world = World(all_sprites, resource_sprites, save_slot=selected_slot, performance_monitor=performance_monitor)
                    
                    # Initialize PlayerDataManager for save/load
                    player_data_manager = PlayerDataManager(selected_slot)
                    
                    # Input & Player
                    input_handler = InputHandler()
                    
                    # Get player spawn position from save or use default
                    start_world_x, start_world_y = player_data_manager.get_spawn_position()
                    player = Player(
                        pos=(start_world_x, start_world_y),
                        input_handler=input_handler,
                        performance_monitor=performance_monitor
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
                    
                    # Initialize Auto-Save System
                    def save_game():
                        """Save game function for auto-save"""
                        try:
                            # Update player position in world metadata
                            world.chunk_manager.update_player_position(player.rect.centerx, player.rect.centery)
                            
                            # Save all chunks (async)
                            world.chunk_manager.save_all_chunks()
                            
                            # Save player data
                            player_data_manager.save_player(
                                position=(player.rect.centerx, player.rect.centery),
                                inventory={},  # TODO: Implement inventory
                                faction_data={'policies': [], 'allies': [], 'enemies': []}  # TODO: Implement faction
                            )
                        except Exception as e:
                            print(f"[AutoSave] Error saving game: {e}")
                    
                    def get_player_pos():
                        """Get current player position"""
                        return (player.rect.centerx, player.rect.centery)
                    
                    auto_save = AutoSaveSystem(save_game, get_player_pos)
                    auto_save.start()
                    controls_settings = settings_menu.controls_menu
                    
                    # Deactivate save menu and start game
                    save_menu.active = False
                    game_initialized = True
                    
                    # Initialize cached fonts
                    debug_font = pygame.font.Font(None, 24)
                    
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
                    
                    # F8 für Chunk-Grid Toggle (cycles: Off → Chunks → Chunks+Tiles)
                    elif event.key == pygame.K_F8:
                        world.grid_mode = (world.grid_mode + 1) % 3
                        modes = ["OFF", "Chunks Only", "Chunks + Tiles"]
                        print(f"[Main] Grid overlay: {modes[world.grid_mode]}")
                        continue
                    
                    # F11 für Vollbild-Toggle
                    elif event.key == pygame.K_F11:
                        if graphics_settings.display_mode == "windowed":
                            graphics_settings.display_mode = "fullscreen_window"
                        else:
                            graphics_settings.display_mode = "windowed"
                        graphics_settings.save_settings()
                        screen = apply_display_mode(graphics_settings.display_mode, use_opengl=use_modern_gl)
                        pause_menu._init_ui()
                        settings_menu.refresh_all_ui()
                        camera.update_screen_size()
                        # Refresh visible chunks after screen size change
                        world.refresh_visible_chunks(player.rect.center)
                        # Update ModernGL renderer if using it
                        if use_modern_gl and modern_gl_renderer:
                            modern_gl_renderer.resize(settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT)
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
                        screen = apply_display_mode(graphics_settings.display_mode, use_opengl=use_modern_gl)
                        pause_menu._init_ui()
                        settings_menu.refresh_all_ui()
                        camera.update_screen_size()
                        # Refresh visible chunks after screen size change
                        world.refresh_visible_chunks(player.rect.center)
                        # Update ModernGL renderer if using it
                        if use_modern_gl and modern_gl_renderer:
                            modern_gl_renderer.resize(settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT)
                    elif result == "auto_save_changed":
                        # Restart auto-save with new settings
                        if 'auto_save' in locals():
                            auto_save.stop()
                            auto_save.start()
                
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
                performance_monitor.start_update()
                input_handler.update()
                all_sprites.update(dt)
                camera.update(dt)
                world.update(player.rect.center)
                performance_monitor.end_update()
            
            # Render
            performance_monitor.start_render()
            
            if use_modern_gl:
                # Clear screen with ModernGL (use bright color to see if clearing works)
                # Try a very bright color to verify clearing works
                modern_gl_renderer.clear(0.5, 0.3, 0.8)  # Bright purple background for testing
                
                # Debug: Check if clear worked
                if not hasattr(main, '_clear_debug'):
                    print(f"[Debug] Cleared screen with color (0.5, 0.3, 0.8) - should be bright purple")
                    main._clear_debug = True
                
                # Render test quad EVERY FRAME to verify rendering works
                import numpy as np
                # moderngl is already imported at the top of the file
                
                # Use identity matrices for test
                identity_proj = np.eye(4, dtype=np.float32)
                identity_view = np.eye(4, dtype=np.float32)
                modern_gl_renderer.chunk_program['projection'].write(identity_proj.tobytes())
                modern_gl_renderer.chunk_program['view'].write(identity_view.tobytes())
                
                # Create a simple test quad directly in NDC coordinates
                # Shader expects colors in [0,255] range
                # NDC: (-1,-1) bottom-left, (1,1) top-right
                test_vertices = np.array([
                    # x, y, r, g, b, offset_x, offset_y
                    [-0.5, -0.5, 255.0, 0.0, 0.0, 0.0, 0.0],  # Red quad covering half screen
                    [0.5, -0.5, 255.0, 0.0, 0.0, 0.0, 0.0],
                    [0.5, 0.5, 255.0, 0.0, 0.0, 0.0, 0.0],
                    [-0.5, -0.5, 255.0, 0.0, 0.0, 0.0, 0.0],
                    [0.5, 0.5, 255.0, 0.0, 0.0, 0.0, 0.0],
                    [-0.5, 0.5, 255.0, 0.0, 0.0, 0.0, 0.0],
                ], dtype=np.float32)
                
                test_vbo = modern_gl_renderer.ctx.buffer(test_vertices.tobytes())
                test_vao = modern_gl_renderer.ctx.simple_vertex_array(
                    modern_gl_renderer.chunk_program,
                    test_vbo,
                    'in_position', 'in_color', 'in_chunk_offset'
                )
                
                # Make sure shader is bound and enabled
                modern_gl_renderer.chunk_program.use()
                modern_gl_renderer.ctx.enable(moderngl.BLEND)
                modern_gl_renderer.ctx.disable(moderngl.DEPTH_TEST)
                
                test_vao.render(moderngl.TRIANGLES)
                test_vao.release()
                test_vbo.release()
                
                # Restore projection for actual rendering
                modern_gl_renderer._setup_projection()
                
                if not hasattr(main, '_test_rendered'):
                    print("[Debug] Test quad rendered EVERY FRAME with identity matrices")
                    main._test_rendered = True
                
                # Temporarily use identity view matrix for debugging
                import numpy as np
                identity_view = np.eye(4, dtype=np.float32)
                modern_gl_renderer.chunk_program['view'].write(identity_view.tobytes())
                if modern_gl_renderer.sprite_program:
                    modern_gl_renderer.sprite_program['view'].write(identity_view.tobytes())
                
                # Debug: Print camera position
                if not hasattr(main, '_debug_printed'):
                    print(f"[Debug] Camera position: ({camera.x}, {camera.y})")
                    print(f"[Debug] Screen size: {modern_gl_renderer.screen_width}x{modern_gl_renderer.screen_height}")
                    print(f"[Debug] Player position: ({player.rect.x}, {player.rect.y})")
                    main._debug_printed = True
                
                # Render chunks with ModernGL
                world.draw_grid(screen, camera, modern_gl_renderer)
                
                # Render sprites with ModernGL
                modern_gl_renderer.render_sprites(list(all_sprites), camera)
                
                # Collect UI surfaces for rendering
                ui_surfaces = []
                
                # Debug info
                if not (pause_menu.active or settings_menu.active or save_menu.active):
                    fps_text = debug_font.render(f"FPS: {int(clock.get_fps())}", True, (255, 255, 255))
                    pos_text = debug_font.render(f"Pos: ({player.rect.x}, {player.rect.y})", True, (255, 255, 255))
                    ui_surfaces.append((fps_text, (10, 10)))
                    ui_surfaces.append((pos_text, (10, 35)))
                    
                    if world.grid_mode == 1:
                        grid_text = debug_font.render("Grid: Chunks (F8)", True, (100, 255, 100))
                        ui_surfaces.append((grid_text, (10, 60)))
                    elif world.grid_mode == 2:
                        grid_text = debug_font.render("Grid: Chunks + Tiles (F8)", True, (255, 200, 100))
                        ui_surfaces.append((grid_text, (10, 60)))
                
                # Render UI with ModernGL
                if ui_surfaces:
                    modern_gl_renderer.render_ui(ui_surfaces)
                
                # Chunk grid overlay (temporarily still Pygame - will migrate)
                if world.grid_mode > 0:
                    # For now, skip grid overlay with ModernGL
                    # TODO: Implement grid overlay in ModernGL
                    pass
                
                # Present frame (ModernGL renders directly to OpenGL buffer)
                pygame.display.flip()
                # Debug output (only if game is initialized)
                if game_initialized and not hasattr(main, '_modern_gl_debug_printed'):
                    print(f"[Debug] ModernGL renderer initialized")
                    print(f"[Debug] Screen size: {modern_gl_renderer.screen_width}x{modern_gl_renderer.screen_height}")
                    if player:
                        print(f"[Debug] Player position: ({player.rect.x}, {player.rect.y})")
                    if camera:
                        print(f"[Debug] Camera position: ({camera.x}, {camera.y})")
                    main._modern_gl_debug_printed = True
            else:
                # Fallback to Pygame rendering
                screen.fill(settings.COLOR_BG)
                world.draw_grid(screen, camera)
                
                for sprite in all_sprites:
                    screen.blit(sprite.image, camera.apply(sprite))
                
                # Draw chunk grid overlay (F8) - Pygame fallback
                if world.grid_mode > 0:
                    world.draw_chunk_grid_overlay(screen, camera, player.rect.center)
                
                # Debug info - Pygame fallback
                if not (pause_menu.active or settings_menu.active or save_menu.active):
                    # Use cached font instead of creating new one every frame
                    fps_text = debug_font.render(f"FPS: {int(clock.get_fps())}", True, (255, 255, 255))
                    pos_text = debug_font.render(f"Pos: ({player.rect.x}, {player.rect.y})", True, (255, 255, 255))
                    screen.blit(fps_text, (10, 10))
                    screen.blit(pos_text, (10, 35))
                    
                    # Show chunk grid status
                    if world.grid_mode == 1:
                        grid_text = debug_font.render("Grid: Chunks (F8)", True, (100, 255, 100))
                        screen.blit(grid_text, (10, 60))
                    elif world.grid_mode == 2:
                        grid_text = debug_font.render("Grid: Chunks + Tiles (F8)", True, (255, 200, 100))
                        screen.blit(grid_text, (10, 60))
            
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
        
        performance_monitor.end_render()  # End render timing
        
        # Only flip if not using ModernGL (ModernGL flips automatically)
        if not use_modern_gl:
            pygame.display.flip()
            print("[Main] Frame rendered with Pygame")
        else:
            # ModernGL renders directly to OpenGL buffer, flip to present
            pygame.display.flip()
            print("[Main] Frame rendered with ModernGL")
    
    # Stop auto-save before quitting
    if 'auto_save' in locals():
        auto_save.stop()
    
    # Cleanup ModernGL renderer
    if use_modern_gl and modern_gl_renderer:
        modern_gl_renderer.cleanup()
    
    # Save performance logs before quitting
    print("\n" + "="*60)
    print("PERFORMANCE STATISTICS")
    print("="*60)
    stats = performance_monitor.get_stats()
    performance_monitor.print_stats()
    
    # Save to logger
    logger.log_stats(stats)
    
    # Log chunk load events
    for event in performance_monitor.chunk_load_events:
        logger.log_chunk_load_event(event)
    
    # Log chunk generation events
    for event in performance_monitor.chunk_generation_events:
        logger.log_chunk_generation_event(event)
    
    # Log chunk save events
    for event in performance_monitor.chunk_save_events:
        logger.log_chunk_save_event(event)
    
    # Log movement events
    for event in performance_monitor.movement_events:
        logger.log_movement_event(event)
    
    # Save log file
    logger.save_log()
    
    print("="*60 + "\n")
    
    pygame.quit()

if __name__ == "__main__":
    main()
