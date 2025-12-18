"""
Performance Monitor: Collects detailed performance metrics during gameplay
"""
import time
from collections import deque
from statistics import mean, median


class PerformanceMonitor:
    """Collects and analyzes performance metrics"""
    
    def __init__(self):
        self.enabled = True  # Always enabled
        
        # Frame timing
        self.frame_times = deque(maxlen=300)  # Last 300 frames (~5 seconds at 60 FPS)
        self.update_times = deque(maxlen=300)
        self.render_times = deque(maxlen=300)
        
        # Current frame timing
        self.frame_start_time = None
        self.update_start_time = None
        self.render_start_time = None
        
        # Chunk loading events
        self.chunk_load_events = []
        
        # Chunk generation events (separate from load)
        self.chunk_generation_events = []
        
        # Chunk save events
        self.chunk_save_events = []
        
        # Chunk render times (per frame)
        self.chunk_render_times = deque(maxlen=300)
        
        # Movement events (direction, delay)
        self.movement_events = []
    
    def start_frame(self):
        """Start timing a new frame"""
        if not self.enabled:
            return
        self.frame_start_time = time.perf_counter()
    
    def start_update(self):
        """Start timing update phase"""
        if not self.enabled:
            return
        self.update_start_time = time.perf_counter()
    
    def end_update(self):
        """End timing update phase"""
        if not self.enabled or self.update_start_time is None:
            return
        update_time = time.perf_counter() - self.update_start_time
        self.update_times.append(update_time * 1000)  # Convert to ms
    
    def start_render(self):
        """Start timing render phase"""
        if not self.enabled:
            return
        self.render_start_time = time.perf_counter()
    
    def end_render(self):
        """End timing render phase"""
        if not self.enabled or self.render_start_time is None:
            return
        render_time = time.perf_counter() - self.render_start_time
        self.render_times.append(render_time * 1000)  # Convert to ms
        
        # End frame timing
        if self.frame_start_time is not None:
            frame_time = time.perf_counter() - self.frame_start_time
            self.frame_times.append(frame_time * 1000)  # Convert to ms
    
    def record_chunk_load(self, chunk_x, chunk_y, load_time):
        """Record a chunk load event"""
        if not self.enabled:
            return
        self.chunk_load_events.append({
            'chunk_x': chunk_x,
            'chunk_y': chunk_y,
            'load_time': load_time * 1000,  # Convert to ms
            'timestamp': time.time()
        })
    
    def record_chunk_generation(self, chunk_x, chunk_y, generation_time):
        """Record a chunk generation event (separate from load)"""
        if not self.enabled:
            return
        self.chunk_generation_events.append({
            'chunk_x': chunk_x,
            'chunk_y': chunk_y,
            'generation_time': generation_time * 1000,  # Convert to ms
            'timestamp': time.time()
        })
    
    def record_chunk_save(self, chunk_x, chunk_y, save_time):
        """Record a chunk save event"""
        if not self.enabled:
            return
        self.chunk_save_events.append({
            'chunk_x': chunk_x,
            'chunk_y': chunk_y,
            'save_time': save_time * 1000,  # Convert to ms
            'timestamp': time.time()
        })
    
    def record_chunk_render_time(self, render_time):
        """Record chunk rendering time for a frame"""
        if not self.enabled:
            return
        self.chunk_render_times.append(render_time * 1000)  # Convert to ms
    
    def record_movement(self, direction):
        """Record a player movement event"""
        if not self.enabled:
            return
        # Calculate delay since last movement (if any)
        delay = 0.0
        if self.movement_events:
            last_timestamp = self.movement_events[-1]['timestamp']
            delay = time.time() - last_timestamp
        
        self.movement_events.append({
            'direction': direction,
            'delay': delay,
            'timestamp': time.time()
        })
    
    def get_stats(self):
        """Get current performance statistics"""
        stats = {
            'frame_times': {
                'min': min(self.frame_times) if self.frame_times else 0,
                'max': max(self.frame_times) if self.frame_times else 0,
                'avg': mean(self.frame_times) if self.frame_times else 0,
                'median': median(self.frame_times) if self.frame_times else 0,
                'p95': self._percentile(self.frame_times, 95) if self.frame_times else 0,
                'p99': self._percentile(self.frame_times, 99) if self.frame_times else 0,
            },
            'update_times': {
                'min': min(self.update_times) if self.update_times else 0,
                'max': max(self.update_times) if self.update_times else 0,
                'avg': mean(self.update_times) if self.update_times else 0,
                'median': median(self.update_times) if self.update_times else 0,
            },
            'render_times': {
                'min': min(self.render_times) if self.render_times else 0,
                'max': max(self.render_times) if self.render_times else 0,
                'avg': mean(self.render_times) if self.render_times else 0,
                'median': median(self.render_times) if self.render_times else 0,
            },
            'fps': {
                'min': 1000.0 / max(self.frame_times) if self.frame_times and max(self.frame_times) > 0 else 0,
                'max': 1000.0 / min(self.frame_times) if self.frame_times and min(self.frame_times) > 0 else 0,
                'avg': 1000.0 / mean(self.frame_times) if self.frame_times and mean(self.frame_times) > 0 else 0,
                'median': 1000.0 / median(self.frame_times) if self.frame_times and median(self.frame_times) > 0 else 0,
            },
            'chunk_load_count': len(self.chunk_load_events),
            'chunk_generation_count': len(self.chunk_generation_events),
            'chunk_save_count': len(self.chunk_save_events),
            'chunk_render_times': {
                'min': min(self.chunk_render_times) if self.chunk_render_times else 0,
                'max': max(self.chunk_render_times) if self.chunk_render_times else 0,
                'avg': mean(self.chunk_render_times) if self.chunk_render_times else 0,
                'median': median(self.chunk_render_times) if self.chunk_render_times else 0,
            },
            'movement_count': len(self.movement_events),
        }
        return stats
    
    def _percentile(self, data, percentile):
        """Calculate percentile of a list"""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]
    
    def print_stats(self):
        """Print performance statistics to console"""
        stats = self.get_stats()
        
        print(f"\nFrame Times (ms):")
        print(f"  Min: {stats['frame_times']['min']:.2f}")
        print(f"  Max: {stats['frame_times']['max']:.2f}")
        print(f"  Avg: {stats['frame_times']['avg']:.2f}")
        print(f"  Median: {stats['frame_times']['median']:.2f}")
        print(f"  P95: {stats['frame_times']['p95']:.2f}")
        print(f"  P99: {stats['frame_times']['p99']:.2f}")
        
        print(f"\nFPS:")
        print(f"  Min: {stats['fps']['min']:.1f}")
        print(f"  Max: {stats['fps']['max']:.1f}")
        print(f"  Avg: {stats['fps']['avg']:.1f}")
        print(f"  Median: {stats['fps']['median']:.1f}")
        
        print(f"\nUpdate Times (ms):")
        print(f"  Min: {stats['update_times']['min']:.2f}")
        print(f"  Max: {stats['update_times']['max']:.2f}")
        print(f"  Avg: {stats['update_times']['avg']:.2f}")
        print(f"  Median: {stats['update_times']['median']:.2f}")
        
        print(f"\nRender Times (ms):")
        print(f"  Min: {stats['render_times']['min']:.2f}")
        print(f"  Max: {stats['render_times']['max']:.2f}")
        print(f"  Avg: {stats['render_times']['avg']:.2f}")
        print(f"  Median: {stats['render_times']['median']:.2f}")
        
        print(f"\nChunk Loads: {stats['chunk_load_count']}")
        print(f"Chunk Generations: {stats['chunk_generation_count']}")
        print(f"Chunk Saves: {stats['chunk_save_count']}")
        
        if self.chunk_render_times:
            render_stats = stats['chunk_render_times']
            print(f"\nChunk Render Times (ms):")
            print(f"  Min: {render_stats['min']:.2f}")
            print(f"  Max: {render_stats['max']:.2f}")
            print(f"  Avg: {render_stats['avg']:.2f}")
            print(f"  Median: {render_stats['median']:.2f}")
        
        print(f"Movement Events: {stats['movement_count']}")
