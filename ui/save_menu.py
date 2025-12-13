import pygame
from config.settings import SCREEN_WIDTH, SCREEN_HEIGHT

class SaveMenu:
    """Save Menu with save slot buttons"""
    
    def __init__(self):
        self.active = False
        self.font = pygame.font.Font(None, 48)
        self.button_font = pygame.font.Font(None, 36)
        self.slot_font = pygame.font.Font(None, 28)
        
        # Define save slot buttons
        button_width = 400
        button_height = 60
        button_spacing = 20
        start_y = 150
        center_x = SCREEN_WIDTH // 2
        
        self.buttons = {}
        
        # Create 3 save slots
        for i in range(1, 4):
            slot_name = f"Slot {i}"
            self.buttons[slot_name] = pygame.Rect(
                center_x - button_width // 2,
                start_y + (i-1) * (button_height + button_spacing),
                button_width,
                button_height
            )
        
        # Add Back button
        self.buttons["Back"] = pygame.Rect(
            center_x - button_width // 2,
            start_y + 3 * (button_height + button_spacing) + 40,
            button_width,
            button_height
        )
    
    def toggle(self):
        """Toggle Save Menu on/off"""
        self.active = not self.active
        return self.active
    
    def handle_event(self, event):
        """Event handling for Save Menu"""
        if not self.active:
            return None
        
        # ESC key to close Save Menu
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.toggle()
                return "back"
        
        # Button click events
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:  # Left click
            for button_name, button_rect in self.buttons.items():
                if button_rect.collidepoint(event.pos):
                    if button_name == "Back":
                        self.toggle()
                        return "back"
                    else:
                        # Return the slot number for saving
                        return button_name.lower().replace(" ", "_")
        
        return None
    
    def draw(self, surface):
        """Draw Save Menu"""
        if not self.active:
            return
        
        # Semi-transparent overlay
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        surface.blit(overlay, (0, 0))
        
        # Title
        title_text = self.font.render("SAVE GAME", True, (255, 255, 255))
        title_rect = title_text.get_rect(center=(SCREEN_WIDTH // 2, 80))
        surface.blit(title_text, title_rect)
        
        # Buttons
        mouse_pos = pygame.mouse.get_pos()
        for button_name, button_rect in self.buttons.items():
            # Button highlight on hover
            if button_rect.collidepoint(mouse_pos):
                pygame.draw.rect(surface, (100, 100, 100), button_rect)
            else:
                pygame.draw.rect(surface, (50, 50, 50), button_rect)
            
            # Button border
            pygame.draw.rect(surface, (200, 200, 200), button_rect, 2)
            
            # Button text
            text = self.button_font.render(button_name, True, (255, 255, 255))
            text_rect = text.get_rect(center=button_rect.center)
            surface.blit(text, text_rect)
            
            # Add save info for slot buttons (placeholder)
            if button_name.startswith("Slot"):
                info_text = self.slot_font.render("Empty", True, (150, 150, 150))
                info_rect = info_text.get_rect(center=(button_rect.centerx, button_rect.centery + 20))
                surface.blit(info_text, info_rect)
