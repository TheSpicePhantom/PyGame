"""
Region Manager: Binary region-based chunk storage system
A region contains 5x5 chunks (25 chunks) in a single binary file

BINARY FORMAT SPECIFICATION:
============================
All multi-byte integers use BIG-ENDIAN byte order ('>' prefix in struct format).
This ensures compatibility with C/C++ tools and network protocols.

Header Structure (256 bytes):
- Offset 0x00-0x03: Magic number (4 bytes, ASCII: "R5CH")
- Offset 0x04: Version (1 byte, uint8, currently 0x01)
- Offset 0x05-0x07: Padding (3 bytes, reserved for future use)
- Offset 0x08-0x0F: Region coordinates (8 bytes, 2x int32 big-endian)
  - region_x (4 bytes, int32, big-endian)
  - region_y (4 bytes, int32, big-endian)
- Offset 0x10-0xF0: Chunk table (225 bytes, 25 entries × 9 bytes)
  Each entry (9 bytes):
    - offset (4 bytes, uint32, big-endian, always HEADER_SIZE + chunk_index * MAX_CHUNK_DATA_SIZE)
    - length (4 bytes, uint32, big-endian, actual compressed chunk size, 0 = empty slot)
    - compression (1 byte, uint8, 0=none, 1=zlib, 2=lz4)
- Offset 0xF1-0xFF: Padding (15 bytes, reserved for future use)

Chunk Slot Structure (Fixed Size, 8 KB per chunk):
- Each chunk occupies a fixed slot of MAX_CHUNK_DATA_SIZE (8192 bytes)
- Slot position: HEADER_SIZE + chunk_index * MAX_CHUNK_DATA_SIZE
- Slot format:
  - compressed_data (variable, up to MAX_CHUNK_DATA_SIZE bytes, actual size stored in header.length)
  - padding (zeros to fill remaining slot space)
- Note: The actual compressed data size is stored in the header (chunk_table entry length field),
  NOT in the slot itself. This avoids redundancy and simplifies reading.

Chunk Data (v2 - Optimized Format):
- Stored after header (offset >= 256)
- Compression: zlib (level 1) by default, or LZ4 if enabled in settings (faster decompression)
- Format:
  * int32 chunk_x, chunk_y (big-endian)
  * int32 seed (big-endian)
  * int16 width, height (15, big-endian)
  * uint8 biome_count (number of unique biomes)
  * Biome table: biome_count entries
    - uint8 biome_string_length
    - string biome_id (UTF-8)
  * Tile data: 225 tiles × 6 bytes
    - uint8 biome_index (index into biome table)
    - uint8 height (0-255)
    - uint8 flags (bit 0 = traversable)
    - uint8[3] color (r, g, b)
  * int16 entity_count (big-endian, currently 0)

Optimization Benefits:
- Biome strings stored once per chunk (not per tile)
- Each tile: 6 bytes (was 8-28+ bytes with variable-length strings)
- Removed unused tile_id_hash (saves 2 bytes per tile)
- Typical savings: 50-80% reduction in chunk size
- Better compression ratio (repeated strings compress better)

Backward Compatibility:
- Deserializer detects old format and reads it correctly
- Old chunks are automatically migrated to new format on save

FIXED SLOT SIZE & IN-PLACE WRITES:
===================================
Each chunk occupies a fixed slot of MAX_CHUNK_DATA_SIZE (8 KB).
This enables true in-place writes and eliminates fragmentation.

Slot Layout:
- Slot position: HEADER_SIZE + chunk_index * MAX_CHUNK_DATA_SIZE
- Each slot: [compressed_data][padding to MAX_CHUNK_DATA_SIZE]
- Actual compressed data size is stored in header (chunk_table entry length field)
- Compressed chunks are typically 1-3 KB, so 8 KB provides ample headroom

Benefits:
- No fragmentation: Each chunk always writes to the same position
- True in-place updates: No need to append or compact
- Predictable file size: HEADER_SIZE + (25 * MAX_CHUNK_DATA_SIZE) = ~205 KB
- Crash-safe: Header update is atomic (5-byte write)
- Fast random access: Direct seek to slot position

Backward Compatibility:
- Old region files (variable-length chunks) are automatically detected and read
- Old chunks are migrated to fixed-slot format on save
"""
import struct
import zlib
import os
import json
import threading
import time
import asyncio
from pathlib import Path
from typing import Dict, Tuple, Optional, List
from collections import OrderedDict

# Optional LZ4 compression support
try:
    import lz4.frame
    LZ4_AVAILABLE = True
    # Check if LZ4FrameError exists (it may not exist in all lz4 versions)
    try:
        LZ4FrameError = lz4.frame.LZ4FrameError
    except AttributeError:
        # Fallback: use a generic exception if LZ4FrameError doesn't exist
        LZ4FrameError = Exception
except ImportError:
    LZ4_AVAILABLE = False
    LZ4FrameError = Exception  # Dummy exception if lz4 is not available


# Custom Exceptions for RegionManager
class RegionManagerError(Exception):
    """Base exception for RegionManager errors"""
    pass


class ChunkNotFoundError(RegionManagerError):
    """Raised when a chunk doesn't exist"""
    pass


class ChunkCorruptedError(RegionManagerError):
    """Raised when chunk data is corrupted or invalid"""
    pass


class SeedMismatchError(RegionManagerError):
    """Raised when chunk seed doesn't match expected seed"""
    pass


class RegionFileError(RegionManagerError):
    """Raised when region file operations fail"""
    pass


class _NoOpContext:
    """Context manager that does nothing (for when lock is already held)"""
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


from core import settings


