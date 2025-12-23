"""
UI: Pause-Menü mit Continue, Settings, Save, Quit Buttons (Pyglet-Version)
"""
from typing import Optional
from pyglet.window import key, mouse
import pyglet.shapes
import pyglet.text


class PauseMenu:
    """Pause-Menü mit Continue, Settings, Save, Quit (Pyglet-Version)"""
    
    def __init__(self, window_width: int, window_height: int):
        """
        Initialize Pause Menu
        
        Args:
            window_width: Window width in pixels
            window_height: Window height in pixels
        """
        self.window_width = window_width
        self.window_height = window_height
        self.active = False
        
        # Menu references (set externally)
        self.save_menu = None
        self.settings_menu = None
        
        # Button dimensions
        self.button_width = 400
        self.button_height = 60
        self.button_spacing = 20
        self.start_y = 200
        
        # Button hover states
        self.button_hovered = {
            "Continue": False,
            "Settings": False,
            "Save": False,
            "Return to Menu": False
        }
        
        # Initialize cached UI shapes
        self._init_cached_shapes()
    
    def _init_cached_shapes(self):
        """Initialize all cached UI shapes"""
        # Overlay (full-screen semi-transparent)
        self.overlay_rect = pyglet.shapes.Rectangle(
            0, 0, self.window_width, self.window_height,
            color=(0, 0, 0)
        )
        self.overlay_rect.opacity = 200
        
        # Title label
        self.title_label = pyglet.text.Label(
            "PAUSED",
            font_name="Arial",
            font_size=72,
            color=(255, 255, 255, 255),
            x=self.window_width // 2,
            y=self.window_height // 2 + 200,
            anchor_x='center',
            anchor_y='center'
        )
        
        # Button backgrounds and labels (cached)
        self.button_bg_rects = {}
        self.button_labels = {}
        
        button_names = ["Continue", "Settings", "Save", "Return to Menu"]
        button_x = self.window_width // 2 - self.button_width // 2
        
        for i, name in enumerate(button_names):
            button_y = self.start_y + i * (self.button_height + self.button_spacing)
            
            # Background rectangle
            self.button_bg_rects[name] = pyglet.shapes.Rectangle(
                button_x, button_y, self.button_width, self.button_height,
                color=(70, 70, 70)  # Default color
            )
            
            # Label
            self.button_labels[name] = pyglet.text.Label(
                name,
                font_name="Arial",
                font_size=40,
                color=(255, 255, 255, 255),
                x=button_x + self.button_width // 2,
                y=button_y + self.button_height // 2,
                anchor_x='center',
                anchor_y='center'
            )
    
    def show(self):
        """Show the pause menu"""
        self.active = True
    
    def hide(self):
        """Hide the pause menu"""
        self.active = False
    
    def toggle(self):
        """Toggle pause menu"""
        self.active = not self.active
    
    def handle_key_press(self, symbol: int, modifiers: int) -> Optional[str]:
        """Handle key press"""
        if not self.active:
            return None
        
        if symbol == key.ESCAPE:
            self.hide()
            return "Continue"
        
        return None
    
    def handle_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> Optional[str]:
        """Handle mouse press"""
        if not self.active:
            return None
        
        if button != mouse.LEFT:
            return None
        
        button_names = ["Continue", "Settings", "Save", "Return to Menu"]
        button_x = self.window_width // 2 - self.button_width // 2
        
        for i, name in enumerate(button_names):
            button_y = self.start_y + i * (self.button_height + self.button_spacing)
            
            if (button_x <= x <= button_x + self.button_width and
                button_y <= y <= button_y + self.button_height):
                
                if name == "Continue":
                    self.hide()
                    return "Continue"
                
                elif name == "Settings":
                    if self.settings_menu:
                        self.active = False
                        self.settings_menu.active = True
                    return "Settings"
                
                elif name == "Save":
                    if self.save_menu:
                        self.active = False
                        self.save_menu.active = True
                    return "Save"
                
                elif name == "Return to Menu":
                    self.hide()
                    return "Quit"  # Return value stays "Quit" for state handler compatibility
        
        return None
    
    def handle_mouse_motion(self, x: int, y: int):
        """Handle mouse motion"""
        if not self.active:
            return
        
        button_names = ["Continue", "Settings", "Save", "Return to Menu"]
        button_x = self.window_width // 2 - self.button_width // 2
        
        # Reset all hover states
        for name in button_names:
            self.button_hovered[name] = False
        
        # Check which button is hovered
        for i, name in enumerate(button_names):
            button_y = self.start_y + i * (self.button_height + self.button_spacing)
            
            if (button_x <= x <= button_x + self.button_width and
                button_y <= y <= button_y + self.button_height):
                self.button_hovered[name] = True
                break
    
    def draw(self):
        """Draw pause menu"""
        if not self.active:
            return
        
        # Draw overlay
        self.overlay_rect.draw()
        
        # Draw title
        self.title_label.draw()
        
        # Draw buttons
        button_names = ["Continue", "Settings", "Save", "Return to Menu"]
        for name in button_names:
            # Update button color based on hover state
            bg_color = (100, 100, 100) if self.button_hovered[name] else (70, 70, 70)
            self.button_bg_rects[name].color = bg_color
            
            # Draw button background
            self.button_bg_rects[name].draw()
            
            # Draw button label
            self.button_labels[name].draw()
    
    def set_save_menu(self, save_menu):
        """Set reference to save menu"""
        self.save_menu = save_menu
    
    def set_settings_menu(self, settings_menu):
        """Set reference to settings menu"""
        self.settings_menu = settings_menu
