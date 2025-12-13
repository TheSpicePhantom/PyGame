"""
Factory: Rezept-System für Produktion
"""
from typing import Dict


class Recipe:
    """Repräsentiert ein Produktionsrezept"""
    
    def __init__(self, recipe_id: str, name: str, 
                 inputs: Dict[str, int], outputs: Dict[str, int], 
                 production_time: float = 1.0):
        self.recipe_id = recipe_id
        self.name = name
        self.inputs = inputs  # {resource_name: amount}
        self.outputs = outputs  # {resource_name: amount}
        self.production_time = production_time
    
    def get_efficiency(self) -> float:
        """Berechnet die Effizienz des Rezepts (Output/Input)"""
        total_input = sum(self.inputs.values())
        total_output = sum(self.outputs.values())
        
        if total_input == 0:
            return float('inf')
        
        return total_output / total_input


class RecipeManager:
    """Verwaltet alle verfügbaren Rezepte"""
    
    def __init__(self):
        self.recipes: Dict[str, Recipe] = {}
        self.load_default_recipes()
    
    def load_default_recipes(self):
        """Lädt Standard-Rezepte"""
        # Beispiel-Rezepte
        self.add_recipe(Recipe(
            "iron_ore_to_iron",
            "Eisen schmelzen",
            {"iron_ore": 2},
            {"iron": 1},
            2.0
        ))
        
        self.add_recipe(Recipe(
            "iron_to_steel",
            "Stahl herstellen",
            {"iron": 2, "coal": 1},
            {"steel": 1},
            3.0
        ))
    
    def add_recipe(self, recipe: Recipe):
        """Fügt ein Rezept hinzu"""
        self.recipes[recipe.recipe_id] = recipe
    
    def get_recipe(self, recipe_id: str) -> Recipe:
        """Gibt ein Rezept zurück"""
        return self.recipes.get(recipe_id)
    
    def get_all_recipes(self) -> Dict[str, Recipe]:
        """Gibt alle Rezepte zurück"""
        return self.recipes.copy()