class RegionManager:
    """Manages binary region files (5x5 chunks per region)"""
    
    # Magic number for region files
    REGION_MAGIC = b"R5CH"  # Region 5x5 Chunks
    REGION_VERSION = 0x01
    
    # Region dimensions (5x5 chunks)
    REGION_SIZE_CHUNKS = 5
    CHUNKS_PER_REGION = REGION_SIZE_CHUNKS * REGION_SIZE_CHUNKS  # 25
    
    # Header structure
    HEADER_SIZE = 256
    CHUNK_TABLE_OFFSET = 16
    # Chunk table entry: 9 bytes (4 bytes offset + 4 bytes length + 1 byte compression)
    # Offset is always HEADER_SIZE + chunk_index * MAX_CHUNK_DATA_SIZE (fixed slot position)
    # Length is actual compressed data size (0 = slot exists but chunk is empty/unsaved)
    CHUNK_TABLE_ENTRY_SIZE = 9  # 4 bytes offset + 4 bytes length + 1 byte compression
    CHUNK_TABLE_SIZE = CHUNKS_PER_REGION * CHUNK_TABLE_ENTRY_SIZE  # 225 bytes
    
    # Compression types
    COMPRESSION_NONE = 0
    COMPRESSION_ZLIB = 1
    COMPRESSION_LZ4 = 2
    
    # Fixed chunk slot size (8 KB per chunk)
    # This enables true in-place writes and eliminates fragmentation
    # Compressed chunks are typically 1-3 KB, so 8 KB provides ample headroom
    MAX_CHUNK_DATA_SIZE = 8192  # 8 KB
    
    # Maximum number of open region files (LRU cache)
    # Increased from 64 to 128 to reduce file open/close overhead
    # Each region file is ~5-50KB, so 128 files = ~6.4MB memory (acceptable)
    MAX_OPEN_REGIONS = 128
    
    def __init__(self, world_name: str, auto_repair_corrupted: bool = False, backup_corrupted: bool = True, diagnostics=None, performance_monitor=None):
        """
        Initialize RegionManager for a specific world
        
        Args:
            world_name: World name (will be sanitized for use as directory name)
            auto_repair_corrupted: If True, automatically create new headers for corrupted files.
                                   If False, rename corrupted files to .corrupt and skip them.
            backup_corrupted: If True, rename corrupted files to .corrupt instead of overwriting.
                              Only used if auto_repair_corrupted is True.
            diagnostics: Optional DiagnosticsService instance for logging
            performance_monitor: Optional PerformanceMonitor instance for tracking disk I/O
        """
        from world.world_utils import get_world_save_dir
        from core import settings
        
        # Compression level (1-9, default 6 for balance between speed and size)
        self.compression_level = getattr(settings, 'CHUNK_COMPRESSION_LEVEL', 6)
        self.world_name = world_name
        self.auto_repair_corrupted = auto_repair_corrupted
        self.backup_corrupted = backup_corrupted
        self.diagnostics = diagnostics
        self.performance_monitor = performance_monitor
        self.save_dir = get_world_save_dir(world_name)
        self.regions_dir = self.save_dir / "regions"
        self.regions_dir.mkdir(parents=True, exist_ok=True)
        
        # Determine compression type based on settings
        compression_setting = getattr(settings, 'CHUNK_COMPRESSION', 'zlib')
        lz4_available = getattr(settings, 'LZ4_AVAILABLE', False)
        
        if compression_setting == "lz4" and lz4_available:
            self.compression_type = self.COMPRESSION_LZ4
        else:
            self.compression_type = self.COMPRESSION_ZLIB
        
        # Thread-safety: RLock (reentrant lock) per region for concurrent access
        # This allows parallel chunk loading/saving from different regions
        # RLock allows the same thread to acquire the lock multiple times (reentrant)
        self._region_locks: Dict[Tuple[int, int], threading.RLock] = {}
        self._locks_lock = threading.Lock()  # Lock for managing region locks
        
        # LRU Cache for open region file handles: OrderedDict[(region_x, region_y), file_handle]
        # OrderedDict maintains insertion order, oldest items are at the beginning
        # Thread-safe: protected by region locks
        self.region_files: OrderedDict[Tuple[int, int], object] = OrderedDict()
        
        # Cache for region headers: Dict[(region_x, region_y), header_dict]
        # This avoids reading headers repeatedly for load_chunk, chunk_exists, save_chunk
        # Thread-safe: protected by region locks
        self.region_headers: Dict[Tuple[int, int], Dict] = {}
        
        # Background compaction: Track region access and fragmentation
        self._region_access_times: Dict[Tuple[int, int], float] = {}  # Last access time per region
        self._region_access_lock = threading.Lock()  # Lock for access tracking
        self._compaction_running = False
        self._compaction_task: Optional[asyncio.Task] = None
        self._shutdown_event: Optional[asyncio.Event] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Check if compaction is enabled (before trying to start it)
        from core import settings
        self._compaction_enabled = getattr(settings, 'REGION_COMPACTION_ENABLED', True)
        
        # Start background compaction if enabled (will be started when event loop is available)
        # Note: We don't start it here because we need an event loop, which might not exist yet
        # It will be started later when needed, or we can start it here if event loop exists
        if self._compaction_enabled:
            try:
                # Try to get event loop, if it exists, start compaction
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Event loop is running, start compaction
                    self.start_background_compaction()
            except RuntimeError:
                # No event loop in current thread, skip for now
                # Compaction will be started later when event loop is available
                pass
    
    def _get_region_lock(self, region_x: int, region_y: int) -> threading.RLock:
        """
        Get or create a reentrant lock for a specific region (thread-safe)
        
        Args:
            region_x: Region X coordinate
            region_y: Region Y coordinate
        
        Returns:
            RLock for this region (reentrant - same thread can acquire multiple times)
        """
        cache_key = (region_x, region_y)
        
        # Fast path: check if lock exists (without acquiring locks_lock)
        if cache_key in self._region_locks:
            return self._region_locks[cache_key]
        
        # Slow path: create lock if it doesn't exist
        with self._locks_lock:
            # Double-check after acquiring lock
            if cache_key not in self._region_locks:
                self._region_locks[cache_key] = threading.RLock()
            return self._region_locks[cache_key]
    
    def _get_region_coords(self, chunk_x: int, chunk_y: int) -> Tuple[int, int]:
        """Convert chunk coordinates to region coordinates"""
        region_x = chunk_x // self.REGION_SIZE_CHUNKS
        region_y = chunk_y // self.REGION_SIZE_CHUNKS
        return region_x, region_y
    
    def _get_local_chunk_coords(self, chunk_x: int, chunk_y: int) -> Tuple[int, int]:
        """Convert global chunk coordinates to local coordinates within region"""
        local_x = chunk_x % self.REGION_SIZE_CHUNKS
        local_y = chunk_y % self.REGION_SIZE_CHUNKS
        return local_x, local_y
    
    def _get_chunk_index(self, local_x: int, local_y: int) -> int:
        """Get chunk index in region table (0-24)"""
        return local_y * self.REGION_SIZE_CHUNKS + local_x
    
    def _get_region_filename(self, region_x: int, region_y: int) -> Path:
        """Get filename for a region"""
        return self.regions_dir / f"r.{region_x}.{region_y}.mcr"
    
    def _create_new_region_file(self, region_x: int, region_y: int) -> bool:
        """
        Create a new region file with valid header structure.
        
        Builds the complete header in a buffer and writes it atomically.
        Only writes the header (256 bytes), slots are not pre-initialized.
        
        Args:
            region_x: Region X coordinate
            region_y: Region Y coordinate
        
        Returns:
            True if successful, False otherwise
        """
        region_file = self._get_region_filename(region_x, region_y)
        
        try:
            # Build header structure in buffer
            header_buffer = bytearray(self.HEADER_SIZE)
            
            # Magic: b"R5CH" at offset 0
            header_buffer[0:4] = self.REGION_MAGIC
            
            # Version: REGION_VERSION at byte 4
            header_buffer[4] = self.REGION_VERSION
            
            # Padding 0x05-0x07 = 0 (already zero-initialized)
            
            # Region coordinates (x, y) at bytes 8-15
            coords_bytes = struct.pack('>ii', region_x, region_y)
            header_buffer[8:16] = coords_bytes
            
            # Chunk table (25 entries) starting at CHUNK_TABLE_OFFSET
            table_offset = self.CHUNK_TABLE_OFFSET
            for i in range(self.CHUNKS_PER_REGION):
                slot_offset = self.HEADER_SIZE + i * self.MAX_CHUNK_DATA_SIZE
                # Pack: offset (4 bytes) + length (4 bytes, 0) + compression (1 byte, 0)
                entry_bytes = struct.pack('>IIB', slot_offset, 0, 0)
                entry_start = table_offset + i * self.CHUNK_TABLE_ENTRY_SIZE
                header_buffer[entry_start:entry_start + self.CHUNK_TABLE_ENTRY_SIZE] = entry_bytes
            
            # Write header atomically (w+b truncates existing file)
            with open(region_file, 'w+b') as f:
                f.write(header_buffer)
                f.flush()  # Ensure data is written to OS buffer
                os.fsync(f.fileno())  # Force write to disk (crash protection)
            
            # Update cache with empty header
            cache_key = (region_x, region_y)
            region_lock = self._get_region_lock(region_x, region_y)
            with region_lock:
                chunk_table = []
                for i in range(self.CHUNKS_PER_REGION):
                    slot_offset = self.HEADER_SIZE + i * self.MAX_CHUNK_DATA_SIZE
                    chunk_table.append({
                        'offset': slot_offset,
                        'length': 0,  # Empty slot
                        'compression': 0
                    })
                self.region_headers[cache_key] = {
                    'region_x': region_x,
                    'region_y': region_y,
                    'chunk_table': chunk_table
                }
            
            return True
        except Exception as e:
            if self.diagnostics:
                self.diagnostics.error("RegionManager",
                    f"Failed to create new region file ({region_x}, {region_y}): {e}")
            else:
                print(f"[RegionManager] Failed to create new region file ({region_x}, {region_y}): {e}")
            return False
    
    async def _initialize_region_file(self, region_x: int, region_y: int):
        """
        Initialize a new region file with empty header (all slots marked as empty).
        This prevents empty header errors when chunks are saved.
        
        Args:
            region_x: Region X coordinate
            region_y: Region Y coordinate
        """
        region_file = self._get_region_filename(region_x, region_y)
        
        # Create directory if needed
        region_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Use existing _create_new_region_file method (run in thread pool for async)
        result = await asyncio.to_thread(self._create_new_region_file, region_x, region_y)
        
        if not result:
            raise RegionFileError(f"Failed to initialize region file ({region_x}, {region_y})")
    
    def _get_region_file_handle(self, region_x: int, region_y: int, create_if_missing: bool = False, _lock_held: bool = False) -> Optional[object]:
        """
        Get or open a region file handle (with LRU caching, thread-safe)
        
        Args:
            region_x: Region X coordinate
            region_y: Region Y coordinate
            create_if_missing: If True, create file if it doesn't exist
            _lock_held: Internal flag - if True, assumes caller already holds region lock
        
        Returns:
            File handle in r+b mode, or None if file doesn't exist and create_if_missing is False
        
        Note: This method is thread-safe per region. Different regions can be accessed concurrently.
        """
        cache_key = (region_x, region_y)
        region_lock = self._get_region_lock(region_x, region_y)
        region_file = self._get_region_filename(region_x, region_y)
        
        # Use context manager only if lock not already held
        if _lock_held:
            lock_context = _NoOpContext()
        else:
            lock_context = region_lock
        
        with lock_context:
            # Check if already open
            if cache_key in self.region_files:
                # Move to end (mark as recently used)
                handle = self.region_files.pop(cache_key)
                self.region_files[cache_key] = handle
                # Track access time for compaction prioritization
                with self._region_access_lock:
                    self._region_access_times[cache_key] = time.time()
                return handle
            
            # Check if file exists
            if not region_file.exists():
                if create_if_missing:
                    # Create new region file with valid header
                    # After _create_new_region_file, the file always has a valid header
                    if not self._create_new_region_file(region_x, region_y):
                        return None  # Failed to create file
                    # File now exists with valid header, continue to open it
                else:
                    return None
            
            # At this point, file exists and has a valid header (either pre-existing or just created)
            # Open file (use buffering for better performance)
            try:
                # Use buffered I/O (8KB buffer) for better performance
                # This reduces system calls and improves read/write performance
                # Buffering helps especially when reading multiple chunks from same region
                handle = open(region_file, 'r+b', buffering=8192)  # 8KB buffer
            except Exception as e:
                print(f"[RegionManager] Error opening region file ({region_x}, {region_y}): {e}")
                return None
            
            # Add to cache (at end = most recently used)
            self.region_files[cache_key] = handle
            # Track access time for compaction prioritization
            with self._region_access_lock:
                self._region_access_times[cache_key] = time.time()
            
            # Evict oldest if cache is full (need to acquire locks_lock for this)
            if len(self.region_files) > self.MAX_OPEN_REGIONS:
                # Remove oldest (first item)
                oldest_key, oldest_handle = self.region_files.popitem(last=False)
                try:
                    oldest_handle.close()
                    # Also remove header cache for closed region (optional optimization)
                    # This prevents stale cache entries
                    self.region_headers.pop(oldest_key, None)
                except Exception:
                    pass
            
            return handle
    
    def _close_region_file(self, region_x: int, region_y: int):
        """
        Close a specific region file handle (thread-safe)
        
        Args:
            region_x: Region X coordinate
            region_y: Region Y coordinate
        """
        cache_key = (region_x, region_y)
        region_lock = self._get_region_lock(region_x, region_y)
        
        with region_lock:
            if cache_key in self.region_files:
                handle = self.region_files.pop(cache_key)
                try:
                    handle.close()
                except Exception:
                    pass
    
    def close_all_files(self):
        """Close all open region file handles (for shutdown, thread-safe)"""
        # Stop background compaction (async)
        self.stop_background_compaction()
        
        # Wait for compaction task to finish if running
        if self._compaction_task and not self._compaction_task.done():
            try:
                if self._event_loop and self._event_loop.is_running():
                    # Schedule task cancellation
                    self._event_loop.call_soon_threadsafe(self._compaction_task.cancel)
                else:
                    self._compaction_task.cancel()
            except Exception:
                pass
        
        # Acquire all locks to ensure no operations are in progress
        with self._locks_lock:
            locks_to_acquire = list(self._region_locks.values())
        
        # Acquire all region locks (in order to avoid deadlock)
        for lock in locks_to_acquire:
            lock.acquire()
        
        try:
            for cache_key, handle in list(self.region_files.items()):
                try:
                    handle.close()
                except Exception:
                    pass
            self.region_files.clear()
        finally:
            # Release all locks
            for lock in locks_to_acquire:
                lock.release()
    
    def _is_old_write_once_format(self, region_x: int, region_y: int) -> bool:
        """
        Check if a region file uses the old write-once format (variable offsets).
        
        Returns:
            True if region uses old format (needs migration), False if already migrated to fixed slots.
        """
        region_file = self._get_region_filename(region_x, region_y)
        
        if not region_file.exists():
            return False  # New file, not old format
        
        try:
            header = self._read_region_header(region_file, region_x, region_y)
            if not header:
                return False
            
            chunk_table = header['chunk_table']
            
            # Check if any chunk uses non-fixed offsets
            # Fixed slots: offset = HEADER_SIZE + chunk_index * MAX_CHUNK_DATA_SIZE
            for i, entry in enumerate(chunk_table):
                if entry['offset'] > 0:
                    expected_offset = self.HEADER_SIZE + i * self.MAX_CHUNK_DATA_SIZE
                    if entry['offset'] != expected_offset:
                        # This chunk is not at its fixed slot position - old format
                        return True
            
            # All chunks are at fixed positions - already migrated
            return False
        except Exception:
            return False  # On error, assume not old format
    
    def _calculate_fragmentation(self, region_x: int, region_y: int) -> Optional[float]:
        """
        Calculate fragmentation ratio for a region file (only for old write-once format).
        
        Returns:
            Fragmentation ratio (actual_size / minimum_size), or None if region doesn't exist, is invalid, or uses fixed slots.
            Ratio > 1.0 indicates fragmentation (e.g., 1.5 = 50% waste).
        """
        # Only calculate fragmentation for old write-once format
        if not self._is_old_write_once_format(region_x, region_y):
            return None  # Fixed slots don't fragment
        
        region_file = self._get_region_filename(region_x, region_y)
        
        if not region_file.exists():
            return None
        
        try:
            # Get actual file size
            actual_size = region_file.stat().st_size
            
            # Read header to calculate minimum size
            header = self._read_region_header(region_file, region_x, region_y)
            if not header:
                return None
            
            chunk_table = header['chunk_table']
            
            # Calculate minimum size: header + sum of all chunk lengths
            min_size = self.HEADER_SIZE
            for entry in chunk_table:
                if entry['offset'] > 0:
                    min_size += entry['length']
            
            if min_size == 0:
                return None  # Empty region
            
            return actual_size / min_size
        except Exception:
            return None
    
    def _find_fragmented_regions(self) -> List[Tuple[int, int, float]]:
        """
        Find regions that are fragmented and eligible for compaction.
        Only finds old write-once format regions (fixed-slot regions don't fragment).
        
        Returns:
            List of (region_x, region_y, fragmentation_ratio) tuples, sorted by fragmentation (highest first).
        """
        from core import settings
        
        if not getattr(settings, 'REGION_COMPACTION_ENABLED', True):
            return []
        
        min_fragmentation = getattr(settings, 'REGION_COMPACTION_MIN_FRAGMENTATION', 1.5)
        min_idle_sec = getattr(settings, 'REGION_COMPACTION_MIN_IDLE_SEC', 60.0)
        
        fragmented_regions = []
        current_time = time.time()
        
        # Scan all region files
        if not self.regions_dir.exists():
            return []
        
        for region_file in self.regions_dir.glob("r.*.mcr"):
            try:
                # Extract region coordinates from filename
                parts = region_file.stem.split('.')
                if len(parts) < 3 or parts[0] != 'r':
                    continue
                
                region_x = int(parts[1])
                region_y = int(parts[2])
                cache_key = (region_x, region_y)
                
                # Only process old write-once format regions
                if not self._is_old_write_once_format(region_x, region_y):
                    continue  # Skip fixed-slot regions (they don't fragment)
                
                # Check if region was accessed recently (skip active regions)
                with self._region_access_lock:
                    last_access = self._region_access_times.get(cache_key, 0)
                
                # Also check file mtime as fallback
                file_mtime = region_file.stat().st_mtime
                time_since_access = current_time - max(last_access, file_mtime)
                
                if time_since_access < min_idle_sec:
                    continue  # Region was accessed recently, skip
                
                # Calculate fragmentation
                fragmentation = self._calculate_fragmentation(region_x, region_y)
                if fragmentation is None or fragmentation < min_fragmentation:
                    continue  # Not fragmented enough
                
                fragmented_regions.append((region_x, region_y, fragmentation))
            except (ValueError, IndexError, OSError):
                continue  # Skip invalid files
        
        # Sort by fragmentation (highest first)
        fragmented_regions.sort(key=lambda x: x[2], reverse=True)
        return fragmented_regions
    
    async def _background_compaction_worker(self):
        """Background async task that periodically compacts fragmented regions."""
        from core import settings
        
        interval = getattr(settings, 'REGION_COMPACTION_INTERVAL_SEC', 300.0)
        max_per_cycle = getattr(settings, 'REGION_COMPACTION_MAX_PER_CYCLE', 3)
        
        if self.diagnostics:
            self.diagnostics.info("RegionManager", f"Background compaction task started (interval={interval}s)")
        
        while not self._shutdown_event.is_set():
            try:
                # Wait for interval or shutdown signal
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=interval)
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    pass  # Interval elapsed, continue with compaction
                
                # Find fragmented regions (sync operation, run in thread pool)
                fragmented = await asyncio.to_thread(self._find_fragmented_regions)
                
                if not fragmented:
                    continue  # No regions to compact
                
                # Compact up to max_per_cycle regions (sync operation, run in thread pool)
                compacted = 0
                for region_x, region_y, fragmentation_ratio in fragmented[:max_per_cycle]:
                    if self._shutdown_event.is_set():
                        break
                    
                    try:
                        # Run sync compact_region in thread pool
                        success = await asyncio.to_thread(self.compact_region, region_x, region_y)
                        if success:
                            compacted += 1
                            if self.diagnostics:
                                self.diagnostics.debug("RegionManager", 
                                    f"Background compaction: Region ({region_x}, {region_y}) "
                                    f"compacted (fragmentation was {fragmentation_ratio:.2f}x)")
                    except Exception as e:
                        if self.diagnostics:
                            self.diagnostics.warning("RegionManager", 
                                f"Background compaction failed for region ({region_x}, {region_y}): {e}")
                
                if compacted > 0 and self.diagnostics:
                    self.diagnostics.info("RegionManager", 
                        f"Background compaction cycle completed: {compacted} regions compacted")
                    
            except Exception as e:
                if self.diagnostics:
                    self.diagnostics.error("RegionManager", f"Background compaction task error: {e}")
                # Continue running despite errors
        
        if self.diagnostics:
            self.diagnostics.info("RegionManager", "Background compaction task stopped")
    
    def start_background_compaction(self):
        """Start the background compaction async task."""
        # Check if compaction is enabled (attribute might not exist in old code)
        if not getattr(self, '_compaction_enabled', True):
            return
        
        if self._compaction_running:
            return  # Already running
        
        # Get or create event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # No event loop in current thread, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        self._event_loop = loop
        self._compaction_running = True
        
        # Create shutdown event if it doesn't exist
        if self._shutdown_event is None:
            self._shutdown_event = asyncio.Event()
        else:
            self._shutdown_event.clear()
        
        # Create async task
        self._compaction_task = loop.create_task(self._background_compaction_worker())
    
    def stop_background_compaction(self):
        """Stop the background compaction async task."""
        if not self._compaction_running:
            return
        
        self._compaction_running = False
        
        if self._shutdown_event:
            # Set shutdown event (async)
            if self._event_loop and self._event_loop.is_running():
                self._event_loop.call_soon_threadsafe(self._shutdown_event.set)
            else:
                self._shutdown_event.set()
        
        if self._compaction_task and not self._compaction_task.done():
            # Cancel task
            if self._event_loop and self._event_loop.is_running():
                self._event_loop.call_soon_threadsafe(self._compaction_task.cancel)
            else:
                self._compaction_task.cancel()
    
    def invalidate_header_cache(self, region_x: int = None, region_y: int = None):
        """
        Invalidate header cache for a specific region or all regions (thread-safe)
        
        Args:
            region_x: Optional region X coordinate (if None, clears all cache)
            region_y: Optional region Y coordinate (if None, clears all cache)
        """
        if region_x is not None and region_y is not None:
            cache_key = (region_x, region_y)
            region_lock = self._get_region_lock(region_x, region_y)
            with region_lock:
                self.region_headers.pop(cache_key, None)
        else:
            # Clear all cache - need to acquire all locks
            with self._locks_lock:
                locks_to_acquire = list(self._region_locks.values())
            
            for lock in locks_to_acquire:
                lock.acquire()
            try:
                self.region_headers.clear()
            finally:
                for lock in locks_to_acquire:
                    lock.release()
    
    def _backup_corrupted_file(self, file_path: Path, region_x: int, region_y: int, error_type: str, error_details: str):
        """
        Backup a corrupted region file as text/hex dump for analysis.
        
        Creates two files:
        1. .corrupt.hex - Hex dump of the file (readable text format)
        2. .corrupt.info - JSON file with metadata and error information
        
        Args:
            file_path: Path to corrupted file
            region_x: Region X coordinate
            region_y: Region Y coordinate
            error_type: Type of error (e.g., "InvalidMagic", "UnsupportedVersion", "ReadError")
            error_details: Detailed error message
        """
        try:
            # Close handle if open
            self._close_region_file(region_x, region_y)
            
            # Create backup filenames with timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            hex_backup_path = file_path.parent / f"{file_path.stem}.corrupt.{timestamp}.hex"
            info_backup_path = file_path.parent / f"{file_path.stem}.corrupt.{timestamp}.info"
            
            # Read file content for hex dump
            file_size = file_path.stat().st_size if file_path.exists() else 0
            file_content = None
            header_bytes = None
            first_256_bytes = None
            
            if file_path.exists():
                try:
                    with open(file_path, 'rb') as f:
                        file_content = f.read()
                        header_bytes = file_content[:self.HEADER_SIZE] if len(file_content) >= self.HEADER_SIZE else file_content
                        first_256_bytes = file_content[:256] if len(file_content) >= 256 else file_content
                except Exception as e:
                    if self.diagnostics:
                        self.diagnostics.warning("RegionManager",
                            f"Could not read corrupted file for backup: {e}")
            
            # Write hex dump (text format)
            with open(hex_backup_path, 'w', encoding='utf-8') as f:
                f.write(f"Corrupted Region File Hex Dump\n")
                f.write(f"{'=' * 80}\n")
                f.write(f"World: {self.world_name}\n")
                f.write(f"Region: ({region_x}, {region_y})\n")
                f.write(f"Original File: {file_path.name}\n")
                f.write(f"File Size: {file_size} bytes\n")
                f.write(f"Error Type: {error_type}\n")
                f.write(f"Error Details: {error_details}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"{'=' * 80}\n\n")
                
                if file_content:
                    # Write hex dump (16 bytes per line)
                    f.write("Hex Dump:\n")
                    f.write(f"{'Offset':<10} {'Hex':<48} {'ASCII':<16}\n")
                    f.write("-" * 80 + "\n")
                    
                    for i in range(0, len(file_content), 16):
                        chunk = file_content[i:i+16]
                        hex_str = ' '.join(f'{b:02x}' for b in chunk)
                        # Pad hex string to 48 chars (16 bytes * 3 chars)
                        hex_str = hex_str.ljust(48)
                        
                        # ASCII representation (replace non-printable with '.')
                        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
                        
                        f.write(f"{i:08x}   {hex_str}   {ascii_str}\n")
                    
                    # Write header analysis
                    if header_bytes:
                        f.write(f"\n{'=' * 80}\n")
                        f.write("Header Analysis (first 256 bytes):\n")
                        f.write(f"{'=' * 80}\n")
                        
                        # Magic number
                        if len(header_bytes) >= 4:
                            magic = header_bytes[0:4]
                            f.write(f"Magic (bytes 0-3): {magic.hex()} = {magic}\n")
                            expected_magic = self.REGION_MAGIC
                            if magic != expected_magic:
                                f.write(f"  Expected: {expected_magic.hex()} = {expected_magic}\n")
                                f.write(f"  MISMATCH!\n")
                        
                        # Version
                        if len(header_bytes) >= 5:
                            version = header_bytes[4]
                            f.write(f"Version (byte 4): {version:02x} = {version}\n")
                            f.write(f"  Expected: {self.REGION_VERSION:02x} = {self.REGION_VERSION}\n")
                            if version != self.REGION_VERSION:
                                f.write(f"  MISMATCH!\n")
                        
                        # Region coordinates
                        if len(header_bytes) >= 16:
                            try:
                                region_x_read, region_y_read = struct.unpack('>ii', header_bytes[8:16])
                                f.write(f"Region Coords (bytes 8-15): x={region_x_read}, y={region_y_read}\n")
                                f.write(f"  Expected: x={region_x}, y={region_y}\n")
                                if region_x_read != region_x or region_y_read != region_y:
                                    f.write(f"  MISMATCH!\n")
                            except struct.error:
                                f.write(f"Region Coords (bytes 8-15): Could not parse\n")
                        
                        # Chunk table preview
                        if len(header_bytes) >= self.CHUNK_TABLE_OFFSET + 9:
                            f.write(f"\nChunk Table Preview (first entry, bytes {self.CHUNK_TABLE_OFFSET}-{self.CHUNK_TABLE_OFFSET + 8}):\n")
                            try:
                                offset, length, comp = struct.unpack('>IIB', header_bytes[self.CHUNK_TABLE_OFFSET:self.CHUNK_TABLE_OFFSET + 9])
                                f.write(f"  Offset: {offset} (0x{offset:08x})\n")
                                f.write(f"  Length: {length} (0x{length:08x})\n")
                                f.write(f"  Compression: {comp}\n")
                            except struct.error:
                                f.write(f"  Could not parse chunk table entry\n")
                else:
                    f.write("Could not read file content.\n")
            
            # Write metadata JSON file
            metadata = {
                'world_name': self.world_name,
                'region_x': region_x,
                'region_y': region_y,
                'original_filename': file_path.name,
                'file_size': file_size,
                'error_type': error_type,
                'error_details': error_details,
                'timestamp': datetime.now().isoformat(),
                'header_info': {}
            }
            
            if header_bytes:
                metadata['header_info'] = {
                    'magic': header_bytes[0:4].hex() if len(header_bytes) >= 4 else None,
                    'expected_magic': self.REGION_MAGIC.hex(),
                    'version': header_bytes[4] if len(header_bytes) >= 5 else None,
                    'expected_version': self.REGION_VERSION,
                    'header_size': len(header_bytes),
                    'first_256_bytes_hex': first_256_bytes.hex() if first_256_bytes else None
                }
            
            with open(info_backup_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            # Rename original file to .corrupt (keep binary copy for reference)
            # After backup, the original file is removed so that on next access,
            # either a new header is created (auto_repair_corrupted=True) or the region is regenerated
            binary_backup_path = file_path.parent / f"{file_path.stem}.corrupt.{timestamp}.bin"
            file_backed_up = False
            if file_path.exists():
                try:
                    # Use os.replace for atomic rename (works on all platforms)
                    os.replace(file_path, binary_backup_path)
                    file_backed_up = True
                except Exception as e:
                    # If rename fails, try regular rename as fallback
                    try:
                        file_path.rename(binary_backup_path)
                        file_backed_up = True
                    except Exception:
                        # If both fail, try to delete the corrupted file to unblock access
                        if self.diagnostics:
                            self.diagnostics.warning("RegionManager",
                                f"Failed to backup corrupted file {file_path}, attempting to delete: {e}")
                        try:
                            file_path.unlink()
                            file_backed_up = True
                        except Exception:
                            pass  # Give up if deletion also fails
            
            # Invalidate cache for this region so it will be recreated on next access
            if file_backed_up and region_x is not None and region_y is not None:
                cache_key = (region_x, region_y)
                self.invalidate_header_cache(region_x, region_y)
                # Also close file handle if open
                self._close_region_file(region_x, region_y)
            
            if self.diagnostics:
                self.diagnostics.warning("RegionManager",
                    f"CORRUPTED FILE BACKUP: World '{self.world_name}', Region ({region_x}, {region_y})\n"
                    f"  Error Type: {error_type}\n"
                    f"  Error Details: {error_details}\n"
                    f"  Hex Dump: {hex_backup_path.name}\n"
                    f"  Metadata: {info_backup_path.name}\n"
                    f"  Binary: {binary_backup_path.name}")
            else:
                print(f"[RegionManager] CORRUPTED FILE BACKUP: World '{self.world_name}', Region ({region_x}, {region_y})")
                print(f"  Error Type: {error_type}")
                print(f"  Error Details: {error_details}")
                print(f"  Hex Dump: {hex_backup_path.name}")
                print(f"  Metadata: {info_backup_path.name}")
                print(f"  Binary: {binary_backup_path.name}")
        except Exception as e:
            error_msg = f"Failed to backup corrupted file {file_path}: {e}"
            if self.diagnostics:
                self.diagnostics.error("RegionManager", error_msg)
            else:
                print(f"[RegionManager] {error_msg}")
            import traceback
            traceback.print_exc()
    
    def _read_region_header(self, file_path: Path, region_x: int = None, region_y: int = None) -> Optional[Dict]:
        """
        Read and parse region file header (with caching and corruption handling)
        
        Args:
            file_path: Path to region file
            region_x: Optional region X coordinate (for cache lookup)
            region_y: Optional region Y coordinate (for cache lookup)
        
        Returns:
            Header dictionary or None if file doesn't exist or is corrupted
        """
        if not file_path.exists():
            return None
        
        # Try to get region coords from file path if not provided
        if region_x is None or region_y is None:
            # Extract from filename: r.X.Y.mcr
            try:
                parts = file_path.stem.split('.')
                if len(parts) >= 3 and parts[0] == 'r':
                    region_x = int(parts[1])
                    region_y = int(parts[2])
            except (ValueError, IndexError):
                pass
        
        # Thread-safe cache check and read
        if region_x is not None and region_y is not None:
            cache_key = (region_x, region_y)
            region_lock = self._get_region_lock(region_x, region_y)
            
            # Check if we're already inside a lock (for nested calls)
            # This is a simple check - in a real implementation, we'd use threading.current_thread()
            # For now, we'll always acquire the lock (caller should avoid nested calls)
            with region_lock:
                # Check cache first (within lock)
                if cache_key in self.region_headers:
                    return self.region_headers[cache_key]
                
                # Use cached file handle if available (lock already held)
                f = self._get_region_file_handle(region_x, region_y, create_if_missing=False, _lock_held=True)
                if f is None:
                    return None
                use_cached_handle = True
        else:
            # Fallback to opening file directly if coords not available
            if not file_path.exists():
                return None
            try:
                f = open(file_path, 'rb')
                use_cached_handle = False
            except Exception as e:
                error_msg = f"World '{self.world_name}', Region ({region_x}, {region_y}): Failed to open file - {type(e).__name__}: {e}"
                print(f"[RegionManager] {error_msg}")
                return None
        
        try:
            # Read magic number
            f.seek(0)
            magic = f.read(4)
            
            # Special case: Uninitialized header (all zeros) with correct file size
            # This likely means the file was created but header write was interrupted
            if magic == b'\x00\x00\x00\x00':
                # Check file size to confirm this is likely an uninitialized file
                file_size = file_path.stat().st_size
                expected_size = self.HEADER_SIZE + (self.CHUNKS_PER_REGION * self.MAX_CHUNK_DATA_SIZE)
                
                if file_size == expected_size or file_size == self.HEADER_SIZE:
                    # This is likely an uninitialized file - reinitialize instead of treating as corrupt
                    if self.diagnostics:
                        self.diagnostics.warning("RegionManager",
                            f"Uninitialized region header detected for ({region_x}, {region_y}), "
                            f"reinitializing (file_size={file_size} bytes)")
                    else:
                        print(f"[RegionManager] Uninitialized region header detected for ({region_x}, {region_y}), reinitializing")
                    
                    if not use_cached_handle:
                        f.close()
                    
                    # Reinitialize the file with a fresh header
                    if self._create_new_region_file(region_x, region_y):
                        # Retry reading header after reinitialization
                        # Close current handle and reopen to ensure we read fresh data
                        if use_cached_handle:
                            # Invalidate cache and reopen
                            self._close_region_file(region_x, region_y)
                            f = self._get_region_file_handle(region_x, region_y, create_if_missing=False, _lock_held=True)
                            if f is None:
                                return None
                        else:
                            f.close()
                            f = open(file_path, 'rb')
                        
                        # Re-read magic (should now be valid)
                        f.seek(0)
                        magic = f.read(4)
                        # Continue with normal header reading below
                    else:
                        # Failed to reinitialize - treat as corrupt
                        error_type = "UninitializedHeader"
                        error_details = f"File exists but header is uninitialized (all zeros) and reinitialization failed"
                        error_msg = f"World '{self.world_name}', Region ({region_x}, {region_y}): {error_type} - {error_details}"
                        print(f"[RegionManager] CORRUPTED HEADER: {error_msg}")
                        
                        if not use_cached_handle:
                            f.close()
                        
                        if self.backup_corrupted and region_x is not None and region_y is not None:
                            self._backup_corrupted_file(file_path, region_x, region_y, error_type, error_details)
                        
                        return None
                else:
                    # Wrong file size - treat as corrupt
                    error_type = "InvalidMagic"
                    error_details = f"Expected '{self.REGION_MAGIC.decode('ascii', errors='replace')}', got all zeros, but file size ({file_size}) doesn't match expected size ({expected_size})"
                    error_msg = f"World '{self.world_name}', Region ({region_x}, {region_y}): {error_type} - {error_details}"
                    print(f"[RegionManager] CORRUPTED HEADER: {error_msg}")
                    
                    if not use_cached_handle:
                        f.close()
                    
                    if self.backup_corrupted and region_x is not None and region_y is not None:
                        self._backup_corrupted_file(file_path, region_x, region_y, error_type, error_details)
                    
                    return None
            
            # Normal case: Check if magic matches expected value
            if magic != self.REGION_MAGIC:
                error_type = "InvalidMagic"
                error_details = f"Expected '{self.REGION_MAGIC.decode('ascii', errors='replace')}', got '{magic.decode('ascii', errors='replace')}'"
                error_msg = f"World '{self.world_name}', Region ({region_x}, {region_y}): {error_type} - {error_details}"
                print(f"[RegionManager] CORRUPTED HEADER: {error_msg}")
                
                if not use_cached_handle:
                    f.close()
                
                # Handle corruption
                if self.backup_corrupted and region_x is not None and region_y is not None:
                    self._backup_corrupted_file(file_path, region_x, region_y, error_type, error_details)
                
                return None
            
            # Read version
            version = struct.unpack('B', f.read(1))[0]
            if version != self.REGION_VERSION:
                error_type = "UnsupportedVersion"
                error_details = f"Expected version {self.REGION_VERSION}, got {version}"
                error_msg = f"World '{self.world_name}', Region ({region_x}, {region_y}): {error_type} - {error_details}"
                print(f"[RegionManager] CORRUPTED HEADER: {error_msg}")
                
                if not use_cached_handle:
                    f.close()
                
                # Handle corruption
                if self.backup_corrupted and region_x is not None and region_y is not None:
                    self._backup_corrupted_file(file_path, region_x, region_y, error_type, error_details)
                
                return None
            
            # Skip padding
            f.read(3)
            
            # Read region coordinates
            region_x_read, region_y_read = struct.unpack('>ii', f.read(8))
            
            # Use read coordinates if not provided
            if region_x is None:
                region_x = region_x_read
            if region_y is None:
                region_y = region_y_read
            
            # Read chunk table (always 9 bytes per entry: offset + length + compression)
            chunk_table = []
            for i in range(self.CHUNKS_PER_REGION):
                try:
                    offset, length, comp = struct.unpack('>IIB', f.read(9))
                    chunk_table.append({
                        'offset': offset,
                        'length': length,  # Actual compressed data size (0 = empty slot)
                        'compression': comp
                    })
                except struct.error:
                    # Corrupted entry - mark as empty
                    chunk_table.append({
                        'offset': 0,
                        'length': 0,
                        'compression': 0
                    })
            
            header = {
                'region_x': region_x,
                'region_y': region_y,
                'chunk_table': chunk_table
            }
            
            # Cache the header (thread-safe if we have region coords)
            if region_x is not None and region_y is not None:
                cache_key = (region_x, region_y)
                region_lock = self._get_region_lock(region_x, region_y)
                with region_lock:
                    self.region_headers[cache_key] = header
            
            return header
        except struct.error as e:
            error_type = "StructError"
            error_details = f"Binary format error: {type(e).__name__}: {e}"
            error_msg = f"World '{self.world_name}', Region ({region_x}, {region_y}): {error_type} - {error_details}"
            print(f"[RegionManager] CORRUPTED HEADER: {error_msg}")
            
            if not use_cached_handle:
                f.close()
            
            # Handle corruption
            if self.backup_corrupted and region_x is not None and region_y is not None:
                self._backup_corrupted_file(file_path, region_x, region_y, error_type, error_details)
            
            return None
        except Exception as e:
            error_type = type(e).__name__
            error_details = str(e)
            error_msg = f"World '{self.world_name}', Region ({region_x}, {region_y}): {error_type} - {error_details}"
            print(f"[RegionManager] CORRUPTED HEADER: {error_msg}")
            
            if not use_cached_handle:
                f.close()
            
            # Handle corruption
            if self.backup_corrupted and region_x is not None and region_y is not None:
                self._backup_corrupted_file(file_path, region_x, region_y, error_type, error_details)
            
            return None
        finally:
            if not use_cached_handle:
                try:
                    f.close()
                except Exception:
                    pass
    
    def _write_region_header(self, file_path: Path, region_x: int, region_y: int, chunk_table: List[Dict]):
        """
        Write region file header (optimized: only updates chunk table, preserves Magic/Version/Coords).
        
        This method is atomic and crash-safe:
        - Only writes the chunk table section (CHUNK_TABLE_OFFSET to CHUNK_TABLE_OFFSET + CHUNK_TABLE_SIZE)
        - Never overwrites Magic/Version/Coords (bytes 0-15)
        - On crash, only the table can be corrupted, not the Magic - allows repair/migration
        
        Also updates the header cache (thread-safe)
        Uses cached file handle if available
        """
        cache_key = (region_x, region_y)
        region_lock = self._get_region_lock(region_x, region_y)
        
        # Get or create file handle (already thread-safe)
        f = self._get_region_file_handle(region_x, region_y, create_if_missing=True)
        if f is None:
            raise IOError(f"Could not open region file ({region_x}, {region_y})")
        
        try:
            # CRITICAL: Only write chunk table section, never overwrite Magic/Version/Coords
            # Seek directly to chunk table offset (skip Magic/Version/Coords)
            f.seek(self.CHUNK_TABLE_OFFSET)
            
            # Write chunk table (9 bytes per entry: offset + length + compression)
            for entry in chunk_table:
                f.write(struct.pack('>IIB', 
                    entry.get('offset', 0),
                    entry.get('length', 0),
                    entry.get('compression', 0)
                ))
            
            # Ensure we wrote exactly CHUNK_TABLE_SIZE bytes
            current_pos = f.tell()
            expected_pos = self.CHUNK_TABLE_OFFSET + self.CHUNK_TABLE_SIZE
            if current_pos != expected_pos:
                # This should never happen, but pad if needed
                if current_pos < expected_pos:
                    f.write(b'\x00' * (expected_pos - current_pos))
            
            # Flush to ensure data is written (crash protection)
            f.flush()
            os.fsync(f.fileno())  # Force write to disk
            
            # Update cache (thread-safe)
            with region_lock:
                self.region_headers[cache_key] = {
                    'region_x': region_x,
                    'region_y': region_y,
                    'chunk_table': chunk_table.copy()  # Copy to avoid reference issues
                }
        except Exception as e:
            print(f"[RegionManager] Error writing header to {file_path}: {e}")
            raise
    
    async def load_chunk_data(self, chunk_x: int, chunk_y: int, seed: Optional[int] = None) -> Dict:
        """
        Load chunk data from region file and deserialize (async)
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
            seed: Optional expected world seed (for validation).
                  If None, seed validation is skipped.
        
        Returns:
            Dictionary with 'chunk_x', 'chunk_y', 'seed', 'tiles'
        
        Raises:
            ChunkNotFoundError: If chunk doesn't exist
            ChunkCorruptedError: If chunk data is corrupted
            SeedMismatchError: If seed is provided and doesn't match chunk seed
            RegionFileError: If file operations fail
        """
        data = await self.load_chunk(chunk_x, chunk_y, seed or 0)  # Pass dummy seed if None
        return self.deserialize_chunk(data, expected_seed=seed)
    
    async def load_chunk(self, chunk_x: int, chunk_y: int, seed: Optional[int] = None) -> bytes:
        """
        Load raw chunk data from region file (internal use, async)
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
            seed: Optional expected world seed (not used here but passed through for consistency)
        
        Returns:
            Uncompressed chunk data bytes
        
        Raises:
            ChunkNotFoundError: If chunk doesn't exist
            RegionFileError: If file operations fail
        """
        import time
        perf_start = time.perf_counter()
        
        region_x, region_y = self._get_region_coords(chunk_x, chunk_y)
        local_x, local_y = self._get_local_chunk_coords(chunk_x, chunk_y)
        chunk_index = self._get_chunk_index(local_x, local_y)
        
        region_file = self._get_region_filename(region_x, region_y)
        
        # Check if file exists (sync, fast)
        if not region_file.exists():
            raise ChunkNotFoundError(f"Chunk ({chunk_x}, {chunk_y}) not found: region file doesn't exist")
        
        # Read header (with caching) - run in thread pool to avoid blocking
        header_start = time.perf_counter()
        header = await asyncio.to_thread(self._read_region_header, region_file, region_x, region_y)
        header_time = time.perf_counter() - header_start
        
        if not header:
            raise RegionFileError(f"Failed to read header for chunk ({chunk_x}, {chunk_y})")
        
        # Get chunk entry from table
        chunk_entry = header['chunk_table'][chunk_index]
        
        # Check if chunk exists (offset != 0)
        if chunk_entry['offset'] == 0:
            raise ChunkNotFoundError(f"Chunk ({chunk_x}, {chunk_y}) not found: no data in region file")
        
        # Use cached file handle (optimized: check cache first, then open if needed) - run in thread pool
        file_handle_start = time.perf_counter()
        f = await asyncio.to_thread(self._get_region_file_handle, region_x, region_y, False)
        file_handle_time = time.perf_counter() - file_handle_start
        
        if f is None:
            raise RegionFileError(f"Failed to open region file for chunk ({chunk_x}, {chunk_y})")
        
        try:
            # Read chunk data - run in thread pool to avoid blocking
            def _read_chunk_data():
                # Seek to chunk data (usually fast if file is in OS cache)
                seek_start = time.perf_counter()
                f.seek(chunk_entry['offset'])
                seek_time = time.perf_counter() - seek_start
                
                # Read compressed data (can be slow if file not in OS cache)
                read_start = time.perf_counter()
                
                # Read actual compressed data size from header (length field)
                actual_size = chunk_entry['length']
                
                # Validate size
                if actual_size == 0:
                    raise ChunkNotFoundError(
                        f"Chunk ({chunk_x}, {chunk_y}) not found: empty slot (chunk not yet saved)"
                    )
                
                if actual_size > self.MAX_CHUNK_DATA_SIZE:
                    raise ChunkCorruptedError(
                        f"Chunk ({chunk_x}, {chunk_y}) corrupted: length {actual_size} exceeds MAX_CHUNK_DATA_SIZE {self.MAX_CHUNK_DATA_SIZE}"
                    )
                
                # Read actual compressed data
                compressed_data = f.read(actual_size)
                read_time = time.perf_counter() - read_start
                
                if len(compressed_data) != actual_size:
                    raise ChunkCorruptedError(
                        f"Chunk ({chunk_x}, {chunk_y}) corrupted: expected {actual_size} bytes, "
                        f"read {len(compressed_data)} bytes"
                    )
                
                return compressed_data, seek_time, read_time
            
            compressed_data, seek_time, read_time = await asyncio.to_thread(_read_chunk_data)
            
            # Decompress (CPU-bound, run in thread pool)
            decompress_start = time.perf_counter()
            try:
                def _decompress():
                    if chunk_entry['compression'] == self.COMPRESSION_ZLIB:
                        return zlib.decompress(compressed_data)
                    elif chunk_entry['compression'] == self.COMPRESSION_LZ4:
                        if not LZ4_AVAILABLE:
                            raise ChunkCorruptedError(
                                f"Chunk ({chunk_x}, {chunk_y}) uses LZ4 compression but lz4 package is not available"
                            )
                        return lz4.frame.decompress(compressed_data)
                    elif chunk_entry['compression'] == self.COMPRESSION_NONE:
                        return compressed_data
                    else:
                        raise ChunkCorruptedError(
                            f"Chunk ({chunk_x}, {chunk_y}) corrupted: unsupported compression type {chunk_entry['compression']}"
                        )
                
                result = await asyncio.to_thread(_decompress)
            except (zlib.error, LZ4FrameError) as e:
                raise ChunkCorruptedError(f"Chunk ({chunk_x}, {chunk_y}) corrupted: decompression failed - {e}")
            decompress_time = time.perf_counter() - decompress_start
            
            # Log slow operations for debugging (only if total time > 5ms)
            total_time = time.perf_counter() - perf_start
            if total_time > 0.005:  # 5ms threshold
                if self.diagnostics:
                    self.diagnostics.debug("RegionManager",
                        f"Slow chunk load ({chunk_x}, {chunk_y}): "
                        f"total={total_time*1000:.2f}ms "
                        f"(header={header_time*1000:.2f}ms, "
                        f"file_handle={file_handle_time*1000:.2f}ms, "
                        f"seek={seek_time*1000:.2f}ms, "
                        f"read={read_time*1000:.2f}ms, "
                        f"decompress={decompress_time*1000:.2f}ms)")
            
            # Track region file load time (Disk I/O)
            if self.performance_monitor:
                # Only track the actual disk I/O time (read + seek), not decompression
                disk_io_time = seek_time + read_time
                self.performance_monitor.record_region_file_load(region_x, region_y, disk_io_time)
            
            return result
        except (ChunkNotFoundError, ChunkCorruptedError, RegionFileError):
            raise
        except Exception as e:
            raise RegionFileError(f"Error loading chunk ({chunk_x}, {chunk_y}): {type(e).__name__}: {e}") from e
    
    async def save_chunk_data(self, chunk_x: int, chunk_y: int, tiles: List[List[Dict]], seed: int):
        """
        Save chunk data to region file (high-level API, async)
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
            tiles: 15x15 array of tile dictionaries
            seed: World seed
        
        Raises:
            RegionFileError: If save operation fails
        """
        chunk_data = self.serialize_chunk(chunk_x, chunk_y, tiles, seed)
        await self.save_chunk(chunk_x, chunk_y, chunk_data, seed)
    
    async def save_chunk(self, chunk_x: int, chunk_y: int, chunk_data: bytes, seed: int):
        """
        Save raw chunk data to region file (internal use, async)
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
            chunk_data: Uncompressed chunk data bytes
            seed: World seed (for validation)
        
        Returns:
            True if successful, False otherwise
        """
        region_x, region_y = self._get_region_coords(chunk_x, chunk_y)
        local_x, local_y = self._get_local_chunk_coords(chunk_x, chunk_y)
        chunk_index = self._get_chunk_index(local_x, local_y)
        
        region_file = self._get_region_filename(region_x, region_y)
        
        # Ensure region header exists (pre-initialize if needed)
        if not region_file.exists():
            # Create region file with initialized header (all empty slots)
            await self._initialize_region_file(region_x, region_y)
        
        # Compress chunk data based on configured compression type (CPU-bound, run in thread pool)
        def _compress():
            if self.compression_type == self.COMPRESSION_LZ4:
                # LZ4 compression: faster decompression, good for high chunk load rates
                return lz4.frame.compress(chunk_data, compression_level=lz4.frame.COMPRESSIONLEVEL_MINHC), self.COMPRESSION_LZ4
            else:
                # Zlib compression: default, good compression ratio
                return zlib.compress(chunk_data, level=self.compression_level), self.COMPRESSION_ZLIB
        
        compressed_data, compression_type = await asyncio.to_thread(_compress)
        
        # Validate compressed data fits in slot
        actual_size = len(compressed_data)
        if actual_size > self.MAX_CHUNK_DATA_SIZE:
            error_msg = (
                f"Chunk ({chunk_x}, {chunk_y}) compressed size ({actual_size} bytes) "
                f"exceeds maximum slot size ({self.MAX_CHUNK_DATA_SIZE} bytes). "
                f"Consider increasing MAX_CHUNK_DATA_SIZE or optimizing chunk data."
            )
            if self.diagnostics:
                self.diagnostics.error("RegionManager", error_msg)
            raise RegionFileError(error_msg)
        
        # Calculate fixed slot offset
        slot_offset = self.HEADER_SIZE + chunk_index * self.MAX_CHUNK_DATA_SIZE
        
        # Thread-safe: Get region lock for all operations
        # Note: We still use threading locks, but run the sync operations in thread pool
        def _save_operation():
            disk_io_start = time.perf_counter()
            
            region_lock = self._get_region_lock(region_x, region_y)
            
            with region_lock:
                cache_key = (region_x, region_y)
                
                # Check if region file exists and uses old write-once format
                needs_migration = False
                if region_file.exists():
                    needs_migration = self._is_old_write_once_format(region_x, region_y)
                    if needs_migration:
                        # Migrate old region file to fixed-slot format
                        if self.diagnostics:
                            self.diagnostics.info("RegionManager",
                                f"Migrating region ({region_x}, {region_y}) from old write-once format to fixed-slot format")
                        try:
                            self._migrate_region_to_fixed_slots(region_x, region_y)
                            # Clear cache to force reload
                            self.region_headers.pop(cache_key, None)
                        except Exception as e:
                            if self.diagnostics:
                                self.diagnostics.error("RegionManager",
                                    f"Failed to migrate region ({region_x}, {region_y}): {e}")
                            raise RegionFileError(f"Failed to migrate region ({region_x}, {region_y}): {e}") from e
                
                # Get or load header (with caching)
                if cache_key in self.region_headers:
                    # Header already in cache - use it directly
                    header = self.region_headers[cache_key]
                elif region_file.exists():
                    # Header not in cache - read from disk
                    header = self._read_region_header(region_file, region_x, region_y)
                    if not header:
                        # Corrupted header - repair or raise error
                        if self.auto_repair_corrupted:
                            if self.diagnostics:
                                self.diagnostics.warning("RegionManager",
                                    f"REPAIR MODE: Creating new header for world '{self.world_name}', Region ({region_x}, {region_y})")
                            # Create new header with fixed slot offsets
                            chunk_table = []
                            for i in range(self.CHUNKS_PER_REGION):
                                slot_offset_fixed = self.HEADER_SIZE + i * self.MAX_CHUNK_DATA_SIZE
                                chunk_table.append({
                                    'offset': slot_offset_fixed,
                                    'length': 0,  # Empty slot
                                    'compression': 0
                                })
                            header = {
                                'region_x': region_x,
                                'region_y': region_y,
                                'chunk_table': chunk_table
                            }
                            self.region_headers[cache_key] = header.copy()
                        else:
                            raise RegionFileError(
                                f"Corrupted header for world '{self.world_name}', Region ({region_x}, {region_y}). "
                                f"Set auto_repair_corrupted=True to repair automatically."
                            )
                else:
                    # New region file - create header with all fixed slot offsets
                    chunk_table = []
                    for i in range(self.CHUNKS_PER_REGION):
                        slot_offset_fixed = self.HEADER_SIZE + i * self.MAX_CHUNK_DATA_SIZE
                        chunk_table.append({
                            'offset': slot_offset_fixed,  # Fixed slot position
                            'length': 0,  # Empty slot (length=0 means unsaved)
                            'compression': 0
                        })
                    header = {
                        'region_x': region_x,
                        'region_y': region_y,
                        'chunk_table': chunk_table
                    }
                    self.region_headers[cache_key] = header.copy()
                
                # Get or create file handle (thread-safe method, lock already held)
                f = self._get_region_file_handle(region_x, region_y, create_if_missing=True, _lock_held=True)
                if f is None:
                    raise IOError(f"Could not open region file ({region_x}, {region_y})")
                
                try:
                    # IN-PLACE WRITE: Write directly to fixed slot position
                    f.seek(slot_offset)
                    f.write(compressed_data)
                    
                    # Pad remaining slot space with zeros
                    padding_size = self.MAX_CHUNK_DATA_SIZE - actual_size
                    if padding_size > 0:
                        f.write(b'\x00' * padding_size)
                    
                    f.flush()  # Ensure data is written before header update
                    
                    # Update header entry: set length to actual compressed size
                    # CRITICAL: Only write the chunk table entry, never overwrite Magic/Version/Coords
                    # This ensures that a crash during header update can only corrupt the table,
                    # not the Magic - allowing repair/migration instead of InvalidMagic error
                    f.seek(self.CHUNK_TABLE_OFFSET + chunk_index * self.CHUNK_TABLE_ENTRY_SIZE)
                    f.write(struct.pack('>IIB', slot_offset, actual_size, compression_type))
                    f.flush()  # Ensure header update is written
                    os.fsync(f.fileno())  # Force write to disk (crash protection)
                    
                    # Update cache
                    self.region_headers[cache_key]['chunk_table'][chunk_index] = {
                        'offset': slot_offset,
                        'length': actual_size,  # Actual compressed size
                        'compression': compression_type
                    }
                    
                    # Note: File should always have a valid header at this point
                    # (created by _create_new_region_file or pre-existing)
                    # We only update individual chunk table entries, never overwrite Magic/Version/Coords
                
                except Exception as e:
                    # If error occurs, we might need to invalidate the handle
                    self._close_region_file(region_x, region_y)
                    raise RegionFileError(f"Error writing chunk ({chunk_x}, {chunk_y}): {type(e).__name__}: {e}") from e
                finally:
                    # Track region file save time (Disk I/O)
                    disk_io_time = time.perf_counter() - disk_io_start
                    if self.performance_monitor:
                        self.performance_monitor.record_region_file_save(region_x, region_y, disk_io_time)
        
        # Run the entire save operation in thread pool
        await asyncio.to_thread(_save_operation)
    
    def _migrate_region_to_fixed_slots(self, region_x: int, region_y: int) -> bool:
        """
        Migrate an old write-once format region file to fixed-slot format.
        
        This method:
        1. Reads all existing chunks from the old region file
        2. Writes them to fixed slot positions in a new file
        3. Atomically replaces the old file with the new one
        
        Args:
            region_x: Region X coordinate
            region_y: Region Y coordinate
        
        Returns:
            True if successful, False otherwise
        """
        region_file = self._get_region_filename(region_x, region_y)
        
        if not region_file.exists():
            return False
        
        # Read old header
        old_header = self._read_region_header(region_file, region_x, region_y)
        if not old_header:
            return False
        
        old_chunk_table = old_header['chunk_table']
        
        # Collect all existing chunks from old format
        chunks_to_migrate = []
        for i, entry in enumerate(old_chunk_table):
            if entry['offset'] > 0 and entry['length'] > 0:
                # Calculate chunk coordinates from index
                local_y = i // self.REGION_SIZE_CHUNKS
                local_x = i % self.REGION_SIZE_CHUNKS
                chunk_x = region_x * self.REGION_SIZE_CHUNKS + local_x
                chunk_y = region_y * self.REGION_SIZE_CHUNKS + local_y
                
                # Load chunk data (sync, but we're in a thread pool anyway)
                try:
                    # Use asyncio.run to call async load_chunk
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        chunk_data = loop.run_until_complete(self.load_chunk(chunk_x, chunk_y, 0))
                    finally:
                        loop.close()
                    
                    if chunk_data is not None:
                        chunks_to_migrate.append({
                            'index': i,
                            'chunk_x': chunk_x,
                            'chunk_y': chunk_y,
                            'data': chunk_data,
                            'compression': entry['compression']
                        })
                except Exception as e:
                    if self.diagnostics:
                        self.diagnostics.warning("RegionManager",
                            f"Failed to load chunk ({chunk_x}, {chunk_y}) during migration: {e}")
                    continue
        
        # Close handle if open
        self._close_region_file(region_x, region_y)
        
        # Create temporary file for atomic update
        temp_file = region_file.with_suffix('.tmp')
        
        try:
            # Write new region file with fixed slots
            with open(temp_file, 'wb') as f:
                # Write header with all fixed slot offsets
                f.write(self.REGION_MAGIC)
                f.write(struct.pack('B', self.REGION_VERSION))
                f.write(b'\x00' * 3)
                f.write(struct.pack('>ii', region_x, region_y))
                
                # Initialize chunk table with fixed slot offsets
                new_chunk_table = []
                for i in range(self.CHUNKS_PER_REGION):
                    slot_offset = self.HEADER_SIZE + i * self.MAX_CHUNK_DATA_SIZE
                    new_chunk_table.append({
                        'offset': slot_offset,
                        'length': 0,  # Will be updated below
                        'compression': 0
                    })
                
                # Write chunk table (will be updated after writing chunks)
                for entry in new_chunk_table:
                    f.write(struct.pack('>IIB', 
                        entry['offset'],
                        entry['length'],
                        entry['compression']
                    ))
                
                # Pad to HEADER_SIZE
                current_pos = f.tell()
                if current_pos < self.HEADER_SIZE:
                    f.write(b'\x00' * (self.HEADER_SIZE - current_pos))
                
                # Write chunks to fixed slots
                for chunk_info in chunks_to_migrate:
                    # Compress chunk data using configured compression type
                    if self.compression_type == self.COMPRESSION_LZ4:
                        compressed_data = lz4.frame.compress(chunk_info['data'], compression_level=lz4.frame.COMPRESSIONLEVEL_MINHC)
                    else:
                        compressed_data = zlib.compress(chunk_info['data'], level=self.compression_level)
                    
                    # Validate size
                    if len(compressed_data) > self.MAX_CHUNK_DATA_SIZE:
                        if self.diagnostics:
                            self.diagnostics.warning("RegionManager",
                                f"Chunk ({chunk_info['chunk_x']}, {chunk_info['chunk_y']}) too large after migration, skipping")
                        continue
                    
                    # Write to fixed slot
                    slot_offset = self.HEADER_SIZE + chunk_info['index'] * self.MAX_CHUNK_DATA_SIZE
                    f.seek(slot_offset)
                    f.write(compressed_data)
                    
                    # Pad slot
                    padding_size = self.MAX_CHUNK_DATA_SIZE - len(compressed_data)
                    if padding_size > 0:
                        f.write(b'\x00' * padding_size)
                    
                    # Update chunk table entry
                    new_chunk_table[chunk_info['index']] = {
                        'offset': slot_offset,
                        'length': len(compressed_data),
                        'compression': self.compression_type
                    }
                
                # Update header with actual chunk table
                f.seek(self.CHUNK_TABLE_OFFSET)
                for entry in new_chunk_table:
                    f.write(struct.pack('>IIB', 
                        entry['offset'],
                        entry['length'],
                        entry['compression']
                    ))
            
            # Atomically replace old file with new using os.replace (atomic on all platforms)
            # This ensures that the original file is never in a half-written state
            os.replace(temp_file, region_file)
            
            # Update cache
            cache_key = (region_x, region_y)
            self.region_headers[cache_key] = {
                'region_x': region_x,
                'region_y': region_y,
                'chunk_table': new_chunk_table
            }
            
            if self.diagnostics:
                self.diagnostics.info("RegionManager",
                    f"Migrated region ({region_x}, {region_y}) to fixed-slot format: {len(chunks_to_migrate)} chunks")
            return True
            
        except Exception as e:
            if self.diagnostics:
                self.diagnostics.error("RegionManager",
                    f"Error migrating region ({region_x}, {region_y}): {e}")
            import traceback
            traceback.print_exc()
            
            # Clean up temp file
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            
            return False
    
    def compact_region(self, region_x: int, region_y: int) -> bool:
        """
        Compact a region file by removing fragmentation (only for old write-once format).
        
        For fixed-slot regions, this is a no-op (they don't fragment).
        This method migrates old regions to fixed-slot format instead of compacting.
        
        Args:
            region_x: Region X coordinate
            region_y: Region Y coordinate
        
        Returns:
            True if successful, False otherwise
        """
        # If already using fixed slots, no compaction needed
        if not self._is_old_write_once_format(region_x, region_y):
            return True  # Already in fixed-slot format, no action needed
        
        # Migrate old format to fixed slots (this is effectively compaction + migration)
        return self._migrate_region_to_fixed_slots(region_x, region_y)
    
    async def chunk_exists(self, chunk_x: int, chunk_y: int) -> bool:
        """Check if chunk exists in region file (async)"""
        region_x, region_y = self._get_region_coords(chunk_x, chunk_y)
        local_x, local_y = self._get_local_chunk_coords(chunk_x, chunk_y)
        chunk_index = self._get_chunk_index(local_x, local_y)
        
        region_file = self._get_region_filename(region_x, region_y)
        
        if not region_file.exists():
            return False
        
        # Read header (with caching) - run in thread pool
        header = await asyncio.to_thread(self._read_region_header, region_file, region_x, region_y)
        if not header:
            return False
        
        chunk_entry = header['chunk_table'][chunk_index]
        return chunk_entry['offset'] > 0
    
    def serialize_chunk(self, chunk_x: int, chunk_y: int, tiles: List[List[Dict]], seed: int) -> bytes:
        """
        Serialize chunk data to optimized binary format
        
        OPTIMIZED FORMAT (v2):
        - int32 chunk_x (big-endian)
        - int32 chunk_y (big-endian)
        - int32 seed (big-endian)
        - int16 width (15, big-endian)
        - int16 height (15, big-endian)
        - uint8 biome_count (number of unique biomes in chunk)
        - Biome table: biome_count entries
          Each entry:
            - uint8 biome_string_length
            - string biome_id (UTF-8, variable length)
        - Tile data: 225 tiles (15x15)
          Per tile (6 bytes):
            - uint8 biome_index (index into biome table, 0-255)
            - uint8 height (0-255, normalized from float)
            - uint8 flags (bitmask: bit 0 = traversable, bits 1-7 reserved)
            - uint8[3] color (r, g, b)
        - int16 entity_count (0 for now, big-endian)
        
        OPTIMIZATION BENEFITS:
        - Biome strings stored once per chunk instead of per tile
        - Each tile uses 1 byte (biome_index) instead of 1-20+ bytes (string + length)
        - Removed unused tile_id_hash (saves 2 bytes per tile)
        - Better compression ratio (repeated biome strings compress better)
        - Typical savings: 50-80% reduction in chunk size for homogeneous biomes
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
            tiles: 15x15 array of tile dictionaries
            seed: World seed
        
        Returns:
            Serialized chunk data as bytes
        """
        # Step 1: Collect all unique biomes and create index mapping
        biome_set = set()
        for row in tiles:
            for tile in row:
                biome_id = tile.get('biome', 'unknown')
                biome_set.add(biome_id)
        
        # Convert to ordered list (for consistent indexing)
        biome_list = sorted(biome_set)  # Sort for consistency
        biome_to_index = {biome: idx for idx, biome in enumerate(biome_list)}
        biome_count = len(biome_list)
        
        if biome_count > 255:
            # Fallback: if more than 255 unique biomes (shouldn't happen), use first 255
            biome_list = biome_list[:255]
            biome_to_index = {biome: idx for idx, biome in enumerate(biome_list)}
            biome_count = 255
        
        # Chunk metadata
        parts = [
            struct.pack('>ii', chunk_x, chunk_y),  # int32 chunk_x, chunk_y
            struct.pack('>i', seed),  # int32 seed
            struct.pack('>hh', 15, 15),  # int16 width, height
            struct.pack('B', biome_count),  # uint8 biome_count
        ]
        
        # Biome table
        for biome_id in biome_list:
            biome_bytes = biome_id.encode('utf-8')
            biome_len = len(biome_bytes)
            parts.append(struct.pack('B', biome_len))  # uint8 biome_string_length
            parts.append(biome_bytes)  # biome_id string
        
        # Tile data (15x15 = 225 tiles)
        # Each tile: biome_index (1 byte) + height (1 byte) + flags (1 byte) + color (3 bytes) = 6 bytes
        for row in tiles:
            for tile in row:
                # Get biome index
                biome_id = tile.get('biome', 'unknown')
                biome_index = biome_to_index.get(biome_id, 0)  # Fallback to 0 if not found
                
                # Extract other tile data
                height_float = tile.get('height', 0.0)
                height_byte = max(0, min(255, int(height_float * 255)))  # Normalize to 0-255
                traversable = 1 if tile.get('traversable', True) else 0
                flags = traversable  # bit 0 = traversable
                color = tile.get('color', (128, 128, 128))
                r, g, b = color[0], color[1], color[2]
                
                # Pack tile data (6 bytes per tile)
                parts.append(struct.pack('B', biome_index))  # uint8 biome_index
                parts.append(struct.pack('B', height_byte))  # uint8 height
                parts.append(struct.pack('B', flags))  # uint8 flags
                parts.append(struct.pack('BBB', r, g, b))  # uint8[3] color
        
        # Entity count (0 for now, future expansion)
        parts.append(struct.pack('>h', 0))  # int16 entity_count
        
        # Decoration data (Sparse-Format with Flags)
        # Collect all decorations from tiles
        decorations = []
        for tile_y in range(len(tiles)):
            if tile_y >= len(tiles):
                continue
            for tile_x in range(len(tiles[tile_y])):
                if tile_x >= len(tiles[tile_y]):
                    continue
                tile = tiles[tile_y][tile_x]
                if not tile:
                    continue
                
                decoration_data = tile.get('decoration')
                if decoration_data:
                    deco_data = decoration_data.get('data', {})
                    
                    # Build flags for changed data
                    flags = 0
                    growth_timer = deco_data.get('growth_timer', 0.0)
                    has_fruit = deco_data.get('has_fruit', True)
                    damage = deco_data.get('damage', 0.0)
                    last_interaction = deco_data.get('last_interaction', 0.0)
                    initial_growth_time = deco_data.get('initial_growth_time', 0.0)
                    
                    if growth_timer != 0.0:
                        flags |= 0x01
                    if not has_fruit:
                        flags |= 0x02
                    if damage != 0.0:
                        flags |= 0x04
                    if last_interaction != 0.0:
                        flags |= 0x08
                    if initial_growth_time != 0.0:
                        flags |= 0x10
                    
                    # Only save if flags are set (sparse format)
                    if flags != 0:
                        decorations.append((
                            tile_x, tile_y,
                            decoration_data.get('decoration_id', ''),
                            flags, growth_timer, has_fruit, damage, last_interaction, initial_growth_time
                        ))
        
        # Decoration count
        parts.append(struct.pack('B', len(decorations)))  # uint8 decoration_count
        
        # Decoration data (only changed data based on flags)
        for tile_x, tile_y, decoration_id, flags, growth_timer, has_fruit, damage, last_interaction, initial_growth_time in decorations:
            parts.append(struct.pack('B', flags))  # uint8 flags
            parts.append(struct.pack('BB', tile_x, tile_y))  # uint8 tile_x, tile_y (0-14)
            
            # Decoration ID
            deco_id_bytes = decoration_id.encode('utf-8')
            parts.append(struct.pack('B', len(deco_id_bytes)))  # uint8 decoration_id_length
            parts.append(deco_id_bytes)  # decoration_id string
            
            # Only save data based on flags
            if flags & 0x01:
                parts.append(struct.pack('>f', growth_timer))  # float32 growth_timer
            if flags & 0x02:
                parts.append(struct.pack('B', 1 if has_fruit else 0))  # uint8 has_fruit
            if flags & 0x04:
                parts.append(struct.pack('>f', damage))  # float32 damage
            if flags & 0x08:
                parts.append(struct.pack('>f', last_interaction))  # float32 last_interaction
            if flags & 0x10:
                parts.append(struct.pack('>f', initial_growth_time))  # float32 initial_growth_time
        
        # Join all parts at once (much faster than extend in loop)
        return b''.join(parts)
    
    def deserialize_chunk(self, data: bytes, expected_seed: int = None) -> Dict:
        """
        Deserialize chunk data from optimized binary format (v2)
        
        Supports both old format (backward compatibility) and new optimized format.
        Detects format by checking if biome_count field exists after dimensions.
        
        Args:
            data: Serialized chunk data bytes
            expected_seed: Optional expected world seed for validation.
                          If provided and doesn't match chunk seed, raises SeedMismatchError.
        
        Returns:
            Dictionary with 'chunk_x', 'chunk_y', 'seed', 'tiles' (15x15 array)
        
        Raises:
            ChunkCorruptedError: If chunk data is corrupted or invalid
            SeedMismatchError: If expected_seed is provided and doesn't match chunk seed
        """
        try:
            offset = 0
            
            # Read metadata
            chunk_x, chunk_y = struct.unpack('>ii', data[offset:offset+8])
            offset += 8
            seed = struct.unpack('>i', data[offset:offset+4])[0]
            offset += 4
            width, height = struct.unpack('>hh', data[offset:offset+4])
            offset += 4
            
            if width != 15 or height != 15:
                raise ChunkCorruptedError(f"Invalid chunk dimensions: {width}x{height} (expected 15x15)")
            
            # Validate seed if expected_seed is provided
            if expected_seed is not None and seed != expected_seed:
                raise SeedMismatchError(
                    f"Seed mismatch for chunk ({chunk_x}, {chunk_y}): "
                    f"expected {expected_seed}, got {seed}. "
                    f"This may indicate files were mixed up between different worlds."
                )
            
            # Check if this is the new optimized format (has biome_count)
            # Old format: directly starts with tile data (biome_id_len)
            # New format: has biome_count first
            if offset >= len(data):
                return None
            
            # Try to detect format: if next byte is reasonable biome_count (0-255) and
            # we have enough data, assume new format. Otherwise, try old format.
            biome_count = struct.unpack('B', data[offset:offset+1])[0]
            offset += 1
            
            # Check if this looks like a valid biome_count (reasonable number)
            # and if we have enough data for the biome table
            is_new_format = False
            if biome_count > 0 and biome_count <= 255:
                # Estimate: check if we have enough bytes for biome table + tiles
                # Minimum: biome_count * (1 + 1) + 225 * 6 = biome_count * 2 + 1350
                estimated_size = biome_count * 2 + 1350  # Rough estimate
                if len(data) - offset >= estimated_size:
                    is_new_format = True
            
            if is_new_format:
                # NEW FORMAT: Read biome table first
                biome_table = []
                for i in range(biome_count):
                    biome_len = struct.unpack('B', data[offset:offset+1])[0]
                    offset += 1
                    if offset + biome_len > len(data):
                        raise ChunkCorruptedError(f"Invalid biome table: truncated data at biome {i}")
                    biome_id = data[offset:offset+biome_len].decode('utf-8')
                    offset += biome_len
                    biome_table.append(biome_id)
                
                # Read tile data (6 bytes per tile: biome_index + height + flags + color)
                tiles = []
                for y in range(height):
                    row = []
                    for x in range(width):
                        if offset + 6 > len(data):
                            raise ChunkCorruptedError(f"Invalid tile data: truncated at tile ({x}, {y})")
                        
                        # Read tile data
                        biome_index = struct.unpack('B', data[offset:offset+1])[0]
                        offset += 1
                        height_byte = struct.unpack('B', data[offset:offset+1])[0]
                        offset += 1
                        flags = struct.unpack('B', data[offset:offset+1])[0]
                        offset += 1
                        r, g, b = struct.unpack('BBB', data[offset:offset+3])
                        offset += 3
                        
                        # Get biome_id from table
                        if biome_index < len(biome_table):
                            biome_id = biome_table[biome_index]
                        else:
                            biome_id = 'unknown'  # Fallback
                        
                        # Convert back to tile dictionary
                        height_float = height_byte / 255.0
                        traversable = bool(flags & 0x01)
                        
                        tile = {
                            'biome': biome_id,
                            'height': height_float,
                            'tile_id': biome_id,  # Use biome_id as tile_id
                            'color': (r, g, b),
                            'traversable': traversable
                        }
                        row.append(tile)
                    tiles.append(row)
            else:
                # OLD FORMAT: Read tile data with per-tile biome strings
                # Reset offset (we already read biome_count, but it was actually biome_id_len)
                offset -= 1  # Go back to read biome_id_len
                
                tiles = []
                for y in range(height):
                    row = []
                    for x in range(width):
                        if offset >= len(data):
                            raise ChunkCorruptedError(f"Invalid tile data: truncated at tile ({x}, {y})")
                        
                        # Read biome_id
                        biome_id_len = struct.unpack('B', data[offset:offset+1])[0]
                        offset += 1
                        if offset + biome_id_len > len(data):
                            raise ChunkCorruptedError(f"Invalid biome_id: truncated at tile ({x}, {y})")
                        biome_id = data[offset:offset+biome_id_len].decode('utf-8')
                        offset += biome_id_len
                        
                        # Read tile_id hash (skip it, not used)
                        if offset + 2 > len(data):
                            raise ChunkCorruptedError(f"Invalid tile_id_hash: truncated at tile ({x}, {y})")
                        tile_id_hash = struct.unpack('>H', data[offset:offset+2])[0]
                        offset += 2
                        
                        # Read height, flags, color
                        if offset + 5 > len(data):
                            raise ChunkCorruptedError(f"Invalid tile data: truncated at tile ({x}, {y})")
                        height_byte = struct.unpack('B', data[offset:offset+1])[0]
                        offset += 1
                        flags = struct.unpack('B', data[offset:offset+1])[0]
                        offset += 1
                        r, g, b = struct.unpack('BBB', data[offset:offset+3])
                        offset += 3
                        
                        # Convert back to tile dictionary
                        height_float = height_byte / 255.0
                        traversable = bool(flags & 0x01)
                        
                        tile = {
                            'biome': biome_id,
                            'height': height_float,
                            'tile_id': biome_id,  # Use biome_id as tile_id
                            'color': (r, g, b),
                            'traversable': traversable
                        }
                        row.append(tile)
                    tiles.append(row)
            
            # Read entity count (skip for now)
            if offset + 2 <= len(data):
                entity_count = struct.unpack('>h', data[offset:offset+2])[0]
                offset += 2
            
            # Read decoration data (if available)
            if offset < len(data):
                try:
                    decoration_count = struct.unpack('B', data[offset:offset+1])[0]
                    offset += 1
                    
                    # Load decorations
                    for i in range(decoration_count):
                        if offset >= len(data):
                            break
                        
                        # Read flags
                        flags = struct.unpack('B', data[offset:offset+1])[0]
                        offset += 1
                        
                        # Read tile coordinates
                        if offset + 2 > len(data):
                            break
                        tile_x, tile_y = struct.unpack('BB', data[offset:offset+2])
                        offset += 2
                        
                        # Read decoration ID
                        if offset + 1 > len(data):
                            break
                        deco_id_len = struct.unpack('B', data[offset:offset+1])[0]
                        offset += 1
                        if offset + deco_id_len > len(data):
                            break
                        decoration_id = data[offset:offset+deco_id_len].decode('utf-8')
                        offset += deco_id_len
                        
                        # Initialize decoration data with defaults
                        deco_data = {
                            'growth_timer': 0.0,
                            'has_fruit': True,
                            'damage': 0.0,
                            'last_interaction': 0.0,
                            'initial_growth_time': 0.0
                        }
                        
                        # Read data based on flags
                        if flags & 0x01:  # growth_timer
                            if offset + 4 > len(data):
                                break
                            deco_data['growth_timer'] = struct.unpack('>f', data[offset:offset+4])[0]
                            offset += 4
                        if flags & 0x02:  # has_fruit
                            if offset + 1 > len(data):
                                break
                            deco_data['has_fruit'] = bool(struct.unpack('B', data[offset:offset+1])[0])
                            offset += 1
                        if flags & 0x04:  # damage
                            if offset + 4 > len(data):
                                break
                            deco_data['damage'] = struct.unpack('>f', data[offset:offset+4])[0]
                            offset += 4
                        if flags & 0x08:  # last_interaction
                            if offset + 4 > len(data):
                                break
                            deco_data['last_interaction'] = struct.unpack('>f', data[offset:offset+4])[0]
                            offset += 4
                        if flags & 0x10:  # initial_growth_time
                            if offset + 4 > len(data):
                                break
                            deco_data['initial_growth_time'] = struct.unpack('>f', data[offset:offset+4])[0]
                            offset += 4
                        
                        # Add decoration to tile
                        if 0 <= tile_y < len(tiles) and 0 <= tile_x < len(tiles[tile_y]):
                            tile = tiles[tile_y][tile_x]
                            if tile:
                                tile['decoration'] = {
                                    'decoration_id': decoration_id,
                                    'data': deco_data
                                }
                except Exception:
                    # Silently ignore decoration loading errors (backward compatibility)
                    pass
            
            return {
                'chunk_x': chunk_x,
                'chunk_y': chunk_y,
                'seed': seed,
                'tiles': tiles
            }
        except (ChunkCorruptedError, SeedMismatchError):
            raise
        except Exception as e:
            raise ChunkCorruptedError(f"Error deserializing chunk: {type(e).__name__}: {e}") from e

