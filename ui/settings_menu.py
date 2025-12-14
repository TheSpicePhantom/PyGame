import pygame
from core import settings
from config.settings_manager import settings_manager
from ui.graphics_settings import GraphicsSettings
from ui.audio_settings import AudioSettings
from ui.controls_settings import ControlsSettings

class SettingsMenu:
    """Settings Menu with submenus for Graphics, Audio, and Controls"""

    def __init__(self):
        self.active = False
        
        # Initialize submenus
        self.graphics_menu = GraphicsSettings()
        self.audio_menu = AudioSettings()
        self.controls_menu = ControlsSettings()
        self.current_submenu = None
        
        # Set parent reference for UI refresh
        self.graphics_menu.parent = self
        self.audio_menu.parent = self
        self.controls_menu.parent = self
        
        # Reference to pause menu and save menu (will be set externally)
        self.pause_menu = None
        self.save_menu = None
        
        # Initialize UI elements
        self._init_ui()
    
    def _init_ui(self):
        """Initialize/reinitialize all UI elements with current scale"""
        # Fonts
        self.font = settings_manager.scale_font_size(48)
        self.button_font = settings_manager.scale_font_size(36)

        # Define buttons (scale dimensions, center on unscaled screen)
        button_width = settings_manager.scale_value(400)
        button_height = settings_manager.scale_value(60)
        button_spacing = settings_manager.scale_value(20)
        start_y = settings_manager.scale_value(200)
        center_x = settings.SCREEN_WIDTH // 2

        self.buttons = {
            "Graphics": pygame.Rect(
                center_x - button_width // 2,
                start_y,
                button_width,
                button_height
            ),
            "Audio": pygame.Rect(
                center_x - button_width // 2,
                start_y + (button_height + button_spacing),
                button_width,
                button_height
            ),
            "Controls": pygame.Rect(
                center_x - button_width // 2,
                start_y + 2 * (button_height + button_spacing),
                button_width,
                button_height
            ),
            "Back": pygame.Rect(
                center_x - button_width // 2,
                start_y + 3 * (button_height + button_spacing),
                button_width,
                button_height
            ),
        }
    
    def refresh_all_ui(self):
        """Refresh UI for all menus after scale change"""
        self._init_ui()
        self.graphics_menu._init_ui()
        self.audio_menu._init_ui()
        self.controls_menu._init_ui()
        
        # Refresh parent menus if they exist
        if self.pause_menu:
            self.pause_menu._init_ui()
        if self.save_menu:
            self.save_menu._init_ui()

    def toggle(self):
        """Toggle Settings Menu on/off"""
        self.active = not self.active
        if not self.active:
            # Close any open submenus when closing main settings
            self.current_submenu = None
            self.graphics_menu.active = False
            self.audio_menu.active = False
            self.controls_menu.active = False
        return self.active

    def handle_event(self, event):
        """Event handling for Settings Menu"""
        if not self.active:
            return None

        # If a submenu is active, forward events to it
        if self.current_submenu:
            result = self.current_submenu.handle_event(event)
            if result == 'back':
                self.current_submenu = None
            return None

        # Main settings menu event handling
        if event.type == pygame.MOUSEBUTTONDOWN:
            mouse_pos = event.pos

            for button_name, button_rect in self.buttons.items():
                if button_rect.collidepoint(mouse_pos):
                    if button_name == "Graphics":
                        self.current_submenu = self.graphics_menu
                        self.graphics_menu.active = True
                    elif button_name == "Audio":
                        self.current_submenu = self.audio_menu
                        self.audio_menu.active = True
                    elif button_name == "Controls":
                        self.current_submenu = self.controls_menu
                        self.controls_menu.active = True
                    elif button_name == "Back":
                        self.active = False
                        # Reactivate pause menu when going back
                        if self.pause_menu:
                            self.pause_menu.active = True
                        return 'back'

        return None

    def draw(self, screen):
        """Draw the Settings Menu"""
        if not self.active:
            return

        # If a submenu is active, draw it instead
        if self.current_submenu:
            self.current_submenu.draw(screen)
            return

        # Draw semi-transparent background
        overlay = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, 0))

        # Draw title
        title_text = self.font.render("Settings", True, (255, 255, 255))
        title_rect = title_text.get_rect(center=(settings.SCREEN_WIDTH // 2, settings_manager.scale_value(100)))
        screen.blit(title_text, title_rect)

        # Draw buttons
        mouse_pos = pygame.mouse.get_pos()
        for button_name, button_rect in self.buttons.items():
            # Highlight button if mouse is over it
            if button_rect.collidepoint(mouse_pos):
                pygame.draw.rect(screen, (100, 100, 100), button_rect)
            else:
                pygame.draw.rect(screen, (50, 50, 50), button_rect)

            pygame.draw.rect(screen, (200, 200, 200), button_rect, 2)

            # Draw button text
            button_text = self.button_font.render(button_name, True, (255, 255, 255))
            text_rect = button_text.get_rect(center=button_rect.center)
            screen.blit(button_text, text_rect)
