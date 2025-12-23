"""
Auto-Save System: Automatisches Speichern der Welt in regelmäßigen Abständen
"""
import time
from typing import Optional


class AutoSaveSystem:
    """Verwaltet automatisches Speichern der Welt"""
    
    def __init__(self, world, save_slot: int, interval_seconds: float = 300.0):
        """
        Initialisiert das Auto-Save-System
        
        Args:
            world: World-Instanz zum Speichern
            save_slot: Speicher-Slot (1-3)
            interval_seconds: Zeit zwischen Auto-Saves in Sekunden (Standard: 5 Minuten)
        """
        self.world = world
        self.save_slot = save_slot
        self.interval_seconds = interval_seconds
        self.last_save_time = time.time()
        self.enabled = True
        
        print(f"[AutoSave] Initialized for save slot {save_slot}, interval: {interval_seconds}s")
    
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
            print(f"[AutoSave] World saved (slot {self.save_slot})")
        except Exception as e:
            print(f"[AutoSave] Error saving world: {e}")
    
    def enable(self):
        """Aktiviert Auto-Save"""
        self.enabled = True
    
    def disable(self):
        """Deaktiviert Auto-Save"""
        self.enabled = False
