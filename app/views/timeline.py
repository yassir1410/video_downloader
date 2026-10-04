"""Interactive Video Timeline custom widget using Cairo."""

import logging
import math
from typing import Callable, Optional

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gtk

from app.utils import format_duration, format_timestamp

logger = logging.getLogger(__name__)

HANDLE_HIT_RADIUS = 12
HANDLE_WIDTH = 12
TRACK_HEIGHT = 56
PADDING_Y = 8


class TimelineWidget(Gtk.DrawingArea):
    """Custom Cairo timeline with filmstrip, draggable Start/End handles, and hover scrubber."""

    def __init__(
        self,
        duration: float = 60.0,
        on_range_changed: Optional[Callable[[float, float], None]] = None,
        on_preview_requested: Optional[Callable[[float], None]] = None,
    ):
        super().__init__()

        self.set_focusable(True)
        self.set_can_focus(True)
        self.set_content_height(TRACK_HEIGHT + PADDING_Y * 2)
        self.set_hexpand(True)

        self._duration: float = max(1.0, duration)
        self._start_time: float = 0.0
        self._end_time: float = self._duration
        self._hover_time: Optional[float] = None
        self._hover_x: Optional[float] = None

        self._zoom: float = 1.0
        self._scroll_offset: float = 0.0  # 0.0 to 1.0

        self._active_handle: Optional[str] = "start"  # "start", "end", "body"
        self._drag_start_x: float = 0.0
        self._initial_start_time: float = 0.0
        self._initial_end_time: float = 0.0

        self._filmstrip_pixbufs: list[Optional[GdkPixbuf.Pixbuf]] = []

        self._on_range_changed = on_range_changed
        self._on_preview_requested = on_preview_requested

        self.set_draw_func(self._on_draw)
        self._setup_controllers()

    def set_duration(self, duration: float) -> None:
        """Update total video duration and reset or adjust range."""
        self._duration = max(1.0, float(duration))
        self._start_time = 0.0
        self._end_time = self._duration
        self._filmstrip_pixbufs = []
        self.queue_draw()

    def set_range(self, start_sec: float, end_sec: float) -> None:
        """Set Start and End times programmatically (clamped)."""
        start = max(0.0, min(float(start_sec), self._duration - 0.5))
        end = min(self._duration, max(float(end_sec), start + 0.5))
        self._start_time = start
        self._end_time = end
        self.queue_draw()

    def get_range(self) -> tuple[float, float]:
        """Return (start_time, end_time) in seconds."""
        return self._start_time, self._end_time

    def set_filmstrip_tile(self, index: int, pixbuf: GdkPixbuf.Pixbuf, total_count: int = 8) -> None:
        """Add or update a filmstrip thumbnail tile."""
        while len(self._filmstrip_pixbufs) < total_count:
            self._filmstrip_pixbufs.append(None)
        if 0 <= index < len(self._filmstrip_pixbufs):
            self._filmstrip_pixbufs[index] = pixbuf
            self.queue_draw()

    def set_zoom(self, zoom: float) -> None:
        """Set zoom level between 1.0 and 5.0."""
        self._zoom = max(1.0, min(5.0, zoom))
        self.queue_draw()

    def get_zoom(self) -> float:
        return self._zoom

    # ─── Coordinate Conversions ──────────────────────────────────────────

    def _time_to_x(self, t: float, width: float) -> float:
        """Convert time in seconds to X pixel coordinate."""
        eff_width = width * self._zoom
        scroll_px = self._scroll_offset * max(0.0, eff_width - width)
        ratio = max(0.0, min(1.0, t / self._duration))
        return (ratio * eff_width) - scroll_px

    def _x_to_time(self, x: float, width: float) -> float:
        """Convert X pixel coordinate to time in seconds."""
        eff_width = width * self._zoom
        scroll_px = self._scroll_offset * max(0.0, eff_width - width)
        ratio = (x + scroll_px) / max(1.0, eff_width)
        return max(0.0, min(self._duration, ratio * self._duration))

    # ─── Controllers & Gestures ──────────────────────────────────────────

    def _setup_controllers(self) -> None:
        # Drag gesture
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.add_controller(drag)

        # Click gesture (for quick seeking / handle selection)
        click = Gtk.GestureClick()
        click.connect("pressed", self._on_click_pressed)
        self.add_controller(click)

        # Motion controller (for hover scrubber)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", self._on_motion_leave)
        self.add_controller(motion)

        # Key controller (for keyboard nudging)
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key)

        # Scroll controller (for zoom)
        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self._on_scroll)
        self.add_controller(scroll)

    def _on_drag_begin(self, gesture, start_x: float, start_y: float) -> None:
        self.grab_focus()
        width = self.get_width()
        start_x_coord = self._time_to_x(self._start_time, width)
        end_x_coord = self._time_to_x(self._end_time, width)

        self._drag_start_x = start_x
        self._initial_start_time = self._start_time
        self._initial_end_time = self._end_time

        # Check hits
        dist_start = abs(start_x - start_x_coord)
        dist_end = abs(start_x - end_x_coord)

        if dist_start <= HANDLE_HIT_RADIUS and dist_start <= dist_end:
            self._active_handle = "start"
        elif dist_end <= HANDLE_HIT_RADIUS:
            self._active_handle = "end"
        elif start_x_coord < start_x < end_x_coord:
            self._active_handle = "body"
        elif start_x < start_x_coord:
            self._active_handle = "start"
            self._start_time = self._x_to_time(start_x, width)
            self._notify_change()
        else:
            self._active_handle = "end"
            self._end_time = self._x_to_time(start_x, width)
            self._notify_change()

        self.queue_draw()

    def _on_drag_update(self, gesture, offset_x: float, offset_y: float) -> None:
        width = self.get_width()
        current_x = self._drag_start_x + offset_x
        new_time = self._x_to_time(current_x, width)

        if self._active_handle == "start":
            self._start_time = max(0.0, min(new_time, self._end_time - 0.5))
            if self._on_preview_requested:
                self._on_preview_requested(self._start_time)
        elif self._active_handle == "end":
            self._end_time = min(self._duration, max(new_time, self._start_time + 0.5))
            if self._on_preview_requested:
                self._on_preview_requested(self._end_time)
        elif self._active_handle == "body":
            span = self._initial_end_time - self._initial_start_time
            dt = new_time - self._x_to_time(self._drag_start_x, width)
            new_start = max(0.0, min(self._initial_start_time + dt, self._duration - span))
            self._start_time = new_start
            self._end_time = new_start + span

        self._notify_change()
        self.queue_draw()

    def _on_drag_end(self, gesture, offset_x: float, offset_y: float) -> None:
        self.queue_draw()

    def _on_click_pressed(self, gesture, n_press: int, x: float, y: float) -> None:
        self.grab_focus()
        width = self.get_width()
        clicked_time = self._x_to_time(x, width)
        dist_start = abs(clicked_time - self._start_time)
        dist_end = abs(clicked_time - self._end_time)

        if dist_start < dist_end:
            self._active_handle = "start"
        else:
            self._active_handle = "end"

        if self._on_preview_requested:
            self._on_preview_requested(clicked_time)
        self.queue_draw()

    def _on_motion(self, controller, x: float, y: float) -> None:
        width = self.get_width()
        self._hover_x = x
        self._hover_time = self._x_to_time(x, width)
        self.queue_draw()

    def _on_motion_leave(self, controller) -> None:
        self._hover_x = None
        self._hover_time = None
        self.queue_draw()

    def _on_key_pressed(self, controller, keyval: int, keycode: int, state: Gdk.ModifierType) -> bool:
        """Handle keyboard nudging (Arrow keys)."""
        is_shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        step = 5.0 if is_shift else 1.0

        if keyval in (Gdk.KEY_Left, Gdk.KEY_KP_Left):
            self.nudge_active(-step)
            return True
        elif keyval in (Gdk.KEY_Right, Gdk.KEY_KP_Right):
            self.nudge_active(step)
            return True
        elif keyval in (Gdk.KEY_Tab, Gdk.KEY_space):
            self._active_handle = "end" if self._active_handle == "start" else "start"
            self.queue_draw()
            return True

        return False

    def _on_scroll(self, controller, dx: float, dy: float) -> bool:
        """Zoom timeline using scroll wheel."""
        factor = 1.1 if dy < 0 else 0.9
        self.set_zoom(self._zoom * factor)
        return True

    def nudge_active(self, delta: float) -> None:
        """Nudge active handle by delta seconds."""
        if self._active_handle == "start":
            self._start_time = max(0.0, min(self._start_time + delta, self._end_time - 0.5))
            if self._on_preview_requested:
                self._on_preview_requested(self._start_time)
        else:
            self._end_time = min(self._duration, max(self._end_time + delta, self._start_time + 0.5))
            if self._on_preview_requested:
                self._on_preview_requested(self._end_time)

        self._notify_change()
        self.queue_draw()

    def _notify_change(self) -> None:
        if self._on_range_changed:
            self._on_range_changed(self._start_time, self._end_time)

    # ─── Drawing ─────────────────────────────────────────────────────────

    def _on_draw(self, drawing_area, cr: cairo.Context, width: int, height: int) -> None:
        """Render complete timeline with filmstrip, handles, and dimming."""
        track_y = PADDING_Y
        track_h = height - PADDING_Y * 2
        radius = 6.0

        # 1. Base track clip path (rounded rectangle)
        self._rounded_rect(cr, 0, track_y, width, track_h, radius)
        cr.save()
        cr.clip()

        # Fill background track
        cr.set_source_rgb(0.12, 0.12, 0.15)
        cr.paint()

        # 2. Render filmstrip tiles if present
        valid_tiles = [p for p in self._filmstrip_pixbufs if p is not None]
        if valid_tiles:
            tile_count = len(self._filmstrip_pixbufs)
            tile_w = width / max(1, tile_count)
            for i, pb in enumerate(self._filmstrip_pixbufs):
                if pb:
                    tx = i * tile_w
                    # Scale pixbuf to tile dimensions
                    scale_x = tile_w / pb.get_width()
                    scale_y = track_h / pb.get_height()
                    cr.save()
                    cr.translate(tx, track_y)
                    cr.scale(scale_x, scale_y)
                    Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0)
                    cr.paint()
                    cr.restore()
        else:
            # Fallback stylized audio/video wave ticks
            cr.set_source_rgba(0.25, 0.25, 0.30, 0.7)
            step_px = 16
            for x in range(0, width, step_px):
                bar_h = track_h * (0.35 + 0.25 * math.sin(x * 0.15))
                cr.rectangle(x + 6, track_y + (track_h - bar_h) / 2, 3, bar_h)
                cr.fill()

        # 3. Dim regions outside the selected range
        start_x = self._time_to_x(self._start_time, width)
        end_x = self._time_to_x(self._end_time, width)

        # Before Start
        if start_x > 0:
            cr.set_source_rgba(0.0, 0.0, 0.0, 0.68)
            cr.rectangle(0, track_y, start_x, track_h)
            cr.fill()

        # After End
        if end_x < width:
            cr.set_source_rgba(0.0, 0.0, 0.0, 0.68)
            cr.rectangle(end_x, track_y, width - end_x, track_h)
            cr.fill()

        # 4. Highlight selected region borders
        cr.set_source_rgba(0.21, 0.52, 0.89, 0.95)  # Libadwaita accent blue
        cr.set_line_width(3.0)
        cr.move_to(start_x, track_y + 1.5)
        cr.line_to(end_x, track_y + 1.5)
        cr.stroke()

        cr.move_to(start_x, track_y + track_h - 1.5)
        cr.line_to(end_x, track_y + track_h - 1.5)
        cr.stroke()

        cr.restore()  # End track clip

        # 5. Draw Draggable Handles (extended slightly outside track)
        self._draw_handle(cr, start_x, track_y, track_h, is_start=True, is_active=(self._active_handle == "start"))
        self._draw_handle(cr, end_x, track_y, track_h, is_start=False, is_active=(self._active_handle == "end"))

        # 6. Draw Hover Scrubber Line and Tooltip
        if self._hover_x is not None and self._hover_time is not None:
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.85)
            cr.set_line_width(1.5)
            cr.move_to(self._hover_x, track_y)
            cr.line_to(self._hover_x, track_y + track_h)
            cr.stroke()

            # Hover timestamp badge
            time_txt = format_timestamp(int(self._hover_time))
            self._draw_time_badge(cr, self._hover_x, track_y - 2, time_txt)

    def _draw_handle(
        self,
        cr: cairo.Context,
        x: float,
        track_y: float,
        track_h: float,
        is_start: bool,
        is_active: bool,
    ) -> None:
        """Render a modern Libadwaita-style handle."""
        hw = HANDLE_WIDTH
        hx = x - hw if is_start else x
        hy = track_y - 3
        hh = track_h + 6
        radius = 4.0

        # Handle pill background
        if is_active:
            cr.set_source_rgb(0.21, 0.52, 0.89)  # Active accent blue
        else:
            cr.set_source_rgb(0.35, 0.65, 0.98)

        self._rounded_rect(cr, hx, hy, hw, hh, radius)
        cr.fill()

        # Handle border
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.8)
        cr.set_line_width(1.0)
        self._rounded_rect(cr, hx + 0.5, hy + 0.5, hw - 1, hh - 1, radius)
        cr.stroke()

        # Grip indicators (two vertical lines)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.9)
        cr.set_line_width(1.2)
        mid_x = hx + hw / 2
        cr.move_to(mid_x - 1.5, hy + hh / 2 - 6)
        cr.line_to(mid_x - 1.5, hy + hh / 2 + 6)
        cr.move_to(mid_x + 1.5, hy + hh / 2 - 6)
        cr.line_to(mid_x + 1.5, hy + hh / 2 + 6)
        cr.stroke()

    def _draw_time_badge(self, cr: cairo.Context, x: float, y: float, text: str) -> None:
        """Draw small hover timestamp badge."""
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(10.0)
        ext = cr.text_extents(text)

        bw = ext.width + 10
        bh = ext.height + 6
        bx = max(2, min(self.get_width() - bw - 2, x - bw / 2))
        by = max(0, y - bh)

        # Background
        cr.set_source_rgba(0.1, 0.1, 0.1, 0.85)
        self._rounded_rect(cr, bx, by, bw, bh, 3.0)
        cr.fill()

        # Text
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.move_to(bx + 5, by + bh - 4)
        cr.show_text(text)

    def _rounded_rect(self, cr: cairo.Context, x: float, y: float, w: float, h: float, r: float) -> None:
        """Helper to create a rounded rectangle path."""
        r = min(r, w / 2, h / 2)
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()
