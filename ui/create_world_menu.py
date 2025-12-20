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
        
        # UI layout
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
        
        # Button dimensions
        self.button_width = 200
        self.button_height = 50
        self.button_spacing = 20
    
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
            self.focused_field = "seed"
            self.use_random_seed = False
            self._update_preview()
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
            # Switch focus between fields
            if self.focused_field == "name":
                self.focused_field = "seed"
            elif self.focused_field == "seed":
                self.focused_field = "name"
            else:
                self.focused_field = "name"
            return None
        
        if symbol == key.ENTER or symbol == key.RETURN:
            if self.focused_field is not None:
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
                    self._update_preview()
                return None
            else:
                char = self._key_to_char(symbol, modifiers)
                if char and char.isdigit() or char == '-':
                    self.seed_input += char
                    self.use_random_seed = False
                    self._update_preview()
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
            
            # Generate first 5x5 chunks (chunks 0,0 to 4,4)
            preview_chunks = []
            for chunk_y in range(self.preview_size):
                for chunk_x in range(self.preview_size):
                    chunk = terrain_gen.generate_chunk(chunk_x, chunk_y, settings.CHUNK_SIZE)
                    preview_chunks.append((chunk_x, chunk_y, chunk))
            
            self.preview_cache = {
                'chunks': preview_chunks,
                'spawn_position': (0, 0)  # Default spawn at origin
            }
            self.preview_seed = seed  # Store seed for consistency
        except Exception as e:
            print(f"[CreateWorld] Error generating preview: {e}")
            self.preview_cache = None
    
    def draw(self):
        """Draw create world menu"""
        if not self.active:
            return
        
        # Draw semi-transparent overlay
        import pyglet.shapes
        overlay = pyglet.shapes.Rectangle(
            0, 0, self.window_width, self.window_height,
            color=(0, 0, 0)
        )
        overlay.opacity = 200
        overlay.draw()
        
        # Draw panel background
        panel_bg = pyglet.shapes.Rectangle(
            self.panel_x, self.panel_y, self.panel_width, self.panel_height,
            color=(40, 40, 40)
        )
        panel_bg.draw()
        
        # Draw panel border
        try:
            panel_border = pyglet.shapes.BorderedRectangle(
                self.panel_x, self.panel_y, self.panel_width, self.panel_height,
                border=3,
                color=(40, 40, 40),
                border_color=(150, 150, 150)
            )
            panel_border.draw()
        except AttributeError:
            # Fallback: draw border with lines
            border_color = (150, 150, 150)
            lines = [
                (self.panel_x, self.panel_y, self.panel_x + self.panel_width, self.panel_y),
                (self.panel_x + self.panel_width, self.panel_y, self.panel_x + self.panel_width, self.panel_y + self.panel_height),
                (self.panel_x + self.panel_width, self.panel_y + self.panel_height, self.panel_x, self.panel_y + self.panel_height),
                (self.panel_x, self.panel_y + self.panel_height, self.panel_x, self.panel_y)
            ]
            for x1, y1, x2, y2 in lines:
                line = pyglet.shapes.Line(x1, y1, x2, y2, width=3, color=border_color)
                line.draw()
        
        # Draw title
        title_label = pyglet.text.Label(
            "Create New World",
            font_name=self.title_font_name,
            font_size=self.title_font_size,
            color=(255, 255, 255, 255),
            x=self.panel_x + self.panel_width // 2,
            y=self.panel_y + self.panel_height - 50,
            anchor_x='center',
            anchor_y='center'
        )
        title_label.draw()
        
        # Draw world name input
        name_label = pyglet.text.Label(
            "World Name:",
            font_name=self.label_font_name,
            font_size=self.label_font_size,
            color=(255, 255, 255, 255),
            x=self.panel_x + 50,
            y=self.panel_y + 470,
            anchor_x='left',
            anchor_y='center'
        )
        name_label.draw()
        
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
        
        # Name text with cursor
        display_name = self.world_name
        if self.focused_field == "name":
            display_name += "_"  # Cursor indicator
        name_text_label = pyglet.text.Label(
            display_name,
            font_name=self.input_font_name,
            font_size=self.input_font_size,
            color=(255, 255, 255, 255),
            x=name_field_x + 10,
            y=name_field_y + name_field_height // 2,
            anchor_x='left',
            anchor_y='center'
        )
        name_text_label.draw()
        
        # Draw seed input
        seed_label = pyglet.text.Label(
            "Seed:",
            font_name=self.label_font_name,
            font_size=self.label_font_size,
            color=(255, 255, 255, 255),
            x=self.panel_x + 50,
            y=self.panel_y + 370,
            anchor_x='left',
            anchor_y='center'
        )
        seed_label.draw()
        
        # Draw seed input field
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
        
        # Seed text with cursor
        if self.use_random_seed:
            display_seed = "Random"
        else:
            display_seed = self.seed_input
            if self.focused_field == "seed":
                display_seed += "_"  # Cursor indicator
        
        seed_text_label = pyglet.text.Label(
            display_seed,
            font_name=self.input_font_name,
            font_size=self.input_font_size,
            color=(255, 255, 255, 255),
            x=seed_field_x + 10,
            y=seed_field_y + seed_field_height // 2,
            anchor_x='left',
            anchor_y='center'
        )
        seed_text_label.draw()
        
        # Random seed button
        random_button_x = self.panel_x + 400
        random_button_y = self.panel_y + 300
        random_button_width = 150
        random_button_height = 40
        
        random_bg_color = (80, 120, 80) if self.random_seed_button_hovered else (60, 100, 60)
        random_button_bg = pyglet.shapes.Rectangle(
            random_button_x, random_button_y, random_button_width, random_button_height,
            color=random_bg_color
        )
        random_button_bg.draw()
        
        random_button_text = "Use Random" if not self.use_random_seed else "Random ✓"
        random_button_label = pyglet.text.Label(
            random_button_text,
            font_name=self.label_font_name,
            font_size=18,
            color=(255, 255, 255, 255),
            x=random_button_x + random_button_width // 2,
            y=random_button_y + random_button_height // 2,
            anchor_x='center',
            anchor_y='center'
        )
        random_button_label.draw()
        
        # Draw preview
        preview_x = self.panel_x + 50
        preview_y = self.panel_y + 100
        preview_label = pyglet.text.Label(
            "Preview:",
            font_name=self.label_font_name,
            font_size=self.label_font_size,
            color=(255, 255, 255, 255),
            x=preview_x,
            y=preview_y + 120,
            anchor_x='left',
            anchor_y='center'
        )
        preview_label.draw()
        
        # Draw preview (only regenerate when seed changes, not every frame)
        if self.preview_cache:
            self._draw_preview(preview_x, preview_y)
        
        # Draw buttons
        button_y = self.panel_y + 50
        button_x_start = self.panel_x + (self.panel_width - (self.button_width * 2 + self.button_spacing)) // 2
        
        # Cancel button
        cancel_x = button_x_start
        cancel_bg_color = (120, 80, 80) if self.cancel_button_hovered else (100, 60, 60)
        cancel_button_bg = pyglet.shapes.Rectangle(
            cancel_x, button_y, self.button_width, self.button_height,
            color=cancel_bg_color
        )
        cancel_button_bg.draw()
        
        cancel_label = pyglet.text.Label(
            "Cancel",
            font_name=self.label_font_name,
            font_size=24,
            color=(255, 255, 255, 255),
            x=cancel_x + self.button_width // 2,
            y=button_y + self.button_height // 2,
            anchor_x='center',
            anchor_y='center'
        )
        cancel_label.draw()
        
        # Create button
        create_x = button_x_start + self.button_width + self.button_spacing
        create_bg_color = (80, 120, 80) if self.create_button_hovered else (60, 100, 60)
        create_button_bg = pyglet.shapes.Rectangle(
            create_x, button_y, self.button_width, self.button_height,
            color=create_bg_color
        )
        create_button_bg.draw()
        
        create_label = pyglet.text.Label(
            "Create World",
            font_name=self.label_font_name,
            font_size=24,
            color=(255, 255, 255, 255),
            x=create_x + self.button_width // 2,
            y=button_y + self.button_height // 2,
            anchor_x='center',
            anchor_y='center'
        )
        create_label.draw()
    
    def _draw_preview(self, x: int, y: int):
        """Draw world preview (5x5 chunks)"""
        if not self.preview_cache:
            return
        
        # Calculate tile size to fit preview nicely
        # Use a larger preview size to ensure all tiles are visible
        preview_size_pixels = 150  # 150x150 pixels for preview
        total_tiles = self.preview_size * settings.CHUNK_SIZE  # 5 * 15 = 75 tiles
        tile_size = max(1, preview_size_pixels // total_tiles)  # Ensure at least 1 pixel per tile
        
        # Recalculate actual preview size to match exactly
        actual_preview_size = total_tiles * tile_size
        
        # Draw preview background (exact size)
        import pyglet.shapes
        preview_bg = pyglet.shapes.Rectangle(
            x, y, actual_preview_size, actual_preview_size,
            color=(20, 20, 20)
        )
        preview_bg.draw()
        
        # Draw chunks
        for chunk_x, chunk_y, chunk in self.preview_cache['chunks']:
            chunk_screen_x = x + chunk_x * settings.CHUNK_SIZE * tile_size
            chunk_screen_y = y + chunk_y * settings.CHUNK_SIZE * tile_size
            
            # Draw tiles
            for tile_y in range(settings.CHUNK_SIZE):
                for tile_x in range(settings.CHUNK_SIZE):
                    tile = chunk[tile_y][tile_x]
                    tile_screen_x = chunk_screen_x + tile_x * tile_size
                    tile_screen_y = chunk_screen_y + tile_y * tile_size
                    
                    # Draw tile
                    color = tile.get('color', (100, 100, 100))
                    tile_rect = pyglet.shapes.Rectangle(
                        tile_screen_x, tile_screen_y, tile_size, tile_size,
                        color=color
                    )
                    tile_rect.draw()
        
        # Mark spawn position (center of preview)
        spawn_x = x + actual_preview_size // 2
        spawn_y = y + actual_preview_size // 2
        spawn_marker = pyglet.shapes.Rectangle(
            spawn_x - 2, spawn_y - 2, 4, 4,
            color=(255, 0, 0)
        )
        spawn_marker.draw()

