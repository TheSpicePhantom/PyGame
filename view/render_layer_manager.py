"""
View: RenderLayerManager - Layer-basiertes Rendering-System
"""
from typing import List, Tuple, Callable, Optional
import moderngl


class RenderLayer:
    """Single render layer with priority and Z-index sorting."""
    
    def __init__(self, layer_id: int, name: str):
        """
        Args:
            layer_id: Layer ID (lower = rendered first = behind)
            name: Human-readable layer name for debugging
        """
        self.layer_id = layer_id
        self.name = name
        self.renderables = []  # List of (z_index, render_func, args, kwargs)
    
    def add(self, render_func: Callable, z_index: float = 0.0, *args, **kwargs):
        """
        Add renderable to this layer.
        
        Args:
            render_func: Function to call for rendering
            z_index: Z-index for sorting within layer (lower = rendered first = behind)
            *args: Positional arguments for render_func
            **kwargs: Keyword arguments for render_func
        """
        self.renderables.append((z_index, render_func, args, kwargs))
    
    def clear(self):
        """Clear all renderables (call each frame before adding new ones)."""
        self.renderables = []
    
    def render(self):
        """Render all items in this layer (sorted by z_index)."""
        # Sort by z_index (lower = rendered first = behind)
        sorted_renderables = sorted(self.renderables, key=lambda x: x[0])
        
        for z_index, render_func, args, kwargs in sorted_renderables:
            try:
                render_func(*args, **kwargs)
            except Exception as e:
                # Log error but continue rendering other items
                print(f"[RenderLayer] Error rendering in layer {self.name} (z={z_index}): {e}")
                import traceback
                traceback.print_exc()


class RenderLayerManager:
    """Manages all render layers and coordinates rendering order."""
    
    # Layer constants (lower = rendered first = behind)
    LAYER_TERRAIN = 0
    LAYER_SHADOWS = 5
    LAYER_DECORATIONS = 10
    LAYER_GROUND_EFFECTS = 15
    LAYER_ENTITIES = 20
    LAYER_PARTICLES = 25
    LAYER_EFFECTS = 30
    LAYER_PROJECTILES = 40
    LAYER_UI_WORLD = 50
    LAYER_UI_SCREEN = 100
    
    def __init__(self):
        """Initialize render layer manager with all layers."""
        self.layers = {
            self.LAYER_TERRAIN: RenderLayer(0, "Terrain"),
            self.LAYER_SHADOWS: RenderLayer(5, "Shadows"),
            self.LAYER_DECORATIONS: RenderLayer(10, "Decorations"),
            self.LAYER_GROUND_EFFECTS: RenderLayer(15, "Ground Effects"),
            self.LAYER_ENTITIES: RenderLayer(20, "Entities"),
            self.LAYER_PARTICLES: RenderLayer(25, "Particles"),
            self.LAYER_EFFECTS: RenderLayer(30, "Effects"),
            self.LAYER_PROJECTILES: RenderLayer(40, "Projectiles"),
            self.LAYER_UI_WORLD: RenderLayer(50, "UI World"),
            self.LAYER_UI_SCREEN: RenderLayer(100, "UI Screen"),
        }
        
        self.post_processing_effects = []
    
    def add_renderable(self, layer_id: int, render_func: Callable, z_index: float = 0.0, *args, **kwargs):
        """
        Add renderable to specific layer.
        
        Args:
            layer_id: Layer ID (use LAYER_* constants)
            render_func: Function to call for rendering
            z_index: Z-index for sorting within layer (lower = rendered first = behind)
            *args: Positional arguments for render_func
            **kwargs: Keyword arguments for render_func
        """
        if layer_id not in self.layers:
            print(f"[RenderLayerManager] Warning: Unknown layer {layer_id}")
            return
        
        self.layers[layer_id].add(render_func, z_index, *args, **kwargs)
    
    def add_post_processing(self, effect_func: Callable, *args, **kwargs):
        """
        Add post-processing effect (applied after all layers).
        
        Args:
            effect_func: Function to call for post-processing
            *args: Positional arguments for effect_func
            **kwargs: Keyword arguments for effect_func
        """
        self.post_processing_effects.append((effect_func, args, kwargs))
    
    def clear_all(self):
        """Clear all layers (call each frame before adding renderables)."""
        for layer in self.layers.values():
            layer.clear()
        self.post_processing_effects = []
    
    def render_all(self):
        """Render all layers in order (lowest layer_id first)."""
        # Render layers (sorted by layer_id)
        for layer_id in sorted(self.layers.keys()):
            self.layers[layer_id].render()
        
        # Apply post-processing effects
        for effect_func, args, kwargs in self.post_processing_effects:
            try:
                effect_func(*args, **kwargs)
            except Exception as e:
                print(f"[RenderLayerManager] Error in post-processing: {e}")
                import traceback
                traceback.print_exc()
    
    def get_layer(self, layer_id: int) -> Optional[RenderLayer]:
        """Get layer by ID (for direct access if needed)."""
        return self.layers.get(layer_id)
