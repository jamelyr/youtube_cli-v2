import asyncio
import logging
import sys
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import json
import threading

# --- Dependency Check and Imports ---
try:
    import yt_dlp
    import mpv
    from textual.app import App, ComposeResult
    from textual.widgets import (
        Header, Footer, Input, DataTable, Static, ProgressBar,
        Label
    )
    from textual.containers import Container, Horizontal, Vertical
    from textual.binding import Binding
    from textual import on
    from textual.widgets.data_table import RowKey
except ImportError as e:
    print(f"Error: A required library is missing: {e.name}", file=sys.stderr)
    print("Please ensure your virtual environment is active and run 'pip install -r requirements.txt' again.", file=sys.stderr)
    sys.exit(1)
# --- End Dependency Check ---

# --- Logging Configuration ---
LOG_FILE = Path.home() / '.youtube_cli' / 'youtube_cli.log'
LOG_FILE.parent.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE, mode='w')]
)
logger = logging.getLogger(__name__)


# --- Application Enums and Dataclasses ---
class PlaybackState(Enum):
    STOPPED = "Stopped"
    PLAYING = "Playing"
    PAUSED = "Paused"
    BUFFERING = "Buffering"
    ERROR = "Error"

@dataclass(slots=True)
class VideoInfo:
    id: str
    title: str
    uploader: str
    duration: Optional[int]
    url: str = field(init=False, repr=False)

    def __post_init__(self):
        self.url = f"https://www.youtube.com/watch?v={self.id}"

    @property
    def formatted_duration(self) -> str:
        if self.duration is None: return "N/A"
        h, rem = divmod(self.duration, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h):02}:{int(m):02}:{int(s):02}" if h > 0 else f"{int(m):02}:{int(s):02}"

# --- Core Application State Management ---
class AppState:
    """The thread-safe, single source of truth for the entire application state."""
    def __init__(self):
        self._lock = threading.RLock()
        self.videos: List[VideoInfo] = []
        self.current_video_index: Optional[int] = None
        self._playback_state = PlaybackState.STOPPED
        self.position = 0.0
        self.duration = 0.0
        self.search_cache: Dict[str, List[VideoInfo]] = {}
        self.play_queue: List[VideoInfo] = []
        self.focus_mode: str = "search"
        self.config = self._load_config()
        self._volume = self.config.get('volume', 100)
        self.autoplay_enabled = self.config.get('autoplay', True)

    @property
    def volume(self) -> int:
        with self._lock: return self._volume

    @property
    def playback_state(self) -> PlaybackState:
        with self._lock: return self._playback_state
        
    def set_volume(self, value: int) -> bool:
        with self._lock:
            new_volume = max(0, min(100, value))
            if self._volume != new_volume:
                self._volume = new_volume
                return True
            return False

    def set_playback_state(self, new_state: PlaybackState) -> bool:
        with self._lock:
            if self._playback_state != new_state:
                logger.info(f"State transition: {self._playback_state.name} -> {new_state.name}")
                self._playback_state = new_state
                return True
            return False

    def set_position(self, new_position: float):
        with self._lock:
            self.position = new_position
            
    def set_duration(self, new_duration: float):
        with self._lock:
            if self.duration != new_duration:
                self.duration = new_duration
                
    def add_to_queue(self, video: VideoInfo):
        with self._lock:
            self.play_queue.insert(0, video)

    def get_next_from_queue(self) -> Optional[VideoInfo]:
        with self._lock:
            return self.play_queue.pop(0) if self.play_queue else None

    def _load_config(self) -> Dict[str, Any]:
        config_path = Path.home() / '.youtube_cli' / 'config.json'
        default_config = {
            'max_search_results': 25, 'cache_size': 50,
            'default_quality': 'bestvideo[height<=480]+bestaudio/best[height<=480]',
            'autoplay': True, 'volume': 100
        }
        if not config_path.exists(): return default_config
        try:
            with config_path.open('r') as f:
                return {**default_config, **json.load(f)}
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Config load failed: {e}. Using defaults.")
            return default_config

    def save_config(self):
        config_path = Path.home() / '.youtube_cli' / 'config.json'
        config_to_save = {'volume': self.volume, 'autoplay': self.autoplay_enabled}
        try:
            with config_path.open('w') as f:
                json.dump(config_to_save, f, indent=4)
        except OSError as e:
            logger.error(f"Failed to save config: {e}")

    @property
    def current_video(self) -> Optional[VideoInfo]:
        if self.current_video_index is not None and 0 <= self.current_video_index < len(self.videos):
            return self.videos[self.current_video_index]
        return None

