""" 
UI: Audio-Einstellungen
"""
import pygame
import json
import os
from core import settings
from config.settings_manager import settings_manager

class AudioSettings:
    """Audio Einstellungen Menu"""

    def __init__(self):
        self.active = False
        self.font = settings_manager.scale_font_size(42)
        self.button_font = settings_manager.scale_font_size(32)
        self.label_font = settings_manager.scale_font_size(28)

        # Lade Einstellungen
        self.config_path = os.path.join('config', 'user_settings.json')
        self.load_settings()

        # Slider-Einstellungen
        self.master_volume_slider = self._create_slider(settings_manager.scale_value(300), 0, settings_manager.scale_value(100))
        self.music_volume_slider = self._create_slider(settings_manager.scale_value(300), 0, settings_manager.scale_value(100))
        self.sfx_volume_slider = self._create_slider(settings_manager.scale_value(300), 0, settings_manager.scale_value(100))

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
        """Lädt Audio-Einstellungen aus JSON"""
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
                audio_data = data.get('audio', {})
                self.master_volume = audio_data.get('master_volume', 100)
                self.music_volume = audio_data.get('music_volume', 100)
                self.sfx_volume = audio_data.get('sfx_volume', 100)
        except:
            self.master_volume = 100
            self.music_volume = 100
            self.sfx_volume = 100

    def save_settings(self):
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            
            if 'audio' not in data:
                data['audio'] = {}
            
            data['audio']['master_volume'] = self.master_volume
            data['audio']['music_volume'] = self.music_volume
            data['audio']['sfx_volume'] = self.sfx_volume
            
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving audio settings: {e}")

    def _create_slider(self, width, min_val, max_val):
        return {
            'x': settings.SCREEN_WIDTH // 2 - width // 2,
            'y': 0,
            'width': width,
            'min': min_val,
            'max': max_val
        }

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
        """Draw the Audio Settings Menu"""
        if not self.active:
            return

        # Draw semi-transparent background
        overlay = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, 0))

        # Draw title
        title_text = self.font.render("Audio Settings", True, (255, 255, 255))
        title_rect = title_text.get_rect(center=(settings.SCREEN_WIDTH // 2, settings_manager.scale_value(60)))
        screen.blit(title_text, title_rect)

        mouse_pos = pygame.mouse.get_pos()

        # Master volume slider
        y_pos = settings_manager.scale_value(130)
        label = self.label_font.render(f'Master Volume: {self.master_volume}%', True, (255, 255, 255))
        screen.blit(label, (settings.SCREEN_WIDTH // 2 - settings_manager.scale_value(150), y_pos - settings_manager.scale_value(30)))

        slider = self.master_volume_slider
        pygame.draw.rect(screen, (100, 100, 100), (slider['x'], y_pos - settings_manager.scale_value(5), slider['width'], settings_manager.scale_value(10)))
        slider_pos = slider['x'] + (self.master_volume / 100) * slider['width']
        pygame.draw.circle(screen, (200, 200, 200), (int(slider_pos), y_pos), settings_manager.scale_value(12))

        # Music volume slider
        y_pos = settings_manager.scale_value(230)
        label = self.label_font.render(f'Music Volume: {self.music_volume}%', True, (255, 255, 255))
        screen.blit(label, (settings.SCREEN_WIDTH // 2 - settings_manager.scale_value(150), y_pos - settings_manager.scale_value(30)))

        slider = self.music_volume_slider
        pygame.draw.rect(screen, (100, 100, 100), (slider['x'], y_pos - settings_manager.scale_value(5), slider['width'], settings_manager.scale_value(10)))
        slider_pos = slider['x'] + (self.music_volume / 100) * slider['width']
        pygame.draw.circle(screen, (200, 200, 200), (int(slider_pos), y_pos), settings_manager.scale_value(12))

        # SFX volume slider
        y_pos = settings_manager.scale_value(330)
        label = self.label_font.render(f'SFX Volume: {self.sfx_volume}%', True, (255, 255, 255))
        screen.blit(label, (settings.SCREEN_WIDTH // 2 - settings_manager.scale_value(150), y_pos - settings_manager.scale_value(30)))

        slider = self.sfx_volume_slider
        pygame.draw.rect(screen, (100, 100, 100), (slider['x'], y_pos - settings_manager.scale_value(5), slider['width'], settings_manager.scale_value(10)))
        slider_pos = slider['x'] + (self.sfx_volume / 100) * slider['width']
        pygame.draw.circle(screen, (200, 200, 200), (int(slider_pos), y_pos), settings_manager.scale_value(12))

        # Back button
        color = (100, 100, 100) if self.back_button.collidepoint(mouse_pos) else (50, 50, 50)
        pygame.draw.rect(screen, color, self.back_button)
        pygame.draw.rect(screen, (200, 200, 200), self.back_button, 2)

        back_text = self.button_font.render('< Back', True, (255, 255, 255))
        back_text_rect = back_text.get_rect(center=self.back_button.center)
        screen.blit(back_text, back_text_rect)
