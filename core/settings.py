"""
Core: Spiel-Einstellungen und Konfiguration
"""
import pygame

# Fenster
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60

# Tiles
TILE_SIZE = 32

# Farben
COLOR_BG = (10, 10, 12)
COLOR_GRID = (40, 40, 48)
COLOR_PLAYER = (200, 200, 50)
COLOR_RESOURCE = (60, 100, 160)
COLOR_BUILDING = (120, 120, 180)

# Layer-Z-Reihenfolge
LAYER_FLOOR = 0
LAYER_BUILDINGS = 1
LAYER_PLAYER = 2

# Controls
KEY_MOVE_UP = pygame.K_w
KEY_MOVE_DOWN = pygame.K_s
KEY_MOVE_LEFT = pygame.K_a
KEY_MOVE_RIGHT = pygame.K_d
KEY_BUILD_MODE = pygame.K_b
KEY_ROTATE = pygame.K_r

# Gameplay
PLAYER_SPEED = 200  # pixels per second
MINER_PRODUCTION_TIME = 1.0  # seconds per item