# --- Core Service Classes ---
class VideoPlayer:
    def __init__(self, state: AppState, app: 'YouTubeCLI'):
        self.state = state
        self.app = app
        self.player: Optional[mpv.MPV] = None
        if not shutil.which('mpv'):
            logger.critical("FATAL: 'mpv' executable not found in PATH.")
            sys.exit(1)
        self._setup_player()

    def _mpv_log_handler(self, level, prefix, text):
        logger.info(f"mpv: [{prefix}] {text.strip()}")

    def _setup_player(self):
        try:
            self.player = mpv.MPV(
                ytdl=True,
                ytdl_format=self.state.config.get('default_quality'),
                cache=True,
                cache_secs=15,
                osc=True,
                keep_open=True, # <-- THE DEFINITIVE FIX: Tells mpv not to exit after a file ends.
                log_handler=self._mpv_log_handler,
                loglevel='info'
            )
            self.player.volume = self.state.volume
            self.player.observe_property('time-pos', self._on_time_pos_change)
            self.player.observe_property('pause', self._on_pause_change)
            self.player.observe_property('eof-reached', self._on_eof_reached)
            self.player.observe_property('duration', self._on_duration_change)
            logger.info("MPV player initialized with keep_open=True for continuous playback.")
        except Exception as e:
            logger.error(f"Failed to initialize MPV player: {e}", exc_info=True)
            self.player = None

    def _on_time_pos_change(self, _, value):
        if value is not None and self.app.is_running:
            self.app.call_from_thread(self.app.sync_playback_timer, float(value))

    def _on_duration_change(self, _, value):
        if value is not None and self.app.is_running:
            self.app.call_from_thread(self.app.sync_duration, float(value))

    def _on_pause_change(self, _, player_is_paused: bool):
        if self.app.is_running:
            self.app.call_from_thread(self.app.sync_playback_status_from_player, player_is_paused)

    def _on_eof_reached(self, _, eof_is_reached: bool):
        """Hardened EOF handling."""
        if eof_is_reached and self.state.autoplay_enabled and self.app.is_running:
            # We only need to check if autoplay is enabled. The state machine will handle the rest.
            logger.info("EOF reached and autoplay is ON. Triggering next video.")
            self.app.call_from_thread(self.app.action_next_video)

    def play(self, video: VideoInfo):
        if not self.player: return
        try:
            self.player.play(video.url)
            self.player.pause = False
        except Exception as e:
            logger.error(f"MPV failed to play URL '{video.url}': {e}", exc_info=True)
            self.app.call_from_thread(self.app.handle_playback_error)

    def set_pause(self, should_pause: bool):
        if self.player: self.player.pause = should_pause
    def set_volume(self, volume: int):
        if self.player: self.player.volume = volume
    def seek(self, seconds: float):
        if self.player: self.player.seek(seconds, reference='relative')

    def cleanup(self):
        if self.player:
            try: self.player.terminate()
            except Exception as e: logger.error(f"Error during MPV cleanup: {e}")

class SearchEngine:
    def __init__(self, state: AppState):
        self.state = state
        self.search_opts = {
            'quiet': True, 'no_warnings': True,
            'default_search': f'ytsearch{state.config.get("max_search_results", 25)}:',
            'extract_flat': 'in_playlist'
        }

    async def search(self, query: str) -> List[VideoInfo]:
        if query in self.state.search_cache: return self.state.search_cache[query]
        logger.info(f"Performing flat search for: '{query}'")
        try:
            loop = asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(self.search_opts) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False))
            results = [
                VideoInfo(id=e['id'], title=e.get('title', 'N/A'), uploader=e.get('uploader', 'N/A'), duration=e.get('duration'))
                for e in info.get('entries', []) if e and e.get('id') and e.get('duration') is not None
            ]
            if len(self.state.search_cache) >= self.state.config['cache_size']:
                self.state.search_cache.pop(next(iter(self.state.search_cache)))
            self.state.search_cache[query] = results
            return results
        except Exception as e:
            logger.error(f"Search failed for '{query}': {e}", exc_info=True)
            return []

