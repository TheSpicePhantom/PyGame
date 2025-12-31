"""
World: Chunk Manager - Binary region-based chunk save/load system
"""
import json
import os
import math
import time
from pathlib import Path
from typing import Dict, Tuple, Optional, List, Set
from core import settings
from core.zoom_utils import calculate_visible_world_size
import threading
import queue
import heapq
from world.region_manager import (
    RegionManager,
    ChunkNotFoundError,
    ChunkCorruptedError,
    SeedMismatchError,
    RegionFileError
)
from world.world_utils import sanitize_world_name, get_world_save_dir

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class Chunk:
    """Represents a single 15x15 tile chunk"""

    def __init__(self, chunk_x, chunk_y, tiles):
        self.chunk_x = chunk_x
        self.chunk_y = chunk_y
        self.tiles = tiles  # 15x15 array of tile data
        self.entities = []  # Entities in this chunk
        self.is_loaded = True
        self.surface = None  # Pre-rendered surface cache
        self.surface_dirty = True  # Flag to indicate surface needs re-rendering
        
        # Debug flags for chunk state tracking
        self.render_state = None  # "rendering", "rendered", "visible", "active", "inactive"
        
        # Decoration lookup optimization: (tile_x, tile_y) -> decoration_index
        # This allows fast lookup of decorations at specific tile positions
        self.decoration_lookup = {}  # Dict[Tuple[int, int], None] - None is placeholder, actual decoration is in tile['decoration']
        
        # Build initial decoration lookup from tiles
        self._rebuild_decoration_lookup()

    def get_world_position(self):
        """Get top-left world position in pixels"""
        return (
            self.chunk_x * settings.CHUNK_SIZE * settings.TILE_SIZE,
            self.chunk_y * settings.CHUNK_SIZE * settings.TILE_SIZE
        )

    def get_bounds(self):
        """Get chunk bounds (x, y, width, height) in pixels"""
        world_pos = self.get_world_position()
        size = settings.CHUNK_SIZE * settings.TILE_SIZE
        return (world_pos[0], world_pos[1], size, size)
    
    def render_to_surface(self):
        """
        Pre-render chunk tiles to a surface (called in background thread)
        NOTE: This method is deprecated - chunks are now rendered directly via ModernGL.
        Kept for compatibility but does nothing.
        """
        # No longer needed - chunks are rendered directly via ModernGL
        # Surface caching was for Pygame blitting, but ModernGL renders directly from tile data
        self.surface_dirty = False
        return None
    
    def _rebuild_decoration_lookup(self):
        """Rebuild decoration lookup dictionary from tiles."""
        self.decoration_lookup.clear()
        if not self.tiles:
            return
        
        from world.metadata_utils import get_metadata
        
        for tile_y in range(len(self.tiles)):
            if not self.tiles[tile_y]:
                continue
            for tile_x in range(len(self.tiles[tile_y])):
                tile = self.tiles[tile_y][tile_x]
                if tile:
                    # Check both old format (tile['decoration']) and new format (tile['metadata']['decoration'])
                    decoration = tile.get('decoration') or get_metadata(tile, 'decoration')
                    if decoration:
                        self.decoration_lookup[(tile_x, tile_y)] = None  # Decoration is stored in tile
    
    def get_decoration_at(self, tile_x: int, tile_y: int):
        """
        Fast lookup for decoration at tile position.
        
        Args:
            tile_x: Tile X coordinate within chunk (0-14)
            tile_y: Tile Y coordinate within chunk (0-14)
            
        Returns:
            Decoration dict from tile or None if no decoration
        """
        if (tile_x, tile_y) in self.decoration_lookup:
            if tile_y < len(self.tiles) and tile_x < len(self.tiles[tile_y]):
                tile = self.tiles[tile_y][tile_x]
                if tile:
                    from world.metadata_utils import get_metadata
                    # Check both old format and new format
                    return tile.get('decoration') or get_metadata(tile, 'decoration')
        return None
    
    def set_decoration_at(self, tile_x: int, tile_y: int, decoration_data: dict, world_renderer=None):
        """
        Set decoration at tile position and update lookup.
        
        Args:
            tile_x: Tile X coordinate within chunk (0-14)
            tile_y: Tile Y coordinate within chunk (0-14)
            decoration_data: Decoration data dict or None to remove
            world_renderer: Optional WorldRenderer instance for cache invalidation
        """
        if tile_y >= len(self.tiles) or tile_x >= len(self.tiles[tile_y]):
            return
        
        tile = self.tiles[tile_y][tile_x]
        if not tile:
            return
        
        from world.metadata_utils import set_metadata, remove_metadata, migrate_decoration_to_metadata
        
        if decoration_data:
            # Migrate old format to new format if needed
            if 'decoration' in tile:
                migrate_decoration_to_metadata(tile)
            # Use new metadata format
            set_metadata(tile, 'decoration', decoration_data)
            self.decoration_lookup[(tile_x, tile_y)] = None
        else:
            # Remove from both old and new format
            if 'decoration' in tile:
                del tile['decoration']
            remove_metadata(tile, 'decoration')
            self.decoration_lookup.pop((tile_x, tile_y), None)
        
        # Invalidate decoration cache in WorldRenderer if available
        if world_renderer:
            world_renderer.invalidate_decoration_cache(self.chunk_x, self.chunk_y)


