"""Video Downloader GTK Application."""

import logging
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")

from gi.repository import Adw, Gio, GLib, Gtk

from app import __app_id__, __version__

logger = logging.getLogger(__name__)


class VideoDownloaderApplication(Adw.Application):
    """Main application class for Video Downloader."""

    def __init__(self):
        super().__init__(
            application_id=__app_id__,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._window = None

    def do_activate(self):
        """Called when the application is activated."""
        win = self.props.active_window
        if not win:
            from app.window import MainWindow

            win = MainWindow(application=self)

        self._window = win
        win.present()

    def do_startup(self):
        """Called when the application starts."""
        Adw.Application.do_startup(self)
        self._setup_icon_theme()
        self._setup_actions()
        self._setup_shortcuts()

    def _setup_icon_theme(self):
        """Add local assets directory to GTK icon theme search paths."""
        try:
            from pathlib import Path
            from gi.repository import Gdk
            display = Gdk.Display.get_default()
            if display:
                icon_theme = Gtk.IconTheme.get_for_display(display)
                assets_dir = str(Path(__file__).resolve().parent.parent / "assets")
                icon_theme.add_search_path(assets_dir)
                logger.debug("Added icon search path: %s", assets_dir)
        except Exception as e:
            logger.warning("Could not setup icon theme: %s", e)

    def _setup_actions(self):
        """Register application-level actions."""
        # Quit action
        action_quit = Gio.SimpleAction.new("quit", None)
        action_quit.connect("activate", self._on_quit)
        self.add_action(action_quit)

        # About action
        action_about = Gio.SimpleAction.new("about", None)
        action_about.connect("activate", self._on_about)
        self.add_action(action_about)

    def _setup_shortcuts(self):
        """Set up keyboard shortcuts."""
        self.set_accels_for_action("app.quit", ["<Control>q"])
        self.set_accels_for_action("win.focus-url", ["<Control>l"])
        self.set_accels_for_action("win.choose-folder", ["<Control>o"])
        self.set_accels_for_action("win.smart-download", ["<Control><Shift>d"])
        self.set_accels_for_action("win.show-history", ["<Control>h"])

    def _on_quit(self, action, param):
        """Handle quit action."""
        logger.info("Quit requested")
        self.quit()

    def _on_about(self, action, param):
        """Show the About dialog."""
        about = Adw.AboutDialog(
            application_name="Video Downloader",
            application_icon=__app_id__,
            version=__version__,
            developer_name="",
            developers=[""],
            copyright="",
            license_type=Gtk.License.GPL_3_0,
            comments=(
                "A fast, native, minimalist video downloader "
                "for Fedora, powered by yt-dlp."
            ),
            website="",
            issue_url="",
        )
        about.add_legal_section(
            "Disclaimer",
            None,
            Gtk.License.CUSTOM,
            (
                "This application is intended for downloading content that "
                "the user has permission to download. Users are responsible "
                "for complying with applicable copyright laws and the terms "
                "of the services they use."
            ),
        )
        about.present(self._window)

    def send_download_notification(self, video_title: str) -> None:
        """Send a desktop notification when a download completes."""
        notification = Gio.Notification.new("Download Complete")
        notification.set_body(
            f'"{video_title}" has finished downloading.'
        )
        notification.set_icon(
            Gio.ThemedIcon.new("folder-download-symbolic")
        )
        notification.set_priority(Gio.NotificationPriority.NORMAL)

        self.send_notification(
            f"download-{hash(video_title)}", notification
        )
