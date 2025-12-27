"""
Core: State Handler - Event-Handler für jeden Game-State
"""
from abc import ABC, abstractmethod
from typing import Optional
from pyglet.window import key
from core.game_state import GameState


class StateHandler(ABC):
    """Basis-Klasse für State-Handler"""
    
    def __init__(self, game_app):
        """
        Args:
            game_app: GameApp instance für State-Transitions
        """
        self.game_app = game_app
    
    @abstractmethod
    def handle_key_press(self, symbol: int, modifiers: int) -> Optional[str]:
        """Handle key press events. Returns action string or None."""
        pass
    
    @abstractmethod
    def handle_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> Optional[str]:
        """Handle mouse press events. Returns action string or None."""
        pass
    
    @abstractmethod
    def handle_mouse_motion(self, x: int, y: int, dx: int, dy: int):
        """Handle mouse motion events."""
        pass
    
    @abstractmethod
    def handle_mouse_scroll(self, x: int, y: int, scroll_x: float, scroll_y: float, modifiers: int):
        """Handle mouse scroll events."""
        pass


class WorldSelectStateHandler(StateHandler):
    """Handler für World Select Menu State"""
    
    def handle_key_press(self, symbol: int, modifiers: int) -> Optional[str]:
        """Handle key press in world select menu"""
        result = self.game_app.ui_controller.world_select_menu.handle_key_press(symbol, modifiers)
        if result == "back":
            if not self.game_app.game_initialized:
                return "exit"
            else:
                self.game_app.change_state(GameState.INGAME)
        return result
    
    def handle_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> Optional[str]:
        """Handle mouse press in world select menu"""
        result = self.game_app.ui_controller.world_select_menu.handle_mouse_press(x, y, button, modifiers)
        if result:
            if result == "create_new":
                self.game_app.change_state(GameState.CREATE_WORLD)
            elif result.startswith("world_"):
                # Extract world name from result (format: "world_<sanitized_name>")
                world_name = result.replace("world_", "", 1)
                self.game_app.load_world(world_name=world_name)
            elif result == "quit":
                # Quit game cleanly
                import pyglet
                pyglet.app.exit()
            elif result == "back":
                if not self.game_app.game_initialized:
                    return "exit"
                else:
                    self.game_app.change_state(GameState.INGAME)
        return result
    
    def handle_mouse_motion(self, x: int, y: int, dx: int, dy: int):
        """Handle mouse motion in world select menu"""
        self.game_app.ui_controller.world_select_menu.handle_mouse_motion(x, y)
    
    def handle_mouse_scroll(self, x: int, y: int, scroll_x: float, scroll_y: float, modifiers: int):
        """Handle mouse scroll in world select menu"""
        pass  # No scroll handling in world select


