"""
UI: Inventar-Menü mit Slot-basierter Struktur
"""
import pyglet
from pyglet.window import key, mouse
from typing import Optional, Dict, List, Tuple
from core import settings


class InventoryMenu:
    """Inventar-Menü mit Slot-basierter Struktur (9 Spalten x 6 Reihen: 5 Inventar + 1 Hotbar)"""
    
    def __init__(self, window_width: int, window_height: int, inventory_size: int = 45):
        """
        Initialize Inventory Menu
        
        Args:
            window_width: Window width in pixels
            window_height: Window height in pixels
            inventory_size: Total number of inventory slots (excluding hotbar). Default: 45 (9x5)
        """
        self.window_width = window_width
        self.window_height = window_height
        self.active = False
        
        # Inventory structure: slots[row][col] = {'item_id': str, 'amount': int} or None
        # Fixed width: 9 columns
        self.inventory_width = 9
        self.inventory_size = inventory_size  # Total slots (excluding hotbar)
        
        # Calculate inventory height dynamically: inventory_size / 9
        self.inventory_height = inventory_size // self.inventory_width
        self.hotbar_height = 1  # Hotbar row (always 1)
        self.total_rows = self.inventory_height + self.hotbar_height
        
        # Initialize empty inventory slots
        self.slots: List[List[Optional[Dict]]] = [
            [None for _ in range(self.inventory_width)]
            for _ in range(self.total_rows)
        ]
        
        # UI layout
        self.slot_size = 64  # Size of each slot in pixels
        self.slot_spacing = 4  # Spacing between slots
        self.panel_padding = 20  # Padding around inventory panel
        
        # Layout structure: Title, Main Inventory, Separator, Hotbar, Optional Details
        self.title_height = 50  # Height for title area
        self.hotbar_separator_height = 8  # Height of separator between main inventory and hotbar
        self.hotbar_separator_spacing = 4  # Additional spacing around separator
        
        # Optional right panel for item details (can be enabled later)
        self.show_details_panel = False  # Set to True to enable details panel
        self.details_panel_width = 200  # Width of details panel
        
        # Calculate layout
        self._calculate_layout()
    
    def _calculate_layout(self):
        """Calculate panel layout based on current inventory size"""
        # Main inventory area
        main_inventory_height = (self.inventory_height * self.slot_size) + \
                               ((self.inventory_height - 1) * self.slot_spacing)
        # Hotbar area
        hotbar_height = (self.hotbar_height * self.slot_size)
        # Total content height
        content_height = self.title_height + main_inventory_height + \
                        self.hotbar_separator_height + (2 * self.hotbar_separator_spacing) + \
                        hotbar_height
        
        panel_width = (self.inventory_width * self.slot_size) + \
                     ((self.inventory_width - 1) * self.slot_spacing) + \
                     (2 * self.panel_padding)
        
        # Add details panel width if enabled
        if self.show_details_panel:
            panel_width += self.details_panel_width + self.panel_padding
        
        panel_height = content_height + (2 * self.panel_padding)
        
        self.panel_width = panel_width
        self.panel_height = panel_height
        self.panel_x = (self.window_width - panel_width) // 2
        self.panel_y = (self.window_height - panel_height) // 2
        
        # Calculate area positions
        self.title_y = self.panel_y + self.panel_height - self.panel_padding - self.title_height
        self.main_inventory_y = self.title_y - main_inventory_height
        self.separator_y = self.main_inventory_y - self.hotbar_separator_spacing - self.hotbar_separator_height
        # hotbar_y is the bottom edge of the hotbar area (where slots start drawing from bottom)
        hotbar_height = (self.hotbar_height * self.slot_size)
        self.hotbar_y = self.separator_y - self.hotbar_separator_spacing - hotbar_height
        
        # Fonts
        self.title_font_name = "Arial"
        self.title_font_size = 32
        self.slot_font_name = "Arial"
        self.slot_font_size = 14  # Consistent font size for item amounts
        
        # Item rendering settings
        self.item_icon_padding = 4  # Padding around item icon within slot
        self.amount_font_size = 14  # Font size for amount display
        self.amount_offset_x = 2  # Offset from right edge for amount text
        self.amount_offset_y = 2  # Offset from bottom edge for amount text
        
        # Selected slot for dragging
        self.selected_slot: Optional[Tuple[int, int]] = None  # (row, col)
        self.drag_item: Optional[Dict] = None
        
        # Hotbar selection (0-8)
        self.selected_hotbar_slot = 0
        
        # Mouse hover tracking
        self.hovered_slot: Optional[Tuple[int, int]] = None  # (row, col)
    
    def set_inventory(self, inventory_data: Dict):
        """
        Set inventory from saved data
        
        Args:
            inventory_data: Dictionary with 'slots' (2D array) and 'inventory_size' (int)
        """
        # Update inventory_size if provided
        if 'inventory_size' in inventory_data:
            new_size = inventory_data['inventory_size']
            if new_size != self.inventory_size:
                # Resize inventory if size changed
                self.inventory_size = new_size
                self.inventory_height = new_size // self.inventory_width
                self.total_rows = self.inventory_height + self.hotbar_height
                
                # Resize slots array
                old_slots = self.slots.copy()
                self.slots = [
                    [None for _ in range(self.inventory_width)]
                    for _ in range(self.total_rows)
                ]
                
                # Copy old slots data
                for row in range(min(len(old_slots), self.total_rows)):
                    for col in range(min(len(old_slots[row]) if old_slots[row] else 0, self.inventory_width)):
                        self.slots[row][col] = old_slots[row][col] if old_slots[row] else None
                
                # Recalculate layout
                self._calculate_layout()
        
        # Copy slots data
        if 'slots' in inventory_data:
            slots_data = inventory_data['slots']
            # Copy slots data, ensuring we have enough rows
            for row in range(min(len(slots_data), self.total_rows)):
                for col in range(min(len(slots_data[row]) if slots_data[row] else 0, self.inventory_width)):
                    self.slots[row][col] = slots_data[row][col] if slots_data[row] else None
    
    def get_inventory_data(self) -> Dict:
        """
        Get inventory data for saving
        
        Returns:
            Dictionary with 'slots' (2D array) and 'inventory_size' (int)
        """
        return {
            'slots': [[slot.copy() if slot else None for slot in row] for row in self.slots],
            'inventory_size': self.inventory_size
        }
    
    def toggle(self):
        """Toggle inventory menu on/off"""
        self.active = not self.active
    
    def handle_key_press(self, symbol: int, modifiers: int) -> bool:
        """
        Handle key press events
        
        Returns:
            True if event was handled, False otherwise
        """
        if not self.active:
            return False
        
        # E or ESC to close inventory
        if symbol == key.E or symbol == key.ESCAPE:
            self.toggle()
            return True
        
        # Number keys 1-9 for hotbar selection
        if symbol >= key._1 and symbol <= key._9:
            hotbar_index = symbol - key._1
            if 0 <= hotbar_index < self.inventory_width:
                self.selected_hotbar_slot = hotbar_index
                return True
        
        return False
    
    def _get_slot_position(self, row: int, col: int) -> Tuple[int, int]:
        """
        Get the screen position (x, y) of a slot's top-left corner.
        
        This is the SINGLE SOURCE OF TRUTH for slot positioning.
        Used by both draw() and mouse handling to ensure consistency.
        
        Args:
            row: Slot row (0 = top inventory row, total_rows-1 = hotbar)
            col: Slot column (0-8)
            
        Returns:
            (x, y) tuple of slot's top-left corner in screen coordinates
        """
        slot_start_x = self.panel_x + self.panel_padding
        
        # Calculate Y position based on row
        if row == self.total_rows - 1:
            # Hotbar row: position below separator
            # hotbar_y is the bottom of the hotbar area, so slot_y = hotbar_y
            slot_y = self.hotbar_y
        else:
            # Main inventory rows: calculate from main_inventory_y
            slot_start_y = self.main_inventory_y + (self.inventory_height - 1) * (self.slot_size + self.slot_spacing)
            slot_y = slot_start_y - row * (self.slot_size + self.slot_spacing)
        
        slot_x = slot_start_x + col * (self.slot_size + self.slot_spacing)
        
        return (slot_x, slot_y)
    
    def handle_mouse_motion(self, x: int, y: int) -> bool:
        """
        Handle mouse motion events for hover highlighting
        
        Args:
            x: Mouse X coordinate (pyglet coordinate system: 0,0 is bottom-left)
            y: Mouse Y coordinate (pyglet coordinate system: 0,0 is bottom-left)
        
        Returns:
            True if event was handled, False otherwise
        """
        if not self.active:
            self.hovered_slot = None
            return False
        
        # Check if mouse is within inventory panel
        if not (self.panel_x <= x <= self.panel_x + self.panel_width and
                self.panel_y <= y <= self.panel_y + self.panel_height):
            self.hovered_slot = None
            return False
        
        # Check which slot is hovered by testing each slot's bounds
        # Use the same position calculation as draw() to ensure consistency
        self.hovered_slot = None
        
        # Iterate through all slots and check if mouse is within bounds
        for row in range(self.total_rows):
            for col in range(self.inventory_width):
                slot_x, slot_y = self._get_slot_position(row, col)
                
                # Check if mouse is within this slot's bounds
                if (slot_x <= x <= slot_x + self.slot_size and
                    slot_y <= y <= slot_y + self.slot_size):
                    self.hovered_slot = (row, col)
                    return True
        
        return False
    
    def handle_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> bool:
        """
        Handle mouse press events
        
        Returns:
            True if event was handled, False otherwise
        """
        if not self.active:
            return False
        
        # Check if click is within inventory panel
        if not (self.panel_x <= x <= self.panel_x + self.panel_width and
                self.panel_y <= y <= self.panel_y + self.panel_height):
            return False
        
        # Check which slot was clicked by testing each slot's bounds
        # Use the same position calculation as draw() to ensure consistency
        for row in range(self.total_rows):
            for col in range(self.inventory_width):
                slot_x, slot_y = self._get_slot_position(row, col)
                
                # Check if click is within this slot's bounds
                if (slot_x <= x <= slot_x + self.slot_size and
                    slot_y <= y <= slot_y + self.slot_size):
                    if button == mouse.LEFT:
                        # Left click: select/pick up item
                        self._handle_slot_click(row, col)
                        return True
        
        return False
    
    def _handle_slot_click(self, row: int, col: int):
        """Handle slot click (pick up/place item)"""
        slot = self.slots[row][col]
        
        if self.drag_item is None:
            # Pick up item from slot
            if slot is not None:
                self.drag_item = slot.copy()
                self.selected_slot = (row, col)
                self.slots[row][col] = None
        else:
            # Place item in slot
            if slot is None:
                # Empty slot: place item
                self.slots[row][col] = self.drag_item
                self.drag_item = None
                self.selected_slot = None
            elif slot.get('item_id') == self.drag_item.get('item_id'):
                # Same item: stack
                self.slots[row][col]['amount'] += self.drag_item['amount']
                self.drag_item = None
                self.selected_slot = None
            else:
                # Different item: swap
                temp = self.slots[row][col]
                self.slots[row][col] = self.drag_item
                self.drag_item = temp
                self.selected_slot = (row, col)
    
    def add_item(self, item_id: str, amount: int = 1) -> bool:
        """
        Add item to inventory
        
        Args:
            item_id: Item identifier
            amount: Amount to add
            
        Returns:
            True if item was added, False if inventory is full
        """
        # Try to stack with existing items first
        for row in range(self.total_rows):
            for col in range(self.inventory_width):
                slot = self.slots[row][col]
                if slot is not None and slot.get('item_id') == item_id:
                    slot['amount'] += amount
                    return True
        
        # Find empty slot
        for row in range(self.total_rows):
            for col in range(self.inventory_width):
                if self.slots[row][col] is None:
                    self.slots[row][col] = {'item_id': item_id, 'amount': amount}
                    return True
        
        # Inventory is full
        return False
    
    def draw(self):
        """Draw inventory menu"""
        if not self.active:
            return
        
        # Draw semi-transparent overlay
        import pyglet.shapes
        overlay = pyglet.shapes.Rectangle(
            0, 0, self.window_width, self.window_height,
            color=(0, 0, 0)
        )
        overlay.opacity = 180
        overlay.draw()
        
        # Draw inventory panel background
        panel_bg = pyglet.shapes.Rectangle(
            self.panel_x, self.panel_y,
            self.panel_width, self.panel_height,
            color=(40, 40, 50)
        )
        panel_bg.draw()
        
        # Draw panel border
        panel_border = pyglet.shapes.BorderedRectangle(
            self.panel_x, self.panel_y,
            self.panel_width, self.panel_height,
            border=2, color=(100, 100, 120), border_color=(200, 200, 200)
        )
        panel_border.draw()
        
        # Draw title area
        title_label = pyglet.text.Label(
            "Inventory",
            font_name=self.title_font_name,
            font_size=self.title_font_size,
            x=self.panel_x + self.panel_width // 2,
            y=self.title_y + self.title_height // 2,
            anchor_x='center',
            anchor_y='center',
            color=(255, 255, 255, 255)
        )
        title_label.draw()
        
        # Draw separator line between main inventory and hotbar
        separator_x = self.panel_x + self.panel_padding
        separator_width = (self.inventory_width * self.slot_size) + \
                         ((self.inventory_width - 1) * self.slot_spacing)
        separator_line = pyglet.shapes.Rectangle(
            separator_x, self.separator_y,
            separator_width, self.hotbar_separator_height,
            color=(80, 80, 90)  # Subtle separator color
        )
        separator_line.draw()
        
        # Draw main inventory slots (5 rows) and hotbar (1 row)
        # Use _get_slot_position() for consistent positioning
        for row in range(self.total_rows):
            for col in range(self.inventory_width):
                slot_x, slot_y = self._get_slot_position(row, col)
                self._draw_slot(slot_x, slot_y, row, col)
        
        # Draw details panel (if enabled)
        if self.show_details_panel:
            self._draw_details_panel()
    
    def _draw_slot(self, slot_x: int, slot_y: int, row: int, col: int):
        """Draw a single inventory slot"""
        is_hotbar = (row == self.total_rows - 1)
        is_hovered = (self.hovered_slot == (row, col))
        is_selected_hotbar = (is_hotbar and col == self.selected_hotbar_slot)
        
        # Determine slot colors based on type and state
        if is_hotbar:
            # Hotbar: kräftigerer Rahmen, dunklere Füllung
            slot_bg_color = (45, 45, 55)  # Darker background
            slot_border_color = (150, 150, 170)  # Brighter border for hotbar
            slot_border_width = 2
            
            if is_selected_hotbar:
                slot_bg_color = (70, 70, 85)  # Highlighted hotbar slot
                slot_border_color = (200, 200, 220)  # Even brighter border
        else:
            # Main inventory: gedämpfter, hellerer Rahmen
            slot_bg_color = (55, 55, 65)  # Slightly lighter background
            slot_border_color = (100, 100, 115)  # Softer border
            slot_border_width = 1
        
        # Hover highlight (applies to both hotbar and main inventory)
        if is_hovered:
            slot_bg_color = tuple(min(255, c + 20) for c in slot_bg_color)  # Brighten on hover
            slot_border_color = tuple(min(255, c + 30) for c in slot_border_color)  # Brighten border
        
        # Draw slot background (darker fill)
        slot_bg = pyglet.shapes.Rectangle(
            slot_x + 1, slot_y + 1,  # Slight inset for border
            self.slot_size - 2, self.slot_size - 2,
            color=slot_bg_color
        )
        slot_bg.draw()
        
        # Draw slot border (brighter frame)
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
        slot = self.slots[row][col]
        if slot is not None:
            item_id = slot.get('item_id', 'unknown')
            amount = slot.get('amount', 0)
            
            # Calculate icon area with padding (reserved space for future icons)
            icon_x = slot_x + self.item_icon_padding
            icon_y = slot_y + self.item_icon_padding
            icon_size = self.slot_size - (2 * self.item_icon_padding)
            
            # Draw item icon (placeholder: colored rectangle)
            # TODO: Replace with actual item sprites/icons
            item_color = self._get_item_color(item_id)
            item_rect = pyglet.shapes.Rectangle(
                icon_x, icon_y,
                icon_size, icon_size,
                color=item_color
            )
            item_rect.draw()
            
            # Draw amount text (bottom-right corner, white)
            # Always show amount, even if it's 1 (for consistency)
            amount_label = pyglet.text.Label(
                str(amount),
                font_name=self.slot_font_name,
                font_size=self.amount_font_size,
                x=slot_x + self.slot_size - self.amount_offset_x,
                y=slot_y + self.amount_offset_y,
                anchor_x='right',
                anchor_y='bottom',
                color=(255, 255, 255, 255)  # White text
            )
            amount_label.draw()
    
    def _draw_details_panel(self):
        """Draw optional details panel on the right side"""
        if not self.show_details_panel:
            return
        
        details_x = self.panel_x + self.panel_padding + \
                   (self.inventory_width * self.slot_size) + \
                   ((self.inventory_width - 1) * self.slot_spacing) + \
                   self.panel_padding
        details_y = self.panel_y + self.panel_padding
        details_height = self.panel_height - (2 * self.panel_padding)
        
        # Draw details panel background
        details_bg = pyglet.shapes.Rectangle(
            details_x, details_y,
            self.details_panel_width, details_height,
            color=(35, 35, 45)
        )
        details_bg.draw()
        
        # Draw details panel border
        details_border = pyglet.shapes.BorderedRectangle(
            details_x, details_y,
            self.details_panel_width, details_height,
            border=2, color=(50, 50, 60), border_color=(120, 120, 140)
        )
        details_border.draw()
        
        # Draw placeholder text
        details_label = pyglet.text.Label(
            "Item Details",
            font_name=self.slot_font_name,
            font_size=16,
            x=details_x + self.details_panel_width // 2,
            y=details_y + details_height - 20,
            anchor_x='center',
            anchor_y='center',
            color=(200, 200, 200, 255)
        )
        details_label.draw()
        
        # TODO: Show item details when slot is hovered/selected
        
        # Draw dragged item (if any)
        if self.drag_item is not None:
            # Get mouse position (would need to be passed in)
            # For now, draw at last known position or center
            pass  # TODO: Implement drag preview
    
    def _get_item_color(self, item_id: str) -> Tuple[int, int, int]:
        """Get color for item (placeholder until sprites are implemented)"""
        # Simple hash-based color generation
        hash_val = hash(item_id) % 360
        import colorsys
        rgb = colorsys.hsv_to_rgb(hash_val / 360.0, 0.7, 0.9)
        return (int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255))

