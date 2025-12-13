import pygame
from core import settings
from ui.graphics_settings import GraphicsSettings
from ui.audio_settings import AudioSettings
from ui.controls_settings import ControlsSettings

class SettingsMenu:
    """Settings Menu with submenus for Graphics, Audio, and Controls"""
    
    def __init__(self):
        self.active = False
        self.font = pygame.font.Font(None, 48)
        self.button_font = pygame.font.Font(None, 36)
        
        # Initialize submenus
        self.graphics_menu = GraphicsSettings()
        self.audio_menu = AudioSettings()
        self.controls_menu = ControlsSettings()
        self.current_submenu = None
        
        # Define buttons
        button_width = 400
        button_height = 60
        button_spacing = 20
        start_y = 200
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
        
        # ESC key to close Settings Menu
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.toggle()
                return 'back'
        
        # Button click events
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:  # Left click
            for button_name, button_rect in self.buttons.items():
                if button_rect.collidepoint(event.pos):
                    if button_name == "Back":
                        self.toggle()
                        return 'back'
                    elif button_name == "Graphics":
                        self.graphics_menu.toggle()
                        self.current_submenu = self.graphics_menu
                    elif button_name == "Audio":
                        self.audio_menu.toggle()
                        self.current_submenu = self.audio_menu
                    elif button_name == "Controls":
                        self.controls_menu.toggle()
                        self.current_submenu = self.controls_menu
                    return None
        
        return None
    
    def draw(self, surface):
        """Draw Settings Menu"""
        if not self.active:
            return
        
        # If a submenu is active, draw only the submenu
        if self.current_submenu:
            self.current_submenu.draw(surface)
            return
        
        # Semi-transparent overlay
        overlay = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        surface.blit(overlay, (0, 0))
        
        # Title
        title_text = self.font.render("EINSTELLUNGEN", True, (255, 255, 255))
        title_rect = title_text.get_rect(center=(settings.SCREEN_WIDTH // 2, 100))
        surface.blit(title_text, title_rect)
        
        # Buttons
        mouse_pos = pygame.mouse.get_pos()
        for button_name, button_rect in self.buttons.items():
            # Button highlight on hover
            if button_rect.collidepoint(mouse_pos):
                pygame.draw.rect(surface, (100, 100, 100), button_rect)
            else:
                pygame.draw.rect(surface, (50, 50, 50), button_rect)
            
            # Button border
            pygame.draw.rect(surface, (200, 200, 200), button_rect, 2)
            
            # Button text
            text = self.button_font.render(button_name, True, (255, 255, 255))
            text_rect = text.get_rect(center=button_rect.center)
            surface.blit(text, text_rect)
