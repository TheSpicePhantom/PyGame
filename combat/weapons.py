"""
Combat: Waffen-System
"""
from typing import Optional
from abc import ABC, abstractmethod


class Weapon:
    """Basisklasse für Waffen"""
    
    def __init__(self, weapon_id: str, name: str, damage: float, range: float = 1.0):
        self.weapon_id = weapon_id
        self.name = name
        self.damage = damage
        self.range = range
        self.cooldown = 0.0
        self.max_cooldown = 1.0
    
    def update(self, dt: float):
        """Aktualisiert die Waffe"""
        if self.cooldown > 0:
            self.cooldown -= dt
    
    def can_attack(self) -> bool:
        """Prüft, ob die Waffe angreifen kann"""
        return self.cooldown <= 0
    
    def attack(self, target) -> bool:
        """Greift ein Ziel an"""
        if not self.can_attack():
            return False
        
        if self.is_in_range(target):
            self.deal_damage(target)
            self.cooldown = self.max_cooldown
            return True
        return False
    
    def is_in_range(self, target) -> bool:
        """Prüft, ob das Ziel in Reichweite ist"""
        # Vereinfachte Distanzberechnung
        if hasattr(target, 'x') and hasattr(target, 'y'):
            # Distanz wird vom Besitzer berechnet
            return True
        return False
    
    def deal_damage(self, target):
        """Fügt dem Ziel Schaden zu"""
        if hasattr(target, 'take_damage'):
            target.take_damage(self.damage)


class MeleeWeapon(Weapon):
    """Nahkampf-Waffe"""
    
    def __init__(self, weapon_id: str, name: str, damage: float):
        super().__init__(weapon_id, name, damage, range=1.0)
        self.max_cooldown = 0.5


class RangedWeapon(Weapon):
    """Fernkampf-Waffe"""
    
    def __init__(self, weapon_id: str, name: str, damage: float, range: float = 5.0):
        super().__init__(weapon_id, name, damage, range)
        self.max_cooldown = 1.0
        self.ammo = 10
        self.max_ammo = 10
    
    def attack(self, target) -> bool:
        """Greift ein Ziel an (verbraucht Munition)"""
        if self.ammo <= 0:
            return False
        
        if super().attack(target):
            self.ammo -= 1
            return True
        return False
    
    def reload(self, amount: int = None):
        """Lädt Munition nach"""
        if amount is None:
            amount = self.max_ammo - self.ammo
        self.ammo = min(self.max_ammo, self.ammo + amount)





