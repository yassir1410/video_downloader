"""Advanced options view for format, quality, clipping, subtitles, and destination."""

import logging
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from app.formats import FormatService
from app.models import DownloadMode, SmartRecommendation, VideoMetadata
from app.subtitles import SubtitleService
from app.utils import parse_timestamp

logger = logging.getLogger(__name__)


class OptionsExpanderView(Gtk.Box):
    """Collapsible advanced settings panel."""

    def __init__(
        self,
        default_dir: str,
        on_download_with_options: Optional[Callable[[], None]] = None,
        on_add_to_queue: Optional[Callable[[], None]] = None,
        on_choose_folder: Optional[Callable[[], None]] = None,
    ):
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16,
        )

        self._format_service = FormatService()
        self._subtitle_service = SubtitleService()
        self._destination_dir = default_dir

        self._on_download_with_options = on_download_with_options
        self._on_add_to_queue = on_add_to_queue
        self._on_choose_folder = on_choose_folder

        self._quality_codes: list[str] = ["Best"]
        self._subtitle_codes: list[str] = ["none"]
        self._metadata: Optional[VideoMetadata] = None

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the options preferences group."""
        group = Adw.PreferencesGroup(
            title="Options",
            description="Customize quality, formats, clip sections, and subtitles",
        )

        # ── Quality ─────────────────────────────────────────────────────────
        self._quality_row = Adw.ComboRow(title="Quality")
        self._quality_model = Gtk.StringList.new(["Best"])
        self._quality_row.set_model(self._quality_model)
        group.add(self._quality_row)

        # ── Mode ────────────────────────────────────────────────────────────
        self._mode_row = Adw.ComboRow(title="Download Mode")
        self._mode_model = Gtk.StringList.new(["Video + Audio", "Audio Only"])
        self._mode_row.set_model(self._mode_model)
        self._mode_row.connect("notify::selected", self._on_mode_changed)
        group.add(self._mode_row)

        # ── Format ──────────────────────────────────────────────────────────
        self._format_row = Adw.ComboRow(title="Output Format")
        self._format_model = Gtk.StringList.new(["MP4", "WebM"])
        self._format_row.set_model(self._format_model)
        group.add(self._format_row)

        # ── Video Clipping Expander ─────────────────────────────────────────
        self._clip_expander = Adw.ExpanderRow(
            title="Clip Video (Optional)",
            subtitle="Download a specific section of the video",
        )
        self._clip_start_row = Adw.EntryRow(
            title="Start Time",
        )
        self._clip_start_row.set_text("")
        self._clip_end_row = Adw.EntryRow(
            title="End Time",
        )
        self._clip_end_row.set_text("")
        self._clip_expander.add_row(self._clip_start_row)
        self._clip_expander.add_row(self._clip_end_row)
        group.add(self._clip_expander)

        # ── Subtitles Expander ──────────────────────────────────────────────
        self._subtitles_expander = Adw.ExpanderRow(
            title="Subtitles",
            subtitle="Download or embed closed captions",
        )
        self._subtitles_row = Adw.ComboRow(title="Subtitle Language")
        self._subtitles_model = Gtk.StringList.new(["None"])
        self._subtitles_row.set_model(self._subtitles_model)
        self._subtitles_row.connect("notify::selected", self._on_subtitles_changed)
        self._subtitles_expander.add_row(self._subtitles_row)

        self._embed_subs_row = Adw.SwitchRow(
            title="Embed Subtitles in Video",
            subtitle="Burn subtitles into the output container (MKV/MP4)",
        )
        self._embed_subs_row.set_active(True)
        self._embed_subs_row.set_sensitive(False)  # only when subtitle chosen
        self._subtitles_expander.add_row(self._embed_subs_row)
        group.add(self._subtitles_expander)

        # ── Destination Folder ──────────────────────────────────────────────
        self._folder_row = Adw.ActionRow(
            title="Save to",
            subtitle=self._destination_dir,
        )
        folder_button = Gtk.Button(
            icon_name="folder-symbolic",
            valign=Gtk.Align.CENTER,
            css_classes=["flat"],
            tooltip_text="Choose folder",
        )
        folder_button.connect("clicked", lambda *_: self._on_choose_folder_clicked())
        self._folder_row.add_suffix(folder_button)
        self._folder_row.set_activatable_widget(folder_button)
        group.add(self._folder_row)

        self.append(group)

        # ── Action Buttons for Options ──────────────────────────────────────
        actions_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
            halign=Gtk.Align.END,
            margin_top=4,
        )

        self._queue_button = Gtk.Button(
            label="Add to Queue",
            css_classes=["pill"],
        )
        self._queue_button.connect("clicked", self._on_queue_clicked)
        actions_box.append(self._queue_button)

        self._download_custom_button = Gtk.Button(
            label="Download with Options",
            css_classes=["suggested-action", "pill"],
        )
        self._download_custom_button.connect("clicked", self._on_download_custom_clicked)
        actions_box.append(self._download_custom_button)

        self.append(actions_box)

    def populate(
        self,
        metadata: VideoMetadata,
        recommendation: Optional[SmartRecommendation] = None,
        default_quality_pref: str = "Best",
    ) -> None:
        """Populate options with metadata details and available options."""
        self._metadata = metadata

        # 1. Qualities with estimated sizes
        details = self._format_service.get_available_qualities_with_details(metadata)
        self._quality_codes = [q for q, _ in details]
        labels = [lbl for _, lbl in details]
        self._quality_model = Gtk.StringList.new(labels)
        self._quality_row.set_model(self._quality_model)

        # Select recommendation or preference
        selected_target = recommendation.quality if recommendation else default_quality_pref
        selected_idx = 0
        for i, q in enumerate(self._quality_codes):
            if q == selected_target:
                selected_idx = i
                break
        self._quality_row.set_selected(selected_idx)

        # 2. Reset mode to Video + Audio
        self._mode_row.set_selected(0)
        self._update_format_options()

        # 3. Reset clipping
        self._clip_start_row.set_text("")
        self._clip_end_row.set_text("")
        self._clip_expander.set_enable_expansion(True)
        self._clip_expander.set_expanded(False)

        # 4. Populate subtitles
        subs = self._subtitle_service.get_available_subtitles(metadata)
        self._subtitle_codes = ["none"]
        sub_labels = ["None"]
        for code, disp, _ in subs:
            self._subtitle_codes.append(code)
            sub_labels.append(disp)

        self._subtitles_model = Gtk.StringList.new(sub_labels)
        self._subtitles_row.set_model(self._subtitles_model)
        self._subtitles_row.set_selected(0)
        self._embed_subs_row.set_sensitive(False)
        self._subtitles_expander.set_expanded(False)

    def _on_mode_changed(self, combo_row, param_spec) -> None:
        """Update formats and subtitle compatibility when mode changes."""
        self._update_format_options()
        mode = self.get_mode()
        is_video = mode == DownloadMode.VIDEO_AUDIO
        self._subtitles_expander.set_visible(is_video)
        self._quality_row.set_sensitive(is_video)

    def _update_format_options(self) -> None:
        mode = self.get_mode()
        formats = self._format_service.get_output_formats(mode)
        self._format_model = Gtk.StringList.new(formats)
        self._format_row.set_model(self._format_model)
        self._format_row.set_selected(0)

    def _on_subtitles_changed(self, combo_row, param_spec) -> None:
        idx = self._subtitles_row.get_selected()
        has_sub = idx > 0
        self._embed_subs_row.set_sensitive(has_sub and self.get_mode() == DownloadMode.VIDEO_AUDIO)

    def _on_choose_folder_clicked(self) -> None:
        if self._on_choose_folder:
            self._on_choose_folder()

    def _on_queue_clicked(self, button: Gtk.Button) -> None:
        if self._on_add_to_queue:
            self._on_add_to_queue()

    def _on_download_custom_clicked(self, button: Gtk.Button) -> None:
        if self._on_download_with_options:
            self._on_download_with_options()

    # ── Getters / Setters ────────────────────────────────────────────────
    def get_quality(self) -> str:
        idx = self._quality_row.get_selected()
        if 0 <= idx < len(self._quality_codes):
            return self._quality_codes[idx]
        return "Best"

    def get_mode(self) -> DownloadMode:
        return DownloadMode.AUDIO_ONLY if self._mode_row.get_selected() == 1 else DownloadMode.VIDEO_AUDIO

    def get_format(self) -> str:
        item = self._format_row.get_selected_item()
        return item.get_string() if item else "MP4"

    def get_clip_range(self) -> tuple[Optional[str], Optional[str]]:
        """Validate and return (clip_start, clip_end) in string format."""
        start_txt = self._clip_start_row.get_text().strip()
        end_txt = self._clip_end_row.get_text().strip()

        start = start_txt if parse_timestamp(start_txt) is not None else None
        end = end_txt if parse_timestamp(end_txt) is not None else None
        return start, end

    def get_subtitles(self) -> tuple[Optional[str], bool]:
        """Return (subtitles_lang, embed_subtitles)."""
        idx = self._subtitles_row.get_selected()
        if idx > 0 and idx < len(self._subtitle_codes):
            lang = self._subtitle_codes[idx]
            embed = self._embed_subs_row.get_active()
            return lang, embed
        return None, False

    def get_destination(self) -> str:
        return self._destination_dir

    def set_destination(self, path: str) -> None:
        self._destination_dir = path
        self._folder_row.set_subtitle(path)
