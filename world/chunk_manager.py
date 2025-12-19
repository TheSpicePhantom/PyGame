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


class ChunkManager:
    """Manages chunk loading/unloading and save/load to JSON"""

    def __init__(self, save_slot: int, terrain_gen, performance_monitor=None):
        """
        Initialize ChunkManager for a specific save slot
        
        Args:
            save_slot: Save slot number (1-3)
            terrain_gen: TerrainGenerator instance for new chunk generation
            performance_monitor: Optional PerformanceMonitor instance for metrics
        """
        self.save_slot = save_slot
        self.terrain_gen = terrain_gen
        self.performance_monitor = performance_monitor
        self.loaded_chunks: Dict[Tuple[int, int], Chunk] = {}
        self.player_chunk_pos = None  # Changed from (0, 0) to None to force initial load
        
        # Setup save directories
        self.save_dir = Path(f"saves/slot_{save_slot}")
        self.chunks_dir = self.save_dir / "chunks"  # Keep for backward compatibility check
        self.chunks_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize RegionManager for binary region-based storage
        self.region_manager = RegionManager(save_slot)
        
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
        
        # Performance limits (documented for tuning):
        # - Max chunks loaded per second: ~30 chunks/sec (3 workers, ~100ms per chunk average)
        # - Max chunks saved per second: 20 chunks/sec (1 worker, 50ms delay between saves)
        # - Max chunks processed per frame: 1 chunk per frame (via process_loaded_chunks)
        # These limits prevent frame drops and I/O overload
        
        # Async save system - Queue-based for better performance
        self.pending_saves = set()  # Track chunks being saved (thread-safe)
        self.save_queue = queue.Queue()  # Queue for chunks to save
        self.dirty_chunks = set()  # Chunks that need saving (marked as dirty, thread-safe)
        self._save_lock = threading.Lock()  # Lock for pending_saves and dirty_chunks
        
        # Start dedicated save worker thread (runs continuously, saves when queue has items)
        self.save_worker_thread = threading.Thread(target=self._chunk_save_worker, daemon=True, name="ChunkSaveWorker")
        self.save_worker_thread.start()
        
        # Start 3 worker threads for chunk loading (increased from 2)
        for i in range(3):
            thread = threading.Thread(target=self._chunk_loader_worker, daemon=True)
            thread.start()
            self.worker_threads.append(thread)

    def _load_metadata(self) -> dict:
        """Load world metadata (seed, player position, etc.)"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading metadata: {e}")
        
        # Default metadata for new world
        return {
            "seed": None,
            "player_position": [0, 0],
            "playtime_seconds": 0,
            "chunks_generated": 0,
            "version": "1.0"
        }

    def save_metadata(self):
        """Save world metadata to file"""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2)
        except Exception as e:
            print(f"Error saving metadata: {e}")

    def set_seed(self, seed: int):
        """Set the world seed"""
        self.metadata["seed"] = seed
        self.save_metadata()

    def get_seed(self) -> Optional[int]:
        """Get the world seed"""
        return self.metadata.get("seed")
    
    def update_player_position(self, x: float, y: float):
        """Update player position in metadata"""
        self.metadata["player_position"] = [x, y]
        self.save_metadata()

    def world_to_chunk(self, world_x: float, world_y: float) -> Tuple[int, int]:
        """Convert world pixel coordinates to chunk coordinates"""
        chunk_x = math.floor(world_x / (settings.CHUNK_SIZE * settings.TILE_SIZE))
        chunk_y = math.floor(world_y / (settings.CHUNK_SIZE * settings.TILE_SIZE))
        return (chunk_x, chunk_y)

    def get_or_create_chunk(self, chunk_x, chunk_y):
        """Get existing chunk or generate new one"""
        key = (chunk_x, chunk_y)
        
        # First check if chunk is already loaded in memory
        if key in self.loaded_chunks:
            return self.loaded_chunks[key]
        
        # Check if chunk file exists - if it does, try to load it
        # (even if it's being saved, we should wait and load it)
        chunk_file = self._get_chunk_filename(chunk_x, chunk_y)
        if chunk_file.exists():
            # File exists - try to load it (with retry logic for locked files)
            loaded_chunk = self._load_chunk_from_file(chunk_x, chunk_y)
            if loaded_chunk:
                self.loaded_chunks[key] = loaded_chunk
                return loaded_chunk
            # If loading failed (file locked or corrupted), don't generate new chunk
            # Instead, wait a bit more and try again, or return None to indicate
            # that the chunk should be loaded from memory if it exists elsewhere
            # For now, we'll generate a new chunk only if file doesn't exist
            # This prevents data loss from locked files
        
        # File doesn't exist - generate new chunk
        tiles = self.terrain_gen.generate_chunk(chunk_x, chunk_y)
        chunk = Chunk(chunk_x, chunk_y, tiles)
        self.loaded_chunks[key] = chunk
        
        # Save newly generated chunk
        self._save_chunk_to_file(chunk)
        
        self.metadata["chunks_generated"] += 1
        self.save_metadata()
        
        return chunk

    def _get_chunk_filename(self, chunk_x: int, chunk_y: int) -> Path:
        """Get the filename for a chunk at given coordinates"""
        return self.chunks_dir / f"chunk_{chunk_x}_{chunk_y}.json"

    def _chunk_exists_on_disk(self, chunk_x: int, chunk_y: int) -> bool:
        """Check if a chunk exists on disk (region file or legacy JSON)"""
        # Check region file first (new format)
        if self.region_manager.chunk_exists(chunk_x, chunk_y):
            return True
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
            # Save using RegionManager (binary format)
            seed = self.get_seed()
            self.region_manager.save_chunk_data(
                chunk.chunk_x,
                chunk.chunk_y,
                chunk.tiles,
                seed
            )
            
            # Record chunk save time
            save_time = time.perf_counter() - save_start_time
            if self.performance_monitor:
                self.performance_monitor.record_chunk_save(chunk.chunk_x, chunk.chunk_y, save_time)
        except RegionFileError as e:
            print(f"[ChunkManager] Failed to save chunk ({chunk.chunk_x}, {chunk.chunk_y}): {e}")
            # Don't re-raise - allow game to continue
        except Exception as e:
            print(f"[ChunkManager] Unexpected error saving chunk ({chunk.chunk_x}, {chunk.chunk_y}): {e}")
            import traceback
            traceback.print_exc()
    
    def _chunk_save_worker(self):
        """
        Dedicated worker thread that saves chunks from queue synchronously.
        Simplified approach: directly call sync save method, no asyncio/executor overhead.
        
        Performance limits:
        - Rate limit: 50ms delay between saves = max 20 chunks/second
        - Prevents I/O overload and frame drops
        """
        while self.running:
            try:
                # Get chunk from queue (with timeout to allow checking if still running)
                try:
                    chunk = self.save_queue.get(timeout=0.1)  # Check every 100ms
                except queue.Empty:
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
                try:
                    self._save_chunk_to_file_sync(chunk)
                finally:
                    # Thread-safe cleanup: Remove from pending and dirty sets
                    with self._save_lock:
                        self.pending_saves.discard(chunk_key)
                        self.dirty_chunks.discard(chunk_key)
                
                self.save_queue.task_done()
                
                # Rate limit: Only save 1 chunk per 50ms = max 20 chunks/second
                # This prevents I/O overload and ensures smooth gameplay
                time.sleep(0.05)  # 50ms delay between saves
                
            except Exception as e:
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
            chunk_data = self.region_manager.load_chunk_data(chunk_x, chunk_y, seed)
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
            print(f"[ChunkManager] SEED MISMATCH: Chunk ({chunk_x}, {chunk_y}) belongs to different world - rejecting and regenerating")
            print(f"  Details: {e}")
            # Return None to force regeneration - don't load chunks from different worlds
            return None
        except (ChunkCorruptedError, RegionFileError) as e:
            # Corrupted or file error - log and fall back to JSON or generate new
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
                    
                    # Migrate to region format (save in new format)
                    migration_start_time = time.perf_counter()
                    try:
                        self.region_manager.save_chunk_data(chunk_x, chunk_y, tiles, seed)
                        migration_time = time.perf_counter() - migration_start_time
                        
                        # Track legacy migration event
                        if self.performance_monitor:
                            self.performance_monitor.record_chunk_migrated_legacy(chunk_x, chunk_y, migration_time)
                    except RegionFileError as e:
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
                            print(f"[ChunkManager] Could not load chunk ({chunk_x}, {chunk_y}) after {retry_count} retries: {e}")
                            return None
                    else:
                        return None
                except Exception as e:
                    # Other errors - log but don't spam console
                    error_str = str(e)
                    if ("Expecting value" not in error_str and 
                        "Expecting ':'" not in error_str):
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
            del self.loaded_chunks[key]

    def get_loaded_chunks(self) -> List[Chunk]:
        """Get list of currently loaded chunks"""
        return list(self.loaded_chunks.values())
    
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
        loaded_count = 0
        for _, chunk_x, chunk_y in chunks_to_load:
            chunk = self.get_or_create_chunk(chunk_x, chunk_y)
            # Surface pre-rendering no longer needed (ModernGL renders directly)
            # chunk.render_to_surface()  # Deprecated - ModernGL renders directly
            loaded_count += 1
        
        print(f"[ChunkManager] Pre-loaded {loaded_count} chunks successfully")
    
    def update(self, player_pos: Tuple[float, float]):
        """Update chunk loading/unloading based on player position
        
        Args:
            player_pos: Player position (x, y) in world coordinates (pixels)
        """
        # Convert player position to chunk coordinates
        player_chunk_x, player_chunk_y = self.world_to_chunk(player_pos[0], player_pos[1])
        
        # Get dynamic chunk distances based on screen size
        load_distance = settings.get_chunk_load_distance()
        unload_distance = settings.get_chunk_unload_distance()
        
        # Only update if player moved to a different chunk or it's the first update
        if self.player_chunk_pos is None or (player_chunk_x, player_chunk_y) != self.player_chunk_pos:
            self.player_chunk_pos = (player_chunk_x, player_chunk_y)
            
            # Load chunks around player with dynamic distance
            self.load_chunks_around_player(player_chunk_x, player_chunk_y, load_distance)
            
            # Unload distant chunks (only if we have chunks loaded already)
            if len(self.loaded_chunks) > 0:
                self.unload_distant_chunks(player_chunk_x, player_chunk_y, unload_distance)
    
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
                print(f"Deleted save slot {self.save_slot}")
            except Exception as e:
                print(f"Error deleting save: {e}")

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
            print(f"Error reading save info: {e}")
            return None

    def _chunk_loader_worker(self):
        """
        Worker thread that loads chunks from the priority queue.
        
        Performance limits:
        - 3 worker threads running in parallel
        - Average load time: ~100ms per chunk (load from disk) or ~50ms (generate new)
        - Effective throughput: ~30 chunks/second (3 workers * ~10 chunks/sec per worker)
        - Chunks are loaded in priority order (closer to player = higher priority)
        """
        import time
        while self.running:
            try:
                # Get chunk coordinates from priority queue (timeout prevents hanging)
                # PriorityQueue returns items in order: (priority, chunk_x, chunk_y)
                priority, chunk_x, chunk_y = self.chunk_load_queue.get(timeout=0.1)
                
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
                    # Don't save immediately - batch save later for better performance
                    
                    # Record generation time (chunk was generated, not loaded from disk)
                    if self.performance_monitor:
                        self.performance_monitor.record_chunk_generation(chunk_x, chunk_y, generation_time)
                
                # Surface pre-rendering no longer needed (ModernGL renders directly)
                # chunk.render_to_surface()  # Deprecated - ModernGL renders directly
                
                # Record overall chunk load time (includes generation if chunk was new)
                # Note: If chunk was loaded from disk, record_chunk_loaded_from_disk was already called
                # This overall load_time includes both disk IO and generation if applicable
                load_time = time.perf_counter() - load_start_time
                if self.performance_monitor:
                    self.performance_monitor.record_chunk_load(chunk_x, chunk_y, load_time)
                
                # Put result in results queue
                self.chunk_load_results.put((chunk_x, chunk_y, chunk))
                self.pending_chunks.discard((chunk_x, chunk_y))
                
            except queue.Empty:
                # No chunks to load, continue waiting
                continue
            except Exception as e:
                print(f"[ChunkManager] Error loading chunk ({chunk_x}, {chunk_y}): {e}")
                self.pending_chunks.discard((chunk_x, chunk_y))

    def request_chunk_load(self, chunk_x: int, chunk_y: int, priority: int = 0):
        """
        Request a chunk to be loaded asynchronously (with priority-based ordering)
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
            priority: Priority (lower = higher priority, based on distance from player)
                     - Priority 0 = immediate area around player (highest priority)
                     - Priority 1-2 = nearby chunks
                     - Priority 3+ = distant chunks (lowest priority)
        
        Note: Uses PriorityQueue to ensure chunks closer to player are loaded first.
              This prevents loading distant chunks while nearby chunks are still missing.
        """
        chunk_key = (chunk_x, chunk_y)
        if chunk_key not in self.loaded_chunks and chunk_key not in self.pending_chunks:
            self.pending_chunks.add(chunk_key)
            self.chunk_priority[chunk_key] = priority
            # PriorityQueue requires tuple: (priority, chunk_x, chunk_y)
            # Lower priority number = higher priority (loaded first)
            self.chunk_load_queue.put((priority, chunk_x, chunk_y))
    
    def process_loaded_chunks(self, all_sprites, resource_sprites):
        """
        Process chunks that have finished loading in background threads.
        
        Performance limits:
        - Max chunks processed per frame: 1 chunk
        - Prevents frame drops by spreading chunk processing across multiple frames
        - Chunks are added to sprite groups and marked for saving asynchronously
        """
        loaded_count = 0
        max_per_frame = 1  # Process 1 chunk per frame to prevent frame drops
        
        while not self.chunk_load_results.empty() and loaded_count < max_per_frame:
            try:
                chunk_x, chunk_y, chunk = self.chunk_load_results.get_nowait()
                self.loaded_chunks[(chunk_x, chunk_y)] = chunk
                
                # Add chunk sprites to sprite groups (if any)
                for entity in chunk.entities:
                    all_sprites.add(entity)
                    if hasattr(entity, 'resource_type'):
                        resource_sprites.add(entity)
                
                # Save chunk asynchronously (batch operation)
                self._save_chunk_to_file(chunk)
                
                loaded_count += 1
            except queue.Empty:
                break
        
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
        
        print(f"[ChunkManager] Refreshing visible chunks with distance {load_distance}...")
        
        # Load additional chunks that are now visible
        self.load_chunks_around_player(player_chunk_x, player_chunk_y, load_distance)
    
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
        print("[ChunkManager] Starting shutdown...")
        
        # Set running flag to False to signal workers to stop
        self.running = False
        
        # Save all loaded chunks before shutdown (ensures no data loss)
        print("[ChunkManager] Saving all loaded chunks...")
        self.save_all_chunks()
        
        # Wait for save queue to empty (with timeout to prevent hanging)
        # PriorityQueue doesn't support task_done/join, so we wait for save_queue instead
        print("[ChunkManager] Waiting for save queue to empty...")
        try:
            # Wait up to 5 seconds for save queue to empty
            timeout = 5.0
            start_time = time.time()
            while not self.save_queue.empty() and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            if not self.save_queue.empty():
                remaining = self.save_queue.qsize()
                print(f"[ChunkManager] WARNING: {remaining} chunks still in save queue after timeout")
        except Exception as e:
            print(f"[ChunkManager] Error waiting for save queue: {e}")
        
        # Wait for save worker thread to finish
        if hasattr(self, 'save_worker_thread') and self.save_worker_thread.is_alive():
            print("[ChunkManager] Waiting for save worker thread...")
            self.save_worker_thread.join(timeout=2.0)
            if self.save_worker_thread.is_alive():
                print("[ChunkManager] WARNING: Save worker thread did not terminate in time")
        
        # Wait for loader worker threads to finish
        print("[ChunkManager] Waiting for loader worker threads...")
        for i, thread in enumerate(self.worker_threads):
            if thread.is_alive():
                thread.join(timeout=1.0)
                if thread.is_alive():
                    print(f"[ChunkManager] WARNING: Loader worker thread {i} did not terminate in time")
        
        # Close all region file handles (releases file handles and locks)
        if hasattr(self, 'region_manager'):
            print("[ChunkManager] Closing region file handles...")
            self.region_manager.close_all_files()
        
        print("[ChunkManager] Shutdown complete")
