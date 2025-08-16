from __future__ import annotations

import math
import itertools
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Iterable
from colorsys import rgb_to_hsv, hsv_to_rgb


Vector = Tuple[float, float]
ColorRGB = Tuple[float, float, float]


@dataclass
class Rect:
    x: float
    y: float
    width: float
    height: float

    def contains_point(self, point: Vector) -> bool:
        px, py = point
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height


@dataclass
class Ball:
    id: str
    position: Vector
    velocity: Vector
    radius: float
    color_rgb: ColorRGB
    mass: float = field(init=False)

    def __post_init__(self) -> None:
        # Use area as a proxy for mass to get more natural feel when forces are applied
        self.mass = max(1e-6, math.pi * (self.radius ** 2))


@dataclass
class StepResult:
    time_advanced_s: float
    mixed_pairs: List[Tuple[str, str]]
    deleted_ball_ids: List[str]
    captured_ball_ids: List[str]
    released_ball_ids: List[str]


@dataclass
class Suction:
    is_active: bool = False
    position: Vector = (0.0, 0.0)
    radius: float = 160.0
    strength: float = 1200.0
    capture_radius: float = 28.0


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _normalize(vec: Vector) -> Vector:
    vx, vy = vec
    mag = math.hypot(vx, vy)
    if mag == 0.0:
        return 0.0, 0.0
    return vx / mag, vy / mag


def _angle_lerp(a: float, b: float, t: float) -> float:
    # Interpolate two angles (in [0, 1) hue-space) along the shortest arc
    # a, b are in 0..1 (representing 0..360 deg)
    two_pi = 2.0 * math.pi
    aa = a * two_pi
    bb = b * two_pi
    delta = (bb - aa + math.pi) % (2.0 * math.pi) - math.pi
    out = (aa + delta * _clamp(t, 0.0, 1.0)) % two_pi
    return out / two_pi


def _mix_color_towards(src_rgb: ColorRGB, dst_rgb: ColorRGB, t: float) -> ColorRGB:
    # Convert to HSV for perceptual mixing, avoid whitening by boosting saturation and capping value
    sh, ss, sv = rgb_to_hsv(*src_rgb)
    dh, ds, dv = rgb_to_hsv(*dst_rgb)

    # Interpolate hue circularly and bias towards stronger saturation
    h = _angle_lerp(sh, dh, t)
    s_target = max(ss, ds)
    s = _clamp((1.0 - t) * ss + t * s_target, 0.35, 1.0)

    # Value: weighted blend with mild cap to keep colors vivid and avoid white-outs
    v = _clamp((1.0 - t) * sv + t * dv, 0.0, 0.92)

    r, g, b = hsv_to_rgb(h, s, v)
    return _clamp(r, 0.0, 1.0), _clamp(g, 0.0, 1.0), _clamp(b, 0.0, 1.0)


