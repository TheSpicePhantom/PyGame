"""
Einfache Sprite-Klasse ohne Pygame-Abhängigkeit
"""
from typing import List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class Rect:
    """Einfache Rect-Klasse ohne Pygame"""
    x: float
    y: float
    width: float
    height: float
    
    @property
    def centerx(self) -> float:
        return self.x + self.width / 2.0
    
    @property
    def centery(self) -> float:
        return self.y + self.height / 2.0
    
    @property
    def center(self) -> Tuple[float, float]:
        return (self.centerx, self.centery)
    
    @center.setter
    def center(self, pos: Tuple[float, float]):
        self.x = pos[0] - self.width / 2.0
        self.y = pos[1] - self.height / 2.0
    
    @property
    def topleft(self) -> Tuple[float, float]:
        return (self.x, self.y)
    
    @topleft.setter
    def topleft(self, pos: Tuple[float, float]):
        self.x = pos[0]
        self.y = pos[1]


class Sprite:
    """Einfache Sprite-Klasse ohne Pygame"""
    
    def __init__(self, pos: Tuple[float, float], size: Tuple[int, int] = (32, 32), color: Tuple[int, int, int] = (255, 255, 255)):
        """
        Args:
            pos: Position (x, y) - wird als center interpretiert
            size: Größe (width, height)
            color: RGB-Farbe für Rendering
        """
        self.width, self.height = size
        self.color = color
        self.rect = Rect(0, 0, self.width, self.height)
        self.rect.center = pos
        self._layer = 0
        self.groups: List['SpriteGroup'] = []
    
    def update(self, dt: float):
        """Update-Methode, überschrieben von Unterklassen"""
        pass
    
    def add(self, *groups: 'SpriteGroup'):
        """Fügt Sprite zu Gruppen hinzu"""
        for group in groups:
            if self not in group.sprites:
                group.sprites.append(self)
            if group not in self.groups:
                self.groups.append(group)
    
    def remove(self, *groups: 'SpriteGroup'):
        """Entfernt Sprite aus Gruppen"""
        for group in groups:
            if self in group.sprites:
                group.sprites.remove(self)
            if group in self.groups:
                self.groups.remove(group)
    
    def kill(self):
        """Entfernt Sprite aus allen Gruppen"""
        for group in self.groups[:]:  # Copy list to avoid modification during iteration
            group.remove(self)
        self.groups.clear()


class SpriteGroup:
    """Einfache Sprite-Gruppe ohne Pygame"""
    
    def __init__(self):
        self.sprites: List[Sprite] = []
    
    def add(self, *sprites: Sprite):
        """Fügt Sprites zur Gruppe hinzu"""
        for sprite in sprites:
            if sprite not in self.sprites:
                self.sprites.append(sprite)
            if self not in sprite.groups:
                sprite.groups.append(self)
    
    def remove(self, *sprites: Sprite):
        """Entfernt Sprites aus der Gruppe"""
        for sprite in sprites:
            if sprite in self.sprites:
                self.sprites.remove(sprite)
            if self in sprite.groups:
                sprite.groups.remove(self)
    
    def update(self, dt: float):
        """Aktualisiert alle Sprites in der Gruppe"""
        for sprite in self.sprites[:]:  # Copy to avoid modification during iteration
            sprite.update(dt)
    
    def draw(self, renderer):
        """Zeichnet alle Sprites (muss von Renderer implementiert werden)"""
        pass
    
    def __iter__(self):
        return iter(self.sprites)
    
    def __len__(self):
        return len(self.sprites)
    
    def __contains__(self, sprite: Sprite):
        return sprite in self.sprites


class LayeredUpdates(SpriteGroup):
    """Sprite-Gruppe mit Layer-Unterstützung"""
    
    def __init__(self):
        super().__init__()
        self._sprites_by_layer: dict = {}
    
    def add(self, *sprites, layer: Optional[int] = None):
        """Fügt Sprites zur Gruppe hinzu, optional mit Layer"""
        for sprite in sprites:
            if sprite not in self.sprites:
                self.sprites.append(sprite)
            if self not in sprite.groups:
                sprite.groups.append(self)
            
            # Handle layer
            sprite_layer = layer if layer is not None else getattr(sprite, '_layer', 0)
            sprite._layer = sprite_layer
            
            if sprite_layer not in self._sprites_by_layer:
                self._sprites_by_layer[sprite_layer] = []
            if sprite not in self._sprites_by_layer[sprite_layer]:
                self._sprites_by_layer[sprite_layer].append(sprite)
    
    def get_sprites_by_layer(self) -> List[Tuple[int, List[Sprite]]]:
        """Gibt Sprites nach Layer sortiert zurück"""
        return sorted(self._sprites_by_layer.items())