# --- UI Widget Classes ---
class NowPlayingWidget(Static):
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[b]Now Playing[/b]", id="now-playing-header")
            yield Label("No track loaded.", id="now-playing-title")
            yield Label("", id="now-playing-uploader")
            yield Label("Status: Stopped", id="now-playing-status")
            yield Label("--:-- / --:--", id="now-playing-timer")
            yield Label("Queue: Empty", id="queue-status")

    def update_all(self, state: AppState):
        video = state.current_video
        title_label = self.query_one("#now-playing-title", Label)
        uploader_label = self.query_one("#now-playing-uploader", Label)
        if video:
            title_label.update(f"[b]Title:[/b] {video.title}")
            uploader_label.update(f"[b]Uploader:[/b] {video.uploader}")
        else:
            title_label.update("No track loaded.")
            uploader_label.update("")
        self.query_one("#now-playing-status", Label).update(f"[b]Status:[/b] {state.playback_state.value}")
        self.query_one("#now-playing-timer", Label).update(f"{self._format_time(state.position)} / {self._format_time(state.duration)}")
        queue_size = len(state.play_queue)
        queue_text = f"Queue: {queue_size} item{'s' if queue_size != 1 else ''}" if queue_size > 0 else "Queue: Empty"
        self.query_one("#queue-status", Label).update(queue_text)

    @staticmethod
    def _format_time(seconds: float) -> str:
        if not seconds or seconds <= 0: return "00:00"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

