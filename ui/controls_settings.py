""" 
UI: Steuerungs-Einstellungen
"""
import pygame
import json
import os
from core import settings
from config.settings_manager import settings_manager

class ControlsSettings:
    """Steuerungs Einstellungen Menu"""

    def __init__(self):
        self.active = False
        self.font = settings_manager.scale_font_size(42)
        self.button_font = settings_manager.scale_font_size(32)
        self.label_font = settings_manager.scale_font_size(28)
        self.small_font = settings_manager.scale_font_size(24)

        # Lade Einstellungen
        self.config_path = os.path.join('config', 'user_settings.json')
        self.load_settings()

        # Standard-Tastenbelegungen
        self.default_keys = {
            'move_up': pygame.K_w,
            'move_down': pygame.K_s,
            'move_left': pygame.K_a,
            'move_right': pygame.K_d,
            'interact': pygame.K_e,
            'inventory': pygame.K_i,
            'pause': pygame.K_ESCAPE,
        }

        # Aktuelle Tastenbelegungen
        self.keys = self.default_keys.copy()

        # Welche Taste wird gerade neu belegt?
        self.rebinding_key = None

        # Buttons
        button_width = settings_manager.scale_value(200)
        button_height = settings_manager.scale_value(50)
        self.back_button = settings_manager.scale_rect(pygame.Rect(
            settings.SCREEN_WIDTH // 2 - button_width // 2,
            settings_manager.scale_value(550),
            button_width,
            button_height
        ))

    def load_settings(self):
        """Lädt Tastenbelegungen aus JSON"""
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
                # TODO: Load keybindings
        except:
            pass

    def save_settings(self):
        try:
            # TODO: Save keybindings to hotkeys.json
            pass
        except Exception as e:
            print(f"Error saving controls settings: {e}")

    def handle_event(self, event):
        if not self.active:
            return None

        if event.type == pygame.MOUSEBUTTONDOWN:
            mouse_pos = event.pos

            if self.back_button.collidepoint(mouse_pos):
                self.save_settings()
                self.active = False
                return 'back'

        return None

    def draw(self, screen):
        """Draw the Controls Settings Menu"""
        if not self.active:
            return

        # Draw semi-transparent background
        overlay = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, 0))

        # Draw title
        title_text = self.font.render("Controls Settings", True, (255, 255, 255))
        title_rect = title_text.get_rect(center=(settings.SCREEN_WIDTH // 2, settings_manager.scale_value(60)))
        screen.blit(title_text, title_rect)

        mouse_pos = pygame.mouse.get_pos()

        # Draw keybindings list
        y_pos = settings_manager.scale_value(130)
        spacing = settings_manager.scale_value(40)
        
        for action, key in self.keys.items():
            # Action name
            action_label = self.label_font.render(f'{action.replace("_", " ").title()}:', True, (255, 255, 255))
            screen.blit(action_label, (settings.SCREEN_WIDTH // 2 - settings_manager.scale_value(200), y_pos))
            
            # Key name
            key_name = pygame.key.name(key)
            key_text = self.label_font.render(key_name.upper(), True, (200, 200, 200))
            screen.blit(key_text, (settings.SCREEN_WIDTH // 2 + settings_manager.scale_value(50), y_pos))
            
            y_pos += spacing

        # Back button
        color = (100, 100, 100) if self.back_button.collidepoint(mouse_pos) else (50, 50, 50)
        pygame.draw.rect(screen, color, self.back_button)
        pygame.draw.rect(screen, (200, 200, 200), self.back_button, 2)

        back_text = self.button_font.render('< Back', True, (255, 255, 255))
        back_text_rect = back_text.get_rect(center=self.back_button.center)
        screen.blit(back_text, back_text_rect)
