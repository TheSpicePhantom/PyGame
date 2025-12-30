"""
Growth Manager: Verwaltet Wachstum von Decorations.
Prüft Growth-Requirements, aktualisiert growth_progress und wechselt Wachstumsstadien.
"""
import random
from typing import Dict, Optional
from world.season_manager import SeasonManager


class GrowthManager:
    """Verwaltet Wachstum von Decorations."""
    
    _update_interval: float = 5.0  # Update nur alle 5 Sekunden
    _time_since_update: float = 0.0
    _initialized: bool = False
    _diagnostics = None
    
    # Random-Tick-System (Minecraft-Style)
    # Pro Update-Intervall werden nur zufällig ausgewählte Decorations aktualisiert
    _random_tick_chance: float = 0.1  # 10% Chance pro Decoration pro Update (wie Minecraft)
    _growth_speed_variance: float = 0.1  # ±10% Varianz in Wachstumsgeschwindigkeit für Realismus
    
    @classmethod
    def set_diagnostics(cls, diagnostics_service):
        """Set diagnostics service for logging."""
        cls._diagnostics = diagnostics_service
    
    @classmethod
    def _log(cls, level: str, message: str):
        """Log message with diagnostics or print fallback."""
        if cls._diagnostics:
            getattr(cls._diagnostics, level)("GrowthManager", message)
        else:
            print(f"[GrowthManager] {message}")
    
    @classmethod
    def initialize(cls):
        """Initialize growth manager."""
        cls._time_since_update = 0.0
        cls._initialized = True
        cls._log("info", "GrowthManager initialized")
    
    @classmethod
    def update_all(cls, world, dt: float):
        """
        Update growth for all decorations in loaded chunks (with throttling).
        
        Args:
            world: World instance
            dt: Delta time in seconds
        """
        if not cls._initialized:
            return
        
        cls._time_since_update += dt
        
        # Only update every 5 seconds for performance
        if cls._time_since_update < cls._update_interval:
            return
        
        # Get accumulated time
        accumulated_dt = cls._time_since_update
        cls._time_since_update = 0.0
        
        # Update all decorations in loaded chunks
        if not world or not hasattr(world, 'chunk_manager'):
            return
        
        chunk_manager = world.chunk_manager
        if not chunk_manager or not hasattr(chunk_manager, 'loaded_chunks'):
            return
        
        # Collect all growable decorations first
        growable_decorations = []
        stump_decorations = []
        
        for chunk_key, chunk in chunk_manager.loaded_chunks.items():
            if not hasattr(chunk, 'tiles'):
                continue
            
            for tile_y in range(len(chunk.tiles)):
                if not chunk.tiles[tile_y]:
                    continue
                for tile_x in range(len(chunk.tiles[tile_y])):
                    tile = chunk.tiles[tile_y][tile_x]
                    if not tile:
                        continue
                    
                    decoration_data = tile.get('decoration')
                    if not decoration_data:
                        continue
                    
                    decoration_id = decoration_data.get('decoration_id')
                    if not decoration_id:
                        continue
                    
                    # Get decoration config
                    from world.decoration_registry import DecorationRegistry
                    deco_config = DecorationRegistry.get(decoration_id)
                    if not deco_config:
                        continue
                    
                    from world.decoration import Decoration
                    decoration = Decoration(deco_config)
                    
                    # Collect growable decorations
                    if decoration.has_growth():
                        deco_data = decoration_data.get('data', {})
                        growable_decorations.append((decoration, deco_data, tile))
                    
                    # Collect stump decorations (always update, no random tick)
                    deco_data = decoration_data.get('data', {})
                    if deco_data.get('is_stump', False):
                        stump_decorations.append((decoration, deco_data, tile))
        
        # Random-Tick-System: Nur zufällig ausgewählte Decorations werden aktualisiert
        updated_count = 0
        ticked_count = 0
        
        for decoration, deco_data, tile in growable_decorations:
            # Random tick chance (Minecraft-Style)
            # Jede Decoration hat eine zufällige Chance, in diesem Update getickt zu werden
            growth_config = decoration.config.get('growth', {})
            random_tick_chance = growth_config.get('random_tick_chance', cls._random_tick_chance)
            
            if random.random() < random_tick_chance:
                # This decoration gets a random tick - update its growth
                cls.update_growth(decoration, deco_data, accumulated_dt, tile)
                ticked_count += 1
                updated_count += 1
        
        # Always update stump removal (not random)
        for decoration, deco_data, tile in stump_decorations:
            cls.update_stump_removal(decoration, deco_data, accumulated_dt, tile)
        
        if ticked_count > 0:
            cls._log("debug", f"Random-ticked {ticked_count} of {len(growable_decorations)} growable decorations")
    
    @classmethod
    def update_growth(cls, decoration, tile_data: dict, dt: float, tile: dict):
        """
        Update growth progress for a decoration.
        
        Args:
            decoration: Decoration instance
            tile_data: Tile decoration data dictionary
            dt: Delta time in seconds
            tile: Tile dictionary (for updating collision)
        """
        growth_config = decoration.config.get('growth', {})
        if not growth_config.get('enabled', False):
            return
        
        # Check if can grow
        current_season = SeasonManager.get_current_season()
        if not cls.can_grow(decoration, tile_data, current_season):
            return
        
        # Get current stage
        current_stage = decoration.get_current_stage(tile_data)
        stages = growth_config.get('stages', [])
        
        # Find current stage config
        current_stage_config = None
        for stage_config in stages:
            if stage_config.get('stage') == current_stage:
                current_stage_config = stage_config
                break
        
        if not current_stage_config:
            return
        
        # Check if already at max stage
        if current_stage >= len(stages):
            return
        
        # Get next stage
        next_stage = current_stage + 1
        next_stage_config = None
        for stage_config in stages:
            if stage_config.get('stage') == next_stage:
                next_stage_config = stage_config
                break
        
        if not next_stage_config:
            return
        
        # Calculate effective growth speed with random variance for realism
        season_multiplier = SeasonManager.get_growth_speed_multiplier()
        stage_multiplier = current_stage_config.get('growth_speed_multiplier', 1.0)
        base_growth_speed = season_multiplier * stage_multiplier
        
        # Add random variance (±10-15% by default) for more realistic, non-uniform growth
        # Each decoration gets a slightly different growth speed
        growth_config = decoration.config.get('growth', {})
        variance = growth_config.get('growth_speed_variance', cls._growth_speed_variance)
        
        # Use decoration position as seed for consistent variance per decoration
        # This ensures each tree has its own "personality" but stays consistent across updates
        # We'll use a combination of decoration_id and a stored random seed
        if 'growth_variance_seed' not in tile_data:
            # Initialize random seed for this decoration (based on position if available)
            # Use a hash of decoration_id + some identifier for deterministic randomness
            import hashlib
            seed_str = f"{decoration.decoration_id}_{id(tile)}"
            seed_hash = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
            tile_data['growth_variance_seed'] = seed_hash
        
        # Use stored seed for consistent variance
        variance_seed = tile_data.get('growth_variance_seed', hash(decoration.decoration_id))
        random.seed(variance_seed)
        variance_multiplier = 1.0 + random.uniform(-variance, variance)
        random.seed()  # Reset to system randomness
        
        effective_growth_speed = base_growth_speed * variance_multiplier
        
        # Update growth progress
        growth_progress = tile_data.get('growth_progress', 0.0)
        growth_progress += dt * effective_growth_speed
        tile_data['growth_progress'] = growth_progress
        
        # Check if ready to advance
        growth_time = next_stage_config.get('growth_time', 0.0)
        if growth_progress >= growth_time:
            cls.advance_stage(decoration, tile_data, tile)
    
    @classmethod
    def can_grow(cls, decoration, tile_data: dict, season: str) -> bool:
        """
        Check if decoration can grow in current conditions.
        
        Args:
            decoration: Decoration instance
            tile_data: Tile decoration data dictionary
            season: Current season name
            
        Returns:
            True if can grow, False otherwise
        """
        growth_config = decoration.config.get('growth', {})
        if not growth_config.get('enabled', False):
            return False
        
        # Check health (don't grow if damaged > 50%)
        health_percent = decoration.get_health_percentage(tile_data)
        if health_percent < 0.5:
            return False
        
        # Check growth requirements
        requirements = growth_config.get('growth_requirements', {})
        
        # Check season
        seasons_allowed = requirements.get('seasons_allowed', [])
        if seasons_allowed and season not in seasons_allowed:
            return False
        
        # Check temperature (simplified - would need world temperature system)
        # min_temperature = requirements.get('min_temperature', -100)
        # current_temperature = World.get_temperature()  # Would need temperature system
        # if current_temperature < min_temperature:
        #     return False
        
        # Check light level (simplified - would need light system)
        # min_light_level = requirements.get('min_light_level', 0.0)
        # current_light = World.get_light_level()  # Would need light system
        # if current_light < min_light_level:
        #     return False
        
        return True
    
    @classmethod
    def advance_stage(cls, decoration, tile_data: dict, tile: dict):
        """
        Advance decoration to next growth stage.
        
        Args:
            decoration: Decoration instance
            tile_data: Tile decoration data dictionary
            tile: Tile dictionary (for updating collision)
        """
        growth_config = decoration.config.get('growth', {})
        stages = growth_config.get('stages', [])
        
        current_stage = decoration.get_current_stage(tile_data)
        next_stage = current_stage + 1
        
        if next_stage > len(stages):
            return  # Already at max stage
        
        # Find next stage config
        next_stage_config = None
        for stage_config in stages:
            if stage_config.get('stage') == next_stage:
                next_stage_config = stage_config
                break
        
        if not next_stage_config:
            return
        
        # Update stage
        tile_data['current_stage'] = next_stage
        tile_data['growth_progress'] = 0.0  # Reset progress
        
        # Update health
        new_health = next_stage_config.get('health', 100)
        tile_data['health'] = new_health
        tile_data['max_health'] = new_health
        
        # Update collision radius (if collision is enabled)
        if decoration.has_collision():
            collision_config = decoration.config.get('collision', {})
            if collision_config.get('type') == 'circle':
                new_radius = next_stage_config.get('collision_radius', 0.4)
                collision_config['radius'] = new_radius
        
        # Spawn particles (placeholder - would need particle system)
        # ParticleManager.spawn('growth_sparkle', tile.x, tile.y, count=10)
        
        cls._log("debug", f"Decoration {decoration.decoration_id} advanced to stage {next_stage}")
    
    @classmethod
    def update_stump_removal(cls, decoration, tile_data: dict, dt: float, tile: dict):
        """
        Update stump removal timer.
        
        Args:
            decoration: Decoration instance
            tile_data: Tile decoration data dictionary
            dt: Delta time in seconds
            tile: Tile dictionary
        """
        mining_config = decoration.config.get('mining', {})
        stump_config = mining_config.get('stump_removal', {})
        
        if not stump_config.get('enabled', False):
            return
        
        stump_timer = tile_data.get('stump_timer', 0.0)
        stump_timer += dt
        tile_data['stump_timer'] = stump_timer
        
        removal_time = stump_config.get('timer', 120.0)
        if stump_timer >= removal_time:
            # Remove stump or regrow
            regrow_chance = stump_config.get('regrow_chance', 0.0)
            
            if random.random() < regrow_chance:
                # Regrow as sapling
                growth_config = decoration.config.get('growth', {})
                if growth_config.get('enabled', False):
                    tile_data['current_stage'] = 1
                    tile_data['growth_progress'] = 0.0
                    tile_data['is_stump'] = False
                    tile_data['sprite_state'] = 'default'
                    tile_data['stump_timer'] = 0.0
                    cls._log("debug", f"Decoration {decoration.decoration_id} regrew as sapling")
            else:
                # Remove completely
                tile['decoration'] = None
                cls._log("debug", f"Decoration {decoration.decoration_id} stump removed")
    
    @classmethod
    def force_grow_all(cls, world):
        """
        Debug: Force-grow all decorations to next stage.
        
        Args:
            world: World instance
        """
        if not world or not hasattr(world, 'chunk_manager'):
            return
        
        chunk_manager = world.chunk_manager
        if not chunk_manager or not hasattr(chunk_manager, 'loaded_chunks'):
            return
        
        forced_count = 0
        for chunk_key, chunk in chunk_manager.loaded_chunks.items():
            if not hasattr(chunk, 'tiles'):
                continue
            
            for tile_y in range(len(chunk.tiles)):
                if not chunk.tiles[tile_y]:
                    continue
                for tile_x in range(len(chunk.tiles[tile_y])):
                    tile = chunk.tiles[tile_y][tile_x]
                    if not tile:
                        continue
                    
                    decoration_data = tile.get('decoration')
                    if not decoration_data:
                        continue
                    
                    decoration_id = decoration_data.get('decoration_id')
                    if not decoration_id:
                        continue
                    
                    from world.decoration_registry import DecorationRegistry
                    deco_config = DecorationRegistry.get(decoration_id)
                    if not deco_config:
                        continue
                    
                    from world.decoration import Decoration
                    decoration = Decoration(deco_config)
                    
                    if decoration.has_growth():
                        deco_data = decoration_data.get('data', {})
                        growth_config = decoration.config.get('growth', {})
                        stages = growth_config.get('stages', [])
                        current_stage = decoration.get_current_stage(deco_data)
                        
                        if current_stage < len(stages):
                            cls.advance_stage(decoration, deco_data, tile)
                            forced_count += 1
        
        cls._log("info", f"Force-grew {forced_count} decorations")