class GameLogic:
    """
    Pure logic module for the marble game.

    Responsibilities:
    - Update positions with simple physics and boundary handling
    - Apply optional suction towards a pointer (mouse) and capture into an inventory
    - Release (spit) balls from the inventory back into the world
    - Mix colors on contact without physical collision response
    - Delete balls that enter a configured delete zone

    All numeric units are arbitrary but self-consistent (pixels, pixels/sec, seconds).
    """

    def __init__(
        self,
        world_width: float,
        world_height: float,
        delete_zone: Optional[Rect] = None,
        boundary_bounce: bool = True,
        linear_damping_per_second: float = 0.15,
        max_color_mix_factor_per_second: float = 0.85,
        gravity: Vector = (0.0, 0.0),
    ) -> None:
        self.world_width = float(world_width)
        self.world_height = float(world_height)
        self.boundary_bounce = boundary_bounce
        self.linear_damping_per_second = float(_clamp(linear_damping_per_second, 0.0, 5.0))
        self.max_color_mix_factor_per_second = float(_clamp(max_color_mix_factor_per_second, 0.0, 5.0))
        self.gravity = gravity

        self.delete_zone = delete_zone or Rect(
            x=self.world_width - 120.0,
            y=self.world_height - 120.0,
            width=120.0,
            height=120.0,
        )

        self._balls: Dict[str, Ball] = {}
        self._inventory: Dict[str, Ball] = {}
        self._suction = Suction()

    # -------- Public API: world and inventory management -------- #

    def add_ball(
        self,
        position: Vector,
        velocity: Vector,
        radius: float,
        color_rgb: ColorRGB,
        ball_id: Optional[str] = None,
    ) -> str:
        bid = ball_id or uuid.uuid4().hex
        px, py = position
        vx, vy = velocity
        ball = Ball(id=bid, position=(float(px), float(py)), velocity=(float(vx), float(vy)), radius=float(radius), color_rgb=color_rgb)
        self._balls[bid] = ball
        return bid

    def remove_ball(self, ball_id: str) -> bool:
        return self._balls.pop(ball_id, None) is not None

    def get_balls_snapshot(self) -> List[Ball]:
        return list(self._balls.values())

    def get_inventory_ids(self) -> List[str]:
        return list(self._inventory.keys())

    def set_delete_zone(self, rect: Rect) -> None:
        self.delete_zone = rect

    # -------- Public API: suction control (mouse interactions) -------- #

    def start_suction(self, position: Vector, radius: Optional[float] = None, strength: Optional[float] = None, capture_radius: Optional[float] = None) -> None:
        self._suction.is_active = True
        self._suction.position = (float(position[0]), float(position[1]))
        if radius is not None:
            self._suction.radius = float(radius)
        if strength is not None:
            self._suction.strength = float(strength)
        if capture_radius is not None:
            self._suction.capture_radius = float(capture_radius)

    def update_suction(self, position: Vector) -> None:
        if not self._suction.is_active:
            return
        self._suction.position = (float(position[0]), float(position[1]))

    def stop_suction(self) -> None:
        self._suction.is_active = False

    # -------- Public API: spitting / releasing -------- #

    def spit_next(self, position: Vector, direction: Vector, speed: float) -> Optional[str]:
        try:
            ball_id, ball = next(iter(self._inventory.items()))
        except StopIteration:
            return None
        del self._inventory[ball_id]
        px, py = float(position[0]), float(position[1])
        dx, dy = _normalize(direction)
        vx, vy = dx * float(speed), dy * float(speed)
        # Reuse same radius and color
        ball.position = (px, py)
        ball.velocity = (vx, vy)
        self._balls[ball_id] = ball
        return ball_id

    def spit_specific(self, ball_id: str, position: Vector, direction: Vector, speed: float) -> bool:
        ball = self._inventory.pop(ball_id, None)
        if ball is None:
            return False
        px, py = float(position[0]), float(position[1])
        dx, dy = _normalize(direction)
        vx, vy = dx * float(speed), dy * float(speed)
        ball.position = (px, py)
        ball.velocity = (vx, vy)
        self._balls[ball_id] = ball
        return True

    # -------- Simulation step -------- #

    def step(self, dt: float) -> StepResult:
        dt = max(0.0, float(dt))
        mixed_pairs: List[Tuple[str, str]] = []
        deleted_ball_ids: List[str] = []
        captured_ball_ids: List[str] = []
        released_ball_ids: List[str] = []

        if dt == 0.0:
            return StepResult(dt, mixed_pairs, deleted_ball_ids, captured_ball_ids, released_ball_ids)

        # Integrate velocities with gravity and damping
        damping = math.exp(-self.linear_damping_per_second * dt)
        gx, gy = self.gravity

        # Apply suction forces and possibly capture
        if self._suction.is_active:
            sx, sy = self._suction.position
            sr = self._suction.radius
            strength = self._suction.strength
            capture_r = self._suction.capture_radius

            for ball in self._balls.values():
                bx, by = ball.position
                to_sx = sx - bx
                to_sy = sy - by
                dist = math.hypot(to_sx, to_sy)
                if dist <= sr and dist > 1e-6:
                    pull_dir = (to_sx / dist, to_sy / dist)
                    # Quadratic falloff for a pleasant suction feel
                    falloff = 1.0 - (dist / sr)
                    accel_mag = strength * (falloff ** 2) / ball.mass
                    ax = pull_dir[0] * accel_mag
                    ay = pull_dir[1] * accel_mag
                    vx, vy = ball.velocity
                    vx += ax * dt
                    vy += ay * dt
                    ball.velocity = (vx, vy)

        # Integrate motion and boundaries
        for ball in self._balls.values():
            vx = ball.velocity[0] + gx * dt
            vy = ball.velocity[1] + gy * dt
            vx *= damping
            vy *= damping
            px = ball.position[0] + vx * dt
            py = ball.position[1] + vy * dt

            if self.boundary_bounce:
                # Left/right
                if px - ball.radius < 0.0:
                    px = ball.radius
                    vx = abs(vx)
                elif px + ball.radius > self.world_width:
                    px = self.world_width - ball.radius
                    vx = -abs(vx)
                # Top/bottom
                if py - ball.radius < 0.0:
                    py = ball.radius
                    vy = abs(vy)
                elif py + ball.radius > self.world_height:
                    py = self.world_height - ball.radius
                    vy = -abs(vy)
            else:
                # Wrap around
                if px < -ball.radius:
                    px = self.world_width + ball.radius
                elif px > self.world_width + ball.radius:
                    px = -ball.radius
                if py < -ball.radius:
                    py = self.world_height + ball.radius
                elif py > self.world_height + ball.radius:
                    py = -ball.radius

            ball.position = (px, py)
            ball.velocity = (vx, vy)

        # Capture after movement so a gentle suction can keep pulling into the mouth
        if self._suction.is_active:
            sx, sy = self._suction.position
            capture_r = self._suction.capture_radius
            to_capture: List[str] = []
            for ball in self._balls.values():
                bx, by = ball.position
                if math.hypot(bx - sx, by - sy) <= max(capture_r, ball.radius * 0.8):
                    to_capture.append(ball.id)

            for bid in to_capture:
                ball = self._balls.pop(bid, None)
                if ball is None:
                    continue
                self._inventory[bid] = ball
                captured_ball_ids.append(bid)

        # Color mixing on overlaps (no physical response)
        balls_list = list(self._balls.values())
        # Simple spatial all-pairs; acceptable for moderate counts; can be optimized later
        mix_t = _clamp(self.max_color_mix_factor_per_second * dt, 0.0, 0.75)
        if mix_t > 0.0:
            for a, b in itertools.combinations(balls_list, 2):
                ax, ay = a.position
                bx, by = b.position
                if math.hypot(ax - bx, ay - by) <= a.radius + b.radius:
                    a.color_rgb = _mix_color_towards(a.color_rgb, b.color_rgb, mix_t)
                    b.color_rgb = _mix_color_towards(b.color_rgb, a.color_rgb, mix_t)
                    mixed_pairs.append((a.id, b.id))

        # Delete-zone processing
        to_delete: List[str] = []
        for ball in self._balls.values():
            if self.delete_zone.contains_point(ball.position):
                to_delete.append(ball.id)
        for bid in to_delete:
            if self._balls.pop(bid, None) is not None:
                deleted_ball_ids.append(bid)

        return StepResult(
            time_advanced_s=dt,
            mixed_pairs=mixed_pairs,
            deleted_ball_ids=deleted_ball_ids,
            captured_ball_ids=captured_ball_ids,
            released_ball_ids=released_ball_ids,
        )


# Convenience factory for quick setup in tests or prototypes
def create_default_logic(world_size: Tuple[int, int]) -> GameLogic:
    w, h = world_size
    return GameLogic(world_width=float(w), world_height=float(h))


