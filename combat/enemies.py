"""
Combat: Feinde-System
"""
from world.entities import MovableEntity
from typing import Optional


class Enemy(MovableEntity):
    """Basisklasse für Feinde"""
    
    def __init__(self, x: float, y: float, enemy_type: str, speed: float = 0.05):
        super().__init__(x, y, speed, f"enemy_{enemy_type}")
        self.enemy_type = enemy_type
        self.health = 50
        self.max_health = 50
        self.damage = 10
        self.attack_range = 1.0
        self.attack_cooldown = 0.0
        self.target: Optional[MovableEntity] = None
        self.aggro_range = 5.0
    
    def on_update(self, dt: float):
        """Aktualisiert den Feind"""
        super().on_update(dt)
        
        if self.attack_cooldown > 0:
            self.attack_cooldown -= dt
        
        # KI-Logik
        self.update_ai(dt)
    
    def update_ai(self, dt: float):
        """Aktualisiert die KI des Feindes"""
        # Finde Ziel (z.B. Spieler)
        if not self.target or not self.target.active:
            self.find_target()
        
        if self.target:
            self.move_towards_target(dt)
            self.try_attack()
    
    def find_target(self):
        """Findet ein Ziel zum Angreifen"""
        # Vereinfachte Implementierung
        # In der echten Implementierung würde hier nach dem Spieler gesucht
        pass
    
    def move_towards_target(self, dt: float):
        """Bewegt sich zum Ziel"""
        if not self.target or not self.world:
            return
        
        dx = self.target.x - self.x
        dy = self.target.y - self.y
        distance = (dx ** 2 + dy ** 2) ** 0.5
        
        if distance > self.attack_range:
            # Bewege dich zum Ziel
            if distance > 0:
                dx /= distance
                dy /= distance
                self.move(dx, dy, self.world)
    
    def try_attack(self):
        """Versucht das Ziel anzugreifen"""
        if not self.target or self.attack_cooldown > 0:
            return
        
        distance = ((self.target.x - self.x) ** 2 + (self.target.y - self.y) ** 2) ** 0.5
        
        if distance <= self.attack_range:
            self.attack(self.target)
            self.attack_cooldown = 1.0
    
    def attack(self, target):
        """Greift ein Ziel an"""
        if hasattr(target, 'take_damage'):
            target.take_damage(self.damage)
    
    def take_damage(self, amount: float):
        """Fügt dem Feind Schaden zu"""
        self.health = max(0, self.health - amount)
        if self.health <= 0:
            self.die()
    
    def die(self):
        """Wird aufgerufen, wenn der Feind stirbt"""
        self.destroy()
        # Drop-Loot, Erfahrung, etc.


class BasicEnemy(Enemy):
    """Einfacher Feind"""
    
    def __init__(self, x: float, y: float):
        super().__init__(x, y, "basic", speed=0.05)
        self.health = 30
        self.max_health = 30
        self.damage = 5


class StrongEnemy(Enemy):
    """Starker Feind"""
    
    def __init__(self, x: float, y: float):
        super().__init__(x, y, "strong", speed=0.03)
        self.health = 100
        self.max_health = 100
        self.damage = 20
        self.aggro_range = 8.0

