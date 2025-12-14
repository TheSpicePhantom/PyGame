"""
Camera: Follows player with smooth lerp and perspective offset
Designed for 60° angled view (Factorio-style)
"""
import pygame
from core import settings


class Camera:
    """Camera that follows a target with smooth interpolation"""
    
    def __init__(self, target=None, lerp_speed=0.1):
        """
        Args:
            target: Entity to follow (usually player)
            lerp_speed: Camera smoothness (0.05-0.2, lower = smoother)
        """
        self.target = target
        self.lerp_speed = lerp_speed
        
        # Camera position in world coordinates
        self.x = 0.0
        self.y = 0.0
        
        # Viewport offset (center camera on player)
        self.offset_x = settings.SCREEN_WIDTH // 2
        self.offset_y = settings.SCREEN_HEIGHT // 2
        
        # No perspective offset for top-down factory shooter
        # Player should be exactly in the center for equal visibility
        self.perspective_offset_y = 0
    
    def update_screen_size(self):
        """Update camera offsets when screen size changes"""
        self.offset_x = settings.SCREEN_WIDTH // 2
        self.offset_y = settings.SCREEN_HEIGHT // 2
        print(f"[Camera] Updated offsets: {self.offset_x}x{self.offset_y}")
    
    def update(self, dt):
        """Smooth camera following with lerp"""
        if self.target is None:
            return
        
        # Target position (center of player)
        target_x = self.target.rect.centerx
        target_y = self.target.rect.centery
        
        # Smooth lerp to target
        self.x += (target_x - self.x) * self.lerp_speed
        self.y += (target_y - self.y) * self.lerp_speed
    
    def apply(self, entity):
        """Apply camera offset to an entity's rect"""
        return pygame.Rect(
            entity.rect.x - self.x + self.offset_x,
            entity.rect.y - self.y + self.offset_y + self.perspective_offset_y,
            entity.rect.width,
            entity.rect.height
        )
    
    def apply_pos(self, pos):
        """Apply camera offset to a position tuple (x, y)"""
        return (
            pos[0] - self.x + self.offset_x,
            pos[1] - self.y + self.offset_y + self.perspective_offset_y
        )
    
    def apply_rect(self, rect):
        """Apply camera offset to a pygame.Rect"""
        return pygame.Rect(
            rect.x - self.x + self.offset_x,
            rect.y - self.y + self.offset_y + self.perspective_offset_y,
            rect.width,
            rect.height
        )
    
    def world_to_screen(self, world_x, world_y):
        """Convert world coordinates to screen coordinates"""
        return (
            world_x - self.x + self.offset_x,
            world_y - self.y + self.offset_y + self.perspective_offset_y
        )
    
    def screen_to_world(self, screen_x, screen_y):
        """Convert screen coordinates to world coordinates"""
        return (
            screen_x + self.x - self.offset_x,
            screen_y + self.y - self.offset_y - self.perspective_offset_y
        )
