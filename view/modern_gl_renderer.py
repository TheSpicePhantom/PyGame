"""
ModernGL Renderer: GPU-beschleunigtes Rendering für Chunks und Sprites
"""
import moderngl
import numpy as np
from typing import List, Tuple, Optional, Dict
from core import settings
import pyglet
from pyglet import font as pyglet_font


class ModernGLRenderer:
    """GPU-beschleunigter Renderer für Chunks und Sprites"""
    
    def __init__(self, ctx: moderngl.Context, screen_width: int, screen_height: int, use_pyglet=False):
        """
        Initialize ModernGL Renderer
        
        Args:
            ctx: ModernGL context
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
            use_pyglet: If True, use pyglet coordinate system (Y up), else Pygame (Y down)
        """
        self.ctx = ctx
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.use_pyglet = use_pyglet
        self.current_zoom = 1.0  # Current zoom level (1.0 = 100%)
        
        # Load shaders
        self.chunk_program = self._load_chunk_shader()
        self.sprite_program = self._load_sprite_shader()
        self.ui_program = self._load_ui_shader()
        
        # No projection matrix needed - vertices are converted to NDC directly
        # self._setup_projection(use_pyglet=use_pyglet)  # DISABLED: Simplified shader doesn't use matrices
        
        # Chunk buffer cache (like Pygame surface cache)
        # IMPORTANT: Buffer are created with view matrix and zoom baked in, so they must be
        # invalidated when camera or zoom changes. We don't cache by camera/zoom because
        # that would create too many buffers. Instead, we invalidate all buffers on change.
        self.chunk_buffers = {}  # (chunk_x, chunk_y) -> (vbo, vao, vertex_count)
        self.last_camera_pos = (0.0, 0.0)  # Track camera changes for cache invalidation
        self.last_zoom = 1.0  # Track zoom changes for cache invalidation
        
        # Sprite texture cache
        self.sprite_textures = {}  # sprite_id -> texture
        
        # UI texture cache (for text/menus)
        self.ui_textures = {}  # text_id -> texture
        
        # Text rendering cache
        self.text_cache: Dict[str, Tuple[moderngl.Texture, int, int]] = {}  # (text, font_name, size, color) -> (texture, width, height)
        self.text_program = None  # Will be created on first use
        
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
            print(f"[ModernGL] Sprite shader compiled successfully")
            return program
        except Exception as e:
            print(f"[ModernGL] Error compiling sprite shader: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _load_ui_shader(self) -> moderngl.Program:
        """Load UI rendering shader (for text/menus)"""
        # Same as sprite shader but for UI elements
        return self._load_sprite_shader()
    
    def _load_text_shader(self) -> moderngl.Program:
        """Load text rendering shader (for text with textures)"""
        vertex_shader = """
        #version 330 core
        
        in vec2 in_position;
        in vec2 in_texcoord;
        
        uniform vec2 screen_size;
        uniform vec2 text_position;  // Screen position in pixels (top-left)
        uniform vec2 text_size;      // Text size in pixels (width, height)
        
        out vec2 frag_texcoord;
        
        void main() {
            // Convert screen position to NDC
            // Screen coordinates: (0,0) top-left, (screen_width, screen_height) bottom-right
            // NDC coordinates: (-1,-1) bottom-left, (1,1) top-right
            vec2 screen_pos = in_position * text_size + text_position;
            
            // Convert to NDC (pyglet: Y increases upward)
            vec2 ndc = vec2(
                2.0 * screen_pos.x / screen_size.x - 1.0,
                1.0 - 2.0 * screen_pos.y / screen_size.y  // Y-flip for pyglet
            );
            
            gl_Position = vec4(ndc, 0.0, 1.0);
            frag_texcoord = in_texcoord;
        }
        """
        
        fragment_shader = """
        #version 330 core
        
        in vec2 frag_texcoord;
        uniform sampler2D text_texture;
        uniform vec3 text_color;  // Text color multiplier (for colored text)
        
        out vec4 out_color;
        
        void main() {
            vec4 tex_color = texture(text_texture, frag_texcoord);
            // Use alpha from texture, apply color multiplier
            out_color = vec4(text_color * tex_color.rgb, tex_color.a);
        }
        """
        
        try:
            program = self.ctx.program(
                vertex_shader=vertex_shader,
                fragment_shader=fragment_shader
            )
            print(f"[ModernGL] Text shader compiled successfully")
            return program
        except Exception as e:
            print(f"[ModernGL] Error compiling text shader: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _load_chunk_shader(self) -> moderngl.Program:
        """Load chunk rendering shader with view matrix and zoom support"""
        # Shader applies view matrix and zoom transformation on GPU
        # This allows buffers to be cached even when camera moves
        vertex_shader = """
        #version 330 core
        
        in vec2 in_position;  // World coordinates (pixels)
        in vec3 in_color;     // Normalized [0,1]
        
        uniform vec2 screen_size;      // (width, height) in pixels
        uniform vec2 view_translation; // Camera offset (view_matrix[0,3], view_matrix[1,3])
        uniform float zoom;            // Zoom factor (1.0 = 100%)
        
        out vec3 frag_color;
        
        void main() {
            // Apply view matrix translation (camera offset)
            vec2 screen_pos = in_position + view_translation;
            
            // Apply zoom: translate to center, scale, translate back
            // Zoom < 1.0 = rauszoomen (mehr Welt sichtbar), Zoom > 1.0 = reinzoomen (weniger Welt sichtbar)
            // Multiply by zoom: smaller zoom = smaller screen position = more world visible
            vec2 screen_center = screen_size * 0.5;
            screen_pos = (screen_pos - screen_center) * zoom + screen_center;
            
            // Convert screen coordinates to NDC
            vec2 ndc = vec2(
                2.0 * screen_pos.x / screen_size.x - 1.0,
                1.0 - 2.0 * screen_pos.y / screen_size.y  // Y-flip for pyglet
            );
            
            gl_Position = vec4(ndc, 0.0, 1.0);
            frag_color = in_color;
        }
        """
        
        fragment_shader = """
        #version 330 core
        
        in vec3 frag_color;
        out vec4 out_color;
        
        void main() {
            out_color = vec4(frag_color, 1.0);
        }
        """
        
        return self.ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=fragment_shader
        )
    
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
        # invalidated when camera moves - only when zoom changes (or chunk data changes)
        camera_pos = (camera_x, camera_y)
        if zoom != self.last_zoom:
            # Only invalidate on zoom change (buffers contain zoom-dependent data)
            self._invalidate_all_chunk_buffers()
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
        
        # Check if buffer already exists
        if chunk_key in self.chunk_buffers:
            return self.chunk_buffers[chunk_key]
        
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
                
                # Normalize color to [0, 1] like test_render.py
                r = float(color[0]) / 255.0
                g = float(color[1]) / 255.0
                b = float(color[2]) / 255.0
                
                # Create quad vertices (2 triangles = 6 vertices)
                # Format: [in_position (world coordinates in pixels), in_color (normalized)]
                # Transformation to NDC happens in shader
                base_vertices = [
                    [x0_world, y0_world, r, g, b],  # Bottom-left
                    [x1_world, y0_world, r, g, b],  # Bottom-right
                    [x1_world, y1_world, r, g, b],  # Top-right
                    [x0_world, y0_world, r, g, b],  # Bottom-left
                    [x1_world, y1_world, r, g, b],  # Top-right
                    [x0_world, y1_world, r, g, b],  # Top-left
                ]
                vertices.extend(base_vertices)
        
        # Convert to numpy array and create buffer
        vertex_array = np.array(vertices, dtype=np.float32)
        vbo = self.ctx.buffer(vertex_array.tobytes())
        
        # Vertex data ready (world coordinates in pixels, normalized colors)
        
        # Create VAO with explicit attribute binding (like test_render.py)
        # Format: [in_position (2), in_color (3)] = 5 floats per vertex
        # Stride = 5 * 4 bytes = 20 bytes
        vao = self.ctx.vertex_array(
            self.chunk_program,
            [(vbo, "2f 3f", "in_position", "in_color")]
        )
        
        # VAO created successfully
        
        vertex_count = len(vertices)
        
        # Cache buffer (with zoom in key)
        self.chunk_buffers[chunk_key] = (vbo, vao, vertex_count)
        
        return (vbo, vao, vertex_count)
    
    def render_chunks(self, chunks_data: List[Tuple[int, int, List[List[dict]]]], performance_monitor=None):
        """
        Render chunks using GPU (with caching - similar to Pygame surface cache)
        
        Args:
            chunks_data: List of (chunk_x, chunk_y, tiles) tuples
                tiles: 15x15 grid of tile dictionaries with 'color' key
            performance_monitor: Optional PerformanceMonitor instance for timing
        """
        if not chunks_data:
            return
        
        # Measure chunk rendering time
        import time
        chunk_render_start = time.perf_counter()
        
        # Render chunks
        
        # IMPORTANT: Ensure shader uniforms are up-to-date before rendering
        # The uniforms (screen_size, view_translation, zoom) are set in update_view(),
        # but we verify they're set here to ensure zoom changes are applied
        if self.chunk_program:
            if 'screen_size' in self.chunk_program:
                self.chunk_program['screen_size'].value = (float(self.screen_width), float(self.screen_height))
            if 'zoom' in self.chunk_program:
                # Ensure zoom is current (should already be set in update_view, but double-check)
                self.chunk_program['zoom'].value = self.current_zoom
        
        # Enable blending for transparency (like test_render.py)
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        
        # No matrices needed - vertices are converted to NDC in _create_chunk_buffer
        # All matrix setup code removed - simplified shader doesn't use matrices
        
        # Render each chunk using cached buffers
        rendered_count = 0
        for chunk_x, chunk_y, tiles in chunks_data:
            # Get or create chunk buffer (cached after first creation)
            vbo, vao, vertex_count = self._create_chunk_buffer(chunk_x, chunk_y, tiles)
            
            # Chunk ready for rendering
            
            # IMPORTANT: Ensure OpenGL state is correct before rendering (like test_render.py)
            self.ctx.enable(moderngl.BLEND)
            self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
            self.ctx.disable(moderngl.DEPTH_TEST)
            self.ctx.disable(moderngl.CULL_FACE)
            
            # No matrices needed - vertices are already in NDC coordinates!
            # Render chunk (fast - buffer already exists)
            vao.render(moderngl.TRIANGLES, vertices=vertex_count)
            rendered_count += 1
        
        # Record chunk rendering time
        chunk_render_time = time.perf_counter() - chunk_render_start
        if performance_monitor:
            performance_monitor.record_chunk_render_time(chunk_render_time)
        
        # Rendered {rendered_count} chunks
    
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
            print(f"[Debug] Error creating simple shader: {e}")
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
        """Invalidate all chunk buffers (called when camera or zoom changes)"""
        for vbo, vao, _ in self.chunk_buffers.values():
            vao.release()
            vbo.release()
        self.chunk_buffers.clear()
    
    def invalidate_chunk(self, chunk_x: int, chunk_y: int):
        """Invalidate cached buffer for a chunk (call when chunk changes)"""
        chunk_key = (chunk_x, chunk_y)
        if chunk_key in self.chunk_buffers:
            vbo, vao, _ = self.chunk_buffers[chunk_key]
            vao.release()
            vbo.release()
            del self.chunk_buffers[chunk_key]
    
    def _get_text_texture(self, text: str, font_name: str = None, size: int = 24, color: Tuple[int, int, int] = (255, 255, 255)) -> Tuple[moderngl.Texture, int, int]:
        """
        Get or create a text texture (with caching)
        
        Args:
            text: Text to render
            font_name: Font name (None = default)
            size: Font size in pixels
            color: Text color (R, G, B)
        
        Returns:
            (texture, width, height) tuple
        """
        # Create cache key
        cache_key = (text, font_name or "default", size, color)
        
        # Check cache
        if cache_key in self.text_cache:
            return self.text_cache[cache_key]
        
        # Load font
        if font_name:
            try:
                font = pyglet_font.load(font_name, size)
            except:
                font = pyglet_font.load(None, size)  # Fallback to default
        else:
            font = pyglet_font.load(None, size)
        
        # Create text label
        label = pyglet.text.Label(
            text,
            font_name=font_name,
            font_size=size,
            color=(*color, 255),  # Add alpha channel
            anchor_x='left',
            anchor_y='top'
        )
        
        # Get text dimensions
        width = max(1, label.content_width)
        height = max(1, label.content_height)
        
        # Render label to texture using PIL/Pillow (most reliable method)
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            # Create text label to get dimensions
            label = pyglet.text.Label(
                text,
                font_name=font_name,
                font_size=size,
                color=(*color, 255),
                anchor_x='left',
                anchor_y='top'
            )
            
            # Get actual text dimensions (convert to int, PIL requires integers)
            actual_width = max(1, int(label.content_width))
            actual_height = max(1, int(label.content_height))
            
            # Create PIL image with transparent background
            pil_img = Image.new('RGBA', (actual_width, actual_height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(pil_img)
            
            # Try to load font
            try:
                if font_name:
                    # Try to find font file
                    pil_font = ImageFont.truetype(font_name, size)
                else:
                    # Use default font
                    pil_font = ImageFont.load_default()
            except:
                try:
                    # Try common system fonts
                    import platform
                    if platform.system() == 'Windows':
                        pil_font = ImageFont.truetype('arial.ttf', size)
                    elif platform.system() == 'Darwin':  # macOS
                        pil_font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', size)
                    else:  # Linux
                        pil_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', size)
                except:
                    pil_font = ImageFont.load_default()
            
            # Draw text
            draw.text((0, 0), text, fill=(*color, 255), font=pil_font)
            
            # Convert PIL image to numpy array
            img_array = np.array(pil_img)
            
            # Convert to RGBA bytes (PIL uses RGBA, which is what we need)
            pixels = img_array.tobytes()
            
            # Create ModernGL texture
            texture = self.ctx.texture((actual_width, actual_height), 4, pixels)
            texture.build_mipmaps()
            
            # Cache texture
            self.text_cache[cache_key] = (texture, actual_width, actual_height)
            
            return texture, actual_width, actual_height
            
        except ImportError:
            # PIL not available, use simple fallback
            print(f"[ModernGL] PIL/Pillow not available, using fallback text rendering")
            label = pyglet.text.Label(
                text,
                font_name=font_name,
                font_size=size,
                color=(*color, 255),
                anchor_x='left',
                anchor_y='top'
            )
            actual_width = max(1, int(label.content_width))
            actual_height = max(1, int(label.content_height))
            
            # Create a simple colored rectangle as fallback
            texture_data = np.full((actual_height, actual_width, 4), [*color, 255], dtype=np.uint8)
            texture = self.ctx.texture((actual_width, actual_height), 4, texture_data.tobytes())
            self.text_cache[cache_key] = (texture, actual_width, actual_height)
            return texture, actual_width, actual_height
            
        except Exception as e:
            # Fallback: create a simple white texture if text rendering fails
            print(f"[ModernGL] Error rendering text '{text}': {e}")
            import traceback
            traceback.print_exc()
            texture_data = np.array([[[255, 255, 255, 255]]], dtype=np.uint8)
            texture = self.ctx.texture((1, 1), 4, texture_data.tobytes())
            self.text_cache[cache_key] = (texture, width, height)
            return texture, width, height
    
    def render_text(self, text: str, x: int, y: int, font_name: str = None, size: int = 24, color: Tuple[int, int, int] = (255, 255, 255)):
        """
        Render text at screen position (x, y)
        
        Args:
            text: Text to render
            x: Screen X position (pixels, left)
            y: Screen Y position (pixels, top for pyglet)
            font_name: Font name (None = default)
            size: Font size in pixels
            color: Text color (R, G, B)
        """
        if not text:
            return
        
        # Lazy-load text shader
        if self.text_program is None:
            self.text_program = self._load_text_shader()
        
        # Get or create text texture
        texture, width, height = self._get_text_texture(text, font_name, size, color)
        
        # Enable blending
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.ctx.disable(moderngl.DEPTH_TEST)
        
        # Create quad vertices (normalized 0-1 coordinates)
        # Position will be transformed by shader
        # PIL stores images top-to-bottom, but we need to flip Y for OpenGL
        vertices = np.array([
            # Position (normalized), TexCoord (flipped Y for PIL -> OpenGL)
            [0.0, 0.0, 0.0, 0.0],  # Bottom-left (texture top-left)
            [1.0, 0.0, 1.0, 0.0],  # Bottom-right (texture top-right)
            [1.0, 1.0, 1.0, 1.0],  # Top-right (texture bottom-right)
            [0.0, 0.0, 0.0, 0.0],  # Bottom-left
            [1.0, 1.0, 1.0, 1.0],  # Top-right
            [0.0, 1.0, 0.0, 1.0],  # Top-left (texture bottom-left)
        ], dtype=np.float32)
        
        vbo = self.ctx.buffer(vertices.tobytes())
        vao = self.ctx.simple_vertex_array(
            self.text_program,
            vbo,
            'in_position', 'in_texcoord'
        )
        
        # Set shader uniforms
        # Convert pyglet Y coordinate (bottom=0, top=height) to top-left coordinate system (top=0, bottom=height)
        # In pyglet: y=0 is bottom, y=height is top
        # Shader expects: y=0 is top, y=height is bottom
        # So we need to flip: y_pyglet -> y_shader = height - y_pyglet
        y_flipped = self.screen_height - y
        
        self.text_program['screen_size'].value = (float(self.screen_width), float(self.screen_height))
        self.text_program['text_position'].value = (float(x), float(y_flipped))
        self.text_program['text_size'].value = (float(width), float(height))
        self.text_program['text_color'].value = (color[0] / 255.0, color[1] / 255.0, color[2] / 255.0)
        
        # Bind texture
        texture.use(0)
        self.text_program['text_texture'] = 0
        
        # Render
        vao.render(moderngl.TRIANGLES)
        
        # Cleanup
        vao.release()
        vbo.release()
    
    def cleanup(self):
        """Cleanup all cached buffers"""
        for vbo, vao, _ in self.chunk_buffers.values():
            vao.release()
            vbo.release()
        self.chunk_buffers.clear()
    
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

