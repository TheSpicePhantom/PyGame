"""
Decoration: Runtime instance of a decoration (tree, bush, rock, etc.)
"""
import random
from typing import Dict, Optional, Tuple
from core import settings


class Decoration:
    """Runtime instance of a decoration (tree, bush, rock, etc.)"""
    
    def __init__(self, config: dict):
        """
        Initialize decoration from config.
        
        Args:
            config: Decoration configuration dictionary
        """
        self.config = config
        self.decoration_id = config['decoration_id']
        self.health = config.get('health', 0)
        self.current_sprite = config['sprites'].get('default')
        
        # Determine initial sprite for harvestable items
        if self.is_harvestable():
            self.current_sprite = config['sprites'].get('with_fruit', self.current_sprite)
    
    def is_harvestable(self) -> bool:
        """Check if this decoration can be harvested (right-click)."""
        return 'harvest' in self.config and self.config['harvest'].get('enabled', False)
    
    def is_mineable(self) -> bool:
        """Check if this decoration can be mined (left-click with tool)."""
        return 'mining' in self.config
    
    def has_collision(self) -> bool:
        """Check if this decoration has collision enabled."""
        collision_config = self.config.get('collision', {})
        return collision_config.get('enabled', False)
    
    def get_collision_rect(self, tile_x: int, tile_y: int) -> Optional[Tuple[float, float, float, float]]:
        """
        Get collision rectangle/circle bounds for this decoration.
        
        Args:
            tile_x: Tile X coordinate
            tile_y: Tile Y coordinate
            
        Returns:
            Tuple of (center_x, center_y, radius_or_width, radius_or_height) or None if no collision
        """
        if not self.has_collision():
            return None
        
        collision_config = self.config.get('collision', {})
        collision_type = collision_config.get('type', 'circle')
        
        # Calculate tile center in world coordinates
        tile_center_x = tile_x * settings.TILE_SIZE + settings.TILE_SIZE / 2.0
        tile_center_y = tile_y * settings.TILE_SIZE + settings.TILE_SIZE / 2.0
        
        if collision_type == 'circle':
            radius = collision_config.get('radius', 0.5) * settings.TILE_SIZE
            return (tile_center_x, tile_center_y, radius, radius)
        elif collision_type == 'rectangle':
            # For rectangle, use full tile size (can be extended later)
            width = settings.TILE_SIZE
            height = settings.TILE_SIZE
            return (tile_center_x, tile_center_y, width, height)
        else:
            return None
    
    def check_collision(self, x: float, y: float, tile_x: int, tile_y: int) -> bool:
        """
        Check if a point (x, y) collides with this decoration.
        
        Args:
            x: World X coordinate
            y: World Y coordinate
            tile_x: Tile X coordinate
            tile_y: Tile Y coordinate
            
        Returns:
            True if collision, False otherwise
        """
        collision_rect = self.get_collision_rect(tile_x, tile_y)
        if not collision_rect:
            return False
        
        center_x, center_y, size_x, size_y = collision_rect
        collision_config = self.config.get('collision', {})
        collision_type = collision_config.get('type', 'circle')
        
        if collision_type == 'circle':
            # Check distance from center
            dx = x - center_x
            dy = y - center_y
            distance_squared = dx * dx + dy * dy
            radius_squared = size_x * size_x
            return distance_squared <= radius_squared
        elif collision_type == 'rectangle':
            # Check if point is within rectangle bounds
            half_width = size_x / 2.0
            half_height = size_y / 2.0
            return (center_x - half_width <= x <= center_x + half_width and
                    center_y - half_height <= y <= center_y + half_height)
        else:
            return False
    
    def update_sprite(self, sprite_key: str):
        """
        Update current sprite based on state.
        
        Args:
            sprite_key: Key in sprites dict (e.g., 'with_fruit', 'without_fruit')
        """
        self.current_sprite = self.config['sprites'].get(sprite_key, self.current_sprite)
    
    def update_damage_sprite(self, health_percent: float):
        """
        Update sprite based on damage (for trees, rocks, etc.).
        
        Args:
            health_percent: Health percentage (1.0 = full health, 0.0 = destroyed)
        """
        sprites = self.config['sprites']
        
        if health_percent > 0.5:
            self.current_sprite = sprites.get('default', self.current_sprite)
        elif health_percent > 0.1:
            self.current_sprite = sprites.get('damaged_50', sprites.get('default', self.current_sprite))
        else:
            self.current_sprite = sprites.get('stump', sprites.get('default', self.current_sprite))
    
    def get_loot(self) -> Dict[str, int]:
        """
        Roll loot table and return {item_id: quantity}.
        
        Returns:
            Dictionary mapping item IDs to quantities
        """
        if self.is_harvestable():
            loot_table_id = self.config['harvest'].get('loot_table')
        elif self.is_mineable():
            loot_table_id = self.config['mining'].get('loot_table')
        else:
            return {}
        
        if not loot_table_id:
            return {}
        
        return self._roll_loot_table(loot_table_id)
    
    def _roll_loot_table(self, loot_table_id: str) -> Dict[str, int]:
        """
        Roll loot table and return items.
        
        Args:
            loot_table_id: Loot table identifier
            
        Returns:
            Dictionary mapping item IDs to quantities
        """
        from world.decoration_registry import DecorationRegistry
        
        loot_table = DecorationRegistry.get_loot_table(loot_table_id)
        if not loot_table:
            return {}
        
        result = {}
        rolls = loot_table.get('rolls', 1)
        
        for _ in range(rolls):
            for entry in loot_table.get('entries', []):
                # Check conditions
                if not self._check_conditions(entry.get('conditions', [])):
                    continue
                
                # Roll quantity
                qty_config = entry.get('quantity', {'min': 1, 'max': 1})
                quantity = random.randint(qty_config['min'], qty_config['max'])
                
                if quantity > 0:
                    item_id = entry['item_id']
                    result[item_id] = result.get(item_id, 0) + quantity
        
        return result
    
    def _check_conditions(self, conditions: list) -> bool:
        """
        Check if all conditions are met.
        
        Args:
            conditions: List of condition dictionaries
            
        Returns:
            True if all conditions are met, False otherwise
        """
        for condition in conditions:
            condition_type = condition.get('type')
            
            if condition_type == 'random_chance':
                chance = condition.get('chance', 0.0)
                if random.random() > chance:
                    return False
            # Add more condition types here as needed
        
        return True
    
    def on_harvest(self, player, tile: dict):
        """
        Called when decoration is harvested (placeholder for events system).
        
        Args:
            player: Player instance
            tile: Tile dictionary containing decoration data
        """
        # Placeholder for future event system (quests, achievements, etc.)
        # EventManager.trigger('decoration_harvested', {
        #     'decoration_id': self.decoration_id,
        #     'player': player,
        #     'loot': self.get_loot()
        # })
        pass
    
    def on_mine_complete(self, player, tile: dict):
        """
        Called when decoration is mined (placeholder for events system).
        
        Args:
            player: Player instance
            tile: Tile dictionary containing decoration data
        """
        # Placeholder for future event system (quests, achievements, etc.)
        # EventManager.trigger('decoration_mined', {
        #     'decoration_id': self.decoration_id,
        #     'player': player
        # })
        pass
    
    def get_rendering_config(self) -> dict:
        """Get rendering configuration (size, offset, layer, shadow)."""
        return self.config.get('rendering', {
            'size': [settings.TILE_SIZE, settings.TILE_SIZE],
            'offset': [0, 0],
            'layer': 10,
            'shadow': {'enabled': False}
        })
    
    def get_animation_config(self) -> dict:
        """Get animation configuration (type, speed, amplitude)."""
        return self.config.get('animation', {
            'enabled': False,
            'type': 'none',
            'speed': 1.0,
            'amplitude': 0.0
        })
