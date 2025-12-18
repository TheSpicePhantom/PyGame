"""
Performance Logger: Saves performance data to JSON files
"""
import json
import time
from pathlib import Path
from datetime import datetime


class PerformanceLogger:
    """Logs performance data to JSON files"""
    
    def __init__(self):
        self.log_dir = Path("perf-logs")
        self.log_dir.mkdir(exist_ok=True)
        
        self.session_data = {
            'session_start': datetime.now().isoformat(),
            'session_end': None,
            'stats': None,
            'chunk_events': [],
            'movement_events': []
        }
    
    def start_log(self):
        """Start a new logging session"""
        self.session_data['session_start'] = datetime.now().isoformat()
        print(f"[PerformanceLogger] Started logging session at {self.session_data['session_start']}")
    
    def log_stats(self, stats):
        """Log performance statistics"""
        self.session_data['stats'] = stats
    
    def log_chunk_event(self, event):
        """Log a chunk load event"""
        self.session_data['chunk_events'].append(event)
    
    def log_movement_event(self, event):
        """Log a movement event"""
        self.session_data['movement_events'].append(event)
    
    def save_log(self):
        """Save log to JSON file"""
        self.session_data['session_end'] = datetime.now().isoformat()
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.log_dir / f"perf_{timestamp}.json"
        
        # Save to JSON
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.session_data, f, indent=2)
        
        print(f"[PerformanceLogger] Saved log to {filename}")
        return filename
