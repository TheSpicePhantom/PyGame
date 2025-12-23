"""
Input Handler für Pyglet
Verarbeitet Tastatur- und Mauseingaben für das Spiel
"""
from pyglet.window import key
import json
import os


class InputHandler:
    """Verarbeitet Spielereingaben für Pyglet"""
    
    def __init__(self, window):
        """
        Args:
            window: Das Pyglet-Fenster (GameWindow)
        """
        self.window = window
        
        # Bewegungsrichtung (-1.0 bis 1.0)
        self.move_dir_x = 0.0
        self.move_dir_y = 0.0
        
        # Gedrückte Tasten (Set von pyglet key symbols)
        self._keys_pressed = set()
        
        # Lade Hotkeys aus Konfiguration
        self._load_hotkeys()
        
        # Aktions-Flags
        self.build_mode = False
        self.rotate = False
        
        # Sprint und Sneak Flags
        self.sprint_pressed = False
        self.sneak_pressed = False
    
    def _load_hotkeys(self):
        """Lädt Hotkeys aus der Konfigurationsdatei"""
        hotkeys_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'hotkeys.json')
        try:
            with open(hotkeys_path, 'r') as f:
                hotkeys = json.load(f)
            
            # Konvertiere String-Tasten zu pyglet key symbols
            self.KEY_MOVE_UP = self._string_to_key(hotkeys.get('KEY_MOVE_UP', 'w'))
            self.KEY_MOVE_DOWN = self._string_to_key(hotkeys.get('KEY_MOVE_DOWN', 's'))
            self.KEY_MOVE_LEFT = self._string_to_key(hotkeys.get('KEY_MOVE_LEFT', 'a'))
            self.KEY_MOVE_RIGHT = self._string_to_key(hotkeys.get('KEY_MOVE_RIGHT', 'd'))
            self.KEY_BUILD_MODE = self._string_to_key(hotkeys.get('KEY_BUILD_MODE', 'b'))
            self.KEY_ROTATE = self._string_to_key(hotkeys.get('KEY_ROTATE', 'r'))
            self.KEY_SPRINT = self._string_to_key(hotkeys.get('KEY_SPRINT', 'shift'))
            self.KEY_SNEAK = self._string_to_key(hotkeys.get('KEY_SNEAK', 'ctrl'))
        except Exception as e:
            print(f"[Input] Fehler beim Laden der Hotkeys: {e}, verwende Standard-Tasten")
            # Fallback zu Standard-Tasten
            self.KEY_MOVE_UP = key.W
            self.KEY_MOVE_DOWN = key.S
            self.KEY_MOVE_LEFT = key.A
            self.KEY_MOVE_RIGHT = key.D
            self.KEY_BUILD_MODE = key.B
            self.KEY_ROTATE = key.R
            self.KEY_SPRINT = key.LSHIFT
            self.KEY_SNEAK = key.LCTRL
    
    def _string_to_key(self, key_string):
        """Konvertiert einen String zu einem pyglet key symbol"""
        key_map = {
            'w': key.W, 'a': key.A, 's': key.S, 'd': key.D,
            'b': key.B, 'r': key.R,
            'q': key.Q, 'e': key.E,
            'space': key.SPACE,
            'shift': key.LSHIFT, 'ctrl': key.LCTRL, 'alt': key.LALT,
            'up': key.UP, 'down': key.DOWN, 'left': key.LEFT, 'right': key.RIGHT,
        }
        return key_map.get(key_string.lower(), key.W)  # Fallback zu W
    
    def _handle_key_down(self, symbol):
        """Wird aufgerufen, wenn eine Taste gedrückt wird"""
        self._keys_pressed.add(symbol)
        self._update_movement()
        
        # Aktions-Tasten
        if symbol == self.KEY_BUILD_MODE:
            self.build_mode = True
        if symbol == self.KEY_ROTATE:
            self.rotate = True
        if symbol == self.KEY_SPRINT:
            self.sprint_pressed = True
        if symbol == self.KEY_SNEAK:
            self.sneak_pressed = True
    
    def _handle_key_up(self, symbol):
        """Wird aufgerufen, wenn eine Taste losgelassen wird"""
        self._keys_pressed.discard(symbol)
        self._update_movement()
        
        # Aktions-Tasten zurücksetzen
        if symbol == self.KEY_BUILD_MODE:
            self.build_mode = False
        if symbol == self.KEY_ROTATE:
            self.rotate = False
        if symbol == self.KEY_SPRINT:
            self.sprint_pressed = False
        if symbol == self.KEY_SNEAK:
            self.sneak_pressed = False
    
    def _update_movement(self):
        """Aktualisiert die Bewegungsrichtung basierend auf gedrückten Tasten"""
        # Reset Bewegung
        self.move_dir_x = 0.0
        self.move_dir_y = 0.0
        
        # Horizontale Bewegung
        if self.KEY_MOVE_LEFT in self._keys_pressed:
            self.move_dir_x -= 1.0
        if self.KEY_MOVE_RIGHT in self._keys_pressed:
            self.move_dir_x += 1.0
        
        # Vertikale Bewegung
        if self.KEY_MOVE_UP in self._keys_pressed:
            self.move_dir_y -= 1.0
        if self.KEY_MOVE_DOWN in self._keys_pressed:
            self.move_dir_y += 1.0
        
        # Normalisiere diagonale Bewegung (damit diagonale Bewegung nicht schneller ist)
        if self.move_dir_x != 0.0 and self.move_dir_y != 0.0:
            length = (self.move_dir_x ** 2 + self.move_dir_y ** 2) ** 0.5
            self.move_dir_x /= length
            self.move_dir_y /= length
    
    def update(self):
        """Wird jeden Frame aufgerufen, um Eingaben zu aktualisieren"""
        # Bewegung wird bereits durch _handle_key_down/_handle_key_up aktualisiert
        # Diese Methode kann für kontinuierliche Eingaben erweitert werden
        pass
    
    def is_key_pressed(self, key_symbol):
        """Prüft, ob eine bestimmte Taste gedrückt ist"""
        return key_symbol in self._keys_pressed
    
    @property
    def move_dir(self):
        """Gibt die Bewegungsrichtung als Tuple (x, y) zurück"""
        return (self.move_dir_x, self.move_dir_y)
