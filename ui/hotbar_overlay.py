"""
UI: Hotbar Overlay - Permanent hotbar display at bottom of screen
"""
import pyglet
from pyglet.window import key
from typing import Optional, Dict, Tuple


class HotbarOverlay:
    """Permanent hotbar overlay displayed at bottom of screen"""
    
    def __init__(self, window_width: int, window_height: int, item_texture_manager=None):
        """
        Initialize Hotbar Overlay
        
        Args:
            window_width: Window width in pixels
            window_height: Window height in pixels
            item_texture_manager: ItemTextureManager instance for rendering item sprites
        """
        self.window_width = window_width
        self.window_height = window_height
        
        # Hotbar settings
        self.hotbar_width = 9  # 9 slots
        self.slot_size = 64  # Size of each slot in pixels
        self.slot_spacing = 4  # Spacing between slots
        self.hotbar_padding = 10  # Padding around hotbar
        self.hotbar_bottom_offset = 20  # Offset from bottom of screen
        
        # Calculate hotbar position (centered horizontally, at bottom)
        hotbar_width = (self.hotbar_width * self.slot_size) + \
                      ((self.hotbar_width - 1) * self.slot_spacing) + \
                      (2 * self.hotbar_padding)
        self.hotbar_x = (window_width - hotbar_width) // 2
        self.hotbar_y = self.hotbar_bottom_offset
        
        # Selected slot (0-8)
        self.selected_slot = 0
        
        # Reference to inventory menu (will be set externally)
        self.inventory_menu = None
        
        # Item texture manager for rendering item sprites
        self.item_texture_manager = item_texture_manager
        
        # Fonts
        self.slot_font_name = "Arial"
        self.amount_font_size = 14
        
        # Item rendering settings
        self.item_icon_padding = 4
        self.item_sprite_size = 32  # Fixed size for all item sprites (same as inventory)
        self.amount_offset_x = 2
        self.amount_offset_y = 2
    
    def set_inventory_menu(self, inventory_menu):
        """Set reference to inventory menu to access hotbar slots"""
        self.inventory_menu = inventory_menu
    
    def handle_key_press(self, symbol: int, modifiers: int) -> bool:
        """
        Handle key press events for hotbar selection
        
        Returns:
            True if event was handled, False otherwise
        """
        # Number keys 1-9 for hotbar selection
        if symbol >= key._1 and symbol <= key._9:
            hotbar_index = symbol - key._1
            if 0 <= hotbar_index < self.hotbar_width:
                self.selected_slot = hotbar_index
                # Also update inventory menu's selected slot if available
                if self.inventory_menu:
                    self.inventory_menu.selected_hotbar_slot = hotbar_index
                return True
        
        return False
    
    def handle_mouse_scroll(self, scroll_y: float) -> bool:
        """
        Handle mouse scroll events for hotbar slot selection
        
        Args:
            scroll_y: Scroll direction (positive = up, negative = down)
        
        Returns:
            True if event was handled, False otherwise
        """
        if scroll_y > 0:  # Scroll up = previous slot
            self.selected_slot = (self.selected_slot - 1) % self.hotbar_width
        elif scroll_y < 0:  # Scroll down = next slot
            self.selected_slot = (self.selected_slot + 1) % self.hotbar_width
        else:
            return False
        
        # Also update inventory menu's selected slot if available
        if self.inventory_menu:
            self.inventory_menu.selected_hotbar_slot = self.selected_slot
        
        return True
    
    def get_slot_position(self, slot_index: int) -> Tuple[int, int]:
        """
        Get screen position (x, y) of a hotbar slot's bottom-left corner
        
        Args:
            slot_index: Slot index (0-8)
            
        Returns:
            (x, y) tuple of slot's bottom-left corner in screen coordinates
        """
        slot_x = self.hotbar_x + self.hotbar_padding + \
                slot_index * (self.slot_size + self.slot_spacing)
        slot_y = self.hotbar_y
        
        return (slot_x, slot_y)
    
    def draw(self):
        """Draw hotbar overlay"""
        if not self.inventory_menu:
            return
        
        # Get hotbar row (last row in inventory)
        hotbar_row = self.inventory_menu.total_rows - 1
        
        # Draw hotbar background (semi-transparent)
        hotbar_width = (self.hotbar_width * self.slot_size) + \
                      ((self.hotbar_width - 1) * self.slot_spacing) + \
                      (2 * self.hotbar_padding)
        hotbar_height = self.slot_size + (2 * self.hotbar_padding)
        
        bg = pyglet.shapes.Rectangle(
            self.hotbar_x, self.hotbar_y,
            hotbar_width, hotbar_height,
            color=(20, 20, 30)
        )
        bg.opacity = 200
        bg.draw()
        
        # Draw hotbar border
        border = pyglet.shapes.BorderedRectangle(
            self.hotbar_x, self.hotbar_y,
            hotbar_width, hotbar_height,
            border=2, color=(40, 40, 50), border_color=(150, 150, 170)
        )
        border.draw()
        
        # Draw slots
        for slot_index in range(self.hotbar_width):
            slot_x, slot_y = self.get_slot_position(slot_index)
            self._draw_slot(slot_x, slot_y, slot_index, hotbar_row)
    
    def _draw_slot(self, slot_x: int, slot_y: int, slot_index: int, row: int):
        """Draw a single hotbar slot"""
        is_selected = (slot_index == self.selected_slot)
        
        # Determine slot colors
        slot_bg_color = (45, 45, 55)  # Darker background
        slot_border_color = (150, 150, 170)  # Brighter border for hotbar
        slot_border_width = 2
        
        if is_selected:
            slot_bg_color = (70, 70, 85)  # Highlighted hotbar slot
            slot_border_color = (200, 200, 220)  # Even brighter border
        
        # Draw slot background
        slot_bg = pyglet.shapes.Rectangle(
            slot_x + 1, slot_y + 1,  # Slight inset for border
            self.slot_size - 2, self.slot_size - 2,
            color=slot_bg_color
        )
        slot_bg.draw()
        
        # Draw slot border
        # Top border
        top_border = pyglet.shapes.Rectangle(
            slot_x, slot_y + self.slot_size - slot_border_width,
            self.slot_size, slot_border_width,
            color=slot_border_color
        )
        top_border.draw()
        
        # Bottom border
        bottom_border = pyglet.shapes.Rectangle(
            slot_x, slot_y,
            self.slot_size, slot_border_width,
            color=slot_border_color
        )
        bottom_border.draw()
        
        # Left border
        left_border = pyglet.shapes.Rectangle(
            slot_x, slot_y,
            slot_border_width, self.slot_size,
            color=slot_border_color
        )
        left_border.draw()
        
        # Right border
        right_border = pyglet.shapes.Rectangle(
            slot_x + self.slot_size - slot_border_width, slot_y,
            slot_border_width, self.slot_size,
            color=slot_border_color
        )
        right_border.draw()
        
        # Draw item in slot
        if self.inventory_menu and row < len(self.inventory_menu.slots):
            slot = self.inventory_menu.slots[row][slot_index]
            if slot is not None:
                item_id = slot.get('item_id', 'unknown')
                amount = slot.get('amount', 0)
                
                # Calculate icon area - all items rendered as 32x32 pixels with 4px padding
                item_padding = 4  # Padding around item (slot is 64x64, item is 32x32)
                icon_x = slot_x + item_padding  # 4px padding from left
                icon_y = slot_y + item_padding  # 4px padding from bottom
                
                # Draw item sprite if available, otherwise fallback to colored rectangle
                if self.item_texture_manager:
                    try:
                        pyglet_img = self.item_texture_manager.get_pyglet_image(item_id)
                        if pyglet_img:
                            # Create sprite from pyglet image
                            sprite = pyglet.sprite.Sprite(pyglet_img, x=icon_x, y=icon_y)
                            # Scale to target size (32x32) - uses NEAREST filtering for pixel-perfect scaling
                            tex_width = pyglet_img.width
                            tex_height = pyglet_img.height
                            # Scale based on the larger dimension to ensure the sprite fits within target size
                            scale = self.item_sprite_size / max(tex_width, tex_height)
                            sprite.scale = scale
                            sprite.draw()
                        else:
                            # No image available, use fallback
                            item_color = self._get_item_color(item_id)
                            item_rect = pyglet.shapes.Rectangle(
                                icon_x, icon_y,
                                self.item_sprite_size, self.item_sprite_size,
                                color=item_color
                            )
                            item_rect.draw()
                    except Exception as e:
                        # Error loading texture, use fallback
                        item_color = self._get_item_color(item_id)
                        item_rect = pyglet.shapes.Rectangle(
                            icon_x, icon_y,
                            self.item_sprite_size, self.item_sprite_size,
                            color=item_color
                        )
                        item_rect.draw()
                else:
                    # No texture manager available, use fallback
                    item_color = self._get_item_color(item_id)
                    item_rect = pyglet.shapes.Rectangle(
                        icon_x, icon_y,
                        self.item_sprite_size, self.item_sprite_size,
                        color=item_color
                    )
                    item_rect.draw()
                
                # Draw amount text (bottom-right corner, white)
                if amount > 1:
                    amount_label = pyglet.text.Label(
                        str(amount),
                        font_name=self.slot_font_name,
                        font_size=self.amount_font_size,
                        x=slot_x + self.slot_size - self.amount_offset_x,
                        y=slot_y + self.amount_offset_y,
                        anchor_x='right',
                        anchor_y='bottom',
                        color=(255, 255, 255, 255)
                    )
                    amount_label.draw()
        
        # Draw slot number (top-left corner, small)
        slot_number_label = pyglet.text.Label(
            str(slot_index + 1),
            font_name=self.slot_font_name,
            font_size=12,
            x=slot_x + 4,
            y=slot_y + self.slot_size - 4,
            anchor_x='left',
            anchor_y='top',
            color=(200, 200, 200, 200)
        )
        slot_number_label.draw()
    
    def _get_item_color(self, item_id: str) -> Tuple[int, int, int]:
        """Get color for item (placeholder until sprites are implemented)"""
        # Simple hash-based color generation
        hash_val = hash(item_id) % 360
        import colorsys
        rgb = colorsys.hsv_to_rgb(hash_val / 360.0, 0.7, 0.9)
        return (int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255))
    
    def update_window_size(self, width: int, height: int):
        """Update overlay position when window is resized"""
        self.window_width = width
        self.window_height = height
        
        # Recalculate hotbar position
        hotbar_width = (self.hotbar_width * self.slot_size) + \
                      ((self.hotbar_width - 1) * self.slot_spacing) + \
                      (2 * self.hotbar_padding)
        self.hotbar_x = (width - hotbar_width) // 2
        self.hotbar_y = self.hotbar_bottom_offset

