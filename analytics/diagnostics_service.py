"""
Analytics: DiagnosticsService - Zentraler Service für Performance-Monitoring und Logging
"""
import time
from typing import Optional, Dict, Any
from enum import Enum
from analytics.performance_monitor import PerformanceMonitor
from analytics.logger import PerformanceLogger


class LogLevel(Enum):
    """Log-Level für verschiedene Arten von Nachrichten"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class DiagnosticsService:
    """
    Zentraler Service für Performance-Monitoring und Logging.
    
    Bündelt:
    - PerformanceMonitor (FPS, CPU/GPU, Frame-Timing)
    - PerformanceLogger (Persistente Logs)
    - Logging-API (Ersatz für print()-Statements)
    - Performance-Events (Chunk-Loads, Saves, etc.)
    """
    
    def __init__(self, enable_logging: bool = True, log_to_file: bool = True):
        """
        Args:
            enable_logging: Ob Logging aktiviert sein soll
            log_to_file: Ob Logs in Dateien gespeichert werden sollen
        """
        self.enable_logging = enable_logging
        self.log_to_file = log_to_file
        
        # Initialize performance monitoring (pass self as diagnostics service)
        self.performance_monitor = PerformanceMonitor(diagnostics=self)
        
        # Initialize performance logger (if file logging enabled)
        self.performance_logger: Optional[PerformanceLogger] = None
        if log_to_file:
            self.performance_logger = PerformanceLogger()
            self.performance_logger.start_log()
            self.performance_monitor.logger = self.performance_logger
        
        # Logging configuration
        self.min_log_level = LogLevel.DEBUG  # Default: log everything
        self.log_to_console = True  # Print to console by default
        
        # Performance event tracking
        self.event_callbacks: Dict[str, list] = {}  # Event name -> list of callbacks
        
        # Frame timing
        self.last_stats_log_time = 0.0
        self.stats_log_interval = 0.5  # Log stats every 0.5 seconds
    
    # ==================== Performance Monitoring API ====================
    
    def start_frame(self):
        """Start timing a new frame"""
        self.performance_monitor.start_frame()
    
    def start_update(self):
        """Start timing update phase"""
        self.performance_monitor.start_update()
    
    def end_update(self):
        """End timing update phase"""
        self.performance_monitor.end_update()
    
    def start_render(self):
        """Start timing render phase"""
        self.performance_monitor.start_render()
    
    def end_render(self):
        """End timing render phase"""
        self.performance_monitor.end_render()
        
        # Auto-log stats periodically
        current_time = time.time()
        if current_time - self.last_stats_log_time >= self.stats_log_interval:
            if self.performance_logger:
                stats = self.performance_monitor.get_stats()
                self.performance_logger.log_stats(stats)
            self.last_stats_log_time = current_time
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current performance statistics"""
        return self.performance_monitor.get_stats()
    
    # ==================== Performance Events API ====================
    
    def record_chunk_load(self, chunk_x: int, chunk_y: int, load_time: float):
        """Record a chunk load event"""
        self.performance_monitor.record_chunk_load(chunk_x, chunk_y, load_time)
        self._trigger_event('chunk_load', {'chunk_x': chunk_x, 'chunk_y': chunk_y, 'load_time': load_time})
    
    def record_chunk_generation(self, chunk_x: int, chunk_y: int, generation_time: float):
        """Record a chunk generation event"""
        self.performance_monitor.record_chunk_generation(chunk_x, chunk_y, generation_time)
        self._trigger_event('chunk_generation', {'chunk_x': chunk_x, 'chunk_y': chunk_y, 'generation_time': generation_time})
    
    def record_chunk_save(self, chunk_x: int, chunk_y: int, save_time: float):
        """Record a chunk save event"""
        self.performance_monitor.record_chunk_save(chunk_x, chunk_y, save_time)
        self._trigger_event('chunk_save', {'chunk_x': chunk_x, 'chunk_y': chunk_y, 'save_time': save_time})
    
    def record_chunk_loaded_from_disk(self, chunk_x: int, chunk_y: int, load_time: float):
        """Record a chunk loaded from disk event"""
        self.performance_monitor.record_chunk_loaded_from_disk(chunk_x, chunk_y, load_time)
        self._trigger_event('chunk_loaded_from_disk', {'chunk_x': chunk_x, 'chunk_y': chunk_y, 'load_time': load_time})
    
    def record_chunk_migrated_legacy(self, chunk_x: int, chunk_y: int):
        """Record a chunk migrated from legacy format event"""
        self.performance_monitor.record_chunk_migrated_legacy(chunk_x, chunk_y)
        self._trigger_event('chunk_migrated_legacy', {'chunk_x': chunk_x, 'chunk_y': chunk_y})
    
    def record_chunk_modified(self, chunk_x: int, chunk_y: int):
        """Record a chunk modification event (chunk marked as dirty)"""
        self.performance_monitor.record_chunk_modified(chunk_x, chunk_y)
        self._trigger_event('chunk_modified', {'chunk_x': chunk_x, 'chunk_y': chunk_y})
    
    def record_movement(self, direction: str, delay: float):
        """Record a player movement event"""
        self.performance_monitor.record_movement(direction, delay)
        self._trigger_event('movement', {'direction': direction, 'delay': delay})
    
    # ==================== Logging API ====================
    
    def log(self, level: LogLevel, component: str, message: str, **kwargs):
        """
        Log a message with level, component, and optional context
        
        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            component: Component name (e.g., "ChunkManager", "RegionManager")
            message: Log message
            **kwargs: Additional context data
        """
        if not self.enable_logging:
            return
        
        # Check if message should be logged based on min_log_level
        level_priority = {
            LogLevel.DEBUG: 0,
            LogLevel.INFO: 1,
            LogLevel.WARNING: 2,
            LogLevel.ERROR: 3,
            LogLevel.CRITICAL: 4
        }
        
        if level_priority[level] < level_priority[self.min_log_level]:
            return
        
        # Format log message
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        log_prefix = f"[{timestamp}][{component}][{level.value}]"
        
        # Build context string if kwargs provided
        context_str = ""
        if kwargs:
            context_parts = [f"{k}={v}" for k, v in kwargs.items()]
            context_str = f" ({', '.join(context_parts)})"
        
        formatted_message = f"{log_prefix} {message}{context_str}"
        
        # Log to console
        if self.log_to_console:
            print(formatted_message)
        
        # Log to file (if enabled and logger exists)
        if self.log_to_file and self.performance_logger:
            # PerformanceLogger doesn't have a general log method, so we skip file logging for now
            # Could be extended in the future
            pass
    
    def debug(self, component: str, message: str, **kwargs):
        """Log a DEBUG message"""
        self.log(LogLevel.DEBUG, component, message, **kwargs)
    
    def info(self, component: str, message: str, **kwargs):
        """Log an INFO message"""
        self.log(LogLevel.INFO, component, message, **kwargs)
    
    def warning(self, component: str, message: str, **kwargs):
        """Log a WARNING message"""
        self.log(LogLevel.WARNING, component, message, **kwargs)
    
    def error(self, component: str, message: str, **kwargs):
        """Log an ERROR message"""
        self.log(LogLevel.ERROR, component, message, **kwargs)
    
    def critical(self, component: str, message: str, **kwargs):
        """Log a CRITICAL message"""
        self.log(LogLevel.CRITICAL, component, message, **kwargs)
    
    # ==================== Event Callbacks ====================
    
    def register_event_callback(self, event_name: str, callback):
        """
        Register a callback for a specific event
        
        Args:
            event_name: Name of the event (e.g., 'chunk_load', 'chunk_save')
            callback: Callback function that will be called with event data
        """
        if event_name not in self.event_callbacks:
            self.event_callbacks[event_name] = []
        self.event_callbacks[event_name].append(callback)
    
    def unregister_event_callback(self, event_name: str, callback):
        """Unregister an event callback"""
        if event_name in self.event_callbacks:
            self.event_callbacks[event_name].remove(callback)
    
    def _trigger_event(self, event_name: str, event_data: Dict[str, Any]):
        """Trigger all callbacks for an event"""
        if event_name in self.event_callbacks:
            for callback in self.event_callbacks[event_name]:
                try:
                    callback(event_data)
                except Exception as e:
                    self.error("DiagnosticsService", f"Error in event callback for {event_name}: {e}")
    
    # ==================== Configuration ====================
    
    def set_log_level(self, level: LogLevel):
        """Set minimum log level"""
        self.min_log_level = level
    
    def set_log_to_console(self, enabled: bool):
        """Enable/disable console logging"""
        self.log_to_console = enabled
    
    def set_stats_log_interval(self, interval: float):
        """Set interval for automatic stats logging (in seconds)"""
        self.stats_log_interval = interval
    
    # ==================== Cleanup ====================
    
    def cleanup(self):
        """Cleanup and save logs"""
        if self.performance_logger:
            self.performance_logger.save_log()
            self.info("DiagnosticsService", "Performance logs saved")
    
    def get_performance_monitor(self) -> PerformanceMonitor:
        """Get the underlying PerformanceMonitor instance (for compatibility)"""
        return self.performance_monitor
    
    def get_performance_logger(self) -> Optional[PerformanceLogger]:
        """Get the underlying PerformanceLogger instance (for compatibility)"""
        return self.performance_logger


