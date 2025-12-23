"""
Create World Menu - Submenu for creating a new world
"""
import pyglet
from pyglet.window import key, mouse
from typing import Optional, Tuple, Dict, List
from pathlib import Path
from world.terrain_generator import TerrainGenerator
from core import settings


class CreateWorldMenu:
    """Menu for creating a new world with name, seed, and preview"""
    
    def __init__(self, window_width: int, window_height: int, renderer):
        """
        Initialize Create World Menu
        
        Args:
            window_width: Window width in pixels
            window_height: Window height in pixels
            renderer: ModernGLRenderer instance for rendering
        """
        self.window_width = window_width
        self.window_height = window_height
        self.renderer = renderer
        self.active = False
        
        # Input fields
        self.world_name = "New World"
        self.seed_input = ""
        self.use_random_seed = True
        
        # Focus tracking
        self.focused_field = None  # "name" or "seed"
        
        # Preview generation
        self.preview_cache: Optional[Dict] = None
        self.preview_seed: Optional[int] = None
        self.preview_size = 5  # 5x5 chunks preview
        self.preview_size_pixels = 150  # Preview size in pixels
        
        # Preview update debouncing (throttle terrain generation)
        import time
        self.last_seed_change_time = 0.0
        self.preview_update_debounce_ms = 500  # Update preview only after 500ms of no changes
        self.pending_preview_update = False
        
        # UI layout (must be set before creating cached shapes)
        self.panel_width = 800
        self.panel_height = 600
        self.panel_x = (window_width - self.panel_width) // 2
        self.panel_y = (window_height - self.panel_height) // 2
        
        # Fonts
        self.title_font_name = "Arial"
        self.title_font_size = 36
        self.label_font_name = "Arial"
        self.label_font_size = 20
        self.input_font_name = "Arial"
        self.input_font_size = 24
        
        # Buttons
        self.create_button_hovered = False
        self.cancel_button_hovered = False
        self.random_seed_button_hovered = False
        self.quit_button_hovered = False
        
        # Button dimensions
        self.button_width = 200
        self.button_height = 50
        self.button_spacing = 20
        
        # Cached UI shapes (created once, reused every frame)
        # Must be called after all layout variables are set
        self._init_cached_shapes()
    
    def _init_cached_shapes(self):
        """Initialize all cached UI shapes"""
        import pyglet.shapes
        
        # Preview shapes
        self.preview_bg_rect = pyglet.shapes.Rectangle(
            0, 0, self.preview_size_pixels, self.preview_size_pixels,
            color=(20, 20, 20)
        )
        self.preview_spawn_marker = pyglet.shapes.Rectangle(
            0, 0, 4, 4,
            color=(255, 0, 0)
        )
        
        # Overlay (full-screen semi-transparent)
        self.overlay_rect = pyglet.shapes.Rectangle(
            0, 0, self.window_width, self.window_height,
            color=(0, 0, 0)
        )
        self.overlay_rect.opacity = 200
        
        # Panel background
        self.panel_bg_rect = pyglet.shapes.Rectangle(
            self.panel_x, self.panel_y, self.panel_width, self.panel_height,
            color=(40, 40, 40)
        )
        
        # Panel border
        try:
            self.panel_border_rect = pyglet.shapes.BorderedRectangle(
                self.panel_x, self.panel_y, self.panel_width, self.panel_height,
                border=3,
                color=(40, 40, 40),
                border_color=(150, 150, 150)
            )
            self.panel_border_lines = None
        except AttributeError:
            # Fallback: create border lines
            self.panel_border_rect = None
            border_color = (150, 150, 150)
            self.panel_border_lines = [
                pyglet.shapes.Line(self.panel_x, self.panel_y, self.panel_x + self.panel_width, self.panel_y, width=3, color=border_color),
                pyglet.shapes.Line(self.panel_x + self.panel_width, self.panel_y, self.panel_x + self.panel_width, self.panel_y + self.panel_height, width=3, color=border_color),
                pyglet.shapes.Line(self.panel_x + self.panel_width, self.panel_y + self.panel_height, self.panel_x, self.panel_y + self.panel_height, width=3, color=border_color),
                pyglet.shapes.Line(self.panel_x, self.panel_y + self.panel_height, self.panel_x, self.panel_y, width=3, color=border_color)
            ]
        
        # Calculate button positions
        button_y = self.panel_y + 50
        button_x_start = self.panel_x + (self.panel_width - (self.button_width * 2 + self.button_spacing)) // 2
        
        # Cancel button
        cancel_x = button_x_start
        self.cancel_button_bg_rect = pyglet.shapes.Rectangle(
            cancel_x, button_y, self.button_width, self.button_height,
            color=(100, 60, 60)  # Default color
        )
        
        # Create button
        create_x = button_x_start + self.button_width + self.button_spacing
        self.create_button_bg_rect = pyglet.shapes.Rectangle(
            create_x, button_y, self.button_width, self.button_height,
            color=(60, 100, 60)  # Default color
        )
        
        # Quit button (below cancel button)
        quit_button_y = button_y - (self.button_height + self.button_spacing)
        self.quit_button_bg_rect = pyglet.shapes.Rectangle(
            cancel_x, quit_button_y, self.button_width, self.button_height,
            color=(100, 60, 60)  # Default color (red-ish)
        )
        
        # Random seed button
        random_button_x = self.panel_x + 400
        random_button_y = self.panel_y + 300
        random_button_width = 150
        random_button_height = 40
        self.random_button_bg_rect = pyglet.shapes.Rectangle(
            random_button_x, random_button_y, random_button_width, random_button_height,
            color=(60, 100, 60)  # Default color
        )
        
        # Cached labels (created once, text updated as needed)
        self.title_label = pyglet.text.Label(
            "Create New World",
            font_name=self.title_font_name,
            font_size=self.title_font_size,
            color=(255, 255, 255, 255),
            x=self.panel_x + self.panel_width // 2,
            y=self.panel_y + self.panel_height - 50,
            anchor_x='center',
            anchor_y='center'
        )
        
        self.cancel_button_label = pyglet.text.Label(
            "Cancel",
            font_name=self.label_font_name,
            font_size=24,
            color=(255, 255, 255, 255),
            x=cancel_x + self.button_width // 2,
            y=button_y + self.button_height // 2,
            anchor_x='center',
            anchor_y='center'
        )
        
        self.create_button_label = pyglet.text.Label(
            "Create World",
            font_name=self.label_font_name,
            font_size=24,
            color=(255, 255, 255, 255),
            x=create_x + self.button_width // 2,
            y=button_y + self.button_height // 2,
            anchor_x='center',
            anchor_y='center'
        )
        
        self.quit_button_label = pyglet.text.Label(
            "Quit",
            font_name=self.label_font_name,
            font_size=24,
            color=(255, 255, 255, 255),
            x=cancel_x + self.button_width // 2,
            y=quit_button_y + self.button_height // 2,
            anchor_x='center',
            anchor_y='center'
        )
        
        self.random_button_label = pyglet.text.Label(
            "Use Random",
            font_name=self.label_font_name,
            font_size=18,
            color=(255, 255, 255, 255),
            x=random_button_x + random_button_width // 2,
            y=random_button_y + random_button_height // 2,
            anchor_x='center',
            anchor_y='center'
        )
        
        # Input field labels (static, created once)
        self.name_label = pyglet.text.Label(
            "World Name:",
            font_name=self.label_font_name,
            font_size=self.label_font_size,
            color=(255, 255, 255, 255),
            x=self.panel_x + 50,
            y=self.panel_y + 470,
            anchor_x='left',
            anchor_y='center'
        )
        
        self.seed_label = pyglet.text.Label(
            "Seed:",
            font_name=self.label_font_name,
            font_size=self.label_font_size,
            color=(255, 255, 255, 255),
            x=self.panel_x + 50,
            y=self.panel_y + 370,
            anchor_x='left',
            anchor_y='center'
        )
        
        self.preview_label = pyglet.text.Label(
            "Preview:",
            font_name=self.label_font_name,
            font_size=self.label_font_size,
            color=(255, 255, 255, 255),
            x=self.panel_x + 50,
            y=self.panel_y + 220,  # preview_y + 120
            anchor_x='left',
            anchor_y='center'
        )
        
        # Dynamic input field text labels (created once, only .text updated)
        name_field_x = self.panel_x + 200
        name_field_y = self.panel_y + 450
        name_field_height = 40
        
        self.name_input_label = pyglet.text.Label(
            "",  # Will be updated dynamically
            font_name=self.input_font_name,
            font_size=self.input_font_size,
            color=(255, 255, 255, 255),
            x=name_field_x + 10,
            y=name_field_y + name_field_height // 2,
            anchor_x='left',
            anchor_y='center'
        )
        
        seed_field_x = self.panel_x + 200
        seed_field_y = self.panel_y + 350
        seed_field_height = 40
        
        self.seed_input_label = pyglet.text.Label(
            "",  # Will be updated dynamically
            font_name=self.input_font_name,
            font_size=self.input_font_size,
            color=(255, 255, 255, 255),
            x=seed_field_x + 10,
            y=seed_field_y + seed_field_height // 2,
            anchor_x='left',
            anchor_y='center'
        )
    
    def show(self):
        """Show the create world menu"""
        self.active = True
        self.focused_field = "name"
        self.world_name = "New World"
        self.seed_input = ""
        self.use_random_seed = True
        self.preview_cache = None
        self.preview_seed = None
        # Generate initial preview with random seed
        self._update_preview()
    
    def hide(self):
        """Hide the create world menu"""
        self.active = False
        self.focused_field = None
    
    def get_world_name(self) -> str:
        """Get the entered world name"""
        return self.world_name.strip() or "New World"
    
    def get_seed(self) -> int:
        """
        Get the seed for world creation.
        
        This is the CENTRAL place for seed generation. All random seeds must be
        generated here to ensure consistency between preview and actual world.
        
        Returns:
            int: The seed value (never None - generates one if needed)
        
        Note: This ensures consistency between preview and actual world.
        If use_random_seed=True and no preview_seed exists yet, generates one
        and stores it to ensure preview and world use the same seed.
        This method always returns a valid seed, never None.
        """
        if self.use_random_seed:
            # If we have a preview seed, use it to ensure consistency
            if self.preview_seed is not None:
                print(f"[CreateWorld] DEBUG: get_seed() returning existing preview_seed: {self.preview_seed}")
                return self.preview_seed
            else:
                # Generate a seed now and store it (ensures preview/world consistency)
                import random
                seed = random.randint(1, 1000000)
                print(f"[CreateWorld] DEBUG: get_seed() generating new random seed: {seed}")
                self.preview_seed = seed
                # Generate preview with this seed
                self._update_preview()
                return seed
        
        # Manual seed input
        if self.seed_input.strip():
            try:
                seed = int(self.seed_input.strip())
                print(f"[CreateWorld] DEBUG: get_seed() returning manual seed from input: {seed}")
                # Update preview seed to match
                if seed != self.preview_seed:
                    self.preview_seed = seed
                    self.preview_cache = None  # Force preview update
                return seed
            except ValueError:
                # Invalid input - fall back to random
                import random
                seed = random.randint(1, 1000000)
                print(f"[CreateWorld] DEBUG: get_seed() invalid input, generating random seed: {seed}")
                self.preview_seed = seed
                self._update_preview()
                return seed
        else:
            # Empty input - use existing preview seed or generate new
            if self.preview_seed is not None:
                print(f"[CreateWorld] DEBUG: get_seed() empty input, using existing preview_seed: {self.preview_seed}")
                return self.preview_seed
            else:
                import random
                seed = random.randint(1, 1000000)
                print(f"[CreateWorld] DEBUG: get_seed() empty input, generating new random seed: {seed}")
                self.preview_seed = seed
                self._update_preview()
                return seed
    
    def handle_mouse_press(self, x: int, y: int, button: int, modifiers: int):
        """Handle mouse press"""
        if not self.active:
            return None
        
        if button != mouse.LEFT:
            return None
        
        # Check buttons
        button_y = self.panel_y + 50
        button_x_start = self.panel_x + (self.panel_width - (self.button_width * 2 + self.button_spacing)) // 2
        
        # Cancel button
        cancel_x = button_x_start
        if (cancel_x <= x <= cancel_x + self.button_width and
            button_y <= y <= button_y + self.button_height):
            return "cancel"
        
        # Create button
        create_x = button_x_start + self.button_width + self.button_spacing
        if (create_x <= x <= create_x + self.button_width and
            button_y <= y <= button_y + self.button_height):
            return "create"
        
        # Quit button (below cancel button)
        quit_button_y = button_y - (self.button_height + self.button_spacing)
        if (cancel_x <= x <= cancel_x + self.button_width and
            quit_button_y <= y <= quit_button_y + self.button_height):
            return "quit"
        
        # Random seed button
        seed_button_y = self.panel_y + 300
        seed_button_x = self.panel_x + 400
        seed_button_width = 150
        seed_button_height = 40
        if (seed_button_x <= x <= seed_button_x + seed_button_width and
            seed_button_y <= y <= seed_button_y + seed_button_height):
            self.use_random_seed = not self.use_random_seed
            if self.use_random_seed:
                self.seed_input = ""
            self._update_preview()
            return None
        
        # Check input field clicks
        name_field_y = self.panel_y + 450
        name_field_x = self.panel_x + 200
        name_field_width = 400
        name_field_height = 40
        
        if (name_field_x <= x <= name_field_x + name_field_width and
            name_field_y <= y <= name_field_y + name_field_height):
            self.focused_field = "name"
            return None
        
        seed_field_y = self.panel_y + 350
        seed_field_x = self.panel_x + 200
        seed_field_width = 200
        seed_field_height = 40
        
        if (seed_field_x <= x <= seed_field_x + seed_field_width and
            seed_field_y <= y <= seed_field_y + seed_field_height):
            # When clicking on seed field, update preview if we're switching TO it
            if self.focused_field != "seed":
                self._update_preview()  # Immediate update when focusing seed field
            self.focused_field = "seed"
            self.use_random_seed = False
            return None
        
        # Click outside fields = unfocus
        self.focused_field = None
        return None
    
    def handle_mouse_motion(self, x: int, y: int):
        """Handle mouse motion"""
        if not self.active:
            return
        
        # Check button hovers
        button_y = self.panel_y + 50
        button_x_start = self.panel_x + (self.panel_width - (self.button_width * 2 + self.button_spacing)) // 2
        
        # Cancel button
        cancel_x = button_x_start
        self.cancel_button_hovered = (
            cancel_x <= x <= cancel_x + self.button_width and
            button_y <= y <= button_y + self.button_height
        )
        
        # Create button
        create_x = button_x_start + self.button_width + self.button_spacing
        self.create_button_hovered = (
            create_x <= x <= create_x + self.button_width and
            button_y <= y <= button_y + self.button_height
        )
        
        # Quit button (below cancel button)
        quit_button_y = button_y - (self.button_height + self.button_spacing)
        self.quit_button_hovered = (
            cancel_x <= x <= cancel_x + self.button_width and
            quit_button_y <= y <= quit_button_y + self.button_height
        )
        
        # Random seed button
        seed_button_y = self.panel_y + 300
        seed_button_x = self.panel_x + 400
        seed_button_width = 150
        seed_button_height = 40
        self.random_seed_button_hovered = (
            seed_button_x <= x <= seed_button_x + seed_button_width and
            seed_button_y <= y <= seed_button_y + seed_button_height
        )
    
    def handle_key_press(self, symbol: int, modifiers: int):
        """Handle key press"""
        if not self.active:
            return None
        
        if symbol == key.ESCAPE:
            return "cancel"
        
        if symbol == key.TAB:
            # Switch focus between fields - update preview when leaving seed field
            if self.focused_field == "seed":
                self._update_preview()  # Immediate update when leaving seed field
            if self.focused_field == "name":
                self.focused_field = "seed"
            elif self.focused_field == "seed":
                self.focused_field = "name"
            else:
                self.focused_field = "name"
            return None
        
        if symbol == key.ENTER or symbol == key.RETURN:
            if self.focused_field is not None:
                # Update preview when pressing ENTER in seed field
                if self.focused_field == "seed":
                    self._update_preview()  # Immediate update on ENTER
                # Move to next field or create
                if self.focused_field == "name":
                    self.focused_field = "seed"
                else:
                    return "create"
            else:
                return "create"
            return None
        
        # Handle text input
        if self.focused_field == "name":
            if symbol == key.BACKSPACE:
                if self.world_name:
                    self.world_name = self.world_name[:-1]
                return None
            else:
                char = self._key_to_char(symbol, modifiers)
                if char:
                    self.world_name += char
                return None
        
        elif self.focused_field == "seed":
            if symbol == key.BACKSPACE:
                if self.seed_input:
                    self.seed_input = self.seed_input[:-1]
                    self._schedule_preview_update()
                return None
            else:
                char = self._key_to_char(symbol, modifiers)
                if char and char.isdigit() or char == '-':
                    self.seed_input += char
                    self.use_random_seed = False
                    self._schedule_preview_update()
                return None
        
        return None
    
    def _key_to_char(self, symbol: int, modifiers: int) -> Optional[str]:
        """Convert key symbol to character"""
        # Handle numbers
        if key._0 <= symbol <= key._9:
            return chr(ord('0') + (symbol - key._0))
        
        # Handle letters
        if key.A <= symbol <= key.Z:
            shift = (modifiers & key.MOD_SHIFT) != 0
            base_char = chr(ord('a') + (symbol - key.A))
            return base_char.upper() if shift else base_char
        
        # Handle space
        if symbol == key.SPACE:
            return ' '
        
        # Handle minus
        if symbol == key.MINUS:
            return '-'
        
        return None
    
    def _schedule_preview_update(self):
        """Schedule a preview update with debouncing"""
        import time
        self.last_seed_change_time = time.time()
        self.pending_preview_update = True
    
    def update(self, dt: float):
        """Update menu state (called every frame) - handles debounced preview updates"""
        if not self.active:
            return
        
        # Check if debounce time has passed and preview update is pending
        if self.pending_preview_update:
            import time
            elapsed_ms = (time.time() - self.last_seed_change_time) * 1000
            if elapsed_ms >= self.preview_update_debounce_ms:
                self._update_preview()
                self.pending_preview_update = False
    
    def _update_preview(self):
        """Update preview when seed changes"""
        # Determine seed to use
        if self.use_random_seed:
            # If we already have a preview seed, use it (for consistency)
            if self.preview_seed is not None:
                seed = self.preview_seed
            else:
                # Generate a new random seed and store it
                import random
                seed = random.randint(1, 1000000)
                self.preview_seed = seed
        else:
            # Use custom seed from input
            if self.seed_input.strip():
                try:
                    seed = int(self.seed_input.strip())
                    # Update preview seed to match
                    if seed != self.preview_seed:
                        self.preview_seed = seed
                        self.preview_cache = None  # Force regeneration
                except ValueError:
                    # Invalid input, use existing preview seed or generate new
                    if self.preview_seed is not None:
                        seed = self.preview_seed
                    else:
                        import random
                        seed = random.randint(1, 1000000)
                        self.preview_seed = seed
            else:
                # Empty input, use existing preview seed or generate new
                if self.preview_seed is not None:
                    seed = self.preview_seed
                else:
                    import random
                    seed = random.randint(1, 1000000)
                    self.preview_seed = seed
        
        # Check if we already have a preview for this seed
        if seed == self.preview_seed and self.preview_cache is not None:
            return  # Already generated with this seed
        
        try:
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
            
            # Note: Spawn marker is drawn as a separate cached shape, not in texture
            
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
            
            self.preview_cache = {
                'chunks': preview_chunks,  # Keep for compatibility
                'spawn_position': (0, 0),  # Default spawn at origin
                'texture': image_data,
                'sprite': sprite
            }
            self.preview_seed = seed  # Store seed for consistency
        except Exception as e:
            print(f"[CreateWorld] Error generating preview: {e}")
            import traceback
            traceback.print_exc()
            self.preview_cache = None
    
    def draw(self):
        """Draw create world menu using cached shapes"""
        if not self.active:
            return
        
        # Draw cached overlay (no recreation, just draw)
        self.overlay_rect.draw()
        
        # Draw cached panel background
        self.panel_bg_rect.draw()
        
        # Draw cached panel border
        if self.panel_border_rect:
            self.panel_border_rect.draw()
        else:
            for line in self.panel_border_lines:
                line.draw()
        
        # Draw cached title label
        self.title_label.draw()
        
        # Draw cached static labels
        self.name_label.draw()
        self.seed_label.draw()
        self.preview_label.draw()
        
        # Draw name input field
        name_field_x = self.panel_x + 200
        name_field_y = self.panel_y + 450
        name_field_width = 400
        name_field_height = 40
        
        # Input field background
        name_bg_color = (60, 60, 60) if self.focused_field != "name" else (80, 80, 80)
        name_field_bg = pyglet.shapes.Rectangle(
            name_field_x, name_field_y, name_field_width, name_field_height,
            color=name_bg_color
        )
        name_field_bg.draw()
        
        # Input field border
        border_color = (100, 200, 100) if self.focused_field == "name" else (100, 100, 100)
        try:
            name_field_border = pyglet.shapes.BorderedRectangle(
                name_field_x, name_field_y, name_field_width, name_field_height,
                border=2,
                color=name_bg_color,
                border_color=border_color
            )
            name_field_border.draw()
        except AttributeError:
            # Fallback
            for x1, y1, x2, y2 in [
                (name_field_x, name_field_y, name_field_x + name_field_width, name_field_y),
                (name_field_x + name_field_width, name_field_y, name_field_x + name_field_width, name_field_y + name_field_height),
                (name_field_x + name_field_width, name_field_y + name_field_height, name_field_x, name_field_y + name_field_height),
                (name_field_x, name_field_y + name_field_height, name_field_x, name_field_y)
            ]:
                line = pyglet.shapes.Line(x1, y1, x2, y2, width=2, color=border_color)
                line.draw()
        
        # Draw input fields (need to be recreated due to dynamic colors/borders)
        self._draw_input_fields()
        
        # Draw cached buttons (update colors based on hover state)
        self._draw_buttons()
        
        # Draw preview (only regenerate when seed changes, not every frame)
        preview_x = self.panel_x + 50
        preview_y = self.panel_y + 100
        if self.preview_cache:
            self._draw_preview(preview_x, preview_y)
    
    def _draw_input_fields(self):
        """Draw input fields (recreated due to dynamic colors/borders)"""
        import pyglet.shapes
        
        # Name input field
        name_field_x = self.panel_x + 200
        name_field_y = self.panel_y + 450
        name_field_width = 400
        name_field_height = 40
        
        name_bg_color = (60, 60, 60) if self.focused_field != "name" else (80, 80, 80)
        name_field_bg = pyglet.shapes.Rectangle(
            name_field_x, name_field_y, name_field_width, name_field_height,
            color=name_bg_color
        )
        name_field_bg.draw()
        
        border_color = (100, 200, 100) if self.focused_field == "name" else (100, 100, 100)
        try:
            name_field_border = pyglet.shapes.BorderedRectangle(
                name_field_x, name_field_y, name_field_width, name_field_height,
                border=2,
                color=name_bg_color,
                border_color=border_color
            )
            name_field_border.draw()
        except AttributeError:
            # Fallback
            for x1, y1, x2, y2 in [
                (name_field_x, name_field_y, name_field_x + name_field_width, name_field_y),
                (name_field_x + name_field_width, name_field_y, name_field_x + name_field_width, name_field_y + name_field_height),
                (name_field_x + name_field_width, name_field_y + name_field_height, name_field_x, name_field_y + name_field_height),
                (name_field_x, name_field_y + name_field_height, name_field_x, name_field_y)
            ]:
                line = pyglet.shapes.Line(x1, y1, x2, y2, width=2, color=border_color)
                line.draw()
        
        # Name text with cursor (update cached label text)
        display_name = self.world_name
        if self.focused_field == "name":
            display_name += "_"  # Cursor indicator
        self.name_input_label.text = display_name
        self.name_input_label.draw()
        
        # Seed input field
        seed_field_x = self.panel_x + 200
        seed_field_y = self.panel_y + 350
        seed_field_width = 200
        seed_field_height = 40
        
        # Input field background
        seed_bg_color = (60, 60, 60) if self.focused_field != "seed" else (80, 80, 80)
        seed_field_bg = pyglet.shapes.Rectangle(
            seed_field_x, seed_field_y, seed_field_width, seed_field_height,
            color=seed_bg_color
        )
        seed_field_bg.draw()
        
        # Input field border
        border_color = (100, 200, 100) if self.focused_field == "seed" else (100, 100, 100)
        try:
            seed_field_border = pyglet.shapes.BorderedRectangle(
                seed_field_x, seed_field_y, seed_field_width, seed_field_height,
                border=2,
                color=seed_bg_color,
                border_color=border_color
            )
            seed_field_border.draw()
        except AttributeError:
            # Fallback
            for x1, y1, x2, y2 in [
                (seed_field_x, seed_field_y, seed_field_x + seed_field_width, seed_field_y),
                (seed_field_x + seed_field_width, seed_field_y, seed_field_x + seed_field_width, seed_field_y + seed_field_height),
                (seed_field_x + seed_field_width, seed_field_y + seed_field_height, seed_field_x, seed_field_y + seed_field_height),
                (seed_field_x, seed_field_y + seed_field_height, seed_field_x, seed_field_y)
            ]:
                line = pyglet.shapes.Line(x1, y1, x2, y2, width=2, color=border_color)
                line.draw()
        
        # Seed text with cursor (update cached label text)
        if self.use_random_seed:
            display_seed = "Random"
        else:
            display_seed = self.seed_input
            if self.focused_field == "seed":
                display_seed += "_"  # Cursor indicator
        
        self.seed_input_label.text = display_seed
        self.seed_input_label.draw()
        

    
    def _draw_buttons(self):
        """Draw buttons using cached shapes (update colors based on hover state)"""
        # Calculate button positions
        button_y = self.panel_y + 50
        button_x_start = self.panel_x + (self.panel_width - (self.button_width * 2 + self.button_spacing)) // 2
        cancel_x = button_x_start
        quit_button_y = button_y - (self.button_height + self.button_spacing)
        
        # Update button colors based on hover state
        cancel_bg_color = (120, 80, 80) if self.cancel_button_hovered else (100, 60, 60)
        self.cancel_button_bg_rect.color = cancel_bg_color
        
        create_bg_color = (80, 120, 80) if self.create_button_hovered else (60, 100, 60)
        self.create_button_bg_rect.color = create_bg_color
        
        quit_bg_color = (150, 80, 80) if self.quit_button_hovered else (100, 60, 60)
        self.quit_button_bg_rect.color = quit_bg_color
        
        random_bg_color = (80, 120, 80) if self.random_seed_button_hovered else (60, 100, 60)
        self.random_button_bg_rect.color = random_bg_color
        
        # Update random button text
        random_button_text = "Use Random" if not self.use_random_seed else "Random ✓"
        self.random_button_label.text = random_button_text
        
        # Update quit button position (in case window was resized)
        self.quit_button_bg_rect.y = quit_button_y
        self.quit_button_label.y = quit_button_y + self.button_height // 2
        
        # Draw cached button backgrounds
        self.cancel_button_bg_rect.draw()
        self.create_button_bg_rect.draw()
        self.quit_button_bg_rect.draw()
        self.random_button_bg_rect.draw()
        
        # Draw cached button labels
        self.cancel_button_label.draw()
        self.create_button_label.draw()
        self.quit_button_label.draw()
        self.random_button_label.draw()
    
    def _draw_preview(self, x: int, y: int):
        """Draw world preview using cached texture and shapes (optimized)"""
        if not self.preview_cache or 'texture' not in self.preview_cache:
            return
        
        texture = self.preview_cache['texture']
        sprite = self.preview_cache.get('sprite')
        
        # Calculate scale to fit preview_size_pixels
        scale = self.preview_size_pixels / max(texture.width, texture.height)
        
        # Update and draw cached preview background (no recreation, just reposition)
        self.preview_bg_rect.x = x
        self.preview_bg_rect.y = y
        self.preview_bg_rect.draw()
        
        # Draw texture using sprite (much faster than individual rectangles)
        if sprite:
            sprite.x = x
            sprite.y = y
            sprite.scale = scale
            sprite.draw()
        else:
            # Fallback: draw texture directly (if sprite not available)
            texture.blit(x, y, width=int(texture.width * scale), height=int(texture.height * scale))
        
        # Draw spawn marker (center of preview) - reposition cached shape
        spawn_x = x + self.preview_size_pixels // 2
        spawn_y = y + self.preview_size_pixels // 2
        self.preview_spawn_marker.x = spawn_x - 2  # Center the 4x4 marker
        self.preview_spawn_marker.y = spawn_y - 2
        self.preview_spawn_marker.draw()

