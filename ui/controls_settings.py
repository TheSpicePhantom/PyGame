"""
UI: Tastenbelegung-Einstellungen
"""
import pygame
import json
import os
from core import settings
from config.settings_manager import settings_manager


class ControlsSettings:
    """Tastenbelegung Einstellungen Menu"""

    def __init__(self):
        self.active = False
        self.font = settings_manager.scale_font_size(32)
        self.button_font = settings_manager.scale_font_size(24)
        self.label_font = settings_manager.scale_font_size(28)

        # Load Einstellungen
        self.config_path = os.path.join('config', 'hotkeys.json')
        self.load_hotkeys()

        # Keybinding Einstellungen
        self.keybindings = [
            ('Move Up', 'KEY_MOVE_UP', self.hotkeys.get('KEY_MOVE_UP', settings.KEY_MOVE_UP)),
            ('Move Down', 'KEY_MOVE_DOWN', self.hotkeys.get('KEY_MOVE_DOWN', settings.KEY_MOVE_DOWN)),
            ('Move Left', 'KEY_MOVE_LEFT', self.hotkeys.get('KEY_MOVE_LEFT', settings.KEY_MOVE_LEFT)),
            ('Move Right', 'KEY_MOVE_RIGHT', self.hotkeys.get('KEY_MOVE_RIGHT', settings.KEY_MOVE_RIGHT)),
            ('Build Mode', 'KEY_BUILD_MODE', self.hotkeys.get('KEY_BUILD_MODE', settings.KEY_BUILD_MODE)),
            ('Rotate', 'KEY_ROTATE', self.hotkeys.get('KEY_ROTATE', settings.KEY_ROTATE)),
        ]

        self.waiting_for_key = None  # Track which keybinding is being remapped

        # Buttons
        button_width = settings_manager.scale_value(200)
        button_height = settings_manager.scale_value(50)
        self.back_button = settings_manager.scale_rect(pygame.Rect(
            settings.SCREEN_WIDTH // 2 - button_width // 2,
            settings_manager.scale_value(850),
            button_width,
            button_height
        ))

        self.reset_button = settings_manager.scale_rect(pygame.Rect(
            settings.SCREEN_WIDTH // 2 - button_width // 2,
            settings_manager.scale_value(770),
            button_width,
            button_height
        ))

    def load_hotkeys(self):
        """Lädt Hotkey Einstellungen aus JSON"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    self.hotkeys = json.load(f)
            else:
                self.hotkeys = {}
        except Exception:
            self.hotkeys = {}

    def save_hotkeys(self):
        """Speichert Hotkey Einstellungen zu JSON"""
        try:
            os.makedirs('config', exist_ok=True)
            hotkeys_to_save = {}
            for label, key_name, key_code in self.keybindings:
                hotkeys_to_save[key_name] = key_code
            
            with open(self.config_path, 'w') as f:
                json.dump(hotkeys_to_save, f, indent=2)
        except Exception as e:
            print(f"Error saving hotkeys: {e}")

    def reset_to_defaults(self):
        """Setzt alle Tastenbelegungen auf Standardwerte zurück"""
        self.keybindings = [
            ('Move Up', 'KEY_MOVE_UP', settings.KEY_MOVE_UP),
            ('Move Down', 'KEY_MOVE_DOWN', settings.KEY_MOVE_DOWN),
            ('Move Left', 'KEY_MOVE_LEFT', settings.KEY_MOVE_LEFT),
            ('Move Right', 'KEY_MOVE_RIGHT', settings.KEY_MOVE_RIGHT),
            ('Build Mode', 'KEY_BUILD_MODE', settings.KEY_BUILD_MODE),
            ('Rotate', 'KEY_ROTATE', settings.KEY_ROTATE),
        ]
        self.save_hotkeys()

    def get_key_name(self, key_code):
        """Konvertiert pygame Key Code zu lesbarem Namen"""
        return pygame.key.name(key_code).upper()

    def handle_event(self, event):
        """Handle Input Events"""
        if not self.active:
            return

        if event.type == pygame.KEYDOWN:
            if self.waiting_for_key is not None:
                # Remap the key
                label, key_name, old_key = self.keybindings[self.waiting_for_key]
                self.keybindings[self.waiting_for_key] = (label, key_name, event.key)
                self.save_hotkeys()
                self.waiting_for_key = None
            elif event.key == pygame.K_ESCAPE:
                self.active = False
                return

        if event.type == pygame.MOUSEBUTTONDOWN:
            mouse_pos = pygame.mouse.get_pos()

            # Check keybinding buttons
            start_y = settings_manager.scale_value(200)
            button_height = settings_manager.scale_value(60)
            spacing = settings_manager.scale_value(15)
            button_width = settings_manager.scale_value(150)
            
            for i in range(len(self.keybindings)):
                y_pos = start_y + i * (button_height + spacing)
                key_button_rect = pygame.Rect(
                    settings.SCREEN_WIDTH // 2 + settings_manager.scale_value(50),
                    y_pos,
                    button_width,
                    button_height
                )
                if key_button_rect.collidepoint(mouse_pos):
                    self.waiting_for_key = i
                    return

            # Check reset button
            if self.reset_button.collidepoint(mouse_pos):
                self.reset_to_defaults()
                return

            # Check back button
            if self.back_button.collidepoint(mouse_pos):
                self.active = False
                return

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
        title_text = self.font.render('Tastenbelegung', True, (255, 255, 255))
        title_rect = title_text.get_rect(center=(settings.SCREEN_WIDTH // 2, settings_manager.scale_value(100)))
        screen.blit(title_text, title_rect)

        # Draw keybindings
        start_y = settings_manager.scale_value(200)
        button_height = settings_manager.scale_value(60)
        spacing = settings_manager.scale_value(15)
        button_width = settings_manager.scale_value(150)

        for i, (label, key_name, key_code) in enumerate(self.keybindings):
            y_pos = start_y + i * (button_height + spacing)
            
            # Draw label
            label_text = self.label_font.render(label, True, (200, 200, 200))
            label_rect = label_text.get_rect(right=settings.SCREEN_WIDTH // 2 - settings_manager.scale_value(70), centery=y_pos + button_height // 2)
            screen.blit(label_text, label_rect)

            # Draw key button
            key_button_rect = pygame.Rect(
                settings.SCREEN_WIDTH // 2 + settings_manager.scale_value(50),
                y_pos,
                button_width,
                button_height
            )
            
            # Highlight if waiting for key press
            if self.waiting_for_key == i:
                color = (100, 150, 255)
                key_text = self.button_font.render('Press key...', True, (255, 255, 255))
            else:
                mouse_pos = pygame.mouse.get_pos()
                color = (80, 80, 100) if key_button_rect.collidepoint(mouse_pos) else (50, 50, 70)
                key_display = self.get_key_name(key_code)
                key_text = self.button_font.render(key_display, True, (255, 255, 255))
            
            pygame.draw.rect(screen, color, key_button_rect)
            pygame.draw.rect(screen, (100, 100, 120), key_button_rect, settings_manager.scale_value(2))
            key_text_rect = key_text.get_rect(center=key_button_rect.center)
            screen.blit(key_text, key_text_rect)

        # Draw reset button
        mouse_pos = pygame.mouse.get_pos()
        reset_color = (100, 50, 50) if self.reset_button.collidepoint(mouse_pos) else (70, 30, 30)
        pygame.draw.rect(screen, reset_color, self.reset_button)
        pygame.draw.rect(screen, (150, 70, 70), self.reset_button, settings_manager.scale_value(2))
        reset_text = self.button_font.render('Reset to Defaults', True, (255, 255, 255))
        reset_text_rect = reset_text.get_rect(center=self.reset_button.center)
        screen.blit(reset_text, reset_text_rect)

        # Draw back button
        back_color = (50, 50, 80) if self.back_button.collidepoint(mouse_pos) else (30, 30, 60)
        pygame.draw.rect(screen, back_color, self.back_button)
        pygame.draw.rect(screen, (100, 100, 150), self.back_button, settings_manager.scale_value(2))
        back_text = self.button_font.render('< Back', True, (255, 255, 255))
        back_text_rect = back_text.get_rect(center=self.back_button.center)
        screen.blit(back_text, back_text_rect)
