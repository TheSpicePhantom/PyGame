"""
View: UIRenderer - Rendering von UI-Elementen (Menüs, Hotbar, Overlays)
"""
from core.game_state import GameState
from core.ui_controller import UIController


class UIRenderer:
    """Rendert UI-Elemente: Menüs, Hotbar, Overlays"""
    
    def __init__(self, ui_controller: UIController):
        """
        Args:
            ui_controller: UIController instance
        """
        self.ui_controller = ui_controller
    
    def draw(self, current_state: GameState):
        """Draw UI elements based on current state"""
        # Draw world select menu if active
        if current_state == GameState.WORLD_SELECT:
            import pyglet.shapes
            overlay = pyglet.shapes.Rectangle(0, 0, self.ui_controller.width, self.ui_controller.height, color=(0, 0, 0))
            overlay.opacity = 180
            overlay.draw()
            self.ui_controller.world_select_menu.draw()
            return  # Don't render game when menu is active
        
        # Draw create world menu if active
        if current_state == GameState.CREATE_WORLD:
            self.ui_controller.create_world_menu.draw()
            return  # Don't render game when menu is active
        
        # Draw inventory menu if active (as overlay, game continues in background)
        if current_state == GameState.INVENTORY:
            self.ui_controller.inventory_menu.draw()
        
        # Always draw hotbar overlay (permanent display)
        self.ui_controller.hotbar_overlay.draw()
        
        # Draw pause menu if active
        if current_state == GameState.PAUSED and self.ui_controller.pause_menu:
            self.ui_controller.pause_menu.draw()


