"""Low-motion random square screensaver optimized for LCD longevity."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
import time

from PIL import Image, ImageDraw, ImageEnhance, ImageOps


def _smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


@dataclass
class SquareCell:
    start_color: tuple[int, int, int]
    target_color: tuple[int, int, int]
    current_color: tuple[int, int, int]
    transition_started_at: float
    transition_duration: float
    next_transition_at: float


class RandomSquareScreensaver:
    """Animated random-square screensaver with lower panel stress."""

    def __init__(
        self,
        block_size: int = 40,
        max_drift_pixels: int = 2,
        color_floor: int = 12,
        color_ceiling: int = 110,
        transition_seconds: tuple[float, float] = (1.2, 2.8),
        hold_seconds: tuple[float, float] = (1.0, 2.0),
        reset_interval_seconds: tuple[float, float] = (18.0, 40.0),
        reset_duration_seconds: tuple[float, float] = (0.65, 1.05),
    ):
        self.block_size = block_size
        self.max_drift_pixels = max_drift_pixels
        self.color_floor = color_floor
        self.color_ceiling = color_ceiling
        self.transition_seconds = transition_seconds
        self.hold_seconds = hold_seconds
        self.reset_interval_seconds = reset_interval_seconds
        self.reset_duration_seconds = reset_duration_seconds

        self._cells: dict[tuple[int, int], SquareCell] = {}
        self._grid_size: tuple[int, int] | None = None

        # Velocity-based directional drift (replaces oscillation)
        self._drift_offset_x = 0.0
        self._drift_offset_y = 0.0
        self._drift_velocity_x = random.uniform(-0.5, 0.5)
        self._drift_velocity_y = random.uniform(-0.5, 0.5)
        self._direction_change_time = time.time()
        self._direction_change_interval = random.uniform(4.0, 8.0)

        self._next_reset_at = 0.0
        self._reset_started_at = 0.0
        self._reset_duration = 0.0
        self._reset_mode = None
        self._last_render_at: float | None = None

    def render(self, width: int, height: int) -> Image.Image:
        now = time.monotonic()
        delta = 0.0 if self._last_render_at is None else max(0.0, now - self._last_render_at)
        self._last_render_at = now
        self._ensure_grid(width, height, now)

        # Update drift direction periodically
        if time.time() - self._direction_change_time >= self._direction_change_interval:
            self._direction_change_time = time.time()
            self._direction_change_interval = random.uniform(4.0, 8.0)
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(0.3, 0.8)
            self._drift_velocity_x = speed * math.cos(angle)
            self._drift_velocity_y = speed * math.sin(angle)

        # Update drift offset with velocity
        self._drift_offset_x += self._drift_velocity_x
        self._drift_offset_y += self._drift_velocity_y

        # Clamp drift within reasonable bounds
        max_drift = 15
        self._drift_offset_x = max(-max_drift, min(max_drift, self._drift_offset_x))
        self._drift_offset_y = max(-max_drift, min(max_drift, self._drift_offset_y))

        image = Image.new("RGB", (width, height), (0, 0, 0))
        draw = ImageDraw.Draw(image)

        drift_x = int(self._drift_offset_x)
        drift_y = int(self._drift_offset_y)

        for (col, row), cell in self._cells.items():
            self._update_cell(cell, now)
            x0 = col * self.block_size + drift_x
            y0 = row * self.block_size + drift_y
            x1 = min(x0 + self.block_size, width)
            y1 = min(y0 + self.block_size, height)
            if x1 <= 0 or y1 <= 0 or x0 >= width or y0 >= height:
                continue
            draw.rectangle([x0, y0, x1, y1], fill=cell.current_color)

        return self._apply_reset_effect(image, now)

    def _ensure_grid(self, width: int, height: int, now: float) -> None:
        grid_size = (
            math.ceil(width / self.block_size),
            math.ceil(height / self.block_size),
        )
        if self._grid_size == grid_size:
            return

        self._grid_size = grid_size
        self._cells = {}
        for col in range(grid_size[0]):
            for row in range(grid_size[1]):
                color = self._random_dark_color()
                transition_duration = random.uniform(*self.transition_seconds)
                hold_duration = random.uniform(*self.hold_seconds)
                self._cells[(col, row)] = SquareCell(
                    start_color=color,
                    target_color=color,
                    current_color=color,
                    transition_started_at=now,
                    transition_duration=transition_duration,
                    next_transition_at=now + hold_duration,
                )

        self._schedule_reset(now)

    def _update_cell(self, cell: SquareCell, now: float) -> None:
        if now >= cell.next_transition_at:
            cell.start_color = cell.current_color
            cell.target_color = self._random_dark_color()
            cell.transition_started_at = now
            cell.transition_duration = random.uniform(*self.transition_seconds)
            cell.next_transition_at = now + random.uniform(*self.hold_seconds)

        progress = (now - cell.transition_started_at) / cell.transition_duration
        eased = _smoothstep(progress)
        cell.current_color = tuple(
            int(start + (target - start) * eased)
            for start, target in zip(cell.start_color, cell.target_color)
        )

    def _random_dark_color(self) -> tuple[int, int, int]:
        return tuple(
            random.randint(self.color_floor, self.color_ceiling)
            for _ in range(3)
        )

    def _schedule_reset(self, now: float) -> None:
        self._reset_mode = None
        self._reset_started_at = 0.0
        self._reset_duration = 0.0
        self._next_reset_at = now + random.uniform(*self.reset_interval_seconds)

    def _apply_reset_effect(self, image: Image.Image, now: float) -> Image.Image:
        if self._reset_mode is None and now >= self._next_reset_at:
            self._reset_mode = "fade" if random.random() < 0.75 else "invert"
            self._reset_started_at = now
            self._reset_duration = random.uniform(*self.reset_duration_seconds)

        if self._reset_mode is None:
            return image

        progress = (now - self._reset_started_at) / self._reset_duration
        if progress >= 1.0:
            self._schedule_reset(now)
            return image

        pulse = 1.0 - abs(progress * 2.0 - 1.0)

        if self._reset_mode == "fade":
            brightness = max(0.05, 1.0 - pulse)
            return ImageEnhance.Brightness(image).enhance(brightness)

        inverted = ImageOps.invert(image)
        blended = Image.blend(image, inverted, 0.16 * pulse)
        return ImageEnhance.Brightness(blended).enhance(max(0.35, 0.8 - 0.35 * pulse))
