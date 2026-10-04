"""Main application window for Video Downloader."""

import logging
import os
import threading
import urllib.request
import uuid

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")
gi.require_version("GObject", "2.0")

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from app.clipboard import ClipboardService
from app.downloader import DownloaderService
from app.formats import FormatService
from app.history import HistoryService
from app.metadata import MetadataError, MetadataService
from app.models import (
    AppState,
    DownloadMode,
    DownloadStatus,
    DownloadTask,
    SmartRecommendation,
    VideoMetadata,
)
from app.queue import DownloadQueue
from app.settings import Settings
from app.utils import (
    check_disk_space,
    detect_provider,
    extract_urls,
    format_file_size,
    is_valid_url,
    open_folder,
)
from app.views.history_dialog import HistoryDialog
from app.views.options_expander import OptionsExpanderView
from app.views.queue_view import QueueView
from app.views.smart_card import SmartCardView

logger = logging.getLogger(__name__)


class MainWindow(Adw.ApplicationWindow):
    """Main application window for Video Downloader."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Services
        self._metadata_service = MetadataService()
        self._format_service = FormatService()
        self._downloader_service = DownloaderService()
        self._history_service = HistoryService()
        self._clipboard_service = ClipboardService()
        self._settings = Settings()

        # Queue
        self._queue = DownloadQueue(
            downloader_service=self._downloader_service,
            history_service=self._history_service,
        )

        # State
        self._state = AppState.EMPTY
        self._metadata: VideoMetadata | None = None
        self._recommendation: SmartRecommendation | None = None

        # Window properties
        self.set_title("Video Downloader")
        self.set_default_size(620, 720)

        # Build UI & Wire
        self._build_ui()
        self._setup_actions()
        self._setup_drag_and_drop()
        self._setup_clipboard_monitoring()
        self._wire_queue_events()
        self._apply_state(AppState.EMPTY)

    # ─── UI Construction ─────────────────────────────────────────────────

    def _build_ui(self):
        """Build the complete window layout."""
        toolbar_view = Adw.ToolbarView()

        # Header bar with menu
        header_bar = Adw.HeaderBar()
        menu_button = Gtk.MenuButton(
            icon_name="open-menu-symbolic",
            menu_model=self._build_menu(),
        )
        header_bar.pack_end(menu_button)
        toolbar_view.add_top_bar(header_bar)

        # Toast overlay
        self._toast_overlay = Adw.ToastOverlay()

        # Main scrollable window
        scrolled = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            propagate_natural_height=True,
        )

        self._main_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=20,
            margin_top=24,
            margin_bottom=24,
            margin_start=24,
            margin_end=24,
        )

        # ── 1. URL Section ───────────────────────────────────────────────────
        url_group = Adw.PreferencesGroup()

        self._url_row = Adw.EntryRow(
            title="Paste video URL…",
        )
        self._url_row.connect("entry-activated", self._on_url_activated)

        self._fetch_button = Gtk.Button(
            icon_name="emblem-synchronizing-symbolic",
            valign=Gtk.Align.CENTER,
            tooltip_text="Analyze video link",
            css_classes=["flat"],
        )
        self._fetch_button.connect("clicked", self._on_fetch_clicked)
        self._url_row.add_suffix(self._fetch_button)

        url_group.add(self._url_row)
        self._main_box.append(url_group)

        # ── 2. Loading Spinner ───────────────────────────────────────────────
        self._loading_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            halign=Gtk.Align.CENTER,
            margin_top=16,
            margin_bottom=16,
        )
        self._spinner = Gtk.Spinner(
            spinning=True,
            width_request=36,
            height_request=36,
            halign=Gtk.Align.CENTER,
        )
        self._loading_label = Gtk.Label(
            label="Analyzing video…",
            css_classes=["dim-label"],
        )
        self._loading_box.append(self._spinner)
        self._loading_box.append(self._loading_label)
        self._main_box.append(self._loading_box)

        # ── 3. Smart Download Hero Card ──────────────────────────────────────
        self._smart_card = SmartCardView(
            on_download=self._start_smart_download,
            on_toggle_options=self._on_toggle_options,
        )
        self._main_box.append(self._smart_card)

        # ── 4. Options Expander Panel ────────────────────────────────────────
        self._options_view = OptionsExpanderView(
            default_dir=self._settings.download_dir,
            on_download_with_options=self._start_options_download,
            on_add_to_queue=self._add_options_to_queue,
            on_choose_folder=lambda: self._on_folder_clicked(None),
            on_download_clip=self._start_clip_download,
        )
        self._main_box.append(self._options_view)

        # ── 5. Queue View ────────────────────────────────────────────────────
        self._queue_view = QueueView(queue=self._queue)
        self._main_box.append(self._queue_view)

        # ── 6. Empty State ───────────────────────────────────────────────────
        self._empty_status = Adw.StatusPage(
            icon_name="folder-download-symbolic",
            title="Video Downloader",
            description="Paste a YouTube or Facebook link to get started.",
        )
        self._empty_status.set_vexpand(True)
        self._main_box.append(self._empty_status)

        # Assemble
        scrolled.set_child(self._main_box)
        self._toast_overlay.set_child(scrolled)
        toolbar_view.set_content(self._toast_overlay)
        self.set_content(toolbar_view)

    def _build_menu(self) -> Gio.Menu:
        """Build the hamburger menu."""
        menu = Gio.Menu()
        menu.append("Recent Downloads", "win.show-history")
        menu.append("About Video Downloader", "app.about")
        menu.append("Quit", "app.quit")
        return menu

    def _setup_actions(self):
        """Set up window actions."""
        # Focus URL field
        action_focus = Gio.SimpleAction.new("focus-url", None)
        action_focus.connect("activate", lambda *_: self._url_row.grab_focus())
        self.add_action(action_focus)

        # Choose folder
        action_folder = Gio.SimpleAction.new("choose-folder", None)
        action_folder.connect("activate", lambda *_: self._on_folder_clicked(None))
        self.add_action(action_folder)

        # Smart Download shortcut (Ctrl+Shift+D)
        action_smart = Gio.SimpleAction.new("smart-download", None)
        action_smart.connect("activate", lambda *_: self._start_smart_download())
        self.add_action(action_smart)

        # Show History (Ctrl+H)
        action_history = Gio.SimpleAction.new("show-history", None)
        action_history.connect("activate", lambda *_: self._on_show_history())
        self.add_action(action_history)

    def _setup_drag_and_drop(self):
        """Configure drag and drop of URLs into the window."""
        drop_target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.COPY)
        drop_target.connect("drop", self._on_drop_url)
        self.add_controller(drop_target)

    def _on_drop_url(self, target, value: str, x: float, y: float) -> bool:
        """Handle dropped text/URL."""
        if not value:
            return False

        urls = extract_urls(value)
        if not urls:
            return False

        if len(urls) == 1:
            self._url_row.set_text(urls[0])
            self._fetch_metadata(urls[0])
            return True
        else:
            self._handle_batch_urls(urls)
            return True

    def _setup_clipboard_monitoring(self):
        """Monitor clipboard when window gains focus."""
        self.connect("notify::is-active", self._on_window_active_changed)

    def _on_window_active_changed(self, window, param_spec):
        """Trigger clipboard check when window becomes active."""
        if self.props.is_active:
            self._clipboard_service.check_clipboard(self._on_clipboard_urls_detected)

    def _on_clipboard_urls_detected(self, urls: list[str]) -> None:
        """Handle detected video URLs from clipboard."""
        if not urls:
            return

        current_text = self._url_row.get_text().strip()

        if len(urls) == 1:
            url = urls[0]
            # Don't prompt if already analyzing or loaded this URL
            if current_text == url or (self._metadata and self._metadata.webpage_url == url):
                return

            toast = Adw.Toast.new("Video link detected in clipboard")
            toast.set_button_label("Analyze")
            toast.connect("button-clicked", lambda *_: self._use_clipboard_url(url))
            self._toast_overlay.add_toast(toast)
        else:
            toast = Adw.Toast.new(f"{len(urls)} video links in clipboard")
            toast.set_button_label("Add All to Queue")
            toast.connect("button-clicked", lambda *_: self._handle_batch_urls(urls))
            self._toast_overlay.add_toast(toast)

    def _use_clipboard_url(self, url: str) -> None:
        self._url_row.set_text(url)
        self._fetch_metadata(url)

    def _wire_queue_events(self):
        """Wire queue events for desktop notifications and state syncing."""
        original_completed = self._queue.on_task_completed

        def on_completed(task: DownloadTask):
            if original_completed:
                original_completed(task)
            app = self.get_application()
            if app and self._settings.notifications_enabled:
                app.send_download_notification(task.title)
            self._update_empty_state_visibility()

        self._queue.on_task_completed = on_completed

    # ─── State Machine ───────────────────────────────────────────────────

    def _apply_state(self, state: AppState):
        """Apply a new state to the window."""
        self._state = state
        logger.debug("State -> %s", state.value)

        show_loading = state == AppState.FETCHING_METADATA
        show_hero = state == AppState.READY and self._metadata is not None

        self._loading_box.set_visible(show_loading)
        self._spinner.set_spinning(show_loading)
        self._smart_card.set_visible(show_hero)

        # Options expander: hide by default when loading or empty, keep hidden until toggled
        if not show_hero:
            self._options_view.set_visible(False)
            self._smart_card.set_options_expanded(False)

        self._update_empty_state_visibility()

    def _update_empty_state_visibility(self):
        """Show empty state only if no metadata and no queue items."""
        has_metadata = self._state == AppState.READY and self._metadata is not None
        is_loading = self._state == AppState.FETCHING_METADATA
        has_queue = self._queue.get_active_count() > 0 or len(self._queue.get_tasks()) > 0

        self._empty_status.set_visible(not has_metadata and not is_loading and not has_queue)

    def _on_toggle_options(self, expanded: bool):
        """Show/hide advanced options below hero card."""
        self._options_view.set_visible(expanded)

    # ─── URL Handling ────────────────────────────────────────────────────

    def _on_url_activated(self, entry_row):
        """Handle Enter key in the URL field."""
        text = self._url_row.get_text().strip()

        # If metadata is already loaded for this exact URL, Enter starts Smart Download!
        if self._metadata and self._metadata.webpage_url == text and self._state == AppState.READY:
            self._start_smart_download()
            return

        urls = extract_urls(text)
        if len(urls) > 1:
            self._handle_batch_urls(urls)
        elif len(urls) == 1:
            self._fetch_metadata(urls[0])
        else:
            self._fetch_metadata(text)

    def _on_fetch_clicked(self, button):
        text = self._url_row.get_text().strip()
        urls = extract_urls(text)
        if len(urls) > 1:
            self._handle_batch_urls(urls)
        elif len(urls) == 1:
            self._fetch_metadata(urls[0])
        else:
            self._fetch_metadata(text)

    def _handle_batch_urls(self, urls: list[str]):
        """Queue multiple URLs for download."""
        self._clipboard_service.dismiss_urls(urls)
        queued_count = 0
        dest = self._settings.download_dir

        for url in urls:
            task = DownloadTask(
                id=str(uuid.uuid4())[:8],
                url=url,
                title=f"Video ({detect_provider(url).value})",
                quality="Best",
                output_format="MP4",
                mode=DownloadMode.VIDEO_AUDIO,
                destination=dest,
            )
            self._queue.add_task(task)
            queued_count += 1

        self._show_toast(f"Added {queued_count} videos to download queue")
        self._url_row.set_text("")
        self._update_empty_state_visibility()

    def _fetch_metadata(self, url: str):
        """Start metadata extraction in background."""
        if not is_valid_url(url):
            self._show_toast("Please enter a valid HTTP or HTTPS video URL.")
            return

        self._clipboard_service.dismiss_urls([url])
        self._apply_state(AppState.FETCHING_METADATA)

        thread = threading.Thread(
            target=self._fetch_metadata_worker,
            args=(url,),
            daemon=True,
        )
        thread.start()

    def _fetch_metadata_worker(self, url: str):
        try:
            metadata = self._metadata_service.extract(url)
            GLib.idle_add(self._on_metadata_success, metadata)
        except MetadataError as e:
            GLib.idle_add(self._on_metadata_error, e.user_message)
        except Exception as e:
            logger.error("Unexpected metadata error: %s", e)
            GLib.idle_add(self._on_metadata_error, "An unexpected error occurred while analyzing the video.")

    def _on_metadata_success(self, metadata: VideoMetadata):
        self._metadata = metadata

        # Generate smart recommendation (1080p MP4 > 720p MP4 > best)
        self._recommendation = self._format_service.get_smart_recommendation(metadata)

        # Update Smart Card
        self._smart_card.set_metadata(metadata, self._recommendation)

        # Update Options Expander
        self._options_view.populate(
            metadata=metadata,
            recommendation=self._recommendation,
            default_quality_pref=self._settings.default_quality,
        )

        # Load thumbnail asynchronously
        if metadata.thumbnail_url:
            self._load_thumbnail_async(metadata.thumbnail_url)
        else:
            self._smart_card.set_placeholder_thumbnail()

        self._apply_state(AppState.READY)
        return GLib.SOURCE_REMOVE

    def _on_metadata_error(self, message: str):
        self._show_toast(message)
        self._apply_state(AppState.EMPTY)
        return GLib.SOURCE_REMOVE

    # ─── Thumbnail Loading ───────────────────────────────────────────────

    def _load_thumbnail_async(self, url: str):
        def worker():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw_bytes = resp.read()

                glib_bytes = GLib.Bytes.new(raw_bytes)
                texture = Gdk.Texture.new_from_bytes(glib_bytes)
                GLib.idle_add(self._smart_card.set_thumbnail, texture)
            except Exception as e:
                logger.warning("Failed to load thumbnail: %s", e)
                GLib.idle_add(self._smart_card.set_placeholder_thumbnail)

        threading.Thread(target=worker, daemon=True).start()

    # ─── Download Triggers ───────────────────────────────────────────────

    def _start_smart_download(self):
        """1-Click Download using the recommended preset."""
        if not self._metadata or not self._recommendation:
            self._show_toast("No video analyzed yet.")
            return

        dest = self._settings.download_dir
        # Disk space check
        if self._recommendation.estimated_size:
            ok, free, req = check_disk_space(dest, self._recommendation.estimated_size)
            if not ok:
                self._show_toast(f"Warning: Low disk space ({format_file_size(free)} available)")

        task = DownloadTask(
            id=str(uuid.uuid4())[:8],
            url=self._metadata.webpage_url,
            title=self._metadata.title,
            uploader=self._metadata.uploader,
            thumbnail_url=self._metadata.thumbnail_url,
            quality=self._recommendation.quality,
            output_format=self._recommendation.format,
            mode=self._recommendation.mode,
            destination=dest,
        )

        self._queue.add_task(task)
        self._show_toast("Added to download queue")

        # Clear active entry and reset card to allow next paste
        self._url_row.set_text("")
        self._metadata = None
        self._recommendation = None
        self._apply_state(AppState.EMPTY)

    def _start_options_download(self):
        """Download using custom options from the options expander."""
        if not self._metadata:
            self._show_toast("No video analyzed yet.")
            return

        self._add_options_to_queue()

        # Clear and reset to allow next paste
        self._url_row.set_text("")
        self._metadata = None
        self._recommendation = None
        self._apply_state(AppState.EMPTY)

    def _add_options_to_queue(self):
        """Create and queue a task using current values from options expander."""
        if not self._metadata:
            self._show_toast("No video analyzed yet.")
            return

        quality = self._options_view.get_quality()
        mode = self._options_view.get_mode()
        out_format = self._options_view.get_format()
        clip_start, clip_end = self._options_view.get_clip_range()
        sub_lang, embed_subs = self._options_view.get_subtitles()
        dest = self._options_view.get_destination()

        task = DownloadTask(
            id=str(uuid.uuid4())[:8],
            url=self._metadata.webpage_url,
            title=self._metadata.title,
            uploader=self._metadata.uploader,
            thumbnail_url=self._metadata.thumbnail_url,
            quality=quality,
            output_format=out_format,
            mode=mode,
            destination=dest,
            clip_start=clip_start,
            clip_end=clip_end,
            subtitles_lang=sub_lang,
            embed_subtitles=embed_subs,
        )

        self._queue.add_task(task)
        self._show_toast("Added to download queue")
        self._update_empty_state_visibility()

    def _start_clip_download(self, start_str: str, end_str: str):
        """Start downloading the selected video clip."""
        if not self._metadata:
            self._show_toast("No video analyzed yet.")
            return

        quality = self._options_view.get_quality()
        mode = self._options_view.get_mode()
        out_format = self._options_view.get_format()
        sub_lang, embed_subs = self._options_view.get_subtitles()
        dest = self._options_view.get_destination()

        task = DownloadTask(
            id=str(uuid.uuid4())[:8],
            url=self._metadata.webpage_url,
            title=f"{self._metadata.title} (Clip {start_str}-{end_str})",
            uploader=self._metadata.uploader,
            thumbnail_url=self._metadata.thumbnail_url,
            quality=quality,
            output_format=out_format,
            mode=mode,
            destination=dest,
            clip_start=start_str,
            clip_end=end_str,
            subtitles_lang=sub_lang,
            embed_subtitles=embed_subs,
        )

        self._queue.add_task(task)
        self._show_toast(f"Clip ({start_str} - {end_str}) added to queue")
        self._update_empty_state_visibility()

    # ─── Folder Selection ────────────────────────────────────────────────

    def _on_folder_clicked(self, button):
        """Open modern folder chooser dialog."""
        dialog = Gtk.FileDialog(title="Select Download Folder")

        current_dir = self._settings.download_dir
        if os.path.isdir(current_dir):
            dialog.set_initial_folder(Gio.File.new_for_path(current_dir))

        dialog.select_folder(self, None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                path = folder.get_path()
                self._settings.download_dir = path
                self._options_view.set_destination(path)
                logger.info("Download directory set to: %s", path)
        except GLib.Error as e:
            if "Dismissed" not in str(e):
                logger.warning("Folder selection failed: %s", e.message)

    # ─── History Dialog ──────────────────────────────────────────────────

    def _on_show_history(self):
        """Open the Recent Downloads history dialog."""
        dialog = HistoryDialog(parent_window=self, history_service=self._history_service)
        dialog.present()

    # ─── Toasts ──────────────────────────────────────────────────────────

    def _show_toast(self, message: str, timeout: int = 5):
        """Display a transient toast notification."""
        toast = Adw.Toast.new(message)
        toast.set_timeout(timeout)
        self._toast_overlay.add_toast(toast)