# --- Main Application Class ---
from importlib.resources import files
class YouTubeCLI(App[None]):
    CSS_PATH = files(__package__).joinpath("style.css")
    BINDINGS = [
        Binding("q", "quit", "Quit", show=True), Binding("space", "toggle_pause", "Play/Pause", show=True),
        Binding("n", "next_video", "Next", show=True), Binding("p", "previous_video", "Previous", show=True),
        Binding("a", "toggle_autoplay", "Autoplay", show=True),
        Binding("l", "queue_next", "Queue Next", show=True),
        Binding("tab", "toggle_focus", "Toggle Focus", show=True),
        Binding("up", "volume_up(5)", "Vol +", show=False),
        Binding("down", "volume_down(5)", "Vol -", show=False), Binding("right", "seek_forward(10)", "Seek +", show=False),
        Binding("left", "seek_back(10)", "Seek -", show=False),
    ]
    UI_UPDATE_INTERVAL = 0.1

    def __init__(self):
        super().__init__()
        self.state = AppState()
        self.search_engine = SearchEngine(self.state)
        self.player = VideoPlayer(self.state, self)
        self._last_ui_update_time = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Input(placeholder="Search YouTube...", id="search-input")
            with Horizontal():
                yield DataTable(id="video-table")
                with Vertical(id="sidebar"):
                    yield NowPlayingWidget()
                    yield Label(f"Volume: {self.state.volume}%", id="volume-label")
            yield ProgressBar(id="progress-bar", total=100, show_eta=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#video-table", DataTable)
        table.add_columns("Title", "Uploader", "Duration")
        table.cursor_type = "row"
        self.query_one("#search-input").focus()
        self.query_one("#video-table").border_title = "Search Results"
        self.query_one("#sidebar").border_title = "Playback"
        self.update_ui_from_state()
        
    def on_unmount(self) -> None:
        self.player.cleanup()
        self.state.save_config()

    def update_ui_from_state(self):
        self.query_one(NowPlayingWidget).update_all(self.state)
        self.query_one("#volume-label").update(f"Volume: {self.state.volume}%")
        progress_bar = self.query_one("#progress-bar", ProgressBar)
        progress_bar.progress = (self.state.position / self.state.duration * 100) if self.state.duration > 0 else 0
        self.update_autoplay_binding_description()

    def update_autoplay_binding_description(self):
        new_bindings = [
            Binding(b.key, b.action, f"Autoplay [{'ON' if self.state.autoplay_enabled else 'OFF'}]", show=True, key_display=b.key_display)
            if b.key == 'a' else b
            for b in self.BINDINGS
        ]
        self.bindings = new_bindings

    @on(Input.Submitted, "#search-input")
    async def on_search_submitted(self, event: Input.Submitted):
        query = event.value.strip()
        if not query: return
        table = self.query_one("#video-table", DataTable)
        table.clear()
        self.notify("Searching...", title="Search")
        videos = await self.search_engine.search(query)
        self.state.videos = videos
        if videos:
            for i, video in enumerate(videos):
                table.add_row(video.title, video.uploader, video.formatted_duration, key=str(i))
            self.notify(f"Found {len(videos)} videos.", title="Search Complete")
        else:
            self.notify("No videos found.", title="Search Failed", severity="warning")

    @on(DataTable.RowSelected, "#video-table")
    async def on_video_selected(self, event: DataTable.RowSelected):
        if event.row_key and event.row_key.value is not None:
            await self.play_video(int(event.row_key.value))

    async def play_video(self, index: int):
        if not (0 <= index < len(self.state.videos)): return
        
        self.state.current_video_index = index
        video = self.state.videos[index]
        self.query_one("#video-table", DataTable).move_cursor(row=index, animate=True)
        
        if self.state.set_playback_state(PlaybackState.BUFFERING): self.update_ui_from_state()
        self.notify(f"Loading: {video.title}")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.player.play, video)
        
        if self.state.playback_state == PlaybackState.BUFFERING:
            if self.state.set_playback_state(PlaybackState.PLAYING):
                self.update_ui_from_state()

    def sync_playback_timer(self, position: float):
        now = time.monotonic()
        if now - self._last_ui_update_time > self.UI_UPDATE_INTERVAL:
            self.state.set_position(position)
            self.update_ui_from_state()
            self._last_ui_update_time = now
    
    def sync_duration(self, duration: float):
        self.state.set_duration(duration)
        self.update_ui_from_state()
    
    def sync_playback_status_from_player(self, player_is_paused: bool):
        current_app_state = self.state.playback_state
        if player_is_paused and current_app_state == PlaybackState.PLAYING:
            if self.state.set_playback_state(PlaybackState.PAUSED): self.update_ui_from_state()
        elif not player_is_paused and current_app_state == PlaybackState.PAUSED:
            if self.state.set_playback_state(PlaybackState.PLAYING): self.update_ui_from_state()
            
    def handle_playback_error(self):
        if self.state.set_playback_state(PlaybackState.ERROR): self.update_ui_from_state()
        self.notify(f"Failed to play video.", title="Playback Error", severity="error")

    def action_toggle_pause(self):
        current_state = self.state.playback_state
        if current_state == PlaybackState.PLAYING:
            if self.state.set_playback_state(PlaybackState.PAUSED):
                self.player.set_pause(True)
                self.update_ui_from_state()
        elif current_state == PlaybackState.PAUSED:
            if self.state.set_playback_state(PlaybackState.PLAYING):
                self.player.set_pause(False)
                self.update_ui_from_state()

    async def action_next_video(self):
        next_video_from_queue = self.state.get_next_from_queue()
        
        if next_video_from_queue:
            logger.info(f"Playing next from queue: {next_video_from_queue.title}")
            try:
                index = self.state.videos.index(next_video_from_queue)
                await self.play_video(index)
            except ValueError:
                logger.warning("Queued video not in current search results. Clearing queue.")
                self.state.play_queue.clear()
                await self.action_next_video()
        elif self.state.current_video_index is not None and len(self.state.videos) > 0:
            logger.info("Playing next from search results (linear).")
            # Ensure we don't wrap around if there's only one video
            if len(self.state.videos) > 1 or self.state.play_queue:
                 next_index = (self.state.current_video_index + 1) % len(self.state.videos)
                 if next_index != self.state.current_video_index: # Avoid replaying same song
                    await self.play_video(next_index)
        
        self.update_ui_from_state()

    async def action_previous_video(self):
        if self.state.current_video_index is not None and len(self.state.videos) > 0:
            prev_index = (self.state.current_video_index - 1) % len(self.state.videos)
            await self.play_video(prev_index)

    def action_toggle_autoplay(self):
        self.state.autoplay_enabled = not self.state.autoplay_enabled
        self.notify(f"Autoplay {'enabled' if self.state.autoplay_enabled else 'disabled'}.")
        self.update_ui_from_state()

    def action_volume_up(self, amount: int):
        if self.state.set_volume(self.state.volume + amount):
            self.player.set_volume(self.state.volume)
            self.update_ui_from_state()

    def action_volume_down(self, amount: int):
        if self.state.set_volume(self.state.volume - amount):
            self.player.set_volume(self.state.volume)
            self.update_ui_from_state()

    def action_seek_forward(self, seconds: int): self.player.seek(seconds)
    def action_seek_back(self, seconds: int): self.player.seek(-seconds)

    def action_queue_next(self):
        table = self.query_one("#video-table", DataTable)
        cursor_row = table.cursor_row
        if 0 <= cursor_row < len(self.state.videos):
            video_to_queue = self.state.videos[cursor_row]
            self.state.add_to_queue(video_to_queue)
            self.notify(f"Queued: {video_to_queue.title}")
            self.update_ui_from_state()

    def action_toggle_focus(self):
        if self.state.focus_mode == "search":
            self.state.focus_mode = "table"
            self.query_one("#video-table").focus()
            self.notify("Focus: Video List")
        else:
            self.state.focus_mode = "search"
            self.query_one("#search-input").focus()
            self.notify("Focus: Search Input")

if __name__ == "__main__":
    css_path = Path("style.css")
    if not css_path.exists():
        css_path.write_text("""
#video-table { width: 2fr; height: 100%; margin-right: 1; }
#sidebar { width: 1fr; height: 100%; }
#progress-bar { margin-top: 1; }
        """)
    app = YouTubeCLI()
    app.run()
