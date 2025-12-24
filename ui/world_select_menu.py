"""
World Select Menu: Minecraft-style world selection with preview
"""
import pyglet
from pyglet.window import key, mouse
from pathlib import Path
import json
import time
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from core import settings
from world.terrain_generator import TerrainGenerator
from world.player_data_manager import PlayerDataManager
import pyglet.shapes


class SlotView:
    """Cached UI elements for a slot - avoids recreating shapes/labels every frame"""
    
    def __init__(self, slot_x: int, slot_y: int, slot_width: int, slot_height: int,
                 preview_x: int, preview_y: int, info_x: int, info_y: int,
                 slot_info: 'WorldSlotInfo', font_names: Dict[str, Optional[str]], font_sizes: Dict[str, int]):
        """
        Initialize cached UI elements for a slot
        
        Args:
            slot_x, slot_y: Slot position
            slot_width, slot_height: Slot dimensions
            preview_x, preview_y: Preview position
            info_x, info_y: Info text position
            slot_info: WorldSlotInfo instance
            font_names: Dict with 'slot' and 'info' font names
            font_sizes: Dict with 'slot' and 'info' font sizes
        """
        self.slot_x = slot_x
        self.slot_y = slot_y
        self.slot_width = slot_width
        self.slot_height = slot_height
        self.preview_x = preview_x
        self.preview_y = preview_y
        self.info_x = info_x
        self.info_y = info_y
        
        # Create background rectangle
        self.bg_rect = pyglet.shapes.Rectangle(
            slot_x, slot_y, slot_width, slot_height,
            color=(60, 60, 60)  # Default color, will be updated
        )
        self.bg_rect.opacity = 200
        
        # Try to create BorderedRectangle, fallback to lines
        self.border_rect = None
        self.border_lines = []
        try:
            self.border_rect = pyglet.shapes.BorderedRectangle(
                slot_x, slot_y, slot_width, slot_height,
                border=2,
                color=(60, 60, 60),
                border_color=(150, 150, 150)
            )
            self.border_rect.opacity = 255
        except AttributeError:
            # Fallback: create border lines
            self.border_lines = [
                pyglet.shapes.Line(slot_x, slot_y, slot_x + slot_width, slot_y, width=2, color=(150, 150, 150)),
                pyglet.shapes.Line(slot_x + slot_width, slot_y, slot_x + slot_width, slot_y + slot_height, width=2, color=(150, 150, 150)),
                pyglet.shapes.Line(slot_x + slot_width, slot_y + slot_height, slot_x, slot_y + slot_height, width=2, color=(150, 150, 150)),
                pyglet.shapes.Line(slot_x, slot_y + slot_height, slot_x, slot_y, width=2, color=(150, 150, 150))
            ]
        
        # Create labels (static text, will be updated when slot info changes)
        slot_name = slot_info.world_name if slot_info.exists and slot_info.world_name else slot_info.world_dir_name if slot_info.exists else "New World"
        
        self.name_label = pyglet.text.Label(
            slot_name,
            font_name=font_names.get('slot'),
            font_size=font_sizes.get('slot', 24),
            color=(255, 255, 255, 255),
            x=info_x,
            y=info_y,
            anchor_x='left',
            anchor_y='top'
        )
        
        # Create info labels (only if slot exists)
        if slot_info.exists:
            self.seed_label = pyglet.text.Label(
                f"Seed: {slot_info.seed}",
                font_name=font_names.get('info'),
                font_size=font_sizes.get('info', 18),
                color=(200, 200, 200, 255),
                x=info_x,
                y=info_y - 30,
                anchor_x='left',
                anchor_y='top'
            )
            
            self.size_label = pyglet.text.Label(
                f"Size: {slot_info.world_size_mb:.1f} MB | Chunks: {slot_info.chunks_generated}",
                font_name=font_names.get('info'),
                font_size=font_sizes.get('info', 18),
                color=(200, 200, 200, 255),
                x=info_x,
                y=info_y - 55,
                anchor_x='left',
                anchor_y='top'
            )
            
            date_text = f"Last played: {slot_info.last_save_date}" if slot_info.last_save_date else ""
            self.date_label = pyglet.text.Label(
                date_text,
                font_name=font_names.get('info'),
                font_size=font_sizes.get('info', 18),
                color=(200, 200, 200, 255),
                x=info_x,
                y=info_y - 80,
                anchor_x='left',
                anchor_y='top'
            ) if date_text else None
            
            self.empty_label = None
        else:
            self.seed_label = None
            self.size_label = None
            self.date_label = None
            self.empty_label = pyglet.text.Label(
                "New World",
                font_name=font_names.get('info'),
                font_size=font_sizes.get('info', 18),
                color=(150, 150, 150, 255),
                x=info_x,
                y=info_y - 30,
                anchor_x='left',
                anchor_y='top'
            )
        
        # Hint label (always created, visibility controlled)
        self.hint_label = pyglet.text.Label(
            "Ctrl+R to rename, Delete to delete",
            font_name=font_names.get('info'),
            font_size=14,
            color=(150, 150, 150, 255),
            x=info_x,
            y=slot_y + 10,
            anchor_x='left',
            anchor_y='bottom'
        )
        self.hint_label.visible = False  # Hidden by default
    
    def update_colors(self, bg_color: Tuple[int, int, int, int], border_color: Tuple[int, int, int, int]):
        """Update colors of background and border"""
        self.bg_rect.color = (bg_color[0], bg_color[1], bg_color[2])
        self.bg_rect.opacity = bg_color[3]
        
        if self.border_rect:
            self.border_rect.color = (bg_color[0], bg_color[1], bg_color[2])
            self.border_rect.border_color = (border_color[0], border_color[1], border_color[2])
            self.border_rect.opacity = border_color[3]
        else:
            for line in self.border_lines:
                line.color = (border_color[0], border_color[1], border_color[2])
    
    def update_name(self, name: str, color: Tuple[int, int, int, int] = (255, 255, 255, 255)):
        """Update slot name label"""
        self.name_label.text = name
        self.name_label.color = color
    
    def update_position(self, slot_y: int):
        """Update slot position (when slots are reordered)"""
        self.slot_y = slot_y
        dy = slot_y - self.bg_rect.y
        
        # Update all elements
        self.bg_rect.y = slot_y
        if self.border_rect:
            self.border_rect.y = slot_y
        else:
            for line in self.border_lines:
                line.y += dy
                if hasattr(line, 'y2'):
                    line.y2 += dy
        
        self.preview_y = slot_y + 10
        self.info_y = slot_y + self.slot_height - 30
        
        # Update label positions
        self.name_label.y = self.info_y
        if self.seed_label:
            self.seed_label.y = self.info_y - 30
        if self.size_label:
            self.size_label.y = self.info_y - 55
        if self.date_label:
            self.date_label.y = self.info_y - 80
        if self.empty_label:
            self.empty_label.y = self.info_y - 30
        if self.hint_label:
            self.hint_label.y = slot_y + 10
    
    
    def draw(self):
        """Draw all cached UI elements"""
        self.bg_rect.draw()
        
        if self.border_rect:
            self.border_rect.draw()
        else:
            for line in self.border_lines:
                line.draw()
        
        self.name_label.draw()
        
        if self.seed_label:
            self.seed_label.draw()
        if self.size_label:
            self.size_label.draw()
        if self.date_label:
            self.date_label.draw()
        if self.empty_label:
            self.empty_label.draw()
        if self.hint_label:
            self.hint_label.draw()


