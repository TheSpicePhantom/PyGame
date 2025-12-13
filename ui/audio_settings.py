"""
UI: Audio-Einstellungen
"""
import pygame
import json
import os
from core import settings


class AudioSettings:
    """Audio-Einstellungen Menü"""
    
    def __init__(self):
        self.active = False
        self.font = pygame.font.Font(None, 42)
        self.button_font = pygame.font.Font(None, 32)
        self.label_font = pygame.font.Font(None, 28)
        
        # Lade Einstellungen
        self.config_path = os.path.join('config', 'user_settings.json')
        self.load_settings()
        
        # Slider-Einstellungen
        self.master_volume_slider = self._create_slider(300, 0, 100)
        self.music_volume_slider = self._create_slider(300, 0, 100)
        self.sfx_volume_slider = self._create_slider(300, 0, 100)
        
        # Buttons
        button_width = 200
        button_height = 50
        self.back_button = pygame.Rect(
            settings.SCREEN_WIDTH // 2 - button_width // 2,
            550,
            button_width,
            button_height
        )
    
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
        """Speichert Audio-Einstellungen in JSON"""
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
        except:
            data = {}
        
        if 'audio' not in data:
            data['audio'] = {}
        
        data['audio']['master_volume'] = self.master_volume
        data['audio']['music_volume'] = self.music_volume
        data['audio']['sfx_volume'] = self.sfx_volume
        
        # Stelle sicher, dass der config-Ordner existiert
        os.makedirs('config', exist_ok=True)
        
        with open(self.config_path, 'w') as f:
            json.dump(data, f, indent=4)
    
    def _create_slider(self, width, min_val, max_val):
        """Erstellt einen Slider-Dictionary"""
        return {
            'x': settings.SCREEN_WIDTH // 2 - width // 2,
            'width': width,
            'min': min_val,
            'max': max_val
        }
    
    def toggle(self):
        """Schaltet das Menü an/aus"""
        self.active = not self.active
        return self.active
    
    def handle_event(self, event):
        """Event-Handling für Audio-Einstellungen"""
        if not self.active:
            return None
        
        # ESC wird in main.py behandelt
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse_pos = event.pos
            
            # Back-Button
            if self.back_button.collidepoint(mouse_pos):
                self.save_settings()
                self.toggle()
                return 'back'
        
        # Slider-Drag für alle drei Slider
        if pygame.mouse.get_pressed()[0]:
            mouse_x, mouse_y = pygame.mouse.get_pos()
            
            # Master Volume Slider
            slider_y = 150
            if abs(mouse_y - slider_y) < 15:
                slider = self.master_volume_slider
                if slider['x'] <= mouse_x <= slider['x'] + slider['width']:
                    ratio = (mouse_x - slider['x']) / slider['width']
                    self.master_volume = int(slider['min'] + ratio * (slider['max'] - slider['min']))
                    self.master_volume = max(0, min(100, self.master_volume))
            
            # Music Volume Slider
            slider_y = 250
            if abs(mouse_y - slider_y) < 15:
                slider = self.music_volume_slider
                if slider['x'] <= mouse_x <= slider['x'] + slider['width']:
                    ratio = (mouse_x - slider['x']) / slider['width']
                    self.music_volume = int(slider['min'] + ratio * (slider['max'] - slider['min']))
                    self.music_volume = max(0, min(100, self.music_volume))
            
            # SFX Volume Slider
            slider_y = 350
            if abs(mouse_y - slider_y) < 15:
                slider = self.sfx_volume_slider
                if slider['x'] <= mouse_x <= slider['x'] + slider['width']:
                    ratio = (mouse_x - slider['x']) / slider['width']
                    self.sfx_volume = int(slider['min'] + ratio * (slider['max'] - slider['min']))
                    self.sfx_volume = max(0, min(100, self.sfx_volume))
        
        return None
    
    def draw(self, surface):
        """Zeichnet das Audio-Einstellungen Menü"""
        if not self.active:
            return
        
        # Halbtransparentes Overlay
        overlay = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        surface.blit(overlay, (0, 0))
        
        # Titel
        title_text = self.font.render('AUDIO-EINSTELLUNGEN', True, (255, 255, 255))
        title_rect = title_text.get_rect(center=(settings.SCREEN_WIDTH // 2, 60))
        surface.blit(title_text, title_rect)
        
        mouse_pos = pygame.mouse.get_pos()
        
        # Master Volume Slider
        y_pos = 150
        label = self.label_font.render(f'Master-Lautstärke: {self.master_volume}%', True, (255, 255, 255))
        surface.blit(label, (settings.SCREEN_WIDTH // 2 - 150, y_pos - 30))
        
        slider = self.master_volume_slider
        pygame.draw.rect(surface, (100, 100, 100), (slider['x'], y_pos - 5, slider['width'], 10))
        slider_pos = slider['x'] + (self.master_volume / 100) * slider['width']
        pygame.draw.circle(surface, (200, 200, 200), (int(slider_pos), y_pos), 12)
        
        # Music Volume Slider
        y_pos = 250
        label = self.label_font.render(f'Musik-Lautstärke: {self.music_volume}%', True, (255, 255, 255))
        surface.blit(label, (settings.SCREEN_WIDTH // 2 - 150, y_pos - 30))
        
        slider = self.music_volume_slider
        pygame.draw.rect(surface, (100, 100, 100), (slider['x'], y_pos - 5, slider['width'], 10))
        slider_pos = slider['x'] + (self.music_volume / 100) * slider['width']
        pygame.draw.circle(surface, (200, 200, 200), (int(slider_pos), y_pos), 12)
        
        # SFX Volume Slider
        y_pos = 350
        label = self.label_font.render(f'SFX-Lautstärke: {self.sfx_volume}%', True, (255, 255, 255))
        surface.blit(label, (settings.SCREEN_WIDTH // 2 - 150, y_pos - 30))
        
        slider = self.sfx_volume_slider
        pygame.draw.rect(surface, (100, 100, 100), (slider['x'], y_pos - 5, slider['width'], 10))
        slider_pos = slider['x'] + (self.sfx_volume / 100) * slider['width']
        pygame.draw.circle(surface, (200, 200, 200), (int(slider_pos), y_pos), 12)
        
        # Back-Button
        color = (100, 100, 100) if self.back_button.collidepoint(mouse_pos) else (50, 50, 50)
        pygame.draw.rect(surface, color, self.back_button)
        pygame.draw.rect(surface, (200, 200, 200), self.back_button, 2)
        
        back_text = self.button_font.render('Zurück', True, (255, 255, 255))
        back_text_rect = back_text.get_rect(center=self.back_button.center)
        surface.blit(back_text, back_text_rect)

