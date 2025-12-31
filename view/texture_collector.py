"""
Scannt data/ Ordner und sammelt alle referenzierten Texturen.
"""
import json
from pathlib import Path
from typing import Set, Dict, List
import logging

logger = logging.getLogger(__name__)

# Fallback logging if logger not configured
def _log(level: str, message: str):
    """Log message with fallback to print."""
    if logger.handlers:
        getattr(logger, level)(message)
    else:
        print(f"[TextureCollector] {message}")

class TextureCollector:
    """Sammelt alle Texture-Referenzen aus data/ Ordner."""
    
    def __init__(self, data_path: str = "data", assets_path: str = "assets"):
        self.data_path = Path(data_path)
        self.assets_path = Path(assets_path)
        self.texture_references = set()  # Set of texture paths
        self.texture_metadata = {}  # texture_id -> metadata
    
    def collect_all_textures(self) -> Dict[str, List[str]]:
        """
        Sammelt alle Texture-Referenzen aus data/ Ordner.
        
        Returns:
            Dictionary mit Kategorien:
            {
                'tiles': ['grass', 'dirt', ...],
                'decorations': ['oak_tree', 'berry_bush', ...],
                'items': ['apple', 'stick', ...],
                'tools': ['wooden_axe', 'iron_axe', ...],
                'entities': ['player', 'zombie', ...]
            }
        """
        _log("info", "[TextureCollector] Starting texture collection from data/...")
        
        collected = {
            'tiles': set(),
            'decorations': set(),
            'items': set(),
            'tools': set(),
            'entities': set(),
        }
        
        # 1. Collect from decorations
        collected['decorations'].update(self._collect_from_decorations())
        
        # 2. Collect from items
        collected['items'].update(self._collect_from_items())
        
        # 3. Collect from tools
        collected['tools'].update(self._collect_from_tools())
        
        # 4. Collect from biomes (tile textures)
        collected['tiles'].update(self._collect_from_biomes())
        
        # 5. Collect from worldgen
        collected['tiles'].update(self._collect_from_worldgen())
        
        # 6. Collect from texture_mapping.json (overlay textures)
        collected['tiles'].update(self._collect_from_texture_mapping())
        
        # Convert sets to sorted lists
        result = {k: sorted(list(v)) for k, v in collected.items()}
        
        # Log statistics
        total = sum(len(v) for v in result.values())
        _log("info", f"[TextureCollector] Collected {total} unique textures:")
        for category, textures in result.items():
            if textures:
                _log("info", f"  - {category}: {len(textures)}")
        
        return result
    
    def _collect_from_decorations(self) -> Set[str]:
        """Sammelt Texturen aus data/decorations/"""
        textures = set()
        decorations_path = self.data_path / "decorations"
        
        if not decorations_path.exists():
            _log("warning", f"Decorations path not found: {decorations_path}")
            return textures
        
        # Rekursiv alle JSON-Dateien finden
        for json_file in decorations_path.rglob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                decoration_id = data.get('decoration_id')
                mod_id = data.get('mod_id', 'core')
                
                # Sprites
                sprites = data.get('sprites', {})
                for sprite_key, sprite_name in sprites.items():
                    if sprite_name:
                        textures.add(f"decoration/{mod_id}/{sprite_name}")
                
                # Rendering shadows
                rendering = data.get('rendering', {})
                shadow = rendering.get('shadow', {})
                if shadow.get('enabled') and shadow.get('sprite'):
                    textures.add(f"decoration/{mod_id}/{shadow['sprite']}")
                
                # Seasons
                seasons = data.get('seasons', {})
                if seasons.get('enabled'):
                    for season_name, season_data in seasons.items():
                        if season_name in ['enabled', 'default_season', 'sprite_base_path']:
                            continue
                        
                        if not isinstance(season_data, dict):
                            continue
                        
                        # Growth stages
                        for stage_key, sprite_name in season_data.get('growth_stages', {}).items():
                            if sprite_name:
                                textures.add(f"decoration/{mod_id}/{sprite_name}")
                        
                        # Growth stages with fruit
                        for stage_key, sprite_name in season_data.get('growth_stages_with_fruit', {}).items():
                            if sprite_name:
                                textures.add(f"decoration/{mod_id}/{sprite_name}")
                        
                        # Growth stages without fruit
                        for stage_key, sprite_name in season_data.get('growth_stages_without_fruit', {}).items():
                            if sprite_name:
                                textures.add(f"decoration/{mod_id}/{sprite_name}")
                        
                        # Damaged sprites
                        for damage_key, sprite_name in season_data.get('damaged_sprites', {}).items():
                            if sprite_name:
                                textures.add(f"decoration/{mod_id}/{sprite_name}")
                        
                        # Snowy variants
                        for stage_key, sprite_name in season_data.get('growth_stages_snowy', {}).items():
                            if sprite_name:
                                textures.add(f"decoration/{mod_id}/{sprite_name}")
                        
                        # Stump variants
                        if season_data.get('stump'):
                            textures.add(f"decoration/{mod_id}/{season_data['stump']}")
                        if season_data.get('stump_snowy'):
                            textures.add(f"decoration/{mod_id}/{season_data['stump_snowy']}")
                
                _log("debug", f"  Collected from decoration: {decoration_id}")
                
            except Exception as e:
                _log("error", f"Error reading decoration file {json_file}: {e}")
        
        return textures
    
    def _collect_from_items(self) -> Set[str]:
        """Sammelt Texturen aus data/items/"""
        textures = set()
        items_path = self.data_path / "items"
        
        if not items_path.exists():
            _log("warning", f"Items path not found: {items_path}")
            return textures
        
        for json_file in items_path.rglob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                item_id = data.get('item_id')
                mod_id = data.get('mod_id', 'core')
                
                # Extract mod_id from item_id if format is "mod_id:item_id"
                if ':' in item_id:
                    mod_id, item_id = item_id.split(':', 1)
                
                # Icon/Sprite
                if data.get('icon'):
                    sprite_name = data['icon']
                    # Remove .png extension if present
                    if sprite_name.endswith('.png'):
                        sprite_name = sprite_name[:-4]
                    textures.add(f"item/{mod_id}/{sprite_name}")
                elif data.get('sprite'):
                    sprite_name = data['sprite']
                    # Handle sprite paths like "food/core/apple" -> extract "apple"
                    if '/' in sprite_name:
                        parts = sprite_name.split('/')
                        sprite_name = parts[-1]
                    # Remove .png extension if present
                    if sprite_name.endswith('.png'):
                        sprite_name = sprite_name[:-4]
                    textures.add(f"item/{mod_id}/{sprite_name}")
                
                _log("debug", f"  Collected from item: {item_id}")
                
            except Exception as e:
                _log("error", f"Error reading item file {json_file}: {e}")
        
        return textures
    
    def _collect_from_tools(self) -> Set[str]:
        """Sammelt Texturen aus data/tools/"""
        textures = set()
        tools_path = self.data_path / "tools"
        
        if not tools_path.exists():
            _log("warning", f"Tools path not found: {tools_path}")
            return textures
        
        for json_file in tools_path.rglob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                tool_id = data.get('tool_id')
                mod_id = data.get('mod_id', 'core')
                
                # Skip if tool_id is missing
                if not tool_id:
                    _log("warning", f"Tool file {json_file} missing tool_id, skipping")
                    continue
                
                # Extract mod_id from tool_id if format is "mod_id:tool_id"
                if isinstance(tool_id, str) and ':' in tool_id:
                    mod_id, tool_id = tool_id.split(':', 1)
                
                # Icon/Sprite
                if data.get('icon'):
                    sprite_name = data['icon']
                    # Remove .png extension if present
                    if sprite_name.endswith('.png'):
                        sprite_name = sprite_name[:-4]
                    textures.add(f"tool/{mod_id}/{sprite_name}")
                elif data.get('sprite'):
                    sprite_name = data['sprite']
                    # Remove .png extension if present
                    if sprite_name.endswith('.png'):
                        sprite_name = sprite_name[:-4]
                    textures.add(f"tool/{mod_id}/{sprite_name}")
                
                _log("debug", f"  Collected from tool: {tool_id}")
                
            except Exception as e:
                _log("error", f"Error reading tool file {json_file}: {e}")
        
        return textures
    
    def _collect_from_biomes(self) -> Set[str]:
        """Sammelt Tile-Texturen aus data/biomes/"""
        textures = set()
        biomes_path = self.data_path / "biomes"
        
        if not biomes_path.exists():
            return textures
        
        for json_file in biomes_path.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Ground tiles
                for tile_config in data.get('ground_tiles', []):
                    if tile_config.get('tile_id'):
                        tile_id = tile_config['tile_id']
                        # Handle tile_id format like "terrain:plains" -> extract "plains"
                        if ':' in tile_id:
                            _, tile_id = tile_id.split(':', 1)
                        # Use format: tile/core/{tile_id} (3 parts for builder compatibility)
                        textures.add(f"tile/core/{tile_id}")
                
            except Exception as e:
                _log("error", f"Error reading biome file {json_file}: {e}")
        
        return textures
    
    def _collect_from_worldgen(self) -> Set[str]:
        """Sammelt Tile-Texturen aus data/worldgen/biomes.json"""
        textures = set()
        biomes_file = self.data_path / "worldgen" / "biomes.json"
        
        if not biomes_file.exists():
            return textures
        
        try:
            with open(biomes_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for biome_id, biome_data in data.get('biomes', {}).items():
                # Base tile
                if biome_data.get('base_tile'):
                    tile_id = biome_data['base_tile']
                    if ':' in tile_id:
                        _, tile_id = tile_id.split(':', 1)
                    # Use format: tile/core/{tile_id} (3 parts for builder compatibility)
                    textures.add(f"tile/core/{tile_id}")
                
                # Tile variants
                for variant in biome_data.get('tile_variants', []):
                    if variant.get('tile_id'):
                        tile_id = variant['tile_id']
                        if ':' in tile_id:
                            _, tile_id = tile_id.split(':', 1)
                        # Use format: tile/core/{tile_id} (3 parts for builder compatibility)
                        textures.add(f"tile/core/{tile_id}")
        
        except Exception as e:
            _log("error", f"Error reading worldgen biomes: {e}")
        
        return textures
    
    def _collect_from_texture_mapping(self) -> Set[str]:
        """Sammelt Tile-Texturen aus data/textures/texture_mapping.json (inkl. Overlays)."""
        textures = set()
        mapping_file = self.data_path / "textures" / "texture_mapping.json"
        
        if not mapping_file.exists():
            return textures
        
        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            texture_mappings = data.get('texture_mappings', {})
            
            for tile_id, mapping in texture_mappings.items():
                # Base texture
                base_texture = mapping.get('base_texture')
                if base_texture:
                    # Use format: tile/core/{base_texture} (3 parts for builder compatibility)
                    textures.add(f"tile/core/{base_texture}")
                
                # Overlay textures from variance_system
                variance_system = mapping.get('variance_system', {})
                growth_patterns = variance_system.get('growth_patterns', [])
                
                for pattern in growth_patterns:
                    overlay = pattern.get('overlay')
                    if overlay:
                        # Use format: tile/core/{overlay} (3 parts for builder compatibility)
                        textures.add(f"tile/core/{overlay}")
        
        except Exception as e:
            _log("error", f"Error reading texture mapping: {e}")
        
        return textures
    
    def save_texture_list(self, output_file: str = "data/texture_references.json"):
        """Speichert gesammelte Texturen als JSON (für Caching)."""
        collected = self.collect_all_textures()
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(collected, f, indent=2)
        
        _log("info", f"[TextureCollector] Saved texture list to: {output_file}")
        
        return collected
    
    def load_texture_list(self, input_file: str = "data/texture_references.json") -> Dict[str, List[str]]:
        """Lädt gesammelte Texturen aus Cache."""
        input_path = Path(input_file)
        
        if not input_path.exists():
            _log("info", f"Cache file not found: {input_file}, will collect from scratch")
            return {}
        
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            _log("info", f"[TextureCollector] Loaded texture list from cache: {input_file}")
            return data
        
        except Exception as e:
            _log("error", f"Error loading texture list from {input_file}: {e}")
            return {}
