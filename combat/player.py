"""
Combat: Spieler-Klasse mit Bewegung und Inventar
"""
from core import settings
from core.sprite import Sprite


class Player(Sprite):
    """Spieler-Charakter mit Top-Down-Bewegung"""
    
    def __init__(self, pos, input_handler, *groups, performance_monitor=None, terrain_gen=None):
        super().__init__(
            pos=pos,
            size=(settings.TILE_SIZE, settings.TILE_SIZE),
            color=settings.COLOR_PLAYER
        )
        self.input_handler = input_handler
        self.speed = settings.PLAYER_SPEED
        self._layer = settings.LAYER_PLAYER
        self.performance_monitor = performance_monitor
        self.terrain_gen = terrain_gen  # TerrainGenerator for traversability checks
        
        # Add to groups if provided
        if groups:
            self.add(*groups)
        
        # Inventar-System (für später)
        self.inventory = {}
    
        # Faction-System (für später)
        self.faction = {
            'policies': [],
            'allies': [],
            'enemies': []
        }
    
    def _is_position_traversable(self, x: float, y: float) -> bool:
        """
        Check if a position is traversable
        
        Args:
            x: X coordinate in pixels
            y: Y coordinate in pixels
            
        Returns:
            True if position is traversable, False otherwise
        """
        if not self.terrain_gen:
            return True  # Allow movement if terrain_gen not available
        
        # Convert pixel coordinates to tile coordinates
        # Use center of player for more accurate checking
        tile_x = int(x // settings.TILE_SIZE)
        tile_y = int(y // settings.TILE_SIZE)
        
        try:
            tile = self.terrain_gen.generate_tile(tile_x, tile_y)
            traversable = tile.get('traversable', True)
            return traversable
        except Exception as e:
            # If tile generation fails, allow movement (fallback)
            print(f"[Player] Warning: Could not check traversability at ({x:.1f}, {y:.1f}): {e}")
            return True
    
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
        
        # If no movement input, do nothing
        if move_x == 0 and move_y == 0:
            return
        
        # Check traversability separately for X and Y movement
        # This allows diagonal movement to continue in one direction if the other is blocked
        # Default: allow all movement if terrain_gen not available
        final_move_x = move_x
        final_move_y = move_y
        
        # Only check traversability if terrain_gen is available
        if self.terrain_gen:
            # Get player center positions for checking
            current_center_x = self.rect.x + self.rect.width / 2.0
            current_center_y = self.rect.y + self.rect.height / 2.0
            
            # Reset movement, then check each direction separately
            final_move_x = 0
            final_move_y = 0
            
            if move_x != 0:
                # Check if X movement is allowed (check center of player at new X position, keep Y same)
                new_center_x = current_center_x + move_x
                if self._is_position_traversable(new_center_x, current_center_y):
                    final_move_x = move_x
            
            if move_y != 0:
                # Check if Y movement is allowed (check center of player at new Y position, keep X same)
                new_center_y = current_center_y + move_y
                if self._is_position_traversable(current_center_x, new_center_y):
                    final_move_y = move_y
        
        # Apply movement if any direction is allowed
        if final_move_x != 0 or final_move_y != 0:
            # Record movement for performance metrics
            if self.performance_monitor:
                # Determine direction based on actual movement
                if abs(final_move_x) > abs(final_move_y):
                    direction = "right" if final_move_x > 0 else "left"
                elif final_move_y != 0:
                    direction = "down" if final_move_y > 0 else "up"
                else:
                    direction = "none"
                self.performance_monitor.record_movement(direction)
            
            # Apply allowed movement
            self.rect.x += final_move_x
            self.rect.y += final_move_y
    
    def add_item(self, item_id, amount=1):
        """Fügt Items zum Inventar hinzu"""
        if item_id in self.inventory:
            self.inventory[item_id] += amount
        else:
            self.inventory[item_id] = amount
