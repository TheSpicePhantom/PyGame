"""
Auto-Save System: Automatically saves game at configurable intervals
"""
import asyncio
import threading
import time
from typing import Optional, Callable
from config.settings_manager import settings_manager


class AutoSaveSystem:
    """Manages automatic game saving at configurable intervals"""
    
    def __init__(self, save_callback: Callable, get_player_pos: Callable):
        """
        Initialize Auto-Save System
        
        Args:
            save_callback: Function to call when saving (should save world and player)
            get_player_pos: Function that returns current player position (x, y)
        """
        self.save_callback = save_callback
        self.get_player_pos = get_player_pos
        self.running = False
        self.save_thread: Optional[threading.Thread] = None
        self.last_save_time = 0.0
        self.last_player_pos = None
        
    def get_interval(self) -> float:
        """Get auto-save interval in seconds from settings"""
        # Default: 30 seconds
        interval = settings_manager.graphics.get('auto_save_interval', 30)
        return float(interval)
    
    def set_interval(self, seconds: float):
        """Set auto-save interval in seconds"""
        settings_manager.graphics['auto_save_interval'] = int(seconds)
        settings_manager.save_settings()
    
    def is_enabled(self) -> bool:
        """Check if auto-save is enabled"""
        return settings_manager.graphics.get('auto_save_enabled', True)
    
    def set_enabled(self, enabled: bool):
        """Enable or disable auto-save"""
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
        
        if not self.is_enabled():
            return
        
        self.running = True
        self.last_save_time = time.time()
        self.last_player_pos = self.get_player_pos()
        
        def run_auto_save():
            """Background thread for auto-save"""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                while self.running:
                    current_time = time.time()
                    interval = self.get_interval()
                    
                    # Check if interval has passed
                    if current_time - self.last_save_time >= interval:
                        # Only save if player has moved (avoid saving when paused)
                        current_pos = self.get_player_pos()
                        if current_pos != self.last_player_pos:
                            print(f"[AutoSave] Auto-saving game (interval: {interval}s)...")
                            try:
                                self.save_callback()
                                self.last_save_time = current_time
                                self.last_player_pos = current_pos
                                print(f"[AutoSave] Auto-save completed")
                            except Exception as e:
                                print(f"[AutoSave] Error during auto-save: {e}")
                    
                    # Sleep for 1 second, then check again
                    time.sleep(1.0)
            finally:
                loop.close()
        
        self.save_thread = threading.Thread(target=run_auto_save, daemon=True, name="AutoSave")
        self.save_thread.start()
        print(f"[AutoSave] Started (interval: {self.get_interval()}s)")
    
    def stop(self):
        """Stop auto-save system"""
        if not self.running:
            return
        
        self.running = False
        if self.save_thread:
            self.save_thread.join(timeout=2.0)
        print("[AutoSave] Stopped")
    
    def force_save(self):
        """Force an immediate save (resets timer)"""
        if not self.is_enabled():
            return
        
        print("[AutoSave] Force saving game...")
        try:
            self.save_callback()
            self.last_save_time = time.time()
            self.last_player_pos = self.get_player_pos()
            print("[AutoSave] Force save completed")
        except Exception as e:
            print(f"[AutoSave] Error during force save: {e}")




