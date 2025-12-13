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

        # Slider-Einstellungen (6 Kanäle)
        slider_width = settings_manager.scale_value(300)
        self.master_slider = self._create_slider(slider_width, 0, 100)
        self.music_slider = self._create_slider(slider_width, 0, 100)
        self.sounds_slider = self._create_slider(slider_width, 0, 100)
        self.machines_slider = self._create_slider(slider_width, 0, 100)
        self.weapons_slider = self._create_slider(slider_width, 0, 100)
        self.build_destroy_slider = self._create_slider(slider_width, 0, 100)
        
        self.dragging_slider = None  # Track which slider is being dragged

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
                self.sounds_volume = audio_data.get('sounds_volume', 100)
                self.machines_volume = audio_data.get('machines_volume', 100)
                self.weapons_volume = audio_data.get('weapons_volume', 100)
                self.build_destroy_volume = audio_data.get('build_destroy_volume', 100)
        except:
            self.master_volume = 100
            self.music_volume = 100
            self.sounds_volume = 100
            self.machines_volume = 100
            self.weapons_volume = 100
            self.build_destroy_volume = 100

    def save_settings(self):
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            
            if 'audio' not in data:
                data['audio'] = {}
            
            data['audio']['master_volume'] = self.master_volume
            data['audio']['music_volume'] = self.music_volume
            data['audio']['sounds_volume'] = self.sounds_volume
            data['audio']['machines_volume'] = self.machines_volume
            data['audio']['weapons_volume'] = self.weapons_volume
            data['audio']['build_destroy_volume'] = self.build_destroy_volume
            
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

    def _handle_slider_interaction(self, mouse_pos, slider, volume_attr, y_pos):
        """Handle click/drag for a slider"""
        slider_rect = pygame.Rect(slider['x'], y_pos - settings_manager.scale_value(12),
                                  slider['width'], settings_manager.scale_value(24))
        if slider_rect.collidepoint(mouse_pos):
            relative_x = mouse_pos[0] - slider['x']
            new_value = int((relative_x / slider['width']) * 100)
            new_value = max(0, min(100, new_value))
            setattr(self, volume_attr, new_value)
            return True
        return False

    def handle_event(self, event):
        if not self.active:
            return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse_pos = event.pos
            
            # Back button
            if self.back_button.collidepoint(mouse_pos):
                self.save_settings()
                self.active = False
                return 'back'
            
            # Check all sliders
            sliders_data = [
                (self.master_slider, 'master_volume', settings_manager.scale_value(130)),
                (self.music_slider, 'music_volume', settings_manager.scale_value(190)),
                (self.sounds_slider, 'sounds_volume', settings_manager.scale_value(250)),
                (self.machines_slider, 'machines_volume', settings_manager.scale_value(310)),
                (self.weapons_slider, 'weapons_volume', settings_manager.scale_value(370)),
                (self.build_destroy_slider, 'build_destroy_volume', settings_manager.scale_value(430)),
            ]
            
            for slider, volume_attr, y_pos in sliders_data:
                if self._handle_slider_interaction(mouse_pos, slider, volume_attr, y_pos):
                    self.dragging_slider = (slider, volume_attr, y_pos)
                    break
        
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging_slider = None
        
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging_slider:
                slider, volume_attr, y_pos = self.dragging_slider
                self._handle_slider_interaction(event.pos, slider, volume_attr, y_pos)

        return None

    def _draw_slider(self, screen, label, volume, slider, y_pos):
        """Draw a single slider"""
        # Label
        label_text = self.label_font.render(f'{label}: {volume}%', True, (255, 255, 255))
        screen.blit(label_text, (settings.SCREEN_WIDTH // 2 - settings_manager.scale_value(150), 
                                 y_pos - settings_manager.scale_value(30)))
        
        # Slider track
        pygame.draw.rect(screen, (100, 100, 100), 
                        (slider['x'], y_pos - settings_manager.scale_value(5), 
                         slider['width'], settings_manager.scale_value(10)))
        
        # Slider handle
        slider_pos = slider['x'] + (volume / 100) * slider['width']
        pygame.draw.circle(screen, (200, 200, 200), (int(slider_pos), y_pos), 
                          settings_manager.scale_value(12))

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

        # Draw all sliders
        self._draw_slider(screen, 'Master Volume', self.master_volume, self.master_slider, settings_manager.scale_value(130))
        self._draw_slider(screen, 'Music', self.music_volume, self.music_slider, settings_manager.scale_value(190))
        self._draw_slider(screen, 'Sounds', self.sounds_volume, self.sounds_slider, settings_manager.scale_value(250))
        self._draw_slider(screen, 'Machines', self.machines_volume, self.machines_slider, settings_manager.scale_value(310))
        self._draw_slider(screen, 'Weapons', self.weapons_volume, self.weapons_slider, settings_manager.scale_value(370))
        self._draw_slider(screen, 'Build & Destroy', self.build_destroy_volume, self.build_destroy_slider, settings_manager.scale_value(430))

        # Back button
        mouse_pos = pygame.mouse.get_pos()
        color = (100, 100, 100) if self.back_button.collidepoint(mouse_pos) else (50, 50, 50)
        pygame.draw.rect(screen, color, self.back_button)
        pygame.draw.rect(screen, (200, 200, 200), self.back_button, 2)
        back_text = self.button_font.render('< Back', True, (255, 255, 255))
        back_text_rect = back_text.get_rect(center=self.back_button.center)
        screen.blit(back_text, back_text_rect)
