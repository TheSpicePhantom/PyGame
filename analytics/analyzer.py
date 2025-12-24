"""
Performance Log Analyzer: Analysiert Performance-Log-Dateien und gibt verständliche Reports aus
"""
import json
import argparse
from pathlib import Path
from datetime import datetime
from statistics import mean, median
from typing import Dict, List, Optional


class PerformanceAnalyzer:
    """Analysiert Performance-Log-Dateien"""
    
    def __init__(self, log_file: Path):
        """
        Args:
            log_file: Pfad zur JSON-Log-Datei
        """
        self.log_file = log_file
        self.data = None
        self.load_data()
    
    def load_data(self):
        """Lädt die Log-Datei"""
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Log-Datei nicht gefunden: {self.log_file}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Ungültige JSON-Datei: {e}")
    
    def analyze(self) -> Dict:
        """Führt die vollständige Analyse durch"""
        if not self.data:
            raise ValueError("Keine Daten geladen")
        
        analysis = {
            'session_info': self._analyze_session(),
            'frame_performance': self._analyze_frame_performance(),
            'chunk_loading': self._analyze_chunk_loading(),
            'chunk_generation': self._analyze_chunk_generation(),
            'chunk_saving': self._analyze_chunk_saving(),
            'chunk_modification': self._analyze_chunk_modification(),
            'chunk_loaded_from_disk': self._analyze_chunk_loaded_from_disk(),
            'chunk_migrated_legacy': self._analyze_chunk_migrated_legacy(),
            'movement': self._analyze_movement(),
            'insights': []
        }
        
        # Generiere Insights
        analysis['insights'] = self._generate_insights(analysis)
        
        return analysis
    
    def _analyze_session(self) -> Dict:
        """Analysiert Session-Informationen"""
        start = datetime.fromisoformat(self.data['session_start'])
        end = datetime.fromisoformat(self.data['session_end'])
        duration = (end - start).total_seconds()
        
        return {
            'start': start.isoformat(),
            'end': end.isoformat(),
            'duration_seconds': duration,
            'duration_minutes': duration / 60,
            'duration_formatted': f"{int(duration // 60)}m {int(duration % 60)}s"
        }
    
    def _analyze_frame_performance(self) -> Dict:
        """Analysiert Frame-Performance"""
        stats = self.data['stats']
        frame_stats = stats['frame_times']
        fps_stats = stats['fps']
        update_stats = stats['update_times']
        render_stats = stats['render_times']
        
        # Chunk Upload Times (falls verfügbar)
        chunk_upload_stats = stats.get('chunk_upload_times', {})
        chunk_render_stats = stats.get('chunk_render_times', {})
        
        # Disk Load Times (aus chunk_loaded_from_disk_events)
        disk_load_times = []
        if 'chunk_loaded_from_disk_events' in self.data:
            disk_load_times = [e['load_time'] for e in self.data['chunk_loaded_from_disk_events']]
        
        # Berechne geschätzte Frame-Anzahl basierend auf Durchschnitts-FPS
        session_duration = self._analyze_session()['duration_seconds']
        estimated_frames = fps_stats['avg'] * session_duration
        
        result = {
            'frame_times': {
                'min_ms': frame_stats['min'],
                'max_ms': frame_stats['max'],
                'avg_ms': frame_stats['avg'],
                'median_ms': frame_stats['median'],
                'p95_ms': frame_stats['p95'],
                'p99_ms': frame_stats['p99'],
            },
            'fps': {
                'min': fps_stats['min'],
                'max': fps_stats['max'],
                'avg': fps_stats['avg'],
                'median': fps_stats['median'],
            },
            'update_times': {
                'min_ms': update_stats['min'],
                'max_ms': update_stats['max'],
                'avg_ms': update_stats['avg'],
                'median_ms': update_stats['median'],
            },
            'render_times': {
                'min_ms': render_stats['min'],
                'max_ms': render_stats['max'],
                'avg_ms': render_stats['avg'],
                'median_ms': render_stats['median'],
            },
            'estimated_frames': estimated_frames,
        }
        
        # Chunk Upload Times hinzufügen (falls verfügbar)
        if chunk_upload_stats:
            result['chunk_upload_times'] = {
                'min_ms': chunk_upload_stats.get('min', 0),
                'max_ms': chunk_upload_stats.get('max', 0),
                'avg_ms': chunk_upload_stats.get('avg', 0),
                'median_ms': chunk_upload_stats.get('median', 0),
            }
        
        # Chunk Render Times hinzufügen (falls verfügbar)
        if chunk_render_stats:
            result['chunk_render_times'] = {
                'min_ms': chunk_render_stats.get('min', 0),
                'max_ms': chunk_render_stats.get('max', 0),
                'avg_ms': chunk_render_stats.get('avg', 0),
                'median_ms': chunk_render_stats.get('median', 0),
            }
        
        # Disk Load Times hinzufügen (falls verfügbar)
        if disk_load_times:
            result['disk_load_times'] = {
                'min_ms': min(disk_load_times) if disk_load_times else 0,
                'max_ms': max(disk_load_times) if disk_load_times else 0,
                'avg_ms': mean(disk_load_times) if disk_load_times else 0,
                'median_ms': median(disk_load_times) if disk_load_times else 0,
                'total_events': len(disk_load_times),
            }
        
        return result
    
    def _analyze_chunk_loading(self) -> Dict:
        """Analysiert Chunk-Loading-Performance"""
        chunk_events = self.data.get('chunk_load_events', [])
        
        if not chunk_events:
            return {
                'total_events': 0,
                'load_times': None,
                'distribution': None,
                'slowest_chunks': []
            }
        
        load_times = [e['load_time'] for e in chunk_events if 'load_time' in e]
        
        if not load_times:
            return {
                'total_events': len(chunk_events),
                'load_times': None,
                'distribution': None,
                'slowest_chunks': []
            }
        
        # Verteilung
        fast_loads = [t for t in load_times if t < 2.0]
        medium_loads = [t for t in load_times if 2.0 <= t < 5.0]
        slow_loads = [t for t in load_times if t >= 5.0]
        
        # Langsamste Chunks
        sorted_events = sorted(chunk_events, key=lambda x: x.get('load_time', 0), reverse=True)
        slowest = [
            {
                'chunk': (e['chunk_x'], e['chunk_y']),
                'load_time_ms': e.get('load_time', 0),
                'has_generation': 'generation_time' in e,
                'has_save': 'save_time' in e,
            }
            for e in sorted_events[:10]
        ]
        
        return {
            'total_events': len(chunk_events),
            'load_times': {
                'min_ms': min(load_times),
                'max_ms': max(load_times),
                'avg_ms': mean(load_times),
                'median_ms': median(load_times),
            },
            'distribution': {
                'fast_count': len(fast_loads),
                'fast_percent': len(fast_loads) / len(load_times) * 100,
                'medium_count': len(medium_loads),
                'medium_percent': len(medium_loads) / len(load_times) * 100,
                'slow_count': len(slow_loads),
                'slow_percent': len(slow_loads) / len(load_times) * 100,
            },
            'slowest_chunks': slowest,
            'events_per_second': len(chunk_events) / self._analyze_session()['duration_seconds'],
        }
    
    def _analyze_chunk_generation(self) -> Dict:
        """Analysiert Chunk-Generation-Performance"""
        chunk_events = self.data.get('chunk_generation_events', [])
        
        if not chunk_events:
            return {
                'total_events': 0,
                'generation_times': None,
                'slowest_chunks': [],
                'events_per_second': 0
            }
        
        generation_times = [e['generation_time'] for e in chunk_events if 'generation_time' in e]
        
        if not generation_times:
            return {
                'total_events': len(chunk_events),
                'generation_times': None,
                'slowest_chunks': [],
                'events_per_second': 0
            }
        
        # Langsamste Chunks
        sorted_events = sorted(chunk_events, key=lambda x: x.get('generation_time', 0), reverse=True)
        slowest = [
            {
                'chunk': (e['chunk_x'], e['chunk_y']),
                'generation_time_ms': e.get('generation_time', 0),
            }
            for e in sorted_events[:10]
        ]
        
        session_duration = self._analyze_session()['duration_seconds']
        return {
            'total_events': len(chunk_events),
            'generation_times': {
                'min_ms': min(generation_times),
                'max_ms': max(generation_times),
                'avg_ms': mean(generation_times),
                'median_ms': median(generation_times),
            },
            'slowest_chunks': slowest,
            'events_per_second': len(chunk_events) / session_duration if session_duration > 0 else 0,
        }
    
    def _analyze_chunk_saving(self) -> Dict:
        """Analysiert Chunk-Saving-Performance"""
        chunk_events = self.data.get('chunk_save_events', [])
        
        if not chunk_events:
            return {
                'total_events': 0,
                'save_times': None,
                'slowest_chunks': [],
                'events_per_second': 0
            }
        
        save_times = [e['save_time'] for e in chunk_events if 'save_time' in e]
        
        if not save_times:
            return {
                'total_events': len(chunk_events),
                'save_times': None,
                'slowest_chunks': [],
                'events_per_second': 0
            }
        
        # Langsamste Chunks
        sorted_events = sorted(chunk_events, key=lambda x: x.get('save_time', 0), reverse=True)
        slowest = [
            {
                'chunk': (e['chunk_x'], e['chunk_y']),
                'save_time_ms': e.get('save_time', 0),
            }
            for e in sorted_events[:10]
        ]
        
        session_duration = self._analyze_session()['duration_seconds']
        return {
            'total_events': len(chunk_events),
            'save_times': {
                'min_ms': min(save_times),
                'max_ms': max(save_times),
                'avg_ms': mean(save_times),
                'median_ms': median(save_times),
            },
            'slowest_chunks': slowest,
            'events_per_second': len(chunk_events) / session_duration if session_duration > 0 else 0,
        }
    
    def _analyze_chunk_modification(self) -> Dict:
        """Analysiert Chunk-Modifikations-Performance (geänderte Chunks)"""
        chunk_events = self.data.get('chunk_modified_events', [])
        
        if not chunk_events:
            return {
                'total_events': 0,
                'events_per_second': 0,
                'unique_chunks': 0
            }
        
        # Zähle eindeutige Chunks
        unique_chunks = set((e['chunk_x'], e['chunk_y']) for e in chunk_events)
        
        session_duration = self._analyze_session()['duration_seconds']
        return {
            'total_events': len(chunk_events),
            'unique_chunks': len(unique_chunks),
            'events_per_second': len(chunk_events) / session_duration if session_duration > 0 else 0,
        }
    
    def _analyze_chunk_loaded_from_disk(self) -> Dict:
        """Analysiert Chunk-Loading von Disk (IO-Operationen, getrennt von Generation)"""
        chunk_events = self.data.get('chunk_loaded_from_disk_events', [])
        
        if not chunk_events:
            return {
                'total_events': 0,
                'load_times': None,
                'distribution': None,
                'slowest_chunks': [],
                'events_per_second': 0
            }
        
        load_times = [e['load_time'] for e in chunk_events if 'load_time' in e]
        
        if not load_times:
            return {
                'total_events': len(chunk_events),
                'load_times': None,
                'distribution': None,
                'slowest_chunks': [],
                'events_per_second': 0
            }
        
        # Verteilung
        fast_loads = [t for t in load_times if t < 2.0]
        medium_loads = [t for t in load_times if 2.0 <= t < 5.0]
        slow_loads = [t for t in load_times if t >= 5.0]
        
        # Langsamste Chunks
        sorted_events = sorted(chunk_events, key=lambda x: x.get('load_time', 0), reverse=True)
        slowest = [
            {
                'chunk': (e['chunk_x'], e['chunk_y']),
                'load_time_ms': e.get('load_time', 0),
            }
            for e in sorted_events[:10]
        ]
        
        session_duration = self._analyze_session()['duration_seconds']
        return {
            'total_events': len(chunk_events),
            'load_times': {
                'min_ms': min(load_times),
                'max_ms': max(load_times),
                'avg_ms': mean(load_times),
                'median_ms': median(load_times),
            },
            'distribution': {
                'fast_count': len(fast_loads),
                'fast_percent': len(fast_loads) / len(load_times) * 100,
                'medium_count': len(medium_loads),
                'medium_percent': len(medium_loads) / len(load_times) * 100,
                'slow_count': len(slow_loads),
                'slow_percent': len(slow_loads) / len(load_times) * 100,
            },
            'slowest_chunks': slowest,
            'events_per_second': len(chunk_events) / session_duration if session_duration > 0 else 0,
        }
    
    def _analyze_chunk_migrated_legacy(self) -> Dict:
        """Analysiert Legacy-Migration-Performance (Migration von JSON zu Region-Format)"""
        chunk_events = self.data.get('chunk_migrated_legacy_events', [])
        
        if not chunk_events:
            return {
                'total_events': 0,
                'migration_times': None,
                'slowest_chunks': [],
                'events_per_second': 0
            }
        
        migration_times = [e['migration_time'] for e in chunk_events if 'migration_time' in e]
        
        if not migration_times:
            return {
                'total_events': len(chunk_events),
                'migration_times': None,
                'slowest_chunks': [],
                'events_per_second': 0
            }
        
        # Langsamste Migrationen
        sorted_events = sorted(chunk_events, key=lambda x: x.get('migration_time', 0), reverse=True)
        slowest = [
            {
                'chunk': (e['chunk_x'], e['chunk_y']),
                'migration_time_ms': e.get('migration_time', 0),
            }
            for e in sorted_events[:10]
        ]
        
        session_duration = self._analyze_session()['duration_seconds']
        return {
            'total_events': len(chunk_events),
            'migration_times': {
                'min_ms': min(migration_times),
                'max_ms': max(migration_times),
                'avg_ms': mean(migration_times),
                'median_ms': median(migration_times),
            },
            'slowest_chunks': slowest,
            'events_per_second': len(chunk_events) / session_duration if session_duration > 0 else 0,
        }
    
    def _analyze_chunk_loaded_from_disk(self) -> Dict:
        """Analysiert Chunk-Loading von Disk (IO-Operationen, getrennt von Generation)"""
        chunk_events = self.data.get('chunk_loaded_from_disk_events', [])
        
        if not chunk_events:
            return {
                'total_events': 0,
                'load_times': None,
                'distribution': None,
                'slowest_chunks': [],
                'events_per_second': 0
            }
        
        load_times = [e['load_time'] for e in chunk_events if 'load_time' in e]
        
        if not load_times:
            return {
                'total_events': len(chunk_events),
                'load_times': None,
                'distribution': None,
                'slowest_chunks': [],
                'events_per_second': 0
            }
        
        # Verteilung
        fast_loads = [t for t in load_times if t < 2.0]
        medium_loads = [t for t in load_times if 2.0 <= t < 5.0]
        slow_loads = [t for t in load_times if t >= 5.0]
        
        # Langsamste Chunks
        sorted_events = sorted(chunk_events, key=lambda x: x.get('load_time', 0), reverse=True)
        slowest = [
            {
                'chunk': (e['chunk_x'], e['chunk_y']),
                'load_time_ms': e.get('load_time', 0),
            }
            for e in sorted_events[:10]
        ]
        
        session_duration = self._analyze_session()['duration_seconds']
        return {
            'total_events': len(chunk_events),
            'load_times': {
                'min_ms': min(load_times),
                'max_ms': max(load_times),
                'avg_ms': mean(load_times),
                'median_ms': median(load_times),
            },
            'distribution': {
                'fast_count': len(fast_loads),
                'fast_percent': len(fast_loads) / len(load_times) * 100,
                'medium_count': len(medium_loads),
                'medium_percent': len(medium_loads) / len(load_times) * 100,
                'slow_count': len(slow_loads),
                'slow_percent': len(slow_loads) / len(load_times) * 100,
            },
            'slowest_chunks': slowest,
            'events_per_second': len(chunk_events) / session_duration if session_duration > 0 else 0,
        }
    
    def _analyze_chunk_migrated_legacy(self) -> Dict:
        """Analysiert Legacy-Migration-Performance (Migration von JSON zu Region-Format)"""
        chunk_events = self.data.get('chunk_migrated_legacy_events', [])
        
        if not chunk_events:
            return {
                'total_events': 0,
                'migration_times': None,
                'slowest_chunks': [],
                'events_per_second': 0
            }
        
        migration_times = [e['migration_time'] for e in chunk_events if 'migration_time' in e]
        
        if not migration_times:
            return {
                'total_events': len(chunk_events),
                'migration_times': None,
                'slowest_chunks': [],
                'events_per_second': 0
            }
        
        # Langsamste Migrationen
        sorted_events = sorted(chunk_events, key=lambda x: x.get('migration_time', 0), reverse=True)
        slowest = [
            {
                'chunk': (e['chunk_x'], e['chunk_y']),
                'migration_time_ms': e.get('migration_time', 0),
            }
            for e in sorted_events[:10]
        ]
        
        session_duration = self._analyze_session()['duration_seconds']
        return {
            'total_events': len(chunk_events),
            'migration_times': {
                'min_ms': min(migration_times),
                'max_ms': max(migration_times),
                'avg_ms': mean(migration_times),
                'median_ms': median(migration_times),
            },
            'slowest_chunks': slowest,
            'events_per_second': len(chunk_events) / session_duration if session_duration > 0 else 0,
        }
    
    def _analyze_movement(self) -> Dict:
        """Analysiert Movement-Performance"""
        movement_events = self.data.get('movement_events', [])
        
        if not movement_events:
            return {
                'total_events': 0,
                'delays': None,
                'high_delay_count': 0
            }
        
        delays = [e['delay'] for e in movement_events if 'delay' in e]
        
        if not delays:
            return {
                'total_events': len(movement_events),
                'delays': None,
                'high_delay_count': 0
            }
        
        # Erwartete Delay bei 60 FPS = 1/60 ≈ 0.0167s
        expected_delay = 1/60
        high_delay_count = len([d for d in delays if d > expected_delay * 2])
        
        return {
            'total_events': len(movement_events),
            'delays': {
                'min_s': min(delays),
                'max_s': max(delays),
                'avg_s': mean(delays),
                'median_s': median(delays),
            },
            'high_delay_count': high_delay_count,
            'high_delay_percent': high_delay_count / len(delays) * 100 if delays else 0,
            'events_per_second': len(movement_events) / self._analyze_session()['duration_seconds'],
        }
    
    def _generate_insights(self, analysis: Dict) -> List[str]:
        """Generiert Performance-Insights"""
        insights = []
        
        frame_perf = analysis['frame_performance']
        chunk_loading = analysis['chunk_loading']
        movement = analysis['movement']
        
        # Frame-Performance Insights
        target_frame_time = 1000 / 60  # 16.67ms für 60 FPS
        avg_frame_time = frame_perf['frame_times']['avg_ms']
        
        if avg_frame_time <= target_frame_time:
            insights.append("[OK] Durchschnittliche Frame-Zeit ({:.2f}ms) ist innerhalb des Ziels ({:.2f}ms)".format(avg_frame_time, target_frame_time))
        else:
            insights.append("[WARN] Durchschnittliche Frame-Zeit ({:.2f}ms) ueberschreitet Ziel ({:.2f}ms)".format(avg_frame_time, target_frame_time))
        
        p99_frame_time = frame_perf['frame_times']['p99_ms']
        if p99_frame_time > target_frame_time * 3:
            insights.append("[WARN] P99 Frame-Zeit ({:.2f}ms) zeigt signifikante Spikes".format(p99_frame_time))
        elif p99_frame_time > target_frame_time:
            insights.append("[INFO] P99 Frame-Zeit ({:.2f}ms) leicht ueber Ziel".format(p99_frame_time))
        else:
            insights.append("[OK] P99 Frame-Zeit ({:.2f}ms) ist akzeptabel".format(p99_frame_time))
        
        # Update vs Render Balance
        avg_update = frame_perf['update_times']['avg_ms']
        avg_render = frame_perf['render_times']['avg_ms']
        
        if avg_update > avg_render * 2:
            insights.append("[WARN] Update-Zeit ({:.2f}ms) ist deutlich hoeher als Render-Zeit ({:.2f}ms)".format(avg_update, avg_render))
        elif avg_render > avg_update * 2:
            insights.append("[WARN] Render-Zeit ({:.2f}ms) ist deutlich hoeher als Update-Zeit ({:.2f}ms)".format(avg_render, avg_update))
        else:
            insights.append("[OK] Update ({:.2f}ms) und Render ({:.2f}ms) Zeiten sind ausgewogen".format(avg_update, avg_render))
        
        # Chunk Loading Insights
        if chunk_loading['total_events'] > 0 and chunk_loading['load_times']:
            avg_load_time = chunk_loading['load_times']['avg_ms']
            if avg_load_time > 5.0:
                insights.append("[WARN] Durchschnittliche Chunk-Load-Zeit ({:.2f}ms) ist hoch".format(avg_load_time))
            elif avg_load_time > 2.0:
                insights.append("[INFO] Durchschnittliche Chunk-Load-Zeit ({:.2f}ms) ist moderat".format(avg_load_time))
            else:
                insights.append("[OK] Durchschnittliche Chunk-Load-Zeit ({:.2f}ms) ist gut".format(avg_load_time))
            
            # Chunk Loading Rate
            events_per_sec = chunk_loading['events_per_second']
            if events_per_sec > 10:
                insights.append("[INFO] Hohe Chunk-Load-Rate ({:.1f} Chunks/Sekunde) - moeglicherweise schnelle Bewegung".format(events_per_sec))
            elif events_per_sec < 1:
                insights.append("[INFO] Niedrige Chunk-Load-Rate ({:.1f} Chunks/Sekunde)".format(events_per_sec))
        
        # IO vs Generation Analysis
        chunk_loaded_from_disk = analysis['chunk_loaded_from_disk']
        chunk_generation = analysis['chunk_generation']
        
        total_io_ops = chunk_loaded_from_disk['total_events']
        total_gen_ops = chunk_generation['total_events']
        total_chunk_ops = total_io_ops + total_gen_ops
        
        if total_chunk_ops > 0:
            io_percent = (total_io_ops / total_chunk_ops) * 100
            gen_percent = (total_gen_ops / total_chunk_ops) * 100
            
            if io_percent > 50:
                insights.append("[INFO] Mehr IO-Operationen ({:.1f}%) als Generation ({:.1f}%) - Chunks werden hauptsaechlich von Disk geladen".format(io_percent, gen_percent))
            elif gen_percent > 50:
                insights.append("[INFO] Mehr Generation ({:.1f}%) als IO ({:.1f}%) - viele neue Chunks werden generiert".format(gen_percent, io_percent))
            else:
                insights.append("[INFO] Ausgewogene Verteilung: IO ({:.1f}%) vs Generation ({:.1f}%)".format(io_percent, gen_percent))
            
            # Disk Load Performance
            if chunk_loaded_from_disk['total_events'] > 0 and chunk_loaded_from_disk['load_times']:
                avg_disk_load = chunk_loaded_from_disk['load_times']['avg_ms']
                if avg_disk_load > 5.0:
                    insights.append("[WARN] Durchschnittliche Disk-Load-Zeit ({:.2f}ms) ist hoch - moeglicher IO-Bottleneck".format(avg_disk_load))
                elif avg_disk_load > 2.0:
                    insights.append("[INFO] Durchschnittliche Disk-Load-Zeit ({:.2f}ms) ist moderat".format(avg_disk_load))
            
            # Generation Performance
            if chunk_generation['total_events'] > 0 and chunk_generation['generation_times']:
                avg_gen_time = chunk_generation['generation_times']['avg_ms']
                if avg_gen_time > 1.0:
                    insights.append("[WARN] Durchschnittliche Generierungs-Zeit ({:.2f}ms) ist hoch - moeglicher CPU-Bottleneck".format(avg_gen_time))
                elif avg_gen_time > 0.7:
                    insights.append("[INFO] Durchschnittliche Generierungs-Zeit ({:.2f}ms) ist moderat".format(avg_gen_time))
        
        # Legacy Migration Insights
        chunk_migrated_legacy = analysis['chunk_migrated_legacy']
        if chunk_migrated_legacy['total_events'] > 0:
            insights.append("[INFO] {:.0f} Chunks wurden von Legacy-Format migriert ({:.2f} Chunks/Sekunde)".format(
                chunk_migrated_legacy['total_events'],
                chunk_migrated_legacy['events_per_second']
            ))
            if chunk_migrated_legacy['migration_times']:
                avg_migration = chunk_migrated_legacy['migration_times']['avg_ms']
                if avg_migration > 10.0:
                    insights.append("[WARN] Durchschnittliche Migrations-Zeit ({:.2f}ms) ist hoch".format(avg_migration))
        
        # Movement Insights
        if movement['total_events'] > 0 and movement['delays']:
            avg_delay = movement['delays']['avg_s']
            expected_delay = 1/60
            if avg_delay > expected_delay * 1.5:
                insights.append("[WARN] Durchschnittliche Movement-Delay ({:.2f}ms) ist hoeher als erwartet ({:.2f}ms)".format(avg_delay*1000, expected_delay*1000))
            else:
                insights.append("[OK] Movement-Verarbeitung ist konsistent ({:.2f}ms Durchschnitt)".format(avg_delay*1000))
        
        # Upload vs Disk Load Insights
        if 'chunk_upload_times' in frame_perf and 'disk_load_times' in frame_perf:
            avg_upload_time = frame_perf['chunk_upload_times']['avg_ms']
            avg_disk_load_time = frame_perf['disk_load_times']['avg_ms']
            upload_budget = 2.5  # CHUNK_UPLOAD_BUDGET_MS (tightened from 3.5ms)
            
            if avg_upload_time > upload_budget:
                insights.append("[WARN] Durchschnittliche Upload-Zeit ({:.2f}ms) überschreitet Budget ({:.2f}ms)".format(avg_upload_time, upload_budget))
            else:
                insights.append("[OK] Upload-Zeit ({:.2f}ms) ist innerhalb des Budgets ({:.2f}ms)".format(avg_upload_time, upload_budget))
            
            # Vergleich: Wenn Frame-Zeiten hoch sind, aber Upload-Zeiten niedrig, liegt das Problem bei IO
            avg_frame_time = frame_perf['frame_times']['avg_ms']
            if avg_frame_time > 16.67 and avg_upload_time <= upload_budget:
                insights.append("[INFO] Hohe Frame-Zeiten ({:.2f}ms) bei niedrigen Upload-Zeiten ({:.2f}ms) deuten auf IO-Bottleneck hin".format(avg_frame_time, avg_upload_time))
            elif avg_frame_time > 16.67 and avg_upload_time > upload_budget:
                insights.append("[WARN] Hohe Frame-Zeiten ({:.2f}ms) UND hohe Upload-Zeiten ({:.2f}ms) - möglicherweise GPU-Bottleneck".format(avg_frame_time, avg_upload_time))
        
        return insights
    
    def print_report(self):
        """Gibt einen formatierten Report aus"""
        analysis = self.analyze()
        
        print("=" * 80)
        print("PERFORMANCE ANALYSE REPORT")
        print("=" * 80)
        print(f"\nDatei: {self.log_file.name}")
        
        # Session Info
        session = analysis['session_info']
        print(f"\n{'=' * 80}")
        print("SESSION INFORMATIONEN")
        print(f"{'=' * 80}")
        print(f"Start:     {session['start']}")
        print(f"Ende:      {session['end']}")
        print(f"Dauer:     {session['duration_formatted']} ({session['duration_seconds']:.2f}s)")
        
        # Frame Performance
        frame_perf = analysis['frame_performance']
        print(f"\n{'=' * 80}")
        print("FRAME PERFORMANCE")
        print(f"{'=' * 80}")
        print(f"\nFrame-Zeiten (ms):")
        print(f"  Minimum:  {frame_perf['frame_times']['min_ms']:>8.2f}")
        print(f"  Maximum:  {frame_perf['frame_times']['max_ms']:>8.2f}")
        print(f"  Durchschnitt: {frame_perf['frame_times']['avg_ms']:>8.2f}")
        print(f"  Median:   {frame_perf['frame_times']['median_ms']:>8.2f}")
        print(f"  P95:      {frame_perf['frame_times']['p95_ms']:>8.2f}")
        print(f"  P99:      {frame_perf['frame_times']['p99_ms']:>8.2f}")
        
        print(f"\nFPS:")
        print(f"  Minimum:  {frame_perf['fps']['min']:>8.1f}")
        print(f"  Maximum:  {frame_perf['fps']['max']:>8.1f}")
        print(f"  Durchschnitt: {frame_perf['fps']['avg']:>8.1f}")
        print(f"  Median:   {frame_perf['fps']['median']:>8.1f}")
        
        print(f"\nUpdate-Zeiten (ms):")
        print(f"  Minimum:  {frame_perf['update_times']['min_ms']:>8.2f}")
        print(f"  Maximum:  {frame_perf['update_times']['max_ms']:>8.2f}")
        print(f"  Durchschnitt: {frame_perf['update_times']['avg_ms']:>8.2f}")
        print(f"  Median:   {frame_perf['update_times']['median_ms']:>8.2f}")
        
        print(f"\nRender-Zeiten (ms):")
        print(f"  Minimum:  {frame_perf['render_times']['min_ms']:>8.2f}")
        print(f"  Maximum:  {frame_perf['render_times']['max_ms']:>8.2f}")
        print(f"  Durchschnitt: {frame_perf['render_times']['avg_ms']:>8.2f}")
        print(f"  Median:   {frame_perf['render_times']['median_ms']:>8.2f}")
        
        # Chunk Upload Times vs Disk Load Times Vergleich
        print(f"\n{'=' * 80}")
        print("CHUNK UPLOAD vs DISK LOAD ZEITEN")
        print(f"{'=' * 80}")
        
        if 'chunk_upload_times' in frame_perf:
            upload_stats = frame_perf['chunk_upload_times']
            print(f"\nUpload-Zeiten (GPU-Upload pro Frame, ms):")
            print(f"  Minimum:  {upload_stats['min_ms']:>8.2f}")
            print(f"  Maximum:  {upload_stats['max_ms']:>8.2f}")
            print(f"  Durchschnitt: {upload_stats['avg_ms']:>8.2f}")
            print(f"  Median:   {upload_stats['median_ms']:>8.2f}")
        else:
            print("\nUpload-Zeiten: Nicht verfügbar")
        
        if 'disk_load_times' in frame_perf:
            disk_stats = frame_perf['disk_load_times']
            print(f"\nDisk-Load-Zeiten (IO pro Chunk, ms):")
            print(f"  Minimum:  {disk_stats['min_ms']:>8.2f}")
            print(f"  Maximum:  {disk_stats['max_ms']:>8.2f}")
            print(f"  Durchschnitt: {disk_stats['avg_ms']:>8.2f}")
            print(f"  Median:   {disk_stats['median_ms']:>8.2f}")
            print(f"  Total Events: {disk_stats['total_events']}")
        else:
            print("\nDisk-Load-Zeiten: Nicht verfügbar")
        
        # Vergleich: Frame-Zeit vs Upload-Zeit vs Disk-Load-Zeit
        if 'chunk_upload_times' in frame_perf and 'disk_load_times' in frame_perf:
            avg_frame_time = frame_perf['frame_times']['avg_ms']
            avg_upload_time = frame_perf['chunk_upload_times']['avg_ms']
            avg_disk_load_time = frame_perf['disk_load_times']['avg_ms']
            
            print(f"\n{'=' * 80}")
            print("ZEIT-VERGLEICH (Durchschnittswerte)")
            print(f"{'=' * 80}")
            print(f"Frame-Zeit:        {avg_frame_time:>8.2f} ms")
            print(f"Upload-Zeit:       {avg_upload_time:>8.2f} ms ({avg_upload_time/avg_frame_time*100:.1f}% des Frames)")
            print(f"Disk-Load-Zeit:    {avg_disk_load_time:>8.2f} ms (pro Chunk)")
            upload_budget = 2.5  # CHUNK_UPLOAD_BUDGET_MS (tightened from 3.5ms)
            print(f"\nUpload-Budget ({upload_budget}ms): {'OK' if avg_upload_time <= upload_budget else 'ÜBERSCHRITTEN'}")
            print(f"  Upload-Zeit ist {'innerhalb' if avg_upload_time <= upload_budget else 'außerhalb'} des Budgets")
        
        # Chunk Loading
        chunk_loading = analysis['chunk_loading']
        print(f"\n{'=' * 80}")
        print("CHUNK LOADING")
        print(f"{'=' * 80}")
        print(f"Gesamt Events: {chunk_loading['total_events']}")
        
        if chunk_loading['load_times']:
            load_times = chunk_loading['load_times']
            print(f"\nLoad-Zeiten (ms):")
            print(f"  Minimum:  {load_times['min_ms']:>8.2f}")
            print(f"  Maximum:  {load_times['max_ms']:>8.2f}")
            print(f"  Durchschnitt: {load_times['avg_ms']:>8.2f}")
            print(f"  Median:   {load_times['median_ms']:>8.2f}")
            
            if chunk_loading['distribution']:
                dist = chunk_loading['distribution']
                print(f"\nVerteilung:")
                print(f"  Schnell (<2ms):   {dist['fast_count']:>4} ({dist['fast_percent']:>5.1f}%)")
                print(f"  Mittel (2-5ms):   {dist['medium_count']:>4} ({dist['medium_percent']:>5.1f}%)")
                print(f"  Langsam (>=5ms):  {dist['slow_count']:>4} ({dist['slow_percent']:>5.1f}%)")
            
            print(f"\nChunk-Load-Rate: {chunk_loading['events_per_second']:.2f} Chunks/Sekunde")
            
            if chunk_loading['slowest_chunks']:
                print(f"\nLangsamste 10 Chunk-Loads:")
                for i, chunk_info in enumerate(chunk_loading['slowest_chunks'][:10], 1):
                    print(f"  {i:>2}. Chunk ({chunk_info['chunk'][0]:>4}, {chunk_info['chunk'][1]:>4}): {chunk_info['load_time_ms']:>6.2f}ms")
        
        # Chunk Generation
        chunk_generation = analysis['chunk_generation']
        print(f"\n{'=' * 80}")
        print("CHUNK GENERATION")
        print(f"{'=' * 80}")
        print(f"Gesamt Events: {chunk_generation['total_events']}")
        
        if chunk_generation['generation_times']:
            gen_times = chunk_generation['generation_times']
            print(f"\nGenerierungs-Zeiten (ms):")
            print(f"  Minimum:  {gen_times['min_ms']:>8.2f}")
            print(f"  Maximum:  {gen_times['max_ms']:>8.2f}")
            print(f"  Durchschnitt: {gen_times['avg_ms']:>8.2f}")
            print(f"  Median:   {gen_times['median_ms']:>8.2f}")
            
            print(f"\nGenerierungs-Rate: {chunk_generation['events_per_second']:.2f} Chunks/Sekunde")
            
            if chunk_generation['slowest_chunks']:
                print(f"\nLangsamste 10 Chunk-Generierungen:")
                for i, chunk_info in enumerate(chunk_generation['slowest_chunks'][:10], 1):
                    print(f"  {i:>2}. Chunk ({chunk_info['chunk'][0]:>4}, {chunk_info['chunk'][1]:>4}): {chunk_info['generation_time_ms']:>6.2f}ms")
        
        # Chunk Saving
        chunk_saving = analysis['chunk_saving']
        print(f"\n{'=' * 80}")
        print("CHUNK SAVING")
        print(f"{'=' * 80}")
        print(f"Gesamt Events: {chunk_saving['total_events']}")
        
        if chunk_saving['save_times']:
            save_times = chunk_saving['save_times']
            print(f"\nSave-Zeiten (ms):")
            print(f"  Minimum:  {save_times['min_ms']:>8.2f}")
            print(f"  Maximum:  {save_times['max_ms']:>8.2f}")
            print(f"  Durchschnitt: {save_times['avg_ms']:>8.2f}")
            print(f"  Median:   {save_times['median_ms']:>8.2f}")
            
            print(f"\nSave-Rate: {chunk_saving['events_per_second']:.2f} Chunks/Sekunde")
            
            if chunk_saving['slowest_chunks']:
                print(f"\nLangsamste 10 Chunk-Saves:")
                for i, chunk_info in enumerate(chunk_saving['slowest_chunks'][:10], 1):
                    print(f"  {i:>2}. Chunk ({chunk_info['chunk'][0]:>4}, {chunk_info['chunk'][1]:>4}): {chunk_info['save_time_ms']:>6.2f}ms")
        
        # Chunk Modification
        chunk_modification = analysis['chunk_modification']
        print(f"\n{'=' * 80}")
        print("CHUNK MODIFICATION")
        print(f"{'=' * 80}")
        print(f"Gesamt Events: {chunk_modification['total_events']}")
        print(f"Eindeutige Chunks: {chunk_modification['unique_chunks']}")
        print(f"Modifikations-Rate: {chunk_modification['events_per_second']:.2f} Events/Sekunde")
        
        # Chunk Loaded from Disk (IO Operations)
        chunk_loaded_from_disk = analysis['chunk_loaded_from_disk']
        print(f"\n{'=' * 80}")
        print("CHUNK LOADED FROM DISK (IO)")
        print(f"{'=' * 80}")
        print(f"Gesamt Events: {chunk_loaded_from_disk['total_events']}")
        
        if chunk_loaded_from_disk['load_times']:
            load_times = chunk_loaded_from_disk['load_times']
            print(f"\nDisk-Load-Zeiten (ms):")
            print(f"  Minimum:  {load_times['min_ms']:>8.2f}")
            print(f"  Maximum:  {load_times['max_ms']:>8.2f}")
            print(f"  Durchschnitt: {load_times['avg_ms']:>8.2f}")
            print(f"  Median:   {load_times['median_ms']:>8.2f}")
            
            if chunk_loaded_from_disk['distribution']:
                dist = chunk_loaded_from_disk['distribution']
                print(f"\nVerteilung:")
                print(f"  Schnell (<2ms):   {dist['fast_count']:>4} ({dist['fast_percent']:>5.1f}%)")
                print(f"  Mittel (2-5ms):   {dist['medium_count']:>4} ({dist['medium_percent']:>5.1f}%)")
                print(f"  Langsam (>=5ms):  {dist['slow_count']:>4} ({dist['slow_percent']:>5.1f}%)")
            
            print(f"\nDisk-Load-Rate: {chunk_loaded_from_disk['events_per_second']:.2f} Chunks/Sekunde")
            
            if chunk_loaded_from_disk['slowest_chunks']:
                print(f"\nLangsamste 10 Disk-Loads:")
                for i, chunk_info in enumerate(chunk_loaded_from_disk['slowest_chunks'][:10], 1):
                    print(f"  {i:>2}. Chunk ({chunk_info['chunk'][0]:>4}, {chunk_info['chunk'][1]:>4}): {chunk_info['load_time_ms']:>6.2f}ms")
        
        # Chunk Migrated Legacy
        chunk_migrated_legacy = analysis['chunk_migrated_legacy']
        print(f"\n{'=' * 80}")
        print("CHUNK MIGRATED FROM LEGACY (JSON -> Region)")
        print(f"{'=' * 80}")
        print(f"Gesamt Events: {chunk_migrated_legacy['total_events']}")
        
        if chunk_migrated_legacy['migration_times']:
            migration_times = chunk_migrated_legacy['migration_times']
            print(f"\nMigration-Zeiten (ms):")
            print(f"  Minimum:  {migration_times['min_ms']:>8.2f}")
            print(f"  Maximum:  {migration_times['max_ms']:>8.2f}")
            print(f"  Durchschnitt: {migration_times['avg_ms']:>8.2f}")
            print(f"  Median:   {migration_times['median_ms']:>8.2f}")
            
            print(f"\nMigration-Rate: {chunk_migrated_legacy['events_per_second']:.2f} Chunks/Sekunde")
            
            if chunk_migrated_legacy['slowest_chunks']:
                print(f"\nLangsamste 10 Migrationen:")
                for i, chunk_info in enumerate(chunk_migrated_legacy['slowest_chunks'][:10], 1):
                    print(f"  {i:>2}. Chunk ({chunk_info['chunk'][0]:>4}, {chunk_info['chunk'][1]:>4}): {chunk_info['migration_time_ms']:>6.2f}ms")
        
        # Chunk Render Times (from stats)
        stats = self.data.get('stats', {})
        if 'chunk_render_times' in stats and stats['chunk_render_times'].get('avg', 0) > 0:
            render_stats = stats['chunk_render_times']
            print(f"\n{'=' * 80}")
            print("CHUNK RENDERING")
            print(f"{'=' * 80}")
            print(f"\nRender-Zeiten pro Frame (ms):")
            print(f"  Minimum:  {render_stats['min']:>8.2f}")
            print(f"  Maximum:  {render_stats['max']:>8.2f}")
            print(f"  Durchschnitt: {render_stats['avg']:>8.2f}")
            print(f"  Median:   {render_stats['median']:>8.2f}")
        
        # Movement
        movement = analysis['movement']
        print(f"\n{'=' * 80}")
        print("MOVEMENT")
        print(f"{'=' * 80}")
        print(f"Gesamt Events: {movement['total_events']}")
        
        if movement['delays']:
            delays = movement['delays']
            print(f"\nMovement-Delays (ms):")
            print(f"  Minimum:  {delays['min_s']*1000:>8.2f}")
            print(f"  Maximum:  {delays['max_s']*1000:>8.2f}")
            print(f"  Durchschnitt: {delays['avg_s']*1000:>8.2f}")
            print(f"  Median:   {delays['median_s']*1000:>8.2f}")
            
            print(f"\nHohe Delay Events (>33ms): {movement['high_delay_count']} ({movement['high_delay_percent']:.1f}%)")
            print(f"Movement-Rate: {movement['events_per_second']:.1f} Events/Sekunde")
        
        # Insights
        print(f"\n{'=' * 80}")
        print("PERFORMANCE INSIGHTS")
        print(f"{'=' * 80}")
        for insight in analysis['insights']:
            print(f"  {insight}")
        
        print(f"\n{'=' * 80}\n")


