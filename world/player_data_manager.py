"""Player Data Manager - Handles player save/load"""
import json
from pathlib import Path
from typing import Optional, Dict

class PlayerDataManager:
    """Manages player data persistence"""
    
    def __init__(self, save_slot: int):
        self.save_slot = save_slot
        self.save_dir = Path(f"saves/slot_{save_slot}")
        self.player_file = self.save_dir / "player_data.json"
    
    def save_player(self, position: tuple, inventory: dict, faction_data: dict):
        """Save player data to JSON
        
        Args:
            position: (x, y) player coordinates
            inventory: dict of items and quantities
            faction_data: {
                'policies': list of policy names,
                'allies': list of ally faction names,
                'enemies': list of enemy faction names
            }
        """
        player_data = {
            'position': {
                'x': position[0],
                'y': position[1]
            },
            'inventory': inventory,
            'faction': faction_data
        }
        
        # Create directory if needed
        self.save_dir.mkdir(parents=True, exist_ok=True)
        
        # Write JSON
        with open(self.player_file, 'w') as f:
            json.dump(player_data, f, indent=2)
    
    def load_player(self) -> Optional[Dict]:
        """Load player data from JSON
        
        Returns:
            Dict with 'position', 'inventory', 'faction' or None if no save exists
        """
        if not self.player_file.exists():
            return None
        
        with open(self.player_file, 'r') as f:
            data = json.load(f)
        
        return data
    
    def get_spawn_position(self) -> tuple:
        """Get player spawn position (from save or default)
        
        Returns:
            (x, y) coordinates
        """
        player_data = self.load_player()
        
        if player_data:
            pos = player_data['position']
            return (pos['x'], pos['y'])
        
        # Default spawn at center of world
        from core import settings
        start_x = settings.WORLD_SIZE_TILES * settings.TILE_SIZE // 2
        start_y = settings.WORLD_SIZE_TILES * settings.TILE_SIZE // 2
        return (start_x, start_y)
    
    def player_exists(self) -> bool:
        """Check if player data exists for this slot"""
        return self.player_file.exists()
