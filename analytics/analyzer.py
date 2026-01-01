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
            'region_file_performance': self._analyze_region_file_performance(),
            'movement': self._analyze_movement(),
            'ui_performance': self._analyze_ui_performance(),
            'sprite_cache_stats': self._analyze_sprite_cache_stats(),
            'gpu_performance': self._analyze_gpu_performance(),
            'generic_metrics': self._analyze_generic_metrics(),  # Phase 5: Multi-Threading Mesh-Generation
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
        
        # Disk Load/Save Times (aus stats, falls verfügbar)
        disk_load_stats = stats.get('disk_load_times', {})
        disk_save_stats = stats.get('disk_save_times', {})
        
        # Fallback: Disk Load Times aus chunk_loaded_from_disk_events (für alte Logs)
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
        
        # Disk Load Times hinzufügen (aus stats, falls verfügbar)
        if disk_load_stats:
            result['disk_load_times'] = {
                'min_ms': disk_load_stats.get('min', 0),
                'max_ms': disk_load_stats.get('max', 0),
                'avg_ms': disk_load_stats.get('avg', 0),
                'median_ms': disk_load_stats.get('median', 0),
                'total_events': disk_load_stats.get('count', 0),
            }
        elif disk_load_times:  # Fallback für alte Logs
            result['disk_load_times'] = {
                'min_ms': min(disk_load_times) if disk_load_times else 0,
                'max_ms': max(disk_load_times) if disk_load_times else 0,
                'avg_ms': mean(disk_load_times) if disk_load_times else 0,
                'median_ms': median(disk_load_times) if disk_load_times else 0,
                'total_events': len(disk_load_times),
            }
        
        # Disk Save Times hinzufügen (aus stats, falls verfügbar)
        if disk_save_stats:
            result['disk_save_times'] = {
                'min_ms': disk_save_stats.get('min', 0),
                'max_ms': disk_save_stats.get('max', 0),
                'avg_ms': disk_save_stats.get('avg', 0),
                'median_ms': disk_save_stats.get('median', 0),
                'total_events': disk_save_stats.get('count', 0),
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
    
    def _analyze_region_file_performance(self) -> Dict:
        """Analysiert Region-Datei-Performance (nur schnellste/langsamste 5)"""
        stats = self.data.get('stats', {})
        region_stats = stats.get('region_file_stats', {})
        
        if not region_stats:
            return {
                'total_regions_tracked': 0,
                'fastest_5': [],
                'slowest_5': [],
            }
        
        fastest_5 = region_stats.get('fastest_5', [])
        slowest_5 = region_stats.get('slowest_5', [])
        total_tracked = region_stats.get('total_regions_tracked', 0)
        
        return {
            'total_regions_tracked': total_tracked,
            'fastest_5': fastest_5,
            'slowest_5': slowest_5,
        }
    
    def _analyze_sprite_cache_stats(self) -> Dict:
        """Analysiert Sprite-Cache-Statistiken"""
        if not self.data or 'sprite_cache_stats' not in self.data:
            return {}
        
        events = self.data.get('sprite_cache_stats', [])
        if not events:
            return {}
        
        # Calculate statistics
        hit_rates = [e.get('hit_rate', 0) for e in events if 'hit_rate' in e]
        cumulative_hit_rates = [e.get('cumulative_hit_rate', 0) for e in events if 'cumulative_hit_rate' in e]
        hits_list = [e.get('hits', 0) for e in events]
        misses_list = [e.get('misses', 0) for e in events]
        totals_list = [e.get('total', 0) for e in events]
        
        # Get final cumulative stats
        final_event = events[-1] if events else {}
        cumulative_hits = final_event.get('cumulative_hits', 0)
        cumulative_misses = final_event.get('cumulative_misses', 0)
        cumulative_total = final_event.get('cumulative_total', 0)
        final_cumulative_hit_rate = final_event.get('cumulative_hit_rate', 0)
        
        return {
            'total_events': len(events),
            'hit_rates': {
                'min': min(hit_rates) if hit_rates else 0,
                'max': max(hit_rates) if hit_rates else 0,
                'avg': mean(hit_rates) if hit_rates else 0,
                'median': median(hit_rates) if hit_rates else 0
            },
            'cumulative_hit_rates': {
                'min': min(cumulative_hit_rates) if cumulative_hit_rates else 0,
                'max': max(cumulative_hit_rates) if cumulative_hit_rates else 0,
                'avg': mean(cumulative_hit_rates) if cumulative_hit_rates else 0,
                'median': median(cumulative_hit_rates) if cumulative_hit_rates else 0
            },
            'per_period': {
                'hits': {
                    'min': min(hits_list) if hits_list else 0,
                    'max': max(hits_list) if hits_list else 0,
                    'avg': mean(hits_list) if hits_list else 0,
                    'median': median(hits_list) if hits_list else 0
                },
                'misses': {
                    'min': min(misses_list) if misses_list else 0,
                    'max': max(misses_list) if misses_list else 0,
                    'avg': mean(misses_list) if misses_list else 0,
                    'median': median(misses_list) if misses_list else 0
                },
                'total': {
                    'min': min(totals_list) if totals_list else 0,
                    'max': max(totals_list) if totals_list else 0,
                    'avg': mean(totals_list) if totals_list else 0,
                    'median': median(totals_list) if totals_list else 0
                }
            },
            'cumulative': {
                'hits': cumulative_hits,
                'misses': cumulative_misses,
                'total': cumulative_total,
                'hit_rate': final_cumulative_hit_rate
            }
        }
    
    def _analyze_gpu_performance(self) -> Dict:
        """Analysiert GPU-Performance-Metriken (von ModernGL Query Objects)"""
        stats = self.data.get('stats', {})
        gpu_stats = stats.get('gpu_performance', {})
        
        if not gpu_stats:
            return {}
        
        return {
            'chunk_render_times': gpu_stats.get('chunk_render_times', {}),
            'decoration_render_times': gpu_stats.get('decoration_render_times', {}),
            'shadow_render_times': gpu_stats.get('shadow_render_times', {}),
            'total_render_times': gpu_stats.get('total_render_times', {}),
        }
    
    def _analyze_ui_performance(self) -> Dict:
        """Analysiert UI-Performance"""
        stats = self.data.get('stats', {})
        ui_stats = stats.get('ui_performance', {})
        
        if not ui_stats:
            return {
                'world_render_times': None,
                'debug_render_times': None,
                'ui_render_times': None,
                'stats_overlay_times': None,
            }
        
        return {
            'world_render_times': ui_stats.get('world_render_times', {}),
            'debug_render_times': ui_stats.get('debug_render_times', {}),
            'ui_render_times': ui_stats.get('ui_render_times', {}),
            'stats_overlay_times': ui_stats.get('stats_overlay_times', {}),
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
    
    def _analyze_generic_metrics(self) -> Dict:
        """Analysiert generische Performance-Metriken (Phase 5: Multi-Threading Mesh-Generation)"""
        stats = self.data.get('stats', {})
        generic_metrics = stats.get('generic_metrics', {})
        
        if not generic_metrics:
            return {}
        
        result = {}
        for metric_name, metric_data in generic_metrics.items():
            result[metric_name] = {
                'min': metric_data.get('min', 0),
                'max': metric_data.get('max', 0),
                'avg': metric_data.get('avg', 0),
                'median': metric_data.get('median', 0),
                'count': metric_data.get('count', 0),
            }
        
        return result
    
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
        
        # Upload vs Disk Load/Save Insights
        if 'chunk_upload_times' in frame_perf and 'disk_load_times' in frame_perf:
            avg_upload_time = frame_perf['chunk_upload_times']['avg_ms']
            avg_disk_load_time = frame_perf['disk_load_times']['avg_ms']
            upload_budget = 2.5  # CHUNK_UPLOAD_BUDGET_MS (tightened from 3.5ms)
            
            if avg_upload_time > upload_budget:
                insights.append("[WARN] Durchschnittliche Upload-Zeit ({:.2f}ms) überschreitet Budget ({:.2f}ms)".format(avg_upload_time, upload_budget))
            else:
                insights.append("[OK] Upload-Zeit ({:.2f}ms) ist innerhalb des Budgets ({:.2f}ms)".format(avg_upload_time, upload_budget))
            
            # Disk Save Performance
            if 'disk_save_times' in frame_perf:
                avg_disk_save_time = frame_perf['disk_save_times']['avg_ms']
                if avg_disk_save_time > 20.0:
                    insights.append("[WARN] Durchschnittliche Disk-Save-Zeit ({:.2f}ms) ist sehr hoch - möglicher IO-Bottleneck".format(avg_disk_save_time))
                elif avg_disk_save_time > 10.0:
                    insights.append("[INFO] Durchschnittliche Disk-Save-Zeit ({:.2f}ms) ist moderat hoch".format(avg_disk_save_time))
            
            # Vergleich: Wenn Frame-Zeiten hoch sind, aber Upload-Zeiten niedrig, liegt das Problem bei IO
            avg_frame_time = frame_perf['frame_times']['avg_ms']
            if avg_frame_time > 16.67 and avg_upload_time <= upload_budget:
                insights.append("[INFO] Hohe Frame-Zeiten ({:.2f}ms) bei niedrigen Upload-Zeiten ({:.2f}ms) deuten auf IO-Bottleneck hin".format(avg_frame_time, avg_upload_time))
            elif avg_frame_time > 16.67 and avg_upload_time > upload_budget:
                insights.append("[WARN] Hohe Frame-Zeiten ({:.2f}ms) UND hohe Upload-Zeiten ({:.2f}ms) - möglicherweise GPU-Bottleneck".format(avg_frame_time, avg_upload_time))
        
        # Region File Performance Insights
        region_file_perf = analysis['region_file_performance']
        if region_file_perf['total_regions_tracked'] > 0:
            fastest = region_file_perf['fastest_5']
            slowest = region_file_perf['slowest_5']
            
            if fastest and slowest:
                fastest_combined = fastest[0]['combined_avg'] if fastest else 0
                slowest_combined = slowest[-1]['combined_avg'] if slowest else 0
                
                if slowest_combined > fastest_combined * 3:
                    insights.append("[WARN] Langsamste Region-Datei ({:.2f}ms) ist deutlich langsamer als schnellste ({:.2f}ms) - mögliche Fragmentierung oder Hardware-Probleme".format(
                        slowest_combined, fastest_combined))
                elif slowest_combined > fastest_combined * 2:
                    insights.append("[INFO] Langsamste Region-Datei ({:.2f}ms) ist langsamer als schnellste ({:.2f}ms) - möglicherweise Fragmentierung".format(
                        slowest_combined, fastest_combined))
        
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
        
        # Disk Save Times (falls verfügbar)
        if 'disk_save_times' in frame_perf:
            disk_save_stats = frame_perf['disk_save_times']
            print(f"\nDisk-Save-Zeiten (IO pro Chunk, ms):")
            print(f"  Minimum:  {disk_save_stats['min_ms']:>8.2f}")
            print(f"  Maximum:  {disk_save_stats['max_ms']:>8.2f}")
            print(f"  Durchschnitt: {disk_save_stats['avg_ms']:>8.2f}")
            print(f"  Median:   {disk_save_stats['median_ms']:>8.2f}")
            print(f"  Total Events: {disk_save_stats['total_events']}")
        
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
            if 'disk_save_times' in frame_perf:
                avg_disk_save_time = frame_perf['disk_save_times']['avg_ms']
                print(f"Disk-Save-Zeit:    {avg_disk_save_time:>8.2f} ms (pro Chunk)")
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
        
        # Decoration Performance
        if 'decoration_collect_times' in stats and stats['decoration_collect_times'].get('avg', 0) > 0:
            print(f"\n{'=' * 80}")
            print("DECORATION PERFORMANCE")
            print(f"{'=' * 80}")
            
            collect_stats = stats.get('decoration_collect_times', {})
            sprite_stats = stats.get('decoration_sprite_times', {})
            vertex_stats = stats.get('decoration_vertex_times', {})
            vbo_stats = stats.get('decoration_vbo_times', {})
            render_stats = stats.get('decoration_render_times', {})
            count_stats = stats.get('decoration_counts', {})
            
            print(f"\nSammeln von Dekorationen (ms):")
            print(f"  Minimum:  {collect_stats.get('min', 0):>8.2f}")
            print(f"  Maximum:  {collect_stats.get('max', 0):>8.2f}")
            print(f"  Durchschnitt: {collect_stats.get('avg', 0):>8.2f}")
            print(f"  Median:   {collect_stats.get('median', 0):>8.2f}")
            
            if sprite_stats.get('avg', 0) > 0:
                print(f"\nSprite-Name-Bestimmung (ms):")
                print(f"  Minimum:  {sprite_stats.get('min', 0):>8.2f}")
                print(f"  Maximum:  {sprite_stats.get('max', 0):>8.2f}")
                print(f"  Durchschnitt: {sprite_stats.get('avg', 0):>8.2f}")
                print(f"  Median:   {sprite_stats.get('median', 0):>8.2f}")
            
            if vertex_stats.get('avg', 0) > 0:
                print(f"\nVertex-Erstellung (ms):")
                print(f"  Minimum:  {vertex_stats.get('min', 0):>8.2f}")
                print(f"  Maximum:  {vertex_stats.get('max', 0):>8.2f}")
                print(f"  Durchschnitt: {vertex_stats.get('avg', 0):>8.2f}")
                print(f"  Median:   {vertex_stats.get('median', 0):>8.2f}")
            
            if vbo_stats.get('avg', 0) > 0:
                print(f"\nVBO-Update/Erstellung (ms):")
                print(f"  Minimum:  {vbo_stats.get('min', 0):>8.2f}")
                print(f"  Maximum:  {vbo_stats.get('max', 0):>8.2f}")
                print(f"  Durchschnitt: {vbo_stats.get('avg', 0):>8.2f}")
                print(f"  Median:   {vbo_stats.get('median', 0):>8.2f}")
            
            if render_stats.get('avg', 0) > 0:
                print(f"\nGPU-Rendering (ms):")
                print(f"  Minimum:  {render_stats.get('min', 0):>8.2f}")
                print(f"  Maximum:  {render_stats.get('max', 0):>8.2f}")
                print(f"  Durchschnitt: {render_stats.get('avg', 0):>8.2f}")
                print(f"  Median:   {render_stats.get('median', 0):>8.2f}")
            
            if count_stats.get('avg', 0) > 0:
                print(f"\nAnzahl Dekorationen pro Frame:")
                print(f"  Minimum:  {count_stats.get('min', 0):>8.0f}")
                print(f"  Maximum:  {count_stats.get('max', 0):>8.0f}")
                print(f"  Durchschnitt: {count_stats.get('avg', 0):>8.1f}")
                print(f"  Median:   {count_stats.get('median', 0):>8.1f}")
            
            # Gesamtzeit berechnen
            total_avg = (collect_stats.get('avg', 0) + 
                        sprite_stats.get('avg', 0) + 
                        vertex_stats.get('avg', 0) + 
                        vbo_stats.get('avg', 0) + 
                        render_stats.get('avg', 0))
            print(f"\nGesamtzeit Dekorationen (ms):")
            print(f"  Durchschnitt: {total_avg:>8.2f}")
        
        # Sprite Cache Statistics
        sprite_cache = analysis.get('sprite_cache_stats', {})
        if sprite_cache and sprite_cache.get('total_events', 0) > 0:
            print(f"\n{'=' * 80}")
            print("SPRITE CACHE STATISTICS")
            print(f"{'=' * 80}")
            
            cumulative = sprite_cache.get('cumulative', {})
            hit_rates = sprite_cache.get('hit_rates', {})
            per_period = sprite_cache.get('per_period', {})
            
            print(f"\nGesamt (Cumulative):")
            print(f"  Hits:      {cumulative.get('hits', 0):>8}")
            print(f"  Misses:    {cumulative.get('misses', 0):>8}")
            print(f"  Total:     {cumulative.get('total', 0):>8}")
            print(f"  Hit Rate:  {cumulative.get('hit_rate', 0):>7.1f}%")
            
            if hit_rates.get('avg', 0) > 0:
                print(f"\nHit Rate pro Periode (%):")
                print(f"  Minimum:  {hit_rates.get('min', 0):>8.1f}")
                print(f"  Maximum:  {hit_rates.get('max', 0):>8.1f}")
                print(f"  Durchschnitt: {hit_rates.get('avg', 0):>8.1f}")
                print(f"  Median:   {hit_rates.get('median', 0):>8.1f}")
            
            if per_period.get('hits', {}).get('avg', 0) > 0:
                print(f"\nHits pro Periode:")
                print(f"  Minimum:  {per_period['hits'].get('min', 0):>8}")
                print(f"  Maximum:  {per_period['hits'].get('max', 0):>8}")
                print(f"  Durchschnitt: {per_period['hits'].get('avg', 0):>8.1f}")
                print(f"  Median:   {per_period['hits'].get('median', 0):>8}")
            
            if per_period.get('misses', {}).get('avg', 0) > 0:
                print(f"\nMisses pro Periode:")
                print(f"  Minimum:  {per_period['misses'].get('min', 0):>8}")
                print(f"  Maximum:  {per_period['misses'].get('max', 0):>8}")
                print(f"  Durchschnitt: {per_period['misses'].get('avg', 0):>8.1f}")
                print(f"  Median:   {per_period['misses'].get('median', 0):>8}")
        
        # Region File Performance (Fastest & Slowest 5)
        region_file_perf = analysis['region_file_performance']
        if region_file_perf['total_regions_tracked'] > 0:
            print(f"\n{'=' * 80}")
            print("REGION-DATEI PERFORMANCE (Top 5 Schnellste & Langsamste)")
            print(f"{'=' * 80}")
            print(f"Gesamt getrackte Regionen: {region_file_perf['total_regions_tracked']}")
            
            fastest = region_file_perf['fastest_5']
            if fastest:
                print(f"\nSchnellste 5 Region-Dateien:")
                for i, region in enumerate(fastest, 1):
                    print(f"  {i:>2}. Region ({region['region_x']:>4}, {region['region_y']:>4}): "
                          f"Load={region['avg_load']:>6.2f}ms, Save={region['avg_save']:>6.2f}ms, "
                          f"Combined={region['combined_avg']:>6.2f}ms "
                          f"(Loads: {region['load_count']}, Saves: {region['save_count']})")
            
            slowest = region_file_perf['slowest_5']
            if slowest:
                print(f"\nLangsamste 5 Region-Dateien:")
                for i, region in enumerate(slowest, 1):
                    print(f"  {i:>2}. Region ({region['region_x']:>4}, {region['region_y']:>4}): "
                          f"Load={region['avg_load']:>6.2f}ms, Save={region['avg_save']:>6.2f}ms, "
                          f"Combined={region['combined_avg']:>6.2f}ms "
                          f"(Loads: {region['load_count']}, Saves: {region['save_count']})")
        
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
        
        # UI Performance
        ui_perf = analysis.get('ui_performance', {})
        if ui_perf.get('world_render_times') or ui_perf.get('ui_render_times'):
            print(f"\n{'=' * 80}")
            print("UI PERFORMANCE")
            print(f"{'=' * 80}")
            
            if ui_perf.get('world_render_times'):
                world_stats = ui_perf['world_render_times']
                print(f"\nWorld-Rendering (ms):")
                print(f"  Minimum:  {world_stats.get('min', 0):>8.2f}")
                print(f"  Maximum:  {world_stats.get('max', 0):>8.2f}")
                print(f"  Durchschnitt: {world_stats.get('avg', 0):>8.2f}")
                print(f"  Median:   {world_stats.get('median', 0):>8.2f}")
            
            if ui_perf.get('debug_render_times') and ui_perf['debug_render_times'].get('avg', 0) > 0:
                debug_stats = ui_perf['debug_render_times']
                print(f"\nDebug-Visualisierung (ms):")
                print(f"  Minimum:  {debug_stats.get('min', 0):>8.2f}")
                print(f"  Maximum:  {debug_stats.get('max', 0):>8.2f}")
                print(f"  Durchschnitt: {debug_stats.get('avg', 0):>8.2f}")
                print(f"  Median:   {debug_stats.get('median', 0):>8.2f}")
            
            if ui_perf.get('ui_render_times'):
                ui_stats = ui_perf['ui_render_times']
                print(f"\nUI-Rendering (ms):")
                print(f"  Minimum:  {ui_stats.get('min', 0):>8.2f}")
                print(f"  Maximum:  {ui_stats.get('max', 0):>8.2f}")
                print(f"  Durchschnitt: {ui_stats.get('avg', 0):>8.2f}")
                print(f"  Median:   {ui_stats.get('median', 0):>8.2f}")
            
            if ui_perf.get('stats_overlay_times'):
                stats_stats = ui_perf['stats_overlay_times']
                print(f"\nPerformance-Stats-Overlay (ms):")
                print(f"  Minimum:  {stats_stats.get('min', 0):>8.2f}")
                print(f"  Maximum:  {stats_stats.get('max', 0):>8.2f}")
                print(f"  Durchschnitt: {stats_stats.get('avg', 0):>8.2f}")
                print(f"  Median:   {stats_stats.get('median', 0):>8.2f}")
        
        # GPU Performance (Phase 4.2)
        gpu_perf = analysis.get('gpu_performance', {})
        if gpu_perf:
            chunk_gpu = gpu_perf.get('chunk_render_times', {})
            deco_gpu = gpu_perf.get('decoration_render_times', {})
            shadow_gpu = gpu_perf.get('shadow_render_times', {})
            total_gpu = gpu_perf.get('total_render_times', {})
            
            if (chunk_gpu.get('avg', 0) > 0 or deco_gpu.get('avg', 0) > 0 or 
                shadow_gpu.get('avg', 0) > 0 or total_gpu.get('avg', 0) > 0):
                print(f"\n{'=' * 80}")
                print("GPU PERFORMANCE (ModernGL Query Objects)")
                print(f"{'=' * 80}")
                
                if chunk_gpu.get('avg', 0) > 0:
                    print(f"\nChunk Rendering (GPU, ms):")
                    print(f"  Minimum:  {chunk_gpu.get('min', 0):>8.2f}")
                    print(f"  Maximum:  {chunk_gpu.get('max', 0):>8.2f}")
                    print(f"  Durchschnitt: {chunk_gpu.get('avg', 0):>8.2f}")
                    print(f"  Median:   {chunk_gpu.get('median', 0):>8.2f}")
                
                if deco_gpu.get('avg', 0) > 0:
                    print(f"\nDecoration Rendering (GPU, ms):")
                    print(f"  Minimum:  {deco_gpu.get('min', 0):>8.2f}")
                    print(f"  Maximum:  {deco_gpu.get('max', 0):>8.2f}")
                    print(f"  Durchschnitt: {deco_gpu.get('avg', 0):>8.2f}")
                    print(f"  Median:   {deco_gpu.get('median', 0):>8.2f}")
                
                if shadow_gpu.get('avg', 0) > 0:
                    print(f"\nShadow Rendering (GPU, ms):")
                    print(f"  Minimum:  {shadow_gpu.get('min', 0):>8.2f}")
                    print(f"  Maximum:  {shadow_gpu.get('max', 0):>8.2f}")
                    print(f"  Durchschnitt: {shadow_gpu.get('avg', 0):>8.2f}")
                    print(f"  Median:   {shadow_gpu.get('median', 0):>8.2f}")
                
                if total_gpu.get('avg', 0) > 0:
                    print(f"\nTotal Frame Rendering (GPU, ms):")
                    print(f"  Minimum:  {total_gpu.get('min', 0):>8.2f}")
                    print(f"  Maximum:  {total_gpu.get('max', 0):>8.2f}")
                    print(f"  Durchschnitt: {total_gpu.get('avg', 0):>8.2f}")
                    print(f"  Median:   {total_gpu.get('median', 0):>8.2f}")
        
        # Generic Metrics (Phase 5: Multi-Threading Mesh-Generation)
        generic_metrics = analysis.get('generic_metrics', {})
        if generic_metrics:
            print(f"\n{'=' * 80}")
            print("GENERIC METRICS (Phase 5: Multi-Threading Mesh-Generation)")
            print(f"{'=' * 80}")
            
            # Chunk Preparation Time
            if 'chunk_prep_time_ms' in generic_metrics:
                prep = generic_metrics['chunk_prep_time_ms']
                print(f"\nChunk Preparation Time (ms):")
                print(f"  Minimum:  {prep.get('min', 0):>8.2f}")
                print(f"  Maximum:  {prep.get('max', 0):>8.2f}")
                print(f"  Durchschnitt: {prep.get('avg', 0):>8.2f}")
                print(f"  Median:   {prep.get('median', 0):>8.2f}")
                print(f"  Total Events: {prep.get('count', 0)}")
            
            # Batch Preparation Time
            if 'chunk_batch_prep_time_ms' in generic_metrics:
                batch_prep = generic_metrics['chunk_batch_prep_time_ms']
                print(f"\nBatch Preparation Time (ms):")
                print(f"  Minimum:  {batch_prep.get('min', 0):>8.2f}")
                print(f"  Maximum:  {batch_prep.get('max', 0):>8.2f}")
                print(f"  Durchschnitt: {batch_prep.get('avg', 0):>8.2f}")
                print(f"  Median:   {batch_prep.get('median', 0):>8.2f}")
                print(f"  Total Events: {batch_prep.get('count', 0)}")
            
            # Batch Size
            if 'chunk_batch_size' in generic_metrics:
                batch_size = generic_metrics['chunk_batch_size']
                print(f"\nBatch Size (chunks per batch):")
                print(f"  Minimum:  {batch_size.get('min', 0):>8.0f}")
                print(f"  Maximum:  {batch_size.get('max', 0):>8.0f}")
                print(f"  Durchschnitt: {batch_size.get('avg', 0):>8.2f}")
                print(f"  Median:   {batch_size.get('median', 0):>8.0f}")
                print(f"  Total Events: {batch_size.get('count', 0)}")
        
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
