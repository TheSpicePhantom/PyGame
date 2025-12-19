"""
Combat: Spieler-Klasse mit Bewegung und Inventar
"""
from core import settings
from core.sprite import Sprite


class Player(Sprite):
    """Spieler-Charakter mit Top-Down-Bewegung"""
    
    def __init__(self, pos, input_handler, *groups, performance_monitor=None):
        super().__init__(
            pos=pos,
            size=(settings.TILE_SIZE, settings.TILE_SIZE),
            color=settings.COLOR_PLAYER
        )
        self.input_handler = input_handler
        self.speed = settings.PLAYER_SPEED
        self._layer = settings.LAYER_PLAYER
        self.performance_monitor = performance_monitor
        
        # Add to groups if provided
        if groups:
            self.add(*groups)
        
        # Inventar-System (für später)
        self.inventory = {}
    
    def update(self, dt):
        """Aktualisiert die Spielerposition basierend auf Input"""
        # Get movement direction (can be pygame.Vector2 or tuple)
        move_dir = self.input_handler.move_dir
        
        # Handle both pygame.Vector2 and tuple
        if hasattr(move_dir, 'x'):  # pygame.Vector2
            move_x = move_dir.x * self.speed * dt
            move_y = move_dir.y * self.speed * dt
        else:  # tuple (x, y)
            move_x = move_dir[0] * self.speed * dt
            move_y = move_dir[1] * self.speed * dt
        
        # Record movement for performance metrics
        if self.performance_monitor and (move_x != 0 or move_y != 0):
            # Determine direction
            if abs(move_x) > abs(move_y):
                direction = "right" if move_x > 0 else "left"
            else:
                direction = "down" if move_y > 0 else "up"
            self.performance_monitor.record_movement(direction)
        
        self.rect.x += move_x
        self.rect.y += move_y
    
    def add_item(self, item_id, amount=1):
        """Fügt Items zum Inventar hinzu"""
        if item_id in self.inventory:
            self.inventory[item_id] += amount
        else:
            self.inventory[item_id] = amount