def main():
    """Hauptfunktion für Kommandozeilen-Nutzung"""
    parser = argparse.ArgumentParser(
        description='Analysiert Performance-Log-Dateien',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  # Analysiere eine spezifische Datei
  python -m analytics.analyzer perf-logs/perf_20251218_213939.json
  
  # Analysiere die neueste Log-Datei
  python -m analytics.analyzer --latest
  
  # Analysiere alle Log-Dateien
  python -m analytics.analyzer --all
        """
    )
    
    parser.add_argument(
        'log_file',
        nargs='?',
        type=str,
        help='Pfad zur Performance-Log-Datei (JSON)'
    )
    
    parser.add_argument(
        '--latest',
        action='store_true',
        help='Analysiere die neueste Log-Datei'
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='Analysiere alle Log-Dateien im perf-logs Verzeichnis'
    )
    
    args = parser.parse_args()
    
    log_dir = Path("perf-logs")
    
    if args.all:
        # Analysiere alle Log-Dateien
        log_files = sorted(log_dir.glob("perf_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not log_files:
            print("Keine Log-Dateien gefunden im perf-logs Verzeichnis")
            return
        
        print(f"Analysiere {len(log_files)} Log-Dateien...\n")
        for log_file in log_files:
            try:
                analyzer = PerformanceAnalyzer(log_file)
                analyzer.print_report()
            except Exception as e:
                print(f"Fehler beim Analysieren von {log_file.name}: {e}\n")
    
    elif args.latest:
        # Finde die neueste Log-Datei
        log_files = sorted(log_dir.glob("perf_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not log_files:
            print("Keine Log-Dateien gefunden im perf-logs Verzeichnis")
            return
        
        log_file = log_files[0]
        print(f"Analysiere neueste Log-Datei: {log_file.name}\n")
        analyzer = PerformanceAnalyzer(log_file)
        analyzer.print_report()
    
    elif args.log_file:
        # Analysiere spezifische Datei
        log_file = Path(args.log_file)
        if not log_file.exists():
            print(f"Datei nicht gefunden: {log_file}")
            return
        
        analyzer = PerformanceAnalyzer(log_file)
        analyzer.print_report()
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
