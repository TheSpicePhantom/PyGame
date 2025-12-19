"""
Performance Monitor: Collects detailed performance metrics during gameplay
"""
import time
import os
from collections import deque
from statistics import mean, median

# Try to import psutil for CPU/GPU monitoring
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


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
        
        # Chunk modification events (chunks marked as dirty)
        self.chunk_modified_events = []
        
        # Chunk loaded from disk events (separate from generation)
        self.chunk_loaded_from_disk_events = []
        
        # Chunk migrated from legacy format events
        self.chunk_migrated_legacy_events = []
        
        # Chunk render times (per frame)
        self.chunk_render_times = deque(maxlen=300)
        
        # Optional logger reference for automatic event logging
        self.logger = None
        
        # Movement events (direction, delay)
        self.movement_events = []
        
        # CPU/GPU usage tracking
        self.cpu_usage_samples = deque(maxlen=60)  # Last 60 samples (~1 second at 60 FPS)
        self.gpu_usage_samples = deque(maxlen=60)
        self.last_cpu_check = time.time()
        self.last_gpu_check = time.time()
        
        # Initialize CPU/GPU monitoring
        if PSUTIL_AVAILABLE:
            self.process = psutil.Process(os.getpid())
            try:
                # Try to get GPU info (requires nvidia-ml-py or similar)
                self.gpu_available = False
            except:
                self.gpu_available = False
        else:
            self.process = None
            self.gpu_available = False
    
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
        
        # Update CPU/GPU usage periodically (every ~16ms = 60 times per second)
        current_time = time.time()
        if current_time - self.last_cpu_check >= 0.016:  # ~60 Hz
            self._update_cpu_usage()
            self._update_gpu_usage()
            self.last_cpu_check = current_time
    
    def record_chunk_load(self, chunk_x, chunk_y, load_time):
        """Record a chunk load event"""
        if not self.enabled:
            return
        event = {
            'chunk_x': chunk_x,
            'chunk_y': chunk_y,
            'load_time': load_time * 1000,  # Convert to ms
            'timestamp': time.time()
        }
        self.chunk_load_events.append(event)
        # Automatically log to logger if available
        if self.logger:
            self.logger.log_chunk_load_event(event)
    
    def record_chunk_generation(self, chunk_x, chunk_y, generation_time):
        """Record a chunk generation event (separate from load)"""
        if not self.enabled:
            return
        event = {
            'chunk_x': chunk_x,
            'chunk_y': chunk_y,
            'generation_time': generation_time * 1000,  # Convert to ms
            'timestamp': time.time()
        }
        self.chunk_generation_events.append(event)
        # Automatically log to logger if available
        if self.logger:
            self.logger.log_chunk_generation_event(event)
    
    def record_chunk_save(self, chunk_x, chunk_y, save_time):
        """Record a chunk save event"""
        if not self.enabled:
            return
        event = {
            'chunk_x': chunk_x,
            'chunk_y': chunk_y,
            'save_time': save_time * 1000,  # Convert to ms
            'timestamp': time.time()
        }
        self.chunk_save_events.append(event)
        # Automatically log to logger if available
        if self.logger:
            self.logger.log_chunk_save_event(event)
    
    def record_chunk_modified(self, chunk_x, chunk_y):
        """Record a chunk modification event (chunk marked as dirty)"""
        if not self.enabled:
            return
        event = {
            'chunk_x': chunk_x,
            'chunk_y': chunk_y,
            'timestamp': time.time()
        }
        self.chunk_modified_events.append(event)
        # Automatically log to logger if available
        if self.logger:
            self.logger.log_chunk_modified_event(event)
    
    def record_chunk_loaded_from_disk(self, chunk_x, chunk_y, load_time):
        """
        Record a chunk loaded from disk event (IO operation, separate from generation)
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
            load_time: Time taken to load chunk from disk (in seconds)
        """
        if not self.enabled:
            return
        event = {
            'chunk_x': chunk_x,
            'chunk_y': chunk_y,
            'load_time': load_time * 1000,  # Convert to ms
            'timestamp': time.time()
        }
        self.chunk_loaded_from_disk_events.append(event)
        # Automatically log to logger if available
        if self.logger:
            self.logger.log_chunk_loaded_from_disk_event(event)
    
    def record_chunk_migrated_legacy(self, chunk_x, chunk_y, migration_time):
        """
        Record a chunk migrated from legacy JSON format to region format
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_y: Chunk Y coordinate
            migration_time: Time taken to migrate chunk (in seconds)
        """
        if not self.enabled:
            return
        event = {
            'chunk_x': chunk_x,
            'chunk_y': chunk_y,
            'migration_time': migration_time * 1000,  # Convert to ms
            'timestamp': time.time()
        }
        self.chunk_migrated_legacy_events.append(event)
        # Automatically log to logger if available
        if self.logger:
            self.logger.log_chunk_migrated_legacy_event(event)
    
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
                'current': 1000.0 / self.frame_times[-1] if self.frame_times and self.frame_times[-1] > 0 else 0,
                'min': 1000.0 / max(self.frame_times) if self.frame_times and max(self.frame_times) > 0 else 0,
                'max': 1000.0 / min(self.frame_times) if self.frame_times and min(self.frame_times) > 0 else 0,
                'avg': 1000.0 / mean(self.frame_times) if self.frame_times and mean(self.frame_times) > 0 else 0,
                'median': 1000.0 / median(self.frame_times) if self.frame_times and median(self.frame_times) > 0 else 0,
            },
            'chunk_load_count': len(self.chunk_load_events),
            'chunk_generation_count': len(self.chunk_generation_events),
            'chunk_save_count': len(self.chunk_save_events),
            'chunk_modified_count': len(self.chunk_modified_events),
            'chunk_render_times': {
                'min': min(self.chunk_render_times) if self.chunk_render_times else 0,
                'max': max(self.chunk_render_times) if self.chunk_render_times else 0,
                'avg': mean(self.chunk_render_times) if self.chunk_render_times else 0,
                'median': median(self.chunk_render_times) if self.chunk_render_times else 0,
            },
            'movement_count': len(self.movement_events),
            'cpu_usage': {
                'current': self.cpu_usage_samples[-1] if self.cpu_usage_samples else 0,
                'avg': mean(self.cpu_usage_samples) if self.cpu_usage_samples else 0,
                'max': max(self.cpu_usage_samples) if self.cpu_usage_samples else 0,
            },
            'gpu_usage': {
                'current': self.gpu_usage_samples[-1] if self.gpu_usage_samples else 0,
                'avg': mean(self.gpu_usage_samples) if self.gpu_usage_samples else 0,
                'max': max(self.gpu_usage_samples) if self.gpu_usage_samples else 0,
            },
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
        print(f"Chunk Modifications: {stats['chunk_modified_count']}")
        
        if self.chunk_render_times:
            render_stats = stats['chunk_render_times']
            print(f"\nChunk Render Times (ms):")
            print(f"  Min: {render_stats['min']:.2f}")
            print(f"  Max: {render_stats['max']:.2f}")
            print(f"  Avg: {render_stats['avg']:.2f}")
            print(f"  Median: {render_stats['median']:.2f}")
        
        print(f"Movement Events: {stats['movement_count']}")
        
        if self.cpu_usage_samples:
            cpu_stats = stats['cpu_usage']
            print(f"\nCPU Usage (%):")
            print(f"  Current: {cpu_stats['current']:.1f}")
            print(f"  Avg: {cpu_stats['avg']:.1f}")
            print(f"  Max: {cpu_stats['max']:.1f}")
        
        if self.gpu_usage_samples:
            gpu_stats = stats['gpu_usage']
            print(f"\nGPU Usage (%):")
            print(f"  Current: {gpu_stats['current']:.1f}")
            print(f"  Avg: {gpu_stats['avg']:.1f}")
            print(f"  Max: {gpu_stats['max']:.1f}")
    
    def _update_cpu_usage(self):
        """Update CPU usage (process-specific) using psutil"""
        if PSUTIL_AVAILABLE and self.process:
            try:
                # Get CPU usage for this process (non-blocking, uses last call's interval)
                cpu_percent = self.process.cpu_percent(interval=None)
                # Also get system-wide CPU usage for context
                system_cpu = psutil.cpu_percent(interval=None)
                
                # Use process CPU, but cap at reasonable values
                cpu_percent = max(0.0, min(100.0, cpu_percent))
                self.cpu_usage_samples.append(cpu_percent)
            except Exception as e:
                # Fallback: estimate from frame times
                if self.frame_times:
                    avg_frame_time = mean(self.frame_times)
                    # Estimate: if frame time is high relative to target (8.33ms for 120 FPS), CPU might be busy
                    # But this is just a rough estimate
                    cpu_estimate = min(100.0, max(0.0, (avg_frame_time / 8.33) * 50.0))  # Cap at 50% for estimate
                    self.cpu_usage_samples.append(cpu_estimate)
        else:
            # Fallback: estimate from frame times (less accurate)
            if self.frame_times:
                avg_frame_time = mean(self.frame_times)
                cpu_estimate = min(100.0, max(0.0, (avg_frame_time / 8.33) * 50.0))
                self.cpu_usage_samples.append(cpu_estimate)
            else:
                self.cpu_usage_samples.append(0.0)
    
    def _update_gpu_usage(self):
        """Update GPU usage - try psutil first, then estimate from render times"""
        # Try to get GPU usage from psutil (if available and GPU sensors are accessible)
        gpu_usage = None
        
        if PSUTIL_AVAILABLE:
            try:
                # psutil can sometimes access GPU info through sensors
                # Check if GPU sensors are available
                sensors = psutil.sensors_temperatures()
                # Note: psutil doesn't directly provide GPU usage, but we can try other methods
                
                # For now, we'll estimate based on render time vs available frame budget
                # This is more accurate than render_time / frame_time
                if self.render_times and self.frame_times:
                    avg_render_time = mean(self.render_times)
                    avg_frame_time = mean(self.frame_times)
                    
                    # Target frame time at 120 FPS = 8.33ms
                    target_frame_time = 8.33
                    
                    if avg_frame_time > 0:
                        # Estimate GPU usage: how much of the frame budget is used for rendering
                        # But normalize it better: if render time is close to frame time, GPU is busy
                        # But we need to account for the fact that at high FPS, render time can be small
                        # relative to frame time, so GPU might not be fully utilized
                        
                        # Better estimate: if render time is high relative to target frame time, GPU is busy
                        # But cap it reasonably - GPU usage shouldn't be 100% just because render time = frame time
                        render_ratio = avg_render_time / target_frame_time
                        # Normalize: if render time is 50% of target frame time, GPU is ~50% utilized
                        # This is still an estimate, but more reasonable
                        gpu_estimate = min(100.0, max(0.0, render_ratio * 100.0))
                        self.gpu_usage_samples.append(gpu_estimate)
                    else:
                        self.gpu_usage_samples.append(0.0)
                else:
                    self.gpu_usage_samples.append(0.0)
                    
            except Exception:
                # Fallback: simple estimate
                if self.render_times:
                    avg_render_time = mean(self.render_times)
                    # Estimate: if render time is high (>5ms), GPU is busy
                    # This is a very rough estimate
                    gpu_estimate = min(100.0, max(0.0, (avg_render_time / 8.33) * 80.0))
                    self.gpu_usage_samples.append(gpu_estimate)
                else:
                    self.gpu_usage_samples.append(0.0)
        else:
            # No psutil: use simple estimate
            if self.render_times:
                avg_render_time = mean(self.render_times)
                gpu_estimate = min(100.0, max(0.0, (avg_render_time / 8.33) * 80.0))
                self.gpu_usage_samples.append(gpu_estimate)
            else:
                self.gpu_usage_samples.append(0.0)
