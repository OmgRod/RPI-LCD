"""Shared base tab class to avoid cross-module import cycles."""

from __future__ import annotations


class Tab:
    """Base class for a tab in the UI."""

    def __init__(self, name, icon=None):
        self.name = name
        self.icon = icon
        self.full_screen = False

    def render(self, monitor, width, height):
        """Render this tab's content into an image."""
        raise NotImplementedError()

    def close(self):
        """Release tab-local resources if needed."""
