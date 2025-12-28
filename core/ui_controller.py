"""
Core: UIController - Verwaltung von Menüs, Overlays und Debug-Anzeigen
"""
from typing import Optional
from pyglet.window import key
from core.game_state import GameState
from ui.pause_menu import PauseMenu
from ui.settings_menu import SettingsMenu
from ui.world_select_menu import WorldSelectMenu
from ui.create_world_menu import CreateWorldMenu
from ui.inventory_menu import InventoryMenu
from ui.hotbar_overlay import HotbarOverlay
from analytics.performance_monitor import PerformanceMonitor


class UIController:
    """Verwaltet alle UI-Elemente: Menüs, Overlays, Debug-Anzeigen"""
    
    def __init__(self, width: int, height: int, modern_gl_renderer, 
                 performance_monitor: PerformanceMonitor):
        """
        Args:
            width: Window width
            height: Window height
            modern_gl_renderer: ModernGLRenderer instance
            performance_monitor: PerformanceMonitor instance
        """
        self.width = width
        self.height = height
        self.modern_gl_renderer = modern_gl_renderer
        self.performance_monitor = performance_monitor
        
        # Menüs
        self.world_select_menu = WorldSelectMenu(width, height, modern_gl_renderer)
        self.create_world_menu = CreateWorldMenu(width, height, modern_gl_renderer)
        # Pass item_texture_manager to inventory menu and hotbar overlay if available
        item_texture_manager = modern_gl_renderer.item_texture_manager if modern_gl_renderer else None
        self.inventory_menu = InventoryMenu(width, height, inventory_size=45, item_texture_manager=item_texture_manager)
        self.hotbar_overlay = HotbarOverlay(width, height, item_texture_manager=item_texture_manager)
        self.hotbar_overlay.set_inventory_menu(self.inventory_menu)
        self.pause_menu = PauseMenu(width, height)  # Initialize pause menu
        self.settings_menu: Optional[SettingsMenu] = None  # Will be initialized when needed
        
        # Debug/Performance
        self.show_performance_stats = False
        self.stats_update_interval = 0.5
        self.last_stats_update = 0.0
        self.debug_visualization_mode = 0
        
        # Show world select menu on startup
        self.world_select_menu.show()
    
    def update(self, dt: float, current_state: GameState):
        """Update UI elements"""
        import time
        
        # Update performance stats display periodically
        current_time = time.time()
        if current_time - self.last_stats_update >= self.stats_update_interval:
            self._update_performance_stats()
            self.last_stats_update = current_time
        
        # Update menus that need per-frame updates (e.g., debounced preview updates)
        if current_state == GameState.CREATE_WORLD:
            self.create_world_menu.update(dt)
    
    def handle_key_press(self, symbol: int, modifiers: int, current_state: GameState):
        """Handle key press events"""
        # State-specific handling is done by GameApp
        # This handles menu-specific keys
        
        if current_state == GameState.CREATE_WORLD:
            result = self.create_world_menu.handle_key_press(symbol, modifiers)
            return result
        elif current_state == GameState.WORLD_SELECT:
            result = self.world_select_menu.handle_key_press(symbol, modifiers)
            return result
        elif current_state == GameState.INVENTORY:
            self.inventory_menu.handle_key_press(symbol, modifiers)
        elif current_state == GameState.PAUSED:
            if self.pause_menu:
                self.pause_menu.handle_key_press(symbol, modifiers)
        
        # Toggle performance stats with F3
        if symbol == key.F3:
            self.show_performance_stats = not self.show_performance_stats
            print(f"[Performance] Stats display: {'ON' if self.show_performance_stats else 'OFF'}")
        
        # Toggle debug visualization with F8
        if symbol == key.F8:
            self.debug_visualization_mode = (self.debug_visualization_mode + 1) % 3
            modes = ["OFF", "Chunk Boundaries", "Chunk Boundaries + Tile Grids"]
            print(f"[Debug] Visualization mode: {modes[self.debug_visualization_mode]}")
    
    def handle_mouse_press(self, x: int, y: int, button: int, modifiers: int, current_state: GameState):
        """Handle mouse press events"""
        if current_state == GameState.CREATE_WORLD:
            result = self.create_world_menu.handle_mouse_press(x, y, button, modifiers)
            return result
        elif current_state == GameState.WORLD_SELECT:
            result = self.world_select_menu.handle_mouse_press(x, y, button, modifiers)
            return result
        elif current_state == GameState.INVENTORY:
            self.inventory_menu.handle_mouse_press(x, y, button, modifiers)
        elif current_state == GameState.PAUSED:
            if self.pause_menu:
                result = self.pause_menu.handle_mouse_press(x, y, button, modifiers)
                return result
    
    def handle_mouse_motion(self, x: int, y: int, dx: int, dy: int, current_state: GameState):
        """Handle mouse motion events"""
        if current_state == GameState.WORLD_SELECT:
            self.world_select_menu.handle_mouse_motion(x, y)
        elif current_state == GameState.INVENTORY:
            self.inventory_menu.handle_mouse_motion(x, y)
        elif current_state == GameState.PAUSED:
            if self.pause_menu:
                self.pause_menu.handle_mouse_motion(x, y)
        elif current_state == GameState.CREATE_WORLD:
            self.create_world_menu.handle_mouse_motion(x, y)
    
    def handle_mouse_scroll(self, x: int, y: int, scroll_x: float, scroll_y: float, 
                           modifiers: int, current_state: GameState):
        """Handle mouse scroll events"""
        # Hotbar selection (when not zooming)
        if current_state == GameState.INGAME:
            if not (key.LCTRL in modifiers or key.RCTRL in modifiers):
                self.hotbar_overlay.handle_mouse_scroll(scroll_y)
    
    def show_world_select_menu(self):
        """Show world select menu"""
        self.world_select_menu.show()
    
    def hide_world_select_menu(self):
        """Hide world select menu"""
        self.world_select_menu.hide()
    
    def show_create_world_menu(self):
        """Show create world menu"""
        self.create_world_menu.show()
        # Generate initial preview with random seed
        self.create_world_menu._update_preview()
    
    def hide_create_world_menu(self):
        """Hide create world menu"""
        self.create_world_menu.hide()
    
    def show_pause_menu(self):
        """Show pause menu"""
        if self.pause_menu:
            self.pause_menu.show()
            # Set menu references if available
            if self.settings_menu:
                self.pause_menu.set_settings_menu(self.settings_menu)
            # Note: save_menu is not yet implemented in UIController
    
    def hide_pause_menu(self):
        """Hide pause menu"""
        if self.pause_menu:
            self.pause_menu.active = False
    
    def show_settings_menu(self):
        """Show settings menu"""
        if not self.settings_menu:
            self.settings_menu = SettingsMenu(self.width, self.height)
        self.settings_menu.show()
    
    def hide_settings_menu(self):
        """Hide settings menu"""
        if self.settings_menu:
            self.settings_menu.hide()
    
    def toggle_inventory_menu(self):
        """Toggle inventory menu"""
        self.inventory_menu.toggle()
    
    def hide_all_menus(self):
        """Hide all menus"""
        self.hide_world_select_menu()
        self.hide_create_world_menu()
        self.hide_pause_menu()
        self.hide_settings_menu()
        # InventoryMenu uses toggle() - only hide if currently active
        if hasattr(self.inventory_menu, 'active') and self.inventory_menu.active:
            self.inventory_menu.toggle()
    
    def set_player_inventory(self, inventory_data: dict):
        """Set player inventory data"""
        self.inventory_menu.set_inventory(inventory_data)
    
    def draw(self, current_state: GameState):
        """Draw UI elements based on current state"""
        # Draw world select menu if active
        if current_state == GameState.WORLD_SELECT:
            import pyglet.shapes
            overlay = pyglet.shapes.Rectangle(0, 0, self.width, self.height, color=(0, 0, 0))
            overlay.opacity = 180
            overlay.draw()
            self.world_select_menu.draw()
            return  # Don't render game when menu is active
        
        # Draw create world menu if active
        if current_state == GameState.CREATE_WORLD:
            self.create_world_menu.draw()
            return  # Don't render game when menu is active
        
        # Draw inventory menu if active (as overlay, game continues in background)
        if current_state == GameState.INVENTORY:
            self.inventory_menu.draw()
        
        # Always draw hotbar overlay (permanent display)
        self.hotbar_overlay.draw()
        
        # Draw pause menu if active
        if current_state == GameState.PAUSED and self.pause_menu:
            self.pause_menu.draw()
        
        # Draw performance stats (toggle with F3)
        if self.show_performance_stats and current_state != GameState.PAUSED:
            self._draw_performance_stats()
    
    def _update_performance_stats(self):
        """Update performance statistics"""
        # Stats are updated by PerformanceMonitor
        # This method can be used for additional UI-specific updates
        pass
    
    def _draw_performance_stats(self):
        """Draw performance statistics overlay"""
        import pyglet.text
        from core import settings
        
        stats = self.performance_monitor.get_stats()
        
        # Create text labels
        lines = [
            f"FPS: {stats.get('fps', 0):.1f}",
            f"CPU: {stats.get('cpu_percent', 0):.1f}%",
            f"GPU: {stats.get('gpu_percent', 0):.1f}%",
        ]
        
        # Add world-specific stats if available
        if hasattr(self, 'world_controller') and self.world_controller and self.world_controller.world:
            world = self.world_controller.world
            if world.chunk_manager:
                visible_chunks = sum(1 for c in world.chunk_manager.loaded_chunks.values() 
                                    if c.render_state in ["visible", "rendering", "active", "rendered"])
                loaded_chunks = len(world.chunk_manager.loaded_chunks)
                lines.append(f"Visible Chunks: {visible_chunks}")
                lines.append(f"Loaded Chunks: {loaded_chunks}")
                
                # Get open regions count
                if hasattr(world.chunk_manager, 'region_manager'):
                    open_regions = len(world.chunk_manager.region_manager.open_regions)
                    lines.append(f"Open Regions: {open_regions}")
        
        # Add camera/zoom info if available
        if hasattr(self, 'world_controller') and self.world_controller:
            if self.world_controller.camera:
                lines.append(f"Camera: ({self.world_controller.camera.x:.0f}, {self.world_controller.camera.y:.0f})")
            if hasattr(self.world_controller, 'camera_zoom'):
                lines.append(f"Zoom: {self.world_controller.camera_zoom:.2f}x")
        
        # Render text labels
        y_offset = self.height - 20
        for i, line in enumerate(lines):
            label = pyglet.text.Label(
                line,
                font_name='Courier New',
                font_size=12,
                x=10,
                y=y_offset - i * 20,
                color=(255, 255, 255, 255)
            )
            label.draw()
    
    def cleanup(self):
        """Cleanup resources"""
        # Menus will be cleaned up automatically
        pass

