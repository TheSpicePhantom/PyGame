import pygame
import json
import os
from core import settings
from config.settings_manager import settings_manager


class GraphicsSettings:
    """Graphics Settings submenu"""

    def __init__(self):
        self.active = False
        self.parent = None  # Will be set by SettingsMenu
        
        # Load settings
        self.config_path = os.path.join('config', 'user_settings.json')
        self.load_settings()

        # Quality options
        self.quality_options = ["low", "medium", "high"]
        self.menu_size_options = [75, 100, 125]
        self.display_mode_options = ["windowed", "fullscreen_window", "fullscreen"]
        self.display_mode_labels = {
            "windowed": "Windowed",
            "fullscreen_window": "Borderless",
            "fullscreen": "Fullscreen"
        }
        
        self.dragging_slider = False
        
        # Store rects for buttons (will be created in draw)
        self.quality_rect = None
        self.size_rect = None
        self.display_mode_rect = None
        
        # Initialize UI elements
        self._init_ui()
    
    def _init_ui(self):
        """Initialize/reinitialize all UI elements with current scale"""
        # Fonts
        self.font = settings_manager.scale_font_size(42)
        self.button_font = settings_manager.scale_font_size(32)
        self.label_font = settings_manager.scale_font_size(28)
        
        # Slider settings (unscaled values, will be scaled when used)
        self.brightness_slider = self._create_slider(300, 0, 200)
        
        # Buttons (scale dimensions, center on unscaled screen)
        button_width = settings_manager.scale_value(200)
        button_height = settings_manager.scale_value(50)
        self.back_button = pygame.Rect(
            settings.SCREEN_WIDTH // 2 - button_width // 2,
            settings_manager.scale_value(650),
            button_width,
            button_height
        )

    def load_settings(self):
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
                self.brightness = data['graphics']['brightness']
                self.quality = data['graphics']['quality']
                self.menu_size = data['graphics']['menu_size']
                self.display_mode = data['graphics'].get('display_mode', 'windowed')
        except:
            self.brightness = 100
            self.quality = "medium"
            self.menu_size = 100
            self.display_mode = "windowed"

    def save_settings(self):
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            data['graphics']['brightness'] = self.brightness
            data['graphics']['quality'] = self.quality
            data['graphics']['menu_size'] = self.menu_size
            data['graphics']['display_mode'] = self.display_mode
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
            # Apply menu size change
            settings_manager.set_menu_scale(self.menu_size / 100)
        except Exception as e:
            print(f"Error saving graphics settings: {e}")

    def _create_slider(self, width, min_val, max_val):
        """Create a slider with scaled dimensions, centered on unscaled screen"""
        scaled_width = settings_manager.scale_value(width)
        return {
            'x': settings.SCREEN_WIDTH // 2 - scaled_width // 2,
            'y': 0,
            'width': scaled_width,
            'min': min_val,
            'max': max_val
        }

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
            
            # Brightness slider
            slider = self.brightness_slider
            y_pos = settings_manager.scale_value(130)
            slider_rect = pygame.Rect(slider['x'], y_pos - settings_manager.scale_value(12), 
                                     slider['width'], settings_manager.scale_value(24))
            if slider_rect.collidepoint(mouse_pos):
                self.dragging_slider = True
                # Update brightness based on click position
                relative_x = mouse_pos[0] - slider['x']
                self.brightness = int((relative_x / slider['width']) * 200)
                self.brightness = max(0, min(200, self.brightness))
            
            # Quality button
            if self.quality_rect and self.quality_rect.collidepoint(mouse_pos):
                current_index = self.quality_options.index(self.quality)
                next_index = (current_index + 1) % len(self.quality_options)
                self.quality = self.quality_options[next_index]
            
            # Menu size button
            if self.size_rect and self.size_rect.collidepoint(mouse_pos):
                current_index = self.menu_size_options.index(self.menu_size)
                next_index = (current_index + 1) % len(self.menu_size_options)
                self.menu_size = self.menu_size_options[next_index]
                # Apply scale immediately and reinitialize all UI
                settings_manager.set_menu_scale(self.menu_size / 100)
                if self.parent:
                    self.parent.refresh_all_ui()
                else:
                    self._init_ui()
                self.save_settings()
            
            # Display mode button
            if self.display_mode_rect and self.display_mode_rect.collidepoint(mouse_pos):
                current_index = self.display_mode_options.index(self.display_mode)
                next_index = (current_index + 1) % len(self.display_mode_options)
                self.display_mode = self.display_mode_options[next_index]
                self.save_settings()
                return 'display_mode_changed'
        
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging_slider = False
        
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging_slider:
                mouse_pos = event.pos
                slider = self.brightness_slider
                relative_x = mouse_pos[0] - slider['x']
                self.brightness = int((relative_x / slider['width']) * 200)
                self.brightness = max(0, min(200, self.brightness))

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
        
        button_width = settings_manager.scale_value(200)
        button_height = settings_manager.scale_value(40)
        self.quality_rect = pygame.Rect(
            settings.SCREEN_WIDTH // 2 - button_width // 2,
            y_pos,
            button_width,
            button_height
        )
        color = (100, 100, 100) if self.quality_rect.collidepoint(mouse_pos) else (50, 50, 50)
        pygame.draw.rect(screen, color, self.quality_rect)
        pygame.draw.rect(screen, (200, 200, 200), self.quality_rect, 2)
        quality_text = self.button_font.render(self.quality.upper(), True, (255, 255, 255))
        quality_text_rect = quality_text.get_rect(center=self.quality_rect.center)
        screen.blit(quality_text, quality_text_rect)

        # Menu size selector
        y_pos = settings_manager.scale_value(330)
        label = self.label_font.render('Menu Size:', True, (255, 255, 255))
        screen.blit(label, (settings.SCREEN_WIDTH // 2 - settings_manager.scale_value(150), y_pos - settings_manager.scale_value(30)))
        
        button_width = settings_manager.scale_value(200)
        button_height = settings_manager.scale_value(40)
        self.size_rect = pygame.Rect(
            settings.SCREEN_WIDTH // 2 - button_width // 2,
            y_pos,
            button_width,
            button_height
        )
        color = (100, 100, 100) if self.size_rect.collidepoint(mouse_pos) else (50, 50, 50)
        pygame.draw.rect(screen, color, self.size_rect)
        pygame.draw.rect(screen, (200, 200, 200), self.size_rect, 2)
        size_text = self.button_font.render(f'{self.menu_size}%', True, (255, 255, 255))
        size_text_rect = size_text.get_rect(center=self.size_rect.center)
        screen.blit(size_text, size_text_rect)

        # Display mode selector
        y_pos = settings_manager.scale_value(430)
        label = self.label_font.render('Display Mode:', True, (255, 255, 255))
        screen.blit(label, (settings.SCREEN_WIDTH // 2 - settings_manager.scale_value(150), y_pos - settings_manager.scale_value(30)))
        
        button_width = settings_manager.scale_value(200)
        button_height = settings_manager.scale_value(40)
        self.display_mode_rect = pygame.Rect(
            settings.SCREEN_WIDTH // 2 - button_width // 2,
            y_pos,
            button_width,
            button_height
        )
        color = (100, 100, 100) if self.display_mode_rect.collidepoint(mouse_pos) else (50, 50, 50)
        pygame.draw.rect(screen, color, self.display_mode_rect)
        pygame.draw.rect(screen, (200, 200, 200), self.display_mode_rect, 2)
        mode_text = self.button_font.render(self.display_mode_labels[self.display_mode], True, (255, 255, 255))
        mode_text_rect = mode_text.get_rect(center=self.display_mode_rect.center)
        screen.blit(mode_text, mode_text_rect)

        # Back button
        color = (100, 100, 100) if self.back_button.collidepoint(mouse_pos) else (50, 50, 50)
        pygame.draw.rect(screen, color, self.back_button)
        pygame.draw.rect(screen, (200, 200, 200), self.back_button, 2)
        back_text = self.button_font.render('< Back', True, (255, 255, 255))
        back_text_rect = back_text.get_rect(center=self.back_button.center)
        screen.blit(back_text, back_text_rect)
