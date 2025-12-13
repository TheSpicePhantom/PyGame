"""
UI: Bau-Menü
"""
import pygame
from typing import List, Dict, Optional, Callable
from factory.buildings import Building


class BuildMenuItem:
    """Ein Item im Bau-Menü"""
    
    def __init__(self, item_id: str, name: str, building_class: type, 
                 cost: Dict[str, int], icon: Optional[pygame.Surface] = None):
        self.item_id = item_id
        self.name = name
        self.building_class = building_class
        self.cost = cost
        self.icon = icon


class BuildMenu:
    """Bau-Menü für Gebäude"""
    
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.visible = False
        self.items: List[BuildMenuItem] = []
        self.selected_item: Optional[BuildMenuItem] = None
        self.font = pygame.font.Font(None, 20)
        self.menu_width = 200
        self.menu_height = 400
        self.menu_x = 10
        self.menu_y = 150
        self.item_height = 40
        self.on_build_callback: Optional[Callable] = None
    
    def add_item(self, item: BuildMenuItem):
        """Fügt ein Item zum Menü hinzu"""
        self.items.append(item)
    
    def toggle(self):
        """Schaltet die Sichtbarkeit um"""
        self.visible = not self.visible
    
    def show(self):
        """Zeigt das Menü"""
        self.visible = True
    
    def hide(self):
        """Versteckt das Menü"""
        self.visible = False
    
    def handle_click(self, pos: tuple[int, int]) -> bool:
        """Behandelt einen Klick auf das Menü"""
        if not self.visible:
            return False
        
        x, y = pos
        
        # Prüfe ob Klick im Menü-Bereich
        if not (self.menu_x <= x <= self.menu_x + self.menu_width and
                self.menu_y <= y <= self.menu_y + self.menu_height):
            return False
        
        # Prüfe welches Item geklickt wurde
        item_index = (y - self.menu_y) // self.item_height
        if 0 <= item_index < len(self.items):
            self.selected_item = self.items[item_index]
            return True
        
        return False
    
    def render(self):
        """Rendert das Bau-Menü"""
        if not self.visible:
            return
        
        # Hintergrund
        pygame.draw.rect(self.screen, (50, 50, 50), 
                        (self.menu_x, self.menu_y, self.menu_width, self.menu_height))
        pygame.draw.rect(self.screen, (255, 255, 255), 
                        (self.menu_x, self.menu_y, self.menu_width, self.menu_height), 2)
        
        # Titel
        title = self.font.render("Build Menu", True, (255, 255, 255))
        self.screen.blit(title, (self.menu_x + 10, self.menu_y + 5))
        
        # Items
        for i, item in enumerate(self.items):
            y = self.menu_y + 30 + i * self.item_height
            
            # Highlight wenn ausgewählt
            if item == self.selected_item:
                pygame.draw.rect(self.screen, (100, 100, 100), 
                               (self.menu_x, y, self.menu_width, self.item_height))
            
            # Item-Name
            name_text = self.font.render(item.name, True, (255, 255, 255))
            self.screen.blit(name_text, (self.menu_x + 10, y + 5))
            
            # Kosten
            cost_text = ", ".join([f"{k}: {v}" for k, v in item.cost.items()])
            cost_surface = pygame.font.Font(None, 16).render(cost_text, True, (200, 200, 200))
            self.screen.blit(cost_surface, (self.menu_x + 10, y + 22))
    
    def can_build(self, item: BuildMenuItem, resources: Dict[str, int]) -> bool:
        """Prüft, ob ein Item gebaut werden kann"""
        for resource, amount in item.cost.items():
            if resources.get(resource, 0) < amount:
                return False
        return True
    
    def build(self, x: int, y: int) -> Optional[Building]:
        """Baut das ausgewählte Gebäude"""
        if not self.selected_item:
            return None
        
        if self.on_build_callback:
            return self.on_build_callback(self.selected_item, x, y)
        
        return None

