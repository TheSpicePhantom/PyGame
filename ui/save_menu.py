import pygame
import os
import json
from pathlib import Path
from core import settings
from config.settings_manager import settings_manager

class SaveMenu:
    """Save Menu with save slot buttons and save/load detection"""
    
    def __init__(self, mode="select"):
        self.active = False
        self.mode = mode  # "select" for startup, "save" for in-game saving
        
        # Initialize UI elements
        self._init_ui()
    
    def _init_ui(self):
        """Initialize/reinitialize all UI elements with current scale"""
        # Fonts
        self.font = settings_manager.scale_font_size(40)
        self.button_font = settings_manager.scale_font_size(36)
        self.slot_font = settings_manager.scale_font_size(24)
        
        # Define save slot buttons (scale dimensions, center on unscaled screen)
        button_width = settings_manager.scale_value(400)
        button_height = settings_manager.scale_value(70)
        button_spacing = settings_manager.scale_value(20)
        start_y = settings_manager.scale_value(150)
        
        self.buttons = {}
        
        # Create 3 save slots
        for i in range(1, 4):
            slot_name = f"Slot {i}"
            y_pos = start_y + (i-1) * (button_height + button_spacing)
            self.buttons[slot_name] = pygame.Rect(
                settings.SCREEN_WIDTH // 2 - button_width // 2,
                y_pos,
                button_width,
                button_height
            )
        
        # Add Back button (only show when in save mode from pause menu)
        if self.mode == "save":
            self.buttons["Back"] = pygame.Rect(
                settings.SCREEN_WIDTH // 2 - button_width // 2,
                start_y + 3 * (button_height + button_spacing) + settings_manager.scale_value(40),
                button_width,
                button_height
            )
    
    def _check_save_exists(self, slot_num):
        """Check if a save exists for the given slot number"""
        save_dir = Path(f"saves/slot_{slot_num}")
        metadata_file = save_dir / "world_metadata.json"
        
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    data = json.load(f)
                    return True, data.get('seed', 'Unknown')
            except:
                return False, None
        return False, None
    
    def toggle(self):
        """Toggle Save Menu on/off"""
        self.active = not self.active
        return self.active
    
    def handle_event(self, event):
        """Event handling for Save Menu"""
        if not self.active:
            return None
        
        # ESC key to close Save Menu (only in save mode)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE and self.mode == "save":
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
                        # Return the slot number
                        return button_name.lower().replace(" ", "_")
        
        return None
    
    def draw(self, surface):
        """Draw Save Menu"""
        if not self.active:
            return
        
        # Semi-transparent overlay
        overlay = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        surface.blit(overlay, (0, 0))
        
        # Title
        if self.mode == "select":
            title_text = self.font.render("SELECT SAVE SLOT", True, (255, 255, 255))
        else:
            title_text = self.font.render("SAVE GAME", True, (255, 255, 255))
        title_rect = title_text.get_rect(center=(settings.SCREEN_WIDTH // 2, settings_manager.scale_value(80)))
        surface.blit(title_text, title_rect)
        
        # Buttons
        mouse_pos = pygame.mouse.get_pos()
        for button_name, button_rect in self.buttons.items():
            # Skip Back button rendering check
            if button_name == "Back":
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
                continue
            
            # Check if save exists for this slot
            slot_num = int(button_name.split()[1])
            save_exists, seed = self._check_save_exists(slot_num)
            
            # Button highlight on hover
            if button_rect.collidepoint(mouse_pos):
                if save_exists:
                    pygame.draw.rect(surface, (80, 120, 80), button_rect)  # Green tint for existing
                else:
                    pygame.draw.rect(surface, (100, 100, 100), button_rect)  # Gray for empty
            else:
                if save_exists:
                    pygame.draw.rect(surface, (50, 80, 50), button_rect)  # Dark green
                else:
                    pygame.draw.rect(surface, (50, 50, 50), button_rect)  # Dark gray
            
            # Button border
            if save_exists:
                pygame.draw.rect(surface, (100, 200, 100), button_rect, 2)  # Green border
            else:
                pygame.draw.rect(surface, (200, 200, 200), button_rect, 2)  # White border
            
            # Button text - slot name
            text = self.button_font.render(button_name, True, (255, 255, 255))
            text_rect = text.get_rect(center=(button_rect.centerx, button_rect.top + settings_manager.scale_value(20)))
            surface.blit(text, text_rect)
            
            # Slot info text
            if save_exists:
                if self.mode == "select":
                    info_text = self.slot_font.render(f"Load Game (Seed: {seed})", True, (150, 255, 150))
                else:
                    info_text = self.slot_font.render(f"Overwrite (Seed: {seed})", True, (255, 200, 100))
            else:
                if self.mode == "select":
                    info_text = self.slot_font.render("New Game", True, (150, 150, 150))
                else:
                    info_text = self.slot_font.render("Empty Slot", True, (150, 150, 150))
            
            info_rect = info_text.get_rect(center=(button_rect.centerx, button_rect.bottom - settings_manager.scale_value(20)))
            surface.blit(info_text, info_rect)
