import pygame
import json
import os
from config.settings import SCREEN_WIDTH, SCREEN_HEIGHT

class GraphicsSettings:
    """Graphics Settings submenu"""
    
    def __init__(self):
        self.active = False
        self.font = pygame.font.Font(None, 42)
        self.button_font = pygame.font.Font(None, 32)
        self.label_font = pygame.font.Font(None, 28)
        
        # Load settings
        self.config_path = os.path.join('config', 'user_settings.json')
        self.load_settings()
        
        # Quality options
        self.quality_options = ['low', 'medium', 'high']
        self.menu_size_options = [75, 100, 125]
        
        # Slider settings
        self.brightness_slider = self._create_slider(150, 0, 200)
        self.menu_size_slider_x = SCREEN_WIDTH // 2 - 150
        
        # Buttons
        self.back_button = pygame.Rect(SCREEN_WIDTH // 2 - 100, 550, 200, 50)
    
    def load_settings(self):
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
                self.brightness = data['graphics']['brightness']
                self.quality = data['graphics']['quality']
                self.menu_size = data['graphics']['menu_size']
        except:
            self.brightness = 100
            self.quality = 'medium'
            self.menu_size = 100
    
    def save_settings(self):
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
        except:
            data = {'graphics': {}, 'audio': {}}
        
        data['graphics']['brightness'] = self.brightness
        data['graphics']['quality'] = self.quality
        data['graphics']['menu_size'] = self.menu_size
        
        with open(self.config_path, 'w') as f:
            json.dump(data, f, indent=4)
    
    def _create_slider(self, width, min_val, max_val):
        return {
            'x': SCREEN_WIDTH // 2 - width // 2,
            'width': width,
            'min': min_val,
            'max': max_val
        }
    
    def toggle(self):
        self.active = not self.active
        return self.active
    
    def handle_event(self, event):
        if not self.active:
            return None
        
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.save_settings()
                self.toggle()
                return 'back'
        
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse_pos = event.pos
            
            # Back button
            if self.back_button.collidepoint(mouse_pos):
                self.save_settings()
                self.toggle()
                return 'back'
            
            # Quality cycle
            quality_rect = pygame.Rect(SCREEN_WIDTH // 2 - 100, 250, 200, 40)
            if quality_rect.collidepoint(mouse_pos):
                idx = self.quality_options.index(self.quality)
                self.quality = self.quality_options[(idx + 1) % len(self.quality_options)]
            
            # Menu size cycle
            size_rect = pygame.Rect(SCREEN_WIDTH // 2 - 100, 350, 200, 40)
            if size_rect.collidepoint(mouse_pos):
                idx = self.menu_size_options.index(self.menu_size)
                self.menu_size = self.menu_size_options[(idx + 1) % len(self.menu_size_options)]
        
        # Brightness slider drag
        if pygame.mouse.get_pressed()[0]:
            mouse_x = pygame.mouse.get_pos()[0]
            slider_y = 150
            if abs(pygame.mouse.get_pos()[1] - slider_y) < 15:
                slider = self.brightness_slider
                if slider['x'] <= mouse_x <= slider['x'] + slider['width']:
                    ratio = (mouse_x - slider['x']) / slider['width']
                    self.brightness = int(slider['min'] + ratio * (slider['max'] - slider['min']))
                    self.brightness = max(0, min(200, self.brightness))
        
        return None
    
    def draw(self, surface):
        if not self.active:
            return
        
        # Semi-transparent overlay
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        surface.blit(overlay, (0, 0))
        
        # Title
        title_text = self.font.render('GRAFIK-EINSTELLUNGEN', True, (255, 255, 255))
        title_rect = title_text.get_rect(center=(SCREEN_WIDTH // 2, 60))
        surface.blit(title_text, title_rect)
        
        # Brightness slider
        y_pos = 150
        label = self.label_font.render(f'Helligkeit: {self.brightness}%', True, (255, 255, 255))
        surface.blit(label, (SCREEN_WIDTH // 2 - 150, y_pos - 30))
        
        slider = self.brightness_slider
        pygame.draw.rect(surface, (100, 100, 100), (slider['x'], y_pos - 5, slider['width'], 10))
        slider_pos = slider['x'] + (self.brightness / 200) * slider['width']
        pygame.draw.circle(surface, (200, 200, 200), (int(slider_pos), y_pos), 12)
        
        # Quality selector
        y_pos = 250
        label = self.label_font.render('Qualität:', True, (255, 255, 255))
        surface.blit(label, (SCREEN_WIDTH // 2 - 150, y_pos - 30))
        
        quality_rect = pygame.Rect(SCREEN_WIDTH // 2 - 100, y_pos, 200, 40)
        mouse_pos = pygame.mouse.get_pos()
        color = (100, 100, 100) if quality_rect.collidepoint(mouse_pos) else (50, 50, 50)
        pygame.draw.rect(surface, color, quality_rect)
        pygame.draw.rect(surface, (200, 200, 200), quality_rect, 2)
        
        quality_text = self.button_font.render(self.quality.upper(), True, (255, 255, 255))
        quality_text_rect = quality_text.get_rect(center=quality_rect.center)
        surface.blit(quality_text, quality_text_rect)
        
        # Menu size selector
        y_pos = 350
        label = self.label_font.render('Menügröße:', True, (255, 255, 255))
        surface.blit(label, (SCREEN_WIDTH // 2 - 150, y_pos - 30))
        
        size_rect = pygame.Rect(SCREEN_WIDTH // 2 - 100, y_pos, 200, 40)
        color = (100, 100, 100) if size_rect.collidepoint(mouse_pos) else (50, 50, 50)
        pygame.draw.rect(surface, color, size_rect)
        pygame.draw.rect(surface, (200, 200, 200), size_rect, 2)
        
        size_text = self.button_font.render(f'{self.menu_size}%', True, (255, 255, 255))
        size_text_rect = size_text.get_rect(center=size_rect.center)
        surface.blit(size_text, size_text_rect)
        
        # Back button
        color = (100, 100, 100) if self.back_button.collidepoint(mouse_pos) else (50, 50, 50)
        pygame.draw.rect(surface, color, self.back_button)
        pygame.draw.rect(surface, (200, 200, 200), self.back_button, 2)
        
        back_text = self.button_font.render('Zurück', True, (255, 255, 255))
        back_text_rect = back_text.get_rect(center=self.back_button.center)
        surface.blit(back_text, back_text_rect)
