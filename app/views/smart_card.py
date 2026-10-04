"""Smart Download Hero Card view."""

import logging
import os
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, Gtk, Pango

from app.models import SmartRecommendation, VideoMetadata
from app.utils import format_duration

logger = logging.getLogger(__name__)


class SmartCardView(Gtk.Box):
    """Hero card displaying video info, recommended preset, and one-click download."""

    def __init__(
        self,
        on_download: Optional[Callable[[], None]] = None,
        on_toggle_options: Optional[Callable[[bool], None]] = None,
    ):
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
            css_classes=["card"],
        )

        self._on_download = on_download
        self._on_toggle_options = on_toggle_options
        self._metadata: Optional[VideoMetadata] = None
        self._recommendation: Optional[SmartRecommendation] = None

        self._build_ui()

    def _build_ui(self) -> None:
        """Construct the smart hero card UI."""
        # ── Top Section: Preview & Meta ──────────────────────────────────────
        top_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=16,
            margin_top=16,
            margin_bottom=14,
            margin_start=16,
            margin_end=16,
        )

        # Thumbnail
        self._thumbnail = Gtk.Picture(
            can_shrink=True,
            content_fit=Gtk.ContentFit.COVER,
            width_request=180,
            height_request=104,
            css_classes=["card"],
        )
        top_box.append(self._thumbnail)

        # Info Box
        info_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4,
            valign=Gtk.Align.CENTER,
            hexpand=True,
        )

        self._provider_badge = Gtk.Label(
            label="",
            xalign=0,
            css_classes=["dim-label", "caption"],
        )

        self._title_label = Gtk.Label(
            label="",
            xalign=0,
            wrap=True,
            wrap_mode=Pango.WrapMode.WORD_CHAR,
            max_width_chars=34,
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
            css_classes=["dim-label", "caption"],
        )

        info_box.append(self._provider_badge)
        info_box.append(self._title_label)
        info_box.append(self._channel_label)
        info_box.append(self._duration_label)
        top_box.append(info_box)

        self.append(top_box)

        # ── Divider ─────────────────────────────────────────────────────────
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(sep)

        # ── Bottom Section: Recommendation Pill + One-click Download ────────
        bottom_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
            margin_top=12,
            margin_bottom=14,
            margin_start=16,
            margin_end=16,
            valign=Gtk.Align.CENTER,
        )

        # Recommendation badge box
        rec_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
            hexpand=True,
            valign=Gtk.Align.CENTER,
        )

        rec_caption = Gtk.Label(
            label="RECOMMENDED",
            xalign=0,
            css_classes=["dim-label", "caption"],
        )
        self._recommendation_label = Gtk.Label(
            label="1080p · MP4",
            xalign=0,
            css_classes=["heading"],
        )
        rec_box.append(rec_caption)
        rec_box.append(self._recommendation_label)
        bottom_box.append(rec_box)

        # Download primary pill button
        self._download_button = Gtk.Button(
            label="Download",
            css_classes=["suggested-action", "pill"],
            width_request=140,
            valign=Gtk.Align.CENTER,
        )
        self._download_button.connect("clicked", self._on_download_clicked)
        bottom_box.append(self._download_button)

        # Options toggle button
        self._options_toggle = Gtk.ToggleButton(
            icon_name="view-more-symbolic",
            tooltip_text="More Options",
            css_classes=["flat", "circular"],
            valign=Gtk.Align.CENTER,
        )
        self._options_toggle.connect("toggled", self._on_options_toggled)
        bottom_box.append(self._options_toggle)

        self.append(bottom_box)

    def set_metadata(
        self,
        metadata: VideoMetadata,
        recommendation: Optional[SmartRecommendation] = None,
    ) -> None:
        """Update card with video metadata and smart recommendation."""
        self._metadata = metadata
        self._recommendation = recommendation

        provider_name = (
            metadata.provider.value
            if hasattr(metadata, "provider") and metadata.provider
            else "Video"
        )
        self._provider_badge.set_label(f"● {provider_name.upper()}")

        self._title_label.set_label(metadata.title or "Untitled Video")

        if metadata.uploader:
            self._channel_label.set_label(metadata.uploader)
            self._channel_label.set_visible(True)
        else:
            self._channel_label.set_visible(False)

        if metadata.duration and metadata.duration > 0:
            self._duration_label.set_label(format_duration(metadata.duration))
            self._duration_label.set_visible(True)
        else:
            self._duration_label.set_visible(False)

        if recommendation:
            self._recommendation_label.set_label(recommendation.label)
        else:
            self._recommendation_label.set_label("Best Available")

    def set_thumbnail(self, texture: Gdk.Texture) -> None:
        """Set the thumbnail image texture."""
        self._thumbnail.set_paintable(texture)

    def set_placeholder_thumbnail(self) -> None:
        """Set the placeholder thumbnail image."""
        placeholder = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "assets",
            "placeholder.svg",
        )
        if os.path.exists(placeholder):
            self._thumbnail.set_filename(placeholder)
        else:
            self._thumbnail.set_paintable(None)

    def set_download_enabled(self, enabled: bool) -> None:
        """Set sensitivity of the Download button."""
        self._download_button.set_sensitive(enabled)

    def set_options_expanded(self, expanded: bool) -> None:
        """Sync toggle button state with options expander."""
        if self._options_toggle.get_active() != expanded:
            self._options_toggle.set_active(expanded)

    def _on_download_clicked(self, button: Gtk.Button) -> None:
        if self._on_download:
            self._on_download()

    def _on_options_toggled(self, button: Gtk.ToggleButton) -> None:
        if self._on_toggle_options:
            self._on_toggle_options(button.get_active())
