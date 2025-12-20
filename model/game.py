"""
Model: Haupt-Spiellogik
"""
import json
from model.map import Map
from model.player import Player


class Game:
    """Haupt-Spielklasse, verwaltet alle Spielelemente"""
    
    def __init__(self, config_path: str = "config/game_config.json"):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        map_config = self.config["map"]
        self.map = Map(map_config["width"], map_config["height"])
        
        player_config = self.config["player"]
        self.player = Player(5, 5, player_config["speed"])
    
    def update(self, dx: float, dy: float):
        """Aktualisiert den Spielzustand"""
        map_width = self.map.width
        map_height = self.map.height
        self.player.move(dx, dy, map_width, map_height)
    
    def get_config(self) -> dict:
        """Gibt die Konfiguration zurück"""
        return self.config
    
    def save_game(self, path: str = "data/game_data.json"):
        """Speichert den Spielstand"""
        data = {
            "player": self.player.to_dict(),
            "map": self.map.to_dict()
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    def load_game(self, path: str = "data/game_data.json"):
        """Lädt einen Spielstand"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.player = Player.from_dict(
            data["player"], 
            self.config["player"]["speed"]
        )
        self.map = Map.from_dict(data["map"])