class WorldSlotInfo:
    """Information about a world save slot"""
    
    def __init__(self, world_dir_name: str):
        from world.world_utils import sanitize_world_name
        self.world_dir_name = world_dir_name  # Sanitized directory name
        self.world_id = world_dir_name  # Use directory name as world_id
        self.save_dir = Path(f"saves/{world_dir_name}")
        self.metadata_file = self.save_dir / "world_metadata.json"
        self.player_file = self.save_dir / "player_data.json"
        
        self.exists = False
        self.seed: Optional[int] = None
        self.playtime_seconds = 0
        self.last_save_date: Optional[str] = None
        self.last_played_at: Optional[str] = None
        self.created_at: Optional[str] = None
        self.spawn_position: Optional[Tuple[float, float]] = None
        self.spawn_chunk: Optional[List[int]] = None
        self.chunks_generated = 0
        self.world_name: Optional[str] = None
        self.world_size_mb = 0.0
        self.region_files = 0
        
        self._load_info()
    
    def _load_info(self):
        """Load world information from files"""
        if not self.metadata_file.exists():
            return
        
        try:
            # Load metadata
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            # Handle new format (version 1)
            if metadata.get("version") == 1:
                self.world_id = metadata.get("world_id", self.world_id)
                self.world_name = metadata.get("name", self.world_dir_name)
                self.created_at = metadata.get("created_at")
                self.last_played_at = metadata.get("last_played_at")
                
                # Extract seed from new structure
                seed_data = metadata.get("seed", {})
                if isinstance(seed_data, dict):
                    self.seed = seed_data.get("world_seed")
                else:
                    self.seed = seed_data
                
                # Extract size information
                size_data = metadata.get("size", {})
                self.chunks_generated = size_data.get("chunks_generated", 0)
                self.world_size_mb = size_data.get("world_size_mb", 0.0)
                self.region_files = size_data.get("region_files", 0)
                
                # Extract spawn chunk
                chunks_data = metadata.get("chunks", {})
                self.spawn_chunk = chunks_data.get("spawn_chunk")
                
                # Convert spawn chunk to pixel position if available
                if self.spawn_chunk:
                    from core import settings
                    chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
                    self.spawn_position = (
                        self.spawn_chunk[0] * chunk_size_pixels,
                        self.spawn_chunk[1] * chunk_size_pixels
                    )
                
                # Format last played date
                if self.last_played_at:
                    try:
                        dt = datetime.fromisoformat(self.last_played_at.replace('Z', '+00:00'))
                        self.last_save_date = dt.strftime("%Y-%m-%d %H:%M")
                    except:
                        # Fallback to file modification time
                        mtime = self.metadata_file.stat().st_mtime
                        self.last_save_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            else:
                # Old format - migrate on the fly
                self.seed = metadata.get('seed')
                self.chunks_generated = metadata.get('chunks_generated', 0)
                self.world_name = metadata.get('world_name', self.world_dir_name)
                
                # Try to get playtime (might not exist in old format)
                self.playtime_seconds = metadata.get('playtime_seconds', 0)
            
            # Load player data for spawn position (fallback if not in metadata)
            if not self.spawn_position and self.player_file.exists():
                try:
                    with open(self.player_file, 'r', encoding='utf-8') as f:
                        player_data = json.load(f)
                        position = player_data.get('position', [0, 0])
                        self.spawn_position = (float(position[0]), float(position[1]))
                        
                        # Get file modification time as last save date if not set
                        if not self.last_save_date:
                            mtime = self.player_file.stat().st_mtime
                            self.last_save_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass
            
            self.exists = True
        except Exception as e:
            print(f"[WorldSelect] Error loading world info for world '{self.world_dir_name}': {e}")
            import traceback
            traceback.print_exc()
    
    def get_playtime_formatted(self) -> str:
        """Format playtime as human-readable string"""
        hours = self.playtime_seconds // 3600
        minutes = (self.playtime_seconds % 3600) // 60
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    
    def delete(self) -> bool:
        """Delete this world save slot"""
        try:
            import shutil
            if self.save_dir.exists():
                shutil.rmtree(self.save_dir)
                self.exists = False
                return True
        except Exception as e:
            print(f"[WorldSelect] Error deleting world '{self.world_dir_name}': {e}")
        return False


