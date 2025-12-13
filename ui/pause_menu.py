""" 
UI: Pause-Menü mit Continue, Settings, Save, Quit Buttons
"""
import pygame
from core import settings
from config.settings_manager import settings_manager

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
            if event.button == 1 and self.rect.collidepoint(event.pos):
                return True
        return False


class PauseMenu:
    """Pause-Menü mit Continue, Settings, Save, Quit"""

    def __init__(self):
        self.active = False
        # Fonts initialisieren (muss nach pygame.init() aufgerufen werden)
        # Vermeide Systemfonts als Fallback, falls Standard-Font nicht verfügbar
        try:
            self.font_title = settings_manager.scale_font_size(72)
            self.font_button = settings_manager.scale_font_size(40)
        except Exception as e:
            print(f"[PauseMenu] Fehler beim Laden des Titels: {e}")

        # Buttons
        button_width = settings_manager.scale_value(400)
        button_height = settings_manager.scale_value(60)
        button_spacing = settings_manager.scale_value(20)
        start_y = settings_manager.scale_value(200)

        self.buttons = {}
        button_names = ["Continue", "Settings", "Save", "Quit"]
        for i, name in enumerate(button_names):
            y_pos = start_y + i * (button_height + button_spacing)
            self.buttons[name] = Button(
                settings.SCREEN_WIDTH // 2 - button_width // 2,
                y_pos,
                button_width,
                button_height,
                name
            )

        # Save menu reference
        self.save_menu = None
        self.settings_menu = None

    def set_settings_menu(self, settings_menu):
        self.settings_menu = settings_menu

    def set_save_menu(self, save_menu):
        self.save_menu = save_menu

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
                return "Continue"

        # Button-Events
        for button_name, button in self.buttons.items():
            if button.handle_event(event):
                if button_name == "Continue":
                    self.toggle()
                return button_name

        return None

    def draw(self, surface):
        """Zeichnet das Pause-Menü"""
        if not self.active:
            return

        # Halbtransparenter Overlay (dunkler Hintergrund)
        overlay = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        surface.blit(overlay, (0, 0))

        # Titel
        try:
            title_text = self.font_title.render("PAUSED", True, (255, 255, 255))
            title_rect = title_text.get_rect(center=(settings.SCREEN_WIDTH // 2, settings_manager.scale_value(100)))
            surface.blit(title_text, title_rect)
        except Exception as e:
            print(f"[PauseMenu] Fehler beim Rendern des Titels: {e}")

        # Buttons
        for button in self.buttons.values():
            try:
                button.draw(surface, self.font_button)
            except Exception as e:
                print(f"[PauseMenu] Fehler beim Rendern eines Buttons: {e}")
