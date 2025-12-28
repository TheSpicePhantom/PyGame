"""
Decoration Registry: Central registry for all decoration types, loot tables, and tags.
Supports hot-reload for development (F5 key).
"""
import json
import os
from typing import Dict, List, Optional
from pathlib import Path


class DecorationRegistry:
    """Central registry for all decoration types."""
    
    _decorations: Dict[str, dict] = {}
    _loot_tables: Dict[str, dict] = {}
    _tags: Dict[str, List[str]] = {}
    _biomes: Dict[str, dict] = {}
    
    @classmethod
    def load_all(cls, data_path: str = "data"):
        """
        Load all decorations, loot tables, tags, and biome extensions from JSON files.
        
        Args:
            data_path: Base path to data directory
        """
        # Clear existing data
        cls._decorations.clear()
        cls._loot_tables.clear()
        cls._tags.clear()
        cls._biomes.clear()
        
        # Load tags
        cls._load_tags(os.path.join(data_path, "tags"))
        
        # Load loot tables
        cls._load_loot_tables(os.path.join(data_path, "loot_tables"))
        
        # Load decorations (recursively from subdirs)
        cls._load_decorations(os.path.join(data_path, "decorations"))
        
        # Load biome extensions
        cls._load_biomes(os.path.join(data_path, "biomes"))
        
        print(f"[DecorationRegistry] Loaded {len(cls._decorations)} decorations, "
              f"{len(cls._loot_tables)} loot tables, {len(cls._tags)} tags, "
              f"{len(cls._biomes)} biome extensions")
    
    @classmethod
    def reload(cls):
        """
        Reload all decorations from disk (dev-only, called via F5 key).
        Useful for rapid iteration during development.
        """
        print("[DecorationRegistry] Reloading all decoration data...")
        cls.load_all()
        print("[DecorationRegistry] Reload complete!")
    
    @classmethod
    def _load_decorations(cls, path: str):
        """Recursively load decoration JSONs from all subdirectories."""
        if not os.path.exists(path):
            print(f"[DecorationRegistry] Warning: Decorations path does not exist: {path}")
            return
        
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith('.json'):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            decoration_id = data.get('decoration_id')
                            if decoration_id:
                                cls._decorations[decoration_id] = data
                                print(f"  Loaded decoration: {decoration_id}")
                            else:
                                print(f"  Warning: {filepath} missing 'decoration_id' field")
                    except Exception as e:
                        print(f"  Error loading {filepath}: {e}")
    
    @classmethod
    def _load_loot_tables(cls, path: str):
        """Load loot table JSONs."""
        if not os.path.exists(path):
            print(f"[DecorationRegistry] Warning: Loot tables path does not exist: {path}")
            return
        
        # Try to import ItemRegistry for validation
        try:
            from world.item_registry import ItemRegistry
            item_registry_available = True
        except ImportError:
            item_registry_available = False
        
        for file in os.listdir(path):
            if file.endswith('.json'):
                filepath = os.path.join(path, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        loot_table_id = data.get('loot_table_id')
                        if loot_table_id:
                            # Validate item_ids in entries if ItemRegistry is available
                            if item_registry_available:
                                entries = data.get('entries', [])
                                for entry in entries:
                                    item_id = entry.get('item_id')
                                    if item_id and not ItemRegistry.get(item_id):
                                        print(f"  Warning: {filepath} references unknown item_id '{item_id}' in loot table '{loot_table_id}'")
                            
                            cls._loot_tables[loot_table_id] = data
                        else:
                            print(f"  Warning: {filepath} missing 'loot_table_id' field")
                except Exception as e:
                    print(f"  Error loading {filepath}: {e}")
    
    @classmethod
    def _load_tags(cls, path: str):
        """Load tag JSONs."""
        if not os.path.exists(path):
            print(f"[DecorationRegistry] Warning: Tags path does not exist: {path}")
            return
        
        for file in os.listdir(path):
            if file.endswith('.json'):
                filepath = os.path.join(path, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        tag_id = data.get('tag_id')
                        members = data.get('members', [])
                        if tag_id:
                            cls._tags[tag_id] = members
                        else:
                            print(f"  Warning: {filepath} missing 'tag_id' field")
                except Exception as e:
                    print(f"  Error loading {filepath}: {e}")
    
    @classmethod
    def _load_biomes(cls, path: str):
        """Load biome extension JSONs."""
        if not os.path.exists(path):
            print(f"[DecorationRegistry] Warning: Biomes path does not exist: {path}")
            return
        
        for file in os.listdir(path):
            if file.endswith('.json'):
                filepath = os.path.join(path, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        biome_id = data.get('biome_id')
                        if biome_id:
                            cls._biomes[biome_id] = data
                            print(f"  Loaded biome extension: {biome_id} from {file}")
                        else:
                            print(f"  Warning: {filepath} missing 'biome_id' field")
                except Exception as e:
                    print(f"  Error loading {filepath}: {e}")
    
    @classmethod
    def get(cls, decoration_id: str) -> Optional[dict]:
        """
        Get decoration config by ID.
        
        Args:
            decoration_id: Decoration identifier
            
        Returns:
            Decoration config dict or None if not found
        """
        return cls._decorations.get(decoration_id)
    
    @classmethod
    def get_all(cls) -> Dict[str, dict]:
        """
        Get all decoration configs.
        
        Returns:
            Dictionary mapping decoration_id to config dict
        """
        return cls._decorations.copy()
    
    @classmethod
    def create(cls, decoration_id: str):
        """
        Create decoration instance from config.
        
        Args:
            decoration_id: Decoration identifier
            
        Returns:
            Decoration instance
            
        Raises:
            ValueError: If decoration not found
        """
        from world.decoration import Decoration
        
        config = cls.get(decoration_id)
        if not config:
            raise ValueError(f"Unknown decoration: {decoration_id}")
        
        return Decoration(config)
    
    @classmethod
    def get_loot_table(cls, loot_table_id: str) -> Optional[dict]:
        """
        Get loot table by ID.
        
        Args:
            loot_table_id: Loot table identifier
            
        Returns:
            Loot table dict or None if not found
        """
        return cls._loot_tables.get(loot_table_id)
    
    @classmethod
    def has_tag(cls, decoration_id: str, tag: str) -> bool:
        """
        Check if decoration has specific tag.
        
        Args:
            decoration_id: Decoration identifier
            tag: Tag identifier
            
        Returns:
            True if decoration has tag, False otherwise
        """
        return decoration_id in cls._tags.get(tag, [])
    
    @classmethod
    def get_biome_extensions(cls, biome_id: str) -> Optional[dict]:
        """
        Get biome extension config by biome ID.
        
        Args:
            biome_id: Biome identifier (e.g., "terrain:forest")
            
        Returns:
            Biome extension dict or None if not found
        """
        return cls._biomes.get(biome_id)
    
    @classmethod
    def get_all_decoration_ids(cls) -> List[str]:
        """Get list of all loaded decoration IDs."""
        return list(cls._decorations.keys())
    
    @classmethod
    def get_stats(cls) -> dict:
        """Get registry statistics for debugging."""
        return {
            'decorations_count': len(cls._decorations),
            'loot_tables_count': len(cls._loot_tables),
            'tags_count': len(cls._tags),
            'biomes_count': len(cls._biomes),
            'decoration_ids': list(cls._decorations.keys())
        }
