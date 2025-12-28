"""
Item Registry: Central registry for all item types.
Supports hot-reload for development (F5 key).
"""
import json
import os
from typing import Dict, Optional
from pathlib import Path


class ItemRegistry:
    """Central registry for all item types."""
    
    _items: Dict[str, dict] = {}
    
    @classmethod
    def load_all(cls, data_path: str = "data/items"):
        """
        Load all items from JSON files recursively.
        Also loads tools from data/tools/ directory.
        
        Args:
            data_path: Base path to items directory
        """
        # Clear existing data
        cls._items.clear()
        
        # Load items (recursively from subdirs)
        cls._load_items(data_path)
        
        # Also load tools from data/tools/ (if exists)
        tools_path = "data/tools"
        if os.path.exists(tools_path):
            cls._load_items(tools_path)
        
        print(f"[ItemRegistry] Loaded {len(cls._items)} items")
    
    @classmethod
    def reload(cls):
        """
        Reload all items from disk (dev-only, called via F5 key).
        Useful for rapid iteration during development.
        """
        print("[ItemRegistry] Reloading all item data...")
        cls.load_all()
        print("[ItemRegistry] Reload complete!")
    
    @classmethod
    def _load_items(cls, path: str):
        """Recursively load item JSONs from all subdirectories."""
        if not os.path.exists(path):
            print(f"[ItemRegistry] Warning: Items path does not exist: {path}")
            return
        
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith('.json'):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            item_id = data.get('item_id')
                            if item_id:
                                # Extract mod_id from path (e.g., data/items/core/wood.json -> "core")
                                # Path structure: data/items/{mod_id}/... or data/tools/{mod_id}/...
                                path_parts = Path(root).parts
                                mod_id = "core"  # Default
                                if "items" in path_parts:
                                    items_index = path_parts.index("items")
                                    if items_index + 1 < len(path_parts):
                                        mod_id = path_parts[items_index + 1]
                                elif "tools" in path_parts:
                                    tools_index = path_parts.index("tools")
                                    if tools_index + 1 < len(path_parts):
                                        mod_id = path_parts[tools_index + 1]
                                
                                # Set mod_id in item config if not already set
                                if 'mod_id' not in data:
                                    data['mod_id'] = mod_id
                                
                                # Validate item before adding
                                if cls.validate_item(data):
                                    cls._items[item_id] = data
                                    print(f"  Loaded item: {item_id} (mod_id: {mod_id})")
                                else:
                                    print(f"  Warning: {filepath} failed validation")
                            else:
                                print(f"  Warning: {filepath} missing 'item_id' field")
                    except Exception as e:
                        print(f"  Error loading {filepath}: {e}")
    
    @classmethod
    def validate_item(cls, item_config: dict) -> bool:
        """
        Validate item configuration.
        
        Args:
            item_config: Item configuration dictionary
            
        Returns:
            True if valid, False otherwise
        """
        # Check required fields
        if not item_config.get('item_id'):
            return False
        
        if not item_config.get('sprite'):
            print(f"  Validation error: Missing 'sprite' field for item {item_config.get('item_id')}")
            return False
        
        # Check max_stack_size
        max_stack = item_config.get('max_stack_size', 0)
        if max_stack <= 0:
            print(f"  Validation error: max_stack_size must be > 0 for item {item_config.get('item_id')}")
            return False
        
        # Check if sprite file exists (with mod_id support)
        sprite_name = item_config.get('sprite')
        mod_id = item_config.get('mod_id', 'core')
        sprite_path = Path("assets/items") / mod_id / sprite_name
        if not sprite_path.exists():
            print(f"  Validation warning: Sprite file not found: {sprite_path} for item {item_config.get('item_id')}")
            # Don't fail validation, just warn (sprite might be added later)
        
        return True
    
    @classmethod
    def get(cls, item_id: str) -> Optional[dict]:
        """
        Get item config by ID.
        
        Args:
            item_id: Item identifier
            
        Returns:
            Item config dict or None if not found
        """
        return cls._items.get(item_id)
    
    @classmethod
    def get_all(cls) -> Dict[str, dict]:
        """
        Get all item configs.
        
        Returns:
            Dictionary mapping item_id to config dict
        """
        return cls._items.copy()
    
    @classmethod
    def get_sprite_path(cls, item_id: str) -> Optional[str]:
        """
        Get sprite file path for item.
        
        Args:
            item_id: Item identifier
            
        Returns:
            Path string (e.g., "assets/items/core/wood.png") or None if not found
        """
        item_config = cls.get(item_id)
        if not item_config:
            return None
        
        sprite_name = item_config.get('sprite')
        if not sprite_name:
            return None
        
        mod_id = item_config.get('mod_id', 'core')
        return f"assets/items/{mod_id}/{sprite_name}"
    
    @classmethod
    def get_all_item_ids(cls) -> list:
        """Get list of all loaded item IDs."""
        return list(cls._items.keys())
    
    @classmethod
    def get_stats(cls) -> dict:
        """Get registry statistics for debugging."""
        return {
            'items_count': len(cls._items),
            'item_ids': list(cls._items.keys())
        }

