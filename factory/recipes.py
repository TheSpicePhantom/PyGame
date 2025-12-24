"""
Factory: JSON-basiertes Rezept-System mit Namespace-Support
"""
import json
import os
from typing import Dict, Any

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "recipes")

RECIPES: Dict[str, Dict[str, Any]] = {}


def load_recipes():
    """Lädt alle JSON-Rezepte aus data/recipes und merged sie.
    
    Spätere Dateien können bestehende IDs bewusst überschreiben,
    aber Kollisionen werden geloggt.
    """
    global RECIPES
    RECIPES = {}
    
    if not os.path.isdir(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
        print(f"[recipes] Created directory: {DATA_DIR}")
        return
    
    loaded_files = 0
    for filename in sorted(os.listdir(DATA_DIR)):
        if not filename.endswith(".json"):
            continue
        
        path = os.path.join(DATA_DIR, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if not isinstance(data, dict):
                print(f"[recipes] WARN: '{filename}' does not contain a dict")
                continue
            
            for recipe_id, recipe_def in data.items():
                # Kollisionen loggen
                if recipe_id in RECIPES:
                    print(f"[recipes] WARN: recipe '{recipe_id}' redefined in '{filename}'")
                RECIPES[recipe_id] = recipe_def
            
            loaded_files += 1
            print(f"[recipes] Loaded {len(data)} recipes from '{filename}'")
        
        except Exception as e:
            print(f"[recipes] ERROR loading '{filename}': {e}")
    
    print(f"[recipes] Total: {len(RECIPES)} recipes from {loaded_files} files")


def get_recipe(recipe_id: str) -> Dict[str, Any] | None:
    """Gibt ein Rezept zurück oder None wenn nicht gefunden"""
    return RECIPES.get(recipe_id)


def get_all_recipes() -> Dict[str, Dict[str, Any]]:
    """Gibt alle geladenen Rezepte zurück"""
    return RECIPES.copy()














