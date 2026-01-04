"""
ModernGL Renderer: GPU-beschleunigtes Rendering für Chunks und Sprites
"""
import moderngl
import numpy as np
import queue
from typing import List, Tuple, Optional
from core import settings
from view.chunk_vbo_pool import ChunkVboPool
from view.tile_color_palette import TileColorPalette
from view.unified_texture_manager import UnifiedTextureManager


class ModernGLRenderer:
    """GPU-beschleunigter Renderer für Chunks und Sprites"""
    
    def __init__(self, ctx: moderngl.Context, screen_width: int, screen_height: int, use_pyglet=False, diagnostics=None):
        """
        Initialize ModernGL Renderer
        
        Args:
            ctx: ModernGL context
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
            use_pyglet: If True, use pyglet coordinate system (Y up), else Pygame (Y down)
            diagnostics: Optional DiagnosticsService instance for logging
        """
        self.ctx = ctx
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.use_pyglet = use_pyglet
        self.current_zoom = 1.0  # Current zoom level (1.0 = 100%)
        self.diagnostics = diagnostics  # Store diagnostics service for logging
        
        # Load shaders
        self.chunk_program = self._load_chunk_shader()
        self.sprite_program = self._load_sprite_shader()
        self.ui_program = self._load_ui_shader()
        
        # Initialize texture manager (may fail if assets don't exist, that's OK)
        try:
            self.tile_texture_manager = UnifiedTextureManager(ctx, diagnostics=self.diagnostics)
            if self.tile_texture_manager.texture_atlas:
                if self.diagnostics:
                    self.diagnostics.info("ModernGLRenderer", 
                        f"Texture atlas initialized: {self.tile_texture_manager.atlas_size}x{self.tile_texture_manager.atlas_size}, "
                        f"textures={len(self.tile_texture_manager.texture_coords)}")
            else:
                if self.diagnostics:
                    self.diagnostics.warning("ModernGLRenderer", 
                        "Texture atlas is None after initialization - textures will not be available")
        except Exception as e:
            if self.diagnostics:
                self.diagnostics.warning("ModernGLRenderer", f"Failed to initialize texture manager: {e}")
            else:
                import traceback
                traceback.print_exc()
            self.tile_texture_manager = None
        
        # Decoration textures are now loaded via UnifiedTextureManager (integrated into atlas)
        # No separate DecorationTextureManager needed
        
        # Initialize item texture manager
        try:
            from view.item_texture_manager import ItemTextureManager
            self.item_texture_manager = ItemTextureManager(ctx, diagnostics=self.diagnostics)
            if self.diagnostics:
                self.diagnostics.info("ModernGLRenderer", "Item texture manager initialized")
        except Exception as e:
            if self.diagnostics:
                self.diagnostics.warning("ModernGLRenderer", f"Failed to initialize item texture manager: {e}")
            else:
                import traceback
                traceback.print_exc()
            self.item_texture_manager = None
        
        # No projection matrix needed - vertices are converted to NDC directly
        # self._setup_projection(use_pyglet=use_pyglet)  # DISABLED: Simplified shader doesn't use matrices
        
        # Chunk buffer cache (like Pygame surface cache)
        # IMPORTANT: Buffers contain world coordinates only. Camera and zoom are applied via shader uniforms,
        # so buffers don't need to be invalidated when camera or zoom changes. Only chunk data changes
        # (tile modifications) require buffer invalidation.
        self.chunk_buffers = {}  # (chunk_x, chunk_y) -> (vbo, vao, vertex_count, pool_index)
        self.chunk_dirty = set()  # Set[(chunk_x, chunk_y)] - Chunks, deren Daten sich geändert haben
        
        # Cache für CPU-seitig vorbereitete Vertex-Daten
        self.prepared_chunk_vertices = {}  # Dict[(chunk_x, chunk_y), np.ndarray]
        self.last_camera_pos = (0.0, 0.0)  # Track camera changes (for reference, no invalidation needed)
        self.last_zoom = 1.0  # Track zoom changes (for reference, no invalidation needed)
        
        # Upload-Queue: ChunkManager legt fertige Preps hier rein, Renderer konsumiert mit hartem Limit
        import queue
        self.pending_uploads = queue.Queue()  # Queue of (chunk_key, vertex_array) tuples
        
        # Merged chunk buffer for batched rendering (single draw call)
        self._merged_chunk_vbo = None
        self._merged_chunk_vao = None
        self._merged_chunk_vertex_count = 0
        self._merged_chunks_hash = None  # Hash of chunk keys to detect changes
        
        # Region-based rebuild tracking
        self.needs_region_rebuild = False  # Flag für vollständigen Rebuild beim Region-Wechsel
        self._current_region_window = None  # Track aktuelles Region-Fenster
        
        # Incremental update tracking for merged buffer
        self._merged_chunk_map = {}  # (chunk_x, chunk_y) -> buffer_offset (in bytes)
        self._merged_chunk_order = []  # Ordered list of chunk keys (for consistent ordering)
        self._merged_max_chunks = self._calculate_max_chunks()  # Maximum chunks that can fit in buffer
        self._merged_vertex_size_bytes = self._calculate_vertex_size_bytes()  # Size of one chunk's vertices in bytes
        
        # Feature-Flag: Merged-Buffer Rendering
        self.use_merged_chunk_buffer = True  # notwendig für rendering, da pipeline vollständig migriert
        self.merged_buffer_min_chunk_threshold = 40  # erst ab so vielen Chunks aktiv
        
        # Initialize tile color palette (before pool, as pool needs correct buffer size)
        self.tile_color_palette = TileColorPalette()
        
        # Initialize VBO/VAO pool for chunk buffers (adaptive sizing)
        self.chunk_vbo_pool = ChunkVboPool(ctx, self.chunk_program, pool_size=100, diagnostics=self.diagnostics)
        
        # OPTIMIZATION Phase 4.2: GPU Time Tracking with ModernGL Query Objects
        # Query objects for measuring GPU render times
        try:
            self.gpu_query_chunks = ctx.query(samples=True, time=True, primitives=True)
            self.gpu_query_decorations = ctx.query(samples=True, time=True, primitives=True)
            self.gpu_query_shadows = ctx.query(samples=True, time=True, primitives=True)
            self.gpu_query_total = ctx.query(samples=True, time=True, primitives=True)
            self.gpu_queries_available = True
        except Exception as e:
            # Query objects not available (older OpenGL version or driver issue)
            self.gpu_query_chunks = None
            self.gpu_query_decorations = None
            self.gpu_query_shadows = None
            self.gpu_query_total = None
            self.gpu_queries_available = False
            if self.diagnostics:
                self.diagnostics.warning("ModernGLRenderer", f"GPU queries not available: {e}")
        
        # Update palette uniform in shader
        self._update_palette_uniform(self.chunk_program)
    
    def _calculate_max_chunks(self) -> int:
        """Calculate maximum number of chunks that can be visible at once"""
        # Estimate based on maximum screen size and minimum zoom
        # At zoom 0.5 (zoomed out), we see more chunks
        min_zoom = 0.5
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        
        # Calculate visible chunks at minimum zoom with padding
        visible_width_chunks = int((self.screen_width / min_zoom) / chunk_size_pixels) + 4  # +2 padding on each side
        visible_height_chunks = int((self.screen_height / min_zoom) / chunk_size_pixels) + 4
        
        max_chunks = visible_width_chunks * visible_height_chunks
        # Add safety margin (50% more)
        return int(max_chunks * 1.5)
    
    def _calculate_vertex_size_bytes(self) -> int:
        """Calculate size of one chunk's vertex data in bytes"""
        chunk_size = settings.CHUNK_SIZE
        base_vertices_per_chunk = chunk_size * chunk_size * 6  # 6 vertices per tile
        # Account for overlays: worst case is 2x vertices (every tile has overlay)
        max_vertices_per_chunk = base_vertices_per_chunk * 2  # Double for overlays
        floats_per_vertex = 6  # 2 position + 1 color_index + 2 texcoord + 1 use_texture
        bytes_per_float = 4
        return max_vertices_per_chunk * floats_per_vertex * bytes_per_float
    
    def _initialize_merged_buffer(self):
        """Initialize merged chunk buffer at maximum size"""
        max_buffer_size = self._merged_max_chunks * self._merged_vertex_size_bytes
        
        # Create buffer with maximum size (reserve space, but don't write data yet)
        self._merged_chunk_vbo = self.ctx.buffer(reserve=max_buffer_size)
        
        # Create VAO for merged buffer
        self._merged_chunk_vao = self.ctx.vertex_array(
            self.chunk_program,
            [(self._merged_chunk_vbo, "2f 1f 2f 1f", "in_position", "in_color_index", "in_texcoord", "in_use_texture")]
        )
        
        # Initialize tracking structures
        self._merged_chunk_map = {}
        self._merged_chunk_order = []
        
        # Sprite texture cache
        self.sprite_textures = {}  # sprite_id -> texture
        
        # UI texture cache (for text/menus)
        self.ui_textures = {}  # text_id -> texture
        
        # View matrix (updated per frame) - initialize to identity
        self.view_matrix = np.eye(4, dtype=np.float32)
        self.view_matrix = np.eye(4, dtype=np.float32)
        
    def _load_sprite_shader(self) -> moderngl.Program:
        """Load sprite rendering shader"""
        vertex_shader = """
        #version 330 core
        
        in vec2 in_position;
        in vec2 in_texcoord;
        in vec2 in_sprite_offset;
        
        uniform mat4 projection;
        uniform mat4 view;
        
        out vec2 frag_texcoord;
        
        void main() {
            vec2 world_pos = in_position + in_sprite_offset;
            gl_Position = projection * view * vec4(world_pos, 0.0, 1.0);
            frag_texcoord = in_texcoord;
        }
        """
        
        fragment_shader = """
        #version 330 core
        
        in vec2 frag_texcoord;
        uniform sampler2D sprite_texture;
        uniform vec3 sprite_color;
        uniform bool use_texture;
        
        out vec4 out_color;
        
        void main() {
            if (use_texture) {
                out_color = texture(sprite_texture, frag_texcoord);
            } else {
                out_color = vec4(sprite_color / 255.0, 1.0);
            }
        }
        """
        
        try:
            program = self.ctx.program(
                vertex_shader=vertex_shader,
                fragment_shader=fragment_shader
            )
            if self.diagnostics:
                self.diagnostics.info("ModernGL", "Sprite shader compiled successfully")
            return program
        except Exception as e:
            if self.diagnostics:
                self.diagnostics.error("ModernGL", f"Error compiling sprite shader: {e}")
            else:
                import traceback
                traceback.print_exc()
            raise
    
    def _load_ui_shader(self) -> moderngl.Program:
        """Load UI rendering shader (for text/menus)"""
        # Same as sprite shader but for UI elements
        return self._load_sprite_shader()
    
    def _load_chunk_shader(self) -> moderngl.Program:
        """Load chunk rendering shader with view matrix, zoom support, textures and color palette"""
        # Shader applies view matrix and zoom transformation on GPU
        # Supports both textures and color palette fallback
        vertex_shader = """
        #version 330 core
        
        in vec2 in_position;      // Weltkoordinaten in Pixeln
        in float in_color_index;
        in vec2 in_texcoord;
        in float in_use_texture;
        
        uniform float viewport_min_x;
        uniform float viewport_max_x;
        uniform float viewport_min_y;
        uniform float viewport_max_y;
        
        out float frag_color_index;
        out vec2 frag_texcoord;
        out float frag_use_texture;
        
        void main() {
            // Direct mapping from world coordinates to NDC using viewport bounds
            // Same transformation as decorations use
            float viewport_width = viewport_max_x - viewport_min_x;
            float viewport_height = viewport_max_y - viewport_min_y;
            
            // Safety check: avoid division by zero
            if (viewport_width <= 0.0) viewport_width = 1.0;
            if (viewport_height <= 0.0) viewport_height = 1.0;
            
            float ndc_x = 2.0 * (in_position.x - viewport_min_x) / viewport_width - 1.0;
            float ndc_y = 1.0 - 2.0 * (in_position.y - viewport_min_y) / viewport_height;  // Y-flip for pyglet
            
            gl_Position = vec4(ndc_x, ndc_y, 0.0, 1.0);
            frag_color_index = in_color_index;
            frag_texcoord = in_texcoord;
            frag_use_texture = in_use_texture;
        }
        """
        
        fragment_shader = """
        #version 330 core
        
        in float frag_color_index;
        in vec2 frag_texcoord;
        in float frag_use_texture;
        
        uniform vec3 color_palette[256];  // Color palette (max 256 colors)
        uniform int palette_size;        // Actual palette size
        uniform sampler2D tile_texture;  // Tile texture (if available)
        
        out vec4 out_color;
        
        void main() {
            if (frag_use_texture > 0.5) {
                // Use texture
                out_color = texture(tile_texture, frag_texcoord);
            } else {
                // Use color palette
                int index = int(frag_color_index);
                // Clamp index to valid range
                if (index < 0) index = 0;
                if (index >= palette_size) index = palette_size - 1;
                
                vec3 color = color_palette[index];
                out_color = vec4(color, 1.0);
            }
        }
        """
        
        program = self.ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=fragment_shader
        )
        
        # Initialize palette uniform (will be updated when palette changes)
        self._update_palette_uniform(program)
        
        return program
    
    def _update_palette_uniform(self, program: moderngl.Program = None):
        """Update color palette uniform in shader"""
        if not hasattr(self, 'tile_color_palette'):
            return
        
        if program is None:
            program = self.chunk_program
        
        palette_normalized = self.tile_color_palette.get_palette_normalized()
        palette_size = self.tile_color_palette.get_palette_size()
        
        # Create array with 256 entries (pad with zeros if needed)
        palette_array = np.zeros((256, 3), dtype=np.float32)
        palette_array[:palette_size] = palette_normalized
        
        # Set uniform
        if 'color_palette' in program:
            program['color_palette'].write(palette_array.tobytes())
        if 'palette_size' in program:
            program['palette_size'].value = palette_size
    
    def _setup_projection(self, use_pyglet=False):
        """Setup orthographic projection matrix
        
        Args:
            use_pyglet: If True, use pyglet coordinate system (Y up), else Pygame (Y down)
        """
        # Orthographic projection: maps screen coordinates to NDC [-1, 1]
        # Projection matrix transforms screen space [0, width] x [0, height] to NDC [-1, 1]
        # NDC: (-1,-1) bottom-left, (1,1) top-right
        
        if use_pyglet:
            # Pyglet: (0,0) bottom-left, Y increases upward
            # Map [0, width] -> [-1, 1] for X: x_ndc = 2*x_screen/width - 1
            # Map [0, height] -> [-1, 1] for Y: y_ndc = 2*y_screen/height - 1
            # Matrix form: [scale_x, 0, 0, offset_x], [0, scale_y, 0, offset_y]
            # scale_x = 2/width, offset_x = -1
            # For pyglet, flip Y in projection (world Y-down -> NDC Y-up)
            # Map [0, width] -> [-1, 1] for X: x_ndc = 2*x_screen/width - 1
            # Map [0, height] -> [1, -1] for Y: y_ndc = -2*y_screen/height + 1 (flip Y)
            proj = np.array([
                [2.0 / self.screen_width, 0.0, 0.0, -1.0],
                [0.0, -2.0 / self.screen_height, 0.0, 1.0],  # Flip Y for pyglet
                [0.0, 0.0, -1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0]
            ], dtype=np.float32)
        else:
            # Pygame: (0,0) top-left, Y increases downward
            # Map [0, width] -> [-1, 1] for X: x_ndc = 2*x_screen/width - 1
            # Map [0, height] -> [1, -1] for Y: y_ndc = -2*y_screen/height + 1 (flip Y)
            proj = np.array([
                [2.0 / self.screen_width, 0.0, 0.0, -1.0],
                [0.0, -2.0 / self.screen_height, 0.0, 1.0],
                [0.0, 0.0, -1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0]
            ], dtype=np.float32)
        
        # Chunk shader doesn't use matrices anymore (simplified like test_render.py)
        # self.chunk_program['projection'].write(proj.tobytes())  # DISABLED
        if self.sprite_program and 'projection' in self.sprite_program:
            self.sprite_program['projection'].write(proj.tobytes())
        if self.ui_program and 'projection' in self.ui_program:
            self.ui_program['projection'].write(proj.tobytes())
    
    def _init_chunk_buffers(self):
        """Initialize vertex buffers for chunk rendering"""
        # Buffers will be created dynamically per frame
        # This is just a placeholder
        pass
    
    def update_view(self, camera_x: float, camera_y: float, zoom: float = 1.0):
        """
        Update view matrix based on camera position
        
        Args:
            camera_x: Camera X position in world coordinates
            camera_y: Camera Y position in world coordinates
                - Pygame: (0,0) top-left, Y increases downward
                - Pyglet: (0,0) bottom-left, Y increases upward
            zoom: Zoom factor (1.0 = 100%, 1.5 = 150% nah, 0.75 = 75% weit weg)
        """
        # Store zoom for shader uniform
        self.current_zoom = zoom
        
        # Store camera position and zoom for shader uniforms
        # Buffers are now created with world coordinates only, so they don't need to be
        # invalidated when camera moves or zoom changes - zoom is applied via shader uniform
        camera_pos = (camera_x, camera_y)
        if zoom != self.last_zoom:
            # No buffer invalidation needed - zoom is applied via shader uniform, buffers contain world coordinates
            self.last_zoom = zoom
        self.last_camera_pos = camera_pos
        
        # Calculate viewport bounds using central utility (same as decorations)
        from core.zoom_utils import get_viewport_bounds
        from core import settings
        
        viewport_min_x, viewport_max_x, viewport_min_y, viewport_max_y = get_viewport_bounds(
            self.screen_width, self.screen_height, camera_x, camera_y, zoom
        )
        
        # Expand viewport bounds to match chunk padding (4 chunks)
        # This ensures chunks loaded with padding are not clipped by the shader
        # NOTE: We need extra padding to account for chunk boundaries (chunks extend to chunk_x+1, chunk_y+1)
        chunk_size_pixels = settings.CHUNK_SIZE * settings.TILE_SIZE
        padding_chunks = 4
        padding_pixels = padding_chunks * chunk_size_pixels
        
        # Add extra padding to account for chunk boundaries (one full chunk extra on each side)
        # This ensures that chunks at the edge (chunk_x+1, chunk_y+1) are also included
        extra_padding = chunk_size_pixels
        padding_pixels = padding_pixels + extra_padding
        
        # Store expanded viewport bounds for chunks (to match padding)
        # IMPORTANT: Use the same padding calculation as WorldController.get_visible_chunks()
        self.viewport_min_x = viewport_min_x - padding_pixels
        self.viewport_max_x = viewport_max_x + padding_pixels
        self.viewport_min_y = viewport_min_y - padding_pixels
        self.viewport_max_y = viewport_max_y + padding_pixels
        
        # Debug: Verify padding calculation
        if self.diagnostics:
            if not hasattr(self, '_padding_debug_counter'):
                self._padding_debug_counter = 0
            self._padding_debug_counter += 1
            if self._padding_debug_counter <= 5 or self._padding_debug_counter % 60 == 0:
                self.diagnostics.debug(
                    "ModernGLRenderer",
                    f"Viewport padding: padding_chunks={padding_chunks}, "
                    f"chunk_size_pixels={chunk_size_pixels}, padding_pixels={padding_pixels}, "
                    f"original=({viewport_min_x:.1f},{viewport_max_x:.1f},{viewport_min_y:.1f},{viewport_max_y:.1f}), "
                    f"expanded=({self.viewport_min_x:.1f},{self.viewport_max_x:.1f},{self.viewport_min_y:.1f},{self.viewport_max_y:.1f})"
                )
        
        # Store original viewport bounds for decorations (they use their own culling)
        self.viewport_min_x_original = viewport_min_x
        self.viewport_max_x_original = viewport_max_x
        self.viewport_min_y_original = viewport_min_y
        self.viewport_max_y_original = viewport_max_y
        
        # View matrix transforms world coordinates to screen coordinates
        # We want camera to be at screen center
        # Screen center in pixels
        screen_center_x = self.screen_width / 2.0
        screen_center_y = self.screen_height / 2.0
        
        # Transform: world -> screen
        # Translate world so camera is at screen center
        # For a point at world position (world_x, world_y):
        # screen_x = world_x - camera_x + screen_center_x
        # screen_y = world_y - camera_y + screen_center_y (for pyglet, Y up)
        # This can be written as: screen = world + translate, where:
        # translate_x = screen_center_x - camera_x
        # translate_y = screen_center_y - camera_y
        translate_x = screen_center_x - camera_x
        
        # TEMPORARY DEBUG: Always use pyglet Y-translation to test if this fixes the horizontal cut
        translate_y = screen_center_y - camera_y
        # Original code (commented out for debugging):
        # if self.use_pyglet:
        #     # Pyglet: Y increases upward, but world coordinates use Pygame system (Y down)
        #     # Y-flip happens in shader, so view matrix is normal
        #     translate_y = screen_center_y - camera_y
        # else:
        #     # Pygame: Y increases downward
        #     translate_y = camera_y - screen_center_y
        
        # Create view matrix: translate world coordinates to screen coordinates
        # This moves everything so camera is at screen center
        self.view_matrix = np.array([
            [1.0, 0.0, 0.0, translate_x],
            [0.0, 1.0, 0.0, translate_y],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]
        ], dtype=np.float32)
        
        # Update shader uniforms for view matrix (chunk shader now uses uniforms)
        if self.chunk_program:
            # Set view translation (camera offset)
            if 'view_translation' in self.chunk_program:
                self.chunk_program['view_translation'].value = (float(translate_x), float(translate_y))
            
            # Set viewport bounds for new shader-based transformation
            if 'viewport_min_x' in self.chunk_program:
                self.chunk_program['viewport_min_x'].value = float(self.viewport_min_x)
            if 'viewport_max_x' in self.chunk_program:
                self.chunk_program['viewport_max_x'].value = float(self.viewport_max_x)
            if 'viewport_min_y' in self.chunk_program:
                self.chunk_program['viewport_min_y'].value = float(self.viewport_min_y)
            if 'viewport_max_y' in self.chunk_program:
                self.chunk_program['viewport_max_y'].value = float(self.viewport_max_y)
            
            # Debug: Verify viewport bounds are set correctly in shader
            if self.diagnostics:
                if not hasattr(self, '_shader_viewport_debug_counter'):
                    self._shader_viewport_debug_counter = 0
                self._shader_viewport_debug_counter += 1
                if self._shader_viewport_debug_counter <= 5 or self._shader_viewport_debug_counter % 60 == 0:
                    # Read back shader uniform values to verify they're set correctly
                    shader_viewport_min_x = self.chunk_program['viewport_min_x'].value if 'viewport_min_x' in self.chunk_program else None
                    shader_viewport_max_x = self.chunk_program['viewport_max_x'].value if 'viewport_max_x' in self.chunk_program else None
                    shader_viewport_min_y = self.chunk_program['viewport_min_y'].value if 'viewport_min_y' in self.chunk_program else None
                    shader_viewport_max_y = self.chunk_program['viewport_max_y'].value if 'viewport_max_y' in self.chunk_program else None
                    
                    self.diagnostics.debug(
                        "ModernGLRenderer",
                        f"Shader viewport bounds: min_x={shader_viewport_min_x:.1f}, max_x={shader_viewport_max_x:.1f}, "
                        f"min_y={shader_viewport_min_y:.1f}, max_y={shader_viewport_max_y:.1f}, "
                        f"stored: min_x={self.viewport_min_x:.1f}, max_x={self.viewport_max_x:.1f}, "
                        f"min_y={self.viewport_min_y:.1f}, max_y={self.viewport_max_y:.1f}"
                    )
            
            # Debug-Logging für Kamera (1 Frame pro Sekunde bei 60 FPS)
            if self.diagnostics:
                if not hasattr(self, '_camera_debug_counter'):
                    self._camera_debug_counter = 0
                self._camera_debug_counter += 1
                
                # Log every 60 frames (once per second at 60 FPS)
                if self._camera_debug_counter % 60 == 0:
                    self.diagnostics.debug(
                        "ModernGLRenderer",
                        f"view: cam=({camera_x:.1f},{camera_y:.1f}), "
                        f"trans=({translate_x:.1f},{translate_y:.1f}), "
                        f"zoom={zoom:.2f}, screen=({self.screen_width},{self.screen_height}), "
                        f"viewport=({self.viewport_min_x:.1f},{self.viewport_max_x:.1f},{self.viewport_min_y:.1f},{self.viewport_max_y:.1f})"
                    )
            
            # Store current zoom (for compatibility, but not used in shader)
            self.current_zoom = zoom
        
        # Sprite shader still uses view matrix
        if self.sprite_program and 'view' in self.sprite_program:
            self.sprite_program['view'].write(self.view_matrix.tobytes())
    
    def _create_chunk_buffer(self, chunk_x: int, chunk_y: int, tiles: List[List[dict]]):
        """
        Create or update GPU buffer for a chunk (cached)
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
            tiles: 15x15 grid of tile dictionaries
        
        Returns:
            (vbo, vao, vertex_count) tuple
        """
        chunk_key = (chunk_x, chunk_y)
        
        # Wenn Buffer existiert und Chunk nicht dirty ist, einfach zurückgeben
        if chunk_key in self.chunk_buffers and chunk_key not in self.chunk_dirty:
            vbo, vao, vertex_count, pool_index = self.chunk_buffers[chunk_key]
            return (vbo, vao, vertex_count)
        
        # Ab hier: neu oder dirty -> GPU-Daten neu aufbauen
        # Wenn Chunk dirty ist und bereits Buffer existiert, alten Buffer freigeben
        if chunk_key in self.chunk_buffers:
            old_vbo, old_vao, old_vertex_count, old_pool_index = self.chunk_buffers[chunk_key]
            # Release buffer back to pool if it came from pool
            if old_pool_index is not None and old_pool_index >= 0:
                self.chunk_vbo_pool.release_chunk(chunk_key)
            else:
                # Manually created buffer or temporary buffer - release normally
                old_vao.release()
                old_vbo.release()
            # Remove from cache (will be re-added below)
            del self.chunk_buffers[chunk_key]
        
        # Check if vertices are already prepared
        # IMPORTANT: Always re-prepare if chunk is dirty (textures might have changed)
        if chunk_key in self.prepared_chunk_vertices and chunk_key not in self.chunk_dirty:
            vertex_array = self.prepared_chunk_vertices[chunk_key]
            vertex_count = len(vertex_array)
        else:
            # Kein Emergency-Prep mehr: Chunk wird in diesem Frame nicht gerendert
            # Wird im nächsten Frame gerendert, wenn prepared_chunk_vertices verfügbar ist
            return None
        
        # Buffer aus Pool holen (mit Recycling)
        vbo, vao, pool_index = self.chunk_vbo_pool.get_vbo_for_chunk(chunk_key)
        self.chunk_vbo_pool.write_data(vbo, vertex_array)
        self.chunk_buffers[chunk_key] = (vbo, vao, vertex_count, pool_index)
        
        # Nach Upload ist der Chunk wieder "clean"
        self.mark_chunk_clean(chunk_x, chunk_y)
        
        return (vbo, vao, vertex_count)
    
    def _process_pending_uploads(self, max_uploads_per_frame: int = 2) -> int:
        """
        Konsumiert Upload-Queue mit hartem Limit.
        Erstellt/aktualisiert VBOs aus prepared vertices.
        
        Args:
            max_uploads_per_frame: Maximal 3 Chunks pro Frame (aus Settings)
        
        Returns:
            Anzahl hochgeladener Chunks
        """
        uploads_this_frame = 0
        
        while uploads_this_frame < max_uploads_per_frame:
            if self.pending_uploads.empty():
                break
            
            try:
                chunk_key, vertex_array = self.pending_uploads.get_nowait()
                
            except queue.Empty:
                break
            
            # VBO erstellen/aktualisieren (kein Vertex-Bau mehr hier)
            if self._upload_chunk_vertices(chunk_key, vertex_array):
                uploads_this_frame += 1
        
        return uploads_this_frame
    
    def _upload_chunk_vertices(self, chunk_key: Tuple[int, int], vertex_array: np.ndarray) -> bool:
        """
        Erstellt/aktualisiert VBO aus vertex_array.
        Nutzt chunk_vbo_pool für Buffer-Management.
        
        Args:
            chunk_key: (chunk_x, chunk_y) tuple
            vertex_array: Prepared vertex array (numpy array)
        
        Returns:
            True if upload successful, False otherwise
        """
        chunk_x, chunk_y = chunk_key
        
        
        # Store in prepared_chunk_vertices cache
        self.prepared_chunk_vertices[chunk_key] = vertex_array
        
        # If buffer exists and chunk is not dirty, update it
        if chunk_key in self.chunk_buffers and chunk_key not in self.chunk_dirty:
            vbo, vao, vertex_count, pool_index = self.chunk_buffers[chunk_key]
            # Update existing buffer
            self.chunk_vbo_pool.write_data(vbo, vertex_array)
            # Update vertex count
            self.chunk_buffers[chunk_key] = (vbo, vao, len(vertex_array), pool_index)
            self.chunk_dirty.discard(chunk_key)
            return True
        
        # If chunk is dirty and buffer exists, release old buffer
        if chunk_key in self.chunk_buffers:
            old_vbo, old_vao, old_vertex_count, old_pool_index = self.chunk_buffers[chunk_key]
            # Release buffer back to pool if it came from pool
            if old_pool_index is not None and old_pool_index >= 0:
                self.chunk_vbo_pool.release_chunk(chunk_key)
            else:
                # Manually created buffer - release normally
                old_vao.release()
                old_vbo.release()
            del self.chunk_buffers[chunk_key]
        
        # Get buffer from pool (with recycling)
        vbo, vao, pool_index = self.chunk_vbo_pool.get_vbo_for_chunk(chunk_key)
        self.chunk_vbo_pool.write_data(vbo, vertex_array)
        vertex_count = len(vertex_array)
        self.chunk_buffers[chunk_key] = (vbo, vao, vertex_count, pool_index)
        
        # Mark chunk as clean after upload
        self.mark_chunk_clean(chunk_x, chunk_y)
        
        return True
    
    def _prepare_chunk_vertices(self, chunk_x: int, chunk_y: int, tiles: List[List[dict]]) -> np.ndarray:
        """
        Prepare vertex data for chunk on CPU (can run asynchronously).
        Returns numpy array ready for GPU upload.
        
        This is the same logic as in _create_chunk_buffer(), but without GPU operations.
        """
        chunk_key = (chunk_x, chunk_y)
        
        
        chunk_size = settings.CHUNK_SIZE
        tile_size = float(settings.TILE_SIZE)
        
        # Calculate chunk world position
        chunk_world_x = chunk_x * chunk_size * tile_size
        chunk_world_y = chunk_y * chunk_size * tile_size
        
        # Pre-allocate NumPy array for all vertices (6 vertices per tile)
        max_vertices = chunk_size * chunk_size * 6
        vertices = np.empty((max_vertices, 6), dtype=np.float32)
        idx = 0
        
        # UV cache per chunk (simplified: only tile_id as key)
        uv_cache = {}
        
        # Debug: Track texture usage
        tiles_with_texture = 0
        tiles_without_texture = 0
        
        for tile_y in range(chunk_size):
            for tile_x in range(chunk_size):
                tile = tiles[tile_y][tile_x]
                color = tile.get('color', (100, 100, 100))
                if isinstance(color, list):
                    color = tuple(color)
                
                # Tile position within chunk
                tile_x_pos = tile_x * tile_size
                tile_y_pos = tile_y * tile_size
                
                # Get tile_id to check for texture
                tile_id = tile.get('tile_id') or tile.get('tileid', '')
                
                # Calculate world position for deterministic variant selection
                world_tile_x = int((chunk_world_x + tile_x_pos) / tile_size)
                world_tile_y = int((chunk_world_y + tile_y_pos) / tile_size)
                
                # Get UV coordinates from atlas (with cache)
                # NOTE: Cache key includes world coordinates because variants are selected deterministically
                # Direct texture_tag lookup (no organic growth recalculation)
                uv_coords = None
                has_texture = False
                
                texture_tag = tile.get('texture_tag')
                
                # Primary: Use texture_tag for direct lookup (fastest path)
                if self.tile_texture_manager and texture_tag:
                    # Direct O(1) lookup in texture_coords dictionary
                    uv_coords = self.tile_texture_manager.texture_coords.get(texture_tag)
                    has_texture = uv_coords is not None
                    
                    # Debug: Log missing UVs for texture_tags (only via diagnostics)
                    if texture_tag and uv_coords is None:
                        if not hasattr(self, '_missing_uv_warning_count'):
                            self._missing_uv_warning_count = 0
                        if self._missing_uv_warning_count < 10:
                            available_keys = list(self.tile_texture_manager.texture_coords.keys())[:10]
                            if self.diagnostics:
                                self.diagnostics.warning("ModernGLRenderer",
                                    f"Missing UV for texture_tag='{texture_tag}'. "
                                    f"Available keys (sample): {available_keys}")
                            self._missing_uv_warning_count += 1
                
                # Fallback: If texture_tag is missing or not found, try tile_id lookup
                if not has_texture and self.tile_texture_manager:
                    tile_id = tile.get('tile_id') or tile.get('tileid', '')
                    if tile_id:
                        try:
                            # Use get_texture_coords() as fallback (calculates texture_tag on-the-fly)
                            fallback_uv_coords = self.tile_texture_manager.get_texture_coords(
                                tile_id, world_tile_x, world_tile_y
                            )
                            if fallback_uv_coords:
                                uv_coords = fallback_uv_coords
                                has_texture = True
                                # Optionally assign texture_tag for future use (but don't modify chunk data here)
                                # This is just for rendering, chunk data should be updated elsewhere
                        except Exception:
                            pass  # Fallback failed, use color rendering
                
                # Tiles ohne Textur laufen automatisch in den Farb-Fallback (Farbpalette wird verwendet)
                    
                    # Debug: Track texture usage
                    if has_texture:
                        tiles_with_texture += 1
                    else:
                        tiles_without_texture += 1
                
                # Build texture coordinates
                if has_texture and uv_coords:
                    u0, v0, u1, v1 = uv_coords
                    # OpenGL: (0,0) bottom-left, but PIL/our coords are top-left
                    # texture_coords from TextureAtlasBuilder: (u0, v0, u1, v1) where v0=top, v1=bottom (PIL format)
                    # So we flip V coordinates for OpenGL (v0=bottom, v1=top)
                    # 
                    # NOTE: If textures appear flipped/incorrect, test by temporarily removing the V-flip:
                    # tex_coords = [
                    #     (u0, v0), (u1, v0), (u1, v1),
                    #     (u0, v0), (u1, v1), (u0, v1)
                    # ]
                    tex_coords = [
                        (u0, v1),  # Bottom-left (tex) - flipped: v1 (bottom in PIL) -> bottom in OpenGL
                        (u1, v1),  # Bottom-right (tex)
                        (u1, v0),  # Top-right (tex) - flipped: v0 (top in PIL) -> top in OpenGL
                        (u0, v1),  # Bottom-left (tex)
                        (u1, v0),  # Top-right (tex)
                        (u0, v0),  # Top-left (tex)
                    ]
                else:
                    # No texture available - use default coords (color rendering)
                    tex_coords = [
                        (0.0, 1.0), (1.0, 1.0), (1.0, 0.0),
                        (0.0, 1.0), (1.0, 0.0), (0.0, 0.0)
                    ]
                
                # World position (top-left corner of tile) in pixels
                world_x0 = chunk_world_x + tile_x_pos
                world_y0 = chunk_world_y + tile_y_pos
                world_x1 = world_x0 + tile_size
                world_y1 = world_y0 + tile_size
                
                # Get color index from palette
                color_index = float(self.tile_color_palette.get_color_index(color))
                
                # Use texture flag (1.0 if texture available, 0.0 for color)
                use_texture = 1.0 if has_texture else 0.0
                
                # Create quad vertices using vectorized NumPy operations
                # Format: [in_position (2f), in_color_index (1f), in_texcoord (2f), in_use_texture (1f)]
                # Note: world_y0 = top (smaller Y), world_y1 = bottom (larger Y), matching decoration coordinate system
                # Vertex order matches decorations: bottom-left, bottom-right, top-right, bottom-left, top-right, top-left
                base_vertices = np.array([
                    [world_x0, world_y1, color_index, tex_coords[0][0], tex_coords[0][1], use_texture],  # Bottom-left
                    [world_x1, world_y1, color_index, tex_coords[1][0], tex_coords[1][1], use_texture],  # Bottom-right
                    [world_x1, world_y0, color_index, tex_coords[2][0], tex_coords[2][1], use_texture],  # Top-right
                    [world_x0, world_y1, color_index, tex_coords[3][0], tex_coords[3][1], use_texture],  # Bottom-left
                    [world_x1, world_y0, color_index, tex_coords[4][0], tex_coords[4][1], use_texture],  # Top-right
                    [world_x0, world_y0, color_index, tex_coords[5][0], tex_coords[5][1], use_texture],  # Top-left
                ], dtype=np.float32)
                
                vertices[idx:idx+6] = base_vertices
                idx += 6
        
        # Return only the used portion of the array
        chunk_vertex_array = vertices[:idx]
        
        
        return chunk_vertex_array
    
    def _bind_chunk_texture(self, tiles: List[List[dict]]):
        """
        Bind the texture atlas (all textures are in one atlas).
        
        Args:
            tiles: 15x15 grid of tile dictionaries (unused, kept for compatibility)
        """
        if not hasattr(self, 'tile_texture_manager') or self.tile_texture_manager is None:
            return
        
        # Bind texture atlas (contains all textures)
        # Always bind atlas if it exists, even if some tiles don't have textures
        if self.tile_texture_manager.texture_atlas is None:
            # No atlas available - textures won't be used
            if self.diagnostics:
                self.diagnostics.debug("ModernGLRenderer", "No texture atlas available")
            return
        
        atlas = self.tile_texture_manager.texture_atlas
        if 'tile_texture' in self.chunk_program:
            try:
                atlas.use(0)
                self.chunk_program['tile_texture'].value = 0
            except Exception as e:
                if self.diagnostics:
                    self.diagnostics.error("ModernGLRenderer", f"Failed to bind texture atlas: {e}")
    
    def render_chunks_from_buffers(self, chunks_data: List[Tuple[int, int, List[List[dict]]]]):
        """
        Rendert Chunks nur aus vorhandenen VBOs.
        Chunks ohne VBO werden übersprungen (werden im nächsten Frame hochgeladen).
        
        Args:
            chunks_data: List of (chunk_x, chunk_y, tiles) tuples
        """
        if not chunks_data:
            return
        
        rendered_chunks = []
        
        # GL State
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.ctx.disable(moderngl.DEPTH_TEST)
        self.ctx.disable(moderngl.CULL_FACE)
        
        # Bind texture atlas once for all chunks (if available)
        if hasattr(self, 'tile_texture_manager') and self.tile_texture_manager is not None:
            if self.tile_texture_manager.texture_atlas is not None:
                try:
                    self.tile_texture_manager.texture_atlas.use(0)
                    if 'tile_texture' in self.chunk_program:
                        self.chunk_program['tile_texture'].value = 0
                except Exception as e:
                    if self.diagnostics:
                        self.diagnostics.error("ModernGLRenderer", f"Failed to bind texture atlas: {e}")
        
        # Shader-Uniforms sicherstellen
        if self.chunk_program:
            if hasattr(self, 'viewport_min_x'):
                if 'viewport_min_x' in self.chunk_program:
                    self.chunk_program['viewport_min_x'].value = float(self.viewport_min_x)
                if 'viewport_max_x' in self.chunk_program:
                    self.chunk_program['viewport_max_x'].value = float(self.viewport_max_x)
                if 'viewport_min_y' in self.chunk_program:
                    self.chunk_program['viewport_min_y'].value = float(self.viewport_min_y)
                if 'viewport_max_y' in self.chunk_program:
                    self.chunk_program['viewport_max_y'].value = float(self.viewport_max_y)
        
        # Render only chunks that have VBOs
        for chunk_x, chunk_y, tiles in chunks_data:
            chunk_key = (chunk_x, chunk_y)
            
            # Nur zeichnen, wenn VBO existiert
            buffer = self.chunk_buffers.get(chunk_key)
            if buffer is None:
                continue  # noch nicht hochgeladen
            
            vbo, vao, vertex_count, pool_index = buffer
            if vao and vertex_count > 0:
                vao.render(moderngl.TRIANGLES, vertices=vertex_count)
                rendered_chunks.append(chunk_key)
    
    def set_visible_chunks(self, visible_chunk_keys: set):
        """
        Inform renderer which chunks are currently visible.
        This enables smart buffer management and cleanup.
        
        Args:
            visible_chunk_keys: Set of (chunk_x, chunk_y) tuples for visible chunks
        """
        if not visible_chunk_keys:
            return
        
        # Inform VBO pool about visibility for smart recycling
        self.chunk_vbo_pool.set_visible_chunks(visible_chunk_keys)
        
        # Smart Cleanup: Only check every 10 frames to avoid overhead
        if not hasattr(self, '_cleanup_frame_counter'):
            self._cleanup_frame_counter = 0
        self._cleanup_frame_counter += 1
        
        # Only check cleanup conditions every 10 frames (not every frame)
        if self._cleanup_frame_counter % 10 == 0:
            cached_chunk_keys = set(self.chunk_buffers.keys())
            invisible_chunks = cached_chunk_keys - visible_chunk_keys
            
            # Cleanup conditions: invisible > 50 OR cached > 2 * visible
            if len(invisible_chunks) > 50 or len(cached_chunk_keys) > 2 * len(visible_chunk_keys):
                if self.diagnostics:
                    self.diagnostics.debug(
                        "ModernGLRenderer",
                        f"Cleaning up {len(invisible_chunks)} invisible chunk buffers "
                        f"(visible: {len(visible_chunk_keys)}, cached: {len(cached_chunk_keys)})"
                    )
                self.release_chunk_buffers(list(invisible_chunks))
    
    def log_vbo_pool_stats(self):
        """Log VBO pool statistics for monitoring and optimization."""
        if not self.diagnostics:
            return
        
        stats = self.chunk_vbo_pool.get_stats()
        
        if stats['in_use'] > stats['pool_size'] * 0.9:
            self.diagnostics.warning(
                "ModernGLRenderer",
                f"VBO Pool near capacity: {stats['in_use']}/{stats['pool_size']} in use. "
                f"Peak visible: {stats['peak_visible_chunks']}, "
                f"Recommended pool size: {stats['recommended_pool_size']}"
            )
        else:
            self.diagnostics.info(
                "ModernGLRenderer",
                f"VBO Pool stats: {stats['in_use']}/{stats['pool_size']} in use, "
                f"{stats['available']} available, "
                f"Peak visible: {stats['peak_visible_chunks']}, "
                f"Recycled: {stats['recycled_count']}"
            )
    
    def render_chunks(self, chunks_data: List[Tuple[int, int, List[List[dict]]]], performance_monitor=None, max_new_chunks_per_frame: Optional[int] = None):
        # Validate texture atlas is available
        if not hasattr(self, 'tile_texture_manager') or self.tile_texture_manager is None:
            if not hasattr(self, '_texture_manager_missing_warning'):
                if self.diagnostics:
                    self.diagnostics.warning("ModernGLRenderer", "tile_texture_manager is None - textures will not be rendered")
                self._texture_manager_missing_warning = True
            return
        
        if self.tile_texture_manager.texture_atlas is None:
            if not hasattr(self, '_atlas_missing_warning'):
                if self.diagnostics:
                    self.diagnostics.warning("ModernGLRenderer", 
                        f"Texture atlas is None - textures will not be rendered. "
                        f"texture_coords={len(self.tile_texture_manager.texture_coords) if hasattr(self.tile_texture_manager, 'texture_coords') else 0}")
                self._atlas_missing_warning = True
        """
        Render chunks using GPU (with caching - similar to Pygame surface cache)
        
        Args:
            chunks_data: List of (chunk_x, chunk_y, tiles) tuples
                tiles: 15x15 grid of tile dictionaries with 'color' key
            performance_monitor: Optional PerformanceMonitor instance for timing
            max_new_chunks_per_frame: Optional[int] = None
                Deprecated: No longer used, kept for compatibility
        """
        if not chunks_data:
            return
        
        # OPTIMIZATION Phase 4.2: GPU queries are now handled with CPU timing
        # No need to process pending queries since we're using CPU timing as approximation
        
        # DEBUG: Track what's happening
        skipped_chunks = []
        rendered_chunks = []
        uploaded_chunks = []
        
        import time
        chunk_render_start = time.perf_counter()
        
        # Shader-Uniforms sicherstellen (screen_size und zoom entfernt - werden nicht genutzt)
        if self.chunk_program:
            
            # Ensure viewport bounds are set (in case update_view wasn't called)
            if hasattr(self, 'viewport_min_x'):
                if 'viewport_min_x' in self.chunk_program:
                    self.chunk_program['viewport_min_x'].value = float(self.viewport_min_x)
                if 'viewport_max_x' in self.chunk_program:
                    self.chunk_program['viewport_max_x'].value = float(self.viewport_max_x)
                if 'viewport_min_y' in self.chunk_program:
                    self.chunk_program['viewport_min_y'].value = float(self.viewport_min_y)
                if 'viewport_max_y' in self.chunk_program:
                    self.chunk_program['viewport_max_y'].value = float(self.viewport_max_y)
        
        # GL State
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.ctx.disable(moderngl.DEPTH_TEST)
        self.ctx.disable(moderngl.CULL_FACE)
        
        # Bind texture atlas once for all chunks (if available)
        if hasattr(self, 'tile_texture_manager') and self.tile_texture_manager is not None:
            if self.tile_texture_manager.texture_atlas is not None:
                try:
                    # Bind atlas to texture unit 0
                    self.tile_texture_manager.texture_atlas.use(0)
                    
                    # Set uniform if available
                    uniform_set = False
                    if 'tile_texture' in self.chunk_program:
                        self.chunk_program['tile_texture'].value = 0
                        uniform_set = True
                    
                except Exception as e:
                    if self.diagnostics:
                        self.diagnostics.error("ModernGLRenderer", f"Failed to bind texture atlas: {e}")
                        import traceback
                        self.diagnostics.error("ModernGLRenderer", f"Traceback: {traceback.format_exc()}")
            else:
                # Atlas not initialized - log warning
                if self.diagnostics:
                    if not hasattr(self, '_atlas_warning_logged'):
                        self.diagnostics.warning("ModernGLRenderer", "Texture atlas is None - textures will not be rendered")
                        self._atlas_warning_logged = True
        
        # OPTIMIZATION Phase 4.2: GPU query for chunk rendering
        # ModernGL queries are used as context managers, not with begin()/end()
        # For now, we'll use CPU timing as approximation
        gpu_chunk_start = None
        if self.gpu_queries_available and self.gpu_query_chunks:
            gpu_chunk_start = time.perf_counter()
        
        upload_start_time = time.perf_counter()
        
        # Use merged buffer for batched rendering (single draw call for all chunks)
        # This reduces draw calls from N (one per chunk) to 1 (all chunks in one call)
        chunk_count = len(chunks_data)
        
        # 1) Entscheiden, ob wir grundsätzlich den Merged-Buffer nutzen wollen
        use_merged_buffer = (
            self.use_merged_chunk_buffer and
            chunk_count >= self.merged_buffer_min_chunk_threshold and
            self._merged_max_chunks > 0
        )
        
        # Debug-Logging
        if self.diagnostics:
            if not hasattr(self, '_render_chunks_debug_counter'):
                self._render_chunks_debug_counter = 0
            self._render_chunks_debug_counter += 1
            if self._render_chunks_debug_counter <= 5 or self._render_chunks_debug_counter % 60 == 0:
                chunk_keys = [(cx, cy) for cx, cy, _ in chunks_data]
                chunk_x_range = [cx for cx, _ in chunk_keys]
                chunk_y_range = [cy for _, cy in chunk_keys]
                viewport_info = ""
                if hasattr(self, 'viewport_min_x'):
                    # Show both original and expanded viewport bounds
                    if hasattr(self, 'viewport_min_x_original'):
                        viewport_info = (
                            f", viewport_expanded=({self.viewport_min_x:.1f},{self.viewport_max_x:.1f},"
                            f"{self.viewport_min_y:.1f},{self.viewport_max_y:.1f}), "
                            f"viewport_original=({self.viewport_min_x_original:.1f},{self.viewport_max_x_original:.1f},"
                            f"{self.viewport_min_y_original:.1f},{self.viewport_max_y_original:.1f})"
                        )
                    else:
                        viewport_info = f", viewport=({self.viewport_min_x:.1f},{self.viewport_max_x:.1f},{self.viewport_min_y:.1f},{self.viewport_max_y:.1f})"
                self.diagnostics.debug(
                    "ModernGLRenderer",
                    f"render_chunks: merged={use_merged_buffer}, chunks={chunk_count}, "
                    f"threshold={self.merged_buffer_min_chunk_threshold}, "
                    f"chunk_x_range=[{min(chunk_x_range)}..{max(chunk_x_range)}], "
                    f"chunk_y_range=[{min(chunk_y_range)}..{max(chunk_y_range)}]"
                    f"{viewport_info}"
                )
        
        # Debug: Log viewport bounds for verification
        if self.diagnostics and hasattr(self, 'viewport_min_x'):
            if not hasattr(self, '_viewport_debug_counter'):
                self._viewport_debug_counter = 0
            self._viewport_debug_counter += 1
            
            # Log every 60 frames (once per second at 60 FPS)
            if self._viewport_debug_counter % 60 == 0:
                self.diagnostics.debug(
                    "ModernGLRenderer",
                    f"render_chunks viewport=({self.viewport_min_x:.1f},{self.viewport_max_x:.1f}) "
                    f"({self.viewport_min_y:.1f},{self.viewport_max_y:.1f}), chunks={len(chunks_data)}"
                )
        
        # Initialize upload counters for monitoring
        uploaded_chunks = []
        new_chunks_uploaded = 0  # For compatibility with logging
        dirty_chunks_uploaded = 0  # For compatibility with logging
        
        
        # Phase 1: Process pending uploads (from ChunkManager's preparation queue)
        # This consumes the upload queue that ChunkManager filled in tick_chunk_manager()
        uploads_this_frame = self._process_pending_uploads(max_uploads_per_frame=2)
        
        if use_merged_buffer:
            try:
                # Build or update merged chunk buffer (handles incremental updates automatically)
                # NOTE: Chunks without prepared vertices are skipped (strict policy)
                # Track uploads by checking which chunks were actually written
                chunks_before = len(self._merged_chunk_map)
                self._build_merged_chunk_buffer(chunks_data)
                chunks_after = len(self._merged_chunk_map)
                # Track chunks that were added to buffer
                new_chunks_uploaded = max(0, chunks_after - chunks_before)
                
                # Render all chunks in a single draw call using merged buffer
                if self._merged_chunk_vao is not None and self._merged_chunk_vertex_count > 0:
                    # Atlas is already bound above, just render all chunks at once
                    # Debug: Log actual vertex count being rendered
                    if self.diagnostics:
                        if not hasattr(self, '_render_vertex_count_counter'):
                            self._render_vertex_count_counter = 0
                        self._render_vertex_count_counter += 1
                        if self._render_vertex_count_counter <= 5 or self._render_vertex_count_counter % 60 == 0:
                            self.diagnostics.debug(
                                "ModernGLRenderer",
                                f"Rendering merged buffer: vertex_count={self._merged_chunk_vertex_count}, "
                                f"chunks_in_buffer={len(self._merged_chunk_map)}, "
                                f"chunks_input={len(chunks_data)}"
                            )
                    self._merged_chunk_vao.render(moderngl.TRIANGLES, vertices=self._merged_chunk_vertex_count)
                    rendered_chunks = [(cx, cy) for cx, cy, _ in chunks_data]
                else:
                    # Nichts zu rendern → auf Fallback-Pfad gehen
                    use_merged_buffer = False
                    
            except Exception as e:
                use_merged_buffer = False
                if self.diagnostics:
                    self.diagnostics.warning(
                        "ModernGLRenderer",
                        f"Merged buffer rendering failed, falling back to per-chunk: {e}"
                    )
        
        if not use_merged_buffer:
            # Phase 2: Render only from existing VBOs (per-chunk path)
            # Chunks without VBOs are skipped (will be uploaded in next frame)
            self.render_chunks_from_buffers(chunks_data)
        
        # OPTIMIZATION Phase 4.2: For now, use CPU timing as approximation
        # TODO: Implement proper GPU query usage with context managers when needed
        # ModernGL queries should be used like: with query: render()
        if gpu_chunk_start and performance_monitor:
            # Approximate GPU time using CPU time (will be replaced with actual GPU queries later)
            gpu_chunk_time = (time.perf_counter() - gpu_chunk_start) * 1000  # Convert to ms
            performance_monitor.record_gpu_chunk_render_time(gpu_chunk_time)
        
        upload_time = time.perf_counter() - upload_start_time
        if performance_monitor:
            performance_monitor.record_chunk_upload_time(upload_time)
        
        # DEBUG: Log what happened
        if self.diagnostics and (skipped_chunks or uploaded_chunks):
            self.diagnostics.debug(
                "ModernGLRenderer",
                f"Render: {len(rendered_chunks)} rendered, {len(uploaded_chunks)} uploaded, "
                f"{len(skipped_chunks)} skipped. Total chunks: {len(chunks_data)}"
            )
            if skipped_chunks:
                self.diagnostics.warning(
                    "ModernGLRenderer",
                    f"Skipped chunks (will render next frame): {skipped_chunks[:10]}"
                )
        
        # Monitoring: Log upload stats every 120 frames
        if self.diagnostics:
            if not hasattr(self, '_upload_log_counter'):
                self._upload_log_counter = 0
            self._upload_log_counter += 1
            if self._upload_log_counter % 120 == 0:
                self.diagnostics.debug(
                    "ModernGLRenderer",
                    f"Chunk uploads/frame: uploaded={len(uploaded_chunks)}, "
                    f"skipped={len(skipped_chunks)}, total_visible={len(chunks_data)}"
                )
        
        # Periodisches Logging (z.B. alle 5 Sekunden bei 60 FPS = 300 Frames)
        if self.diagnostics and hasattr(self, '_stats_log_counter'):
            self._stats_log_counter += 1
        else:
            self._stats_log_counter = 0
        
        # Debug output disabled
        # if self._stats_log_counter % 300 == 0:  # Alle 5 Sekunden
        #     stats = self.chunk_vbo_pool.get_stats()
        #     self.diagnostics.info(
        #         "ModernGLRenderer",
        #         f"VBO Pool: {stats['in_use']}/{stats['current_pool_size']} "
        #         f"(peak: {stats['peak_usage']}, target: {stats['target_size']}, "
        #         f"efficiency: {stats['efficiency']:.1%}, expansions: {stats['expansion_count']})"
        #     )
        
        chunk_render_time = time.perf_counter() - chunk_render_start
        if performance_monitor:
            performance_monitor.record_chunk_render_time(chunk_render_time)
    
    def rebuild_region_buffer(self, chunks_data: List[Tuple[int, int, List[List[dict]]]]):
        """
        Vollständiger Rebuild des Merged-Buffers für ein neues Region-Fenster.
        Wird nur beim Region-Wechsel aufgerufen.
        
        Args:
            chunks_data: List of (chunk_x, chunk_y, tiles) tuples
        """
        if self._merged_chunk_vbo is None:
            self._initialize_merged_buffer()
        
        # Alle Chunks mit prepared vertices sammeln
        vertex_chunks = []
        chunk_keys = []
        chunks_without_vertices = []
        chunks_with_vertices = []
        
        for chunk_x, chunk_y, tiles in chunks_data:
            key = (chunk_x, chunk_y)
            va = self.prepared_chunk_vertices.get(key)
            if va is not None:
                vertex_chunks.append(va)
                chunk_keys.append(key)
                chunks_with_vertices.append(key)
            else:
                chunks_without_vertices.append(key)
        
        # Debug: Log chunks without prepared vertices (only via diagnostics)
        if chunks_without_vertices:
            if not hasattr(self, '_rebuild_missing_vertices_logged'):
                if self.diagnostics:
                    self.diagnostics.warning("ModernGLRenderer",
                        f"rebuild_region_buffer: {len(chunks_without_vertices)} chunks without prepared vertices: {chunks_without_vertices[:10]}")
                self._rebuild_missing_vertices_logged = True
        
        if not vertex_chunks:
            self._merged_chunk_vertex_count = 0
            self._merged_chunk_map = {}
            self._merged_chunk_order = []
            # Debug: Log empty rebuild
            if not hasattr(self, '_rebuild_empty_logged'):
                print(f"[ModernGLRenderer] rebuild_region_buffer: No prepared vertices found for {len(chunks_data)} chunks")
                if self.diagnostics:
                    self.diagnostics.warning("ModernGLRenderer",
                        f"rebuild_region_buffer: No prepared vertices found for {len(chunks_data)} chunks")
                self._rebuild_empty_logged = True
            return
        
        # Alle Vertices konkatenieren
        vertices = np.concatenate(vertex_chunks, axis=0)
        
        # Validate vertex data structure
        if len(vertices.shape) != 2 or vertices.shape[1] != 6:
            if self.diagnostics:
                self.diagnostics.error("ModernGLRenderer", 
                    f"ERROR: Invalid vertex shape: {vertices.shape}, expected (N, 6)")
            return
        
        # Buffer komplett neu schreiben
        self._merged_chunk_vbo.write(vertices.tobytes())
        self._merged_chunk_vertex_count = len(vertices)
        
        # Chunk-Map aktualisieren: Offset-Berechnung basiert auf echter Vertexanzahl
        # sizeof(vertex) = vertices.dtype.itemsize * vertices.shape[1]
        # vertices.shape = (num_vertices, num_components) z.B. (N, 6) für 6 floats pro Vertex
        # float32 = 4 bytes, also vertex_size_bytes = 4 * 6 = 24 bytes pro Vertex
        vertex_size_bytes = vertices.dtype.itemsize * vertices.shape[1] if len(vertices.shape) > 1 else vertices.dtype.itemsize
        
        self._merged_chunk_map = {}
        self._merged_chunk_order = chunk_keys
        offset = 0
        for i, key in enumerate(chunk_keys):
            self._merged_chunk_map[key] = offset
            # Echte Vertexanzahl * sizeof(vertex), nicht Worst-Case
            chunk_vertex_count = len(vertex_chunks[i])
            offset += chunk_vertex_count * vertex_size_bytes
        
        # Logging für Debugging
        if self.diagnostics:
            self.diagnostics.info("ModernGLRenderer",
                f"rebuild_region_buffer: chunks_in_buffer={len(chunk_keys)}, "
                f"vertex_count={self._merged_chunk_vertex_count}, "
                f"total_bytes={offset}")
    
    def _build_merged_chunk_buffer(self, chunks_data: List[Tuple[int, int, List[List[dict]]]]):
        """
        Build or incrementally update merged VBO containing all visible chunks for batched rendering.
        
        Uses region-based rebuild: Full rebuild on region switch, incremental updates for dirty chunks.
        
        Args:
            chunks_data: List of (chunk_x, chunk_y, tiles) tuples
        """
        import time
        from core import settings
        
        # Initialize buffer if it doesn't exist
        if self._merged_chunk_vbo is None:
            self._initialize_merged_buffer()
        
        # Check if region rebuild is needed
        if self.needs_region_rebuild:
            # Vollständiger Rebuild beim Region-Wechsel
            self.rebuild_region_buffer(chunks_data)
            self.needs_region_rebuild = False
            return
        
        # Inkrementelle Updates für dirty chunks
        chunk_keys_set = set((chunk_x, chunk_y) for chunk_x, chunk_y, _ in chunks_data)
        dirty_patches_count = 0
        chunks_missing_vertices = []
        chunks_not_in_buffer = []
        
        # Check for new chunks that need to be added to buffer
        new_chunks = []
        for chunk_key in chunk_keys_set:
            if chunk_key in self.prepared_chunk_vertices and chunk_key not in self._merged_chunk_map:
                new_chunks.append(chunk_key)
        
        # If there are new chunks, we need a full rebuild
        if new_chunks:
            # Trigger full rebuild to include new chunks
            self.needs_region_rebuild = True
            self.rebuild_region_buffer(chunks_data)
            self.needs_region_rebuild = False
            return
        
        if self.chunk_dirty:
            # Nur dirty chunks aktualisieren
            for chunk_key in self.chunk_dirty & chunk_keys_set:
                if chunk_key in self.prepared_chunk_vertices:
                    vertex_array = self.prepared_chunk_vertices[chunk_key]
                    offset = self._merged_chunk_map.get(chunk_key)
                    if offset is not None:
                        # Einfaches Update: Offset aus Map, direkt schreiben
                        self._merged_chunk_vbo.write(vertex_array.tobytes(), offset=offset)
                        dirty_patches_count += 1
                    else:
                        chunks_not_in_buffer.append(chunk_key)
                else:
                    chunks_missing_vertices.append(chunk_key)
        
        # Debug: Log chunks missing vertices in dirty update (only via diagnostics)
        if chunks_missing_vertices and not hasattr(self, '_dirty_missing_vertices_logged'):
            if self.diagnostics:
                self.diagnostics.warning("ModernGLRenderer",
                    f"_build_merged_chunk_buffer: {len(chunks_missing_vertices)} dirty chunks without prepared vertices")
            self._dirty_missing_vertices_logged = True
            
            # Logging für Debugging
            if self.diagnostics and dirty_patches_count > 0:
                self.diagnostics.debug("ModernGLRenderer",
                    f"dirty_patches_per_frame: {dirty_patches_count}")
        
        # Clear dirty flags for chunks that were updated
        if dirty_patches_count > 0:
            # Mark updated chunks as clean
            for chunk_key in self.chunk_dirty & chunk_keys_set:
                if chunk_key in self.prepared_chunk_vertices and chunk_key in self._merged_chunk_map:
                    self.chunk_dirty.discard(chunk_key)
    
    def _render_test_quad_ndc(self):
        """Render a test quad directly in NDC coordinates (bypasses all transformations)"""
        # Create a simple shader that outputs NDC coordinates directly
        simple_vertex_shader = """
        #version 330 core
        in vec2 in_position;
        in vec3 in_color;
        out vec3 frag_color;
        void main() {
            gl_Position = vec4(in_position, 0.0, 1.0);
            frag_color = in_color;
        }
        """
        
        simple_fragment_shader = """
        #version 330 core
        in vec3 frag_color;
        out vec4 out_color;
        void main() {
            out_color = vec4(frag_color / 255.0, 1.0);
        }
        """
        
        try:
            simple_program = self.ctx.program(
                vertex_shader=simple_vertex_shader,
                fragment_shader=simple_fragment_shader
            )
        except Exception as e:
            if self.diagnostics:
                self.diagnostics.error("ModernGL", f"Error creating simple shader: {e}")
            return
        
        # Create a red quad in NDC coordinates (center of screen)
        # NDC: (-1,-1) bottom-left, (1,1) top-right
        # Quad from (-0.5, -0.5) to (0.5, 0.5) = center of screen
        test_vertices = np.array([
            # Position (NDC), Color
            [-0.5, -0.5, 255.0, 0.0, 0.0],  # Bottom-left
            [0.5, -0.5, 255.0, 0.0, 0.0],    # Bottom-right
            [0.5, 0.5, 255.0, 0.0, 0.0],     # Top-right
            [-0.5, -0.5, 255.0, 0.0, 0.0],  # Bottom-left
            [0.5, 0.5, 255.0, 0.0, 0.0],     # Top-right
            [-0.5, 0.5, 255.0, 0.0, 0.0],   # Top-left
        ], dtype=np.float32)
        
        test_vbo = self.ctx.buffer(test_vertices.tobytes())
        test_vao = self.ctx.simple_vertex_array(
            simple_program,
            test_vbo,
            'in_position', 'in_color'
        )
        
        test_vao.render(moderngl.TRIANGLES)
        test_vao.release()
        test_vbo.release()
        
        # Test quad rendered
    
    def _invalidate_all_chunk_buffers(self):
        """
        Invalidate all chunk buffers.
        
        WARNING: This method should ONLY be called for:
        - Renderer reset/reinitialization (e.g., shader changes, format changes)
        - Vertex format changes (e.g., new shader attributes)
        - Complete buffer cache invalidation (e.g., after major renderer updates)
        
        DO NOT call this for:
        - Camera position changes (buffers contain world coordinates)
        - Zoom changes (zoom is applied via shader uniform)
        - Individual chunk data changes (use invalidate_chunk() instead)
        
        Buffers contain world coordinates only and are transformed via shader uniforms,
        so they remain valid across camera/zoom changes.
        """
        for chunk_key, buffer_data in list(self.chunk_buffers.items()):
            vbo, vao, vertex_count, pool_index = buffer_data
            # Release buffer back to pool if it came from pool
            if pool_index is not None:
                self.chunk_vbo_pool.release(pool_index)
            else:
                # Manually created buffer (pool exhausted) - release normally
                vao.release()
                vbo.release()
        self.chunk_buffers.clear()
        
        # Invalidate merged buffer (will be rebuilt on next render)
        if self._merged_chunk_vao is not None:
            self._merged_chunk_vao.release()
            self._merged_chunk_vao = None
        if self._merged_chunk_vbo is not None:
            self._merged_chunk_vbo.release()
            self._merged_chunk_vbo = None
        self._merged_chunks_hash = None
        self._merged_chunk_map = {}
        self._merged_chunk_order = []
    
    def reset_renderer(self):
        """
        Reset renderer (invalidates all buffers).
        
        Call this when:
        - Shader programs are reloaded
        - Vertex format changes
        - Renderer needs complete reinitialization
        
        This will force all chunks to be re-uploaded on next render.
        """
        self._invalidate_all_chunk_buffers()
        # Set region rebuild flag for merged buffer
        if hasattr(self, 'needs_region_rebuild'):
            self.needs_region_rebuild = True
            if self.diagnostics:
                self.diagnostics.info("ModernGLRenderer",
                    "Renderer reset: needs_region_rebuild=True")
    
    def invalidate_chunk(self, chunk_x: int, chunk_y: int):
        """Invalidate cached buffer for a chunk (call when chunk changes)"""
        chunk_key = (chunk_x, chunk_y)
        if chunk_key in self.chunk_buffers:
            vbo, vao, vertex_count, pool_index = self.chunk_buffers[chunk_key]
            # Release buffer back to pool if it came from pool
            if pool_index is not None:
                self.chunk_vbo_pool.release(pool_index)
            else:
                # Manually created buffer (pool exhausted) - release normally
                vao.release()
                vbo.release()
            del self.chunk_buffers[chunk_key]
        
        # Mark chunk as dirty when invalidated
        self.chunk_dirty.add(chunk_key)
    
    def release_chunk_buffer(self, chunk_x: int, chunk_y: int):
        """
        Release chunk buffer resources when chunk is no longer visible.
        
        This method should be called when a chunk becomes invisible to free up
        GPU resources and prevent the VBO pool from filling up.
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
        """
        chunk_key = (chunk_x, chunk_y)
        if chunk_key in self.chunk_buffers:
            vbo, vao, vertex_count, pool_index = self.chunk_buffers.pop(chunk_key)
            # Remove from dirty set (chunk is being released, no need to track dirty state)
            self.chunk_dirty.discard(chunk_key)
            
            if pool_index is not None and pool_index >= 0:
                # Return buffer to pool for reuse
                self.chunk_vbo_pool.release_chunk(chunk_key)
            else:
                # Manually created buffer or temporary buffer - release normally
                vao.release()
                vbo.release()
    
    def mark_chunk_dirty(self, chunk_x: int, chunk_y: int):
        """
        Markiere einen Chunk als dirty (Daten haben sich geändert).
        
        Wird extern aufgerufen, wenn sich die Tiles eines Chunks geändert haben
        (z.B. durch Build/Abbau im ChunkManager oder Multiplayer-Updates).
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
        """
        self.chunk_dirty.add((chunk_x, chunk_y))
    
    def mark_chunk_clean(self, chunk_x: int, chunk_y: int):
        """
        Markiere einen Chunk als clean (Daten sind aktuell).
        
        Wird aufgerufen, nachdem ein Chunk erfolgreich aktualisiert wurde.
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
        """
        self.chunk_dirty.discard((chunk_x, chunk_y))
    
    def clear_prepared_chunk(self, chunk_x: int, chunk_y: int):
        """Clear prepared vertex data for a chunk (called when chunk is unloaded)."""
        chunk_key = (chunk_x, chunk_y)
        if chunk_key in self.prepared_chunk_vertices:
            del self.prepared_chunk_vertices[chunk_key]
    
    def is_chunk_dirty(self, chunk_x: int, chunk_y: int) -> bool:
        """
        Prüfe, ob ein Chunk dirty ist (Daten müssen aktualisiert werden).
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
        
        Returns:
            True wenn der Chunk dirty ist, False sonst
        """
        return (chunk_x, chunk_y) in self.chunk_dirty
    
    def release_chunk_buffers(self, chunk_keys: List[Tuple[int, int]]):
        """
        Release VBOs for chunks that are no longer visible (batch operation)
        
        Args:
            chunk_keys: List of (chunk_x, chunk_y) tuples to release
        """
        if not chunk_keys:
            return
        
        released_count = 0
        for chunk_key in chunk_keys:
            if chunk_key in self.chunk_buffers:
                vbo, vao, vertex_count, pool_index = self.chunk_buffers[chunk_key]
                if pool_index is not None and pool_index >= 0:
                    # Buffer from pool
                    self.chunk_vbo_pool.release_chunk(chunk_key)
                else:
                    # Manually created buffer or temporary buffer (index=-1)
                    vao.release()
                    vbo.release()
                del self.chunk_buffers[chunk_key]
                released_count += 1
        
        if released_count > 0 and self.diagnostics:
            self.diagnostics.debug("ModernGLRenderer", 
                f"Released {released_count} chunk buffers")
    
    def cleanup(self):
        """Cleanup all cached buffers"""
        # Release all buffers back to pool
        for chunk_key, buffer_data in list(self.chunk_buffers.items()):
            vbo, vao, vertex_count, pool_index = buffer_data
            if pool_index is not None and pool_index >= 0:
                self.chunk_vbo_pool.release_chunk(chunk_key)
            else:
                # Manually created buffer or temporary buffer - release normally
                vao.release()
                vbo.release()
        self.chunk_buffers.clear()
        
        # Clear dirty tracking
        self.chunk_dirty.clear()
        
        # Release merged chunk buffer
        if self._merged_chunk_vao is not None:
            self._merged_chunk_vao.release()
            self._merged_chunk_vao = None
        if self._merged_chunk_vbo is not None:
            self._merged_chunk_vbo.release()
            self._merged_chunk_vbo = None
        
        # Cleanup pool
        if hasattr(self, 'chunk_vbo_pool'):
            self.chunk_vbo_pool.cleanup()
    
    # Removed: _sprite_surface_to_texture - no longer needed (sprites use color, not textures)
    # def _sprite_surface_to_texture(self, surface) -> moderngl.Texture:
    #     """Convert Pygame surface to ModernGL texture"""
    #     # This method is no longer needed - sprites use color instead of textures
    #     pass
    
    def render_sprites(self, sprites, camera):
        """
        Render sprites using GPU
        
        Args:
            sprites: List of sprites (from core.sprite)
            camera: Camera instance for coordinate transformation
        """
        if not sprites:
            return
        
        # Enable blending
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        
        # Render each sprite (world coordinates, camera transform handled by view matrix)
        for sprite in sprites:
            width, height = sprite.rect.width, sprite.rect.height
            
            # Use world coordinates (camera transform handled by view matrix)
            world_x = sprite.rect.x
            world_y = sprite.rect.y
            
            # Get color (RGB)
            r, g, b = sprite.color[:3] if len(sprite.color) >= 3 else (255, 255, 255)
            
            # Create vertices for sprite quad (colored, no texture)
            # Format: x, y, r, g, b, offset_x, offset_y
            vertices = np.array([
                [0.0, 0.0, r, g, b, world_x, world_y],
                [width, 0.0, r, g, b, world_x, world_y],
                [width, height, r, g, b, world_x, world_y],
                [0.0, 0.0, r, g, b, world_x, world_y],
                [width, height, r, g, b, world_x, world_y],
                [0.0, height, r, g, b, world_x, world_y],
            ], dtype=np.float32)
            
            vbo = self.ctx.buffer(vertices.tobytes())
            vao = self.ctx.simple_vertex_array(
                self.chunk_program,  # Use chunk shader (colored quads)
                vbo,
                'in_position', 'in_color', 'in_chunk_offset'
            )
            
            # Render sprite
            vao.render(moderngl.TRIANGLES)
            
            # Cleanup
            vao.release()
            vbo.release()
    
    def render_ui(self, ui_surfaces: List[Tuple]):
        """
        Render UI elements (text/menus) using GPU
        
        Args:
            ui_surfaces: List of (surface, position) tuples
            TODO: Migrate UI rendering to ModernGL (currently not used)
        """
        if not ui_surfaces:
            return
        
        # Enable blending
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        
        # Use UI shader (same as sprite shader)
        # Render each UI element
        for surface, (x, y) in ui_surfaces:
            ui_id = id(surface)
            
            # Create texture if not cached
            if ui_id not in self.ui_textures:
                texture = self._sprite_surface_to_texture(surface)
                self.ui_textures[ui_id] = texture
            
            texture = self.ui_textures[ui_id]
            width, height = surface.get_size()
            
            # Create vertices for UI element (screen space, no camera transform)
            vertices = np.array([
                [0.0, 0.0, 0.0, 0.0, x, y],
                [width, 0.0, 1.0, 0.0, x, y],
                [width, height, 1.0, 1.0, x, y],
                [0.0, 0.0, 0.0, 0.0, x, y],
                [width, height, 1.0, 1.0, x, y],
                [0.0, height, 0.0, 1.0, x, y],
            ], dtype=np.float32)
            
            vbo = self.ctx.buffer(vertices.tobytes())
            vao = self.ctx.simple_vertex_array(
                self.ui_program,
                vbo,
                'in_position', 'in_texcoord', 'in_sprite_offset'
            )
            
            # Use identity view matrix for UI (screen space)
            identity_view = np.eye(4, dtype=np.float32)
            self.ui_program['view'].write(identity_view.tobytes())
            
            texture.use(0)
            self.ui_program['sprite_texture'] = 0
            self.ui_program['use_texture'] = True
            self.ui_program['sprite_color'] = (255, 255, 255)
            
            vao.render(moderngl.TRIANGLES)
            
            vao.release()
            vbo.release()
    
    def clear(self, r: float = 0.1, g: float = 0.1, b: float = 0.15):
        """Clear the screen"""
        self.ctx.clear(r, g, b)
    
    def resize(self, width: int, height: int):
        """Handle window resize"""
        self.screen_width = width
        self.screen_height = height
        self._setup_projection(use_pyglet=self.use_pyglet)

