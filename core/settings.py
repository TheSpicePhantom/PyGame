"""
Core: Spiel-Einstellungen und Konfiguration
"""
import json
from typing import Dict, Any


class Settings:
    """Verwaltet alle Spiel-Einstellungen"""
    
    def __init__(self, config_path: str = "config/game_config.json"):
        self.config_path = config_path
        self.load_config()
    
    def load_config(self):
        """Lädt die Konfiguration aus der JSON-Datei"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            self.config = self.get_default_config()
            self.save_config()
    
    def save_config(self):
        """Speichert die Konfiguration in die JSON-Datei"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2)
    
    def get_default_config(self) -> Dict[str, Any]:
        """Gibt die Standard-Konfiguration zurück"""
        return {
            "window": {
                "width": 800,
                "height": 600,
                "title": "PyGame"
            },
            "map": {
                "width": 128,
                "height": 128,
                "tile_size": 64
            },
            "player": {
                "color": [0, 255, 0],
                "size": 1,
                "height": 1,
                "speed": 0.1
            },
            "isometric": {
                "tile_width": 64,
                "tile_height": 64
            }
        }
    
    def get(self, key: str, default=None):
        """Gibt einen Konfigurationswert zurück"""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value
    
    def set(self, key: str, value: Any):
        """Setzt einen Konfigurationswert"""
        keys = key.split('.')
        config = self.config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

