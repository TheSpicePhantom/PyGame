"""
Factory: Gebäude-Klassen für Produktion
"""
import pygame
from core import settings
from world.entities import Entity
from factory.recipes import get_recipe


class Building(Entity):
    """Basis-Klasse für alle Gebäude"""
    
    def __init__(self, pos, *groups):
        super().__init__(pos, settings.COLOR_BUILDING, *groups)
        self._layer = settings.LAYER_BUILDINGS
        self.inventory = {}


class Miner(Building):
    """Mining-Gebäude: Baut Ressourcen ab"""
    
    def __init__(self, pos, resource_node, *groups):
        super().__init__(pos, *groups)
        self.resource_node = resource_node
        self.resource_type = resource_node.resource_type
        self.progress = 0.0
        self.production_time = settings.MINER_PRODUCTION_TIME
        
        # Visuelle Kennzeichnung
        self.image.fill((140, 140, 200))
    
    def update(self, dt):
        """Produziert Items über Zeit"""
        if self.resource_node and self.resource_node.amount > 0:
            self.progress += dt
            
            if self.progress >= self.production_time:
                self.progress -= self.production_time
                
                # Mine resource
                mined = self.resource_node.mine(1)
                if mined > 0:
                    # Add to internal inventory
                    if self.resource_type in self.inventory:
                        self.inventory[self.resource_type] += mined
                    else:
                        self.inventory[self.resource_type] = mined


class Assembler(Building):
    """Assembler: Craftet Items nach Rezepten"""
    
    def __init__(self, pos, recipe_id, *groups):
        super().__init__(pos, *groups)
        self.recipe_id = recipe_id
        self.recipe = get_recipe(recipe_id)
        self.progress = 0.0
        self.input_inventory = {}
        self.output_inventory = {}
        
        # Visuelle Kennzeichnung
        self.image.fill((100, 160, 100))
    
    def update(self, dt):
        """Verarbeitet Rezept wenn genug Input vorhanden"""
        if not self.recipe:
            return
        
        # Check if we have enough inputs
        can_craft = True
        for input_id, input_amount in self.recipe.get("inputs", {}).items():
            if self.input_inventory.get(input_id, 0) < input_amount:
                can_craft = False
                break
        
        if can_craft:
            self.progress += dt
            
            if self.progress >= self.recipe.get("time", 1.0):
                self.progress -= self.recipe.get("time", 1.0)
                
                # Consume inputs
                for input_id, input_amount in self.recipe.get("inputs", {}).items():
                    self.input_inventory[input_id] -= input_amount
                
                # Produce outputs
                for output_id, output_amount in self.recipe.get("output", {}).items():
                    if output_id in self.output_inventory:
                        self.output_inventory[output_id] += output_amount
                    else:
                        self.output_inventory[output_id] = output_amount
