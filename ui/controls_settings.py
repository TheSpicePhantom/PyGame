"""
UI: Steuerungs-Einstellungen
"""
import pygame
import json
import os
from core import settings


class ControlsSettings:
    """Steuerungs-Einstellungen Menü"""
    
    def __init__(self):
        self.active = False
        self.font = pygame.font.Font(None, 42)
        self.button_font = pygame.font.Font(None, 32)
        self.label_font = pygame.font.Font(None, 28)
        self.small_font = pygame.font.Font(None, 24)
        
        # Lade Einstellungen
        self.config_path = os.path.join('config', 'user_settings.json')
        self.load_settings()
        
        # Standard-Tastenbelegungen
        self.default_keys = {
            'move_up': pygame.K_w,
            'move_down': pygame.K_s,
            'move_left': pygame.K_a,
            'move_right': pygame.K_d,
            'interact': pygame.K_e,
            'inventory': pygame.K_i,
            'pause': pygame.K_ESCAPE,
        }
        
        # Aktuelle Tastenbelegungen
        self.keys = self.default_keys.copy()
        
        # Welche Taste wird gerade neu belegt?
        self.rebinding_key = None
        
        # Buttons
        button_width = 200
        button_height = 50
        self.back_button = pygame.Rect(
            settings.SCREEN_WIDTH // 2 - button_width // 2,
            550,
            button_width,
            button_height
        )
        
        # Key-Button-Rectangles
        self.key_buttons = {}
        self._create_key_buttons()
    
    def _create_key_buttons(self):
        """Erstellt Buttons für jede Taste"""
        button_width = 150
        button_height = 40
        start_y = 150
        spacing = 50
        
        key_labels = {
            'move_up': 'Bewegung Oben',
            'move_down': 'Bewegung Unten',
            'move_left': 'Bewegung Links',
            'move_right': 'Bewegung Rechts',
            'interact': 'Interagieren',
            'inventory': 'Inventar',
            'pause': 'Pause',
        }
        
        y = start_y
        for key_name in key_labels.keys():
            self.key_buttons[key_name] = {
                'rect': pygame.Rect(
                    settings.SCREEN_WIDTH // 2 - button_width // 2,
                    y,
                    button_width,
                    button_height
                ),
                'label': key_labels[key_name]
            }
            y += spacing
    
    def load_settings(self):
        """Lädt Steuerungs-Einstellungen aus JSON"""
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
                controls_data = data.get('controls', {})
                # Konvertiere String-Keys zu pygame.K_* Konstanten
                for key_name, key_value in controls_data.items():
                    if isinstance(key_value, int):
                        self.keys[key_name] = key_value
        except:
            pass  # Verwende Standard-Tasten
    
    def save_settings(self):
        """Speichert Steuerungs-Einstellungen in JSON"""
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
        except:
            data = {}
        
        if 'controls' not in data:
            data['controls'] = {}
        
        data['controls'] = self.keys.copy()
        
        # Stelle sicher, dass der config-Ordner existiert
        os.makedirs('config', exist_ok=True)
        
        with open(self.config_path, 'w') as f:
            json.dump(data, f, indent=4)
    
    def toggle(self):
        """Schaltet das Menü an/aus"""
        self.active = not self.active
        self.rebinding_key = None  # Reset beim Schließen
        return self.active
    
    def handle_event(self, event):
        """Event-Handling für Steuerungs-Einstellungen"""
        if not self.active:
            return None
        
        # Wenn wir gerade eine Taste neu belegen
        if self.rebinding_key:
            if event.type == pygame.KEYDOWN:
                if event.key != pygame.K_ESCAPE:  # ESC zum Abbrechen
                    self.keys[self.rebinding_key] = event.key
                    self.rebinding_key = None
                    self.save_settings()
            return None
        
        # ESC wird in main.py behandelt
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse_pos = event.pos
            
            # Back-Button
            if self.back_button.collidepoint(mouse_pos):
                self.save_settings()
                self.toggle()
                return 'back'
            
            # Key-Buttons
            for key_name, button_data in self.key_buttons.items():
                if button_data['rect'].collidepoint(mouse_pos):
                    self.rebinding_key = key_name
                    break
        
        return None
    
    def _get_key_name(self, key_code):
        """Konvertiert pygame key code zu lesbarem Namen"""
        key_names = {
            pygame.K_w: 'W',
            pygame.K_s: 'S',
            pygame.K_a: 'A',
            pygame.K_d: 'D',
            pygame.K_e: 'E',
            pygame.K_i: 'I',
            pygame.K_ESCAPE: 'ESC',
            pygame.K_SPACE: 'SPACE',
            pygame.K_LSHIFT: 'LSHIFT',
            pygame.K_RSHIFT: 'RSHIFT',
            pygame.K_LCTRL: 'LCTRL',
            pygame.K_RCTRL: 'RCTRL',
        }
        return key_names.get(key_code, pygame.key.name(key_code).upper())
    
    def draw(self, surface):
        """Zeichnet das Steuerungs-Einstellungen Menü"""
        if not self.active:
            return
        
        # Halbtransparentes Overlay
        overlay = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        surface.blit(overlay, (0, 0))
        
        # Titel
        title_text = self.font.render('STEUERUNGS-EINSTELLUNGEN', True, (255, 255, 255))
        title_rect = title_text.get_rect(center=(settings.SCREEN_WIDTH // 2, 60))
        surface.blit(title_text, title_rect)
        
        mouse_pos = pygame.mouse.get_pos()
        
        # Key-Buttons
        for key_name, button_data in self.key_buttons.items():
            rect = button_data['rect']
            label = button_data['label']
            
            # Button-Hintergrund
            if self.rebinding_key == key_name:
                color = (150, 100, 50)  # Orange wenn aktiv
            elif rect.collidepoint(mouse_pos):
                color = (100, 100, 100)  # Hover
            else:
                color = (50, 50, 50)  # Normal
            
            pygame.draw.rect(surface, color, rect)
            pygame.draw.rect(surface, (200, 200, 200), rect, 2)
            
            # Label links vom Button
            label_text = self.label_font.render(label + ':', True, (255, 255, 255))
            label_x = rect.x - label_text.get_width() - 20
            label_y = rect.centery - label_text.get_height() // 2
            surface.blit(label_text, (label_x, label_y))
            
            # Key-Name im Button
            if self.rebinding_key == key_name:
                key_text = self.button_font.render('Drücke Taste...', True, (255, 255, 255))
            else:
                key_name_str = self._get_key_name(self.keys[key_name])
                key_text = self.button_font.render(key_name_str, True, (255, 255, 255))
            
            key_text_rect = key_text.get_rect(center=rect.center)
            surface.blit(key_text, key_text_rect)
        
        # Hinweis
        hint_text = self.small_font.render('Klicke auf eine Taste, um sie neu zu belegen', True, (150, 150, 150))
        hint_rect = hint_text.get_rect(center=(settings.SCREEN_WIDTH // 2, 500))
        surface.blit(hint_text, hint_rect)
        
        # Back-Button
        color = (100, 100, 100) if self.back_button.collidepoint(mouse_pos) else (50, 50, 50)
        pygame.draw.rect(surface, color, self.back_button)
        pygame.draw.rect(surface, (200, 200, 200), self.back_button, 2)
        
        back_text = self.button_font.render('Zurück', True, (255, 255, 255))
        back_text_rect = back_text.get_rect(center=self.back_button.center)
        surface.blit(back_text, back_text_rect)

