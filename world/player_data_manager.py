"""Player Data Manager - Handles player save/load"""
import json
import logging
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime

class PlayerDataManager:
    """Manages player data persistence"""
    
    # Schema version for format migration
    CURRENT_SCHEMA_VERSION = 1
    
    # Default values for missing fields (backward compatibility)
    DEFAULT_INVENTORY_SIZE = 45  # Default inventory size in slots (9 width x 5 height)
    DEFAULT_INVENTORY = {
        'slots': [[None for _ in range(9)] for _ in range(6)],  # 9 columns x 6 rows (5 inventory + 1 hotbar)
        'size_rows': 5,  # Default inventory size (5 rows + 1 hotbar row) - DEPRECATED, use inventory_size
        'inventory_size': DEFAULT_INVENTORY_SIZE  # Total number of inventory slots (excluding hotbar)
    }
    DEFAULT_FACTION = {
        'policies': [],
        'allies': [],
        'enemies': []
    }
    DEFAULT_SPRINT_MULTIPLIER = 1.2  # Default sprint speed multiplier
    DEFAULT_SNEAK_MULTIPLIER = 0.8  # Default sneak speed multiplier
    
    def __init__(self, world_name: str):
        from world.world_utils import get_world_save_dir
        self.world_name = world_name
        self.save_dir = get_world_save_dir(world_name)
        self.player_file = self.save_dir / "player_data.json"
        self.logger = logging.getLogger(__name__)
    
    def save_player(self, position: tuple, inventory: dict, faction_data: dict, inventory_size: int = None,
                    sprint_multiplier: float = None, sneak_multiplier: float = None):
        """
        Save player data to JSON
        
        Args:
            position: (x, y) player coordinates in PIXEL WORLD COORDINATES (not chunk/tile coordinates)
            inventory: dict of items and quantities
            faction_data: {
                'policies': list of policy names,
                'allies': list of ally faction names,
                'enemies': list of enemy faction names
            }
            inventory_size: Total number of inventory slots (excluding hotbar). If None, uses existing value or default.
            sprint_multiplier: Sprint speed multiplier. If None, uses existing value or default.
            sneak_multiplier: Sneak speed multiplier. If None, uses existing value or default.
        
        Raises:
            IOError: If file write fails (logged before raising)
        
        Note:
            Position is stored in pixel world coordinates (same as get_spawn_position returns).
            spawn_chunk is calculated automatically for faster chunk preloading.
        """
        from core import settings
        
        # Calculate chunk coordinates from pixel world coordinates
        chunk_x = int(position[0] // (settings.CHUNK_SIZE * settings.TILE_SIZE))
        chunk_y = int(position[1] // (settings.CHUNK_SIZE * settings.TILE_SIZE))
        
        # Determine inventory_size (use provided value, or try to get from existing data, or use default)
        if inventory_size is None:
            # Try to load existing player data to get inventory_size
            existing_data = self.load_player()
            if existing_data and 'inventory_size' in existing_data:
                inventory_size = existing_data['inventory_size']
            else:
                inventory_size = self.DEFAULT_INVENTORY_SIZE
        
        # Determine sprint_multiplier (use provided value, or try to get from existing data, or use default)
        if sprint_multiplier is None:
            existing_data = self.load_player()
            if existing_data and 'sprint_multiplier' in existing_data:
                sprint_multiplier = existing_data['sprint_multiplier']
            else:
                sprint_multiplier = self.DEFAULT_SPRINT_MULTIPLIER
        
        # Determine sneak_multiplier (use provided value, or try to get from existing data, or use default)
        if sneak_multiplier is None:
            existing_data = self.load_player()
            if existing_data and 'sneak_multiplier' in existing_data:
                sneak_multiplier = existing_data['sneak_multiplier']
            else:
                sneak_multiplier = self.DEFAULT_SNEAK_MULTIPLIER
        
        # Ensure inventory is a dict
        if not isinstance(inventory, dict):
            inventory = {}
        
        # Remove inventory_size from inventory if it exists there (migration)
        if 'inventory_size' in inventory:
            del inventory['inventory_size']
        
        player_data = {
            'version': self.CURRENT_SCHEMA_VERSION,
            'position': {
                'x': position[0],  # Pixel world X coordinate
                'y': position[1]   # Pixel world Y coordinate
            },
            'spawn_chunk': {  # Chunk coordinates for faster preloading
                'x': chunk_x,
                'y': chunk_y
            },
            'inventory': inventory,
            'inventory_size': inventory_size,  # Store inventory_size at top level
            'sprint_multiplier': sprint_multiplier,  # Sprint speed multiplier
            'sneak_multiplier': sneak_multiplier,  # Sneak speed multiplier
            'faction': faction_data
        }
        
        try:
            # Create directory if needed
            self.save_dir.mkdir(parents=True, exist_ok=True)
            
            # Write JSON with UTF-8 encoding
            with open(self.player_file, 'w', encoding='utf-8') as f:
                json.dump(player_data, f, indent=2)
            
            self.logger.debug(f"Player data saved to {self.player_file}")
        except (IOError, OSError) as e:
            self.logger.error(f"Failed to save player data to {self.player_file}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error saving player data: {e}", exc_info=True)
            raise
    
    def load_player(self) -> Optional[Dict]:
        """
        Load player data from JSON
        
        Returns:
            Dict with 'position', 'inventory', 'faction' or None if no save exists or corrupted
        
        Note: Corrupted JSON files are automatically backed up to prevent blocking game startup.
        """
        if not self.player_file.exists():
            return None
        
        try:
            with open(self.player_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Migrate and fill missing fields with defaults
            data = self._migrate_and_fill_defaults(data)
            
            self.logger.debug(f"Player data loaded from {self.player_file} (version: {data.get('version', 'unknown')})")
            return data
        
        except json.JSONDecodeError as e:
            # Corrupted JSON - backup and return None to prevent blocking game startup
            self.logger.error(
                f"Corrupted player data file {self.player_file}: {e}. "
                f"Backing up corrupted file and returning None."
            )
            self._backup_corrupted_file()
            return None
        
        except (IOError, OSError) as e:
            self.logger.error(f"Failed to read player data from {self.player_file}: {e}")
            return None
        
        except Exception as e:
            self.logger.error(f"Unexpected error loading player data: {e}", exc_info=True)
            return None
    
    def _migrate_and_fill_defaults(self, data: Dict) -> Dict:
        """
        Migrate player data to current schema version and fill missing fields with defaults.
        
        Args:
            data: Loaded player data dictionary
        
        Returns:
            Migrated player data with all required fields
        """
        # Get version (default to 0 for old saves without version)
        version = data.get('version', 0)
        
        # Migrate based on version
        if version < self.CURRENT_SCHEMA_VERSION:
            self.logger.info(
                f"Migrating player data from version {version} to {self.CURRENT_SCHEMA_VERSION}"
            )
            
            # Version 0 -> 1: Add version field and ensure all required fields exist
            if version == 0:
                # Fill missing inventory with defaults
                if 'inventory' not in data:
                    data['inventory'] = self.DEFAULT_INVENTORY.copy()
                    self.logger.debug("Added missing 'inventory' field with defaults")
                
                # Fill missing faction with defaults
                if 'faction' not in data:
                    data['faction'] = self.DEFAULT_FACTION.copy()
                    self.logger.debug("Added missing 'faction' field with defaults")
                
                # Ensure faction has all required sub-fields
                if 'faction' in data:
                    faction = data['faction']
                    if 'policies' not in faction:
                        faction['policies'] = []
                    if 'allies' not in faction:
                        faction['allies'] = []
                    if 'enemies' not in faction:
                        faction['enemies'] = []
                
                # Calculate spawn_chunk from position if missing (for faster preloading)
                if 'spawn_chunk' not in data and 'position' in data:
                    from core import settings
                    pos = data['position']
                    chunk_x = int(pos.get('x', 0) // (settings.CHUNK_SIZE * settings.TILE_SIZE))
                    chunk_y = int(pos.get('y', 0) // (settings.CHUNK_SIZE * settings.TILE_SIZE))
                    data['spawn_chunk'] = {'x': chunk_x, 'y': chunk_y}
                    self.logger.debug("Calculated missing 'spawn_chunk' field from position")
                
                # Set version to current
                data['version'] = self.CURRENT_SCHEMA_VERSION
        
        # Always ensure current version is set (even if already migrated)
        if 'version' not in data or data['version'] != self.CURRENT_SCHEMA_VERSION:
            data['version'] = self.CURRENT_SCHEMA_VERSION
        
        # Fill any missing fields with defaults (safety check)
        if 'inventory' not in data:
            data['inventory'] = self.DEFAULT_INVENTORY.copy()
        else:
            # Migrate inventory_size from inside inventory to top level if present
            if 'inventory_size' in data['inventory']:
                data['inventory_size'] = data['inventory']['inventory_size']
                del data['inventory']['inventory_size']
                self.logger.debug("Migrated inventory_size from inventory to top level")
            # Try to migrate from size_rows if present (old format)
            elif 'size_rows' in data['inventory']:
                data['inventory_size'] = data['inventory']['size_rows'] * 9
                self.logger.debug("Migrated inventory_size from size_rows")
        
        # Ensure inventory_size exists at top level
        if 'inventory_size' not in data:
            data['inventory_size'] = self.DEFAULT_INVENTORY_SIZE
            self.logger.debug("Added missing inventory_size field with default")
        
        # Ensure sprint_multiplier exists
        if 'sprint_multiplier' not in data:
            data['sprint_multiplier'] = self.DEFAULT_SPRINT_MULTIPLIER
            self.logger.debug("Added missing sprint_multiplier field with default")
        
        # Ensure sneak_multiplier exists
        if 'sneak_multiplier' not in data:
            data['sneak_multiplier'] = self.DEFAULT_SNEAK_MULTIPLIER
            self.logger.debug("Added missing sneak_multiplier field with default")
        
        if 'faction' not in data:
            data['faction'] = self.DEFAULT_FACTION.copy()
        
        # Calculate spawn_chunk from position if missing (for faster preloading)
        if 'spawn_chunk' not in data and 'position' in data:
            from core import settings
            pos = data['position']
            chunk_x = int(pos.get('x', 0) // (settings.CHUNK_SIZE * settings.TILE_SIZE))
            chunk_y = int(pos.get('y', 0) // (settings.CHUNK_SIZE * settings.TILE_SIZE))
            data['spawn_chunk'] = {'x': chunk_x, 'y': chunk_y}
            self.logger.debug("Calculated missing 'spawn_chunk' field from position")
        
        return data
    
    def _backup_corrupted_file(self):
        """
        Backup corrupted player data file by renaming it with timestamp.
        This prevents blocking game startup while preserving the corrupted file for recovery.
        """
        if not self.player_file.exists():
            return
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"player_data.json.corrupt.{timestamp}"
            backup_path = self.save_dir / backup_name
            
            self.player_file.rename(backup_path)
            self.logger.info(f"Corrupted player data backed up to {backup_path}")
        except Exception as e:
            self.logger.error(f"Failed to backup corrupted file: {e}", exc_info=True)
            # If backup fails, try to delete the corrupted file to unblock startup
            try:
                self.player_file.unlink()
                self.logger.warning(f"Deleted corrupted player data file {self.player_file}")
            except Exception as delete_error:
                self.logger.error(f"Failed to delete corrupted file: {delete_error}", exc_info=True)
    
    def get_spawn_position(self) -> Optional[tuple]:
        """
        Get player spawn position from save
        
        Returns:
            (x, y) coordinates in PIXEL WORLD COORDINATES (same format as position in save)
            or None if no save exists
        
        Note:
            This method only returns saved positions. If no save exists, returns None.
            The caller must handle the None case (e.g., create initial save or use default spawn).
        """
        player_data = self.load_player()
        
        if player_data and 'position' in player_data:
            pos = player_data['position']
            return (pos['x'], pos['y'])
        
        # No save exists - return None
        return None
    
    def get_spawn_chunk(self) -> Optional[tuple]:
        """
        Get player spawn chunk coordinates (for faster chunk preloading)
        
        Returns:
            (chunk_x, chunk_y) tuple or None if no save exists
        
        Note:
            This is calculated from spawn position if not stored directly.
            Use this for faster chunk preloading instead of calculating from pixel coordinates.
        """
        player_data = self.load_player()
        
        if player_data and 'spawn_chunk' in player_data:
            chunk = player_data['spawn_chunk']
            return (chunk['x'], chunk['y'])
        
        # Calculate from position if spawn_chunk not available
        if player_data and 'position' in player_data:
            from core import settings
            pos = player_data['position']
            chunk_x = int(pos['x'] // (settings.CHUNK_SIZE * settings.TILE_SIZE))
            chunk_y = int(pos['y'] // (settings.CHUNK_SIZE * settings.TILE_SIZE))
            return (chunk_x, chunk_y)
        
        return None
    
    def player_exists(self) -> bool:
        """
        Check if player data exists and is readable (soft existence check)
        
        Returns:
            True if player file exists AND JSON is readable, False otherwise
        
        Note:
            This performs a "soft" check - not only verifies file existence,
            but also that the JSON content is readable and valid. This prevents
            treating corrupted files as valid saves.
        """
        if not self.player_file.exists():
            return False
        
        # Try to load player data to verify JSON is readable
        try:
            player_data = self.load_player()
            return player_data is not None
        except Exception as e:
            self.logger.warning(f"Player file exists but is not readable: {e}")
            return False
    
    def delete_player(self) -> bool:
        """
        Delete player save data for this slot
        
        Returns:
            True if deletion was successful, False otherwise
        
        Note:
            This permanently deletes the player save file. Use with caution.
            Useful for save slot management in world select menus.
        """
        if not self.player_file.exists():
            self.logger.debug(f"Player file {self.player_file} does not exist, nothing to delete")
            return True  # Already deleted, consider it successful
        
        try:
            self.player_file.unlink()
            self.logger.info(f"Deleted player save file: {self.player_file}")
            return True
        except (IOError, OSError) as e:
            self.logger.error(f"Failed to delete player save file {self.player_file}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error deleting player save file: {e}", exc_info=True)
            return False
