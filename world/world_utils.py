"""
World Utilities: Helper functions for world management
"""
import re
from pathlib import Path
from typing import Optional


def sanitize_world_name(world_name: str) -> str:
    """
    Konvertiert einen Weltnamen in einen sicheren Ordnernamen.
    
    Entfernt ungültige Zeichen für Dateisysteme und ersetzt Leerzeichen durch Unterstriche.
    
    Args:
        world_name: Der Weltname aus der Eingabe
        
    Returns:
        Ein sicherer Ordnername für das Dateisystem
    """
    if not world_name or not world_name.strip():
        return "Unnamed World"
    
    # Entferne führende/abschließende Leerzeichen
    world_name = world_name.strip()
    
    # Ersetze ungültige Zeichen durch Unterstriche
    # Windows ungültige Zeichen: < > : " / \ | ? *
    # Zusätzlich entfernen wir auch Steuerzeichen
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    safe_name = re.sub(invalid_chars, '_', world_name)
    
    # Ersetze mehrere aufeinanderfolgende Unterstriche durch einen
    safe_name = re.sub(r'_+', '_', safe_name)
    
    # Entferne führende/abschließende Unterstriche
    safe_name = safe_name.strip('_')
    
    # Stelle sicher, dass der Name nicht leer ist
    if not safe_name:
        return "Unnamed World"
    
    # Begrenze die Länge (Windows hat ein Limit von 260 Zeichen für Pfade)
    # Wir begrenzen auf 100 Zeichen für den Ordnernamen
    if len(safe_name) > 100:
        safe_name = safe_name[:100]
    
    return safe_name


def get_world_save_dir(world_name: str) -> Path:
    """
    Gibt den Save-Ordner-Pfad für einen Weltnamen zurück.
    
    Args:
        world_name: Der Weltname (wird automatisch sanitized)
        
    Returns:
        Path zum Save-Ordner
    """
    safe_name = sanitize_world_name(world_name)
    return Path("saves") / safe_name


def find_world_by_name(world_name: str) -> Optional[Path]:
    """
    Findet einen Welt-Ordner anhand des Weltnamens.
    
    Args:
        world_name: Der Weltname (wird automatisch sanitized)
        
    Returns:
        Path zum Save-Ordner, oder None wenn nicht gefunden
    """
    save_dir = get_world_save_dir(world_name)
    if save_dir.exists() and save_dir.is_dir():
        return save_dir
    return None

