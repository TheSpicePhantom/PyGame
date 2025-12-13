import pygame
import json
import os
from core import settings
from config.settings_manager import settings_manager

class GraphicsSettings:
    """Graphics Settings submenu"""

    def __init__(self):
        self.active = False
        self.font = settings_manager.scale_font_size(42)
        self.button_font = settings_manager.scale_font_size(32)
        self.label_font = settings_manager.scale_font_size(28)

        # Load settings
        self.config_path = os.path.join('config', 'user_settings.json')
        self.load_settings()

        # Quality options
        self.quality_options = ["low", "medium", "high"]
        self.menu_size_options = [75, 100, 125]

        # Slider settings
        self.brightness_slider = self._create_slider(settings_manager.scale_value(300), 0, settings_manager.scale_value(200))

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
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
                self.brightness = data['graphics']['brightness']
                self.quality = data['graphics']['quality']
                self.menu_size = data['graphics']['menu_size']
        except:
            self.brightness = 100
            self.quality = "medium"
            self.menu_size = 100

    def save_settings(self):
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
                data['graphics']['brightness'] = self.brightness
                data['graphics']['quality'] = self.quality
                data['graphics']['menu_size'] = self.menu_size
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
                # Apply menu size change
                settings_manager.set_menu_scale(self.menu_size / 100)
        except Exception as e:
            print(f"Error saving graphics settings: {e}")

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
        """Draw the Graphics Settings Menu"""
        if not self.active:
            return

        # Draw semi-transparent background
        overlay = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, 0))

        # Draw title
        title_text = self.font.render("Graphics Settings", True, (255, 255, 255))
        title_rect = title_text.get_rect(center=(settings.SCREEN_WIDTH // 2, settings_manager.scale_value(60)))
        screen.blit(title_text, title_rect)

        mouse_pos = pygame.mouse.get_pos()

        # Brightness slider
        y_pos = settings_manager.scale_value(130)
        label = self.label_font.render(f'Brightness: {self.brightness}%', True, (255, 255, 255))
        screen.blit(label, (settings.SCREEN_WIDTH // 2 - settings_manager.scale_value(150), y_pos - settings_manager.scale_value(30)))

        slider = self.brightness_slider
        slider_y = y_pos
        pygame.draw.rect(screen, (100, 100, 100), (slider['x'], y_pos - settings_manager.scale_value(5), slider['width'], settings_manager.scale_value(10)))
        slider_pos = slider['x'] + (self.brightness / 200) * slider['width']
        pygame.draw.circle(screen, (200, 200, 200), (int(slider_pos), y_pos), settings_manager.scale_value(12))

        # Quality selector
        y_pos = settings_manager.scale_value(230)
        label = self.label_font.render('Quality:', True, (255, 255, 255))
        screen.blit(label, (settings.SCREEN_WIDTH // 2 - settings_manager.scale_value(150), y_pos - settings_manager.scale_value(30)))

        quality_rect = settings_manager.scale_rect(pygame.Rect(settings.SCREEN_WIDTH // 2 - settings_manager.scale_value(100), y_pos, settings_manager.scale_value(200), settings_manager.scale_value(40)))
        color = (100, 100, 100) if quality_rect.collidepoint(mouse_pos) else (50, 50, 50)
        pygame.draw.rect(screen, color, quality_rect)
        pygame.draw.rect(screen, (200, 200, 200), quality_rect, 2)

        quality_text = self.button_font.render(self.quality.upper(), True, (255, 255, 255))
        quality_text_rect = quality_text.get_rect(center=quality_rect.center)
        screen.blit(quality_text, quality_text_rect)

        # Menu size selector
        y_pos = settings_manager.scale_value(330)
        label = self.label_font.render('Menu Size:', True, (255, 255, 255))
        screen.blit(label, (settings.SCREEN_WIDTH // 2 - settings_manager.scale_value(150), y_pos - settings_manager.scale_value(30)))

        size_rect = settings_manager.scale_rect(pygame.Rect(settings.SCREEN_WIDTH // 2 - settings_manager.scale_value(100), y_pos, settings_manager.scale_value(200), settings_manager.scale_value(40)))
        color = (100, 100, 100) if size_rect.collidepoint(mouse_pos) else (50, 50, 50)
        pygame.draw.rect(screen, color, size_rect)
        pygame.draw.rect(screen, (200, 200, 200), size_rect, 2)

        size_text = self.button_font.render(f'{self.menu_size}%', True, (255, 255, 255))
        size_text_rect = size_text.get_rect(center=size_rect.center)
        screen.blit(size_text, size_text_rect)

        # Back button
        color = (100, 100, 100) if self.back_button.collidepoint(mouse_pos) else (50, 50, 50)
        pygame.draw.rect(screen, color, self.back_button)
        pygame.draw.rect(screen, (200, 200, 200), self.back_button, 2)

        back_text = self.button_font.render('< Back', True, (255, 255, 255))
        back_text_rect = back_text.get_rect(center=self.back_button.center)
        screen.blit(back_text, back_text_rect)
