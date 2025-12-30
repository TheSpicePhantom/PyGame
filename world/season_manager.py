"""
Season Manager: Verwaltet Jahreszeiten und Übergänge.
Speichert/Lädt Zeit-Daten in world_metadata.json.
"""
import json
import random
from typing import Dict, Optional, Tuple
from pathlib import Path


class SeasonManager:
    """Verwaltet Jahreszeiten und Übergänge."""
    
    _seasons: Dict[str, dict] = {}
    _world_settings: dict = {}
    _current_season: str = "summer"
    _current_day: float = 1.0
    _elapsed_time: float = 0.0
    _season_start_day: float = 1.0
    _is_snowing: bool = False
    _chunk_manager = None
    _diagnostics = None
    
    @classmethod
    def set_diagnostics(cls, diagnostics_service):
        """Set diagnostics service for logging."""
        cls._diagnostics = diagnostics_service
    
    @classmethod
    def _log(cls, level: str, message: str):
        """Log message with diagnostics or print fallback."""
        if cls._diagnostics:
            getattr(cls._diagnostics, level)("SeasonManager", message)
        else:
            print(f"[SeasonManager] {message}")
    
    @classmethod
    def load_all(cls, data_path: str = "data/mappings/seasons.json"):
        """
        Load season configuration from JSON file.
        
        Args:
            data_path: Path to seasons.json file
        """
        cls._seasons.clear()
        cls._world_settings = {}
        
        if not Path(data_path).exists():
            cls._log("warning", f"Seasons file does not exist: {data_path}")
            return
        
        try:
            with open(data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Load seasons
                seasons = data.get('seasons', {})
                for season_name, season_config in seasons.items():
                    cls._seasons[season_name] = season_config
                    cls._log("debug", f"  Loaded season: {season_name} (order: {season_config.get('order', 0)})")
                
                # Load world settings
                cls._world_settings = data.get('world_settings', {})
                
                cls._log("info", f"Loaded {len(cls._seasons)} seasons")
                
        except Exception as e:
            cls._log("error", f"Error loading seasons: {e}")
    
    @classmethod
    def initialize_world(cls, world_name: str, chunk_manager):
        """
        Initialize season system for a world.
        Loads season data from world_metadata.json or uses defaults.
        
        Args:
            world_name: World name
            chunk_manager: ChunkManager instance (for accessing metadata)
        """
        cls._chunk_manager = chunk_manager
        
        # Try to load season data from metadata
        if chunk_manager and hasattr(chunk_manager, 'metadata'):
            season_data = chunk_manager.metadata.get('season_data', {})
            if season_data:
                cls._current_season = season_data.get('current_season', cls._world_settings.get('start_season', 'summer'))
                cls._current_day = season_data.get('current_day', cls._world_settings.get('start_day', 1.0))
                cls._elapsed_time = season_data.get('elapsed_time', 0.0)
                cls._season_start_day = season_data.get('season_start_day', cls._current_day)
                cls._is_snowing = season_data.get('is_snowing', False)
                cls._log("info", f"Loaded season data: {cls._current_season}, day {cls._current_day:.1f}")
            else:
                # Initialize with defaults
                cls._current_season = cls._world_settings.get('start_season', 'summer')
                cls._current_day = cls._world_settings.get('start_day', 1.0)
                cls._elapsed_time = 0.0
                cls._season_start_day = cls._current_day
                cls._is_snowing = False
                cls._log("info", f"Initialized season system: {cls._current_season}, day {cls._current_day:.1f}")
        else:
            # Fallback if no chunk_manager
            cls._current_season = cls._world_settings.get('start_season', 'summer')
            cls._current_day = cls._world_settings.get('start_day', 1.0)
            cls._elapsed_time = 0.0
            cls._season_start_day = cls._current_day
            cls._is_snowing = False
    
    @classmethod
    def update(cls, dt: float):
        """
        Update season system (called every frame).
        
        Args:
            dt: Delta time in seconds
        """
        if not cls._seasons:
            return
        
        day_length = cls._world_settings.get('day_length_seconds', 600.0)
        
        # Update elapsed time
        cls._elapsed_time += dt
        cls._current_day = cls._elapsed_time / day_length
        
        # Check for season change
        current_season_config = cls._seasons.get(cls._current_season, {})
        season_duration = current_season_config.get('duration_days', 20.0)
        
        # Calculate days since season start
        days_in_season = cls._current_day - cls._season_start_day
        
        if days_in_season >= season_duration:
            # Advance to next season
            old_season = cls._current_season
            cls._advance_season()
            
            # Trigger event (placeholder for future event system)
            # EventManager.trigger('season_changed', {
            #     'old_season': old_season,
            #     'new_season': cls._current_season,
            #     'day': cls._current_day
            # })
            
            cls._log("info", f"Season changed: {old_season} → {cls._current_season} (day {cls._current_day:.1f})")
        
        # Update snow state (only in winter)
        if cls._current_season == "winter":
            weather = current_season_config.get('weather', {})
            snow_chance = weather.get('snow_chance', 0.5)
            # Re-evaluate snow state periodically (every 10 seconds)
            if int(cls._elapsed_time) % 10 == 0:
                cls._is_snowing = random.random() < snow_chance
        else:
            cls._is_snowing = False
        
        # Save season data to metadata (periodically, every 5 seconds)
        if cls._chunk_manager and int(cls._elapsed_time) % 5 == 0:
            cls._save_season_data()
    
    @classmethod
    def _advance_season(cls):
        """Advance to the next season in the cycle."""
        current_season_config = cls._seasons.get(cls._current_season, {})
        current_order = current_season_config.get('order', 1)
        
        # Find next season (order + 1, or wrap to 1)
        next_order = (current_order % 4) + 1
        next_season = None
        
        for season_name, season_config in cls._seasons.items():
            if season_config.get('order', 0) == next_order:
                next_season = season_name
                break
        
        if next_season:
            cls._current_season = next_season
            cls._season_start_day = cls._current_day
            cls._is_snowing = False  # Reset snow state
    
    @classmethod
    def _save_season_data(cls):
        """Save season data to world_metadata.json."""
        if not cls._chunk_manager:
            return
        
        try:
            if not hasattr(cls._chunk_manager, 'metadata'):
                return
            
            # Update metadata
            if 'season_data' not in cls._chunk_manager.metadata:
                cls._chunk_manager.metadata['season_data'] = {}
            
            cls._chunk_manager.metadata['season_data'] = {
                'current_day': cls._current_day,
                'current_season': cls._current_season,
                'elapsed_time': cls._elapsed_time,
                'season_start_day': cls._season_start_day,
                'is_snowing': cls._is_snowing
            }
            
        except Exception as e:
            cls._log("warning", f"Error saving season data: {e}")
    
    @classmethod
    def get_current_season(cls) -> str:
        """Get current season name."""
        return cls._current_season
    
    @classmethod
    def get_growth_speed_multiplier(cls) -> float:
        """Get growth speed multiplier for current season."""
        season_config = cls._seasons.get(cls._current_season, {})
        return season_config.get('growth_speed_multiplier', 1.0)
    
    @classmethod
    def is_snowing(cls) -> bool:
        """Check if it's currently snowing."""
        return cls._is_snowing
    
    @classmethod
    def get_season_tint(cls) -> Tuple[int, int, int, int]:
        """Get season tint color (RGBA)."""
        season_config = cls._seasons.get(cls._current_season, {})
        tint = season_config.get('tint_color', [255, 255, 255, 0])
        return tuple(tint)
    
    @classmethod
    def get_next_season_tint(cls) -> Tuple[int, int, int, int]:
        """Get next season tint color (for transition overlay)."""
        next_season = cls.get_next_season()
        season_config = cls._seasons.get(next_season, {})
        tint = season_config.get('tint_color', [255, 255, 255, 0])
        return tuple(tint)
    
    @classmethod
    def get_transition_progress(cls) -> float:
        """
        Get transition progress (0.0-1.0) for smooth season transitions.
        
        Returns:
            Progress from 0.0 (start of season) to 1.0 (end of transition period)
        """
        if not cls._world_settings.get('enable_season_transitions', True):
            return 0.0
        
        transition_duration = cls._world_settings.get('transition_duration_days', 2.0)
        current_season_config = cls._seasons.get(cls._current_season, {})
        season_duration = current_season_config.get('duration_days', 20.0)
        
        # Calculate days since season start
        days_in_season = cls._current_day - cls._season_start_day
        
        # Transition happens in last N days of season
        transition_start = season_duration - transition_duration
        if days_in_season < transition_start:
            return 0.0
        
        # Calculate progress (0.0 at transition_start, 1.0 at season_end)
        progress = (days_in_season - transition_start) / transition_duration
        return min(progress, 1.0)
    
    @classmethod
    def get_next_season(cls) -> str:
        """Get next season in the cycle."""
        current_season_config = cls._seasons.get(cls._current_season, {})
        current_order = current_season_config.get('order', 1)
        
        # Find next season (order + 1, or wrap to 1)
        next_order = (current_order % 4) + 1
        
        for season_name, season_config in cls._seasons.items():
            if season_config.get('order', 0) == next_order:
                return season_name
        
        return cls._current_season  # Fallback
    
    @classmethod
    def force_season(cls, season: str):
        """
        Debug: Force season change.
        
        Args:
            season: Season name to force
        """
        if season in cls._seasons:
            cls._current_season = season
            cls._season_start_day = cls._current_day
            cls._is_snowing = False
            cls._log("info", f"Forced season to: {season}")
    
    @classmethod
    def skip_time(cls, days: float):
        """
        Debug: Skip time forward.
        
        Args:
            days: Number of days to skip
        """
        day_length = cls._world_settings.get('day_length_seconds', 600.0)
        cls._elapsed_time += days * day_length
        cls._current_day = cls._elapsed_time / day_length
        cls._log("info", f"Skipped {days} days (now at day {cls._current_day:.1f})")
    
    @classmethod
    def reload(cls):
        """Reload season configuration (for hot-reload with F5)."""
        cls._log("info", "Reloading season configuration...")
        cls.load_all()
        cls._log("info", "Reload complete!")
