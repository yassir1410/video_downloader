"""Recent downloads history dialog."""

import logging
import os
from typing import Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, Gtk, Pango

from app.history import HistoryService
from app.models import HistoryItem
from app.utils import format_file_size, open_file, open_folder

logger = logging.getLogger(__name__)


class HistoryRow(Gtk.ListBoxRow):
    """Row displaying a single history entry with actions."""

    def __init__(self, item: HistoryItem, history_service: HistoryService, on_removed):
        super().__init__()
        self.item = item
        self._history_service = history_service
        self._on_removed = on_removed

        self.set_activatable(False)
        self.set_selectable(False)
        self._build_ui()

    def _build_ui(self) -> None:
        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
            margin_start=12,
            margin_end=12,
            margin_top=10,
            margin_bottom=10,
            valign=Gtk.Align.CENTER,
        )

        # Provider / format icon
        icon = Gtk.Image(
            icon_name="video-x-generic-symbolic",
            pixel_size=20,
        )
        box.append(icon)

        # Info Box
        info = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=3,
            hexpand=True,
        )

        title = Gtk.Label(
            label=self.item.title or "Untitled Video",
            xalign=0,
            ellipsize=Pango.EllipsizeMode.END,
            max_width_chars=36,
            css_classes=["heading"],
        )
        info.append(title)

        parts = [self.item.date]
        if self.item.quality:
            parts.append(self.item.quality)
        if self.item.output_format:
            parts.append(self.item.output_format)
        if self.item.filesize:
            parts.append(format_file_size(self.item.filesize))

        meta = Gtk.Label(
            label=" • ".join(parts),
            xalign=0,
            css_classes=["dim-label", "caption"],
        )
        info.append(meta)
        box.append(info)

        # Action Buttons
        btn_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=4,
            valign=Gtk.Align.CENTER,
        )

        exists = bool(self.item.filepath and os.path.exists(self.item.filepath))

        if exists:
            btn_open = Gtk.Button(
                icon_name="document-open-symbolic",
                tooltip_text="Open file",
                css_classes=["flat", "circular"],
            )
            btn_open.connect("clicked", lambda *_: open_file(self.item.filepath))
            btn_box.append(btn_open)

            folder = os.path.dirname(self.item.filepath)
            btn_folder = Gtk.Button(
                icon_name="folder-symbolic",
                tooltip_text="Show in folder",
                css_classes=["flat", "circular"],
            )
            btn_folder.connect("clicked", lambda *_: open_folder(folder))
            btn_box.append(btn_folder)
        else:
            lbl_missing = Gtk.Label(
                label="Moved",
                css_classes=["dim-label", "caption"],
                margin_end=4,
            )
            btn_box.append(lbl_missing)

        btn_del = Gtk.Button(
            icon_name="user-trash-symbolic",
            tooltip_text="Remove from history",
            css_classes=["flat", "circular"],
        )
        btn_del.connect("clicked", self._on_delete_clicked)
        btn_box.append(btn_del)

        box.append(btn_box)
        self.set_child(box)

    def _on_delete_clicked(self, button: Gtk.Button) -> None:
        self._history_service.remove_item(self.item.id)
        if self._on_removed:
            self._on_removed(self)


class HistoryDialog(Adw.Window):
    """Window dialog presenting download history."""

    def __init__(self, parent_window: Gtk.Window, history_service: Optional[HistoryService] = None):
        super().__init__(
            title="Download History",
            transient_for=parent_window,
            modal=True,
            default_width=520,
            default_height=580,
        )

        self._history_service = history_service or HistoryService()

        self._build_ui()
        self._load_items()

    def _build_ui(self) -> None:
        toolbar_view = Adw.ToolbarView()

        # HeaderBar
        header_bar = Adw.HeaderBar()
        self._clear_btn = Gtk.Button(
            label="Clear All",
            css_classes=["destructive-action", "flat"],
        )
        self._clear_btn.connect("clicked", self._on_clear_all)
        header_bar.pack_start(self._clear_btn)
        toolbar_view.add_top_bar(header_bar)

        # Main content stack
        self._stack = Gtk.Stack()

        # 1. Empty state
        self._empty_page = Adw.StatusPage(
            icon_name="document-open-recent-symbolic",
            title="No Download History",
            description="Videos you download will appear here.",
        )
        self._stack.add_named(self._empty_page, "empty")

        # 2. History list
        scrolled = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
        )
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_start=16,
            margin_end=16,
            margin_top=16,
            margin_bottom=16,
        )

        self._list_box = Gtk.ListBox(
            css_classes=["boxed-list"],
            selection_mode=Gtk.SelectionMode.NONE,
        )
        box.append(self._list_box)
        scrolled.set_child(box)
        self._stack.add_named(scrolled, "list")

        toolbar_view.set_content(self._stack)
        self.set_content(toolbar_view)

    def _load_items(self) -> None:
        # Clear list
        while (child := self._list_box.get_first_child()) is not None:
            self._list_box.remove(child)

        items = self._history_service.get_items()

        if not items:
            self._stack.set_visible_child_name("empty")
            self._clear_btn.set_sensitive(False)
            return

        self._stack.set_visible_child_name("list")
        self._clear_btn.set_sensitive(True)

        for item in items:
            row = HistoryRow(item, self._history_service, on_removed=self._on_row_removed)
            self._list_box.append(row)

    def _on_row_removed(self, row: HistoryRow) -> None:
        self._list_box.remove(row)
        if self._list_box.get_first_child() is None:
            self._stack.set_visible_child_name("empty")
            self._clear_btn.set_sensitive(False)

    def _on_clear_all(self, button: Gtk.Button) -> None:
        self._history_service.clear_history()
        self._load_items()