class ChunkManager:
    """Manages chunk loading/unloading and save/load to JSON"""

    def __init__(self, world_name: str, terrain_gen, performance_monitor=None, diagnostics=None):
        """
        Initialize ChunkManager for a specific world
        
        Args:
            world_name: World name (will be sanitized for use as directory name)
            terrain_gen: TerrainGenerator instance for new chunk generation
            performance_monitor: Optional PerformanceMonitor instance for metrics
            diagnostics: Optional DiagnosticsService instance for logging
        """
        self.world_name = world_name
        self.sanitized_name = sanitize_world_name(world_name)
        self.terrain_gen = terrain_gen
        self.performance_monitor = performance_monitor
        self.diagnostics = diagnostics  # Store diagnostics service for logging
        self.loaded_chunks: Dict[Tuple[int, int], Chunk] = {}
        self.player_chunk_pos = None  # Changed from (0, 0) to None to force initial load
        self.chunk_load_times: Dict[Tuple[int, int], float] = {}  # Track when chunks were loaded (for cooldown)
        self.chunk_unload_cooldown: float = 9.0  # Seconds before chunk can be unloaded after leaving visible area (9s for smooth preload/cooldown ring, reduces disk loads)
        
        # Region prefetch tracking
        self._last_camera_region: Optional[Tuple[int, int]] = None  # Last region camera was in (region_x, region_y)
        self._prefetched_regions: set = set()  # Set of regions that have been prefetched
        
        # Setup save directories using world name
        self.save_dir = get_world_save_dir(world_name)
        self.chunks_dir = self.save_dir / "chunks"  # Keep for backward compatibility check
        self.chunks_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize RegionManager for binary region-based storage
        self.region_manager = RegionManager(world_name, diagnostics=diagnostics, performance_monitor=performance_monitor)
        
        # Renderer reference (optional, set via set_renderer() method)
        # Used to mark chunks as dirty when tiles are modified
        self.renderer = None
        
        # WorldController reference (optional, set by WorldController)
        # Used for cache invalidation in SeasonManager
        self.world_controller = None
        
        # Load or create world metadata
        self.metadata_file = self.save_dir / "world_metadata.json"
        self.metadata = self._load_metadata()
        
        # Setup chunk loading queue and worker threads
        # Priority Queue: Lower priority number = higher priority (loads chunks closer to player first)
        # Uses heapq internally for efficient priority-based ordering
        self.chunk_load_queue = queue.PriorityQueue()
        self.chunk_load_results = queue.Queue()
        self.worker_threads = []
        self.running = True
        self.pending_chunks = set()  # Track chunks being loaded
        self.chunk_priority = {}  # Distance-based priority (for tracking/cleanup)
        
        # Global load rate limiting (thread-safe)
        self._load_rate_lock = threading.Lock()
        self._load_timestamps = []  # Timestamps of recent chunk loads (for rate calculation)
        self._worker_token_buckets = {}  # Token bucket per worker thread (thread_id -> (tokens, last_refill_time))
        self._worker_token_lock = threading.Lock()  # Lock for token buckets
        
        # Performance limits (documented for tuning):
        # - Max chunks loaded per second: ~60 chunks/sec (3 workers, ~25 chunks/sec per worker)
        # - Max chunks saved per second: 20 chunks/sec (1 worker, 50ms delay between saves)
        # - Max chunks processed per frame: 2 chunks per frame (via process_loaded_chunks)
        #   - Conservative limit to prevent frame spikes and maintain smooth FPS
        #   - Keeps FPS stable while continuously loading chunks in visible area + buffer
        # These limits prevent frame drops and I/O overload
        
        # Async save system - Queue-based for better performance
        self.pending_saves = set()  # Track chunks being saved (thread-safe)
        self.save_queue = queue.Queue()  # Queue for chunks to save
        self.dirty_chunks = set()  # Chunks that need saving (marked as dirty, thread-safe)
        self._save_lock = threading.Lock()  # Lock for pending_saves and dirty_chunks
        
        # Adaptive save throttling (dynamic sleep based on save times)
        self._current_save_sleep = settings.CHUNK_SAVE_BASE_SLEEP  # Current sleep time (adapts to save performance)
        
        # Token bucket for save rate limiting (prevents IO bursts)
        self._save_token_bucket = settings.CHUNK_SAVE_TOKEN_BUCKET_SIZE  # Current tokens available
        self._save_token_last_refill = time.perf_counter()  # Last time tokens were refilled
        self._save_token_lock = threading.Lock()  # Lock for token bucket access
        
        # Start dedicated save worker thread (runs continuously, saves when queue has items)
        self.save_worker_thread = threading.Thread(target=self._chunk_save_worker, daemon=True, name="ChunkSaveWorker")
        self.save_worker_thread.start()
        
        # Start 3 worker threads for chunk loading (balanced: good parallelization without overload)
        for i in range(3):
            thread = threading.Thread(target=self._chunk_loader_worker, daemon=True)
            thread.start()
            self.worker_threads.append(thread)

    def _load_metadata(self) -> dict:
        """Load world metadata (seed, player position, etc.)"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    # Migrate old format to new format if needed
                    if "version" not in metadata or metadata.get("version") == "1.0":
                        metadata = self._migrate_metadata(metadata)
                    return metadata
            except Exception as e:
                if self.diagnostics:
                    self.diagnostics.error("ChunkManager", f"Error loading metadata: {e}")
                else:
                    print(f"[ChunkManager] Error loading metadata: {e}")
        
        # Default metadata for new world (new structure)
        from datetime import datetime
        world_id = self.sanitized_name
        return {
            "version": 1,
            "world_id": world_id,
            "name": self.world_name,
            "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "last_played_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "seed": {
                "world_seed": None,
                "generator_version": "terrain_v1",
                "params": {
                    "biome_config": "biomes_v1",
                    "noise_profile": "default"
                }
            },
            "multiplayer": {
                "enabled": False,
                "max_players": 4,
                "last_host": None,
                "last_host_id": None,
                "permissions": {
                    "public": False,
                    "allow_guests_build": True
                }
            },
            "size": {
                "world_size_mb": 0.0,
                "region_files": 0,
            "chunks_generated": 0,
                "chunks_saved": 0
            },
            "factions": {
                "list": [],
                "alliances": []
            },
            "resources": {
                "summary": {},
                "by_region": []
            },
            "chunks": {
                "claimed": [],
                "loaded_last_session": [],
                "spawn_chunk": None
            },
            "flags": {
                "hardcore": False,
                "mods_used": []
            }
        }
    
    def _migrate_metadata(self, old_metadata: dict) -> dict:
        """Migrate old metadata format to new format"""
        from datetime import datetime
        
        # Extract old values
        old_seed = old_metadata.get("seed")
        old_playtime = old_metadata.get("playtime_seconds", 0)
        old_chunks = old_metadata.get("chunks_generated", 0)
        old_player_pos = old_metadata.get("player_position", [0, 0])
        
        # Calculate spawn chunk from player position
        spawn_chunk = None
        if old_player_pos:
            from core import settings
            chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
            spawn_chunk_x = int(old_player_pos[0] // chunk_size_pixels)
            spawn_chunk_y = int(old_player_pos[1] // chunk_size_pixels)
            spawn_chunk = [spawn_chunk_x, spawn_chunk_y]
        
        # Count region files
        region_files = 0
        regions_dir = self.save_dir / "regions"
        if regions_dir.exists():
            region_files = len(list(regions_dir.glob("*.mcr")))
        
        # Calculate world size (approximate)
        world_size_mb = 0.0
        if regions_dir.exists():
            for region_file in regions_dir.glob("*.mcr"):
                try:
                    world_size_mb += region_file.stat().st_size / (1024 * 1024)
                except:
                    pass
        
        # Create new metadata structure
        world_id = self.sanitized_name
        return {
            "version": 1,
            "world_id": world_id,
            "name": old_metadata.get("world_name", self.world_name),
            "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),  # Approximate
            "last_played_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "seed": {
                "world_seed": old_seed,
                "generator_version": "terrain_v1",
                "params": {
                    "biome_config": "biomes_v1",
                    "noise_profile": "default"
                }
            },
            "multiplayer": {
                "enabled": False,
                "max_players": 4,
                "last_host": None,
                "last_host_id": None,
                "permissions": {
                    "public": False,
                    "allow_guests_build": True
                }
            },
            "size": {
                "world_size_mb": round(world_size_mb, 2),
                "region_files": region_files,
                "chunks_generated": old_chunks,
                "chunks_saved": old_chunks  # Approximate
            },
            "factions": {
                "list": [],
                "alliances": []
            },
            "resources": {
                "summary": {},
                "by_region": []
            },
            "chunks": {
                "claimed": [],
                "loaded_last_session": [],
                "spawn_chunk": spawn_chunk
            },
            "flags": {
                "hardcore": False,
                "mods_used": []
            }
        }

    def save_metadata(self, generate_preview: bool = False):
        """
        Save world metadata to file
        
        Args:
            generate_preview: If True, generate preview image after saving (only for manual saves)
        """
        try:
            # Update last_played_at timestamp
            from datetime import datetime
            self.metadata["last_played_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            
            # Update size information
            regions_dir = self.save_dir / "regions"
            if regions_dir.exists():
                region_files = len(list(regions_dir.glob("*.mcr")))
                world_size_mb = 0.0
                for region_file in regions_dir.glob("*.mcr"):
                    try:
                        world_size_mb += region_file.stat().st_size / (1024 * 1024)
                    except:
                        pass
                
                self.metadata["size"]["region_files"] = region_files
                self.metadata["size"]["world_size_mb"] = round(world_size_mb, 2)
                self.metadata["size"]["chunks_generated"] = len(self.loaded_chunks) + self.metadata["size"].get("chunks_generated", 0)
            
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, indent=2, ensure_ascii=False)
            
            # Generate preview image only if explicitly requested (manual saves)
            if generate_preview:
                if hasattr(self, 'generate_preview_image'):
                    try:
                        self.generate_preview_image()
                    except Exception as e:
                        if self.diagnostics:
                            self.diagnostics.warning("ChunkManager", f"Failed to generate preview image: {e}")
                        else:
                            print(f"[ChunkManager] Failed to generate preview image: {e}")
        except Exception as e:
            if self.diagnostics:
                self.diagnostics.error("ChunkManager", f"Error saving metadata: {e}")
            else:
                print(f"[ChunkManager] Error saving metadata: {e}")

    def set_seed(self, seed: int):
        """Set the world seed"""
        if "seed" in self.metadata and isinstance(self.metadata["seed"], dict):
            self.metadata["seed"]["world_seed"] = seed
        else:
            # Fallback for old format
            self.metadata["seed"] = {
                "world_seed": seed,
                "generator_version": "terrain_v1",
                "params": {
                    "biome_config": "biomes_v1",
                    "noise_profile": "default"
                }
            }
        self.save_metadata()

    def get_seed(self) -> Optional[int]:
        """Get the world seed"""
        seed_data = self.metadata.get("seed")
        if isinstance(seed_data, dict):
            return seed_data.get("world_seed")
        return seed_data  # Old format fallback
    
    def set_renderer(self, renderer):
        """
        Set the renderer instance for dirty flag management.
        
        Args:
            renderer: ModernGLRenderer instance (or None to remove)
        """
        self.renderer = renderer
    
    def modify_tile(self, chunk_x: int, chunk_y: int, local_x: int, local_y: int, new_tile_data: dict):
        """
        Modify a tile in a chunk and mark the chunk as dirty for GPU update.
        
        This method is called when a tile is changed (e.g., build/destroy operations).
        It updates the tile data and informs the renderer that the chunk needs to be re-rendered.
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
            local_x: Local X coordinate within chunk (0-14)
            local_y: Local Y coordinate within chunk (0-14)
            new_tile_data: New tile data dictionary (biome, height, color, traversable, etc.)
        
        Raises:
            KeyError: If chunk is not loaded
            IndexError: If local coordinates are out of bounds
        """
        chunk_key = (chunk_x, chunk_y)
        
        # Check if chunk is loaded
        if chunk_key not in self.loaded_chunks:
            raise KeyError(f"Chunk ({chunk_x}, {chunk_y}) is not loaded")
        
        chunk = self.loaded_chunks[chunk_key]
        
        # Validate local coordinates
        if not (0 <= local_x < settings.CHUNK_SIZE and 0 <= local_y < settings.CHUNK_SIZE):
            raise IndexError(f"Local coordinates ({local_x}, {local_y}) out of bounds (0-{settings.CHUNK_SIZE-1})")
        
        # Update tile data
        chunk.tiles[local_y][local_x] = new_tile_data
        
        # Mark chunk as dirty in renderer (if available)
        if self.renderer is not None:
            self.renderer.mark_chunk_dirty(chunk_x, chunk_y)
        
        # Mark chunk for saving (async save will happen later)
        self._save_chunk_to_file(chunk)
    
    def modify_tile_at_world_pos(self, world_x: float, world_y: float, new_tile_data: dict):
        """
        Modify a tile at world coordinates and mark the chunk as dirty.
        
        Convenience method that converts world coordinates to chunk coordinates
        and calls modify_tile().
        
        Args:
            world_x: World X coordinate (pixels)
            world_y: World Y coordinate (pixels)
            new_tile_data: New tile data dictionary
        
        Raises:
            KeyError: If chunk is not loaded
            IndexError: If coordinates are out of bounds
        """
        # Convert world coordinates to chunk coordinates
        chunk_x = math.floor(world_x / (settings.CHUNK_SIZE * settings.TILE_SIZE))
        chunk_y = math.floor(world_y / (settings.CHUNK_SIZE * settings.TILE_SIZE))
        
        # Calculate local coordinates within chunk
        chunk_world_x = chunk_x * settings.CHUNK_SIZE * settings.TILE_SIZE
        chunk_world_y = chunk_y * settings.CHUNK_SIZE * settings.TILE_SIZE
        local_x = int((world_x - chunk_world_x) // settings.TILE_SIZE)
        local_y = int((world_y - chunk_world_y) // settings.TILE_SIZE)
        
        # Call modify_tile with calculated coordinates
        self.modify_tile(chunk_x, chunk_y, local_x, local_y, new_tile_data)
    
    def get_world_name(self) -> str:
        """Get the world name"""
        return self.metadata.get("name", self.world_name)
    
    def set_world_name(self, name: str):
        """Set the world name"""
        self.metadata["name"] = name
        self.save_metadata()
    
    def update_player_position(self, x: float, y: float):
        """Update player position in metadata (legacy support)"""
        # Update spawn chunk in new format
        from core import settings
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        spawn_chunk_x = int(x // chunk_size_pixels)
        spawn_chunk_y = int(y // chunk_size_pixels)
        
        if "chunks" not in self.metadata:
            self.metadata["chunks"] = {}
        self.metadata["chunks"]["spawn_chunk"] = [spawn_chunk_x, spawn_chunk_y]
        
        # Keep old format for backward compatibility
        if "player_position" not in self.metadata:
            self.metadata["player_position"] = [x, y]
        self.save_metadata()

    def world_to_chunk(self, world_x: float, world_y: float) -> Tuple[int, int]:
        """Convert world pixel coordinates to chunk coordinates"""
        chunk_x = math.floor(world_x / (settings.CHUNK_SIZE * settings.TILE_SIZE))
        chunk_y = math.floor(world_y / (settings.CHUNK_SIZE * settings.TILE_SIZE))
        return (chunk_x, chunk_y)

    def get_visible_chunk_range(self, camera_x: float, camera_y: float, 
                                 screen_width: int, screen_height: int,
                                 zoom: float = 1.0, padding_chunks: int = 2,
                                 movement_dir: Optional[Tuple[float, float]] = None) -> Tuple[int, int, int, int]:
        """
        Calculate visible chunk range based on camera position and screen size.
        
        Supports asymmetric loading: more chunks in movement direction for better preload during fast movement.
        
        Args:
            camera_x: Camera X position in world coordinates (pixels)
            camera_y: Camera Y position in world coordinates (pixels)
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
            zoom: Camera zoom factor (default: 1.0)
            padding_chunks: Number of chunks to add as padding in all directions (default: 3, increased for smoother preload ring)
            movement_dir: Optional movement direction tuple (dx, dy) for asymmetric loading. If provided, adds extra chunks in movement direction.
        
        Returns:
            Tuple of (min_chunk_x, max_chunk_x, min_chunk_y, max_chunk_y)
        """
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        
        # Calculate visible area bounds using central zoom utility
        visible_world_width, visible_world_height = calculate_visible_world_size(
            screen_width, screen_height, zoom
        )
        
        # Calculate world bounds (visible area centered on camera)
        world_min_x = camera_x - visible_world_width / 2.0
        world_max_x = camera_x + visible_world_width / 2.0
        world_min_y = camera_y - visible_world_height / 2.0
        world_max_y = camera_y + visible_world_height / 2.0
        
        # Convert to chunk coordinates
        min_chunk_x = int(world_min_x // chunk_size_pixels)
        max_chunk_x = int(world_max_x // chunk_size_pixels) + 1
        min_chunk_y = int(world_min_y // chunk_size_pixels)
        max_chunk_y = int(world_max_y // chunk_size_pixels) + 1
        
        # Calculate asymmetric padding based on movement direction
        forward_buffer = getattr(settings, 'CHUNK_LOAD_FORWARD_BUFFER', 1)
        
        if movement_dir is not None and (movement_dir[0] != 0.0 or movement_dir[1] != 0.0):
            # Determine dominant movement direction
            move_x, move_y = movement_dir
            
            # Add extra padding in movement direction
            if abs(move_x) > abs(move_y):
                # Horizontal movement dominant
                if move_x > 0:
                    # Moving right: more chunks to the right
                    max_chunk_x += forward_buffer
                else:
                    # Moving left: more chunks to the left
                    min_chunk_x -= forward_buffer
            else:
                # Vertical movement dominant
                if move_y > 0:
                    # Moving down (positive Y): more chunks below
                    max_chunk_y += forward_buffer
                else:
                    # Moving up (negative Y): more chunks above
                    min_chunk_y -= forward_buffer
            
            # Also add standard padding
            min_chunk_x -= padding_chunks
            max_chunk_x += padding_chunks
            min_chunk_y -= padding_chunks
            max_chunk_y += padding_chunks
        else:
            # No movement direction: symmetric padding
            min_chunk_x -= padding_chunks
            max_chunk_x += padding_chunks
            min_chunk_y -= padding_chunks
            max_chunk_y += padding_chunks
        
        # Clamp to world bounds
        min_chunk_x = max(0, min_chunk_x)
        max_chunk_x = min(settings.WORLD_SIZE_CHUNKS, max_chunk_x)
        min_chunk_y = max(0, min_chunk_y)
        max_chunk_y = min(settings.WORLD_SIZE_CHUNKS, max_chunk_y)
        
        return (min_chunk_x, max_chunk_x, min_chunk_y, max_chunk_y)
    
    def update_visible_chunks(self, camera_x: float, camera_y: float,
                              screen_width: int, screen_height: int,
                              zoom: float = 1.0, padding_chunks: int = 2,
                              movement_dir: Optional[Tuple[float, float]] = None):
        """
        Update visible chunks by requesting load for all chunks in visible range.
        
        ABSOLUTE PRIORITIZATION:
        - Chunks that are actually visible on screen → priority = 0 (highest priority)
        - Padding chunks (ring outside visible area) → priority >= REGION_PREFETCH_PRIORITY_OFFSET (lower priority)
        
        This ensures visible chunks are always loaded before prefetch/padding chunks.
        
        Args:
            camera_x: Camera X position in world coordinates (pixels)
            camera_y: Camera Y position in world coordinates (pixels)
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
            zoom: Camera zoom factor (default: 1.0)
            padding_chunks: Number of chunks to add as padding in all directions (default: 3, increased for smoother preload ring)
        """
        from core import settings
        
        # Get visible chunk range WITHOUT padding (truly visible chunks)
        visible_min_x, visible_max_x, visible_min_y, visible_max_y = self.get_visible_chunk_range(
            camera_x, camera_y, screen_width, screen_height, zoom, padding_chunks=0, movement_dir=movement_dir
        )
        
        # Get full range WITH padding (includes padding ring + forward buffer)
        full_min_x, full_max_x, full_min_y, full_max_y = self.get_visible_chunk_range(
            camera_x, camera_y, screen_width, screen_height, zoom, padding_chunks, movement_dir=movement_dir
        )
        
        # Priority offset for padding/prefetch chunks
        # Use priority=1 for prefetch chunks, offset will be applied automatically in request_chunk_load
        prefetch_priority = 1
        
        # FIRST: Load visible chunks with priority = 0 (absolute highest priority)
        visible_chunks = []
        for chunk_x in range(visible_min_x, visible_max_x + 1):
            for chunk_y in range(visible_min_y, visible_max_y + 1):
                # Check world bounds
                if not (0 <= chunk_x < settings.WORLD_SIZE_CHUNKS and
                        0 <= chunk_y < settings.WORLD_SIZE_CHUNKS):
                    continue
                
                chunk_key = (chunk_x, chunk_y)
                
                # Skip if already loaded or pending
                if chunk_key in self.loaded_chunks:
                    continue
                if chunk_key in self.pending_chunks:
                    continue
                
                visible_chunks.append((chunk_x, chunk_y))
        
        # Load visible chunks with priority = 0
        for chunk_x, chunk_y in visible_chunks:
            self.request_chunk_load(chunk_x, chunk_y, priority=0)
        
        # SECOND: Load padding chunks (ring outside visible area) with lower priority
        padding_chunks = []
        for chunk_x in range(full_min_x, full_max_x + 1):
            for chunk_y in range(full_min_y, full_max_y + 1):
                # Check world bounds
                if not (0 <= chunk_x < settings.WORLD_SIZE_CHUNKS and
                        0 <= chunk_y < settings.WORLD_SIZE_CHUNKS):
                    continue
                
                # Skip if in visible area (already handled above)
                if (visible_min_x <= chunk_x <= visible_max_x and
                    visible_min_y <= chunk_y <= visible_max_y):
                    continue
                
                chunk_key = (chunk_x, chunk_y)
                
                # Skip if already loaded or pending
                if chunk_key in self.loaded_chunks:
                    continue
                if chunk_key in self.pending_chunks:
                    continue
                
                padding_chunks.append((chunk_x, chunk_y))
        
        # Load padding chunks with lower priority (same as prefetch)
        # Priority 1 will be automatically offset to REGION_PREFETCH_PRIORITY_OFFSET + 1
        for chunk_x, chunk_y in padding_chunks:
            self.request_chunk_load(chunk_x, chunk_y, priority=prefetch_priority)
    
    def unload_chunks_outside_view(self, camera_x: float, camera_y: float,
                                    screen_width: int, screen_height: int,
                                    zoom: float = 1.0, padding_chunks: int = 3,
                                    max_unloads_per_call: int = 3,
                                    movement_dir: Optional[Tuple[float, float]] = None):
        """
        Unload chunks that are outside the visible view area (with padding).
        
        Iterates over all currently loaded chunks and unloads those whose
        (chunk_x, chunk_y) coordinates are outside the visible range (min/max + padding).
        
        Args:
            camera_x: Camera X position in world coordinates (pixels)
            camera_y: Camera Y position in world coordinates (pixels)
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
            zoom: Camera zoom factor (default: 1.0)
            padding_chunks: Number of chunks padding around visible area (default: 3, increased for smoother preload ring)
            max_unloads_per_call: Maximum number of chunks to unload per call (default: 3)
            movement_dir: Optional movement direction tuple (dx, dy) for asymmetric unload range.
        """
        # Get visible chunk range (with padding + forward buffer)
        min_chunk_x, max_chunk_x, min_chunk_y, max_chunk_y = self.get_visible_chunk_range(
            camera_x, camera_y, screen_width, screen_height, zoom, padding_chunks, movement_dir=movement_dir
        )
        
        # Collect chunks to unload (with cooldown check)
        import time
        current_time = time.time()
        chunks_to_unload = []
        
        for chunk_key, chunk in list(self.loaded_chunks.items()):
            chunk_x, chunk_y = chunk_key
            
            # Check if chunk is INSIDE visible range (should be KEPT)
            # Note: max_chunk_x is exclusive (like range()), so we use < not <=
            # Chunks inside: min_chunk_x <= chunk_x < max_chunk_x
            # Chunks outside: chunk_x < min_chunk_x OR chunk_x >= max_chunk_x
            is_inside_visible_range = (min_chunk_x <= chunk_x < max_chunk_x and
                                      min_chunk_y <= chunk_y < max_chunk_y)
            
            # Only unload chunks that are OUTSIDE the visible range
            if not is_inside_visible_range:
                
                # Check cooldown: chunk must be loaded for at least cooldown seconds
                # This prevents rapid load/unload cycles
                load_time = self.chunk_load_times.get(chunk_key, current_time)
                time_since_load = current_time - load_time
                
                # Only unload if chunk has been loaded for at least cooldown seconds
                if time_since_load >= self.chunk_unload_cooldown:
                    chunks_to_unload.append(chunk_key)
                    
                    # Chunk will be unloaded (no debug output needed)
        
        # Unload chunks (limit to avoid frame drops)
        for chunk_key in chunks_to_unload[:max_unloads_per_call]:
            self.unload_chunk(chunk_key[0], chunk_key[1])
    
    def _get_region_coords(self, chunk_x: int, chunk_y: int) -> Tuple[int, int]:
        """Convert chunk coordinates to region coordinates"""
        from world.region_manager import RegionManager
        region_x = chunk_x // RegionManager.REGION_SIZE_CHUNKS
        region_y = chunk_y // RegionManager.REGION_SIZE_CHUNKS
        return (region_x, region_y)
    
    def _update_region_prefetch(self, camera_x: float, camera_y: float,
                                screen_width: int, screen_height: int,
                                zoom: float):
        """
        Prefetch regions when camera is moving towards a new region boundary.
        
        This method detects when the camera is approaching a region boundary and
        proactively loads region headers and some chunks from adjacent regions.
        
        Args:
            camera_x: Camera X position in world coordinates (pixels)
            camera_y: Camera Y position in world coordinates (pixels)
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
            zoom: Camera zoom factor
        """
        from core import settings
        
        if not getattr(settings, 'REGION_PREFETCH_ENABLED', True):
            return
        
        # Get current camera chunk position
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        camera_chunk_x = int(camera_x // chunk_size_pixels)
        camera_chunk_y = int(camera_y // chunk_size_pixels)
        
        # Get current region
        current_region = self._get_region_coords(camera_chunk_x, camera_chunk_y)
        
        # Check if we've moved to a new region
        if self._last_camera_region is None:
            self._last_camera_region = current_region
            return
        
        if current_region == self._last_camera_region:
            # Still in same region - check if we're close to boundary
            self._prefetch_nearby_regions(camera_chunk_x, camera_chunk_y, screen_width, screen_height, zoom)
        else:
            # Moved to new region - prefetch adjacent regions
            self._prefetch_adjacent_regions(current_region)
            self._last_camera_region = current_region
    
    def _prefetch_nearby_regions(self, camera_chunk_x: int, camera_chunk_y: int,
                                 screen_width: int, screen_height: int,
                                 zoom: float):
        """
        Prefetch regions when camera is near a region boundary.
        
        Args:
            camera_chunk_x: Camera chunk X coordinate
            camera_chunk_y: Camera chunk Y coordinate
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
            zoom: Camera zoom factor
        """
        from core import settings
        from world.region_manager import RegionManager
        
        prefetch_distance = getattr(settings, 'REGION_PREFETCH_DISTANCE_CHUNKS', 2)
        
        # Get current region
        current_region = self._get_region_coords(camera_chunk_x, camera_chunk_y)
        region_x, region_y = current_region
        
        # Calculate local chunk position within region
        local_chunk_x = camera_chunk_x % RegionManager.REGION_SIZE_CHUNKS
        local_chunk_y = camera_chunk_y % RegionManager.REGION_SIZE_CHUNKS
        
        # Check if we're close to region boundaries
        regions_to_prefetch = []
        
        # Check each direction
        if local_chunk_x < prefetch_distance:
            # Close to left boundary - prefetch left region
            regions_to_prefetch.append((region_x - 1, region_y))
        elif local_chunk_x >= RegionManager.REGION_SIZE_CHUNKS - prefetch_distance:
            # Close to right boundary - prefetch right region
            regions_to_prefetch.append((region_x + 1, region_y))
        
        if local_chunk_y < prefetch_distance:
            # Close to bottom boundary - prefetch bottom region
            regions_to_prefetch.append((region_x, region_y - 1))
        elif local_chunk_y >= RegionManager.REGION_SIZE_CHUNKS - prefetch_distance:
            # Close to top boundary - prefetch top region
            regions_to_prefetch.append((region_x, region_y + 1))
        
        # Prefetch corner regions if close to corners
        if (local_chunk_x < prefetch_distance and local_chunk_y < prefetch_distance):
            regions_to_prefetch.append((region_x - 1, region_y - 1))
        elif (local_chunk_x >= RegionManager.REGION_SIZE_CHUNKS - prefetch_distance and 
              local_chunk_y < prefetch_distance):
            regions_to_prefetch.append((region_x + 1, region_y - 1))
        elif (local_chunk_x < prefetch_distance and 
              local_chunk_y >= RegionManager.REGION_SIZE_CHUNKS - prefetch_distance):
            regions_to_prefetch.append((region_x - 1, region_y + 1))
        elif (local_chunk_x >= RegionManager.REGION_SIZE_CHUNKS - prefetch_distance and 
              local_chunk_y >= RegionManager.REGION_SIZE_CHUNKS - prefetch_distance):
            regions_to_prefetch.append((region_x + 1, region_y + 1))
        
        # Prefetch identified regions
        for region in regions_to_prefetch:
            if region not in self._prefetched_regions:
                self._prefetch_region(region)
    
    def _prefetch_adjacent_regions(self, current_region: Tuple[int, int]):
        """
        Prefetch all adjacent regions when entering a new region.
        
        Args:
            current_region: Current region coordinates (region_x, region_y)
        """
        region_x, region_y = current_region
        
        # Prefetch all 8 adjacent regions (including diagonals)
        adjacent_regions = [
            (region_x - 1, region_y - 1),  # Bottom-left
            (region_x, region_y - 1),      # Bottom
            (region_x + 1, region_y - 1),  # Bottom-right
            (region_x - 1, region_y),      # Left
            (region_x + 1, region_y),      # Right
            (region_x - 1, region_y + 1),  # Top-left
            (region_x, region_y + 1),      # Top
            (region_x + 1, region_y + 1),  # Top-right
        ]
        
        for region in adjacent_regions:
            if region not in self._prefetched_regions:
                self._prefetch_region(region)
    
    def _prefetch_region(self, region: Tuple[int, int]):
        """
        Prefetch a region by loading its header and some center chunks.
        
        Args:
            region: Region coordinates (region_x, region_y)
        """
        from core import settings
        from world.region_manager import RegionManager
        
        region_x, region_y = region
        
        # Mark as prefetched
        self._prefetched_regions.add(region)
        
        # Check if region file exists (this loads header into cache)
        # We don't need to do anything else - just checking existence loads the header
        try:
            region_file = self.region_manager._get_region_filename(region_x, region_y)
            if not region_file.exists():
                return  # Region doesn't exist yet, skip
        except Exception:
            return  # Error accessing region, skip
        
        # Prefetch some center chunks from the region
        # These are the chunks most likely to be visible when entering the region
        chunks_per_region = getattr(settings, 'REGION_PREFETCH_CHUNKS_PER_REGION', 5)
        # Use priority=1 for prefetch chunks, offset will be applied automatically in request_chunk_load
        prefetch_priority = 1
        
        # Calculate center chunk of region
        center_local_x = RegionManager.REGION_SIZE_CHUNKS // 2
        center_local_y = RegionManager.REGION_SIZE_CHUNKS // 2
        
        # Convert to global chunk coordinates
        center_chunk_x = region_x * RegionManager.REGION_SIZE_CHUNKS + center_local_x
        center_chunk_y = region_y * RegionManager.REGION_SIZE_CHUNKS + center_local_y
        
        # Prefetch center chunks (small cross pattern around center)
        prefetch_chunks = [
            (center_chunk_x, center_chunk_y),  # Center
            (center_chunk_x - 1, center_chunk_y),  # Left
            (center_chunk_x + 1, center_chunk_y),  # Right
            (center_chunk_x, center_chunk_y - 1),  # Bottom
            (center_chunk_x, center_chunk_y + 1),  # Top
        ]
        
        # Limit to requested number
        prefetch_chunks = prefetch_chunks[:chunks_per_region]
        
        # Request prefetch with lower priority (higher priority number)
        # Priority 1 will be automatically offset to REGION_PREFETCH_PRIORITY_OFFSET + 1
        for chunk_x, chunk_y in prefetch_chunks:
            # Check world bounds
            if not (0 <= chunk_x < settings.WORLD_SIZE_CHUNKS and
                    0 <= chunk_y < settings.WORLD_SIZE_CHUNKS):
                continue
            
            chunk_key = (chunk_x, chunk_y)
            
            # Skip if already loaded or pending
            if chunk_key in self.loaded_chunks:
                continue
            if chunk_key in self.pending_chunks:
                continue
            
            # Request with lower priority (prefetch should not interfere with visible chunks)
            self.request_chunk_load(chunk_x, chunk_y, priority=prefetch_priority)

    def get_or_create_chunk(self, chunk_x, chunk_y, async_load: bool = True):
        """
        Get existing chunk or request async load/generation
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
            async_load: If True, use async loading (default). If False, load synchronously (for initial preload)
        
        Returns:
            Chunk instance if loaded, None if async loading was requested
        """
        key = (chunk_x, chunk_y)
        
        # First check if chunk is already loaded in memory
        if key in self.loaded_chunks:
            return self.loaded_chunks[key]
        
        # If async_load is False, load synchronously (for initial preload)
        if not async_load:
            import time
            current_time = time.time()
            
            # Check if chunk file exists - if it does, try to load it synchronously
            if self._chunk_exists_on_disk(chunk_x, chunk_y):
                loaded_chunk = self._load_chunk_from_file(chunk_x, chunk_y)
                if loaded_chunk:
                    # Populate chunk with decorations if it doesn't have any
                    if not self._chunk_has_decorations(loaded_chunk):
                        self.populate_chunk(loaded_chunk)
                        # Save chunk after decoration population
                        self._save_chunk_to_file(loaded_chunk)
                    
                    self.loaded_chunks[key] = loaded_chunk
                    # Track when chunk was loaded (for cooldown before unloading)
                    self.chunk_load_times[key] = current_time
                    return loaded_chunk
            
            # File doesn't exist - generate new chunk synchronously
            tiles = self.terrain_gen.generate_chunk(chunk_x, chunk_y)
            chunk = Chunk(chunk_x, chunk_y, tiles)
            
            # Populate chunk with decorations (deterministic based on tile raster)
            self.populate_chunk(chunk)
            
            self.loaded_chunks[key] = chunk
            
            # Track when chunk was loaded (for cooldown before unloading)
            self.chunk_load_times[key] = current_time
            
            # Save newly generated chunk IMMEDIATELY (synchronously for preload)
            # Note: Chunk is saved AFTER decoration population
            if not async_load:
                # Save synchronously during preload to prevent empty slots
                seed = self.get_seed()
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.region_manager.save_chunk_data(chunk_x, chunk_y, tiles, seed))
                finally:
                    loop.close()
            else:
                # Save asynchronously for normal loading
                self._save_chunk_to_file(chunk)
            
            # Update chunks_generated in new metadata structure
            if "size" not in self.metadata:
                self.metadata["size"] = {}
            if "chunks_generated" not in self.metadata["size"]:
                self.metadata["size"]["chunks_generated"] = 0
            self.metadata["size"]["chunks_generated"] += 1
            self.save_metadata()
            
            return chunk
        
        # Async loading mode (default)
        # Check if chunk is already being loaded
        if key in self.pending_chunks:
            # Chunk is being loaded asynchronously, return None for now
            # Caller should check again next frame or use process_loaded_chunks
            return None
        
        # Check if chunk exists on disk (fast check without loading)
        if self._chunk_exists_on_disk(chunk_x, chunk_y):
            # Request async load with high priority (distance 0 = immediate area)
            self.request_chunk_load(chunk_x, chunk_y, priority=0)
            return None  # Will be available after async load completes
        
        # Chunk doesn't exist - request async generation with high priority
        self.request_chunk_load(chunk_x, chunk_y, priority=0)
        return None  # Will be available after async generation completes

    def _get_chunk_filename(self, chunk_x: int, chunk_y: int) -> Path:
        """Get the filename for a chunk at given coordinates"""
        return self.chunks_dir / f"chunk_{chunk_x}_{chunk_y}.json"

    def _chunk_exists_on_disk(self, chunk_x: int, chunk_y: int) -> bool:
        """Check if a chunk exists on disk (region file or legacy JSON)"""
        # Check region file first (new format) - async call
        try:
            import asyncio
            # Run async method in new event loop (for thread safety)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(self.region_manager.chunk_exists(chunk_x, chunk_y))
                if result:
                    return True
            finally:
                loop.close()
        except Exception:
            pass  # Fall back to legacy check
        
        # Check legacy JSON file (for migration)
        return self._get_chunk_filename(chunk_x, chunk_y).exists()

    def _wait_until_not_saving(self, chunk_key: Tuple[int, int], max_retries: int = 3) -> bool:
        """
        Wait until a chunk is no longer being saved (thread-safe)
        
        Args:
            chunk_key: Chunk coordinates (chunk_x, chunk_y)
            max_retries: Maximum number of retry attempts (default: 3)
        
        Returns:
            True if chunk is no longer being saved, False if still saving after max_retries
        """
        # Thread-safe check: Check if chunk is currently being saved
        with self._save_lock:
            is_pending = chunk_key in self.pending_saves
        
        if not is_pending:
            return True
        
        # Chunk is being saved - wait with exponential backoff
        for attempt in range(max_retries):
            time.sleep(0.01 * (attempt + 1))  # Exponential backoff: 10ms, 20ms, 30ms
            
            # Thread-safe check again
            with self._save_lock:
                if chunk_key not in self.pending_saves:
                    return True
        
        # Still saving after max retries
        return False

    def _save_chunk_to_file_sync(self, chunk: Chunk):
        """
        Synchronous save a chunk to region file (binary format)
        
        Args:
            chunk: Chunk instance to save
        """
        save_start_time = time.perf_counter()
        
        try:
            # Save using RegionManager (binary format) - async call
            seed = self.get_seed()
            import asyncio
            # Run async method in new event loop (for thread safety)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.region_manager.save_chunk_data(
                    chunk.chunk_x,
                    chunk.chunk_y,
                    chunk.tiles,
                    seed
                ))
            finally:
                loop.close()
            
            # Record chunk save time
            save_time = time.perf_counter() - save_start_time
            if self.performance_monitor:
                self.performance_monitor.record_chunk_save(chunk.chunk_x, chunk.chunk_y, save_time)
        except RegionFileError as e:
            if self.diagnostics:
                self.diagnostics.error("ChunkManager", f"Failed to save chunk ({chunk.chunk_x}, {chunk.chunk_y})", error=str(e))
            else:
                print(f"[ChunkManager] Failed to save chunk ({chunk.chunk_x}, {chunk.chunk_y}): {e}")
            # Don't re-raise - allow game to continue
        except Exception as e:
            if self.diagnostics:
                self.diagnostics.error("ChunkManager", f"Unexpected error saving chunk ({chunk.chunk_x}, {chunk.chunk_y})", error=str(e))
            else:
                print(f"[ChunkManager] Unexpected error saving chunk ({chunk.chunk_x}, {chunk.chunk_y}): {e}")
            import traceback
            traceback.print_exc()
    
    def _chunk_save_worker(self):
        """
        Dedicated worker thread that saves chunks from queue synchronously.
        
        HARD RATE LIMITS (prevents IO spikes):
        - Global rate limit: CHUNK_SAVE_RATE_LIMIT saves/second (HARD CAP: 15-20/sec)
        - Base sleep: 50ms between saves = max 20 chunks/second
        - After slow save (>20ms): Sleep increased to 150ms + 100ms extra = ~6.7 chunks/second
        - After very slow save (>50ms): Sleep increased to 250ms + 150ms extra = ~2.5 chunks/second
        - Token bucket prevents bursts
        - During shutdown: No delay, saves as fast as possible
        - Better delayed saves than storage controller under constant fire causing 100ms spikes
        """
        while self.running or not self.save_queue.empty():
            try:
                # Get chunk from queue (with timeout to allow checking if still running)
                try:
                    # During shutdown, use shorter timeout to process queue faster
                    timeout = 0.01 if not self.running else 0.1
                    chunk = self.save_queue.get(timeout=timeout)
                except queue.Empty:
                    # If not running and queue is empty, exit
                    if not self.running:
                        break
                    continue
                
                chunk_key = (chunk.chunk_x, chunk.chunk_y)
                
                # Thread-safe check: Skip if chunk is no longer loaded or already being saved
                with self._save_lock:
                    if chunk_key not in self.loaded_chunks or chunk_key in self.pending_saves:
                        self.save_queue.task_done()
                        continue
                    
                    # Mark as saving (thread-safe)
                    self.pending_saves.add(chunk_key)
                
                # Save chunk synchronously (direct call, no asyncio/executor overhead)
                # Measure save time for adaptive throttling
                save_start_time = time.perf_counter()
                try:
                    self._save_chunk_to_file_sync(chunk)
                finally:
                    # Thread-safe cleanup: Remove from pending and dirty sets
                    with self._save_lock:
                        self.pending_saves.discard(chunk_key)
                        self.dirty_chunks.discard(chunk_key)
                
                save_time_ms = (time.perf_counter() - save_start_time) * 1000.0
                
                # Adaptive throttling: Increase sleep time if saves are slow
                # This prevents I/O spikes and frame drops during heavy save operations
                extra_sleep = 0.0  # Additional sleep after slow saves to smooth out spikes
                if save_time_ms > settings.CHUNK_SAVE_VERY_SLOW_THRESHOLD_MS:
                    # Very slow save (>50ms): Use maximum throttling + extra sleep
                    self._current_save_sleep = settings.CHUNK_SAVE_VERY_SLOW_SLEEP
                    extra_sleep = settings.CHUNK_SAVE_VERY_SLOW_EXTRA_SLEEP
                elif save_time_ms > settings.CHUNK_SAVE_SLOW_THRESHOLD_MS:
                    # Slow save (>20ms): Use increased throttling + extra sleep to smooth out spikes
                    self._current_save_sleep = settings.CHUNK_SAVE_SLOW_SLEEP
                    extra_sleep = settings.CHUNK_SAVE_SLOW_EXTRA_SLEEP
                else:
                    # Normal save (<=20ms): Gradually return to base sleep time
                    # Smoothly reduce sleep time back to base (prevents oscillation)
                    if self._current_save_sleep > settings.CHUNK_SAVE_BASE_SLEEP:
                        self._current_save_sleep = max(
                            settings.CHUNK_SAVE_BASE_SLEEP,
                            self._current_save_sleep * 0.9  # Reduce by 10% each fast save
                        )
                    else:
                        self._current_save_sleep = settings.CHUNK_SAVE_BASE_SLEEP
                
                self.save_queue.task_done()
                
                # Rate limit: Adaptive sleep based on save performance + token bucket
                # During shutdown (self.running = False), skip delay to save faster
                # This prevents I/O overload and ensures smooth gameplay during normal operation
                if self.running:
                    # Token bucket rate limiting: Check if we have tokens available
                    with self._save_token_lock:
                        now = time.perf_counter()
                        elapsed_ms = (now - self._save_token_last_refill) * 1000.0
                        
                        # Refill tokens based on elapsed time
                        tokens_to_add = elapsed_ms * settings.CHUNK_SAVE_TOKEN_REFILL_RATE
                        self._save_token_bucket = min(
                            settings.CHUNK_SAVE_TOKEN_BUCKET_SIZE,
                            self._save_token_bucket + tokens_to_add
                        )
                        self._save_token_last_refill = now
                        
                        # Check if we have a token available
                        if self._save_token_bucket < 1.0:
                            # No token available - wait for refill
                            # Calculate how long to wait
                            tokens_needed = 1.0 - self._save_token_bucket
                            wait_time_ms = tokens_needed / settings.CHUNK_SAVE_TOKEN_REFILL_RATE
                            wait_time = max(0.0, wait_time_ms / 1000.0)
                            if wait_time > 0:
                                time.sleep(wait_time)
                                # Refill after wait
                                self._save_token_bucket = min(
                                    settings.CHUNK_SAVE_TOKEN_BUCKET_SIZE,
                                    self._save_token_bucket + tokens_needed
                                )
                        
                        # Consume token
                        self._save_token_bucket -= 1.0
                    
                    # Adaptive sleep based on save performance
                    time.sleep(self._current_save_sleep)
                    
                    # Additional sleep after slow saves to smooth out spikes
                    # This prevents multiple slow saves from clustering together
                    if extra_sleep > 0:
                        time.sleep(extra_sleep)
                # During shutdown, no delay - save as fast as possible
                
            except Exception as e:
                if self.diagnostics:
                    self.diagnostics.error("ChunkManager", f"Error in save worker: {e}")
                else:
                    print(f"[ChunkManager] Error in save worker: {e}")
                    import traceback
                    traceback.print_exc()
                # Clean up on error
                try:
                    with self._save_lock:
                        self.pending_saves.discard(chunk_key)
                        self.dirty_chunks.discard(chunk_key)
                except:
                    pass
    
    def _save_chunk_to_file(self, chunk: Chunk):
        """
        Mark chunk for saving (adds to queue, non-blocking, thread-safe)
        Chunks are kept in memory and saved asynchronously when the worker thread has time.
        
        Args:
            chunk: Chunk instance to save
        """
        chunk_key = (chunk.chunk_x, chunk.chunk_y)
        
        # Thread-safe check: Skip if already in queue or being saved
        with self._save_lock:
            if chunk_key in self.pending_saves or chunk_key in self.dirty_chunks:
                return
            
            # Mark as dirty (thread-safe)
            self.dirty_chunks.add(chunk_key)
        
        # Track chunk modification event
        if self.performance_monitor:
            self.performance_monitor.record_chunk_modified(chunk.chunk_x, chunk.chunk_y)
        
        try:
            self.save_queue.put(chunk, block=False)  # Non-blocking, fails if queue full
        except queue.Full:
            # Queue is full, chunk will be saved later when queue has space
            pass

    def _load_chunk_from_file(self, chunk_x: int, chunk_y: int, retry_count: int = 3) -> Optional[Chunk]:
        """
        Load a chunk from region file (binary format) or legacy JSON file
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
            retry_count: Number of retries if file is locked (default: 3)
            
        Returns:
            Chunk instance or None if file doesn't exist or is corrupted
        """
        chunk_key = (chunk_x, chunk_y)
        
        # Wait until chunk is no longer being saved (unified retry logic)
        if not self._wait_until_not_saving(chunk_key, max_retries=retry_count):
            # Chunk is still being saved after retries - return None to retry later
            return None
        
        # Try to load from region file first (new binary format)
        seed = self.get_seed()
        load_start_time = time.perf_counter()
        try:
            # Load using RegionManager (async) - run in new event loop
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                chunk_data = loop.run_until_complete(self.region_manager.load_chunk_data(chunk_x, chunk_y, seed))
            finally:
                loop.close()
            
            # Successfully loaded from region file
            load_time = time.perf_counter() - load_start_time
            tiles = chunk_data['tiles']
            chunk = Chunk(chunk_x, chunk_y, tiles)
            
            # Track chunk loaded from disk (IO operation)
            if self.performance_monitor:
                self.performance_monitor.record_chunk_loaded_from_disk(chunk_x, chunk_y, load_time)
            
            return chunk
        except ChunkNotFoundError:
            # Chunk doesn't exist - this is normal, will generate new one
            pass
        except SeedMismatchError as e:
            # Seed mismatch = chunk belongs to a different world
            # Reject it and return None to force regeneration (prevents mixing worlds)
            if self.diagnostics:
                self.diagnostics.warning("ChunkManager", f"SEED MISMATCH: Chunk ({chunk_x}, {chunk_y}) belongs to different world - rejecting and regenerating", error=str(e))
            else:
                print(f"[ChunkManager] SEED MISMATCH: Chunk ({chunk_x}, {chunk_y}) belongs to different world - rejecting and regenerating")
                print(f"  Details: {e}")
            # Return None to force regeneration - don't load chunks from different worlds
            return None
        except (ChunkCorruptedError, RegionFileError) as e:
            # Corrupted or file error - log and fall back to JSON or generate new
            if self.diagnostics:
                self.diagnostics.error("ChunkManager", f"Error loading chunk ({chunk_x}, {chunk_y})", error=str(e))
            else:
                print(f"[ChunkManager] Error loading chunk ({chunk_x}, {chunk_y}): {e}")
            # Fall through to JSON fallback or generation
        
        # Fallback: Try to load from legacy JSON file (for migration)
        chunk_file = self._get_chunk_filename(chunk_x, chunk_y)
        if chunk_file.exists():
            # Try to load legacy JSON file
            for attempt in range(retry_count):
                try:
                    with open(chunk_file, 'r') as f:
                        content = f.read().strip()
                        if not content:
                            # Empty file - delete it
                            try:
                                chunk_file.unlink()
                            except:
                                pass
                            return None
                        json_data = json.loads(content)
                    
                    if "tiles" not in json_data:
                        # Invalid chunk data - delete corrupted file
                        try:
                            chunk_file.unlink()
                        except:
                            pass
                        return None
                    
                    # Load from JSON and migrate to region format
                    tiles = json_data["tiles"]
                    chunk = Chunk(chunk_x, chunk_y, tiles)
                    
                    # Migrate to region format (save in new format) - async call
                    migration_start_time = time.perf_counter()
                    try:
                        import asyncio
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            loop.run_until_complete(self.region_manager.save_chunk_data(chunk_x, chunk_y, tiles, seed))
                        finally:
                            loop.close()
                        migration_time = time.perf_counter() - migration_start_time
                        
                        # Track legacy migration event
                        if self.performance_monitor:
                            self.performance_monitor.record_chunk_migrated_legacy(chunk_x, chunk_y, migration_time)
                    except RegionFileError as e:
                        if self.diagnostics:
                            self.diagnostics.warning("ChunkManager", f"Failed to migrate chunk ({chunk_x}, {chunk_y})", error=str(e))
                        else:
                            print(f"[ChunkManager] Failed to migrate chunk ({chunk_x}, {chunk_y}): {e}")
                        # Continue anyway - chunk is loaded from JSON
                    
                    # Optionally delete old JSON file after migration
                    # (commented out for safety - uncomment after testing)
                    # try:
                    #     chunk_file.unlink()
                    # except:
                    #     pass
                    
                    return chunk
                    
                except json.JSONDecodeError as e:
                    # Corrupted JSON file
                    if attempt == retry_count - 1:
                        try:
                            chunk_file.unlink()
                            if self.diagnostics:
                                self.diagnostics.warning("ChunkManager", f"Deleted corrupted chunk file ({chunk_x}, {chunk_y})", error=str(e))
                            else:
                                print(f"[ChunkManager] Deleted corrupted chunk file ({chunk_x}, {chunk_y}): {e}")
                        except:
                            pass
                    else:
                        time.sleep(0.01 * (attempt + 1))
                        
                except (PermissionError, OSError) as e:
                    # File is locked
                    error_str = str(e)
                    if "WinError 32" in error_str or "Der Prozess kann nicht auf die Datei zugreifen" in error_str:
                        if attempt < retry_count - 1:
                            wait_time = 0.01 * (2 ** attempt)
                            time.sleep(wait_time)
                            continue
                        else:
                            if self.diagnostics:
                                self.diagnostics.error("ChunkManager", f"Could not load chunk ({chunk_x}, {chunk_y}) after {retry_count} retries", error=str(e))
                            else:
                                print(f"[ChunkManager] Could not load chunk ({chunk_x}, {chunk_y}) after {retry_count} retries: {e}")
                            return None
                    else:
                        return None
                except Exception as e:
                    # Other errors - log but don't spam console
                    error_str = str(e)
                    if ("Expecting value" not in error_str and 
                        "Expecting ':'" not in error_str):
                        if self.diagnostics:
                            self.diagnostics.error("ChunkManager", f"Error loading chunk ({chunk_x}, {chunk_y})", error=str(e))
                        else:
                            print(f"[ChunkManager] Error loading chunk ({chunk_x}, {chunk_y}): {e}")
                    if attempt == retry_count - 1:
                        return None
                    time.sleep(0.01 * (attempt + 1))
        
        # All retries failed - return None (chunk will be loaded from memory or generated)
        return None

    def unload_chunk(self, chunk_x: int, chunk_y: int):
        """
        Save and remove chunk from memory (thread-safe)
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
        """
        key = (chunk_x, chunk_y)
        if key in self.loaded_chunks:
            chunk = self.loaded_chunks[key]
            
            # Wait until chunk is no longer being saved (if it is)
            self._wait_until_not_saving(key, max_retries=3)
            
            # Mark chunk for saving
            self._save_chunk_to_file(chunk)
            
            # Release GPU buffer resources (if renderer is available)
            if self.renderer is not None:
                self.renderer.release_chunk_buffer(chunk_x, chunk_y)
            
            del self.loaded_chunks[key]
            
            # Clean up load time tracking
            self.chunk_load_times.pop(key, None)

    def get_loaded_chunks(self) -> List[Chunk]:
        """Get list of currently loaded chunks"""
        return list(self.loaded_chunks.values())
    
    def preload_visible_area(self, camera_x: float, camera_y: float, 
                             screen_width: int, screen_height: int, 
                             zoom: float = 1.0, padding_chunks: int = 2):
        """
        Pre-load all chunks in visible area synchronously (for world initialization).
        This prevents "empty slot" errors by ensuring chunks are loaded before rendering.
        
        Args:
            camera_x: Camera X position
            camera_y: Camera Y position
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
            zoom: Camera zoom level
            padding_chunks: Number of chunks to load beyond visible area
        """
        # Calculate visible chunk range
        min_chunk_x, max_chunk_x, min_chunk_y, max_chunk_y = self.get_visible_chunk_range(
            camera_x, camera_y, screen_width, screen_height, zoom, padding_chunks
        )
        
        if self.diagnostics:
            self.diagnostics.info("ChunkManager", 
                f"Pre-loading visible area: chunks ({min_chunk_x}, {min_chunk_y}) to ({max_chunk_x}, {max_chunk_y})")
        else:
            print(f"[ChunkManager] Pre-loading visible area: chunks ({min_chunk_x}, {min_chunk_y}) to ({max_chunk_x}, {max_chunk_y})")
        
        # Load all visible chunks synchronously (async_load=False)
        loaded_count = 0
        for chunk_x in range(min_chunk_x, max_chunk_x + 1):
            for chunk_y in range(min_chunk_y, max_chunk_y + 1):
                # Check world bounds
                if not (0 <= chunk_x < settings.WORLD_SIZE_CHUNKS and
                        0 <= chunk_y < settings.WORLD_SIZE_CHUNKS):
                    continue
                
                # Load chunk synchronously (creates if doesn't exist)
                chunk = self.get_or_create_chunk(chunk_x, chunk_y, async_load=False)
                if chunk:
                    loaded_count += 1
        
        if self.diagnostics:
            self.diagnostics.info("ChunkManager", f"Pre-loaded {loaded_count} chunks in visible area")
        else:
            print(f"[ChunkManager] Pre-loaded {loaded_count} chunks in visible area")
    
    def preload_visible_chunks(self, player_pos: Tuple[float, float], buffer: int = 1):
        """Pre-load all chunks visible on screen + buffer (synchronously for initial load)
        
        Args:
            player_pos: Player position (x, y) in world coordinates
            buffer: Extra chunks to load beyond visible area (default: 1, reduced from 2)
        """
        # Calculate visible area in chunks
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        
        # Player chunk position
        player_chunk_x, player_chunk_y = self.world_to_chunk(player_pos[0], player_pos[1])
        
        # Calculate chunks needed to cover screen
        screen_width = settings.SCREEN_WIDTH
        screen_height = settings.SCREEN_HEIGHT
        chunks_horizontal = (screen_width // chunk_size_pixels) + 2  # +2 for partial chunks
        chunks_vertical = (screen_height // chunk_size_pixels) + 2
        
        # Load chunks in a rectangle around player
        half_h = (chunks_horizontal // 2) + buffer
        half_v = (chunks_vertical // 2) + buffer
        
        if self.diagnostics:
            self.diagnostics.info("ChunkManager", f"Pre-loading visible area ({half_h*2}x{half_v*2} chunks)...")
        else:
            print(f"[ChunkManager] Pre-loading visible area ({half_h*2}x{half_v*2} chunks)...")
        
        # Create priority list (center chunks first)
        chunks_to_load = []
        for dx in range(-half_h, half_h + 1):
            for dy in range(-half_v, half_v + 1):
                chunk_x = player_chunk_x + dx
                chunk_y = player_chunk_y + dy
                
                # Only load if within world bounds
                if (0 <= chunk_x < settings.WORLD_SIZE_CHUNKS and
                    0 <= chunk_y < settings.WORLD_SIZE_CHUNKS):
                    # Priority based on distance from center
                    distance = abs(dx) + abs(dy)
                    chunks_to_load.append((distance, chunk_x, chunk_y))
        
        # Sort by distance (center first)
        chunks_to_load.sort()
        
        # Load chunks synchronously (for initial load only)
        # Use async_load=False for synchronous loading during initial preload
        loaded_count = 0
        for _, chunk_x, chunk_y in chunks_to_load:
            chunk = self.get_or_create_chunk(chunk_x, chunk_y, async_load=False)
            if chunk:  # Only count if chunk was actually loaded
                # Surface pre-rendering no longer needed (ModernGL renders directly)
                # chunk.render_to_surface()  # Deprecated - ModernGL renders directly
                loaded_count += 1
        
        if self.diagnostics:
            self.diagnostics.info("ChunkManager", f"Pre-loaded {loaded_count} chunks successfully")
        else:
            print(f"[ChunkManager] Pre-loaded {loaded_count} chunks successfully")
    
    def update(self, player_pos: Tuple[float, float], camera_pos: Optional[Tuple[float, float]] = None,
               screen_width: Optional[int] = None, screen_height: Optional[int] = None,
               zoom: float = 1.0, preload_radius: Optional[int] = None,
               movement_dir: Optional[Tuple[float, float]] = None):
        """
        Update chunk loading/unloading based on camera position (screen-based).
        
        Args:
            player_pos: Player position (x, y) in world coordinates (pixels)
            camera_pos: Camera position (x, y) in world coordinates (pixels). If None, uses player_pos
            screen_width: Screen width in pixels. If None, uses settings.SCREEN_WIDTH
            screen_height: Screen height in pixels. If None, uses settings.SCREEN_HEIGHT
            zoom: Camera zoom factor (default: 1.0)
            preload_radius: Optional radius for preloading chunks around player (for initial load).
                          If None, preloading is skipped.
            movement_dir: Optional movement direction tuple (dx, dy) for asymmetric loading.
                         If provided, loads more chunks in movement direction for better preload during fast movement.
        """
        # Use camera position if provided, otherwise use player position
        if camera_pos is None:
            camera_pos = player_pos
        camera_x, camera_y = camera_pos
        
        # Use screen dimensions from settings if not provided
        if screen_width is None:
            screen_width = settings.SCREEN_WIDTH
        if screen_height is None:
            screen_height = settings.SCREEN_HEIGHT
        
        # Region prefetch: Check if camera is moving towards a new region
        self._update_region_prefetch(camera_x, camera_y, screen_width, screen_height, zoom)
        
        # Optional: Preload chunks around player with radius (for initial load)
        if preload_radius is not None:
            player_chunk_x, player_chunk_y = self.world_to_chunk(player_pos[0], player_pos[1])
            # Only update if player moved to a different chunk or it's the first update
            if self.player_chunk_pos is None or (player_chunk_x, player_chunk_y) != self.player_chunk_pos:
                self.player_chunk_pos = (player_chunk_x, player_chunk_y)
                self.load_chunks_around_player(player_chunk_x, player_chunk_y, preload_radius)
        
        # Update visible chunks based on camera position and screen size
        # Reduced padding to 2 chunks for aggressiveres culling (reduces VBO pool usage)
        # Pass movement direction for asymmetric loading (more chunks in movement direction)
        self.update_visible_chunks(camera_x, camera_y, screen_width, screen_height, zoom, padding_chunks=2, movement_dir=movement_dir)
        
        # Unload chunks outside visible view
        # DISABLED: Unloading is now handled by world_controller.load_visible_chunks()
        # to avoid conflicts and ensure consistent unload logic
        # self.unload_chunks_outside_view(camera_x, camera_y, screen_width, screen_height, zoom, padding_chunks=2, movement_dir=movement_dir)
    
    def load_chunks_around_player(self, player_chunk_x: int, player_chunk_y: int, radius: int):
        """
        Load all chunks within radius of player with priority based on distance
        
        Args:
            player_chunk_x: Player's current chunk X
            player_chunk_y: Player's current chunk Y
            radius: Radius in chunks to load around player
        """
        # Create list of chunks with priorities (distance from player)
        chunks_to_load = []
        
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                chunk_x = player_chunk_x + dx
                chunk_y = player_chunk_y + dy
                
                # Only load if within world bounds
                if (0 <= chunk_x < settings.WORLD_SIZE_CHUNKS and 
                    0 <= chunk_y < settings.WORLD_SIZE_CHUNKS):
                    
                    # Calculate distance priority (closer = lower number = higher priority)
                    distance = abs(dx) + abs(dy)  # Manhattan distance
                    chunks_to_load.append((distance, chunk_x, chunk_y))
        
        # Sort by distance (closest first)
        chunks_to_load.sort()
        
        # Load chunks in priority order
        for priority, chunk_x, chunk_y in chunks_to_load:
            chunk_key = (chunk_x, chunk_y)
            if chunk_key not in self.loaded_chunks and chunk_key not in self.pending_chunks:
                self.request_chunk_load(chunk_x, chunk_y, priority)

    def unload_distant_chunks(self, player_chunk_x: int, player_chunk_y: int, max_distance: int = 3):
        """
        Unload chunks that are too far from player
        
        Args:
            player_chunk_x: Player's current chunk X
            player_chunk_y: Player's current chunk Y
            max_distance: Maximum chunk distance to keep loaded
        """
        chunks_to_unload = []
        
        for (chunk_x, chunk_y) in self.loaded_chunks.keys():
            distance = max(abs(chunk_x - player_chunk_x), abs(chunk_y - player_chunk_y))
            if distance > max_distance:
                chunks_to_unload.append((chunk_x, chunk_y))
        
        for coords in chunks_to_unload:
            self.unload_chunk(*coords)

    def save_all_chunks(self):
        """Save all currently loaded chunks to disk"""
        for chunk in self.loaded_chunks.values():
            self._save_chunk_to_file(chunk)

    def delete_save(self):
        """Delete entire save slot (WARNING: Cannot be undone!)"""
        import shutil
        if self.save_dir.exists():
            try:
                shutil.rmtree(self.save_dir)
                if self.diagnostics:
                    self.diagnostics.info("ChunkManager", f"Deleted save directory: {self.save_dir}")
                else:
                    print(f"Deleted save directory: {self.save_dir}")
            except Exception as e:
                if self.diagnostics:
                    self.diagnostics.error("ChunkManager", f"Error deleting save", error=str(e))
                else:
                    print(f"[ChunkManager] Error deleting save: {e}")

    @staticmethod
    def save_exists(save_slot: int) -> bool:
        """Check if a save slot has existing data"""
        save_dir = Path(f"saves/slot_{save_slot}")
        metadata_file = save_dir / "world_metadata.json"
        return metadata_file.exists()

    @staticmethod
    def get_save_info(save_slot: int) -> Optional[dict]:
        """Get metadata for a save slot without loading the full world"""
        save_dir = Path(f"saves/slot_{save_slot}")
        metadata_file = save_dir / "world_metadata.json"
        
        if not metadata_file.exists():
            return None
        
        try:
            with open(metadata_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            # Note: Static method, no access to diagnostics service
            print(f"Error reading save info: {e}")
            return None

    def _chunk_loader_worker(self):
        """
        Worker thread that loads chunks from the priority queue.
        
        HARD RATE LIMITS (prevents IO spikes):
        - 3 worker threads running in parallel (balanced for good performance)
        - Global rate limit: CHUNK_LOAD_RATE_LIMIT chunks/second (HARD CAP: 60/sec, conservative to prevent bursts)
        - Per-worker rate limit: CHUNK_LOAD_WORKER_RATE_LIMIT chunks/second (HARD CAP: ~25/sec per worker, conservative)
        - Token bucket per worker prevents bursts (bucket size: 8 tokens)
        - Chunks are loaded in priority order (closer to player = higher priority)
        - Sleep times: 20ms for smoother load distribution
        """
        import time
        import threading as thread_module
        
        # Initialize token bucket for this worker
        worker_id = thread_module.get_ident()
        with self._worker_token_lock:
            self._worker_token_buckets[worker_id] = {
                'tokens': float(settings.CHUNK_LOAD_TOKEN_BUCKET_SIZE),
                'last_refill': time.perf_counter()
            }
        
        while self.running:
            try:
                # Check per-worker token bucket rate limit
                with self._worker_token_lock:
                    bucket = self._worker_token_buckets[worker_id]
                    now = time.perf_counter()
                    elapsed_ms = (now - bucket['last_refill']) * 1000.0
                    
                    # Refill tokens based on elapsed time
                    tokens_to_add = elapsed_ms * settings.CHUNK_LOAD_TOKEN_REFILL_RATE
                    bucket['tokens'] = min(
                        settings.CHUNK_LOAD_TOKEN_BUCKET_SIZE,
                        bucket['tokens'] + tokens_to_add
                    )
                    bucket['last_refill'] = now
                    
                    # Check if we have tokens available
                    if bucket['tokens'] < 1.0:
                        # No tokens available, sleep briefly
                        time.sleep(settings.CHUNK_LOAD_RATE_SLEEP_MS)
                        continue
                    
                    # Consume one token
                    bucket['tokens'] -= 1.0
                
                # Check global load rate limit
                current_time = time.perf_counter()
                with self._load_rate_lock:
                    # Remove timestamps older than 1 second
                    cutoff_time = current_time - (settings.CHUNK_LOAD_RATE_WINDOW_MS / 1000.0)
                    self._load_timestamps = [ts for ts in self._load_timestamps if ts > cutoff_time]
                    
                    # Check if we're exceeding the global rate limit
                    if len(self._load_timestamps) >= settings.CHUNK_LOAD_RATE_LIMIT:
                        # Rate limit exceeded, sleep briefly before continuing
                        time.sleep(settings.CHUNK_LOAD_RATE_SLEEP_MS)
                        continue
                
                # Get chunk coordinates from priority queue (conservative timeout for smooth load distribution)
                # PriorityQueue returns items in order: (priority, chunk_x, chunk_y)
                priority, chunk_x, chunk_y = self.chunk_load_queue.get(timeout=0.01)  # Standard timeout for smooth operation
                
                # Check if chunk already loaded (double-check with lock)
                if (chunk_x, chunk_y) in self.loaded_chunks:
                    self.pending_chunks.discard((chunk_x, chunk_y))
                    continue
                
                # Start timing chunk load
                load_start_time = time.perf_counter()
                
                # Load or generate chunk
                chunk = self._load_chunk_from_file(chunk_x, chunk_y)
                generation_time = None
                was_generated = False
                if not chunk:
                    # Generate new chunk - measure generation time separately
                    was_generated = True
                    gen_start_time = time.perf_counter()
                    tiles = self.terrain_gen.generate_chunk(chunk_x, chunk_y)
                    generation_time = time.perf_counter() - gen_start_time
                    chunk = Chunk(chunk_x, chunk_y, tiles)
                
                # Populate chunk with decorations if it doesn't have any (for both generated and loaded chunks)
                if not self._chunk_has_decorations(chunk):
                    self.populate_chunk(chunk)
                
                # Update chunks_generated in metadata (only for newly generated chunks)
                if was_generated:
                    if "size" not in self.metadata:
                        self.metadata["size"] = {}
                    if "chunks_generated" not in self.metadata["size"]:
                        self.metadata["size"]["chunks_generated"] = 0
                    self.metadata["size"]["chunks_generated"] += 1
                    # Note: save_metadata() is called periodically, not on every chunk generation
                    
                    # Save chunk asynchronously (batch operation for better performance)
                    # Note: Chunk is saved AFTER decoration population
                    self._save_chunk_to_file(chunk)
                    
                    # Record generation time (chunk was generated, not loaded from disk)
                    if self.performance_monitor:
                        self.performance_monitor.record_chunk_generation(chunk_x, chunk_y, generation_time)
                
                # Surface pre-rendering no longer needed (ModernGL renders directly)
                # chunk.render_to_surface()  # Deprecated - ModernGL renders directly
                
                # Record overall chunk load time (includes generation if chunk was new)
                # Note: If chunk was loaded from disk, record_chunk_loaded_from_disk was already called
                # This overall load_time includes both disk IO and generation if applicable
                load_time = time.perf_counter() - load_start_time
                load_time_ms = load_time * 1000  # Convert to milliseconds
                
                # Log slow chunks (>50ms)
                if load_time_ms > 50:
                    chunk_size = len(chunk.tiles) if chunk and chunk.tiles else 0
                    if self.diagnostics:
                        self.diagnostics.warning("ChunkManager", 
                            f"Slow chunk load: ({chunk_x}, {chunk_y}): {load_time_ms:.1f}ms, "
                            f"Size: {chunk_size} tiles, Generated: {was_generated}")
                
                if self.performance_monitor:
                    self.performance_monitor.record_chunk_load(chunk_x, chunk_y, load_time)
                
                # Record load timestamp for global rate limiting
                with self._load_rate_lock:
                    self._load_timestamps.append(time.perf_counter())
                
                # Put result in results queue
                self.chunk_load_results.put((chunk_x, chunk_y, chunk))
                self.pending_chunks.discard((chunk_x, chunk_y))
                
            except queue.Empty:
                # No chunks to load, continue waiting
                continue
            except Exception as e:
                if self.diagnostics:
                    self.diagnostics.error("ChunkManager", f"Error loading chunk ({chunk_x}, {chunk_y})", error=str(e))
                else:
                    print(f"[ChunkManager] Error loading chunk ({chunk_x}, {chunk_y}): {e}")
                self.pending_chunks.discard((chunk_x, chunk_y))

    def populate_chunk(self, chunk: Chunk) -> None:
        """
        Populate chunk with decorations based on tile raster.
        Uses deterministic noise based on world coordinates for consistent placement across chunk boundaries.
        
        Args:
            chunk: Chunk instance to populate
        """
        import random
        from world.decoration_registry import DecorationRegistry
        from world.metadata_utils import get_metadata, set_metadata
        
        # Initialize statistics for debugging
        stats = {
            'tiles_checked': 0,
            'decorations_placed': 0,
            'tiles_skipped_already_has_decoration': 0,
            'tiles_skipped_water_biome': 0,
            'tiles_skipped_not_traversable': 0,
            'tiles_skipped_no_valid_decoration': 0,
            'tiles_skipped_noise_threshold': 0,
            'tiles_skipped_density': 0,
            'tiles_skipped_clustering': 0,
        }
        
        # Check if DecorationRegistry is available
        try:
            all_decorations = DecorationRegistry.get_all()
        except (ImportError, AttributeError):
            # DecorationRegistry not available, skip decoration generation
            if self.diagnostics:
                self.diagnostics.debug("ChunkManager", 
                    f"DecorationRegistry not available, skipping populate for chunk ({chunk.chunk_x}, {chunk.chunk_y})")
            return
        
        if not all_decorations:
            if self.diagnostics:
                self.diagnostics.debug("ChunkManager", 
                    f"No decorations available, skipping populate for chunk ({chunk.chunk_x}, {chunk.chunk_y})")
            return
        
        chunk_size = settings.CHUNK_SIZE
        tiles = chunk.tiles
        
        # Calculate world offset for this chunk
        world_offset_x = chunk.chunk_x * chunk_size
        world_offset_y = chunk.chunk_y * chunk_size
        
        # Iterate through all tiles in chunk
        for tile_y in range(chunk_size):
            if tile_y >= len(tiles):
                continue
            for tile_x in range(chunk_size):
                if tile_x >= len(tiles[tile_y]):
                    continue
                
                tile = tiles[tile_y][tile_x]
                if not tile:
                    continue
                
                stats['tiles_checked'] += 1
                
                # Skip if tile already has decoration (check both old and new format)
                if tile.get('decoration') or get_metadata(tile, 'decoration'):
                    stats['tiles_skipped_already_has_decoration'] += 1
                    continue
                
                biome_id = tile.get('biome', '')
                if not biome_id or biome_id.startswith('water:'):
                    stats['tiles_skipped_water_biome'] += 1
                    continue  # Skip water biomes
                
                # Skip if not traversable (e.g., water, mountains)
                if not tile.get('traversable', True):
                    stats['tiles_skipped_not_traversable'] += 1
                    continue
                
                # Calculate world coordinates for noise (deterministic based on world position)
                world_x = world_offset_x + tile_x
                world_y = world_offset_y + tile_y
                
                # Get noise value for this position (deterministic based on world coordinates)
                raw_noise = self.terrain_gen._get_noise_value(world_x, world_y)
                noise_value = (raw_noise + 1.0) / 2.0  # Normalize from [-1, 1] to [0, 1]
                
                # Collect all valid decorations for this tile (instead of using first match)
                valid_decorations = []
                
                for decoration_id, deco_config in all_decorations.items():
                    placement_config = deco_config.get('placement', {})
                    if not placement_config:
                        continue
                    
                    # Get placement settings (support both old 'biomes' and new 'valid_biomes')
                    valid_biomes = placement_config.get('valid_biomes', [])
                    if not valid_biomes:
                        # Fallback to old 'biomes' field for backwards compatibility
                        valid_biomes = placement_config.get('biomes', [])
                    invalid_biomes = placement_config.get('invalid_biomes', [])
                    stray_factor = placement_config.get('stray_factor', 0)
                    
                    # CRITICAL: Check biome validity FIRST (before any other checks)
                    # Decorations MUST only spawn in valid_biomes (with optional stray_factor blending)
                    # If no valid_biomes specified, skip this decoration entirely
                    if not valid_biomes:
                        continue
                    
                    # Check if current biome is explicitly invalid (hard block)
                    if invalid_biomes and biome_id in invalid_biomes:
                        continue
                    
                    # Check if tile is valid for this decoration (includes stray_factor check)
                    is_valid = self._is_tile_valid_for_decoration(
                        tiles, tile_x, tile_y, chunk_size,
                        valid_biomes, invalid_biomes, stray_factor, biome_id
                    )
                    
                    if not is_valid:
                        continue
                    
                    # Only continue with other checks if biome is valid
                    density = placement_config.get('density', 0.1)
                    noise_threshold = placement_config.get('noise_threshold', {})
                    clustering = placement_config.get('clustering', {})
                    
                    # Check noise threshold
                    noise_min = noise_threshold.get('min', 0.0)
                    noise_max = noise_threshold.get('max', 1.0)
                    noise_check = (noise_min <= noise_value <= noise_max)
                    if not noise_check:
                        stats['tiles_skipped_noise_threshold'] += 1
                        continue
                    
                    # Density check
                    density_roll = random.random()
                    density_check = density_roll <= density
                    if not density_check:
                        stats['tiles_skipped_density'] += 1
                        continue
                    
                    # Check clustering if enabled
                    clustering_valid = True
                    if clustering.get('enabled', False):
                        cluster_radius = clustering.get('cluster_radius', 3)
                        nearby_count = 0
                        for dy in range(-cluster_radius, cluster_radius + 1):
                            for dx in range(-cluster_radius, cluster_radius + 1):
                                if dx == 0 and dy == 0:
                                    continue
                                check_x = tile_x + dx
                                check_y = tile_y + dy
                                if 0 <= check_x < chunk_size and 0 <= check_y < chunk_size:
                                    if check_y < len(tiles) and check_x < len(tiles[check_y]):
                                        check_tile = tiles[check_y][check_x]
                                        if check_tile:
                                            # Check new format for decorations
                                            check_decoration = get_metadata(check_tile, 'decoration')
                                            if check_decoration and check_decoration.get('decoration_id') == decoration_id:
                                                nearby_count += 1
                        
                        # Clustering logic: prefer spawning near other decorations, but allow isolated spawns
                        if nearby_count == 0:
                            isolated_spawn_chance = clustering.get('isolated_spawn_chance', 0.7)  # Default 70% chance
                            if random.random() > isolated_spawn_chance:
                                clustering_valid = False
                    
                    if clustering_valid:
                        valid_decorations.append((decoration_id, deco_config))
                
                # Randomly select one decoration from valid decorations (if any)
                if not valid_decorations:
                    stats['tiles_skipped_no_valid_decoration'] += 1
                
                if valid_decorations:
                    decoration_id, deco_config = random.choice(valid_decorations)
                    
                    # Spawn decoration
                    decoration_data = {
                        'decoration_id': decoration_id,
                        'data': {
                            'growth_timer': 0.0,
                            'has_fruit': True,  # Default for harvestable items
                            'damage': 0.0,
                            'last_interaction': 0.0
                        }
                    }
                    
                    # Initialize harvestable-specific data
                    if deco_config.get('harvest', {}).get('enabled'):
                        decoration_data['data']['has_fruit'] = True
                        decoration_data['data']['growth_timer'] = 0.0
                    
                    # Initialize growth stage if growth is enabled
                    growth_config = deco_config.get('growth', {})
                    if growth_config.get('enabled', False):
                        placement_config = deco_config.get('placement', {})
                        spawn_stage_mode = placement_config.get('spawn_stage', 'default')
                        
                        if spawn_stage_mode == 'random':
                            # Use weighted random selection
                            spawn_weights = placement_config.get('spawn_stage_weights', {})
                            if spawn_weights:
                                # Convert weights to list for random.choices
                                stages = []
                                weights = []
                                for stage_str, weight in spawn_weights.items():
                                    try:
                                        stage = int(stage_str)
                                        stages.append(stage)
                                        weights.append(weight)
                                    except ValueError:
                                        continue
                                
                                if stages and weights:
                                    selected_stage = random.choices(stages, weights=weights)[0]
                                    decoration_data['data']['current_stage'] = selected_stage
                                    
                                    # Initialize health based on stage
                                    stages_list = growth_config.get('stages', [])
                                    for stage_config in stages_list:
                                        if stage_config.get('stage') == selected_stage:
                                            decoration_data['data']['health'] = stage_config.get('health', 100)
                                            decoration_data['data']['max_health'] = stage_config.get('health', 100)
                                            decoration_data['data']['growth_progress'] = 0.0
                                            break
                        else:
                            # Use default_stage
                            default_stage = growth_config.get('default_stage', 4)
                            decoration_data['data']['current_stage'] = default_stage
                            
                            # Initialize health based on default stage
                            stages_list = growth_config.get('stages', [])
                            for stage_config in stages_list:
                                if stage_config.get('stage') == default_stage:
                                    decoration_data['data']['health'] = stage_config.get('health', 100)
                                    decoration_data['data']['max_health'] = stage_config.get('health', 100)
                                    decoration_data['data']['growth_progress'] = 0.0
                                    break
                    
                    # Store decoration in tile metadata (new format)
                    set_metadata(tile, 'decoration', decoration_data)
                    
                    # Update chunk's decoration lookup
                    chunk.decoration_lookup[(tile_x, tile_y)] = None
                    
                    stats['decorations_placed'] += 1
        
        # Log statistics for debugging
        if self.diagnostics:
            self.diagnostics.debug("ChunkManager", 
                f"Populated chunk ({chunk.chunk_x}, {chunk.chunk_y}): "
                f"{stats['decorations_placed']} decorations placed, "
                f"{stats['tiles_checked']} tiles checked, "
                f"skipped: already_has={stats['tiles_skipped_already_has_decoration']}, "
                f"water={stats['tiles_skipped_water_biome']}, "
                f"not_traversable={stats['tiles_skipped_not_traversable']}, "
                f"no_valid={stats['tiles_skipped_no_valid_decoration']}, "
                f"noise={stats['tiles_skipped_noise_threshold']}, "
                f"density={stats['tiles_skipped_density']}, "
                f"clustering={stats['tiles_skipped_clustering']}")
    
    def _chunk_has_decorations(self, chunk: Chunk) -> bool:
        """
        Check if chunk has any decorations.
        
        Args:
            chunk: Chunk instance to check
            
        Returns:
            True if chunk has at least one decoration, False otherwise
        """
        from world.metadata_utils import get_metadata
        
        if not chunk.tiles:
            return False
        
        chunk_size = settings.CHUNK_SIZE
        for tile_y in range(chunk_size):
            if tile_y >= len(chunk.tiles):
                continue
            if not chunk.tiles[tile_y]:
                continue
            for tile_x in range(chunk_size):
                if tile_x >= len(chunk.tiles[tile_y]):
                    continue
                tile = chunk.tiles[tile_y][tile_x]
                if tile:
                    # Check new metadata format
                    decoration = get_metadata(tile, 'decoration')
                    if decoration:
                        return True
        return False
    
    def _is_tile_valid_for_decoration(self, tiles, tile_x, tile_y, chunk_size, valid_biomes, invalid_biomes, stray_factor, current_biome_id):
        """
        Check if a tile is valid for spawning a decoration.
        
        Args:
            tiles: 2D list of tile dictionaries
            tile_x: Tile X coordinate within chunk
            tile_y: Tile Y coordinate within chunk
            chunk_size: Size of chunk
            valid_biomes: List of valid biome IDs (empty list = no valid biomes)
            invalid_biomes: List of invalid biome IDs
            stray_factor: Maximum distance in tiles from valid biome (0 = no stray)
            current_biome_id: Current biome ID of the tile
            
        Returns:
            bool: True if tile is valid for spawning
        """
        from world.metadata_utils import get_metadata
        
        # If no valid biomes specified, decoration cannot spawn
        if not valid_biomes:
            return False
        
        # Check if current biome is explicitly invalid
        if invalid_biomes and current_biome_id in invalid_biomes:
            return False
        
        # Check if current biome is directly valid
        if current_biome_id in valid_biomes:
            return True
        
        # If stray_factor is 0, only allow exact biome match
        if stray_factor <= 0:
            return False
        
        # Check if within stray_factor of a valid biome
        # Search in a square around the tile (using Manhattan distance)
        for dy in range(-stray_factor, stray_factor + 1):
            for dx in range(-stray_factor, stray_factor + 1):
                # Skip the center tile (already checked)
                if dx == 0 and dy == 0:
                    continue
                
                # Calculate Manhattan distance
                distance = abs(dx) + abs(dy)
                if distance > stray_factor:
                    continue
                
                # Check neighboring tile
                check_x = tile_x + dx
                check_y = tile_y + dy
                
                # Check bounds
                if 0 <= check_x < chunk_size and 0 <= check_y < chunk_size:
                    if check_y < len(tiles) and check_x < len(tiles[check_y]):
                        check_tile = tiles[check_y][check_x]
                        if check_tile:
                            check_biome_id = check_tile.get('biome', '')
                            if check_biome_id in valid_biomes:
                                return True
        
        return False

    def request_chunk_load(self, chunk_x: int, chunk_y: int, priority: int = 0):
        """
        Request a chunk to be loaded asynchronously (with priority-based ordering)
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
            priority: Priority (lower = higher priority, based on distance from player)
                     - Priority 0 = visible chunks (highest priority, no offset applied)
                     - Priority 1+ = prefetch chunks (deprioritized with REGION_PREFETCH_PRIORITY_OFFSET)
        
        Note: Uses PriorityQueue to ensure chunks closer to player are loaded first.
              Prefetch chunks (priority > 0) are automatically deprioritized to ensure
              visible chunks are always loaded first, even during zoom changes.
              If priority already includes the offset (priority >= REGION_PREFETCH_PRIORITY_OFFSET),
              no additional offset is applied to avoid double-deprioritization.
        """
        chunk_key = (chunk_x, chunk_y)
        if chunk_key not in self.loaded_chunks and chunk_key not in self.pending_chunks:
            self.pending_chunks.add(chunk_key)
            
            # Apply priority offset for prefetch chunks (priority > 0)
            # This ensures visible chunks (priority=0) are always loaded first
            # Prefetch chunks get deprioritized to prevent them from blocking visible chunks
            # Only apply offset if priority doesn't already include it (to avoid double-offset)
            if priority > 0:
                priority_offset = getattr(settings, 'REGION_PREFETCH_PRIORITY_OFFSET', 50)
                # Only add offset if priority is still low (hasn't been offset yet)
                if priority < priority_offset:
                    priority += priority_offset
            
            self.chunk_priority[chunk_key] = priority
            # PriorityQueue requires tuple: (priority, chunk_x, chunk_y)
            # Lower priority number = higher priority (loaded first)
            self.chunk_load_queue.put((priority, chunk_x, chunk_y))
    
    def process_loaded_chunks(self, all_sprites, resource_sprites):
        """
        Process chunks that have finished loading in background threads.
        
        TIME BUDGET WITH MINIMUM GUARANTEE:
        - Time budget: CHUNK_UPLOAD_BUDGET_MS (4.5 ms) per frame - enforced with minimum chunk guarantee
        - Minimum chunks per frame: CHUNK_UPLOAD_MIN_PER_FRAME (2 chunks) - ensures progress even if single chunk is expensive
        - Budget check happens BEFORE processing each chunk, but allows processing minimum chunks even if budget exceeded
        - Effect: Guarantees at least 2 chunks per frame while staying within budget in normal cases
        - Prevents frame drops by spreading chunk processing across multiple frames
        - Chunks are added to sprite groups and marked for saving asynchronously
        """
        frame_start = time.perf_counter()
        loaded_count = 0
        current_time = time.time()
        # Minimum chunks per frame - ensures progress even if single chunk is expensive
        # Increased to 3 for better responsiveness during zoom changes
        MIN_CHUNKS_PER_FRAME = getattr(settings, 'CHUNK_UPLOAD_MIN_PER_FRAME', 3)
        
        # BUDGET ENFORCEMENT WITH MINIMUM GUARANTEE:
        # Process at least MIN_CHUNKS_PER_FRAME chunks, even if budget is exceeded
        # This ensures progress during fast movement and zoom changes, even if a single chunk takes longer
        while not self.chunk_load_results.empty():
            # Budget check: Stop if budget exceeded AND minimum chunks already processed
            # This allows processing minimum chunks even if budget is exceeded (prevents stalling)
            elapsed_ms = (time.perf_counter() - frame_start) * 1000.0
            if elapsed_ms >= settings.CHUNK_UPLOAD_BUDGET_MS and loaded_count >= MIN_CHUNKS_PER_FRAME:
                # Budget exceeded AND minimum chunks processed - stop processing
                if self.diagnostics:
                    self.diagnostics.debug("ChunkManager", 
                        f"Upload budget ({settings.CHUNK_UPLOAD_BUDGET_MS:.2f}ms) exceeded after {loaded_count} chunks. "
                        f"{self.chunk_load_results.qsize()} remaining in queue.")
                break
            
            try:
                chunk_x, chunk_y, chunk = self.chunk_load_results.get_nowait()
                chunk_key = (chunk_x, chunk_y)
                
                # Skip if chunk was already loaded by another thread (race condition protection)
                if chunk_key in self.loaded_chunks:
                    continue
                
                self.loaded_chunks[chunk_key] = chunk
                
                # Track when chunk was loaded (for cooldown before unloading)
                self.chunk_load_times[chunk_key] = current_time
                
                # NOTE: Vertex preparation with texture assignment is now done separately
                # in process_texture_assignment() to ensure textures are assigned AFTER chunk loading
                
                # Add chunk sprites to sprite groups (if any)
                for entity in chunk.entities:
                    all_sprites.add(entity)
                    if hasattr(entity, 'resource_type'):
                        resource_sprites.add(entity)
                
                # Save chunk asynchronously (batch operation)
                self._save_chunk_to_file(chunk)
                
                loaded_count += 1
                
                # Additional budget check AFTER processing (safety net)
                # Stop if budget exceeded AND minimum chunks already processed
                elapsed_ms = (time.perf_counter() - frame_start) * 1000.0
                if elapsed_ms >= settings.CHUNK_UPLOAD_BUDGET_MS and loaded_count >= MIN_CHUNKS_PER_FRAME:
                    # Budget exceeded after processing AND minimum chunks processed - stop immediately
                    break
            except queue.Empty:
                break
        
        # Clean up old priority entries
        if len(self.chunk_priority) > 100:
            # Keep only loaded chunks in priority dict
            self.chunk_priority = {k: v for k, v in self.chunk_priority.items() 
                                   if k in self.loaded_chunks or k in self.pending_chunks}
        
        return loaded_count
    
    def process_texture_assignment(self, max_chunks_per_frame: int = 10):
        """
        Process texture assignment for loaded chunks (separate phase after chunk loading).
        
        This ensures textures are assigned AFTER chunks are fully loaded, preventing
        race conditions where chunks are rendered before textures are available.
        
        Args:
            max_chunks_per_frame: Maximum number of chunks to process per frame (default: 10)
        
        Returns:
            Number of chunks processed
        """
        if not hasattr(self, 'renderer') or self.renderer is None:
            return 0
        
        frame_start = time.perf_counter()
        processed_count = 0
        
        # Process chunks that need texture assignment
        # Only process chunks that are loaded but don't have prepared vertices yet
        chunks_to_process = []
        for chunk_key, chunk in self.loaded_chunks.items():
            if chunk_key not in self.renderer.prepared_chunk_vertices:
                chunks_to_process.append((chunk_key[0], chunk_key[1], chunk))
        
        # Prioritize visible chunks (if renderer has visible_chunks set)
        if hasattr(self.renderer, 'visible_chunks') and self.renderer.visible_chunks:
            visible_chunks = []
            other_chunks = []
            for chunk_x, chunk_y, chunk in chunks_to_process:
                chunk_key = (chunk_x, chunk_y)
                if chunk_key in self.renderer.visible_chunks:
                    visible_chunks.append((chunk_x, chunk_y, chunk))
                else:
                    other_chunks.append((chunk_x, chunk_y, chunk))
            # Process visible chunks first
            chunks_to_process = visible_chunks + other_chunks
        
        # Limit processing to max_chunks_per_frame to prevent frame drops
        for chunk_x, chunk_y, chunk in chunks_to_process[:max_chunks_per_frame]:
            chunk_key = (chunk_x, chunk_y)
            
            # Budget check: Stop if we've exceeded time budget
            elapsed_ms = (time.perf_counter() - frame_start) * 1000.0
            if elapsed_ms >= settings.CHUNK_UPLOAD_BUDGET_MS:
                break
            
            try:
                # Prepare vertices with texture assignment
                vertex_array = self.renderer._prepare_chunk_vertices(chunk_x, chunk_y, chunk.tiles)
                self.renderer.prepared_chunk_vertices[chunk_key] = vertex_array
                processed_count += 1
            except Exception as e:
                # If preparation fails, log but continue
                if self.diagnostics:
                    self.diagnostics.warning("ChunkManager", f"Failed to assign textures for chunk {chunk_key}: {e}")
        
        return processed_count
        
        # Clean up old priority entries
        if len(self.chunk_priority) > 100:
            # Keep only loaded chunks in priority dict
            self.chunk_priority = {k: v for k, v in self.chunk_priority.items() 
                                   if k in self.loaded_chunks or k in self.pending_chunks}
    
    def refresh_visible_chunks(self, player_pos: Tuple[float, float]):
        """Refresh chunk loading after screen size change (e.g., fullscreen toggle)
        
        Args:
            player_pos: Player position (x, y) in world coordinates
        """
        player_chunk_x, player_chunk_y = self.world_to_chunk(player_pos[0], player_pos[1])
        load_distance = settings.get_chunk_load_distance()
        
        if self.diagnostics:
            self.diagnostics.info("ChunkManager", f"Refreshing visible chunks with distance {load_distance}...")
        else:
            print(f"[ChunkManager] Refreshing visible chunks with distance {load_distance}...")
        
        # Load additional chunks that are now visible
        self.load_chunks_around_player(player_chunk_x, player_chunk_y, load_distance)
    
    def refresh_visible_chunks_for_zoom(self, camera_pos: Tuple[float, float], zoom: float,
                                         screen_width: int = None, screen_height: int = None):
        """
        Refresh chunk loading after zoom change.
        
        This method should be called when the zoom level changes (e.g., via mouse wheel)
        to ensure the correct chunks are loaded for the new visible area.
        
        Args:
            camera_pos: Camera position (x, y) in world coordinates (pixels)
            zoom: Camera zoom factor (1.0 = 100%, 1.5 = 150% nah, 0.75 = 75% weit weg)
            screen_width: Screen width in pixels (optional, uses settings if not provided)
            screen_height: Screen height in pixels (optional, uses settings if not provided)
        """
        camera_x, camera_y = camera_pos
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        
        # Get current screen size
        if screen_width is None:
            screen_width = settings.get_screen_width()
        if screen_height is None:
            screen_height = settings.get_screen_height()
        
        if self.diagnostics:
            self.diagnostics.debug("ChunkManager", f"Refreshing visible chunks for zoom change (zoom={zoom:.2f})...")
        
        # Calculate visible area in world coordinates using central zoom utility
        visible_world_width, visible_world_height = calculate_visible_world_size(
            screen_width, screen_height, zoom
        )
        
        world_min_x = camera_x - visible_world_width / 2.0
        world_max_x = camera_x + visible_world_width / 2.0
        world_min_y = camera_y - visible_world_height / 2.0
        world_max_y = camera_y + visible_world_height / 2.0
        
        # Convert to chunk coordinates (with padding)
        min_chunk_x = int(math.floor(world_min_x / chunk_size_pixels)) - 1
        max_chunk_x = int(math.floor(world_max_x / chunk_size_pixels)) + 1
        min_chunk_y = int(math.floor(world_min_y / chunk_size_pixels)) - 1
        max_chunk_y = int(math.floor(world_max_y / chunk_size_pixels)) + 1
        
        # Collect visible chunks
        visible_chunks = []
        for cx in range(min_chunk_x, max_chunk_x + 1):
            for cy in range(min_chunk_y, max_chunk_y + 1):
                if 0 <= cx < settings.WORLD_SIZE_CHUNKS and 0 <= cy < settings.WORLD_SIZE_CHUNKS:
                    visible_chunks.append((cx, cy))
        
        # Load visible chunks with highest priority (priority 0)
        # Force all visible chunks to Priority 0, even if they were previously requested with lower priority
        # This ensures visible chunks are loaded immediately, even if they were prefetched earlier
        for chunk_x, chunk_y in visible_chunks:
            chunk_key = (chunk_x, chunk_y)
            # Skip if already loaded
            if chunk_key not in self.loaded_chunks:
                # Remove from pending_chunks if it was there with lower priority
                # This allows re-queuing with Priority 0
                if chunk_key in self.pending_chunks:
                    self.pending_chunks.discard(chunk_key)
                # Request with highest priority (Priority 0)
                self.request_chunk_load(chunk_x, chunk_y, priority=0)
        
        # Also unload chunks that are now outside the visible area
        self.unload_chunks_outside_view(
            camera_x, camera_y,
            screen_width, screen_height,
            zoom=zoom,
            padding_chunks=2
        )
    
    def save_all_chunks(self):
        """
        Save all loaded chunks (thread-safe, simplified approach)
        Marks all chunks as dirty and adds them to the save queue.
        """
        with self._save_lock:
            chunks_to_save = list(self.loaded_chunks.values())
        
        # Add all chunks to save queue (non-blocking)
        for chunk in chunks_to_save:
            self._save_chunk_to_file(chunk)
    
    def shutdown(self):
        """
        Stop worker threads and cleanup resources.
        
        Ensures:
        - All pending chunks are saved before shutdown
        - Worker threads are gracefully stopped
        - All queues are processed
        - Region file handles are closed
        """
        if self.diagnostics:
            self.diagnostics.info("ChunkManager", "Starting shutdown...")
        else:
            print("[ChunkManager] Starting shutdown...")
        
        # Set running flag to False to signal workers to stop
        self.running = False
        
        # Save all loaded chunks before shutdown (ensures no data loss)
        if self.diagnostics:
            self.diagnostics.info("ChunkManager", "Saving all loaded chunks...")
        else:
            print("[ChunkManager] Saving all loaded chunks...")
        self.save_all_chunks()
        
        # Calculate timeout based on queue size (50ms per chunk + buffer)
        queue_size = self.save_queue.qsize()
        # Estimate: 50ms per chunk + 2 seconds buffer
        estimated_time = (queue_size * 0.05) + 2.0
        timeout = max(10.0, estimated_time)  # Minimum 10 seconds, more if needed
        if self.diagnostics:
            self.diagnostics.info("ChunkManager", f"Waiting for save queue to empty ({queue_size} chunks, timeout: {timeout:.1f}s)...")
        else:
            print(f"[ChunkManager] Waiting for save queue to empty ({queue_size} chunks, timeout: {timeout:.1f}s)...")
        
        # Wait for save queue to empty (with dynamic timeout based on queue size)
        try:
            start_time = time.time()
            last_size = queue_size
            while not self.save_queue.empty() and (time.time() - start_time) < timeout:
                current_size = self.save_queue.qsize()
                # Log progress every second or when queue size changes significantly
                elapsed = time.time() - start_time
                if elapsed > 1.0 and (current_size != last_size or int(elapsed) % 2 == 0):
                    remaining = current_size
                    if self.diagnostics:
                        self.diagnostics.info("ChunkManager", f"Save queue: {remaining} chunks remaining ({elapsed:.1f}s elapsed)")
                    else:
                        print(f"[ChunkManager] Save queue: {remaining} chunks remaining ({elapsed:.1f}s elapsed)")
                    last_size = current_size
                time.sleep(0.1)
            
            if not self.save_queue.empty():
                remaining = self.save_queue.qsize()
                if self.diagnostics:
                    self.diagnostics.warning("ChunkManager", f"{remaining} chunks still in save queue after timeout")
                else:
                    print(f"[ChunkManager] WARNING: {remaining} chunks still in save queue after timeout")
                # Force save remaining chunks synchronously (last resort)
                if self.diagnostics:
                    self.diagnostics.info("ChunkManager", f"Force-saving {remaining} remaining chunks synchronously...")
                else:
                    print(f"[ChunkManager] Force-saving {remaining} remaining chunks synchronously...")
                force_saved = 0
                while not self.save_queue.empty():
                    try:
                        chunk = self.save_queue.get_nowait()
                        try:
                            self._save_chunk_to_file_sync(chunk)
                            force_saved += 1
                        except Exception as e:
                            if self.diagnostics:
                                self.diagnostics.error("ChunkManager", f"Error force-saving chunk ({chunk.chunk_x}, {chunk.chunk_y})", error=str(e))
                            else:
                                print(f"[ChunkManager] Error force-saving chunk ({chunk.chunk_x}, {chunk.chunk_y}): {e}")
                    except queue.Empty:
                        break
                if self.diagnostics:
                    self.diagnostics.info("ChunkManager", f"Force-saved {force_saved} chunks")
                else:
                    print(f"[ChunkManager] Force-saved {force_saved} chunks")
        except Exception as e:
            if self.diagnostics:
                self.diagnostics.error("ChunkManager", "Error waiting for save queue", error=str(e))
            else:
                print(f"[ChunkManager] Error waiting for save queue: {e}")
            import traceback
            traceback.print_exc()
        
        # Wait for save worker thread to finish
        if hasattr(self, 'save_worker_thread') and self.save_worker_thread.is_alive():
            if self.diagnostics:
                self.diagnostics.info("ChunkManager", "Waiting for save worker thread...")
            else:
                print("[ChunkManager] Waiting for save worker thread...")
            self.save_worker_thread.join(timeout=2.0)
            if self.save_worker_thread.is_alive():
                if self.diagnostics:
                    self.diagnostics.warning("ChunkManager", "Save worker thread did not terminate in time")
                else:
                    print("[ChunkManager] WARNING: Save worker thread did not terminate in time")
        
        # Wait for loader worker threads to finish
        if self.diagnostics:
            self.diagnostics.info("ChunkManager", "Waiting for loader worker threads...")
        else:
            print("[ChunkManager] Waiting for loader worker threads...")
        for i, thread in enumerate(self.worker_threads):
            if thread.is_alive():
                thread.join(timeout=1.0)
                if thread.is_alive():
                    if self.diagnostics:
                        self.diagnostics.warning("ChunkManager", f"Loader worker thread {i} did not terminate in time")
                    else:
                        print(f"[ChunkManager] WARNING: Loader worker thread {i} did not terminate in time")
        
        # Close all region file handles (releases file handles and locks)
        if hasattr(self, 'region_manager'):
            if self.diagnostics:
                self.diagnostics.info("ChunkManager", "Closing region file handles...")
            else:
                print("[ChunkManager] Closing region file handles...")
            self.region_manager.close_all_files()
        
        if self.diagnostics:
            self.diagnostics.info("ChunkManager", "Shutdown complete")
        else:
            print("[ChunkManager] Shutdown complete")
