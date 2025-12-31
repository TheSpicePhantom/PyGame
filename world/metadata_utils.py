"""
Metadata Utilities: Helper functions for tile metadata access
"""
from typing import Dict, Optional, List, Any


def has_metadata(tile: dict) -> bool:
    """
    Check if tile has any metadata.
    
    Args:
        tile: Tile dictionary
        
    Returns:
        True if tile has metadata, False otherwise
    """
    return 'metadata' in tile and tile['metadata']


def get_metadata(tile: dict, metadata_type: str) -> Optional[dict]:
    """
    Get specific metadata type from tile.
    
    Args:
        tile: Tile dictionary
        metadata_type: Type of metadata ('decoration', 'tile_entity', 'entities', 'texture_override', 'state')
        
    Returns:
        Metadata dict or None if not found
    """
    if not has_metadata(tile):
        return None
    return tile['metadata'].get(metadata_type)


def set_metadata(tile: dict, metadata_type: str, data: dict) -> None:
    """
    Set metadata for tile.
    
    Args:
        tile: Tile dictionary
        metadata_type: Type of metadata ('decoration', 'tile_entity', 'entities', 'texture_override', 'state')
        data: Metadata data dict
    """
    if 'metadata' not in tile:
        tile['metadata'] = {}
    tile['metadata'][metadata_type] = data


def remove_metadata(tile: dict, metadata_type: str) -> None:
    """
    Remove specific metadata type from tile.
    
    Args:
        tile: Tile dictionary
        metadata_type: Type of metadata to remove
    """
    if has_metadata(tile):
        tile['metadata'].pop(metadata_type, None)
        # Remove metadata dict if empty
        if not tile['metadata']:
            del tile['metadata']


def clear_metadata(tile: dict) -> None:
    """
    Remove all metadata from tile.
    
    Args:
        tile: Tile dictionary
    """
    if 'metadata' in tile:
        del tile['metadata']


def migrate_decoration_to_metadata(tile: dict) -> None:
    """
    Migrate old tile['decoration'] to tile['metadata']['decoration'].
    
    Args:
        tile: Tile dictionary
    """
    if 'decoration' in tile and tile['decoration']:
        set_metadata(tile, 'decoration', tile['decoration'])
        del tile['decoration']
