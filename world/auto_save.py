"""
Auto-Save System: Automatisches Speichern der Welt in regelmäßigen Abständen
"""
import time
from typing import Optional


class AutoSaveSystem:
    """Verwaltet automatisches Speichern der Welt"""
    
    def __init__(self, world, world_name: str, interval_seconds: float = 300.0, diagnostics=None):
        """
        Initialisiert das Auto-Save-System
        
        Args:
            world: World-Instanz zum Speichern
            world_name: Weltname (wird für Logging verwendet)
            interval_seconds: Zeit zwischen Auto-Saves in Sekunden (Standard: 5 Minuten)
            diagnostics: Optional DiagnosticsService instance for logging
        """
        self.world = world
        self.world_name = world_name
        self.interval_seconds = interval_seconds
        self.last_save_time = time.time()
        self.enabled = True
        self.diagnostics = diagnostics  # Store diagnostics service for logging
        
        if self.diagnostics:
            self.diagnostics.info("AutoSave", f"Initialized for world '{world_name}'", interval_seconds=interval_seconds)
    
    def update(self, dt: float):
        """Wird jeden Frame aufgerufen, prüft ob gespeichert werden muss"""
        if not self.enabled or not self.world:
            return
        
        current_time = time.time()
        time_since_last_save = current_time - self.last_save_time
        
        if time_since_last_save >= self.interval_seconds:
            self.save()
    
    def save(self):
        """Speichert die Welt manuell"""
        if not self.world or not self.world.chunk_manager:
            return
        
        try:
            # Speichere alle geladenen Chunks
            self.world.chunk_manager.save_all_chunks()
            
            # Speichere Metadaten
            self.world.chunk_manager.save_metadata()
            
            self.last_save_time = time.time()
            if self.diagnostics:
                self.diagnostics.info("AutoSave", f"World saved (world '{self.world_name}')")
        except Exception as e:
            if self.diagnostics:
                self.diagnostics.error("AutoSave", f"Error saving world: {e}")
    
    def enable(self):
        """Aktiviert Auto-Save"""
        self.enabled = True
    
    def disable(self):
        """Deaktiviert Auto-Save"""
        self.enabled = False
    
    def stop(self, final_save: bool = False):
        """
        Stoppt das Auto-Save-System und führt optional einen finalen Save durch
        
        Args:
            final_save: Wenn True, wird ein finaler Save durchgeführt bevor das System gestoppt wird
        """
        if final_save:
            self.save()
        self.disable()
        if self.diagnostics:
            self.diagnostics.info("AutoSave", f"Stopped (final_save={final_save})")
