"""
Core: GameApp - State-Machine für Menüs und Ingame-States
"""
from typing import Optional, Dict
from pyglet.window import key
from core.game_state import GameState
from core.lifecycle_manager import LifecycleManager
from core.state_handlers import (
    StateHandler,
    WorldSelectStateHandler,
    CreateWorldStateHandler,
    IngameStateHandler,
    PausedStateHandler,
    InventoryStateHandler,
    SettingsStateHandler
)


class GameApp:
    """State-Machine für Menüs und Ingame-States"""
    
    def __init__(self, world_controller, ui_controller, find_next_available_slot_func, diagnostics=None):
        """
        Args:
            world_controller: WorldController instance
            ui_controller: UIController instance
            find_next_available_slot_func: Function to find next available save slot
            diagnostics: DiagnosticsService instance (optional, for lifecycle logging)
        """
        self.world_controller = world_controller
        self.ui_controller = ui_controller
        self._find_next_available_slot = find_next_available_slot_func
        self.diagnostics = diagnostics
        
        # Initialize lifecycle manager
        self.lifecycle = LifecycleManager(
            world_controller=world_controller,
            ui_controller=ui_controller,
            diagnostics=diagnostics
        )
        
        # Current state
        self.current_state = GameState.WORLD_SELECT
        self.previous_state: Optional[GameState] = None
        
        # State flags
        self.game_initialized = False
        
        # Initialize state handlers
        self.state_handlers: Dict[GameState, StateHandler] = {
            GameState.WORLD_SELECT: WorldSelectStateHandler(self),
            GameState.CREATE_WORLD: CreateWorldStateHandler(self),
            GameState.INGAME: IngameStateHandler(self),
            GameState.PAUSED: PausedStateHandler(self),
            GameState.INVENTORY: InventoryStateHandler(self),
            GameState.SETTINGS: SettingsStateHandler(self),
        }
    
    def get_current_handler(self) -> StateHandler:
        """Get the handler for the current state"""
        return self.state_handlers[self.current_state]
    
    def update(self, dt: float):
        """Update game app based on current state"""
        # Update world controller if in game
        if self.current_state == GameState.INGAME:
            self.world_controller.update(dt)
        
        # Update UI controller (handles menu updates)
        self.ui_controller.update(dt, self.current_state)
    
    def change_state(self, new_state: GameState):
        """Change to a new state"""
        if new_state == self.current_state:
            return
        
        # Handle state exit
        self._exit_state(self.current_state)
        
        # Store previous state
        self.previous_state = self.current_state
        self.current_state = new_state
        
        # Handle state entry
        self._enter_state(new_state)
    
    def _enter_state(self, state: GameState):
        """Handle state entry"""
        if state == GameState.WORLD_SELECT:
            self.ui_controller.show_world_select_menu()
        elif state == GameState.CREATE_WORLD:
            self.ui_controller.show_create_world_menu()
        elif state == GameState.INGAME:
            # Game is already initialized, just ensure UI is hidden
            self.ui_controller.hide_all_menus()
        elif state == GameState.PAUSED:
            self.ui_controller.show_pause_menu()
        elif state == GameState.SETTINGS:
            self.ui_controller.show_settings_menu()
        elif state == GameState.INVENTORY:
            self.ui_controller.toggle_inventory_menu()
    
    def _exit_state(self, state: GameState):
        """Handle state exit"""
        if state == GameState.WORLD_SELECT:
            self.ui_controller.hide_world_select_menu()
        elif state == GameState.CREATE_WORLD:
            self.ui_controller.hide_create_world_menu()
        elif state == GameState.PAUSED:
            self.ui_controller.hide_pause_menu()
        elif state == GameState.SETTINGS:
            self.ui_controller.hide_settings_menu()
    
    def start_new_world(self, world_name: str, seed: Optional[int] = None):
        """
        Starte eine neue Welt
        
        Args:
            world_name: Name der Welt (wird als Ordnername verwendet)
            seed: Optionaler Seed für Weltgenerierung
        """
        self.lifecycle.start_new_world(world_name, seed)
        self.game_initialized = True
        self.change_state(GameState.INGAME)
    
    def load_world(self, world_name: str):
        """
        Lade eine bestehende Welt
        
        Args:
            world_name: Name der Welt (wird als Ordnername verwendet)
        """
        self.lifecycle.load_world(world_name)
        self.game_initialized = True
        self.change_state(GameState.INGAME)
    
    def shutdown_world(self, final_save: bool = True):
        """
        Beende die aktuelle Welt (aber App läuft weiter)
        
        Args:
            final_save: Ob ein finaler Save durchgeführt werden soll
        """
        self.lifecycle.shutdown_world(final_save=final_save)
        self.game_initialized = False
        self.change_state(GameState.WORLD_SELECT)
    
    def shutdown_app(self):
        """
        Beende die gesamte App (inkl. Welt-Shutdown)
        """
        self.lifecycle.shutdown_app()
        self.game_initialized = False
    
    # Legacy method for compatibility
    def initialize_game(self, world_name: Optional[str] = None, seed: Optional[int] = None):
        """Legacy method - use start_new_world() or load_world() instead"""
        if world_name:
            self.start_new_world(world_name, seed)
        else:
            raise ValueError("world_name is required")
    
    def is_menu_active(self) -> bool:
        """Check if any menu is currently active"""
        return self.current_state in [
            GameState.WORLD_SELECT,
            GameState.CREATE_WORLD,
            GameState.PAUSED,
            GameState.SETTINGS,
            GameState.INVENTORY
        ]
    
    def handle_key_press(self, symbol, modifiers):
        """Handle key press events - delegates to current state handler"""
        handler = self.get_current_handler()
        result = handler.handle_key_press(symbol, modifiers)
        
        # Handle special results
        if result == "exit":
            import pyglet
            pyglet.app.exit()
    
    def handle_mouse_press(self, x: int, y: int, button: int, modifiers: int):
        """Handle mouse press events - delegates to current state handler"""
        handler = self.get_current_handler()
        result = handler.handle_mouse_press(x, y, button, modifiers)
        
        # Handle special results
        if result == "exit":
            import pyglet
            pyglet.app.exit()
    
    def handle_mouse_motion(self, x: int, y: int, dx: int, dy: int):
        """Handle mouse motion events - delegates to current state handler"""
        handler = self.get_current_handler()
        handler.handle_mouse_motion(x, y, dx, dy)
    
    def handle_mouse_scroll(self, x: int, y: int, scroll_x: float, scroll_y: float, modifiers: int):
        """Handle mouse scroll events - delegates to current state handler"""
        handler = self.get_current_handler()
        handler.handle_mouse_scroll(x, y, scroll_x, scroll_y, modifiers)
    
    def handle_mouse_release(self, x: int, y: int, button: int, modifiers: int):
        """Handle mouse release events - delegates to current state handler"""
        handler = self.get_current_handler()
        handler.handle_mouse_release(x, y, button, modifiers)
    
    def draw(self):
        """Draw everything based on current state - now handled by renderers in main_pyglet.py"""
        # Rendering is now handled by WorldRenderer, UIRenderer, and DebugRenderer
        # This method is kept for compatibility but does nothing
        pass
    
    def cleanup(self):
        """Cleanup resources"""
        self.world_controller.cleanup()
        self.ui_controller.cleanup()

