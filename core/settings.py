"""
Core: Spiel-Einstellungen und Konfiguration
"""

# Fenster - Default Werte für Windowed Mode
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
FPS = 60

def get_screen_size():
    """Get current screen size"""
    # Return default values (screen size is managed by window system)
    return (SCREEN_WIDTH, SCREEN_HEIGHT)

def get_screen_width():
    """Get current screen width"""
    return SCREEN_WIDTH

def get_screen_height():
    """Get current screen height"""
    return SCREEN_HEIGHT

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

# Controls (key codes - pyglet uses different constants, handled in input_pyglet.py)
# These are kept for reference but not used in pyglet version
KEY_MOVE_UP = ord('W')
KEY_MOVE_DOWN = ord('S')
KEY_MOVE_LEFT = ord('A')
KEY_MOVE_RIGHT = ord('D')
KEY_BUILD_MODE = ord('B')
KEY_ROTATE = ord('R')

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

# Base chunk distances (for 1920x1080)
_BASE_CHUNK_LOAD_DISTANCE = 2
_BASE_CHUNK_UNLOAD_DISTANCE = 4

def get_chunk_load_distance():
    """Calculate chunk load distance based on screen size"""
    screen_width, screen_height = get_screen_size()
    chunk_size_pixels = CHUNK_SIZE * TILE_SIZE
    
    # Calculate how many chunks fit on screen
    chunks_horizontal = (screen_width // chunk_size_pixels) + 1
    chunks_vertical = (screen_height // chunk_size_pixels) + 1
    
    # Load visible area + 1 chunk buffer to prevent black edges
    min_distance = max(chunks_horizontal, chunks_vertical) // 2 + 1  # +1 buffer
    
    # Cap at maximum for performance
    return min(max(_BASE_CHUNK_LOAD_DISTANCE, min_distance), 6)  # Max 6 chunks distance

# Chunk processing time budget (in milliseconds per frame)
CHUNK_UPLOAD_BUDGET_MS = 1.5  # Maximum time allowed for chunk uploads per frame (1-2 ms, HARD LIMIT - strictly enforced)

# Chunk load rate limiting (HARD CAPS to prevent IO spikes)
CHUNK_LOAD_RATE_LIMIT = 35  # Maximum disk loads per second globally (30-40 range) - HARD CAP
CHUNK_LOAD_RATE_WINDOW_MS = 1000  # Time window for measuring load rate (1 second)
CHUNK_LOAD_RATE_SLEEP_MS = 0.025  # Sleep time when rate limit exceeded (25ms - longer sleep for stricter limit)
CHUNK_LOAD_WORKER_RATE_LIMIT = 12  # Maximum chunks per second per worker (with 3 workers: ~36 total, limited by global cap)
CHUNK_LOAD_TOKEN_BUCKET_SIZE = 3  # Token bucket size per worker (smaller bursts)
CHUNK_LOAD_TOKEN_REFILL_RATE = CHUNK_LOAD_WORKER_RATE_LIMIT / 1000.0  # Tokens per millisecond

# Chunk save rate limiting (HARD CAPS to prevent IO spikes)
CHUNK_SAVE_BASE_SLEEP = 0.05  # Base sleep time between saves (50ms = 20 chunks/second)
CHUNK_SAVE_SLOW_THRESHOLD_MS = 20  # Threshold for slow saves (triggers additional throttling)
CHUNK_SAVE_SLOW_SLEEP = 0.15  # Sleep time when slow saves detected (150ms = ~6.7 chunks/second) - INCREASED
CHUNK_SAVE_SLOW_EXTRA_SLEEP = 0.1  # Additional sleep after slow saves >20ms (100ms) - INCREASED
CHUNK_SAVE_VERY_SLOW_THRESHOLD_MS = 50  # Threshold for very slow saves (triggers even more throttling)
CHUNK_SAVE_VERY_SLOW_SLEEP = 0.25  # Sleep time when very slow saves detected (250ms = 4 chunks/second) - INCREASED
CHUNK_SAVE_VERY_SLOW_EXTRA_SLEEP = 0.15  # Additional sleep after very slow saves (150ms) - INCREASED

# Token bucket for save rate limiting (HARD CAP - prevents IO bursts)
CHUNK_SAVE_RATE_LIMIT = 20  # Maximum saves per second globally (15-20 range) - HARD CAP
CHUNK_SAVE_TOKEN_BUCKET_SIZE = 3  # Token bucket size (smaller bursts)
CHUNK_SAVE_TOKEN_REFILL_RATE = CHUNK_SAVE_RATE_LIMIT / 1000.0  # Tokens per millisecond

# Background region compaction settings
REGION_COMPACTION_ENABLED = True  # Enable background compaction of fragmented regions
REGION_COMPACTION_INTERVAL_SEC = 300.0  # Check for regions to compact every 5 minutes
REGION_COMPACTION_MIN_FRAGMENTATION = 1.5  # Only compact if file size is 1.5x larger than minimum (50% waste)
REGION_COMPACTION_MIN_IDLE_SEC = 60.0  # Only compact regions not accessed in last 60 seconds (avoid active regions)
REGION_COMPACTION_MAX_PER_CYCLE = 3  # Maximum regions to compact per cycle (prevent IO spikes)

# Region prefetch settings (proactive loading when moving towards new regions)
REGION_PREFETCH_ENABLED = True  # Enable region prefetching for sequential movement
REGION_PREFETCH_DISTANCE_CHUNKS = 2  # Prefetch regions when camera is within N chunks of region boundary
REGION_PREFETCH_CHUNKS_PER_REGION = 5  # Number of chunks to prefetch per adjacent region (center chunks)
REGION_PREFETCH_PRIORITY_OFFSET = 50  # Priority offset for prefetch requests (lower priority than visible chunks)

# Chunk compression (optional LZ4 support)
# Options: "zlib" (default, always available) or "lz4" (faster decompression, requires lz4 package)
CHUNK_COMPRESSION = "lz4"  # Default to zlib for compatibility
try:
    import lz4.frame
    # LZ4 available - can be enabled by setting CHUNK_COMPRESSION = "lz4"
    LZ4_AVAILABLE = True
except ImportError:
    LZ4_AVAILABLE = False
    # If LZ4 is requested but not available, fall back to zlib
    if CHUNK_COMPRESSION == "lz4":
        CHUNK_COMPRESSION = "zlib"

def get_chunk_unload_distance():
    """Calculate chunk unload distance based on load distance"""
    return get_chunk_load_distance() + 2

# Legacy constants for backward compatibility
CHUNK_LOAD_DISTANCE = _BASE_CHUNK_LOAD_DISTANCE
CHUNK_UNLOAD_DISTANCE = _BASE_CHUNK_UNLOAD_DISTANCE





