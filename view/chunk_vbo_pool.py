"""
View: ChunkVboPool - Pool für wiederverwendbare VBOs/VAOs für Chunks
"""
import moderngl
import numpy as np
import threading
from collections import OrderedDict
from typing import List, Tuple, Optional, Set, Dict
from core import settings


class ChunkVboPool:
    """
    Pool für wiederverwendbare VBOs/VAOs für Chunks.
    
    Erstellt beim Start eine feste Anzahl gleich großer VBOs/VAOs und verwaltet
    deren Wiederverwendung, um die Performance zu verbessern.
    """
    
    def __init__(self, ctx: moderngl.Context, program: moderngl.Program, pool_size: int = 100, diagnostics=None):
        """
        Initialize VBO/VAO Pool
        
        Args:
            ctx: ModernGL context
            program: Shader program for VAO creation
            pool_size: Number of VBOs/VAOs to create in the pool (default: 100)
            diagnostics: Optional DiagnosticsService instance for logging
        """
        self.ctx = ctx
        self.program = program
        self.pool_size = pool_size
        self.diagnostics = diagnostics
        
        # Thread-Safety
        self._lock = threading.Lock()
        
        # LRU-Order: Chunk-basierte Zuordnung mit OrderedDict (behält Einfüge-Reihenfolge)
        self.chunk_to_index: OrderedDict[Tuple[int, int], int] = OrderedDict()
        self.index_to_chunk: Dict[int, Tuple[int, int]] = {}  # Reverse mapping
        
        # Stats-Tracking
        self.stats = {
            'recycled_count': 0,
            'peak_usage': 0,
            'current_usage': 0
        }
        
        # NEW: Visibility tracking
        self.visible_chunks: Set[Tuple[int, int]] = set()  # Set of (chunk_x, chunk_y) that are visible
        self.peak_visible_chunks = 0
        self.recommended_pool_size = pool_size
        
        # Adaptive sizing parameters
        self.initial_size = pool_size
        self.max_size = 500
        self.safety_margin = 1.25  # 25% buffer
        self.growth_increment = 75  # Add 50 buffers per expansion
        self.shrink_delay = 30.0  # Wait 60s before shrinking
        self.shrink_increment = 15  # Remove 20 buffers per shrink
        
        # Runtime metrics for adaptive sizing
        self.peak_usage_time = 0.0
        self.last_expansion_time = 0.0
        self.last_shrink_time = 0.0
        self.expansion_count = 0
        self.shrink_count = 0
        
        # Calculate buffer size for one chunk
        # Chunk size: 15x15 tiles
        # Each tile: 6 vertices (2 triangles) for base tile
        # Each tile can have additional 6 vertices for overlay sprites (flowers, bushes, etc.)
        # Worst case: every tile has an overlay = 2x vertices
        # Each vertex: 6 floats (2 position + 1 color_index + 2 texcoord + 1 use_texture)
        # Base: 15 * 15 * 6 = 1350 vertices
        # With overlays (worst case): 15 * 15 * 6 * 2 = 2700 vertices
        # Size in bytes: 2700 * 6 * 4 = 64800 bytes
        chunk_size = settings.CHUNK_SIZE
        base_vertices_per_chunk = chunk_size * chunk_size * 6  # 6 vertices per tile
        # Account for overlays: worst case is 2x vertices (every tile has overlay)
        max_vertices_per_chunk = base_vertices_per_chunk * 2  # Double for overlays
        floats_per_vertex = 6  # 2 position + 1 color_index + 2 texcoord + 1 use_texture
        self.vertex_count_per_chunk = base_vertices_per_chunk  # Base count (without overlays)
        self.buffer_size_bytes = max_vertices_per_chunk * floats_per_vertex * 4  # 4 bytes per float
        
        # Create pool of VBOs/VAOs
        self.pool: List[Tuple[moderngl.Buffer, moderngl.VertexArray]] = []
        self.available: Set[int] = set()  # Indices of available buffers
        self.in_use: Set[int] = set()  # Indices of buffers currently in use
        
        # Initialize pool with empty buffers
        self._initialize_pool()
    
    def _initialize_pool(self, size: Optional[int] = None):
        """
        Create all VBOs/VAOs in the pool or expand by 'size' buffers.
        
        Args:
            size: Number of buffers to create. If None, uses self.pool_size.
        """
        if size is None:
            size = self.pool_size
        
        start_idx = len(self.pool)
        
        try:
            for i in range(size):
                # Create empty buffer with correct size
                vbo = self.ctx.buffer(reserve=self.buffer_size_bytes)
                
                # Create VAO with the buffer
                # Format: 2 floats for position, 1 float for color_index, 2 floats for texcoord, 1 float for use_texture
                vao = self.ctx.vertex_array(
                    self.program,
                    [(vbo, "2f 1f 2f 1f", "in_position", "in_color_index", "in_texcoord", "in_use_texture")]
                )
                
                self.pool.append((vbo, vao))
                self.available.add(start_idx + i)
            
            if self.diagnostics:
                if size == self.pool_size:
                    self.diagnostics.info("ChunkVboPool", f"Initialized VBO pool with {self.pool_size} buffers")
                else:
                    self.diagnostics.debug("ChunkVboPool", f"Expanded pool by {size} buffers (total: {len(self.pool)})")
        except Exception as e:
            if self.diagnostics:
                self.diagnostics.error("ChunkVboPool", f"Failed to initialize VBO pool: {e}")
            else:
                import traceback
                traceback.print_exc()
            raise
    
    def _should_expand(self) -> bool:
        """Check if pool should expand based on usage patterns."""
        import time
        now = time.time()
        current_usage = len(self.in_use)
        utilization = current_usage / len(self.pool) if len(self.pool) > 0 else 1.0
        
        # Expand if:
        # 1. Utilization > 90% (running out of buffers)
        # 2. Peak usage exceeds current size * safety margin
        # 3. We haven't expanded in the last 1 second (prevent spam)
        
        if utilization > 0.90:
            if now - self.last_expansion_time > 1.0:
                return True
        
        target_size = int(self.stats['peak_usage'] * self.safety_margin)
        if target_size > len(self.pool):
            if now - self.last_expansion_time > 1.0:
                return True
        
        return False
    
    def _should_shrink(self) -> bool:
        """Check if pool should shrink based on prolonged underutilization."""
        import time
        now = time.time()
        current_usage = len(self.in_use)
        utilization = current_usage / len(self.pool) if len(self.pool) > 0 else 0.0
        
        # Shrink only if:
        # 1. Utilization < 50% (significantly underutilized)
        # 2. Peak usage hasn't changed in 60+ seconds
        # 3. Pool is larger than initial size
        # 4. We haven't shrunk in the last 60 seconds
        
        if utilization < 0.50 and len(self.pool) > self.initial_size:
            if now - self.peak_usage_time > self.shrink_delay:
                if now - self.last_shrink_time > self.shrink_delay:
                    return True
        
        return False
    
    def _expand_pool(self):
        """Expand pool by growth_increment buffers."""
        if len(self.pool) >= self.max_size:
            if self.diagnostics:
                self.diagnostics.warning(
                    "ChunkVboPool",
                    f"Pool at max size ({self.max_size}). Cannot expand further."
                )
            return
        
        import time
        expansion_size = min(self.growth_increment, self.max_size - len(self.pool))
        
        old_size = len(self.pool)
        self._initialize_pool(expansion_size)
        self.last_expansion_time = time.time()
        self.expansion_count += 1
        
        if self.diagnostics:
            self.diagnostics.info(
                "ChunkVboPool",
                f"Pool expanded: {len(self.pool)} buffers (+{expansion_size}, "
                f"expansions: {self.expansion_count}, utilization: {len(self.in_use)}/{len(self.pool)})"
            )
    
    def _shrink_pool(self):
        """Shrink pool by removing unused buffers from the end."""
        if len(self.available) < self.shrink_increment:
            return  # Not enough free buffers to shrink
        
        import time
        
        # Only remove from end to preserve indices
        to_remove = []
        for idx in range(len(self.pool) - 1, self.initial_size - 1, -1):
            if len(to_remove) >= self.shrink_increment:
                break
            if idx in self.available:
                to_remove.append(idx)
        
        if not to_remove:
            return  # Can't shrink - no buffers at end are available
        
        # Remove buffers
        for idx in to_remove:
            vbo, vao = self.pool[idx]
            vbo.release()
            vao.release()
            self.available.remove(idx)
        
        # Truncate pool (preserves all indices)
        self.pool = self.pool[:len(self.pool) - len(to_remove)]
        
        self.last_shrink_time = time.time()
        self.shrink_count += 1
        
        if self.diagnostics:
            self.diagnostics.info(
                "ChunkVboPool",
                f"Pool shrunk: {len(self.pool)} buffers "
                f"(-{len(to_remove)}, shrinks: {self.shrink_count})"
            )
    
    def acquire(self) -> Optional[Tuple[moderngl.Buffer, moderngl.VertexArray, int]]:
        """
        Acquire a free VBO/VAO from the pool (thread-safe)
        
        Returns:
            (vbo, vao, index) tuple if available, None if pool is exhausted
        """
        with self._lock:
            if not self.available:
                # Pool exhausted - return None (caller should handle this)
                return None
            
            # Get first available buffer
            index = next(iter(self.available))
            self.available.remove(index)
            self.in_use.add(index)
            
            vbo, vao = self.pool[index]
            return (vbo, vao, index)
    
    def _release_internal(self, index: int):
        """Internal release without locking - caller must hold lock
        
        Args:
            index: Index of the buffer to release
        """
        if index in self.in_use:
            self.in_use.remove(index)
            self.available.add(index)
            # Update stats
            self.stats['current_usage'] = len(self.in_use)
    
    def release(self, index: int):
        """
        Release a VBO/VAO back to the pool (thread-safe)
        
        Args:
            index: Index of the buffer to release
        """
        with self._lock:
            self._release_internal(index)
    
    def write_data(self, vbo: moderngl.Buffer, vertex_data: np.ndarray):
        """
        Write vertex data to a VBO
        
        Args:
            vbo: VBO to write to
            vertex_data: Numpy array of vertex data (dtype=np.float32)
        """
        # Ensure data fits in buffer
        data_bytes = vertex_data.tobytes()
        if len(data_bytes) > self.buffer_size_bytes:
            raise ValueError(f"Vertex data ({len(data_bytes)} bytes) exceeds buffer size ({self.buffer_size_bytes} bytes)")
        
        # Write data to buffer
        vbo.write(data_bytes)
    
    def get_vbo_for_chunk(self, chunk_key: Tuple[int, int]) -> Tuple[moderngl.Buffer, moderngl.VertexArray, int]:
        """
        Get or recycle VBO for specific chunk (thread-safe, LRU-based)
        
        Args:
            chunk_key: Chunk coordinates (chunk_x, chunk_y)
        
        Returns:
            (vbo, vao, index) tuple
        """
        with self._lock:
            import time
            now = time.time()
            
            # Update peak usage tracking
            current_usage = len(self.in_use) + 1  # +1 for the one we're about to allocate
            if current_usage > self.stats['peak_usage']:
                self.stats['peak_usage'] = current_usage
                self.peak_usage_time = now
            
            # Check if expansion needed
            if self._should_expand():
                self._expand_pool()
            
            # Periodically check if shrinking possible (every 30s)
            if now - self.last_shrink_time > 30.0:
                if self._should_shrink():
                    self._shrink_pool()
            
            # Wenn Chunk bereits VBO hat, wiederverwenden (LRU-Update)
            if chunk_key in self.chunk_to_index:
                # Move to end (most recently used) - effizienter als pop + re-insert
                self.chunk_to_index.move_to_end(chunk_key)
                index = self.chunk_to_index[chunk_key]
                vbo, vao = self.pool[index]
                # Stats am Ende aktualisieren
                self.stats['current_usage'] = len(self.in_use)
                self.stats['peak_usage'] = max(self.stats['peak_usage'], self.stats['current_usage'])
                return (vbo, vao, index)
            
            was_recycled = False
            # Neuen VBO holen (mit Smart Recycling wenn nötig)
            if not self.available:
                # SMART RECYCLING: Only recycle invisible chunks
                recyclable_chunks = self._get_recyclable_chunks()
                
                if recyclable_chunks:
                    oldest_chunk = recyclable_chunks[0]
                    if self.diagnostics:
                        self.diagnostics.debug(
                            "ChunkVboPool",
                            f"Recycling invisible chunk {oldest_chunk} for {chunk_key}"
                        )
                    was_recycled = True
                    self.stats['recycled_count'] += 1
                    
                    if oldest_chunk in self.chunk_to_index:
                        old_index = self.chunk_to_index.pop(oldest_chunk)
                        self.index_to_chunk.pop(old_index, None)
                        self._release_internal(old_index)
                else:
                    # No recyclable chunks - all visible!
                    if self.diagnostics:
                        self.diagnostics.warning(
                            "ChunkVboPool",
                            f"Pool exhausted with {len(self.visible_chunks)} visible chunks, "
                            f"pool size: {len(self.pool)}. Recommended: {self.recommended_pool_size}. "
                            "Creating temporary buffer."
                        )
                    return self._create_temporary_vbo()
            
            # Acquire from pool (interner Aufruf, kein Lock nötig da bereits im Lock)
            if not self.available:
                # Sollte nicht passieren nach Recycling, aber sicherheitshalber prüfen
                raise RuntimeError("VBO pool exhausted after recycling")
            
            # Get first available buffer
            index = next(iter(self.available))
            self.available.remove(index)
            self.in_use.add(index)
            
            vbo, vao = self.pool[index]
            self.chunk_to_index[chunk_key] = index
            self.index_to_chunk[index] = chunk_key
            # Stats am Ende aktualisieren
            self.stats['current_usage'] = len(self.in_use)
            self.stats['peak_usage'] = max(self.stats['peak_usage'], self.stats['current_usage'])
            return (vbo, vao, index)
    
    def _get_recyclable_chunks(self) -> List[Tuple[int, int]]:
        """
        Get list of chunks that can be recycled, sorted by priority.
        Prioritizes invisible chunks over visible ones.
        
        Returns:
            List of (chunk_x, chunk_y) tuples, oldest invisible first
        """
        if not self.chunk_to_index:
            return []
        
        recyclable = []
        
        # Separate visible and invisible chunks
        invisible_chunks = []
        visible_chunks = []
        
        for chunk_key in self.chunk_to_index.keys():
            if chunk_key in self.visible_chunks:
                visible_chunks.append(chunk_key)
            else:
                invisible_chunks.append(chunk_key)
        
        # PRIORITY 1: Recycle invisible chunks first (oldest first)
        recyclable.extend(invisible_chunks)
        
        # PRIORITY 2: Only recycle visible chunks if absolutely necessary
        # (This should rarely happen if pool is sized correctly)
        recyclable.extend(visible_chunks)
        
        return recyclable
    
    def _create_temporary_vbo(self) -> Tuple[moderngl.Buffer, moderngl.VertexArray, int]:
        """
        Create temporary VBO outside pool (emergency fallback)
        
        Returns:
            (vbo, vao, -1) tuple where -1 indicates temporary buffer
        """
        vbo = self.ctx.buffer(reserve=self.buffer_size_bytes)
        vao = self.ctx.vertex_array(
            self.program,
            [(vbo, "2f 1f 2f 1f", "in_position", "in_color_index", "in_texcoord", "in_use_texture")]
        )
        # Return with index=-1 to indicate temporary buffer
        return (vbo, vao, -1)
    
    def set_visible_chunks(self, visible_chunk_keys: Set[Tuple[int, int]]):
        """
        Inform pool which chunks are currently visible.
        Pool will prioritize these chunks and avoid recycling them.
        
        Args:
            visible_chunk_keys: Set of (chunk_x, chunk_y) tuples
        """
        with self._lock:
            self.visible_chunks = visible_chunk_keys.copy()
            
            # Track peak for sizing recommendations
            current_visible = len(visible_chunk_keys)
            if current_visible > self.peak_visible_chunks:
                self.peak_visible_chunks = current_visible
                # Recommend pool size = peak * 1.5
                self.recommended_pool_size = int(current_visible * 1.5)
                
                # FIX: Verwende len(self.pool) statt self.pool_size
                current_pool_size = len(self.pool)
                if self.diagnostics and current_visible > current_pool_size * 0.8:
                    self.diagnostics.warning(
                        "ChunkVboPool",
                        f"Pool usage high: {current_visible}/{current_pool_size} visible chunks. "
                        f"Recommended pool size: {self.recommended_pool_size}"
                    )
    
    def release_chunk(self, chunk_key: Tuple[int, int]):
        """
        Release VBO for specific chunk (thread-safe)
        
        Args:
            chunk_key: Chunk coordinates (chunk_x, chunk_y)
        """
        with self._lock:
            if chunk_key in self.chunk_to_index:
                index = self.chunk_to_index.pop(chunk_key)
                self.index_to_chunk.pop(index, None)
                self._release_internal(index)  # Use internal method to avoid nested lock
    
    def get_stats(self) -> dict:
        """Get pool statistics including sizing recommendations (thread-safe)"""
        with self._lock:
            base_stats = {
                'initial_pool_size': self.initial_size,  # Umbenennen von pool_size
                'current_pool_size': len(self.pool),     # Aktueller Wert (war current_size)
                'available': len(self.available),
                'in_use': len(self.in_use),
                'buffer_size_bytes': self.buffer_size_bytes,
                'vertex_count_per_chunk': self.vertex_count_per_chunk,
                'peak_visible_chunks': self.peak_visible_chunks,
                'recommended_pool_size': self.recommended_pool_size,
                'current_visible_chunks': len(self.visible_chunks),
                # Adaptive sizing metrics
                'max_size': self.max_size,
                'target_size': int(self.stats['peak_usage'] * self.safety_margin),
                'utilization': len(self.in_use) / len(self.pool) if len(self.pool) > 0 else 0.0,
                'expansion_count': self.expansion_count,
                'shrink_count': self.shrink_count,
                'efficiency': 1.0 - (len(self.available) / len(self.pool)) if len(self.pool) > 0 else 0.0
            }
            return {**base_stats, **self.stats}
    
    def cleanup(self):
        """Release all buffers and clean up resources (thread-safe)"""
        with self._lock:
            # Release all buffers (use internal method to avoid nested lock)
            for index in list(self.in_use):
                self._release_internal(index)
            
            # Release all VBOs/VAOs
            for vbo, vao in self.pool:
                vbo.release()
                vao.release()
            
            self.pool.clear()
            self.available.clear()
            self.in_use.clear()
            self.chunk_to_index.clear()
            self.index_to_chunk.clear()

