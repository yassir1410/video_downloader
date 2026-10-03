"""Main application window."""

import logging
import os
import threading
import urllib.request

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from app.downloader import DownloadCancelled, DownloadError, DownloaderService
from app.formats import FormatService
from app.metadata import MetadataError, MetadataService
from app.models import AppState, DownloadMode, DownloadProgress, VideoMetadata
from app.settings import Settings
from app.utils import (
    format_duration,
    format_eta,
    format_file_size,
    format_speed,
    is_valid_url,
    open_folder,
)

logger = logging.getLogger(__name__)


class MainWindow(Adw.ApplicationWindow):
    """Main application window for Video Downloader."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Services
        self._metadata_service = MetadataService()
        self._format_service = FormatService()
        self._downloader_service = DownloaderService()
        self._settings = Settings()

        # State
        self._state = AppState.EMPTY
        self._metadata: VideoMetadata | None = None
        self._download_filepath: str | None = None

        # Window properties
        self.set_title("Video Downloader")
        self.set_default_size(600, 680)

        # Build UI
        self._build_ui()
        self._setup_actions()
        self._apply_state(AppState.EMPTY)

    # ─── UI Construction ─────────────────────────────────────────────────

    def _build_ui(self):
        """Build the complete window layout."""
        # ToolbarView for header bar management
        toolbar_view = Adw.ToolbarView()

        # Header bar with menu
        header_bar = Adw.HeaderBar()
        menu_button = Gtk.MenuButton(
            icon_name="open-menu-symbolic",
            menu_model=self._build_menu(),
        )
        header_bar.pack_end(menu_button)
        toolbar_view.add_top_bar(header_bar)

        # Toast overlay wraps all content
        self._toast_overlay = Adw.ToastOverlay()

        # Main scrollable content
        scrolled = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            propagate_natural_height=True,
        )

        # Main vertical box
        main_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=24,
            margin_top=24,
            margin_bottom=24,
            margin_start=24,
            margin_end=24,
        )

        # ── URL Section ──────────────────────────────────────────────────
        url_group = Adw.PreferencesGroup()

        self._url_row = Adw.EntryRow(
            title="Paste video URL…",
        )
        self._url_row.connect("entry-activated", self._on_url_activated)

        # Fetch button as suffix
        self._fetch_button = Gtk.Button(
            icon_name="emblem-synchronizing-symbolic",
            valign=Gtk.Align.CENTER,
            tooltip_text="Fetch video info",
            css_classes=["flat"],
        )
        self._fetch_button.connect("clicked", self._on_fetch_clicked)
        self._url_row.add_suffix(self._fetch_button)

        url_group.add(self._url_row)
        main_box.append(url_group)

        # ── Loading Spinner ──────────────────────────────────────────────
        self._loading_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            halign=Gtk.Align.CENTER,
            margin_top=12,
            margin_bottom=12,
        )
        self._spinner = Gtk.Spinner(
            spinning=True,
            width_request=32,
            height_request=32,
            halign=Gtk.Align.CENTER,
        )
        self._loading_label = Gtk.Label(
            label="Fetching video information…",
            css_classes=["dim-label"],
        )
        self._loading_box.append(self._spinner)
        self._loading_box.append(self._loading_label)
        main_box.append(self._loading_box)

        # ── Metadata Section ─────────────────────────────────────────────
        self._metadata_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=16,
            margin_top=4,
            margin_bottom=4,
        )

        # Thumbnail
        self._thumbnail = Gtk.Picture(
            can_shrink=True,
            content_fit=Gtk.ContentFit.CONTAIN,
            width_request=200,
            height_request=112,
        )
        # Rounded corners via CSS
        self._thumbnail.add_css_class("card")
        self._metadata_box.append(self._thumbnail)

        # Info labels
        info_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4,
            valign=Gtk.Align.CENTER,
            hexpand=True,
        )
        self._title_label = Gtk.Label(
            label="",
            xalign=0,
            wrap=True,
            wrap_mode=2,  # WORD_CHAR
            max_width_chars=35,
            css_classes=["title-3"],
        )
        self._channel_label = Gtk.Label(
            label="",
            xalign=0,
            css_classes=["dim-label"],
        )
        self._duration_label = Gtk.Label(
            label="",
            xalign=0,
            css_classes=["dim-label"],
        )
        info_box.append(self._title_label)
        info_box.append(self._channel_label)
        info_box.append(self._duration_label)
        self._metadata_box.append(info_box)

        main_box.append(self._metadata_box)

        # ── Options Section ──────────────────────────────────────────────
        self._options_group = Adw.PreferencesGroup(title="Options")

        # Quality selector
        self._quality_row = Adw.ComboRow(title="Quality")
        self._quality_model = Gtk.StringList.new(["Best"])
        self._quality_row.set_model(self._quality_model)
        self._options_group.add(self._quality_row)

        # Download mode selector
        self._mode_row = Adw.ComboRow(title="Download")
        self._mode_model = Gtk.StringList.new(["Video + Audio", "Audio Only"])
        self._mode_row.set_model(self._mode_model)
        self._mode_row.connect("notify::selected", self._on_mode_changed)
        self._options_group.add(self._mode_row)

        # Format selector
        self._format_row = Adw.ComboRow(title="Format")
        self._format_model = Gtk.StringList.new(["MP4", "WebM"])
        self._format_row.set_model(self._format_model)
        self._options_group.add(self._format_row)

        # Destination folder
        self._folder_row = Adw.ActionRow(
            title="Save to",
            subtitle=self._settings.download_dir,
        )
        folder_button = Gtk.Button(
            icon_name="folder-symbolic",
            valign=Gtk.Align.CENTER,
            css_classes=["flat"],
            tooltip_text="Choose folder",
        )
        folder_button.connect("clicked", self._on_folder_clicked)
        self._folder_row.add_suffix(folder_button)
        self._folder_row.set_activatable_widget(folder_button)
        self._options_group.add(self._folder_row)

        main_box.append(self._options_group)

        # ── Progress Section ─────────────────────────────────────────────
        self._progress_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
        )
        self._progress_status_label = Gtk.Label(
            label="Downloading…",
            xalign=0,
            css_classes=["heading"],
        )
        self._progress_bar = Gtk.ProgressBar(
            show_text=True,
        )
        self._progress_detail_label = Gtk.Label(
            label="",
            xalign=0,
            css_classes=["dim-label", "caption"],
        )
        self._progress_box.append(self._progress_status_label)
        self._progress_box.append(self._progress_bar)
        self._progress_box.append(self._progress_detail_label)
        main_box.append(self._progress_box)

        # ── Empty State ──────────────────────────────────────────────────
        self._empty_status = Adw.StatusPage(
            icon_name="folder-download-symbolic",
            title="Video Downloader",
            description="Paste a video link to get started.",
        )
        self._empty_status.set_vexpand(True)
        main_box.append(self._empty_status)

        # ── Action Buttons ───────────────────────────────────────────────
        button_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
            halign=Gtk.Align.CENTER,
            margin_top=8,
        )

        self._download_button = Gtk.Button(
            label="Download",
            css_classes=["suggested-action", "pill"],
            width_request=200,
        )
        self._download_button.connect("clicked", self._on_download_clicked)
        button_box.append(self._download_button)

        self._cancel_button = Gtk.Button(
            label="Cancel",
            css_classes=["destructive-action", "pill"],
            width_request=120,
        )
        self._cancel_button.connect("clicked", self._on_cancel_clicked)
        button_box.append(self._cancel_button)

        self._open_folder_button = Gtk.Button(
            label="Open Folder",
            css_classes=["pill"],
            width_request=140,
        )
        self._open_folder_button.connect("clicked", self._on_open_folder_clicked)
        button_box.append(self._open_folder_button)

        main_box.append(button_box)

        # Assemble
        scrolled.set_child(main_box)
        self._toast_overlay.set_child(scrolled)
        toolbar_view.set_content(self._toast_overlay)
        self.set_content(toolbar_view)

    def _build_menu(self) -> Gio.Menu:
        """Build the hamburger menu."""
        menu = Gio.Menu()
        menu.append("About Video Downloader", "app.about")
        menu.append("Quit", "app.quit")
        return menu

    def _setup_actions(self):
        """Set up window-level actions."""
        # Focus URL field
        action_focus = Gio.SimpleAction.new("focus-url", None)
        action_focus.connect("activate", lambda *_: self._url_row.grab_focus())
        self.add_action(action_focus)

        # Choose folder
        action_folder = Gio.SimpleAction.new("choose-folder", None)
        action_folder.connect("activate", lambda *_: self._on_folder_clicked(None))
        self.add_action(action_folder)

    # ─── State Machine ───────────────────────────────────────────────────

    def _apply_state(self, state: AppState):
        """Apply a new application state to all widgets."""
        self._state = state
        logger.debug("State → %s", state.value)

        # Visibility map
        show_loading = state == AppState.FETCHING_METADATA
        show_metadata = state in (
            AppState.READY, AppState.DOWNLOADING, AppState.PROCESSING,
            AppState.COMPLETED,
        )
        show_options = state in (AppState.READY, AppState.COMPLETED)
        show_progress = state in (AppState.DOWNLOADING, AppState.PROCESSING)
        show_empty = state == AppState.EMPTY
        show_download = state in (AppState.READY, AppState.COMPLETED, AppState.ERROR)
        show_cancel = state in (AppState.DOWNLOADING, AppState.PROCESSING)
        show_open_folder = state == AppState.COMPLETED

        self._loading_box.set_visible(show_loading)
        self._spinner.set_spinning(show_loading)
        self._metadata_box.set_visible(show_metadata)
        self._options_group.set_visible(show_options)
        self._progress_box.set_visible(show_progress)
        self._empty_status.set_visible(show_empty)
        self._download_button.set_visible(show_download)
        self._cancel_button.set_visible(show_cancel)
        self._open_folder_button.set_visible(show_open_folder)

        # Sensitivity
        url_sensitive = state not in (AppState.DOWNLOADING, AppState.PROCESSING)
        self._url_row.set_sensitive(url_sensitive)
        self._fetch_button.set_sensitive(url_sensitive)
        self._download_button.set_sensitive(
            state in (AppState.READY, AppState.COMPLETED)
        )

    # ─── URL Handling ────────────────────────────────────────────────────

    def _on_url_activated(self, entry_row):
        """Handle Enter key in the URL field."""
        self._fetch_metadata()

    def _on_fetch_clicked(self, button):
        """Handle the fetch button click."""
        self._fetch_metadata()

    def _fetch_metadata(self):
        """Start metadata extraction in a background thread."""
        url = self._url_row.get_text().strip()

        if not is_valid_url(url):
            self._show_toast("Please enter a valid HTTP or HTTPS URL.")
            return

        self._apply_state(AppState.FETCHING_METADATA)

        thread = threading.Thread(
            target=self._fetch_metadata_worker,
            args=(url,),
            daemon=True,
        )
        thread.start()

    def _fetch_metadata_worker(self, url: str):
        """Background worker for metadata extraction."""
        try:
            metadata = self._metadata_service.extract(url)
            GLib.idle_add(self._on_metadata_success, metadata)
        except MetadataError as e:
            GLib.idle_add(self._on_metadata_error, e.user_message)
        except Exception as e:
            logger.error("Unexpected metadata error: %s", e)
            GLib.idle_add(
                self._on_metadata_error,
                "An unexpected error occurred.",
            )

    def _on_metadata_success(self, metadata: VideoMetadata):
        """Handle successful metadata extraction (main thread)."""
        self._metadata = metadata

        # Update UI with metadata
        self._title_label.set_label(metadata.title)
        self._channel_label.set_label(metadata.uploader)
        self._duration_label.set_label(format_duration(metadata.duration))

        # Load thumbnail in background
        if metadata.thumbnail_url:
            self._load_thumbnail_async(metadata.thumbnail_url)
        else:
            self._thumbnail.set_paintable(None)

        # Update quality options
        qualities = self._format_service.get_available_qualities(metadata)
        self._quality_model = Gtk.StringList.new(qualities)
        self._quality_row.set_model(self._quality_model)

        # Set default quality from settings
        default_q = self._settings.default_quality
        for i, q in enumerate(qualities):
            if q == default_q:
                self._quality_row.set_selected(i)
                break

        # Reset mode and format
        self._mode_row.set_selected(0)
        self._update_format_options()

        self._apply_state(AppState.READY)
        return GLib.SOURCE_REMOVE

    def _on_metadata_error(self, message: str):
        """Handle metadata extraction failure (main thread)."""
        self._show_toast(message)
        self._apply_state(AppState.EMPTY)
        return GLib.SOURCE_REMOVE

    # ─── Thumbnail Loading ───────────────────────────────────────────────

    def _load_thumbnail_async(self, url: str):
        """Load a thumbnail image from URL in a background thread."""

        def worker():
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw_bytes = resp.read()

                glib_bytes = GLib.Bytes.new(raw_bytes)
                texture = Gdk.Texture.new_from_bytes(glib_bytes)
                GLib.idle_add(self._set_thumbnail, texture)
            except Exception as e:
                logger.warning("Failed to load thumbnail: %s", e)
                GLib.idle_add(self._set_thumbnail, None)

        threading.Thread(target=worker, daemon=True).start()

    def _set_thumbnail(self, texture):
        """Set thumbnail paintable (main thread)."""
        self._thumbnail.set_paintable(texture)
        return GLib.SOURCE_REMOVE

    # ─── Mode / Format Selectors ─────────────────────────────────────────

    def _on_mode_changed(self, combo_row, param_spec):
        """Handle download mode change."""
        self._update_format_options()

    def _update_format_options(self):
        """Update the format dropdown based on current mode."""
        mode = self._get_selected_mode()
        formats = self._format_service.get_output_formats(mode)
        self._format_model = Gtk.StringList.new(formats)
        self._format_row.set_model(self._format_model)

    def _get_selected_mode(self) -> DownloadMode:
        """Get the currently selected download mode."""
        idx = self._mode_row.get_selected()
        if idx == 1:
            return DownloadMode.AUDIO_ONLY
        return DownloadMode.VIDEO_AUDIO

    def _get_selected_quality(self) -> str:
        """Get the currently selected quality label."""
        item = self._quality_row.get_selected_item()
        if item:
            return item.get_string()
        return "Best"

    def _get_selected_format(self) -> str:
        """Get the currently selected output format."""
        item = self._format_row.get_selected_item()
        if item:
            return item.get_string()
        return "MP4"

    # ─── Folder Selection ────────────────────────────────────────────────

    def _on_folder_clicked(self, button):
        """Open the folder chooser dialog."""
        dialog = Gtk.FileDialog(title="Select Download Folder")

        current_dir = self._settings.download_dir
        if os.path.isdir(current_dir):
            dialog.set_initial_folder(
                Gio.File.new_for_path(current_dir)
            )

        dialog.select_folder(self, None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        """Handle folder selection result."""
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                path = folder.get_path()
                self._settings.download_dir = path
                self._folder_row.set_subtitle(path)
                logger.info("Download directory set to: %s", path)
        except GLib.Error as e:
            # User cancelled — not an error
            if "Dismissed" not in str(e):
                logger.warning("Folder selection failed: %s", e.message)

    # ─── Download ────────────────────────────────────────────────────────

    def _on_download_clicked(self, button):
        """Start the download."""
        if self._metadata is None:
            self._show_toast("No video loaded. Fetch a URL first.")
            return

        url = self._metadata.webpage_url
        quality = self._get_selected_quality()
        output_format = self._get_selected_format()
        mode = self._get_selected_mode()
        destination = self._settings.download_dir

        self._apply_state(AppState.DOWNLOADING)
        self._progress_bar.set_fraction(0.0)
        self._progress_bar.set_text("0%")
        self._progress_status_label.set_label("Downloading…")
        self._progress_detail_label.set_label("Starting download…")

        thread = threading.Thread(
            target=self._download_worker,
            args=(url, quality, output_format, mode, destination),
            daemon=True,
        )
        thread.start()

    def _download_worker(self, url, quality, output_format, mode, destination):
        """Background worker for downloading."""
        try:
            filepath = self._downloader_service.download(
                url=url,
                quality=quality,
                output_format=output_format,
                mode=mode,
                destination=destination,
                progress_callback=lambda p: GLib.idle_add(
                    self._on_download_progress, p
                ),
            )
            GLib.idle_add(self._on_download_complete, filepath)

        except DownloadCancelled:
            GLib.idle_add(self._on_download_cancelled)

        except DownloadError as e:
            GLib.idle_add(self._on_download_error, e.user_message)

        except Exception as e:
            logger.error("Unexpected download error: %s", e)
            GLib.idle_add(
                self._on_download_error,
                "An unexpected error occurred during download.",
            )

    def _on_download_progress(self, progress: DownloadProgress):
        """Update progress UI (main thread)."""
        if progress.status == "downloading":
            fraction = progress.percentage / 100.0
            self._progress_bar.set_fraction(fraction)
            self._progress_bar.set_text(f"{progress.percentage:.0f}%")
            self._progress_status_label.set_label("Downloading…")

            # Build detail string
            parts = []
            if progress.total_bytes and progress.downloaded_bytes:
                parts.append(
                    f"{format_file_size(progress.downloaded_bytes)} / "
                    f"{format_file_size(progress.total_bytes)}"
                )
            elif progress.downloaded_bytes:
                parts.append(format_file_size(progress.downloaded_bytes))

            if progress.speed:
                parts.append(format_speed(progress.speed))
            if progress.eta:
                parts.append(format_eta(progress.eta))

            self._progress_detail_label.set_label(" • ".join(parts))

        elif progress.status == "processing":
            self._apply_state(AppState.PROCESSING)
            self._progress_bar.set_fraction(1.0)
            self._progress_bar.set_text("100%")
            self._progress_status_label.set_label("Processing video…")
            self._progress_detail_label.set_label(
                "Merging streams and finalizing…"
            )

        elif progress.status == "finished":
            pass  # Handled by _on_download_complete

        return GLib.SOURCE_REMOVE

    def _on_download_complete(self, filepath: str):
        """Handle download completion (main thread)."""
        self._download_filepath = filepath
        self._apply_state(AppState.COMPLETED)

        # Show success toast
        self._show_toast("Download complete!")

        # Desktop notification
        app = self.get_application()
        if app and self._metadata and self._settings.notifications_enabled:
            app.send_download_notification(self._metadata.title)

        return GLib.SOURCE_REMOVE

    def _on_download_cancelled(self):
        """Handle download cancellation (main thread)."""
        self._show_toast("Download cancelled.")
        self._apply_state(AppState.READY)
        return GLib.SOURCE_REMOVE

    def _on_download_error(self, message: str):
        """Handle download error (main thread)."""
        self._show_toast(message)
        self._apply_state(AppState.ERROR)
        # Allow retry
        self._download_button.set_sensitive(True)
        self._download_button.set_visible(True)
        return GLib.SOURCE_REMOVE

    # ─── Cancel ──────────────────────────────────────────────────────────

    def _on_cancel_clicked(self, button):
        """Cancel the active download."""
        self._downloader_service.cancel()
        self._cancel_button.set_sensitive(False)

    # ─── Open Folder ─────────────────────────────────────────────────────

    def _on_open_folder_clicked(self, button):
        """Open the download destination folder."""
        if self._download_filepath:
            folder = os.path.dirname(self._download_filepath)
        else:
            folder = self._settings.download_dir
        open_folder(folder)

    # ─── Toasts ──────────────────────────────────────────────────────────

    def _show_toast(self, message: str, timeout: int = 5):
        """Show a transient toast notification."""
        toast = Adw.Toast.new(message)
        toast.set_timeout(timeout)
        self._toast_overlay.add_toast(toast)
