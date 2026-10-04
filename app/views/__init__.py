"""Views for Video Downloader UI."""

from app.views.smart_card import SmartCardView
from app.views.options_expander import OptionsExpanderView
from app.views.queue_view import QueueView
from app.views.history_dialog import HistoryDialog

__all__ = [
    "SmartCardView",
    "OptionsExpanderView",
    "QueueView",
    "HistoryDialog",
]
