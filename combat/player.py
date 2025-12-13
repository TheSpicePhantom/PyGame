"""
Combat: Spieler-Logik
"""
from world.entities import MovableEntity
from combat.weapons import Weapon


class Player(MovableEntity):
    """Spieler-Entität"""
    
    def __init__(self, x: float, y: float, speed: float = 0.1):
        super().__init__(x, y, speed, "player")
        self.health = 100
        self.max_health = 100
        self.weapon: Weapon = None
        self.inventory: dict = {}
        self.experience = 0
        self.level = 1
    
    def on_update(self, dt: float):
        """Aktualisiert den Spieler"""
        super().on_update(dt)
        
        if self.weapon:
            self.weapon.update(dt)
    
    def equip_weapon(self, weapon: Weapon):
        """Rüstet eine Waffe aus"""
        self.weapon = weapon
    
    def attack(self, target):
        """Greift ein Ziel an"""
        if self.weapon:
            return self.weapon.attack(target)
        return False
    
    def take_damage(self, amount: float):
        """Fügt dem Spieler Schaden zu"""
        self.health = max(0, self.health - amount)
        if self.health <= 0:
            self.die()
    
    def heal(self, amount: float):
        """Heilt den Spieler"""
        self.health = min(self.max_health, self.health + amount)
    
    def die(self):
        """Wird aufgerufen, wenn der Spieler stirbt"""
        self.active = False
        # Respawn-Logik hier
    
    def gain_experience(self, amount: int):
        """Gibt dem Spieler Erfahrung"""
        self.experience += amount
        while self.experience >= self.get_experience_for_level(self.level + 1):
            self.level_up()
    
    def level_up(self):
        """Erhöht das Level des Spielers"""
        self.level += 1
        self.max_health += 10
        self.health = self.max_health
    
    def get_experience_for_level(self, level: int) -> int:
        """Berechnet die benötigte Erfahrung für ein Level"""
        return level * 100

