"""
Core: LifecycleManager - Verwaltet Lebenszyklus von Welt und App
"""
from typing import Optional
from core.world_controller import WorldController
from core.ui_controller import UIController
from analytics.diagnostics_service import DiagnosticsService


class LifecycleManager:
    """
    Verwaltet den Lebenszyklus von Welt und App.
    
    Stellt sicher, dass Initialisierung und Shutdown in der richtigen Reihenfolge erfolgen:
    - AutoSave wird vor World-Cleanup gestoppt
    - Threads werden ordnungsgemäß beendet
    - Saves werden vor Shutdown durchgeführt
    """
    
    def __init__(self, world_controller: WorldController, ui_controller: UIController,
                 diagnostics: DiagnosticsService):
        """
        Args:
            world_controller: WorldController instance
            ui_controller: UIController instance
            diagnostics: DiagnosticsService instance
        """
        self.world_controller = world_controller
        self.ui_controller = ui_controller
        self.diagnostics = diagnostics
        
        self._world_active = False
    
    def start_new_world(self, world_name: str, seed: Optional[int] = None):
        """
        Starte eine neue Welt
        
        Args:
            world_name: Name der Welt (wird als Ordnername verwendet)
            seed: Optionaler Seed für Weltgenerierung
        """
        if self._world_active:
            self.diagnostics.warning("LifecycleManager", "World already active, shutting down first")
            self.shutdown_world()
        
        self.diagnostics.info("LifecycleManager", f"Starting new world: {world_name} (seed={seed})")
        
        # 1. Initialize world
        self.world_controller.initialize_game(world_name, seed)
        
        # 2. Setup UI (player inventory)
        self._setup_player_inventory()
        
        # 3. Mark world as active
        self._world_active = True
        
        self.diagnostics.info("LifecycleManager", f"World '{world_name}' started successfully")
    
    def load_world(self, world_name: str):
        """
        Lade eine bestehende Welt
        
        Args:
            world_name: Name der Welt (wird als Ordnername verwendet)
        """
        if self._world_active:
            self.diagnostics.warning("LifecycleManager", "World already active, shutting down first")
            self.shutdown_world()
        
        self.diagnostics.info("LifecycleManager", f"Loading world: {world_name}")
        
        # 1. Initialize world (loads existing data)
        self.world_controller.initialize_game(world_name, seed=None)
        
        # 2. Setup UI (player inventory)
        self._setup_player_inventory()
        
        # 3. Mark world as active
        self._world_active = True
        
        self.diagnostics.info("LifecycleManager", f"World '{world_name}' loaded successfully")
    
    def shutdown_world(self, final_save: bool = True):
        """
        Beende die aktuelle Welt (aber App läuft weiter)
        
        Args:
            final_save: Ob ein finaler Save durchgeführt werden soll
        """
        if not self._world_active:
            self.diagnostics.debug("LifecycleManager", "No active world to shutdown")
            return
        
        self.diagnostics.info("LifecycleManager", "Shutting down world...")
        
        # 1. Stop AutoSave first (before any cleanup)
        if self.world_controller.auto_save:
            self.diagnostics.info("LifecycleManager", "Stopping AutoSave system...")
            self.world_controller.auto_save.stop(final_save=final_save)
        
        # 2. Final save if requested
        if final_save:
            self._perform_final_save()
        
        # 3. Cleanup world (chunks, threads, etc.)
        self.world_controller.cleanup()
        
        # 4. Reset world state
        self.world_controller.game_initialized = False
        self._world_active = False
        
        self.diagnostics.info("LifecycleManager", "World shutdown complete")
    
    def shutdown_app(self):
        """
        Beende die gesamte App (inkl. Welt-Shutdown)
        """
        self.diagnostics.info("LifecycleManager", "Shutting down application...")
        
        # 1. Shutdown world first
        if self._world_active:
            self.shutdown_world(final_save=True)
        
        # 2. Cleanup diagnostics (saves logs)
        self.diagnostics.cleanup()
        
        # 3. UI cleanup (if needed)
        self.ui_controller.cleanup()
        
        self.diagnostics.info("LifecycleManager", "Application shutdown complete")
    
    def _setup_player_inventory(self):
        """Setup player inventory in UI controller after game initialization"""
        if not self.world_controller.player:
            return
        
        player_inventory = getattr(self.world_controller.player, 'inventory', {})
        
        # Convert old format to new slot-based format if needed
        if isinstance(player_inventory, dict) and 'slots' not in player_inventory:
            slots = [[None for _ in range(9)] for _ in range(6)]  # Default 6 rows (5 inv + 1 hotbar)
            slot_index = 0
            for item_id, amount in player_inventory.items():
                if slot_index < 54:  # Max 54 slots for default 6 rows
                    row = slot_index // 9
                    col = slot_index % 9
                    slots[row][col] = {'item_id': item_id, 'amount': amount}
                    slot_index += 1
            player_inventory = {'slots': slots}
        
        # Get inventory size from player data
        if self.world_controller.player_data_manager:
            player_data = self.world_controller.player_data_manager.load_player()
            if player_data:
                inventory_size = player_data.get('inventory_size', 45)
                player_inventory['inventory_size'] = inventory_size
        
        self.ui_controller.set_player_inventory(player_inventory)
    
    def _perform_final_save(self):
        """Perform final save before shutdown"""
        try:
            if not self.world_controller.player or not self.world_controller.player_data_manager:
                return
            
            self.diagnostics.info("LifecycleManager", "Performing final save...")
            
            # Get player attributes
            sprint_multiplier = getattr(self.world_controller.player, 'sprint_multiplier', 1.2)
            sneak_multiplier = getattr(self.world_controller.player, 'sneak_multiplier', 0.8)
            
            # Get inventory from inventory menu if available (new slot-based format)
            inventory = {}
            inventory_size = None
            if self.world_controller.game_app and self.world_controller.game_app.ui_controller:
                if self.world_controller.game_app.ui_controller.inventory_menu:
                    inventory_data = self.world_controller.game_app.ui_controller.inventory_menu.get_inventory_data()
                    inventory = inventory_data  # Pass full dict with 'slots' and 'inventory_size'
                    inventory_size = inventory_data.get('inventory_size', 45)
            # Fallback to old player.inventory format if inventory menu not available
            if not inventory or (isinstance(inventory, dict) and 'slots' not in inventory):
                old_inventory = getattr(self.world_controller.player, 'inventory', {})
                if old_inventory:
                    inventory = old_inventory
            
            # Save player data
            self.world_controller.player_data_manager.save_player(
                position=(self.world_controller.player.rect.x, self.world_controller.player.rect.y),
                inventory=inventory,
                faction_data=getattr(self.world_controller.player, 'faction', {'policies': [], 'allies': [], 'enemies': []}),
                inventory_size=inventory_size,
                sprint_multiplier=sprint_multiplier,
                sneak_multiplier=sneak_multiplier
            )
            
            self.diagnostics.info("LifecycleManager", "Final save completed")
        except Exception as e:
            self.diagnostics.error("LifecycleManager", f"Failed to perform final save: {e}")
    
    def is_world_active(self) -> bool:
        """Check if a world is currently active"""
        return self._world_active


