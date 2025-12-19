"""
Core: Input-Handler für Spielersteuerung (pyglet-Version)
"""
from pyglet.window import key
from core import settings

# Key mapping: pygame key codes -> pyglet key codes
KEY_MAP = {
    # Movement keys
    'w': key.W,
    's': key.S,
    'a': key.A,
    'd': key.D,
    # Other keys
    'b': key.B,
    'r': key.R,
    'escape': key.ESCAPE,
    'space': key.SPACE,
    'enter': key.ENTER,
}

# Map pygame key constants to pyglet
def get_pyglet_key(pygame_key):
    """Convert pygame key constant to pyglet key constant"""
    # Simple mapping for common keys
    if hasattr(key, chr(pygame_key).upper()):
        return getattr(key, chr(pygame_key).upper())
    return None


class InputHandler:
    """Verarbeitet Tastatur- und Maus-Eingaben (pyglet)"""
    
    def __init__(self, window):
        """
        Args:
            window: pyglet.window.Window instance (or object with get_keys_pressed method)
        """
        self.window = window
        self.move_dir_x = 0.0
        self.move_dir_y = 0.0
        self.build_mode = False
        self.rotate_pressed = False
    
    def _handle_key_down(self, symbol):
        """Handle key press"""
        KEY_BUILD_MODE = key.B
        KEY_ROTATE = key.R
        
        if symbol == KEY_BUILD_MODE:
            self.build_mode = not self.build_mode
        elif symbol == KEY_ROTATE:
            self.rotate_pressed = True
    
    def _handle_key_up(self, symbol):
        """Handle key release"""
        if symbol == settings.KEY_ROTATE:
            self.rotate_pressed = False
    
    def update(self):
        """Aktualisiert den Bewegungsvektor basierend auf Tasteneingaben"""
        self.move_dir_x = 0.0
        self.move_dir_y = 0.0
        
        # Get pressed keys from window
        keys_pressed = self.window.get_keys_pressed() if hasattr(self.window, 'get_keys_pressed') else set()
        
        # Check pressed keys (using pyglet key constants)
        KEY_MOVE_LEFT = key.A
        KEY_MOVE_RIGHT = key.D
        KEY_MOVE_UP = key.W
        KEY_MOVE_DOWN = key.S
        
        if KEY_MOVE_LEFT in keys_pressed:
            self.move_dir_x = -1.0
        if KEY_MOVE_RIGHT in keys_pressed:
            self.move_dir_x = 1.0
        if KEY_MOVE_UP in keys_pressed:
            self.move_dir_y = -1.0
        if KEY_MOVE_DOWN in keys_pressed:
            self.move_dir_y = 1.0
        
        # Normalisiere Bewegung bei diagonaler Bewegung
        length_squared = self.move_dir_x * self.move_dir_x + self.move_dir_y * self.move_dir_y
        if length_squared > 0:
            length = (length_squared) ** 0.5
            self.move_dir_x /= length
            self.move_dir_y /= length
    
    def _handle_key_down(self, symbol):
        """Handle key press (called from window)"""
        KEY_BUILD_MODE = key.B
        KEY_ROTATE = key.R
        
        if symbol == KEY_BUILD_MODE:
            self.build_mode = not self.build_mode
        elif symbol == KEY_ROTATE:
            self.rotate_pressed = True
    
    def _handle_key_up(self, symbol):
        """Handle key release (called from window)"""
        KEY_ROTATE = key.R
        
        if symbol == KEY_ROTATE:
            self.rotate_pressed = False
    
    @property
    def move_dir(self):
        """Return movement direction as tuple (x, y)"""
        return (self.move_dir_x, self.move_dir_y)

