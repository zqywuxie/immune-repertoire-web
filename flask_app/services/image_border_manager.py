"""
Utilities for applying border styles to PPT picture shapes.
"""
from typing import Tuple

from pptx.dml.color import RGBColor
from pptx.util import Pt


class ImageBorderStyleManager:
    """Apply consistent border styling to a picture shape."""

    def __init__(
        self,
        border_width: float = 1.0,
        border_color: Tuple[int, int, int] = (0, 0, 0),
    ):
        self.border_width = float(border_width)
        self.border_color = self._normalize_color(border_color)

    @staticmethod
    def _normalize_color(color: Tuple[int, int, int]) -> Tuple[int, int, int]:
        if not isinstance(color, tuple) or len(color) != 3:
            return (0, 0, 0)
        normalized = []
        for value in color:
            try:
                normalized.append(max(0, min(255, int(value))))
            except (TypeError, ValueError):
                normalized.append(0)
        return tuple(normalized)  # type: ignore[return-value]

    def apply_border(self, picture_shape) -> None:
        """
        Apply border style to a PPT picture shape.
        """
        line = picture_shape.line
        line.fill.solid()
        line.fill.fore_color.rgb = RGBColor(*self.border_color)
        line.width = Pt(self.border_width)