class WorldSelectMenu:
    """Minecraft-style world selection menu with preview"""
    
    def __init__(self, window_width: int, window_height: int, renderer):
        """
        Initialize World Select Menu
        
        Args:
            window_width: Window width in pixels
            window_height: Window height in pixels
            renderer: ModernGLRenderer instance for rendering
        """
        self.window_width = window_width
        self.window_height = window_height
        self.renderer = renderer
        self.active = False
        
        # Load save slot information
        self.slots: List[WorldSlotInfo] = []
        self.selected_slot: Optional[int] = None
        self.hovered_slot: Optional[int] = None
        self.create_button_hovered = False
        self.quit_button_hovered = False
        
        # Preview generation
        self.preview_cache: Dict[str, List] = {}  # world_id -> preview chunks data
        self.preview_size = 5  # 5x5 chunks preview
        
        # UI layout
        self.slot_width = 600
        self.slot_height = 200
        self.slot_spacing = 20
        self.preview_size_pixels = 150  # Preview size in pixels
        
        # Cached slot views (index -> SlotView)
        self.slot_views: Dict[int, SlotView] = {}
        
        # Fonts (pyglet doesn't support bold parameter in load, use bold in Label instead)
        # Try to use system fonts, fallback to None (default) if not available
        self.title_font_name = None  # None = default font
        self.slot_font_name = None
        self.info_font_name = None
        
        self.title_font_size = 48
        self.slot_font_size = 24
        self.info_font_size = 18
        
        # Action buttons
        self.delete_mode = False
        self.rename_mode = False
        self.renaming_slot: Optional[int] = None
        self.rename_text = ""
        
        # Profiling (optional, for performance measurement)
        self.profiling_enabled = False  # Set to True to enable profiling
        self.draw_stats = {
            'total_slots': 0,
            'visible_slots': 0,
            'draw_calls': 0
        }
        
        # Create cached title label
        self.title_label = pyglet.text.Label(
            "Select World",
            font_name=self.title_font_name,
            font_size=self.title_font_size,
            color=(255, 255, 255, 255),
            x=self.window_width // 2,
            y=self.window_height - 50,
            anchor_x='center',
            anchor_y='top'
        )
        
        # Create cached create button UI elements
        button_y = 150  # Moved up to make room for quit button below
        button_height = 60
        button_x = (self.window_width - self.slot_width) // 2
        
        self.create_button_bg_rect = pyglet.shapes.Rectangle(
            button_x, button_y, self.slot_width, button_height,
            color=(60, 100, 60)  # Default dark green
        )
        
        # Try to create BorderedRectangle for create button, fallback to lines
        self.create_button_border_rect = None
        self.create_button_border_lines = []
        try:
            self.create_button_border_rect = pyglet.shapes.BorderedRectangle(
                button_x, button_y, self.slot_width, button_height,
                border=3,
                color=(60, 100, 60),
                border_color=(100, 200, 100)
            )
        except AttributeError:
            # Fallback: create border lines
            self.create_button_border_lines = [
                pyglet.shapes.Line(button_x, button_y, button_x + self.slot_width, button_y, width=3, color=(100, 200, 100)),
                pyglet.shapes.Line(button_x + self.slot_width, button_y, button_x + self.slot_width, button_y + button_height, width=3, color=(100, 200, 100)),
                pyglet.shapes.Line(button_x + self.slot_width, button_y + button_height, button_x, button_y + button_height, width=3, color=(100, 200, 100)),
                pyglet.shapes.Line(button_x, button_y + button_height, button_x, button_y, width=3, color=(100, 200, 100))
            ]
        
        self.create_button_label = pyglet.text.Label(
            "+ Create New World",
            font_name=self.slot_font_name,
            font_size=28,
            color=(255, 255, 255, 255),
            x=button_x + self.slot_width // 2,
            y=button_y + button_height // 2,
            anchor_x='center',
            anchor_y='center'
        )
        
        # Create cached quit button UI elements (below create button)
        quit_button_y = button_y - (button_height + self.slot_spacing)
        self.quit_button_bg_rect = pyglet.shapes.Rectangle(
            button_x, quit_button_y, self.slot_width, button_height,
            color=(100, 60, 60)  # Default dark red
        )
        
        # Try to create BorderedRectangle for quit button, fallback to lines
        self.quit_button_border_rect = None
        self.quit_button_border_lines = []
        try:
            self.quit_button_border_rect = pyglet.shapes.BorderedRectangle(
                button_x, quit_button_y, self.slot_width, button_height,
                border=3,
                color=(100, 60, 60),
                border_color=(200, 100, 100)
            )
        except AttributeError:
            # Fallback: create border lines
            self.quit_button_border_lines = [
                pyglet.shapes.Line(button_x, quit_button_y, button_x + self.slot_width, quit_button_y, width=3, color=(200, 100, 100)),
                pyglet.shapes.Line(button_x + self.slot_width, quit_button_y, button_x + self.slot_width, quit_button_y + button_height, width=3, color=(200, 100, 100)),
                pyglet.shapes.Line(button_x + self.slot_width, quit_button_y + button_height, button_x, quit_button_y + button_height, width=3, color=(200, 100, 100)),
                pyglet.shapes.Line(button_x, quit_button_y + button_height, button_x, quit_button_y, width=3, color=(200, 100, 100))
            ]
        
        self.quit_button_label = pyglet.text.Label(
            "Quit",
            font_name=self.slot_font_name,
            font_size=28,
            color=(255, 255, 255, 255),
            x=button_x + self.slot_width // 2,
            y=quit_button_y + button_height // 2,
            anchor_x='center',
            anchor_y='center'
        )
        
        self.refresh_slots()
    
    def refresh_slots(self):
        """Refresh save slot information - scan all worlds in saves/ directory"""
        self.slots = []
        saves_dir = Path("saves")
        
        if not saves_dir.exists():
            # Clear slot views if no saves directory
            self.slot_views.clear()
            return
        
        # Scan all directories in saves/ folder
        for save_dir in saves_dir.iterdir():
            if not save_dir.is_dir():
                continue
            
            # Skip hidden directories and system files
            if save_dir.name.startswith('.'):
                continue
            
            # Use directory name as world identifier (new format)
            # Also support old slot_X format for backward compatibility
            world_dir_name = save_dir.name
            
            slot_info = WorldSlotInfo(world_dir_name)
            self.slots.append(slot_info)
            
            # Generate preview if slot exists
            if slot_info.exists and slot_info.seed is not None:
                self._generate_preview(slot_info.world_id, slot_info.seed, slot_info.spawn_position)
        
        # Sort by last played date (newest first)
        self.slots.sort(key=lambda s: s.last_played_at or "", reverse=True)
        
        # Create/update cached slot views
        self._update_slot_views()
    
    def _update_slot_views(self):
        """Create or update cached slot views"""
        start_y = 200
        slot_x = (self.window_width - self.slot_width) // 2
        preview_x = slot_x + 10
        info_x = slot_x + self.preview_size_pixels + 30
        
        font_names = {
            'slot': self.slot_font_name,
            'info': self.info_font_name
        }
        font_sizes = {
            'slot': self.slot_font_size,
            'info': self.info_font_size
        }
        
        # Update existing views or create new ones
        for i, slot_info in enumerate(self.slots):
            slot_y = start_y + i * (self.slot_height + self.slot_spacing)
            info_y = slot_y + self.slot_height - 30
            
            if i in self.slot_views:
                # Update existing view
                self.slot_views[i].update_position(slot_y)
                # Update labels if slot info changed
                slot_name = slot_info.world_name if slot_info.exists and slot_info.world_name else slot_info.world_dir_name if slot_info.exists else "New World"
                self.slot_views[i].update_name(slot_name)
                
                # Update info labels if they exist
                if slot_info.exists and self.slot_views[i].seed_label:
                    self.slot_views[i].seed_label.text = f"Seed: {slot_info.seed}"
                    self.slot_views[i].size_label.text = f"Size: {slot_info.world_size_mb:.1f} MB | Chunks: {slot_info.chunks_generated}"
                    if self.slot_views[i].date_label and slot_info.last_save_date:
                        self.slot_views[i].date_label.text = f"Last played: {slot_info.last_save_date}"
            else:
                # Create new view
                self.slot_views[i] = SlotView(
                    slot_x, slot_y, self.slot_width, self.slot_height,
                    preview_x, slot_y + 10, info_x, info_y,
                    slot_info, font_names, font_sizes
                )
        
        # Remove views for slots that no longer exist
        keys_to_remove = [k for k in self.slot_views.keys() if k >= len(self.slots)]
        for k in keys_to_remove:
            del self.slot_views[k]
    
    def _generate_preview(self, world_id: str, seed: int, spawn_position: Optional[Tuple[float, float]]):
        """Generate preview chunks for a world and create texture"""
        if world_id in self.preview_cache:
            return  # Already cached
        
        try:
            # First, try to load preview.png from save directory
            preview_path = Path(f"saves/{world_id}/preview.png")
            if preview_path.exists():
                try:
                    # Load PNG image using pyglet
                    preview_image = pyglet.image.load(str(preview_path))
                    
                    # Create sprite for easy drawing
                    sprite = pyglet.sprite.Sprite(preview_image)
                    
                    # Extract spawn marker position if spawn_position is available
                    spawn_marker_pos = None
                    if spawn_position:
                        preview_width = self.preview_size * settings.CHUNK_SIZE
                        preview_height = self.preview_size * settings.CHUNK_SIZE
                        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
                        spawn_chunk_x = int(spawn_position[0] // chunk_size_pixels)
                        spawn_chunk_y = int(spawn_position[1] // chunk_size_pixels)
                        spawn_tile_x = int((spawn_position[0] % chunk_size_pixels) // settings.TILE_SIZE)
                        spawn_tile_y = int((spawn_position[1] % chunk_size_pixels) // settings.TILE_SIZE)
                        
                        if 0 <= spawn_chunk_x < self.preview_size and 0 <= spawn_chunk_y < self.preview_size:
                            array_x = spawn_chunk_x * settings.CHUNK_SIZE + spawn_tile_x
                            array_y = spawn_chunk_y * settings.CHUNK_SIZE + spawn_tile_y
                            spawn_marker_pos = (array_x, array_y)
                    
                    self.preview_cache[world_id] = {
                        'chunks': [],  # Not needed when loading from file
                        'spawn_position': spawn_position,
                        'texture': preview_image,
                        'sprite': sprite,
                        'spawn_marker_pos': spawn_marker_pos
                    }
                    return  # Successfully loaded from file
                except Exception as e:
                    # If loading fails, fall through to generate preview
                    pass
            
            # Fallback: Generate preview from terrain generator
            # Create terrain generator with seed
            terrain_gen = TerrainGenerator(seed=seed)
            
            # Calculate preview dimensions
            preview_width = self.preview_size * settings.CHUNK_SIZE
            preview_height = self.preview_size * settings.CHUNK_SIZE
            
            # Create 2D array for tile colors (width x height)
            # Format: [y][x] = (r, g, b)
            color_array = [[(100, 100, 100) for _ in range(preview_width)] for _ in range(preview_height)]
            
            # Generate chunks and fill color array
            preview_chunks = []
            for chunk_y in range(self.preview_size):
                for chunk_x in range(self.preview_size):
                    chunk = terrain_gen.generate_chunk(chunk_x, chunk_y, settings.CHUNK_SIZE)
                    preview_chunks.append((chunk_x, chunk_y, chunk))
                    
                    # Fill color array with tile colors
                    for tile_y in range(settings.CHUNK_SIZE):
                        for tile_x in range(settings.CHUNK_SIZE):
                            tile = chunk[tile_y][tile_x]
                            tile_color = tile.get('color', (100, 100, 100))
                            
                            # Ensure RGB tuple
                            if isinstance(tile_color, (list, tuple)):
                                if len(tile_color) >= 3:
                                    tile_color = tuple(tile_color[:3])
                                else:
                                    tile_color = (100, 100, 100)
                            else:
                                tile_color = (100, 100, 100)
                            
                            # Calculate array position
                            array_x = chunk_x * settings.CHUNK_SIZE + tile_x
                            array_y = chunk_y * settings.CHUNK_SIZE + tile_y
                            
                            # pyglet uses bottom-left origin, so we need to flip Y
                            flipped_y = preview_height - 1 - array_y
                            color_array[flipped_y][array_x] = tile_color
            
            # Mark spawn position with red color if available
            spawn_marker_pos = None
            if spawn_position:
                spawn_chunk_x = int(spawn_position[0] // (settings.CHUNK_SIZE * settings.TILE_SIZE))
                spawn_chunk_y = int(spawn_position[1] // (settings.CHUNK_SIZE * settings.TILE_SIZE))
                spawn_tile_x = int((spawn_position[0] % (settings.CHUNK_SIZE * settings.TILE_SIZE)) // settings.TILE_SIZE)
                spawn_tile_y = int((spawn_position[1] % (settings.CHUNK_SIZE * settings.TILE_SIZE)) // settings.TILE_SIZE)
                
                # Only mark if spawn is in preview area
                if 0 <= spawn_chunk_x < self.preview_size and 0 <= spawn_chunk_y < self.preview_size:
                    array_x = spawn_chunk_x * settings.CHUNK_SIZE + spawn_tile_x
                    array_y = spawn_chunk_y * settings.CHUNK_SIZE + spawn_tile_y
                    flipped_y = preview_height - 1 - array_y
                    
                    if 0 <= array_x < preview_width and 0 <= flipped_y < preview_height:
                        color_array[flipped_y][array_x] = (255, 0, 0)  # Red marker
                        spawn_marker_pos = (array_x, array_y)  # Store original Y for drawing overlay
            
            # Convert 2D color array to 1D byte array (RGB format)
            # pyglet.image.ImageData expects data in row-major order, bottom-to-top
            pixel_data = bytearray()
            for y in range(preview_height):
                for x in range(preview_width):
                    r, g, b = color_array[y][x]
                    pixel_data.extend([r, g, b])
            
            # Create pyglet ImageData texture
            image_data = pyglet.image.ImageData(
                preview_width,
                preview_height,
                'RGB',
                bytes(pixel_data),
                pitch=preview_width * 3  # Bytes per row (width * 3 for RGB)
            )
            
            # Create sprite for easy drawing (optional, but convenient)
            sprite = pyglet.sprite.Sprite(image_data)
            
            self.preview_cache[world_id] = {
                'chunks': preview_chunks,  # Keep for compatibility
                'spawn_position': spawn_position,
                'texture': image_data,
                'sprite': sprite,
                'spawn_marker_pos': spawn_marker_pos  # Store spawn marker position for overlay
            }
        except Exception as e:
            print(f"[WorldSelect] Error generating preview for world {world_id}: {e}")
            import traceback
            traceback.print_exc()
            self.preview_cache[world_id] = None
    
    def handle_mouse_motion(self, x: int, y: int):
        """Handle mouse motion"""
        if not self.active:
            return
        
        # In pyglet, (0,0) is bottom-left, so y is already in the correct coordinate system
        # No conversion needed - use y directly
        
        # Check "Create New World" button hover
        self.create_button_hovered = False
        create_button_y = 150  # Moved up to make room for quit button below
        create_button_height = 60
        create_button_x = (self.window_width - self.slot_width) // 2
        
        if (create_button_x <= x <= create_button_x + self.slot_width and
            create_button_y <= y <= create_button_y + create_button_height):
            self.create_button_hovered = True
            self.quit_button_hovered = False
            self.hovered_slot = None
            return
        
        # Check "Quit" button hover
        self.quit_button_hovered = False
        quit_button_y = create_button_y - (create_button_height + self.slot_spacing)
        
        if (create_button_x <= x <= create_button_x + self.slot_width and
            quit_button_y <= y <= quit_button_y + create_button_height):
            self.quit_button_hovered = True
            self.create_button_hovered = False
            self.hovered_slot = None
            return
        
        # Check which slot is hovered
        self.hovered_slot = None
        start_y = 200
        for i, slot in enumerate(self.slots):
            slot_y = start_y + i * (self.slot_height + self.slot_spacing)
            slot_x = (self.window_width - self.slot_width) // 2
            
            if (slot_x <= x <= slot_x + self.slot_width and
                slot_y <= y <= slot_y + self.slot_height):
                self.hovered_slot = i
                break
    
    def handle_mouse_press(self, x: int, y: int, button: int, modifiers: int):
        """Handle mouse press"""
        if not self.active:
            return None
        
        if button != mouse.LEFT:
            return None
        
        # In pyglet, (0,0) is bottom-left, so y is already in the correct coordinate system
        # No conversion needed - use y directly
        
        # Check "Create New World" button first
        create_button_y = 150  # Moved up to make room for quit button below
        create_button_height = 60
        create_button_x = (self.window_width - self.slot_width) // 2
        
        if (create_button_x <= x <= create_button_x + self.slot_width and
            create_button_y <= y <= create_button_y + create_button_height):
            return "create_new"
        
        # Check "Quit" button
        quit_button_y = create_button_y - (create_button_height + self.slot_spacing)
        
        if (create_button_x <= x <= create_button_x + self.slot_width and
            quit_button_y <= y <= quit_button_y + create_button_height):
            return "quit"
        
        # Check save slots
        start_y = 200
        for i, slot in enumerate(self.slots):
            slot_y = start_y + i * (self.slot_height + self.slot_spacing)
            slot_x = (self.window_width - self.slot_width) // 2
            
            if (slot_x <= x <= slot_x + self.slot_width and
                slot_y <= y <= slot_y + self.slot_height):
                self.selected_slot = i
                return f"world_{slot.world_dir_name}"
        
        return None
    
    def handle_key_press(self, symbol: int, modifiers: int):
        """Handle key press"""
        if not self.active:
            return None
        
        # Handle rename mode
        if self.rename_mode and self.renaming_slot is not None:
            if symbol == key.ENTER or symbol == key.RETURN:
                # Confirm rename
                self._confirm_rename()
                return "renamed"
            elif symbol == key.ESCAPE:
                # Cancel rename
                self.rename_mode = False
                self.renaming_slot = None
                self.rename_text = ""
                return None
            elif symbol == key.BACKSPACE:
                # Delete last character
                if self.rename_text:
                    self.rename_text = self.rename_text[:-1]
                return None
            else:
                # Add character (if printable)
                char = self._key_to_char(symbol, modifiers)
                if char:
                    self.rename_text += char
                return None
        
        if symbol == key.ESCAPE:
            self.active = False
            return "back"
        
        if symbol == key.DELETE and self.selected_slot is not None:
            # Delete selected slot
            slot = self.slots[self.selected_slot]
            if slot.exists:
                if slot.delete():
                    self.refresh_slots()
                    self.selected_slot = None
                    return "deleted"
        
        if symbol == key.R and self.selected_slot is not None and modifiers & key.MOD_CTRL:
            # Ctrl+R: Rename slot
            slot = self.slots[self.selected_slot]
            if slot.exists:
                self.rename_mode = True
                self.renaming_slot = self.selected_slot
                self.rename_text = slot.world_name if slot.world_name else slot.world_dir_name
                return "rename_start"
        
        return None
    
    def _key_to_char(self, symbol: int, modifiers: int) -> Optional[str]:
        """Convert key symbol to character"""
        # Basic ASCII mapping (simplified)
        if symbol >= key.A and symbol <= key.Z:
            char = chr(ord('a') + (symbol - key.A))
            if modifiers & key.MOD_SHIFT:
                char = char.upper()
            return char
        elif symbol >= key._0 and symbol <= key._9:
            return str(symbol - key._0)
        elif symbol == key.SPACE:
            return " "
        elif symbol == key.MINUS:
            return "-" if not (modifiers & key.MOD_SHIFT) else "_"
        return None
    
    def _confirm_rename(self):
        """Confirm rename and update world name"""
        if self.renaming_slot is None or not self.rename_text.strip():
            self.rename_mode = False
            self.renaming_slot = None
            self.rename_text = ""
            return
        
        slot = self.slots[self.renaming_slot]
        if slot.exists:
            # Save world name to metadata (new format)
            try:
                metadata = {}
                if slot.metadata_file.exists():
                    with open(slot.metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                
                # Update name in new format
                if metadata.get("version") == 1:
                    metadata['name'] = self.rename_text.strip()
                else:
                    # Old format - migrate
                    metadata['world_name'] = self.rename_text.strip()
                    if 'name' not in metadata:
                        metadata['name'] = self.rename_text.strip()
                
                with open(slot.metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
                
                self.refresh_slots()
            except Exception as e:
                print(f"[WorldSelect] Error renaming world: {e}")
                import traceback
                traceback.print_exc()
        
        self.rename_mode = False
        self.renaming_slot = None
        self.rename_text = ""
    
    def draw(self):
        """Draw world select menu with visibility culling"""
        if not self.active:
            return
        
        # Profiling start
        if self.profiling_enabled:
            import time
            draw_start_time = time.perf_counter()
            self.draw_stats['total_slots'] = len(self.slots)
            self.draw_stats['visible_slots'] = 0
            self.draw_stats['draw_calls'] = 0
        
        # Draw semi-transparent overlay
        self._draw_overlay()
        
        # Draw title
        self._draw_title()
        
        # Draw save slots (only visible ones)
        start_y = 200
        visible_range = self._get_visible_slot_range(start_y)
        
        if visible_range:
            start_idx, end_idx = visible_range
            for i in range(start_idx, end_idx):
                if i < len(self.slots):
                    slot = self.slots[i]
                    self._draw_slot(i, slot)
                    
                    if self.profiling_enabled:
                        self.draw_stats['visible_slots'] += 1
                        self.draw_stats['draw_calls'] += 1
        
        # Draw "Create New World" button at the bottom
        self._draw_create_button()
        
        # Draw "Quit" button below create button
        self._draw_quit_button()
        
        # Profiling end
        if self.profiling_enabled:
            draw_time = (time.perf_counter() - draw_start_time) * 1000  # Convert to ms
            if draw_time > 1.0:  # Only log if draw takes more than 1ms
                print(f"[WorldSelect] Draw: {draw_time:.2f}ms | "
                      f"Slots: {self.draw_stats['visible_slots']}/{self.draw_stats['total_slots']} visible | "
                      f"Draw calls: {self.draw_stats['draw_calls']}")
    
    def _get_visible_slot_range(self, start_y: int) -> Optional[Tuple[int, int]]:
        """
        Calculate which slots are visible in the window.
        
        Returns:
            Tuple of (start_index, end_index) for visible slots, or None if no slots visible
        """
        if not self.slots:
            return None
        
        # Calculate window bounds (with some margin for partial visibility)
        window_bottom = 0
        window_top = self.window_height
        
        # Calculate slot positions
        slot_height_with_spacing = self.slot_height + self.slot_spacing
        
        # Find first visible slot
        start_idx = None
        for i in range(len(self.slots)):
            slot_y = start_y + i * slot_height_with_spacing
            slot_top = slot_y + self.slot_height
            
            # Slot is visible if any part is in window
            if slot_top >= window_bottom and slot_y <= window_top:
                start_idx = i
                break
        
        if start_idx is None:
            return None  # No visible slots
        
        # Find last visible slot
        end_idx = start_idx + 1
        for i in range(start_idx + 1, len(self.slots)):
            slot_y = start_y + i * slot_height_with_spacing
            
            # Slot is visible if any part is in window
            if slot_y <= window_top:
                end_idx = i + 1
            else:
                break  # No more visible slots
        
        return (start_idx, end_idx)
    
    def _draw_overlay(self):
        """Draw semi-transparent overlay"""
        # Use ModernGL to draw a semi-transparent quad
        # For now, we'll use pyglet's built-in drawing
        pass  # Overlay will be handled by main window
    
    def _draw_title(self):
        """Draw menu title using cached label"""
        self.title_label.draw()
    
    def _draw_slot(self, index: int, slot: WorldSlotInfo):
        """Draw a save slot entry using cached UI elements"""
        # Get cached view or create if missing
        if index not in self.slot_views:
            self._update_slot_views()
        
        if index not in self.slot_views:
            return  # Should not happen
        
        slot_view = self.slot_views[index]
        
        # Determine colors based on state
        is_selected = self.selected_slot == index
        is_hovered = self.hovered_slot == index
        
        if is_selected:
            bg_color = (100, 150, 100, 200)  # Green tint
            border_color = (150, 255, 150, 255)  # Bright green border
        elif is_hovered:
            bg_color = (80, 80, 80, 200)  # Gray tint
            border_color = (200, 200, 200, 255)  # White border
        elif slot.exists:
            bg_color = (60, 60, 60, 200)  # Dark gray
            border_color = (150, 150, 150, 255)  # Gray border
        else:
            bg_color = (40, 40, 40, 200)  # Very dark gray
            border_color = (100, 100, 100, 255)  # Dark gray border
        
        # Update colors (no recreation, just update properties)
        slot_view.update_colors(bg_color, border_color)
        
        # Update name if in rename mode
        if self.rename_mode and self.renaming_slot == index:
            display_name = self.rename_text + "_"  # Cursor indicator
            name_color = (255, 255, 0, 255)  # Yellow for editing
            slot_view.update_name(display_name, name_color)
        else:
            slot_name = slot.world_name if slot.exists and slot.world_name else f"World {slot.slot_num}" if slot.exists else "New World"
            slot_view.update_name(slot_name, (255, 255, 255, 255))
        
        # Show/hide hint label (already created in SlotView)
        if self.selected_slot == index and slot.exists:
            slot_view.hint_label.visible = True
        else:
            slot_view.hint_label.visible = False
        
        # Draw preview (if exists)
        if slot.exists and slot.world_id in self.preview_cache:
            self._draw_preview(slot_view.preview_x, slot_view.preview_y, slot.world_id)
        
        # Draw all cached UI elements (much faster than creating new ones)
        slot_view.draw()
    
    def _draw_create_button(self):
        """Draw 'Create New World' button using cached UI elements"""
        # Determine colors based on hover state
        if self.create_button_hovered:
            bg_color = (80, 120, 80)  # Green tint
            border_color = (150, 255, 150)  # Bright green border
        else:
            bg_color = (60, 100, 60)  # Dark green
            border_color = (100, 200, 100)  # Green border
        
        # Update colors (no recreation, just update properties)
        self.create_button_bg_rect.color = bg_color
        
        if self.create_button_border_rect:
            self.create_button_border_rect.color = bg_color
            self.create_button_border_rect.border_color = border_color
        else:
            for line in self.create_button_border_lines:
                line.color = border_color
        
        # Draw cached UI elements
        self.create_button_bg_rect.draw()
        
        if self.create_button_border_rect:
            self.create_button_border_rect.draw()
        else:
            for line in self.create_button_border_lines:
                line.draw()
        
        self.create_button_label.draw()
    
    def _draw_quit_button(self):
        """Draw 'Quit' button using cached UI elements"""
        # Determine colors based on hover state
        if self.quit_button_hovered:
            bg_color = (150, 80, 80)  # Red tint
            border_color = (255, 150, 150)  # Bright red border
        else:
            bg_color = (100, 60, 60)  # Dark red
            border_color = (200, 100, 100)  # Red border
        
        # Update colors (no recreation, just update properties)
        self.quit_button_bg_rect.color = bg_color
        
        if self.quit_button_border_rect:
            self.quit_button_border_rect.color = bg_color
            self.quit_button_border_rect.border_color = border_color
        else:
            for line in self.quit_button_border_lines:
                line.color = border_color
        
        # Draw cached UI elements
        self.quit_button_bg_rect.draw()
        
        if self.quit_button_border_rect:
            self.quit_button_border_rect.draw()
        else:
            for line in self.quit_button_border_lines:
                line.draw()
        
        self.quit_button_label.draw()
    
    def _draw_preview(self, x: int, y: int, world_id: str):
        """Draw world preview using texture (optimized)"""
        if world_id not in self.preview_cache or self.preview_cache[world_id] is None:
            return
        
        preview_data = self.preview_cache[world_id]
        
        # Texture-based rendering (always used now)
        if 'texture' not in preview_data:
            return  # Should not happen - texture should always be created
        
        texture = preview_data['texture']
        sprite = preview_data.get('sprite')
        
        # Calculate scale to fit preview_size_pixels
        scale = self.preview_size_pixels / max(texture.width, texture.height)
        
        # Draw texture using sprite (much faster than individual rectangles)
        if sprite:
            sprite.x = x
            sprite.y = y
            sprite.scale = scale
            sprite.draw()
        else:
            # Fallback: draw texture directly (if sprite not available)
            texture.blit(x, y, width=int(texture.width * scale), height=int(texture.height * scale))
        
        # Note: Spawn marker is already included in the texture, no overlay needed
    
    def toggle(self):
        """Toggle menu visibility"""
        self.active = not self.active
        if self.active:
            self.refresh_slots()
        return self.active
    
    def show(self):
        """Show menu"""
        self.active = True
        self.refresh_slots()
    
    def hide(self):
        """Hide menu"""
        self.active = False

