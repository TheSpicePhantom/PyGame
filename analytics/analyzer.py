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
        
        # Berechne geschätzte Frame-Anzahl basierend auf Durchschnitts-FPS
        session_duration = self._analyze_session()['duration_seconds']
        estimated_frames = fps_stats['avg'] * session_duration
        
        return {
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
    
    def _analyze_chunk_loading(self) -> Dict:
        """Analysiert Chunk-Loading-Performance"""
        chunk_events = self.data.get('chunk_events', [])
        
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
        
        # Movement Insights
        if movement['total_events'] > 0 and movement['delays']:
            avg_delay = movement['delays']['avg_s']
            expected_delay = 1/60
            if avg_delay > expected_delay * 1.5:
                insights.append("[WARN] Durchschnittliche Movement-Delay ({:.2f}ms) ist hoeher als erwartet ({:.2f}ms)".format(avg_delay*1000, expected_delay*1000))
            else:
                insights.append("[OK] Movement-Verarbeitung ist konsistent ({:.2f}ms Durchschnitt)".format(avg_delay*1000))
        
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
                    flags = []
                    if chunk_info['has_generation']:
                        flags.append("GEN")
                    if chunk_info['has_save']:
                        flags.append("SAVE")
                    flag_str = f" [{', '.join(flags)}]" if flags else ""
                    print(f"  {i:>2}. Chunk ({chunk_info['chunk'][0]:>4}, {chunk_info['chunk'][1]:>4}): {chunk_info['load_time_ms']:>6.2f}ms{flag_str}")
        
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
