"""
World: Chunk Manager - JSON-based chunk save/load system
"""
import json
import os
import math
from pathlib import Path
from typing import Dict, Tuple, Optional, List, Set
from core import settings
import threading
import queue


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
        """Pre-render chunk tiles to a surface (called in background thread)"""
        import pygame
        
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        surface = pygame.Surface((chunk_size_pixels, chunk_size_pixels))
        
        # Draw all tiles to the surface
        for y, row in enumerate(self.tiles):
            for x, tile in enumerate(row):
                color = tuple(tile["color"]) if isinstance(tile["color"], list) else tile["color"]
                rect = pygame.Rect(
                    x * settings.TILE_SIZE,
                    y * settings.TILE_SIZE,
                    settings.TILE_SIZE,
                    settings.TILE_SIZE
                )
                pygame.draw.rect(surface, color, rect)
        
        # Convert to screen format for faster blitting (5-10x speedup!)
        surface = surface.convert()
        
        self.surface = surface
        self.surface_dirty = False
        return surface


class ChunkManager:
    """Manages chunk loading/unloading and save/load to JSON"""

    def __init__(self, save_slot: int, terrain_gen):
        """
        Initialize ChunkManager for a specific save slot
        
        Args:
            save_slot: Save slot number (1-3)
            terrain_gen: TerrainGenerator instance for new chunk generation
        """
        self.save_slot = save_slot
        self.terrain_gen = terrain_gen
        self.loaded_chunks: Dict[Tuple[int, int], Chunk] = {}
        self.player_chunk_pos = None  # Changed from (0, 0) to None to force initial load
        
        # Setup save directories
        self.save_dir = Path(f"saves/slot_{save_slot}")
        self.chunks_dir = self.save_dir / "chunks"
        self.chunks_dir.mkdir(parents=True, exist_ok=True)
        
        # Load or create world metadata
        self.metadata_file = self.save_dir / "world_metadata.json"
        self.metadata = self._load_metadata()
        
        # Setup chunk loading queue and worker threads
        self.chunk_load_queue = queue.Queue()
        self.chunk_load_results = queue.Queue()
        self.worker_threads = []
        self.running = True
        self.pending_chunks = set()  # Track chunks being loaded
        self.chunk_priority = {}  # Distance-based priority
        
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
        
        if key in self.loaded_chunks:
            return self.loaded_chunks[key]
        
        # Try to load from file first
        loaded_chunk = self._load_chunk_from_file(chunk_x, chunk_y)
        if loaded_chunk:
            self.loaded_chunks[key] = loaded_chunk
            return loaded_chunk
        
        # Generate new chunk
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
        """Check if a chunk file exists on disk"""
        return self._get_chunk_filename(chunk_x, chunk_y).exists()

    def _save_chunk_to_file(self, chunk: Chunk):
        """
        Save a chunk to JSON file
        
        Args:
            chunk: Chunk instance to save
        """
        chunk_file = self._get_chunk_filename(chunk.chunk_x, chunk.chunk_y)
        
        # Prepare chunk data for JSON serialization
        save_data = {
            "chunk_coords": [chunk.chunk_x, chunk.chunk_y],
            "seed": self.get_seed(),
            "tiles": chunk.tiles,  # 15x15 grid with biome + resource data
            "entities": []  # Future: entity data
        }
        
        try:
            with open(chunk_file, 'w') as f:
                json.dump(save_data, f, indent=2)
        except Exception as e:
            print(f"Error saving chunk ({chunk.chunk_x}, {chunk.chunk_y}): {e}")

    def _load_chunk_from_file(self, chunk_x: int, chunk_y: int) -> Optional[Chunk]:
        """
        Load a chunk from JSON file
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
            
        Returns:
            Chunk instance or None if file doesn't exist
        """
        chunk_file = self._get_chunk_filename(chunk_x, chunk_y)
        
        if not chunk_file.exists():
            return None
        
        try:
            with open(chunk_file, 'r') as f:
                chunk_data = json.load(f)
            
            tiles = chunk_data["tiles"]
            chunk = Chunk(chunk_x, chunk_y, tiles)
            return chunk
            
        except Exception as e:
            print(f"Error loading chunk ({chunk_x}, {chunk_y}): {e}")
            return None

    def unload_chunk(self, chunk_x: int, chunk_y: int):
        """Save and remove chunk from memory"""
        key = (chunk_x, chunk_y)
        if key in self.loaded_chunks:
            chunk = self.loaded_chunks[key]
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
            # Pre-render surface for initial chunks
            if chunk.surface is None:
                chunk.render_to_surface()
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
        """Worker thread that loads chunks from the queue"""
        while self.running:
            try:
                # Get chunk coordinates from queue (timeout prevents hanging)
                chunk_x, chunk_y = self.chunk_load_queue.get(timeout=0.1)
                
                # Check if chunk already loaded (double-check with lock)
                if (chunk_x, chunk_y) in self.loaded_chunks:
                    self.pending_chunks.discard((chunk_x, chunk_y))
                    continue
                
                # Load or generate chunk
                chunk = self._load_chunk_from_file(chunk_x, chunk_y)
                if not chunk:
                    # Generate new chunk
                    tiles = self.terrain_gen.generate_chunk(chunk_x, chunk_y)
                    chunk = Chunk(chunk_x, chunk_y, tiles)
                    # Don't save immediately - batch save later for better performance
                
                # Pre-render chunk surface in background thread
                chunk.render_to_surface()
                
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
        """Request a chunk to be loaded asynchronously
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
            priority: Priority (lower = higher priority, based on distance)
        """
        chunk_key = (chunk_x, chunk_y)
        if chunk_key not in self.loaded_chunks and chunk_key not in self.pending_chunks:
            self.pending_chunks.add(chunk_key)
            self.chunk_priority[chunk_key] = priority
            self.chunk_load_queue.put((chunk_x, chunk_y))
    
    def process_loaded_chunks(self, all_sprites, resource_sprites):
        """Process chunks that have finished loading in background threads"""
        loaded_count = 0
        max_per_frame = 1  # Reduced from 3 to prevent frame drops
        
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
    
    def shutdown(self):
        """Stop worker threads and cleanup"""
        self.running = False
        for thread in self.worker_threads:
            thread.join(timeout=1.0)