class CreateWorldStateHandler(StateHandler):
    """Handler für Create World Menu State"""
    
    def handle_key_press(self, symbol: int, modifiers: int) -> Optional[str]:
        """Handle key press in create world menu"""
        result = self.game_app.ui_controller.create_world_menu.handle_key_press(symbol, modifiers)
        if result == "create":
            self._create_world()
        elif result == "cancel":
            self.game_app.change_state(GameState.WORLD_SELECT)
        elif result == "quit":
            # Quit game cleanly
            import pyglet
            pyglet.app.exit()
        return result
    
    def handle_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> Optional[str]:
        """Handle mouse press in create world menu"""
        result = self.game_app.ui_controller.create_world_menu.handle_mouse_press(x, y, button, modifiers)
        if result == "create":
            self._create_world()
        elif result == "cancel":
            self.game_app.change_state(GameState.WORLD_SELECT)
        elif result == "quit":
            # Quit game cleanly
            import pyglet
            pyglet.app.exit()
        return result
    
    def handle_mouse_motion(self, x: int, y: int, dx: int, dy: int):
        """Handle mouse motion in create world menu"""
        pass  # Create world menu handles its own mouse motion
    
    def handle_mouse_scroll(self, x: int, y: int, scroll_x: float, scroll_y: float, modifiers: int):
        """Handle mouse scroll in create world menu"""
        pass  # No scroll handling in create world menu
    
    def _create_world(self):
        """Create world with entered name and seed"""
        from world.world_utils import ensure_unique_world_name
        
        world_name = self.game_app.ui_controller.create_world_menu.get_world_name()
        # Stelle sicher, dass der Weltname eindeutig ist (fügt "_" hinzu falls nötig)
        unique_world_name = ensure_unique_world_name(world_name)
        seed = self.game_app.ui_controller.create_world_menu.get_seed()
        self.game_app.start_new_world(world_name=unique_world_name, seed=seed)
    
    def _setup_player_inventory(self):
        """Setup player inventory in UI controller after game initialization"""
        if self.game_app.world_controller.player:
            player_inventory = getattr(self.game_app.world_controller.player, 'inventory', {})
            if isinstance(player_inventory, dict) and 'slots' not in player_inventory:
                slots = [[None for _ in range(9)] for _ in range(6)]
                slot_index = 0
                for item_id, amount in player_inventory.items():
                    if slot_index < 54:
                        row = slot_index // 9
                        col = slot_index % 9
                        slots[row][col] = {'item_id': item_id, 'amount': amount}
                        slot_index += 1
                player_inventory = {'slots': slots}
            
            if self.game_app.world_controller.player_data_manager:
                player_data = self.game_app.world_controller.player_data_manager.load_player()
                if player_data:
                    inventory_size = player_data.get('inventory_size', 45)
                    player_inventory['inventory_size'] = inventory_size
            
            self.game_app.ui_controller.set_player_inventory(player_inventory)


class IngameStateHandler(StateHandler):
    """Handler für Ingame State"""
    
    def handle_key_press(self, symbol: int, modifiers: int) -> Optional[str]:
        """Handle key press in ingame"""
        if symbol == key.ESCAPE:
            self.game_app.change_state(GameState.PAUSED)
            return None
        elif symbol == key.E:
            self.game_app.change_state(GameState.INVENTORY)
            return None
        
        # Global keys (F3, F5, F8)
        if symbol == key.F3:
            self.game_app.ui_controller.show_performance_stats = not self.game_app.ui_controller.show_performance_stats
            print(f"[Performance] Stats display: {'ON' if self.game_app.ui_controller.show_performance_stats else 'OFF'}")
        elif symbol == key.F5:
            # Hot-reload decoration registry (dev mode)
            try:
                from world.decoration_registry import DecorationRegistry
                DecorationRegistry.reload()
                print("[DecorationRegistry] Reloaded all decoration data (F5)")
            except Exception as e:
                print(f"[DecorationRegistry] Failed to reload: {e}")
        elif symbol == key.F8:
            self.game_app.ui_controller.debug_visualization_mode = (self.game_app.ui_controller.debug_visualization_mode + 1) % 3
            modes = ["OFF", "Chunk Boundaries", "Chunk Boundaries + Tile Grids"]
            print(f"[Debug] Visualization mode: {modes[self.game_app.ui_controller.debug_visualization_mode]}")
        
        return None
    
    def handle_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> Optional[str]:
        """Handle mouse press in ingame"""
        # Handle tile interaction
        self.game_app.world_controller.handle_mouse_press(x, y, button, modifiers)
        return None
    
    def handle_mouse_motion(self, x: int, y: int, dx: int, dy: int):
        """Handle mouse motion in ingame"""
        self.game_app.world_controller.handle_mouse_motion(x, y, dx, dy)
    
    def handle_mouse_scroll(self, x: int, y: int, scroll_x: float, scroll_y: float, modifiers: int):
        """Handle mouse scroll in ingame"""
        # Delegate to UI controller for hotbar, then to world controller for zoom
        self.game_app.ui_controller.handle_mouse_scroll(x, y, scroll_x, scroll_y, modifiers, GameState.INGAME)
        self.game_app.world_controller.handle_mouse_scroll(x, y, scroll_x, scroll_y, modifiers)


