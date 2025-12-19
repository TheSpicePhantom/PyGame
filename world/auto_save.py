"""
Auto-Save System: Automatically saves game at configurable intervals
"""
import threading
import time
import logging
import traceback
from typing import Optional, Callable
from config.settings_manager import settings_manager


class AutoSaveSystem:
    """Manages automatic game saving at configurable intervals"""
    
    def __init__(self, save_callback: Callable, get_player_pos: Callable, get_game_state: Optional[Callable] = None, debug_mode: bool = False, max_retries: int = 2):
        """
        Initialize Auto-Save System
        
        Args:
            save_callback: Function to call when saving (should save world and player)
            get_player_pos: Function that returns current player position (x, y)
            get_game_state: Optional function that returns game state dict with keys:
                - 'can_save': bool - True if game is in a state where saving is allowed
                - 'is_paused': bool - True if game is paused
                - 'menu_active': bool - True if any menu is active
                If None, only player movement is checked (default: None)
            debug_mode: If True, print full tracebacks for exceptions (default: False)
            max_retries: Maximum number of retry attempts for IO errors (default: 2)
        """
        self.save_callback = save_callback
        self.get_player_pos = get_player_pos
        self.get_game_state = get_game_state
        self.debug_mode = debug_mode
        self.max_retries = max_retries
        self.running = False
        self.save_thread: Optional[threading.Thread] = None
        self.last_save_time = 0.0
        self.last_player_pos = None
        
        # Setup logger
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            # Add console handler if not already configured
            handler = logging.StreamHandler()
            formatter = logging.Formatter('[%(name)s] %(levelname)s: %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
        
        # Thread-safe cached settings (updated only from main thread)
        # These are read by the background thread, so we cache them to avoid
        # thread-safety issues when reading from settings_manager.graphics
        self._cached_interval: float = self._read_interval()
        self._cached_enabled: bool = self._read_enabled()
        self._settings_lock = threading.Lock()  # Lock for updating cached values
        
    def _read_interval(self) -> float:
        """Read interval from settings (called from main thread only)"""
        interval = settings_manager.graphics.get('auto_save_interval', 30)
        return float(interval)
    
    def _read_enabled(self) -> bool:
        """Read enabled state from settings (called from main thread only)"""
        return settings_manager.graphics.get('auto_save_enabled', True)
    
    def get_interval(self) -> float:
        """
        Get auto-save interval in seconds (thread-safe cached value)
        
        Returns:
            Cached interval value (updated only from main thread)
        """
        with self._settings_lock:
            return self._cached_interval
    
    def set_interval(self, seconds: float):
        """
        Set auto-save interval in seconds (updates cache and settings)
        
        Args:
            seconds: New interval in seconds
        
        Note:
            This method should be called from the main thread only.
            The cached value is updated immediately for thread-safe access.
        """
        with self._settings_lock:
            self._cached_interval = float(seconds)
        
        # Update settings (main thread only)
        settings_manager.graphics['auto_save_interval'] = int(seconds)
        settings_manager.save_settings()
    
    def is_enabled(self) -> bool:
        """
        Check if auto-save is enabled (thread-safe cached value)
        
        Returns:
            Cached enabled state (updated only from main thread)
        """
        with self._settings_lock:
            return self._cached_enabled
    
    def set_enabled(self, enabled: bool):
        """
        Enable or disable auto-save (updates cache and settings)
        
        Args:
            enabled: True to enable, False to disable
        
        Note:
            This method should be called from the main thread only.
            The cached value is updated immediately for thread-safe access.
        """
        with self._settings_lock:
            self._cached_enabled = enabled
        
        # Update settings (main thread only)
        settings_manager.graphics['auto_save_enabled'] = enabled
        settings_manager.save_settings()
        
        if enabled and not self.running:
            self.start()
        elif not enabled and self.running:
            self.stop()
    
    def start(self):
        """Start auto-save system"""
        if self.running:
            return
        
        # Refresh cached settings before starting (main thread)
        with self._settings_lock:
            self._cached_interval = self._read_interval()
            self._cached_enabled = self._read_enabled()
        
        if not self._cached_enabled:
            return
        
        self.running = True
        self.last_save_time = time.time()
        self.last_player_pos = self.get_player_pos()
        
        def run_auto_save():
            """Background thread for auto-save (uses cached settings for thread safety)"""
            while self.running:
                # Check if still enabled (thread-safe cached read)
                with self._settings_lock:
                    enabled = self._cached_enabled
                    interval = self._cached_interval
                
                if not enabled:
                    break  # Exit thread if disabled
                
                current_time = time.time()
                
                # Check if interval has passed
                if current_time - self.last_save_time >= interval:
                    # Check game state (if callback provided)
                    can_save = True
                    if self.get_game_state:
                        try:
                            game_state = self.get_game_state()
                            if isinstance(game_state, dict):
                                # Use explicit 'can_save' flag if provided
                                if 'can_save' in game_state:
                                    can_save = game_state['can_save']
                                else:
                                    # Fallback: check individual flags
                                    is_paused = game_state.get('is_paused', False)
                                    menu_active = game_state.get('menu_active', False)
                                    can_save = not is_paused and not menu_active
                        except Exception as e:
                            # If game state check fails, log warning but allow save attempt
                            self.logger.warning(f"Failed to check game state: {e}. Proceeding with save check.")
                            can_save = True
                    
                    # Only save if game state allows it and player has moved (avoid saving when paused/in menus)
                    if can_save:
                        current_pos = self.get_player_pos()
                        if current_pos != self.last_player_pos:
                            self.logger.info(f"Auto-saving game (interval: {interval}s)...")
                            if self._save_with_retry("auto-save"):
                                self.last_save_time = current_time
                                self.last_player_pos = current_pos
                                self.logger.info("Auto-save completed")
                            else:
                                self.logger.error("Auto-save failed - will retry on next interval")
                        else:
                            # Player hasn't moved, skip save (but don't log - this is normal)
                            pass
                    else:
                        # Game state doesn't allow saving (paused/menu active), skip silently
                        pass
                
                # Sleep for 1 second, then check again
                time.sleep(1.0)
        
        self.save_thread = threading.Thread(target=run_auto_save, daemon=True, name="AutoSave")
        self.save_thread.start()
        self.logger.info(f"Started (interval: {self.get_interval()}s)")
    
    def _save_with_retry(self, operation_name: str = "save") -> bool:
        """
        Execute save_callback with retry logic for IO errors
        
        Args:
            operation_name: Name of the operation for logging (e.g., "auto-save", "force save")
        
        Returns:
            True if save succeeded, False if all retries failed
        """
        retry_delay = 0.5  # Initial delay between retries (seconds)
        
        for attempt in range(self.max_retries + 1):  # +1 for initial attempt
            try:
                self.save_callback()
                if attempt > 0:
                    self.logger.info(f"{operation_name.capitalize()} succeeded on retry {attempt}")
                return True
            except (IOError, OSError) as e:
                # IO-related errors: retry with backoff
                if attempt < self.max_retries:
                    self.logger.warning(
                        f"{operation_name.capitalize()} failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}. "
                        f"Retrying in {retry_delay}s..."
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    # Final attempt failed
                    self.logger.error(
                        f"{operation_name.capitalize()} failed after {self.max_retries + 1} attempts: {e}"
                    )
                    if self.debug_mode:
                        self.logger.debug("Full traceback:", exc_info=True)
                    return False
            except Exception as e:
                # Non-IO errors: log and don't retry
                self.logger.error(f"{operation_name.capitalize()} failed with unexpected error: {e}")
                if self.debug_mode:
                    self.logger.debug("Full traceback:", exc_info=True)
                    traceback.print_exc()
                return False
        
        return False
    
    def stop(self, final_save: bool = True):
        """
        Stop auto-save system and wait for thread to terminate
        
        Args:
            final_save: If True (default), perform a final save before stopping
        
        IMPORTANT: This method MUST be called during game shutdown (e.g., from World.cleanup()
        or in main.py) to ensure the background thread is properly terminated. Failure to call
        stop() may result in the thread continuing to run after the game exits.
        
        Lifecycle: This marks the end of the AutoSaveSystem lifecycle. After stop(), the
        instance should not be used anymore unless start() is called again.
        """
        if not self.running:
            return
        
        # Perform final save before stopping (if requested)
        if final_save:
            self.logger.info("Performing final save before shutdown...")
            self.force_save()
        
        self.running = False
        if self.save_thread:
            self.save_thread.join(timeout=2.0)
        self.logger.info("Stopped")
    
    def force_save(self):
        """Force an immediate save (resets timer)"""
        if not self.is_enabled():
            self.logger.warning("Force save requested but auto-save is disabled")
            return
        
        # Check game state (if callback provided)
        can_save = True
        if self.get_game_state:
            try:
                game_state = self.get_game_state()
                if isinstance(game_state, dict):
                    # Use explicit 'can_save' flag if provided
                    if 'can_save' in game_state:
                        can_save = game_state['can_save']
                    else:
                        # Fallback: check individual flags
                        is_paused = game_state.get('is_paused', False)
                        menu_active = game_state.get('menu_active', False)
                        can_save = not is_paused and not menu_active
            except Exception as e:
                # If game state check fails, log warning but allow save attempt
                self.logger.warning(f"Failed to check game state: {e}. Proceeding with force save.")
                can_save = True
        
        if not can_save:
            self.logger.warning("Force save requested but game state doesn't allow saving (paused/menu active)")
            return
        
        self.logger.info("Force saving game...")
        if self._save_with_retry("force save"):
            self.last_save_time = time.time()
            self.last_player_pos = self.get_player_pos()
            self.logger.info("Force save completed")
        else:
            self.logger.error("Force save failed")




