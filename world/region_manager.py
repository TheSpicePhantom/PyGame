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
    - offset (4 bytes, uint32, big-endian, 0 = chunk not present)
    - length (4 bytes, uint32, big-endian, compressed chunk size)
    - compression (1 byte, uint8, 0=none, 1=zlib, 2=lz4)
- Offset 0xF1-0xFF: Padding (15 bytes, reserved for future use)

Chunk Data (v2 - Optimized Format):
- Stored after header (offset >= 256)
- Compression: zlib (level 1) by default
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

FRAGMENTATION & CRASH-SAFETY:
==============================
To ensure crash-safety, chunks are always written to the end of the file (write-once).
When a chunk is updated, the old space is left unused (fragmentation).

This ensures:
- Header always points to valid data (atomic 9-byte write)
- No data loss if write is interrupted
- Old chunks remain readable until header is updated

Fragmentation can be reclaimed by calling compact_region() in the background.
"""
import struct
import zlib
import os
import json
import threading
from pathlib import Path
from typing import Dict, Tuple, Optional, List
from collections import OrderedDict


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
    CHUNK_TABLE_ENTRY_SIZE = 9  # 4 bytes offset + 4 bytes length + 1 byte compression
    CHUNK_TABLE_SIZE = CHUNKS_PER_REGION * CHUNK_TABLE_ENTRY_SIZE  # 225 bytes
    
    # Compression types
    COMPRESSION_NONE = 0
    COMPRESSION_ZLIB = 1
    COMPRESSION_LZ4 = 2
    
    # Maximum number of open region files (LRU cache)
    # Increased from 64 to 128 to reduce file open/close overhead
    # Each region file is ~5-50KB, so 128 files = ~6.4MB memory (acceptable)
    MAX_OPEN_REGIONS = 128
    
    def __init__(self, world_name: str, auto_repair_corrupted: bool = False, backup_corrupted: bool = True):
        """
        Initialize RegionManager for a specific world
        
        Args:
            world_name: World name (will be sanitized for use as directory name)
            auto_repair_corrupted: If True, automatically create new headers for corrupted files.
                                   If False, rename corrupted files to .corrupt and skip them.
            backup_corrupted: If True, rename corrupted files to .corrupt instead of overwriting.
                              Only used if auto_repair_corrupted is True.
        """
        from world.world_utils import get_world_save_dir
        self.world_name = world_name
        self.auto_repair_corrupted = auto_repair_corrupted
        self.backup_corrupted = backup_corrupted
        self.save_dir = get_world_save_dir(world_name)
        self.regions_dir = self.save_dir / "regions"
        self.regions_dir.mkdir(parents=True, exist_ok=True)
        
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
                return handle
            
            # Check if file exists
            if not region_file.exists():
                if create_if_missing:
                    # Create empty file
                    region_file.touch()
                else:
                    return None
            
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
        Backup a corrupted region file by renaming it to .corrupt
        
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
            
            # Create backup filename with timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = file_path.parent / f"{file_path.stem}.corrupt.{timestamp}"
            
            # Rename file
            file_path.rename(backup_path)
            
            print(f"[RegionManager] CORRUPTED FILE BACKUP: Slot {self.save_slot}, Region ({region_x}, {region_y})")
            print(f"  Error Type: {error_type}")
            print(f"  Error Details: {error_details}")
            print(f"  Original: {file_path.name}")
            print(f"  Backup: {backup_path.name}")
        except Exception as e:
            print(f"[RegionManager] Failed to backup corrupted file {file_path}: {e}")
    
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
                error_msg = f"Slot {self.save_slot}, Region ({region_x}, {region_y}): Failed to open file - {type(e).__name__}: {e}"
                print(f"[RegionManager] {error_msg}")
                return None
        
        try:
            # Read magic number
            f.seek(0)
            magic = f.read(4)
            if magic != self.REGION_MAGIC:
                error_type = "InvalidMagic"
                error_details = f"Expected '{self.REGION_MAGIC.decode('ascii', errors='replace')}', got '{magic.decode('ascii', errors='replace')}'"
                error_msg = f"Slot {self.save_slot}, Region ({region_x}, {region_y}): {error_type} - {error_details}"
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
                error_msg = f"Slot {self.save_slot}, Region ({region_x}, {region_y}): {error_type} - {error_details}"
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
            
            # Read chunk table
            chunk_table = []
            for i in range(self.CHUNKS_PER_REGION):
                offset, length, comp = struct.unpack('>IIB', f.read(9))
                chunk_table.append({
                    'offset': offset,
                    'length': length,
                    'compression': comp
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
            error_msg = f"Slot {self.save_slot}, Region ({region_x}, {region_y}): {error_type} - {error_details}"
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
            error_msg = f"Slot {self.save_slot}, Region ({region_x}, {region_y}): {error_type} - {error_details}"
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
        Write region file header (optimized: only write header, not entire file)
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
            # Seek to start
            f.seek(0)
            
            # Write magic
            f.write(self.REGION_MAGIC)
            
            # Write version
            f.write(struct.pack('B', self.REGION_VERSION))
            
            # Write padding
            f.write(b'\x00' * 3)
            
            # Write region coordinates
            f.write(struct.pack('>ii', region_x, region_y))
            
            # Write chunk table
            for entry in chunk_table:
                f.write(struct.pack('>IIB', 
                    entry.get('offset', 0),
                    entry.get('length', 0),
                    entry.get('compression', 0)
                ))
            
            # Pad to HEADER_SIZE
            current_pos = f.tell()
            if current_pos < self.HEADER_SIZE:
                f.write(b'\x00' * (self.HEADER_SIZE - current_pos))
            
            # Flush to ensure data is written
            f.flush()
            
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
    
    def load_chunk_data(self, chunk_x: int, chunk_y: int, seed: Optional[int] = None) -> Dict:
        """
        Load chunk data from region file and deserialize
        
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
        data = self.load_chunk(chunk_x, chunk_y, seed or 0)  # Pass dummy seed if None
        return self.deserialize_chunk(data, expected_seed=seed)
    
    def load_chunk(self, chunk_x: int, chunk_y: int, seed: Optional[int] = None) -> bytes:
        """
        Load raw chunk data from region file (internal use)
        
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
        
        if not region_file.exists():
            raise ChunkNotFoundError(f"Chunk ({chunk_x}, {chunk_y}) not found: region file doesn't exist")
        
        # Read header (with caching) - this is usually fast if cached
        header_start = time.perf_counter()
        header = self._read_region_header(region_file, region_x, region_y)
        header_time = time.perf_counter() - header_start
        
        if not header:
            raise RegionFileError(f"Failed to read header for chunk ({chunk_x}, {chunk_y})")
        
        # Get chunk entry from table
        chunk_entry = header['chunk_table'][chunk_index]
        
        # Check if chunk exists (offset != 0)
        if chunk_entry['offset'] == 0:
            raise ChunkNotFoundError(f"Chunk ({chunk_x}, {chunk_y}) not found: no data in region file")
        
        # Use cached file handle (optimized: check cache first, then open if needed)
        file_handle_start = time.perf_counter()
        f = self._get_region_file_handle(region_x, region_y, create_if_missing=False)
        file_handle_time = time.perf_counter() - file_handle_start
        
        if f is None:
            raise RegionFileError(f"Failed to open region file for chunk ({chunk_x}, {chunk_y})")
        
        try:
            # Seek to chunk data (usually fast if file is in OS cache)
            seek_start = time.perf_counter()
            f.seek(chunk_entry['offset'])
            seek_time = time.perf_counter() - seek_start
            
            # Read compressed data (can be slow if file not in OS cache)
            read_start = time.perf_counter()
            compressed_data = f.read(chunk_entry['length'])
            read_time = time.perf_counter() - read_start
            
            if len(compressed_data) != chunk_entry['length']:
                raise ChunkCorruptedError(
                    f"Chunk ({chunk_x}, {chunk_y}) corrupted: expected {chunk_entry['length']} bytes, "
                    f"read {len(compressed_data)} bytes"
                )
            
            # Decompress (usually fast, but can be slow for large chunks)
            decompress_start = time.perf_counter()
            try:
                if chunk_entry['compression'] == self.COMPRESSION_ZLIB:
                    result = zlib.decompress(compressed_data)
                elif chunk_entry['compression'] == self.COMPRESSION_NONE:
                    result = compressed_data
                else:
                    raise ChunkCorruptedError(
                        f"Chunk ({chunk_x}, {chunk_y}) corrupted: unsupported compression type {chunk_entry['compression']}"
                    )
            except zlib.error as e:
                raise ChunkCorruptedError(f"Chunk ({chunk_x}, {chunk_y}) corrupted: decompression failed - {e}")
            decompress_time = time.perf_counter() - decompress_start
            
            # Log slow operations for debugging (only if total time > 5ms)
            total_time = time.perf_counter() - perf_start
            if total_time > 0.005:  # 5ms threshold
                print(f"[RegionManager] Slow chunk load ({chunk_x}, {chunk_y}): "
                      f"total={total_time*1000:.2f}ms "
                      f"(header={header_time*1000:.2f}ms, "
                      f"file_handle={file_handle_time*1000:.2f}ms, "
                      f"seek={seek_time*1000:.2f}ms, "
                      f"read={read_time*1000:.2f}ms, "
                      f"decompress={decompress_time*1000:.2f}ms)")
            
            return result
        except (ChunkNotFoundError, ChunkCorruptedError, RegionFileError):
            raise
        except Exception as e:
            raise RegionFileError(f"Error loading chunk ({chunk_x}, {chunk_y}): {type(e).__name__}: {e}") from e
    
    def save_chunk_data(self, chunk_x: int, chunk_y: int, tiles: List[List[Dict]], seed: int):
        """
        Save chunk data to region file (high-level API)
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
            tiles: 15x15 array of tile dictionaries
            seed: World seed
        
        Raises:
            RegionFileError: If save operation fails
        """
        chunk_data = self.serialize_chunk(chunk_x, chunk_y, tiles, seed)
        self.save_chunk(chunk_x, chunk_y, chunk_data, seed)
    
    def save_chunk(self, chunk_x: int, chunk_y: int, chunk_data: bytes, seed: int):
        """
        Save raw chunk data to region file (internal use)
        
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
        
        # Compress chunk data (use level=1 for faster compression, trade-off: slightly larger files)
        compressed_data = zlib.compress(chunk_data, level=1)  # Fast compression for better performance
        compression_type = self.COMPRESSION_ZLIB
        
        # Thread-safe: Get region lock for all operations
        region_lock = self._get_region_lock(region_x, region_y)
        
        with region_lock:
            # Read existing header or create new one (with caching)
            # _read_region_header is already thread-safe, but we hold lock for cache consistency
            if region_file.exists():
                header = self._read_region_header(region_file, region_x, region_y)
                if not header:
                    # Corrupted header
                    if self.auto_repair_corrupted:
                        # Create new header (repair mode)
                        print(f"[RegionManager] REPAIR MODE: Creating new header for Slot {self.save_slot}, Region ({region_x}, {region_y})")
                        header = {
                            'region_x': region_x,
                            'region_y': region_y,
                            'chunk_table': [{'offset': 0, 'length': 0, 'compression': 0} for _ in range(self.CHUNKS_PER_REGION)]
                        }
                        # Cache the new header
                        cache_key = (region_x, region_y)
                        self.region_headers[cache_key] = header.copy()
                    else:
                        # Don't repair, raise exception
                        raise RegionFileError(
                            f"Corrupted header for Slot {self.save_slot}, Region ({region_x}, {region_y}). "
                            f"Set auto_repair_corrupted=True to repair automatically."
                        )
            else:
                # New region file
                header = {
                    'region_x': region_x,
                    'region_y': region_y,
                    'chunk_table': [{'offset': 0, 'length': 0, 'compression': 0} for _ in range(self.CHUNKS_PER_REGION)]
                }
                # Cache the new header
                cache_key = (region_x, region_y)
                self.region_headers[cache_key] = header.copy()
            
            # Get existing entry info (for crash-safe update)
            chunk_table = header['chunk_table']
            existing_entry = chunk_table[chunk_index]
            old_offset = existing_entry.get('offset', 0)
            old_length = existing_entry.get('length', 0)
            
            # Find next available offset (after header and all existing chunks)
            # CRASH-SAFE STRATEGY: Always append new chunks to end (write-once)
            # This ensures header always points to valid data, even if write is interrupted
            max_offset = self.HEADER_SIZE
            
            # Find the end of existing data (including the chunk we're updating)
            for i, entry in enumerate(chunk_table):
                if entry['offset'] > 0:
                    end_pos = entry['offset'] + entry['length']
                    max_offset = max(max_offset, end_pos)
            
            # Always write to end (crash-safe: header update is atomic)
            # Old space will be marked as free (can be reclaimed by compact_region later)
            new_offset = max_offset
            new_length = len(compressed_data)
            
            file_exists = region_file.exists()
            
            # Get or create file handle (thread-safe method, lock already held)
            f = self._get_region_file_handle(region_x, region_y, create_if_missing=True, _lock_held=True)
            if f is None:
                raise IOError(f"Could not open region file ({region_x}, {region_y})")
            
            try:
                if file_exists:
                    # CRASH-SAFE WRITE SEQUENCE:
                    # 1. Write new chunk data to end of file (write-once)
                    # 2. Flush to ensure data is on disk
                    # 3. Atomically update header entry (single 9-byte write)
                    # 4. Flush again
                    # 5. Update cache
                    
                    # Step 1: Write new chunk data to end
                    f.seek(new_offset)
                    f.write(compressed_data)
                    f.flush()  # Ensure data is written before header update
                    
                    # Step 2: Atomically update header entry (single 9-byte write)
                    # This is atomic on most filesystems (single sector write)
                    f.seek(self.CHUNK_TABLE_OFFSET + chunk_index * self.CHUNK_TABLE_ENTRY_SIZE)
                    f.write(struct.pack('>IIB', new_offset, new_length, compression_type))
                    f.flush()  # Ensure header update is written
                    
                    # Step 3: Update cache (already holding lock)
                    cache_key = (region_x, region_y)
                    if cache_key in self.region_headers:
                        self.region_headers[cache_key]['chunk_table'][chunk_index] = {
                            'offset': new_offset,
                            'length': new_length,
                            'compression': compression_type
                        }
                else:
                    # New file: update chunk table entry, then write header and data
                    chunk_table[chunk_index] = {
                        'offset': new_offset,
                        'length': new_length,
                        'compression': compression_type
                    }
                    # Write header (will update cache internally)
                    # Note: _write_region_header will try to get lock, but we already have it
                    # We need to write header directly here to avoid deadlock
                    f.seek(0)
                    f.write(self.REGION_MAGIC)
                    f.write(struct.pack('B', self.REGION_VERSION))
                    f.write(b'\x00' * 3)
                    f.write(struct.pack('>ii', region_x, region_y))
                    for entry in chunk_table:
                        f.write(struct.pack('>IIB', 
                            entry.get('offset', 0),
                            entry.get('length', 0),
                            entry.get('compression', 0)
                        ))
                    current_pos = f.tell()
                    if current_pos < self.HEADER_SIZE:
                        f.write(b'\x00' * (self.HEADER_SIZE - current_pos))
                    f.flush()
                    
                    # Update cache
                    cache_key = (region_x, region_y)
                    self.region_headers[cache_key] = {
                        'region_x': region_x,
                        'region_y': region_y,
                        'chunk_table': chunk_table.copy()
                    }
                    
                    # Write chunk data
                    f.seek(new_offset)
                    f.write(compressed_data)
                    f.flush()
            
            except Exception as e:
                # If error occurs, we might need to invalidate the handle
                self._close_region_file(region_x, region_y)
                raise RegionFileError(f"Error writing chunk ({chunk_x}, {chunk_y}): {type(e).__name__}: {e}") from e
        
        # Get existing entry info (for crash-safe update)
        chunk_table = header['chunk_table']
        existing_entry = chunk_table[chunk_index]
        old_offset = existing_entry.get('offset', 0)
        old_length = existing_entry.get('length', 0)
        
        # Find next available offset (after header and all existing chunks)
        # CRASH-SAFE STRATEGY: Always append new chunks to end (write-once)
        # This ensures header always points to valid data, even if write is interrupted
        max_offset = self.HEADER_SIZE
        
        # Find the end of existing data (including the chunk we're updating)
        for i, entry in enumerate(chunk_table):
            if entry['offset'] > 0:
                end_pos = entry['offset'] + entry['length']
                max_offset = max(max_offset, end_pos)
        
        # Always write to end (crash-safe: header update is atomic)
        # Old space will be marked as free (can be reclaimed by compact_region later)
        new_offset = max_offset
        new_length = len(compressed_data)
        
        try:
            file_exists = region_file.exists()
            
            # Get or create file handle
            f = self._get_region_file_handle(region_x, region_y, create_if_missing=True)
            if f is None:
                raise IOError(f"Could not open region file ({region_x}, {region_y})")
            
            try:
                if file_exists:
                    # CRASH-SAFE WRITE SEQUENCE:
                    # 1. Write new chunk data to end of file (write-once)
                    # 2. Flush to ensure data is on disk
                    # 3. Atomically update header entry (single 9-byte write)
                    # 4. Flush again
                    # 5. Optionally zero out old space (can be done later)
                    
                    # Step 1: Write new chunk data to end
                    f.seek(new_offset)
                    f.write(compressed_data)
                    f.flush()  # Ensure data is written before header update
                    
                    # Step 2: Atomically update header entry (single 9-byte write)
                    # This is atomic on most filesystems (single sector write)
                    f.seek(self.CHUNK_TABLE_OFFSET + chunk_index * self.CHUNK_TABLE_ENTRY_SIZE)
                    f.write(struct.pack('>IIB', new_offset, new_length, compression_type))
                    f.flush()  # Ensure header update is written
                    
                    # Step 3: Update cache
                    cache_key = (region_x, region_y)
                    if cache_key in self.region_headers:
                        self.region_headers[cache_key]['chunk_table'][chunk_index] = {
                            'offset': new_offset,
                            'length': new_length,
                            'compression': compression_type
                        }
                    
                    # Step 4: Optionally zero out old space (non-critical, can be done later)
                    # This helps with fragmentation but is not required for correctness
                    if old_offset > 0 and old_offset != new_offset:
                        # Mark old space as free (zero it out)
                        # This is optional and can be deferred to compact_region()
                        # For now, we'll skip it to keep writes fast
                        # TODO: Background task to zero out old chunks
                        pass
                else:
                    # New file: write header first, then chunk data
                    # Update chunk table entry before writing header
                    chunk_table[chunk_index] = {
                        'offset': new_offset,
                        'length': new_length,
                        'compression': compression_type
                    }
                    self._write_region_header(region_file, region_x, region_y, chunk_table)
                    
                    # Write chunk data
                    f.seek(new_offset)
                    f.write(compressed_data)
                    f.flush()
            except Exception as e:
                # If error occurs, we might need to invalidate the handle
                self._close_region_file(region_x, region_y)
                raise RegionFileError(f"Error writing chunk ({chunk_x}, {chunk_y}): {type(e).__name__}: {e}") from e
            
        except (RegionFileError, ChunkCorruptedError):
            raise
        except Exception as e:
            raise RegionFileError(f"Error saving chunk ({chunk_x}, {chunk_y}): {type(e).__name__}: {e}") from e
    
    def compact_region(self, region_x: int, region_y: int) -> bool:
        """
        Compact a region file by removing fragmentation.
        
        This method:
        1. Reads all existing chunks from the region
        2. Rewrites them sequentially starting after the header
        3. Updates the chunk table with new offsets
        4. Truncates the file to remove unused space
        
        NOTE: This is a background operation and should be called when the region
        is not actively being accessed. It requires reading all chunks, so it can
        be slow for large regions.
        
        Args:
            region_x: Region X coordinate
            region_y: Region Y coordinate
        
        Returns:
            True if successful, False otherwise
        """
        region_file = self._get_region_filename(region_x, region_y)
        
        if not region_file.exists():
            return False
        
        # Read header
        header = self._read_region_header(region_file, region_x, region_y)
        if not header:
            return False
        
        chunk_table = header['chunk_table']
        
        # Collect all existing chunks
        chunks_to_compact = []
        for i, entry in enumerate(chunk_table):
            if entry['offset'] > 0:
                # Calculate chunk coordinates from index
                local_y = i // self.REGION_SIZE_CHUNKS
                local_x = i % self.REGION_SIZE_CHUNKS
                chunk_x = region_x * self.REGION_SIZE_CHUNKS + local_x
                chunk_y = region_y * self.REGION_SIZE_CHUNKS + local_y
                
                # Load chunk data
                chunk_data = self.load_chunk(chunk_x, chunk_y, 0)  # seed not needed for loading
                if chunk_data is not None:
                    chunks_to_compact.append({
                        'index': i,
                        'chunk_x': chunk_x,
                        'chunk_y': chunk_y,
                        'data': chunk_data,
                        'compression': entry['compression']
                    })
        
        if not chunks_to_compact:
            # No chunks to compact
            return True
        
        # Close handle if open
        self._close_region_file(region_x, region_y)
        
        # Create temporary file for atomic update
        temp_file = region_file.with_suffix('.tmp')
        
        try:
            # Write new compacted region
            with open(temp_file, 'wb') as f:
                # Write header placeholder (will be updated)
                f.write(b'\x00' * self.HEADER_SIZE)
                
                # Write chunks sequentially
                new_offset = self.HEADER_SIZE
                new_chunk_table = [{'offset': 0, 'length': 0, 'compression': 0} for _ in range(self.CHUNKS_PER_REGION)]
                
                for chunk_info in chunks_to_compact:
                    # Compress chunk data
                    compressed_data = zlib.compress(chunk_info['data'], level=1)
                    
                    # Write chunk data
                    f.seek(new_offset)
                    f.write(compressed_data)
                    
                    # Update chunk table entry
                    new_chunk_table[chunk_info['index']] = {
                        'offset': new_offset,
                        'length': len(compressed_data),
                        'compression': self.COMPRESSION_ZLIB
                    }
                    
                    new_offset += len(compressed_data)
                
                # Write header
                f.seek(0)
                f.write(self.REGION_MAGIC)
                f.write(struct.pack('B', self.REGION_VERSION))
                f.write(b'\x00' * 3)
                f.write(struct.pack('>ii', region_x, region_y))
                
                for entry in new_chunk_table:
                    f.write(struct.pack('>IIB', 
                        entry.get('offset', 0),
                        entry.get('length', 0),
                        entry.get('compression', 0)
                    ))
                
                # Pad to HEADER_SIZE
                current_pos = f.tell()
                if current_pos < self.HEADER_SIZE:
                    f.write(b'\x00' * (self.HEADER_SIZE - current_pos))
                
                # Truncate to actual size
                f.truncate(new_offset)
            
            # Atomically replace old file with new
            region_file.unlink()
            temp_file.rename(region_file)
            
            # Update cache
            cache_key = (region_x, region_y)
            self.region_headers[cache_key] = {
                'region_x': region_x,
                'region_y': region_y,
                'chunk_table': new_chunk_table
            }
            
            print(f"[RegionManager] Compacted region ({region_x}, {region_y}): {len(chunks_to_compact)} chunks")
            return True
            
        except Exception as e:
            print(f"[RegionManager] Error compacting region ({region_x}, {region_y}): {e}")
            import traceback
            traceback.print_exc()
            
            # Clean up temp file
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            
            return False
    
    def chunk_exists(self, chunk_x: int, chunk_y: int) -> bool:
        """Check if chunk exists in region file"""
        region_x, region_y = self._get_region_coords(chunk_x, chunk_y)
        local_x, local_y = self._get_local_chunk_coords(chunk_x, chunk_y)
        chunk_index = self._get_chunk_index(local_x, local_y)
        
        region_file = self._get_region_filename(region_x, region_y)
        
        if not region_file.exists():
            return False
        
        # Read header (with caching)
        header = self._read_region_header(region_file, region_x, region_y)
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

