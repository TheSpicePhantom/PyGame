"""
View: ChunkVboPool - Pool für wiederverwendbare VBOs/VAOs für Chunks
"""
import moderngl
import numpy as np
from typing import List, Tuple, Optional, Set
from core import settings


class ChunkVboPool:
    """
    Pool für wiederverwendbare VBOs/VAOs für Chunks.
    
    Erstellt beim Start eine feste Anzahl gleich großer VBOs/VAOs und verwaltet
    deren Wiederverwendung, um die Performance zu verbessern.
    """
    
    def __init__(self, ctx: moderngl.Context, program: moderngl.Program, pool_size: int = 100):
        """
        Initialize VBO/VAO Pool
        
        Args:
            ctx: ModernGL context
            program: Shader program for VAO creation
            pool_size: Number of VBOs/VAOs to create in the pool (default: 100)
        """
        self.ctx = ctx
        self.program = program
        self.pool_size = pool_size
        
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
    
    def _initialize_pool(self):
        """Create all VBOs/VAOs in the pool"""
        for i in range(self.pool_size):
            # Create empty buffer with correct size
            vbo = self.ctx.buffer(reserve=self.buffer_size_bytes)
            
            # Create VAO with the buffer
            # Format: 2 floats for position, 1 float for color_index, 2 floats for texcoord, 1 float for use_texture
            vao = self.ctx.vertex_array(
                self.program,
                [(vbo, "2f 1f 2f 1f", "in_position", "in_color_index", "in_texcoord", "in_use_texture")]
            )
            
            self.pool.append((vbo, vao))
            self.available.add(i)
    
    def acquire(self) -> Optional[Tuple[moderngl.Buffer, moderngl.VertexArray, int]]:
        """
        Acquire a free VBO/VAO from the pool
        
        Returns:
            (vbo, vao, index) tuple if available, None if pool is exhausted
        """
        if not self.available:
            # Pool exhausted - return None (caller should handle this)
            return None
        
        # Get first available buffer
        index = next(iter(self.available))
        self.available.remove(index)
        self.in_use.add(index)
        
        vbo, vao = self.pool[index]
        return (vbo, vao, index)
    
    def release(self, index: int):
        """
        Release a VBO/VAO back to the pool
        
        Args:
            index: Index of the buffer to release
        """
        if index in self.in_use:
            self.in_use.remove(index)
            self.available.add(index)
    
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
    
    def get_stats(self) -> dict:
        """Get pool statistics"""
        return {
            'pool_size': self.pool_size,
            'available': len(self.available),
            'in_use': len(self.in_use),
            'buffer_size_bytes': self.buffer_size_bytes,
            'vertex_count_per_chunk': self.vertex_count_per_chunk
        }
    
    def cleanup(self):
        """Release all buffers and clean up resources"""
        # Release all buffers
        for index in list(self.in_use):
            self.release(index)
        
        # Release all VBOs/VAOs
        for vbo, vao in self.pool:
            vbo.release()
            vao.release()
        
        self.pool.clear()
        self.available.clear()
        self.in_use.clear()

