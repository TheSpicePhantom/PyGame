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
        """
        Check if this decoration can be mined (left-click with tool).
        All decorations are mineable - if no mining config exists, default values will be used.
        """
        return True  # All decorations are mineable
    
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
        loot_table_id = None
        
        # Check harvest loot table first (for harvestable items)
        if self.is_harvestable():
            loot_table_id = self.config['harvest'].get('loot_table')
        
        # Check mining loot table (for mineable items)
        if not loot_table_id and 'mining' in self.config:
            loot_table_id = self.config['mining'].get('loot_table')
        
        # If no loot table, return empty dict (no loot)
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
    
    def get_current_stage(self, tile_data: dict) -> int:
        """
        Get current growth stage (1-4).
        
        Args:
            tile_data: Tile decoration data dictionary
            
        Returns:
            Current growth stage (1-4) or default_stage if not set
        """
        growth_config = self.config.get('growth', {})
        if not growth_config.get('enabled', False):
            return growth_config.get('default_stage', 4)
        
        return tile_data.get('current_stage', growth_config.get('default_stage', 4))
    
    def get_health_percentage(self, tile_data: dict) -> float:
        """
        Get health percentage (1.0 = full health, 0.0 = destroyed).
        
        Args:
            tile_data: Tile decoration data dictionary
            
        Returns:
            Health percentage (0.0-1.0)
        """
        # Check if explicit health is stored
        if 'health' in tile_data and 'max_health' in tile_data:
            max_health = tile_data.get('max_health', 100)
            if max_health > 0:
                return min(tile_data.get('health', max_health) / max_health, 1.0)
        
        # Calculate from mining progress
        mining_config = self.config.get('mining', {})
        if not mining_config:
            return 1.0
        
        elapsed_time = tile_data.get('elapsed_time', 0.0)
        mining_time = mining_config.get('mining_time', 3.0)
        hardness_multiplier = mining_config.get('hardness_multiplier', 1.0)
        
        # Calculate time_to_mine (simplified, actual calculation uses tool speed)
        time_to_mine = mining_time * hardness_multiplier
        
        if time_to_mine <= 0:
            return 1.0
        
        health_percent = 1.0 - (elapsed_time / time_to_mine)
        return max(0.0, min(1.0, health_percent))
    
    def get_current_sprite(self, season_manager, growth_manager, tile_data: dict) -> str:
        """
        Get current sprite name based on Season + Stage + Damage + Snow.
        
        DEPRECATED: This method has been moved to WorldRenderer._determine_sprite_name() for
        centralization of rendering logic. This method is kept for backward compatibility
        but should not be used in new code.
        
        Args:
            season_manager: SeasonManager class (for get_current_season, is_snowing)
            growth_manager: GrowthManager class (not used directly, but passed for consistency)
            tile_data: Tile decoration data dictionary
            
        Returns:
            Sprite name string
        """
        # Check if seasons are enabled
        seasons_config = self.config.get('seasons', {})
        if not seasons_config.get('enabled', False):
            # Fallback to old system
            health_percent = self.get_health_percentage(tile_data)
            return self._get_fallback_sprite(health_percent, tile_data)
        
        # Get current season and stage
        current_season = season_manager.get_current_season()
        current_stage = self.get_current_stage(tile_data)
        health_percent = self.get_health_percentage(tile_data)
        is_snowy = season_manager.is_snowing() and current_season == "winter"
        
        # Get season config
        season_config = seasons_config.get(current_season, {})
        
        # Check if harvestable and has fruit state
        has_fruit = True  # Default to having fruit
        if self.is_harvestable() and tile_data is not None:
            has_fruit = tile_data.get('has_fruit', True)
        
        # Choose growth stages based on fruit state, snowy state, and season
        growth_stages = None
        
        if is_snowy:
            # Snowy variants
            if has_fruit and 'growth_stages_snowy_with_fruit' in season_config:
                growth_stages = season_config.get('growth_stages_snowy_with_fruit', {})
            elif not has_fruit and 'growth_stages_snowy_without_fruit' in season_config:
                growth_stages = season_config.get('growth_stages_snowy_without_fruit', {})
            elif 'growth_stages_snowy' in season_config:
                growth_stages = season_config.get('growth_stages_snowy', {})
        else:
            # Normal variants
            if has_fruit and 'growth_stages_with_fruit' in season_config:
                growth_stages = season_config.get('growth_stages_with_fruit', {})
            elif not has_fruit and 'growth_stages_without_fruit' in season_config:
                growth_stages = season_config.get('growth_stages_without_fruit', {})
        
        # Fallback to standard growth_stages if fruit variants not found
        if not growth_stages:
            if is_snowy and 'growth_stages_snowy' in season_config:
                growth_stages = season_config.get('growth_stages_snowy', {})
            else:
                growth_stages = season_config.get('growth_stages', {})
        
        # Get sprite for current stage
        sprite_name = growth_stages.get(str(current_stage))
        
        # Override with damage sprite if damaged
        if health_percent < 0.5:
            if health_percent < 0.1:
                # Stump
                if is_snowy and 'stump_snowy' in season_config:
                    sprite_name = season_config.get('stump_snowy', sprite_name)
                else:
                    sprite_name = season_config.get('stump', sprite_name)
            else:
                # Damaged (50%)
                if is_snowy and 'damaged_sprites_snowy' in season_config:
                    damaged_sprites = season_config.get('damaged_sprites_snowy', {})
                    sprite_name = damaged_sprites.get('damaged_50', sprite_name)
                else:
                    damaged_sprites = season_config.get('damaged_sprites', {})
                    sprite_name = damaged_sprites.get('damaged_50', sprite_name)
        
        # Fallback to default sprite if not found
        if not sprite_name:
            sprite_name = self.config.get('sprites', {}).get('default', 'default')
        
        return sprite_name
    
    def _get_fallback_sprite(self, health_percent: float, tile_data: dict = None) -> str:
        """
        Get fallback sprite using old system (for decorations without seasons).
        
        Args:
            health_percent: Health percentage (1.0 = full, 0.0 = destroyed)
            tile_data: Optional tile decoration data dictionary (for harvestable items)
            
        Returns:
            Sprite name
        """
        sprites = self.config.get('sprites', {})
        
        # Check if this is a harvestable decoration (like berry bushes)
        if self.is_harvestable() and tile_data is not None:
            has_fruit = tile_data.get('has_fruit', True)
            if has_fruit:
                sprite_name = sprites.get('with_fruit')
            else:
                sprite_name = sprites.get('without_fruit')
            
            # If sprite found, return it (unless damaged)
            if sprite_name and health_percent > 0.1:
                return sprite_name
            # If damaged, fall through to damage sprites
        
        # Standard damage-based sprite selection
        if health_percent > 0.5:
            return sprites.get('default', 'default')
        elif health_percent > 0.1:
            return sprites.get('damaged_50', sprites.get('default', 'default'))
        else:
            return sprites.get('stump', sprites.get('default', 'default'))
    
    def has_growth(self) -> bool:
        """Check if this decoration has growth enabled."""
        growth_config = self.config.get('growth', {})
        return growth_config.get('enabled', False)
