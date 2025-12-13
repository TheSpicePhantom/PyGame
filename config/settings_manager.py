"""Settings Manager - Central manager for loading and applying user settings"""
import json
import os
import pygame

class SettingsManager:
    """Singleton class to manage game settings and UI scaling"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.config_path = os.path.join('config', 'user_settings.json')
        self.load_settings()
        self._initialized = True
    
    def load_settings(self):
        """Load settings from user_settings.json"""
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
                self.graphics = data.get('graphics', {})
                self.audio = data.get('audio', {})
        except FileNotFoundError:
            # Default settings
            self.graphics = {
                'brightness': 100,
                'quality': 'medium',
                'menu_size': 100
            }
            self.audio = {
                'master': 100,
                'music': 80,
                'sounds': 100,
                'machines': 90,
                'weapons': 95,
                'build_destroy': 85
            }
            self.save_settings()
    
    def save_settings(self):
        """Save current settings to user_settings.json"""
        data = {
            'graphics': self.graphics,
            'audio': self.audio
        }
        os.makedirs('config', exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(data, f, indent=4)
    
    def get_ui_scale(self):
        """Get UI scaling factor based on menu_size setting"""
        menu_size = self.graphics.get('menu_size', 100)
        return menu_size / 100.0
    
    def scale_value(self, value):
        """Scale a single value by the UI scale factor"""
        return int(value * self.get_ui_scale())
    
    def scale_font_size(self, base_size):
        """Scale font size and return pygame.font.Font"""
        scaled_size = self.scale_value(base_size)
        return pygame.font.Font(None, scaled_size)
    
    def scale_rect(self, x, y, width, height):
        """Scale a rectangle's position and size"""
        scale = self.get_ui_scale()
        return pygame.Rect(
            int(x * scale),
            int(y * scale),
            int(width * scale),
            int(height * scale)
        )
    
    def update_graphics_setting(self, key, value):
        """Update a graphics setting and save"""
        self.graphics[key] = value
        self.save_settings()
    
    def update_audio_setting(self, key, value):
        """Update an audio setting and save"""
        self.audio[key] = value
        self.save_settings()
    
    def get_audio_volume(self, channel):
        """Get volume for a specific audio channel (0.0 - 1.0)"""
        master = self.audio.get('master', 100) / 100.0
        channel_vol = self.audio.get(channel, 100) / 100.0
        return master * channel_vol

# Global instance
settings_manager = SettingsManager()
