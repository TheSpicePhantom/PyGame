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


class WorldSlotInfo:
    """Information about a world save slot"""
    
    def __init__(self, slot_num: int):
        self.slot_num = slot_num
        self.world_id = f"slot_{slot_num}"  # Initialize before _load_info()
        self.save_dir = Path(f"saves/slot_{slot_num}")
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
                self.world_name = metadata.get("name", f"World {self.slot_num}")
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
                self.world_name = metadata.get('world_name', f"World {self.slot_num}")
                
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
            print(f"[WorldSelect] Error loading world info for slot {self.slot_num}: {e}")
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
            print(f"[WorldSelect] Error deleting slot {self.slot_num}: {e}")
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
        
        # Preview generation
        self.preview_cache: Dict[str, List] = {}  # world_id -> preview chunks data
        self.preview_size = 5  # 5x5 chunks preview
        
        # UI layout
        self.slot_width = 600
        self.slot_height = 200
        self.slot_spacing = 20
        self.preview_size_pixels = 150  # Preview size in pixels
        
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
        
        self.refresh_slots()
    
    def refresh_slots(self):
        """Refresh save slot information - scan all worlds in saves/ directory"""
        self.slots = []
        saves_dir = Path("saves")
        
        if not saves_dir.exists():
            return
        
        # Scan all directories in saves/ folder
        for save_dir in saves_dir.iterdir():
            if not save_dir.is_dir():
                continue
            
            # Extract slot number from directory name (slot_1, slot_2, etc.)
            if save_dir.name.startswith("slot_"):
                try:
                    slot_num = int(save_dir.name.split("_")[1])
                except (ValueError, IndexError):
                    continue
            else:
                # New format: use directory name as world_id
                # For now, still use numeric IDs for compatibility
                continue
            
            slot_info = WorldSlotInfo(slot_num)
            self.slots.append(slot_info)
            
            # Generate preview if slot exists
            if slot_info.exists and slot_info.seed is not None:
                self._generate_preview(slot_info.world_id, slot_info.seed, slot_info.spawn_position)
        
        # Sort by last played date (newest first)
        self.slots.sort(key=lambda s: s.last_played_at or "", reverse=True)
    
    def _generate_preview(self, world_id: str, seed: int, spawn_position: Optional[Tuple[float, float]]):
        """Generate preview chunks for a world"""
        if world_id in self.preview_cache:
            return  # Already cached
        
        try:
            # Create terrain generator with seed
            terrain_gen = TerrainGenerator(seed=seed)
            
            # Generate first 5x5 chunks (chunks 0,0 to 4,4)
            preview_chunks = []
            for chunk_y in range(self.preview_size):
                for chunk_x in range(self.preview_size):
                    chunk = terrain_gen.generate_chunk(chunk_x, chunk_y, settings.CHUNK_SIZE)
                    preview_chunks.append((chunk_x, chunk_y, chunk))
            
            self.preview_cache[world_id] = {
                'chunks': preview_chunks,
                'spawn_position': spawn_position
            }
        except Exception as e:
            print(f"[WorldSelect] Error generating preview for world {world_id}: {e}")
            self.preview_cache[world_id] = None
    
    def handle_mouse_motion(self, x: int, y: int):
        """Handle mouse motion"""
        if not self.active:
            return
        
        # In pyglet, (0,0) is bottom-left, so y is already in the correct coordinate system
        # No conversion needed - use y directly
        
        # Check "Create New World" button hover
        self.create_button_hovered = False
        create_button_y = 50
        create_button_height = 60
        create_button_x = (self.window_width - self.slot_width) // 2
        
        if (create_button_x <= x <= create_button_x + self.slot_width and
            create_button_y <= y <= create_button_y + create_button_height):
            self.create_button_hovered = True
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
        create_button_y = 50
        create_button_height = 60
        create_button_x = (self.window_width - self.slot_width) // 2
        
        if (create_button_x <= x <= create_button_x + self.slot_width and
            create_button_y <= y <= create_button_y + create_button_height):
            return "create_new"
        
        # Check save slots
        start_y = 200
        for i, slot in enumerate(self.slots):
            slot_y = start_y + i * (self.slot_height + self.slot_spacing)
            slot_x = (self.window_width - self.slot_width) // 2
            
            if (slot_x <= x <= slot_x + self.slot_width and
                slot_y <= y <= slot_y + self.slot_height):
                self.selected_slot = i
                return f"slot_{slot.slot_num}"
        
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
                self.rename_text = f"World {slot.slot_num}"
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
        """Draw world select menu"""
        if not self.active:
            return
        
        # Draw semi-transparent overlay
        self._draw_overlay()
        
        # Draw title
        self._draw_title()
        
        # Draw save slots
        for i, slot in enumerate(self.slots):
            self._draw_slot(i, slot)
        
        # Draw "Create New World" button at the bottom
        self._draw_create_button()
    
    def _draw_overlay(self):
        """Draw semi-transparent overlay"""
        # Use ModernGL to draw a semi-transparent quad
        # For now, we'll use pyglet's built-in drawing
        pass  # Overlay will be handled by main window
    
    def _draw_title(self):
        """Draw menu title"""
        title_text = "Select World"
        label = pyglet.text.Label(
            title_text,
            font_name=self.title_font_name,
            font_size=self.title_font_size,
            # Note: bold parameter not supported in pyglet.text.Label
            color=(255, 255, 255, 255),
            x=self.window_width // 2,
            y=self.window_height - 50,
            anchor_x='center',
            anchor_y='top'
        )
        label.draw()
    
    def _draw_slot(self, index: int, slot: WorldSlotInfo):
        """Draw a save slot entry"""
        start_y = 200
        slot_y = start_y + index * (self.slot_height + self.slot_spacing)
        slot_x = (self.window_width - self.slot_width) // 2
        
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
        
        # Draw slot background (using pyglet shapes)
        import pyglet.shapes
        bg_rect = pyglet.shapes.Rectangle(
            slot_x, slot_y, self.slot_width, self.slot_height,
            color=(bg_color[0], bg_color[1], bg_color[2])
        )
        bg_rect.opacity = bg_color[3]
        bg_rect.draw()
        
        # Draw border (using Rectangle with border parameter if available, else draw separately)
        try:
            border_rect = pyglet.shapes.BorderedRectangle(
                slot_x, slot_y, self.slot_width, self.slot_height,
                border=2,
                color=(bg_color[0], bg_color[1], bg_color[2]),
                border_color=(border_color[0], border_color[1], border_color[2])
            )
            border_rect.opacity = border_color[3]
            border_rect.draw()
        except AttributeError:
            # BorderedRectangle not available, draw border manually
            border_line = pyglet.shapes.Line(
                slot_x, slot_y, slot_x + self.slot_width, slot_y,
                width=2, color=(border_color[0], border_color[1], border_color[2])
            )
            border_line.draw()
            border_line = pyglet.shapes.Line(
                slot_x + self.slot_width, slot_y, slot_x + self.slot_width, slot_y + self.slot_height,
                width=2, color=(border_color[0], border_color[1], border_color[2])
            )
            border_line.draw()
            border_line = pyglet.shapes.Line(
                slot_x + self.slot_width, slot_y + self.slot_height, slot_x, slot_y + self.slot_height,
                width=2, color=(border_color[0], border_color[1], border_color[2])
            )
            border_line.draw()
            border_line = pyglet.shapes.Line(
                slot_x, slot_y + self.slot_height, slot_x, slot_y,
                width=2, color=(border_color[0], border_color[1], border_color[2])
            )
            border_line.draw()
        
        # Draw preview (if exists)
        preview_x = slot_x + 10
        preview_y = slot_y + 10
        if slot.exists and slot.world_id in self.preview_cache:
            self._draw_preview(preview_x, preview_y, slot.world_id)
        
        # Draw slot information
        info_x = slot_x + self.preview_size_pixels + 30
        info_y = slot_y + self.slot_height - 30
        
        # Slot name
        if slot.exists:
            slot_name = slot.world_name if slot.world_name else f"World {slot.slot_num}"
        else:
            slot_name = f"New World"
        
        # Show rename input if in rename mode
        if self.rename_mode and self.renaming_slot == index:
            display_name = self.rename_text + "_"  # Cursor indicator
            name_color = (255, 255, 0, 255)  # Yellow for editing
        else:
            display_name = slot_name
            name_color = (255, 255, 255, 255)
        
        name_label = pyglet.text.Label(
            display_name,
            font_name=self.slot_font_name,
            font_size=self.slot_font_size,
            # Note: bold parameter not supported in pyglet.text.Label
            color=name_color,
            x=info_x,
            y=info_y,
            anchor_x='left',
            anchor_y='top'
        )
        name_label.draw()
        
        # Show rename hint
        if self.selected_slot == index and slot.exists:
            hint_text = "Ctrl+R to rename, Delete to delete"
            hint_label = pyglet.text.Label(
                hint_text,
                font_name=self.info_font_name,
                font_size=14,
                color=(150, 150, 150, 255),
                x=info_x,
                y=slot_y + 10,
                anchor_x='left',
                anchor_y='bottom'
            )
            hint_label.draw()
        
        if slot.exists:
            # Seed
            seed_text = f"Seed: {slot.seed}"
            seed_label = pyglet.text.Label(
                seed_text,
                font_name=self.info_font_name,
                font_size=self.info_font_size,
                color=(200, 200, 200, 255),
                x=info_x,
                y=info_y - 30,
                anchor_x='left',
                anchor_y='top'
            )
            seed_label.draw()
            
            # World size and chunks
            size_text = f"Size: {slot.world_size_mb:.1f} MB | Chunks: {slot.chunks_generated}"
            size_label = pyglet.text.Label(
                size_text,
                font_name=self.info_font_name,
                font_size=self.info_font_size,
                color=(200, 200, 200, 255),
                x=info_x,
                y=info_y - 55,
                anchor_x='left',
                anchor_y='top'
            )
            size_label.draw()
            
            # Last played date
            if slot.last_save_date:
                date_text = f"Last played: {slot.last_save_date}"
                date_label = pyglet.text.Label(
                    date_text,
                    font_name=self.info_font_name,
                    font_size=self.info_font_size,
                    color=(200, 200, 200, 255),
                    x=info_x,
                    y=info_y - 80,
                    anchor_x='left',
                    anchor_y='top'
                )
                date_label.draw()
        else:
            # Empty slot message
            empty_label = pyglet.text.Label(
                "New World",
                font_name=self.info_font_name,
                font_size=self.info_font_size,
                color=(150, 150, 150, 255),
                x=info_x,
                y=info_y - 30,
                anchor_x='left',
                anchor_y='top'
            )
            empty_label.draw()
    
    def _draw_create_button(self):
        """Draw 'Create New World' button"""
        button_y = 50
        button_height = 60
        button_x = (self.window_width - self.slot_width) // 2
        
        # Determine colors based on hover state
        if self.create_button_hovered:
            bg_color = (80, 120, 80, 255)  # Green tint
            border_color = (150, 255, 150, 255)  # Bright green border
        else:
            bg_color = (60, 100, 60, 255)  # Dark green
            border_color = (100, 200, 100, 255)  # Green border
        
        # Draw button background
        import pyglet.shapes
        bg_rect = pyglet.shapes.Rectangle(
            button_x, button_y, self.slot_width, button_height,
            color=(bg_color[0], bg_color[1], bg_color[2])
        )
        bg_rect.draw()
        
        # Draw border
        try:
            border_rect = pyglet.shapes.BorderedRectangle(
                button_x, button_y, self.slot_width, button_height,
                border=3,
                color=(bg_color[0], bg_color[1], bg_color[2]),
                border_color=(border_color[0], border_color[1], border_color[2])
            )
            border_rect.draw()
        except AttributeError:
            # Fallback: draw border with lines
            border_line = pyglet.shapes.Line(
                button_x, button_y, button_x + self.slot_width, button_y,
                width=3, color=(border_color[0], border_color[1], border_color[2])
            )
            border_line.draw()
            border_line = pyglet.shapes.Line(
                button_x + self.slot_width, button_y, button_x + self.slot_width, button_y + button_height,
                width=3, color=(border_color[0], border_color[1], border_color[2])
            )
            border_line.draw()
            border_line = pyglet.shapes.Line(
                button_x + self.slot_width, button_y + button_height, button_x, button_y + button_height,
                width=3, color=(border_color[0], border_color[1], border_color[2])
            )
            border_line.draw()
            border_line = pyglet.shapes.Line(
                button_x, button_y + button_height, button_x, button_y,
                width=3, color=(border_color[0], border_color[1], border_color[2])
            )
            border_line.draw()
        
        # Draw button text
        button_text = "+ Create New World"
        button_label = pyglet.text.Label(
            button_text,
            font_name=self.slot_font_name,
            font_size=28,
            color=(255, 255, 255, 255),
            x=button_x + self.slot_width // 2,
            y=button_y + button_height // 2,
            anchor_x='center',
            anchor_y='center'
        )
        button_label.draw()
    
    def _draw_preview(self, x: int, y: int, world_id: str):
        """Draw world preview (5x5 chunks)"""
        if world_id not in self.preview_cache or self.preview_cache[world_id] is None:
            return
        
        preview_data = self.preview_cache[world_id]
        chunks = preview_data['chunks']
        spawn_pos = preview_data.get('spawn_position')
        
        # Calculate tile size for preview
        tile_size = self.preview_size_pixels // (self.preview_size * settings.CHUNK_SIZE)
        if tile_size < 1:
            tile_size = 1
        
        # Draw chunks
        for chunk_x, chunk_y, tiles in chunks:
            chunk_world_x = chunk_x * settings.CHUNK_SIZE * tile_size
            chunk_world_y = chunk_y * settings.CHUNK_SIZE * tile_size
            
            # Draw tiles in chunk
            for tile_y in range(settings.CHUNK_SIZE):
                for tile_x in range(settings.CHUNK_SIZE):
                    tile = tiles[tile_y][tile_x]
                    tile_color = tile.get('color', (100, 100, 100))
                    
                    # Convert RGB to RGBA
                    if len(tile_color) == 3:
                        tile_color = (*tile_color, 255)
                    
                    tile_screen_x = x + chunk_world_x + tile_x * tile_size
                    tile_screen_y = y + chunk_world_y + tile_y * tile_size
                    
                    # Draw tile using pyglet shapes
                    import pyglet.shapes
                    tile_rect = pyglet.shapes.Rectangle(
                        tile_screen_x, tile_screen_y, tile_size, tile_size,
                        color=(tile_color[0], tile_color[1], tile_color[2])
                    )
                    if len(tile_color) > 3:
                        tile_rect.opacity = tile_color[3]
                    tile_rect.draw()
        
        # Draw spawn position marker (red tile)
        if spawn_pos:
            spawn_chunk_x = int(spawn_pos[0] // (settings.CHUNK_SIZE * settings.TILE_SIZE))
            spawn_chunk_y = int(spawn_pos[1] // (settings.CHUNK_SIZE * settings.TILE_SIZE))
            spawn_tile_x = int((spawn_pos[0] % (settings.CHUNK_SIZE * settings.TILE_SIZE)) // settings.TILE_SIZE)
            spawn_tile_y = int((spawn_pos[1] % (settings.CHUNK_SIZE * settings.TILE_SIZE)) // settings.TILE_SIZE)
            
            # Only draw if spawn is in preview area
            if 0 <= spawn_chunk_x < self.preview_size and 0 <= spawn_chunk_y < self.preview_size:
                spawn_screen_x = x + spawn_chunk_x * settings.CHUNK_SIZE * tile_size + spawn_tile_x * tile_size
                spawn_screen_y = y + spawn_chunk_y * settings.CHUNK_SIZE * tile_size + spawn_tile_y * tile_size
                
                # Draw red marker using pyglet shapes
                import pyglet.shapes
                spawn_marker = pyglet.shapes.Rectangle(
                    spawn_screen_x, spawn_screen_y, tile_size, tile_size,
                    color=(255, 0, 0)
                )
                spawn_marker.draw()
    
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