class PausedStateHandler(StateHandler):
    """Handler für Paused State"""
    
    def handle_key_press(self, symbol: int, modifiers: int) -> Optional[str]:
        """Handle key press in paused state"""
        if self.game_app.ui_controller.pause_menu:
            result = self.game_app.ui_controller.pause_menu.handle_key_press(symbol, modifiers)
            if result == "Continue":
                self.game_app.change_state(GameState.INGAME)
            elif result == "Quit":
                # Handle quit - could return to main menu or exit game
                self.game_app.change_state(GameState.WORLD_SELECT)
            elif result == "Settings":
                self.game_app.change_state(GameState.SETTINGS)
            elif result == "Save":
                # Handle save - could show save menu
                pass
            return result
        
        return None
    
    def handle_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> Optional[str]:
        """Handle mouse press in paused state"""
        if self.game_app.ui_controller.pause_menu:
            result = self.game_app.ui_controller.pause_menu.handle_mouse_press(x, y, button, modifiers)
            if result == "Continue":
                self.game_app.change_state(GameState.INGAME)
            elif result == "Quit":
                # Handle quit - could return to main menu or exit game
                self.game_app.change_state(GameState.WORLD_SELECT)
            elif result == "Settings":
                self.game_app.change_state(GameState.SETTINGS)
            elif result == "Save":
                # Handle save - could show save menu
                pass
            return result
        return None
    
    def handle_mouse_motion(self, x: int, y: int, dx: int, dy: int):
        """Handle mouse motion in paused state"""
        if self.game_app.ui_controller.pause_menu:
            self.game_app.ui_controller.pause_menu.handle_mouse_motion(x, y)
    
    def handle_mouse_scroll(self, x: int, y: int, scroll_x: float, scroll_y: float, modifiers: int):
        """Handle mouse scroll in paused state"""
        pass  # No scroll handling when paused


class InventoryStateHandler(StateHandler):
    """Handler für Inventory State"""
    
    def handle_key_press(self, symbol: int, modifiers: int) -> Optional[str]:
        """Handle key press in inventory"""
        if symbol == key.ESCAPE or symbol == key.E:
            self.game_app.change_state(GameState.INGAME)
            return None
        
        self.game_app.ui_controller.inventory_menu.handle_key_press(symbol, modifiers)
        return None
    
    def handle_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> Optional[str]:
        """Handle mouse press in inventory"""
        self.game_app.ui_controller.inventory_menu.handle_mouse_press(x, y, button, modifiers)
        return None
    
    def handle_mouse_motion(self, x: int, y: int, dx: int, dy: int):
        """Handle mouse motion in inventory"""
        self.game_app.ui_controller.inventory_menu.handle_mouse_motion(x, y)
    
    def handle_mouse_scroll(self, x: int, y: int, scroll_x: float, scroll_y: float, modifiers: int):
        """Handle mouse scroll in inventory"""
        pass  # Inventory handles its own scroll if needed


class SettingsStateHandler(StateHandler):
    """Handler für Settings State"""
    
    def handle_key_press(self, symbol: int, modifiers: int) -> Optional[str]:
        """Handle key press in settings"""
        if symbol == key.ESCAPE:
            self.game_app.change_state(self.game_app.previous_state or GameState.INGAME)
            return None
        
        if self.game_app.ui_controller.settings_menu:
            self.game_app.ui_controller.settings_menu.handle_key_press(symbol, modifiers)
        return None
    
    def handle_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> Optional[str]:
        """Handle mouse press in settings"""
        if self.game_app.ui_controller.settings_menu:
            self.game_app.ui_controller.settings_menu.handle_mouse_press(x, y, button, modifiers)
        return None
    
    def handle_mouse_motion(self, x: int, y: int, dx: int, dy: int):
        """Handle mouse motion in settings"""
        if self.game_app.ui_controller.settings_menu:
            self.game_app.ui_controller.settings_menu.handle_mouse_motion(x, y)
    
    def handle_mouse_scroll(self, x: int, y: int, scroll_x: float, scroll_y: float, modifiers: int):
        """Handle mouse scroll in settings"""
        pass  # Settings handles its own scroll if needed

