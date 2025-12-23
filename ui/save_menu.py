"""
UI: Save Menu für Speicher-Slot-Auswahl
TODO: Vollständige Implementierung mit Pyglet (aktuell nur Placeholder)
"""
from core import settings


class SaveMenu:
    """Save Menu für Speicher-Slot-Auswahl und Speichern"""
    
    def __init__(self):
        """Initialisiert das Save-Menü"""
        self.active = False
        self.mode = "select"  # "select" = Slot-Auswahl, "save" = Speichern
        
        # Speicher-Slots (1-3)
        self.slots = {
            1: {"exists": False, "name": "Slot 1"},
            2: {"exists": False, "name": "Slot 2"},
            3: {"exists": False, "name": "Slot 3"}
        }
        
        # Prüfe welche Slots existieren
        self._check_slots()
        
        print("[SaveMenu] Initialized (placeholder - needs Pyglet implementation)")
    
    def _check_slots(self):
        """Prüft welche Speicher-Slots existieren"""
        from pathlib import Path
        
        for slot_num in [1, 2, 3]:
            save_dir = Path(f"saves/slot_{slot_num}")
            metadata_file = save_dir / "world_metadata.json"
            
            if metadata_file.exists():
                self.slots[slot_num]["exists"] = True
                # TODO: Lade Speicher-Name aus Metadaten
    
    def toggle(self):
        """Schaltet das Menü an/aus"""
        self.active = not self.active
    
    def select_slot(self, slot_num: int):
        """Wählt einen Speicher-Slot aus"""
        if slot_num in [1, 2, 3]:
            self.selected_slot = slot_num
            return True
        return False
    
    def save_to_slot(self, slot_num: int, world, player):
        """Speichert die Welt und Spieler-Daten in einen Slot"""
        if slot_num not in [1, 2, 3]:
            return False
        
        try:
            # Speichere Welt
            if world and world.chunk_manager:
                world.chunk_manager.save_all_chunks()
                world.chunk_manager.save_metadata()
            
            # Speichere Spieler-Daten
            from world.player_data_manager import PlayerDataManager
            player_manager = PlayerDataManager(slot_num)
            
            if player:
                player_manager.save_player(
                    position=(player.rect.centerx, player.rect.centery),
                    inventory={},  # TODO: Implementiere Inventar
                    faction_data={}  # TODO: Implementiere Faction-Daten
                )
            
            print(f"[SaveMenu] Saved to slot {slot_num}")
            return True
        except Exception as e:
            print(f"[SaveMenu] Error saving to slot {slot_num}: {e}")
            return False
    
    def load_from_slot(self, slot_num: int):
        """Lädt einen Speicher-Slot (gibt Slot-Nummer zurück)"""
        if slot_num not in [1, 2, 3]:
            return None
        
        if not self.slots[slot_num]["exists"]:
            print(f"[SaveMenu] Slot {slot_num} does not exist")
            return None
        
        print(f"[SaveMenu] Loading slot {slot_num}")
        return slot_num

