"""
Core: Spiel-Einstellungen und Konfiguration
"""
import pygame

# Fenster - Default Werte für Windowed Mode
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
FPS = 60

def get_screen_size():
    """Get current screen size (works even if display mode changed)"""
    try:
        screen = pygame.display.get_surface()
        if screen:
            return screen.get_size()
    except:
        pass
    return (SCREEN_WIDTH, SCREEN_HEIGHT)

def get_screen_width():
    """Get current screen width"""
    return get_screen_size()[0]

def get_screen_height():
    """Get current screen height"""
    return get_screen_size()[1]

# Tiles
TILE_SIZE = 16

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

# Camera / Perspective
CAMERA_LERP_SPEED = 0.15  # 0.05-0.2 (lower = smoother)
PERSPECTIVE_OFFSET_ENABLED = True  # Enable angled view
PERSPECTIVE_TILE_HEIGHT_RATIO = 0.5  # For 60° view simulation

# Chunk System (Minecraft-Style)
CHUNK_SIZE = 15  # Tiles per chunk (15x15)
WORLD_SIZE_CHUNKS = 128  # Max world size in chunks (128x128 chunks)
WORLD_SIZE_TILES = CHUNK_SIZE * WORLD_SIZE_CHUNKS  # 1920x1920 tiles total
CHUNK_LOAD_DISTANCE = 2  # Load chunks within N chunks of player
CHUNK_UNLOAD_DISTANCE = 4  # Unload chunks farther than N chunks from player




