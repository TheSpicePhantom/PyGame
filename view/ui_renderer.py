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
        if current_state == GameState.PAUSED:
            # Draw semi-transparent overlay
            import pyglet.shapes
            overlay = pyglet.shapes.Rectangle(0, 0, self.ui_controller.width, self.ui_controller.height, color=(0, 0, 0))
            overlay.opacity = 200
            overlay.draw()
            
            # Draw "PAUSED" text
            import pyglet.text
            label = pyglet.text.Label(
                'PAUSED',
                font_name='Arial',
                font_size=72,
                x=self.ui_controller.width // 2,
                y=self.ui_controller.height // 2 + 100,
                anchor_x='center',
                anchor_y='center',
                color=(255, 255, 255, 255)
            )
            label.draw()
            
            # Draw hint text
            hint_label = pyglet.text.Label(
                'Press ESC to continue',
                font_name='Arial',
                font_size=24,
                x=self.ui_controller.width // 2,
                y=self.ui_controller.height // 2 - 100,
                anchor_x='center',
                anchor_y='center',
                color=(200, 200, 200, 255)
            )
            hint_label.draw()


