import pygame
from config.settings import SCREEN_WIDTH, SCREEN_HEIGHT
from config.settings_manager import settings_manager


class SaveMenu:
    """Save Menu with save slot buttons"""

    def __init__(self):
        self.active = False
        self.font = pygame.font.Font(None, settings_manager.scale_font_size(40))
        self.button_font = pygame.font.Font(None, settings_manager.scale_font_size(36))
        self.slot_font = pygame.font.Font(None, settings_manager.scale_font_size(28))

        # Define save slot buttons with scaling
        button_width = settings_manager.scale_value(400)
        button_height = settings_manager.scale_value(60)
        button_spacing = settings_manager.scale_value(20)
        start_y = settings_manager.scale_value(150)

        self.buttons = {}

        # Create 3 save slots
        for i in range(1, 4):
            slot_name = f"Slot {i}"
            y_pos = start_y + (i-1) * (button_height + button_spacing)
            self.buttons[slot_name] = pygame.Rect(
                SCREEN_WIDTH // 2 - button_width // 2,
                y_pos,
                button_width,
                button_height
            )

        # Add Back button
        self.buttons["Back"] = pygame.Rect(
            SCREEN_WIDTH // 2 - button_width // 2,
            start_y + 3 * (button_height + button_spacing) + settings_manager.scale_value(40),
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
                return "Back"

        # Button click events
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:  # Left click
            for button_name, button_rect in self.buttons.items():
                if button_rect.collidepoint(event.pos):
                    if button_name == "Back":
                        self.toggle()
                        return "Back"
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
        title_rect = title_text.get_rect(center=(SCREEN_WIDTH // 2, settings_manager.scale_value(80)))
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
                info_rect = info_text.get_rect(center=(button_rect.centerx, button_rect.centery + settings_manager.scale_value(30)))
                surface.blit(info_text, info_rect)
