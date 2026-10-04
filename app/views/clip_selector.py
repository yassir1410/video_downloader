"""Interactive visual video clip selector with frame preview and timeline."""

import logging
import os
import urllib.request
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk

from app.models import VideoMetadata
from app.thumbnail_service import ThumbnailService
from app.utils import format_duration, format_timestamp, parse_timestamp
from app.views.timeline import TimelineWidget

logger = logging.getLogger(__name__)


class ClipSelectorView(Gtk.Box):
    """Complete visual video trimming panel with live frame preview, timeline, and controls."""

    def __init__(
        self,
        on_download_clip: Optional[Callable[[str, str], None]] = None,
        thumbnail_service: Optional[ThumbnailService] = None,
    ):
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16,
            margin_top=8,
            margin_bottom=8,
        )

        self._on_download_clip = on_download_clip
        self._thumbnail_service = thumbnail_service or ThumbnailService()
        self._metadata: Optional[VideoMetadata] = None
        self._updating_inputs: bool = False

        self._build_ui()

    def _build_ui(self) -> None:
        """Construct the visual trimmer UI layout."""
        # ── 1. Top Section: Frame Preview & Current Time ─────────────────────
        preview_container = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            halign=Gtk.Align.CENTER,
            margin_top=4,
        )

        # Frame Preview Box (Frame + Spinner)
        self._frame_overlay = Gtk.Overlay()

        self._preview_picture = Gtk.Picture(
            can_shrink=True,
            content_fit=Gtk.ContentFit.COVER,
            width_request=240,
            height_request=135,
            css_classes=["card"],
        )
        self._frame_overlay.set_child(self._preview_picture)

        self._preview_spinner = Gtk.Spinner(
            spinning=False,
            width_request=32,
            height_request=32,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            visible=False,
        )
        self._frame_overlay.add_overlay(self._preview_spinner)
        preview_container.append(self._frame_overlay)

        # Current preview timestamp label
        self._current_time_label = Gtk.Label(
            label="00:00:00",
            css_classes=["title-4"],
        )
        preview_container.append(self._current_time_label)

        self.append(preview_container)

        # ── 2. Middle Section: Timeline & Boundary Labels ────────────────────
        timeline_container = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4,
            hexpand=True,
        )

        # Header boundary timestamps (00:00 on left, total duration on right)
        bounds_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            hexpand=True,
        )
        self._lbl_start_bound = Gtk.Label(
            label="00:00",
            xalign=0,
            hexpand=True,
            css_classes=["dim-label", "caption"],
        )
        self._lbl_end_bound = Gtk.Label(
            label="00:00",
            xalign=1,
            css_classes=["dim-label", "caption"],
        )
        bounds_box.append(self._lbl_start_bound)
        bounds_box.append(self._lbl_end_bound)
        timeline_container.append(bounds_box)

        # Cairo Timeline Widget
        self._timeline = TimelineWidget(
            duration=60.0,
            on_range_changed=self._on_timeline_range_changed,
            on_preview_requested=self._on_preview_requested,
        )
        timeline_container.append(self._timeline)

        # Handle position readouts below timeline
        handle_labels_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            hexpand=True,
            margin_top=2,
        )
        self._lbl_handle_start = Gtk.Label(
            label="Start: 00:00:00",
            xalign=0,
            hexpand=True,
            css_classes=["caption"],
        )
        self._lbl_handle_end = Gtk.Label(
            label="End: 00:00:00",
            xalign=1,
            css_classes=["caption"],
        )
        handle_labels_box.append(self._lbl_handle_start)
        handle_labels_box.append(self._lbl_handle_end)
        timeline_container.append(handle_labels_box)

        self.append(timeline_container)

        # ── 3. Bottom Section: Controls, Manual Inputs, & Download Button ────
        controls_group = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_top=4,
        )

        # Duration & Zoom Row
        dur_zoom_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
            valign=Gtk.Align.CENTER,
        )

        # Duration pill badge
        self._duration_badge = Gtk.Label(
            label="Selected Clip: 00:00",
            xalign=0,
            hexpand=True,
            css_classes=["heading"],
        )
        dur_zoom_row.append(self._duration_badge)

        # Zoom Controls
        zoom_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=4,
            css_classes=["linked"],
        )
        btn_zoom_out = Gtk.Button(
            icon_name="zoom-out-symbolic",
            tooltip_text="Zoom Out",
            css_classes=["flat"],
        )
        btn_zoom_out.connect("clicked", lambda *_: self._zoom_by(0.8))
        zoom_box.append(btn_zoom_out)

        btn_zoom_reset = Gtk.Button(
            label="1x",
            tooltip_text="Reset Zoom",
            css_classes=["flat"],
        )
        btn_zoom_reset.connect("clicked", lambda *_: self._timeline.set_zoom(1.0))
        zoom_box.append(btn_zoom_reset)

        btn_zoom_in = Gtk.Button(
            icon_name="zoom-in-symbolic",
            tooltip_text="Zoom In",
            css_classes=["flat"],
        )
        btn_zoom_in.connect("clicked", lambda *_: self._zoom_by(1.25))
        zoom_box.append(btn_zoom_in)

        dur_zoom_row.append(zoom_box)
        controls_group.append(dur_zoom_row)

        # Manual Entry Rows (Start & End with steppers)
        entries_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=16,
            homogeneous=True,
        )

        # Start Entry Box
        start_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_s = Gtk.Label(label="Start Time", xalign=0, css_classes=["dim-label", "caption"])
        start_input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._entry_start = Gtk.Entry(text="00:00:00", hexpand=True)
        self._entry_start.connect("changed", self._on_manual_start_changed)

        btn_start_minus = Gtk.Button(label="-1s", css_classes=["flat"])
        btn_start_minus.connect("clicked", lambda *_: self._step_start(-1))
        btn_start_plus = Gtk.Button(label="+1s", css_classes=["flat"])
        btn_start_plus.connect("clicked", lambda *_: self._step_start(1))

        start_input_box.append(self._entry_start)
        start_input_box.append(btn_start_minus)
        start_input_box.append(btn_start_plus)
        start_box.append(lbl_s)
        start_box.append(start_input_box)
        entries_box.append(start_box)

        # End Entry Box
        end_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_e = Gtk.Label(label="End Time", xalign=0, css_classes=["dim-label", "caption"])
        end_input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._entry_end = Gtk.Entry(text="00:00:00", hexpand=True)
        self._entry_end.connect("changed", self._on_manual_end_changed)

        btn_end_minus = Gtk.Button(label="-1s", css_classes=["flat"])
        btn_end_minus.connect("clicked", lambda *_: self._step_end(-1))
        btn_end_plus = Gtk.Button(label="+1s", css_classes=["flat"])
        btn_end_plus.connect("clicked", lambda *_: self._step_end(1))

        end_input_box.append(self._entry_end)
        end_input_box.append(btn_end_minus)
        end_input_box.append(btn_end_plus)
        end_box.append(lbl_e)
        end_box.append(end_input_box)
        entries_box.append(end_box)

        controls_group.append(entries_box)

        # Download Selected Clip Button
        btn_dl_clip = Gtk.Button(
            label="Download Selected Clip",
            css_classes=["suggested-action", "pill"],
            halign=Gtk.Align.CENTER,
            width_request=220,
            margin_top=8,
        )
        btn_dl_clip.connect("clicked", self._on_download_clip_clicked)
        controls_group.append(btn_dl_clip)

        self.append(controls_group)

    def set_metadata(self, metadata: VideoMetadata) -> None:
        """Initialize clip selector with video metadata and start async thumbnail extraction."""
        self._metadata = metadata
        duration = float(metadata.duration or 60)

        self._lbl_start_bound.set_label("00:00")
        self._lbl_end_bound.set_label(format_duration(int(duration)))

        self._timeline.set_duration(duration)
        self._timeline.set_range(0.0, duration)

        self._update_readouts(0.0, duration)

        # Initial frame preview: use main thumbnail
        if metadata.thumbnail_url:
            self._load_initial_thumbnail(metadata.thumbnail_url)
        else:
            self._preview_picture.set_paintable(None)

        # Generate filmstrip asynchronously
        self._thumbnail_service.generate_filmstrip(
            metadata=metadata,
            count=8,
            on_thumbnail_ready=self._on_filmstrip_tile_ready,
        )

    def _load_initial_thumbnail(self, url: str) -> None:
        def worker():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw_bytes = resp.read()
                glib_bytes = GLib.Bytes.new(raw_bytes)
                texture = Gdk.Texture.new_from_bytes(glib_bytes)
                GLib.idle_add(self._preview_picture.set_paintable, texture)
            except Exception as e:
                logger.debug("Failed to load initial preview thumbnail: %s", e)

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _on_filmstrip_tile_ready(self, index: int, timestamp: float, texture: Gdk.Texture) -> None:
        """Handle filmstrip thumbnail tile arrival."""
        # Convert texture to GdkPixbuf for Cairo drawing
        try:
            bytes_data = texture.save_to_png_bytes()
            loader = GdkPixbuf.PixbufLoader.new_with_type("png")
            loader.write(bytes_data.get_data())
            loader.close()
            pixbuf = loader.get_pixbuf()
            self._timeline.set_filmstrip_tile(index, pixbuf, total_count=8)
        except Exception as e:
            logger.debug("Could not process filmstrip tile %s: %s", index, e)

    def _on_timeline_range_changed(self, start_sec: float, end_sec: float) -> None:
        """Synchronize manual inputs and duration badge with timeline drag."""
        self._update_readouts(start_sec, end_sec)

    def _on_preview_requested(self, timestamp: float) -> None:
        """Handle frame preview request when seeking or dragging handles."""
        self._current_time_label.set_label(format_timestamp(int(timestamp)))
        if not self._metadata:
            return

        self._preview_spinner.set_visible(True)
        self._preview_spinner.set_spinning(True)

        def on_frame(ts: float, texture: Optional[Gdk.Texture]):
            self._preview_spinner.set_spinning(False)
            self._preview_spinner.set_visible(False)
            if texture:
                self._preview_picture.set_paintable(texture)

        self._thumbnail_service.request_frame_preview(self._metadata, timestamp, on_frame)

    def _update_readouts(self, start_sec: float, end_sec: float) -> None:
        """Update time badges and text entries."""
        start_str = format_timestamp(int(start_sec))
        end_str = format_timestamp(int(end_sec))
        clip_dur = max(0, int(end_sec - start_sec))

        self._lbl_handle_start.set_label(f"Start: {start_str}")
        self._lbl_handle_end.set_label(f"End: {end_str}")
        self._duration_badge.set_label(f"Selected Clip: {format_duration(clip_dur)}")

        self._updating_inputs = True
        try:
            self._entry_start.set_text(start_str)
            self._entry_end.set_text(end_str)
        finally:
            self._updating_inputs = False

    def _on_manual_start_changed(self, entry: Gtk.Entry) -> None:
        if self._updating_inputs or not self._metadata:
            return
        txt = entry.get_text().strip()
        sec = parse_timestamp(txt)
        if sec is not None:
            _, cur_end = self._timeline.get_range()
            if sec < cur_end:
                self._timeline.set_range(sec, cur_end)
                self._on_preview_requested(sec)

    def _on_manual_end_changed(self, entry: Gtk.Entry) -> None:
        if self._updating_inputs or not self._metadata:
            return
        txt = entry.get_text().strip()
        sec = parse_timestamp(txt)
        if sec is not None:
            cur_start, _ = self._timeline.get_range()
            if sec > cur_start:
                self._timeline.set_range(cur_start, sec)
                self._on_preview_requested(sec)

    def _step_start(self, delta: int) -> None:
        start, end = self._timeline.get_range()
        new_start = max(0, min(start + delta, end - 1))
        self._timeline.set_range(new_start, end)
        self._update_readouts(new_start, end)
        self._on_preview_requested(new_start)

    def _step_end(self, delta: int) -> None:
        start, end = self._timeline.get_range()
        max_dur = float(self._metadata.duration or end) if self._metadata else end
        new_end = min(max_dur, max(end + delta, start + 1))
        self._timeline.set_range(start, new_end)
        self._update_readouts(start, new_end)
        self._on_preview_requested(new_end)

    def _zoom_by(self, factor: float) -> None:
        cur = self._timeline.get_zoom()
        self._timeline.set_zoom(cur * factor)

    def _on_download_clip_clicked(self, button: Gtk.Button) -> None:
        start_str, end_str = self.get_clip_range()
        if self._on_download_clip and start_str and end_str:
            self._on_download_clip(start_str, end_str)

    def get_clip_range(self) -> tuple[Optional[str], Optional[str]]:
        """Return (start_timestamp_str, end_timestamp_str) or (None, None) if full video."""
        if not self._metadata or not self._metadata.duration:
            return None, None
        start, end = self._timeline.get_range()
        total = float(self._metadata.duration)
        if start <= 0.5 and end >= total - 0.5:
            return None, None
        return format_timestamp(int(start)), format_timestamp(int(end))
