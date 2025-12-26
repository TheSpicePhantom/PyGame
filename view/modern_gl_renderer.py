"""
ModernGL Renderer: GPU-beschleunigtes Rendering für Chunks und Sprites
"""
import moderngl
import numpy as np
from typing import List, Tuple, Optional
from core import settings
from view.chunk_vbo_pool import ChunkVboPool
from view.tile_color_palette import TileColorPalette
from view.tile_texture_manager import TileTextureManager


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
            self.tile_texture_manager = TileTextureManager(ctx, diagnostics=self.diagnostics)
            if self.diagnostics and self.tile_texture_manager.texture_atlas:
                self.diagnostics.info("ModernGLRenderer", f"Texture atlas initialized: {self.tile_texture_manager.atlas_size}x{self.tile_texture_manager.atlas_size}")
        except Exception as e:
            if self.diagnostics:
                self.diagnostics.warning("ModernGLRenderer", f"Failed to initialize texture manager: {e}")
            else:
                import traceback
                traceback.print_exc()
            self.tile_texture_manager = None
        
        # No projection matrix needed - vertices are converted to NDC directly
        # self._setup_projection(use_pyglet=use_pyglet)  # DISABLED: Simplified shader doesn't use matrices
        
        # Chunk buffer cache (like Pygame surface cache)
        # IMPORTANT: Buffers contain world coordinates only. Camera and zoom are applied via shader uniforms,
        # so buffers don't need to be invalidated when camera or zoom changes. Only chunk data changes
        # (tile modifications) require buffer invalidation.
        self.chunk_buffers = {}  # (chunk_x, chunk_y) -> (vbo, vao, vertex_count, pool_index)
        self.chunk_dirty = set()  # Set[(chunk_x, chunk_y)] - Chunks, deren Daten sich geändert haben
        self.last_camera_pos = (0.0, 0.0)  # Track camera changes (for reference, no invalidation needed)
        self.last_zoom = 1.0  # Track zoom changes (for reference, no invalidation needed)
        
        # Merged chunk buffer for batched rendering (single draw call)
        self._merged_chunk_vbo = None
        self._merged_chunk_vao = None
        self._merged_chunk_vertex_count = 0
        self._merged_chunks_hash = None  # Hash of chunk keys to detect changes
        
        # Incremental update tracking for merged buffer
        self._merged_chunk_map = {}  # (chunk_x, chunk_y) -> buffer_offset (in bytes)
        self._merged_chunk_order = []  # Ordered list of chunk keys (for consistent ordering)
        self._merged_max_chunks = self._calculate_max_chunks()  # Maximum chunks that can fit in buffer
        self._merged_vertex_size_bytes = self._calculate_vertex_size_bytes()  # Size of one chunk's vertices in bytes
        
        # Initialize tile color palette (before pool, as pool needs correct buffer size)
        self.tile_color_palette = TileColorPalette()
        
        # Initialize VBO/VAO pool for chunk buffers
        self.chunk_vbo_pool = ChunkVboPool(ctx, self.chunk_program, pool_size=100)
        
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
        
        in vec2 in_position;  // World coordinates (pixels)
        in float in_color_index;  // Color index (0-255) into palette
        in vec2 in_texcoord;  // Texture coordinates (0.0-1.0)
        in float in_use_texture;  // 1.0 if texture should be used, 0.0 for color
        
        uniform vec2 screen_size;      // (width, height) in pixels
        uniform vec2 view_translation; // Camera offset (view_matrix[0,3], view_matrix[1,3])
        uniform float zoom;            // Zoom factor (1.0 = 100%)
        
        out float frag_color_index;
        out vec2 frag_texcoord;
        out float frag_use_texture;
        
        void main() {
            // Apply view matrix translation (camera offset)
            vec2 screen_pos = in_position + view_translation;
            
            // Apply zoom: translate to center, scale, translate back
            // Zoom > 1.0 = reinzoomen (weniger Welt sichtbar), Zoom < 1.0 = rauszoomen (mehr Welt sichtbar)
            // Multiply by zoom: larger zoom = larger screen position offset = less world visible (zoomed in)
            // Smaller zoom = smaller screen position offset = more world visible (zoomed out)
            vec2 screen_center = screen_size * 0.5;
            screen_pos = (screen_pos - screen_center) * zoom + screen_center;
            
            // Convert screen coordinates to NDC
            vec2 ndc = vec2(
                2.0 * screen_pos.x / screen_size.x - 1.0,
                1.0 - 2.0 * screen_pos.y / screen_size.y  // Y-flip for pyglet
            );
            
            gl_Position = vec4(ndc, 0.0, 1.0);
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
        
        if self.use_pyglet:
            # Pyglet: Y increases upward, but world coordinates use Pygame system (Y down)
            # Y-flip happens in shader, so view matrix is normal
            translate_y = screen_center_y - camera_y
        else:
            # Pygame: Y increases downward
            translate_y = camera_y - screen_center_y
        
        # Create view matrix: translate world coordinates to screen coordinates
        # This moves everything so camera is at screen center
        self.view_matrix = np.array([
            [1.0, 0.0, 0.0, translate_x],
            [0.0, 1.0, 0.0, translate_y],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]
        ], dtype=np.float32)
        
        # Update shader uniforms for view matrix and zoom (chunk shader now uses uniforms)
        if self.chunk_program:
            # Set screen size
            if 'screen_size' in self.chunk_program:
                self.chunk_program['screen_size'].value = (float(self.screen_width), float(self.screen_height))
            
            # Set view translation (camera offset)
            if 'view_translation' in self.chunk_program:
                self.chunk_program['view_translation'].value = (float(translate_x), float(translate_y))
            
            # Set zoom
            if 'zoom' in self.chunk_program:
                self.chunk_program['zoom'].value = zoom
                # Store current zoom for render_chunks
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
            if old_pool_index is not None:
                self.chunk_vbo_pool.release(old_pool_index)
            else:
                # Manually created buffer - release normally
                old_vao.release()
                old_vbo.release()
            # Remove from cache (will be re-added below)
            del self.chunk_buffers[chunk_key]
        
        chunk_size = settings.CHUNK_SIZE
        tile_size = float(settings.TILE_SIZE)
        
        # Calculate chunk world position
        chunk_world_x = chunk_x * chunk_size * tile_size
        chunk_world_y = chunk_y * chunk_size * tile_size
        
        # Build vertex data for chunk
        vertices = []
        
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
                has_texture = (hasattr(self, 'tile_texture_manager') and 
                              self.tile_texture_manager is not None and 
                              self.tile_texture_manager.has_texture(tile_id))
                
                # Calculate world position for deterministic variant selection
                world_tile_x = int((chunk_world_x + tile_x_pos) / tile_size)
                world_tile_y = int((chunk_world_y + tile_y_pos) / tile_size)
                
                # Get UV coordinates from atlas if texture exists (with variant support)
                if has_texture:
                    uv_coords = self.tile_texture_manager.get_texture_coords(tile_id, world_tile_x, world_tile_y)
                    if uv_coords:
                        u0, v0, u1, v1 = uv_coords
                        # OpenGL: (0,0) bottom-left, but PIL/our coords are top-left
                        # So we flip V coordinates
                        tex_coords = [
                            (u0, v1),  # Bottom-left (tex)
                            (u1, v1),  # Bottom-right (tex)
                            (u1, v0),  # Top-right (tex)
                            (u0, v1),  # Bottom-left (tex)
                            (u1, v0),  # Top-right (tex)
                            (u0, v0),  # Top-left (tex)
                        ]
                    else:
                        # Fallback to full texture if coords not found
                        tex_coords = [
                            (0.0, 1.0), (1.0, 1.0), (1.0, 0.0),
                            (0.0, 1.0), (1.0, 0.0), (0.0, 0.0)
                        ]
                else:
                    # No texture, use default coords (won't be used anyway)
                    tex_coords = [
                        (0.0, 1.0), (1.0, 1.0), (1.0, 0.0),
                        (0.0, 1.0), (1.0, 0.0), (0.0, 0.0)
                    ]
                
                # World position (top-left corner of tile) in pixels
                # Store as world coordinates - transformation happens in shader
                world_x0 = chunk_world_x + tile_x_pos
                world_y0 = chunk_world_y + tile_y_pos
                world_x1 = world_x0 + tile_size
                world_y1 = world_y0 + tile_size
                
                # Store world coordinates directly (no transformation here)
                # View matrix and zoom are applied in shader via uniforms
                x0_world = world_x0
                y0_world = world_y0
                x1_world = world_x1
                y1_world = world_y1
                
                # Get color index from palette (instead of storing RGB directly)
                color_index = float(self.tile_color_palette.get_color_index(color))
                
                # Use texture flag (1.0 if texture available, 0.0 for color)
                use_texture = 1.0 if has_texture else 0.0
                
                # Create quad vertices (2 triangles = 6 vertices)
                # Format: [in_position (2f), in_color_index (1f), in_texcoord (2f), in_use_texture (1f)]
                base_vertices = [
                    [x0_world, y0_world, color_index, tex_coords[0][0], tex_coords[0][1], use_texture],  # Bottom-left
                    [x1_world, y0_world, color_index, tex_coords[1][0], tex_coords[1][1], use_texture],  # Bottom-right
                    [x1_world, y1_world, color_index, tex_coords[2][0], tex_coords[2][1], use_texture],  # Top-right
                    [x0_world, y0_world, color_index, tex_coords[3][0], tex_coords[3][1], use_texture],  # Bottom-left
                    [x1_world, y1_world, color_index, tex_coords[4][0], tex_coords[4][1], use_texture],  # Top-right
                    [x0_world, y1_world, color_index, tex_coords[5][0], tex_coords[5][1], use_texture],  # Top-left
                ]
                vertices.extend(base_vertices)
                
                # NOTE: Overlays are now handled in get_texture_coords() - they replace the base texture
                # instead of being rendered on top. This means variants 2-6 replace plains_grass_1,
                # not overlay it. If you want true overlays (like flowers/bushes), use get_overlay_texture()
                # separately for non-variant textures.
        
        # Convert to numpy array
        vertex_array = np.array(vertices, dtype=np.float32)
        vertex_count = len(vertices)
        
        # Buffer aus Pool holen oder neuen erstellen
        pool_result = self.chunk_vbo_pool.acquire()
        if pool_result is None:
            # Fallback: neuer Buffer
            if self.diagnostics:
                self.diagnostics.warning("ModernGLRenderer", "VBO pool exhausted, creating new buffer", chunk_x=chunk_x, chunk_y=chunk_y)
            vbo = self.ctx.buffer(vertex_array.tobytes())
            vao = self.ctx.vertex_array(
                self.chunk_program,
                [(vbo, "2f 1f 2f 1f", "in_position", "in_color_index", "in_texcoord", "in_use_texture")]
            )
            self.chunk_buffers[chunk_key] = (vbo, vao, vertex_count, None)
        else:
            vbo, vao, pool_index = pool_result
            self.chunk_vbo_pool.write_data(vbo, vertex_array)
            self.chunk_buffers[chunk_key] = (vbo, vao, vertex_count, pool_index)
        
        # Nach Upload ist der Chunk wieder "clean"
        self.mark_chunk_clean(chunk_x, chunk_y)
        
        return (vbo, vao, vertex_count)
    
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
    
    def render_chunks(self, chunks_data: List[Tuple[int, int, List[List[dict]]]], performance_monitor=None, max_new_chunks_per_frame: int = 8):
        """
        Render chunks using GPU (with caching - similar to Pygame surface cache)
        
        Args:
            chunks_data: List of (chunk_x, chunk_y, tiles) tuples
                tiles: 15x15 grid of tile dictionaries with 'color' key
            performance_monitor: Optional PerformanceMonitor instance for timing
            max_new_chunks_per_frame: Maximum number of new/dirty chunks to upload per frame
                (prevents frame time spikes when loading many chunks at once)
        """
        if not chunks_data:
            return
        
        import time
        chunk_render_start = time.perf_counter()
        
        # Shader-Uniforms sicherstellen
        if self.chunk_program:
            if 'screen_size' in self.chunk_program:
                self.chunk_program['screen_size'].value = (float(self.screen_width), float(self.screen_height))
            if 'zoom' in self.chunk_program:
                self.chunk_program['zoom'].value = self.current_zoom
        
        # GL State
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.ctx.disable(moderngl.DEPTH_TEST)
        self.ctx.disable(moderngl.CULL_FACE)
        
        # Bind texture atlas once for all chunks (if available)
        if hasattr(self, 'tile_texture_manager') and self.tile_texture_manager is not None:
            if self.tile_texture_manager.texture_atlas is not None:
                self.tile_texture_manager.texture_atlas.use(0)
                if 'tile_texture' in self.chunk_program:
                    self.chunk_program['tile_texture'].value = 0
        
        upload_start_time = time.perf_counter()
        new_chunks_uploaded = 0
        
        # Pro Chunk: ggf. Buffer neu aufbauen und einmal drawen
        for chunk_x, chunk_y, tiles in chunks_data:
            chunk_key = (chunk_x, chunk_y)
            is_dirty = chunk_key in self.chunk_dirty or chunk_key not in self.chunk_buffers
            
            # Upload-Budget begrenzen
            if is_dirty and new_chunks_uploaded >= max_new_chunks_per_frame:
                # Noch nicht im GPU-Cache? Dann diesen Chunk in diesem Frame überspringen
                if chunk_key not in self.chunk_buffers:
                    continue
                # Im Cache aber dirty? Mit altem Buffer rendern (ohne Upload)
                if chunk_key in self.chunk_buffers:
                    vbo, vao, vertex_count, pool_index = self.chunk_buffers[chunk_key]
                    if vao and vertex_count > 0:
                        # Atlas is already bound above, just render
                        vao.render(moderngl.TRIANGLES, vertices=vertex_count)
                    continue
            
            # Normaler Pfad: Buffer erstellen/aktualisieren
            vbo, vao, vertex_count = self._create_chunk_buffer(chunk_x, chunk_y, tiles)
            if is_dirty:
                new_chunks_uploaded += 1
            
            if vao and vertex_count > 0:
                # Atlas is already bound above, just render
                vao.render(moderngl.TRIANGLES, vertices=vertex_count)
        
        upload_time = time.perf_counter() - upload_start_time
        if performance_monitor:
            performance_monitor.record_chunk_upload_time(upload_time)
        
        chunk_render_time = time.perf_counter() - chunk_render_start
        if performance_monitor:
            performance_monitor.record_chunk_render_time(chunk_render_time)
    
    def _build_merged_chunk_buffer(self, chunks_data: List[Tuple[int, int, List[List[dict]]]]):
        """
        Build or incrementally update merged VBO containing all visible chunks for batched rendering.
        
        Uses incremental updates: VBO is allocated once at maximum size, then only changed
        chunks are updated using write(offset, data) instead of recreating the entire buffer.
        
        Args:
            chunks_data: List of (chunk_x, chunk_y, tiles) tuples
        """
        # Calculate hash of chunk keys to detect changes
        chunk_keys_set = set((chunk_x, chunk_y) for chunk_x, chunk_y, _ in chunks_data)
        chunk_keys = tuple(sorted(chunk_keys_set))
        chunks_hash = hash(chunk_keys)
        
        # Reuse existing merged buffer if chunks haven't changed
        if self._merged_chunks_hash == chunks_hash and self._merged_chunk_vbo is not None:
            return
        
        # Initialize buffer if it doesn't exist
        if self._merged_chunk_vbo is None:
            self._initialize_merged_buffer()
        
        # Determine which chunks need to be added/removed/updated
        current_chunks_set = set(self._merged_chunk_order)
        chunks_to_add = chunk_keys_set - current_chunks_set
        chunks_to_remove = current_chunks_set - chunk_keys_set
        chunks_to_update = chunk_keys_set & current_chunks_set  # Chunks that are in both sets
        
        # Remove chunks that are no longer visible
        for chunk_key in chunks_to_remove:
            if chunk_key in self._merged_chunk_map:
                # Mark slot as empty (we'll reuse it for new chunks)
                del self._merged_chunk_map[chunk_key]
                self._merged_chunk_order.remove(chunk_key)
        
        # Rebuild chunk order list (sorted for consistency)
        new_chunk_order = sorted(chunk_keys_set)
        
        # Update or add chunks
        chunk_size = settings.CHUNK_SIZE
        tile_size = float(settings.TILE_SIZE)
        total_vertex_count = 0
        
        for chunk_key in new_chunk_order:
            # Find chunk data
            chunk_data = next((c for c in chunks_data if (c[0], c[1]) == chunk_key), None)
            if not chunk_data:
                continue
            
            chunk_x, chunk_y, tiles = chunk_data
            
            # Build vertex data for this chunk
            chunk_vertices = []
            chunk_world_x = chunk_x * chunk_size * tile_size
            chunk_world_y = chunk_y * chunk_size * tile_size
            
            for tile_y in range(chunk_size):
                for tile_x in range(chunk_size):
                    tile = tiles[tile_y][tile_x]
                    color = tile.get('color', (100, 100, 100))
                    if isinstance(color, list):
                        color = tuple(color)
                    
                    # Tile position within chunk
                    tile_x_pos = tile_x * tile_size
                    tile_y_pos = tile_y * tile_size
                    
                    # World position (top-left corner of tile) in pixels
                    world_x0 = chunk_world_x + tile_x_pos
                    world_y0 = chunk_world_y + tile_y_pos
                    world_x1 = world_x0 + tile_size
                    world_y1 = world_y0 + tile_size
                    
                    # Store world coordinates directly (no transformation here)
                    # View matrix and zoom are applied in shader via uniforms
                    x0_world = world_x0
                    y0_world = world_y0
                    x1_world = world_x1
                    y1_world = world_y1
                    
                    # Get tile_id to check for texture
                    tile_id = tile.get('tile_id') or tile.get('tileid', '')
                    has_texture = (hasattr(self, 'tile_texture_manager') and 
                                  self.tile_texture_manager is not None and 
                                  self.tile_texture_manager.has_texture(tile_id))
                    
                    # Calculate world position for deterministic variant selection
                    world_tile_x = int(world_x0 / tile_size)
                    world_tile_y = int(world_y0 / tile_size)
                    
                    # Get UV coordinates from atlas if texture exists (with variant support)
                    if has_texture:
                        uv_coords = self.tile_texture_manager.get_texture_coords(tile_id, world_tile_x, world_tile_y)
                        if uv_coords:
                            u0, v0, u1, v1 = uv_coords
                            # OpenGL: (0,0) bottom-left, but PIL/our coords are top-left
                            # So we flip V coordinates
                            tex_coords = [
                                (u0, v1),  # Bottom-left (tex)
                                (u1, v1),  # Bottom-right (tex)
                                (u1, v0),  # Top-right (tex)
                                (u0, v1),  # Bottom-left (tex)
                                (u1, v0),  # Top-right (tex)
                                (u0, v0),  # Top-left (tex)
                            ]
                        else:
                            # Fallback to full texture if coords not found
                            tex_coords = [
                                (0.0, 1.0), (1.0, 1.0), (1.0, 0.0),
                                (0.0, 1.0), (1.0, 0.0), (0.0, 0.0)
                            ]
                    else:
                        # No texture, use default coords (won't be used anyway)
                        tex_coords = [
                            (0.0, 1.0), (1.0, 1.0), (1.0, 0.0),
                            (0.0, 1.0), (1.0, 0.0), (0.0, 0.0)
                        ]
                    
                    # Get color index from palette (instead of storing RGB directly)
                    color_index = float(self.tile_color_palette.get_color_index(color))
                    
                    # Use texture flag (1.0 if texture available, 0.0 for color)
                    use_texture = 1.0 if has_texture else 0.0
                    
                    # Create quad vertices (2 triangles = 6 vertices)
                    # Format: [in_position (2f), in_color_index (1f), in_texcoord (2f), in_use_texture (1f)]
                    base_vertices = [
                        [x0_world, y0_world, color_index, tex_coords[0][0], tex_coords[0][1], use_texture],  # Bottom-left
                        [x1_world, y0_world, color_index, tex_coords[1][0], tex_coords[1][1], use_texture],  # Bottom-right
                        [x1_world, y1_world, color_index, tex_coords[2][0], tex_coords[2][1], use_texture],  # Top-right
                        [x0_world, y0_world, color_index, tex_coords[3][0], tex_coords[3][1], use_texture],  # Bottom-left
                        [x1_world, y1_world, color_index, tex_coords[4][0], tex_coords[4][1], use_texture],  # Top-right
                        [x0_world, y1_world, color_index, tex_coords[5][0], tex_coords[5][1], use_texture],  # Top-left
                    ]
                    chunk_vertices.extend(base_vertices)
                    
                    # NOTE: Variants are now selected directly in get_texture_coords() based on overlay config
                    # They replace the base texture instead of being rendered on top
            
            # Convert chunk vertices to numpy array
            chunk_vertex_array = np.array(chunk_vertices, dtype=np.float32)
            
            # Calculate buffer offset for this chunk
            chunk_index = new_chunk_order.index(chunk_key)
            buffer_offset = chunk_index * self._merged_vertex_size_bytes
            
            # Update buffer at specific offset (incremental update)
            self._merged_chunk_vbo.write(chunk_vertex_array.tobytes(), offset=buffer_offset)
            
            # Update mapping
            self._merged_chunk_map[chunk_key] = buffer_offset
            total_vertex_count += len(chunk_vertices)
        
        # Update tracking
        self._merged_chunk_order = new_chunk_order
        self._merged_chunk_vertex_count = total_vertex_count
        self._merged_chunks_hash = chunks_hash
    
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
            
            if pool_index is not None:
                # Return buffer to pool for reuse
                self.chunk_vbo_pool.release(pool_index)
            else:
                # Manually created buffer (pool exhausted) - release normally
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
    
    def cleanup(self):
        """Cleanup all cached buffers"""
        # Release all buffers back to pool
        for chunk_key, buffer_data in list(self.chunk_buffers.items()):
            vbo, vao, vertex_count, pool_index = buffer_data
            if pool_index is not None:
                self.chunk_vbo_pool.release(pool_index)
            else:
                # Manually created buffer (pool exhausted) - release normally
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

