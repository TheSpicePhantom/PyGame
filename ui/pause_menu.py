"""
UI: Pause-Menü mit Continue, Settings, Save, Quit Buttons
"""
import pygame
from core import settings


class Button:
    """Einfacher Button für das Pause-Menü"""

    def __init__(self, x, y, width, height, text, color=(70, 70, 70), hover_color=(100, 100, 100)):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.color = color
        self.hover_color = hover_color
        self.is_hovered = False

    def draw(self, surface, font):
        """Zeichnet den Button"""
        color = self.hover_color if self.is_hovered else self.color
        pygame.draw.rect(surface, color, self.rect)
        pygame.draw.rect(surface, (200, 200, 200), self.rect, 2)  # Border

        # Text zentriert
        text_surf = font.render(self.text, True, (255, 255, 255))
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)

    def handle_event(self, event):
        """Prüft ob Button geklickt wurde"""
        if event.type == pygame.MOUSEMOTION:
            self.is_hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.is_hovered:
                return True
        return False


class PauseMenu:
    """Pause-Menü mit Continue, Settings, Save, Quit"""

    def __init__(self):
        self.active = False
        self.font_title = pygame.font.Font(None, 72)
        self.font_button = pygame.font.Font(None, 48)

        # Buttons erstellen (zentriert)
        button_width = 300
        button_height = 60
        button_spacing = 20
        start_y = 300

        center_x = settings.SCREEN_WIDTH // 2

        self.buttons = {
            "continue": Button(
                center_x - button_width // 2,
                start_y,
                button_width,
                button_height,
                "Continue"
            ),
            "settings": Button(
                center_x - button_width // 2,
                start_y + (button_height + button_spacing),
                button_width,
                button_height,
                "Settings"
            ),
            "save": Button(
                center_x - button_width // 2,
                start_y + 2 * (button_height + button_spacing),
                button_width,
                button_height,
                "Save"
            ),
            "quit": Button(
                center_x - button_width // 2,
                start_y + 3 * (button_height + button_spacing),
                button_width,
                button_height,
                "Quit"
            ),
        }

    def toggle(self):
        """Pause-Menü an/aus"""
        self.active = not self.active

    def handle_event(self, event):
        """Event-Handling für Buttons"""
        if not self.active:
            return None

        # ESC zum Schließen
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.toggle()
                return "continue"

        # Button-Events
        for button_name, button in self.buttons.items():
            if button.handle_event(event):
                if button_name == "continue":
                    self.toggle()
                return button_name

        return None

    def draw(self, surface):
        """Zeichnet das Pause-Menü"""
        if not self.active:
            return

        # Halbtransparenter Overlay
        overlay = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        surface.blit(overlay, (0, 0))

        # Titel
        title_text = self.font_title.render("PAUSED", True, (255, 255, 255))
        title_rect = title_text.get_rect(center=(settings.SCREEN_WIDTH // 2, 150))
        surface.blit(title_text, title_rect)

        # Buttons
        for button in self.buttons.values():
            button.draw(surface, self.font_button)
