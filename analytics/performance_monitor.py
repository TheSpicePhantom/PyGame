"""
Performance Monitor: Collects detailed performance metrics during gameplay
"""
import time
import os
import threading
from collections import deque
from statistics import mean, median
from typing import Dict, Tuple

# Try to import psutil for CPU/GPU monitoring
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class PerformanceMonitor:
    """Collects and analyzes performance metrics"""
    
    def __init__(self, diagnostics=None):
        """
        Initialize PerformanceMonitor
        
        Args:
            diagnostics: Optional DiagnosticsService instance for logging
        """
        self.enabled = True  # Always enabled
        self.diagnostics = diagnostics  # Store diagnostics service for logging
        
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
        
        # Chunk upload times (per frame) - time spent uploading vertex data to GPU
        self.chunk_upload_times = deque(maxlen=300)
        
        # Disk I/O times (per operation) - separate tracking for load and save
        self.disk_load_times = deque(maxlen=300)  # Track all disk load times
        self.disk_save_times = deque(maxlen=300)  # Track all disk save times
        
        # Region file performance tracking (only fastest and slowest 5)
        # Structure: {region_key: {'load_times': [...], 'save_times': [...], 'avg_load': float, 'avg_save': float}}
        self.region_file_stats: Dict[Tuple[int, int], Dict] = {}
        self._region_stats_lock = threading.Lock()  # Thread-safe access to region stats
        
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
    
    def record_chunk_upload_time(self, upload_time):
        """
        Record chunk upload time for a frame (time spent uploading vertex data to GPU)
        
        Args:
            upload_time: Time taken to upload chunk vertex data to GPU (in seconds)
        """
        if not self.enabled:
            return
        self.chunk_upload_times.append(upload_time * 1000)  # Convert to ms
    
    def record_region_file_load(self, region_x: int, region_y: int, load_time: float):
        """
        Record a region file load operation (Disk I/O)
        Only tracks the fastest and slowest 5 region files.
        
        Args:
            region_x: Region X coordinate
            region_y: Region Y coordinate
            load_time: Time taken to load from region file (in seconds)
        """
        if not self.enabled:
            return
        
        load_time_ms = load_time * 1000  # Convert to ms
        self.disk_load_times.append(load_time_ms)
        
        region_key = (region_x, region_y)
        
        with self._region_stats_lock:
            if region_key not in self.region_file_stats:
                self.region_file_stats[region_key] = {
                    'load_times': deque(maxlen=100),  # Keep last 100 load times per region
                    'save_times': deque(maxlen=100),  # Keep last 100 save times per region
                    'avg_load': 0.0,
                    'avg_save': 0.0,
                    'load_count': 0,
                    'save_count': 0
                }
            
            stats = self.region_file_stats[region_key]
            stats['load_times'].append(load_time_ms)
            stats['load_count'] += 1
            stats['avg_load'] = mean(stats['load_times']) if stats['load_times'] else 0.0
            
            # Keep only fastest and slowest 5 regions
            self._prune_region_stats()
    
    def record_region_file_save(self, region_x: int, region_y: int, save_time: float):
        """
        Record a region file save operation (Disk I/O)
        Only tracks the fastest and slowest 5 region files.
        
        Args:
            region_x: Region X coordinate
            region_y: Region Y coordinate
            save_time: Time taken to save to region file (in seconds)
        """
        if not self.enabled:
            return
        
        save_time_ms = save_time * 1000  # Convert to ms
        self.disk_save_times.append(save_time_ms)
        
        region_key = (region_x, region_y)
        
        with self._region_stats_lock:
            if region_key not in self.region_file_stats:
                self.region_file_stats[region_key] = {
                    'load_times': deque(maxlen=100),
                    'save_times': deque(maxlen=100),
                    'avg_load': 0.0,
                    'avg_save': 0.0,
                    'load_count': 0,
                    'save_count': 0
                }
            
            stats = self.region_file_stats[region_key]
            stats['save_times'].append(save_time_ms)
            stats['save_count'] += 1
            stats['avg_save'] = mean(stats['save_times']) if stats['save_times'] else 0.0
            
            # Keep only fastest and slowest 5 regions
            self._prune_region_stats()
    
    def _prune_region_stats(self):
        """
        Prune region stats to keep only the fastest and slowest 5 regions.
        Uses average load time as the metric for ranking.
        """
        if len(self.region_file_stats) <= 10:  # Keep all if 10 or fewer
            return
        
        # Calculate combined performance score (avg_load + avg_save) for ranking
        regions_with_scores = []
        for region_key, stats in self.region_file_stats.items():
            # Use combined average time as performance metric
            combined_avg = stats['avg_load'] + stats['avg_save']
            if combined_avg > 0:  # Only include regions with actual operations
                regions_with_scores.append((region_key, combined_avg))
        
        if len(regions_with_scores) <= 10:
            return  # Not enough regions to prune
        
        # Sort by combined average time (ascending = fastest first)
        regions_with_scores.sort(key=lambda x: x[1])
        
        # Keep fastest 5 and slowest 5
        fastest_5 = {key for key, _ in regions_with_scores[:5]}
        slowest_5 = {key for key, _ in regions_with_scores[-5:]}
        keep_regions = fastest_5 | slowest_5
        
        # Remove regions not in keep list
        regions_to_remove = [key for key in self.region_file_stats.keys() if key not in keep_regions]
        for key in regions_to_remove:
            del self.region_file_stats[key]
    
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
            'chunk_upload_times': {
                'min': min(self.chunk_upload_times) if self.chunk_upload_times else 0,
                'max': max(self.chunk_upload_times) if self.chunk_upload_times else 0,
                'avg': mean(self.chunk_upload_times) if self.chunk_upload_times else 0,
                'median': median(self.chunk_upload_times) if self.chunk_upload_times else 0,
            },
            'disk_load_times': {
                'min': min(self.disk_load_times) if self.disk_load_times else 0,
                'max': max(self.disk_load_times) if self.disk_load_times else 0,
                'avg': mean(self.disk_load_times) if self.disk_load_times else 0,
                'median': median(self.disk_load_times) if self.disk_load_times else 0,
                'count': len(self.disk_load_times),
            },
            'disk_save_times': {
                'min': min(self.disk_save_times) if self.disk_save_times else 0,
                'max': max(self.disk_save_times) if self.disk_save_times else 0,
                'avg': mean(self.disk_save_times) if self.disk_save_times else 0,
                'median': median(self.disk_save_times) if self.disk_save_times else 0,
                'count': len(self.disk_save_times),
            },
            'region_file_stats': self._get_region_file_stats_summary(),
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
    
    def _get_region_file_stats_summary(self):
        """Get summary of region file statistics (fastest and slowest 5)"""
        with self._region_stats_lock:
            if not self.region_file_stats:
                return {}
            
            # Sort regions by combined average time
            regions_list = []
            for region_key, stats in self.region_file_stats.items():
                combined_avg = stats['avg_load'] + stats['avg_save']
                if combined_avg > 0:
                    regions_list.append({
                        'region_x': region_key[0],
                        'region_y': region_key[1],
                        'avg_load': stats['avg_load'],
                        'avg_save': stats['avg_save'],
                        'combined_avg': combined_avg,
                        'load_count': stats['load_count'],
                        'save_count': stats['save_count'],
                    })
            
            # Sort by combined average (ascending = fastest first)
            regions_list.sort(key=lambda x: x['combined_avg'])
            
            return {
                'fastest_5': regions_list[:5] if len(regions_list) >= 5 else regions_list,
                'slowest_5': regions_list[-5:] if len(regions_list) >= 5 else [],
                'total_regions_tracked': len(self.region_file_stats),
            }
    
    def print_stats(self):
        """Print performance statistics using diagnostics service"""
        stats = self.get_stats()
        
        if not self.diagnostics:
            return  # No diagnostics service available, skip output
        
        # Use diagnostics service for structured logging
        self.diagnostics.info("PerformanceMonitor", "Performance Statistics:")
        
        # Frame Times
        self.diagnostics.info("PerformanceMonitor", 
            f"Frame Times (ms) - Min: {stats['frame_times']['min']:.2f}, "
            f"Max: {stats['frame_times']['max']:.2f}, "
            f"Avg: {stats['frame_times']['avg']:.2f}, "
            f"Median: {stats['frame_times']['median']:.2f}, "
            f"P95: {stats['frame_times']['p95']:.2f}, "
            f"P99: {stats['frame_times']['p99']:.2f}")
        
        # FPS
        self.diagnostics.info("PerformanceMonitor",
            f"FPS - Min: {stats['fps']['min']:.1f}, "
            f"Max: {stats['fps']['max']:.1f}, "
            f"Avg: {stats['fps']['avg']:.1f}, "
            f"Median: {stats['fps']['median']:.1f}")
        
        # Update Times
        self.diagnostics.info("PerformanceMonitor",
            f"Update Times (ms) - Min: {stats['update_times']['min']:.2f}, "
            f"Max: {stats['update_times']['max']:.2f}, "
            f"Avg: {stats['update_times']['avg']:.2f}, "
            f"Median: {stats['update_times']['median']:.2f}")
        
        # Render Times
        self.diagnostics.info("PerformanceMonitor",
            f"Render Times (ms) - Min: {stats['render_times']['min']:.2f}, "
            f"Max: {stats['render_times']['max']:.2f}, "
            f"Avg: {stats['render_times']['avg']:.2f}, "
            f"Median: {stats['render_times']['median']:.2f}")
        
        # Chunk Statistics
        self.diagnostics.info("PerformanceMonitor",
            f"Chunk Statistics - Loads: {stats['chunk_load_count']}, "
            f"Generations: {stats['chunk_generation_count']}, "
            f"Saves: {stats['chunk_save_count']}, "
            f"Modifications: {stats['chunk_modified_count']}")
        
        # Chunk Render Times
        if self.chunk_render_times:
            render_stats = stats['chunk_render_times']
            self.diagnostics.info("PerformanceMonitor",
                f"Chunk Render Times (ms) - Min: {render_stats['min']:.2f}, "
                f"Max: {render_stats['max']:.2f}, "
                f"Avg: {render_stats['avg']:.2f}, "
                f"Median: {render_stats['median']:.2f}")
        
        # Chunk Upload Times
        if self.chunk_upload_times:
            upload_stats = stats['chunk_upload_times']
            self.diagnostics.info("PerformanceMonitor",
                f"Chunk Upload Times (ms) - Min: {upload_stats['min']:.2f}, "
                f"Max: {upload_stats['max']:.2f}, "
                f"Avg: {upload_stats['avg']:.2f}, "
                f"Median: {upload_stats['median']:.2f}")
        
        # Disk I/O Statistics
        if self.disk_load_times:
            load_stats = stats['disk_load_times']
            self.diagnostics.info("PerformanceMonitor",
                f"Disk Load Times (ms) - Min: {load_stats['min']:.2f}, "
                f"Max: {load_stats['max']:.2f}, "
                f"Avg: {load_stats['avg']:.2f}, "
                f"Median: {load_stats['median']:.2f}, "
                f"Count: {load_stats['count']}")
        
        if self.disk_save_times:
            save_stats = stats['disk_save_times']
            self.diagnostics.info("PerformanceMonitor",
                f"Disk Save Times (ms) - Min: {save_stats['min']:.2f}, "
                f"Max: {save_stats['max']:.2f}, "
                f"Avg: {save_stats['avg']:.2f}, "
                f"Median: {save_stats['median']:.2f}, "
                f"Count: {save_stats['count']}")
        
        # Region File Performance (Fastest and Slowest 5)
        region_stats = stats['region_file_stats']
        if region_stats and (region_stats.get('fastest_5') or region_stats.get('slowest_5')):
            self.diagnostics.info("PerformanceMonitor", "Region File Performance (Top 5 Fastest & Slowest):")
            
            fastest = region_stats.get('fastest_5', [])
            if fastest:
                self.diagnostics.info("PerformanceMonitor", "  Fastest 5 Regions:")
                for i, region in enumerate(fastest, 1):
                    self.diagnostics.info("PerformanceMonitor",
                        f"    {i}. Region ({region['region_x']}, {region['region_y']}): "
                        f"Load={region['avg_load']:.2f}ms, Save={region['avg_save']:.2f}ms, "
                        f"Combined={region['combined_avg']:.2f}ms "
                        f"(Loads: {region['load_count']}, Saves: {region['save_count']})")
            
            slowest = region_stats.get('slowest_5', [])
            if slowest:
                self.diagnostics.info("PerformanceMonitor", "  Slowest 5 Regions:")
                for i, region in enumerate(slowest, 1):
                    self.diagnostics.info("PerformanceMonitor",
                        f"    {i}. Region ({region['region_x']}, {region['region_y']}): "
                        f"Load={region['avg_load']:.2f}ms, Save={region['avg_save']:.2f}ms, "
                        f"Combined={region['combined_avg']:.2f}ms "
                        f"(Loads: {region['load_count']}, Saves: {region['save_count']})")
        
        # Movement Events
        self.diagnostics.info("PerformanceMonitor", f"Movement Events: {stats['movement_count']}")
        
        # CPU Usage
        if self.cpu_usage_samples:
            cpu_stats = stats['cpu_usage']
            self.diagnostics.info("PerformanceMonitor",
                f"CPU Usage (%) - Current: {cpu_stats['current']:.1f}, "
                f"Avg: {cpu_stats['avg']:.1f}, "
                f"Max: {cpu_stats['max']:.1f}")
        
        # GPU Usage
        if self.gpu_usage_samples:
            gpu_stats = stats['gpu_usage']
            self.diagnostics.info("PerformanceMonitor",
                f"GPU Usage (%) - Current: {gpu_stats['current']:.1f}, "
                f"Avg: {gpu_stats['avg']:.1f}, "
                f"Max: {gpu_stats['max']:.1f}")
    
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
