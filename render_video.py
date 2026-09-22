#!/usr/bin/env python3
"""Render a seamless, 30-second space flight. No external video service required.

The generated photographic plates are in assets/. Planets, their lighting and
rings, the perspective star field, camera motion and sound are procedural.
"""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import subprocess
import time
import wave

os.environ.setdefault("OMP_NUM_THREADS", "2")
import cv2
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw
from scipy import fft

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".cache" / "space-flight"
EXPORT = ROOT / "exports"
DURATION = 30.0
FPS = 30
TAU = math.tau
cv2.setNumThreads(2)


def smoothstep(a, b, x):
    y = np.clip((x - a) / (b - a), 0, 1)
    return y * y * (3 - 2 * y)


def fractal_noise(height, width, seed, octaves=7, initial=4, persistence=0.53):
    rng = np.random.default_rng(seed)
    out = np.zeros((height, width), np.float32)
    amplitude = 1.0
    norm = 0.0
    for octave in range(octaves):
        gh = min(height, initial * 2**octave)
        gw = min(width, initial * 2**octave * 2)
        tile = rng.random((gh, gw), dtype=np.float32)
        out += amplitude * cv2.resize(tile, (width, height), interpolation=cv2.INTER_CUBIC)
        norm += amplitude
        amplitude *= persistence
    return np.clip(out / norm, 0, 1)


def palette(values, stops, colors):
    return np.stack([np.interp(values, stops, np.array(colors)[:, c]) for c in range(3)], -1).astype(np.float32)


def planet_texture(kind, width=2048, height=1024):
    seeds = {"amber": 51, "rings": 27, "ocean": 18, "ice": 65, "rock": 10}
    seed = seeds[kind]
    noise = fractal_noise(height, width, seed, 8)
    fine = fractal_noise(height, width, seed + 400, 6, 24)
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    u, v = xx / width, yy / height
    if kind in ("amber", "rings", "ice"):
        # A warped latitude field gives gas bands and a large cyclonic storm.
        dx, dy = (u - 0.58) / 0.09, (v - 0.52) / 0.038
        radius = np.sqrt(dx * dx + dy * dy)
        angle = np.arctan2(dy, dx) + 3.6 * np.exp(-radius * radius * 0.40)
        vv = 0.52 + radius * np.sin(angle) * 0.038
        band = vv * 125 + (noise - 0.5) * 9 + np.sin(u * 36 + noise * 8) * 0.35
        values = np.clip(0.54 + 0.19 * np.sin(band) + 0.080 * np.sin(band * 2.31) + 0.022 * np.sin(band * 7.13) + (fine - 0.5) * 0.42, 0, 1)
        if kind == "amber":
            colors = [(0.13, 0.065, 0.037), (0.37, 0.19, 0.10), (0.69, 0.40, 0.20), (0.92, 0.72, 0.43), (0.98, 0.88, 0.65)]
        elif kind == "rings":
            colors = [(0.21, 0.19, 0.14), (0.48, 0.41, 0.29), (0.69, 0.60, 0.44), (0.90, 0.83, 0.65), (0.99, 0.93, 0.76)]
        else:
            colors = [(0.015, 0.055, 0.15), (0.035, 0.16, 0.30), (0.07, 0.34, 0.50), (0.28, 0.60, 0.71), (0.66, 0.86, 0.86)]
            values = 0.61 + np.sin(vv * 54 + noise * 2.4) * 0.09 + (noise - 0.5) * 0.37 + (fine - 0.5) * 0.25
        texture = palette(values, [0, 0.25, 0.5, 0.75, 1], colors)
        if kind == "ice":
            texture *= (0.85 + 0.15 * np.sin(v * math.pi))[..., None]
        return texture
    if kind == "ocean":
        terrain = fractal_noise(height, width, seed + 12, 8, 5)
        land = smoothstep(0.49, 0.505, terrain)
        terrain_colors = palette(terrain, [0.40, 0.50, 0.57, 0.65, 0.8], [(0.17, 0.30, 0.22), (0.20, 0.38, 0.29), (0.46, 0.47, 0.26), (0.71, 0.62, 0.39), (0.90, 0.83, 0.64)])
        water = np.empty((height, width, 3), np.float32)
        water[:] = (0.017, 0.12, 0.22)
        water += smoothstep(0.40, 0.51, terrain)[..., None] * np.array([0.02, 0.17, 0.19], np.float32)
        texture = terrain_colors * land[..., None] + water * (1 - land[..., None])
        cloud_field = fractal_noise(height, width, seed + 88, 8, 7)
        clouds = smoothstep(0.49, 0.65, cloud_field) * 0.92
        texture = texture * (1 - clouds[..., None]) + np.array([0.88, 0.94, 0.96]) * clouds[..., None]
        ice = smoothstep(0.40, 0.49, np.abs(v - 0.5) + (noise - 0.5) * 0.1)
        texture = texture * (1 - ice[..., None]) + np.array([0.79, 0.87, 0.87]) * ice[..., None]
        return texture.astype(np.float32)
    values = np.clip(noise * 0.7 + fine * 0.3, 0, 1)
    texture = palette(values, [0, 0.35, 0.5, 0.65, 1], [(0.045, 0.035, 0.039), (0.18, 0.10, 0.075), (0.40, 0.26, 0.18), (0.60, 0.41, 0.27), (0.80, 0.66, 0.48)])
    rng = np.random.default_rng(seed + 9)
    crater_light = np.ones((height, width), np.float32)
    for _ in range(420):
        cx, cy = rng.integers(0, width), rng.integers(0, height)
        r = rng.uniform(3, 36)
        x0, x1 = max(0, int(cx - r * 1.5)), min(width, int(cx + r * 1.5) + 1)
        y0, y1 = max(0, int(cy - r * 1.5)), min(height, int(cy + r * 1.5) + 1)
        dy, dx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        rr = np.sqrt(((dx - cx) / r) ** 2 + ((dy - cy) / r) ** 2)
        bowl = -0.28 * np.exp(-((rr / 0.74) ** 4))
        rim = np.exp(-((rr - 0.93) / 0.10) ** 2) * (0.23 - (dx - cx) / r * 0.25)
        crater_light[y0:y1, x0:x1] *= 1 + bowl + rim
    return np.clip(texture * crater_light[..., None], 0, 1)


def make_planet(kind):
    """Orthographic lit sphere + ray/plane rings, saved premultiplied RGBA."""
    path = CACHE / f"planet-{kind}-v3.png"
    bounds = 3.08 if kind == "rings" else 1.10
    if path.exists():
        return cv2.cvtColor(cv2.imread(str(path), cv2.IMREAD_UNCHANGED), cv2.COLOR_BGRA2RGBA).astype(np.float32) / 255, bounds
    print(f"Building {kind} planet", flush=True)
    size = 2200 if kind == "rings" else 1400
    coord = (np.arange(size, dtype=np.float32) + 0.5) / size * 2 * bounds - bounds
    x, y = np.meshgrid(coord, -coord)
    rr = np.sqrt(x * x + y * y)
    z = np.sqrt(np.maximum(0, 1 - rr * rr))
    eps = bounds * 2 / size
    solid = 1 - smoothstep(1 - eps, 1 + eps, rr)
    # Tilt the planet axis, then use longitude/latitude to sample its albedo.
    tilt = {"amber": -0.20, "rings": 0.42, "ocean": 0.22, "ice": -0.35, "rock": 0.15}[kind]
    tx = x * math.cos(tilt) - y * math.sin(tilt)
    ty = x * math.sin(tilt) + y * math.cos(tilt)
    long = np.arctan2(tx, z) / TAU + 0.5
    lat = 0.5 - np.arcsin(np.clip(ty, -1, 1)) / math.pi
    texture = planet_texture(kind)
    albedo = cv2.remap(texture, (long * (texture.shape[1] - 1)).astype(np.float32), (lat * (texture.shape[0] - 1)).astype(np.float32), interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
    sun = np.array([-0.69, 0.40, 0.61], np.float32)
    sun /= np.linalg.norm(sun)
    ndotl = x * sun[0] + y * sun[1] + z * sun[2]
    daylight = np.maximum(ndotl, 0)
    shade = 0.018 + daylight ** 0.78 * 1.02
    rgb = albedo * shade[..., None]
    atmosphere_colors = {
        "amber": (0.88, 0.46, 0.15), "rings": (0.70, 0.66, 0.41),
        "ocean": (0.09, 0.51, 0.98), "ice": (0.10, 0.62, 1.0), "rock": (0.48, 0.18, 0.08),
    }
    atmosphere = np.array(atmosphere_colors[kind], np.float32)
    strength = 0.18 if kind == "rock" else 0.44
    rim = (1 - z) ** 3.7 * (np.maximum(ndotl, 0) * 0.8 + 0.04)
    rgb += rim[..., None] * atmosphere * strength
    if kind == "ocean":
        half = sun + np.array([0, 0, 1], np.float32)
        half /= np.linalg.norm(half)
        highlight = np.maximum(0, x * half[0] + y * half[1] + z * half[2]) ** 110
        rgb += highlight[..., None] * np.array([0.68, 0.78, 0.80]) * 0.4
    # Thin atmospheric scattering extends past the solid silhouette.
    glow = np.exp(-((np.maximum(rr - 1, 0)) / 0.026) ** 2) * (1 - solid)
    glow *= (np.maximum(x * sun[0] + y * sun[1], 0) * 0.9 + 0.1) * strength
    alpha = solid + glow
    premult = rgb * solid[..., None] + glow[..., None] * atmosphere
    if kind == "rings":
        angle = math.radians(-27)
        rx = x * math.cos(angle) + y * math.sin(angle)
        ry = -x * math.sin(angle) + y * math.cos(angle)
        q = 0.39
        radial = np.sqrt(rx * rx + (ry / q) ** 2)
        depth = ry * math.sqrt(1 - q * q) / q
        edge = smoothstep(1.30, 1.36, radial) * (1 - smoothstep(2.80, 2.86, radial))
        bands = 0.67 + 0.12 * np.sin(radial * 122) + 0.08 * np.sin(radial * 373) + 0.07 * np.sin(radial * 53)
        gaps = (1 - 0.96 * np.exp(-((radial - 2.28) / 0.042) ** 6)) * (1 - 0.65 * np.exp(-((radial - 2.65) / 0.019) ** 2))
        ring_alpha = np.clip(edge * bands * gaps, 0, 0.94)
        dot = x * sun[0] + y * sun[1] + depth * sun[2]
        dist_to_sun_ray = np.sqrt(np.maximum(0, x * x + y * y + depth * depth - dot * dot))
        shadow = np.where(dot < 0, 0.16 + smoothstep(0.95, 1.13, dist_to_sun_ray) * 0.84, 1)
        ring_rgb = np.array([0.83, 0.73, 0.56], np.float32)[None, None, :] * (0.71 + 0.19 * np.sin(radial * 21))[..., None]
        ring_rgb *= shadow[..., None]
        visible = np.maximum(1 - solid, smoothstep(z - 0.018, z + 0.018, depth))
        ring_alpha *= visible
        premult = premult * (1 - ring_alpha[..., None]) + ring_rgb * ring_alpha[..., None]
        alpha = alpha * (1 - ring_alpha) + ring_alpha
    rgba = np.concatenate([np.clip(premult, 0, 1), np.clip(alpha, 0, 1)[..., None]], -1)
    cv2.imwrite(str(path), cv2.cvtColor((rgba * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGBA2BGRA))
    return rgba.astype(np.float32), bounds


def make_sun():
    size = 720
    y, x = np.mgrid[:size, :size].astype(np.float32)
    x, y = (x + 0.5 - size / 2) / (size / 2) * 12, (y + 0.5 - size / 2) / (size / 2) * 12
    r = np.sqrt(x * x + y * y)
    theta = np.arctan2(y, x)
    edge = 1 - smoothstep(9, 11.8, r)
    halo = (0.18 * np.exp(-r / 2.2) + 0.035 * np.exp(-r / 5.0)) * edge
    corona = 0.17 * np.exp(-r / 1.6) * (0.75 + 0.25 * np.sin(theta * 39 + r * 3)) * edge
    core = np.exp(-((r / 0.79) ** 4)) * 1.9
    spikes = (np.exp(-((y / 0.04) ** 2)) * np.exp(-np.abs(x) / 3.4) + np.exp(-((x / 0.032) ** 2)) * np.exp(-np.abs(y) / 2.1)) * 0.075 * edge
    return ((halo + corona + spikes)[..., None] * np.array([1.0, 0.51, 0.18], np.float32) + core[..., None] * np.array([1.0, 0.87, 0.62], np.float32)).astype(np.float32)


class Flight:
    def __init__(self, width=1080, height=1920):
        CACHE.mkdir(parents=True, exist_ok=True)
        self.w, self.h = width, height
        self.focal = height * 0.90
        self.rscale = height / 1920
        self.depth = 960.0
        self.speed = self.depth / DURATION
        raw = cv2.imread(str(ROOT / "assets" / "nebula-source.jpg"))
        if raw is None:
            raise FileNotFoundError("assets/nebula-source.jpg")
        self.nebula = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB).astype(np.float32) / 255
        self.nebula = cv2.resize(self.nebula, (width, height), interpolation=cv2.INTER_CUBIC)
        # Remove the largest embedded stellar pinpoints from the moving gas plate.
        self.nebula = cv2.GaussianBlur(self.nebula, (0, 0), 0.65 * self.rscale)
        galaxy = cv2.imread(str(ROOT / "assets" / "galaxy-source.jpg"))
        if galaxy is None:
            raise FileNotFoundError("assets/galaxy-source.jpg")
        galaxy = cv2.cvtColor(galaxy, cv2.COLOR_BGR2RGB).astype(np.float32) / 255
        gh, gw = galaxy.shape[:2]
        gy, gx = np.mgrid[:gh, :gw].astype(np.float32)
        gr = np.sqrt(((gx - gw / 2) / (gw / 2)) ** 2 + ((gy - gh / 2) / (gh / 2)) ** 2)
        galaxy = np.maximum(0, galaxy - 0.012)
        galaxy *= (1 - smoothstep(0.80, 0.99, gr))[..., None]
        self.galaxy = galaxy
        self.sun = make_sun()
        self.planets = {kind: make_planet(kind) for kind in ["amber", "rings", "ocean", "ice", "rock"]}
        self.objects = [
            # x, y, radius, moment the camera passes its depth plane.
            dict(kind="amber", x=-46, y=-37, r=23.0, at=5.0),
            dict(kind="rings", x=39, y=65, r=14.0, at=11.0),
            dict(kind="ocean", x=-36, y=60, r=19.0, at=17.0),
            dict(kind="ice", x=45, y=-67, r=22.0, at=23.0),
            dict(kind="rock", x=-44, y=-29, r=15.0, at=29.0),
            dict(kind="sun", x=-58, y=11, r=2.4, at=15.0),
            dict(kind="sun", x=65, y=31, r=2.0, at=27.5),
            dict(kind="galaxy", x=74, y=-145, r=72, at=10.5, tilt=-28, ratio=0.52, gain=0.73),
            dict(kind="galaxy", x=-100, y=-106, r=76, at=20.0, tilt=32, ratio=0.64, gain=0.88),
            dict(kind="galaxy", x=100, y=107, r=74, at=30.0, tilt=-34, ratio=0.50, gain=0.77),
        ]
        rng = np.random.default_rng(8201)
        count = 2350
        self.star_x = rng.uniform(-335, 335, count).astype(np.float32)
        self.star_y = rng.uniform(-595, 595, count).astype(np.float32)
        self.star_z = rng.uniform(0, self.depth, count).astype(np.float32)
        self.star_speed = np.full(count, self.speed, np.float32)
        self.star_speed[-420:] *= 4  # Four complete near-star flights per loop.
        self.star_brightness = (0.28 + rng.power(0.8, count) * 0.72).astype(np.float32)
        temperatures = np.array([(0.67, 0.83, 1), (0.82, 0.90, 1), (1, 0.95, 0.80), (1, 0.70, 0.45), (0.92, 0.84, 1)], np.float32)
        self.star_colors = temperatures[rng.choice(len(temperatures), count, p=[0.32, 0.38, 0.20, 0.04, 0.06])]
        self.star_size = rng.uniform(0.50, 1.20, count).astype(np.float32)
        self.star_size[rng.choice(count, 48, replace=False)] *= 1.7
        yy, xx = np.mgrid[:height, :width].astype(np.float32)
        radius = ((xx - width * 0.5) / (width * 0.75)) ** 2 + ((yy - height * 0.5) / (height * 0.80)) ** 2
        self.vignette = (1 - 0.20 * smoothstep(0.10, 1.8, radius))[..., None]
        self.last_progress = time.monotonic()

    def camera(self, t):
        phase = TAU * (t % DURATION) / DURATION
        return (4.5 * math.sin(phase), 4.0 * math.cos(phase), self.w * (0.5 + 0.012 * math.sin(phase)), self.h * (0.485 + 0.009 * math.cos(phase)), 0.021 * math.sin(phase))

    def projection(self, x, y, z, t):
        camx, camy, vx, vy, roll = self.camera(t)
        px = (x - camx) * self.focal / z
        py = (y - camy) * self.focal / z
        co, si = math.cos(roll), math.sin(roll)
        return vx + px * co - py * si, vy + px * si + py * co

    def background(self, t):
        # Two expanding cloud plates trade opacity at invisible reset points.
        frame = np.empty((self.h, self.w, 3), np.float32)
        frame[:] = (0.0015, 0.0025, 0.006)
        _, _, vx, vy, roll = self.camera(t)
        for offset in (0, 0.5):
            p = (t / DURATION + offset) % 1
            weight = math.sin(math.pi * p) ** 2
            if weight < 0.00001:
                continue
            zoom = math.exp(p * math.log(3.7))
            angle = 3.5 * math.sin(TAU * p) + math.degrees(roll)
            matrix = cv2.getRotationMatrix2D((self.w * 0.5, self.h * 0.5), angle, zoom)
            matrix[0, 2] += vx - self.w * 0.5
            matrix[1, 2] += vy - self.h * 0.5
            layer = cv2.warpAffine(self.nebula, matrix, (self.w, self.h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
            frame += layer * (weight * 0.76)
        return frame

    def stars(self, frame, t):
        z = (self.star_z - self.star_speed * t) % self.depth
        safe = np.maximum(z, 0.01)
        px, py = self.projection(self.star_x, self.star_y, safe, t)
        trailing = 0.085
        qx, qy = self.projection(self.star_x, self.star_y, safe + self.star_speed * trailing, t - trailing)
        valid = (z > 1) & (px > -70) & (px < self.w + 70) & (py > -70) & (py < self.h + 70)
        fade = smoothstep(0, 90, self.depth - z)
        nearness = np.clip(1 - z / self.depth, 0, 1)
        brightness = self.star_brightness * fade * (0.48 + 0.70 * nearness)
        radius = self.star_size * (0.38 + 1.04 * nearness**2) * self.rscale
        color = self.star_colors * brightness[:, None]
        # Subpixel AA avoids the popping of rounded integer coordinates.
        canvas = np.zeros((self.h, self.w, 3), np.uint8)
        shift = 4
        for i in np.flatnonzero(valid):
            c = tuple(float(k) for k in color[i] * 255)
            head = (int(px[i] * 16), int(py[i] * 16))
            tail = (int(qx[i] * 16), int(qy[i] * 16))
            streak = math.hypot(px[i] - qx[i], py[i] - qy[i])
            if streak > 0.8:
                cv2.line(canvas, tail, head, tuple(k * 0.48 for k in c), max(1, int(radius[i])), cv2.LINE_AA, shift)
            cv2.circle(canvas, head, max(5, int(radius[i] * 16)), c, -1, cv2.LINE_AA, shift)
            if radius[i] > 1.40 * self.rscale and brightness[i] > 0.55:
                arm = int(radius[i] * 16 * 3.1)
                cv2.line(canvas, (head[0] - arm, head[1]), (head[0] + arm, head[1]), tuple(k * 0.21 for k in c), 1, cv2.LINE_AA, shift)
                cv2.line(canvas, (head[0], head[1] - arm), (head[0], head[1] + arm), tuple(k * 0.21 for k in c), 1, cv2.LINE_AA, shift)
        # Bloom at quarter-resolution rather than blurring the full frame.
        glow = cv2.resize(canvas, (self.w // 4, self.h // 4), interpolation=cv2.INTER_AREA)
        glow = cv2.GaussianBlur(glow, (0, 0), 1.1)
        glow = cv2.resize(glow, (self.w, self.h), interpolation=cv2.INTER_LINEAR)
        frame += canvas.astype(np.float32) / 255
        frame += glow.astype(np.float32) / 255 * 0.70

    def sprite(self, frame, image, cx, cy, half_width, opacity=1.0, ratio=1.0, angle=0.0, additive=False):
        ih, iw = image.shape[:2]
        theta = math.radians(angle)
        co, si = math.cos(theta), math.sin(theta)
        hw, hh = half_width, half_width * ih / iw * ratio
        ex, ey = abs(hw * co) + abs(hh * si), abs(hw * si) + abs(hh * co)
        x0, x1 = max(0, math.floor(cx - ex - 2)), min(self.w, math.ceil(cx + ex + 2))
        y0, y1 = max(0, math.floor(cy - ey - 2)), min(self.h, math.ceil(cy + ey + 2))
        if x1 <= x0 or y1 <= y0 or opacity < 0.001:
            return
        sx, sy = hw * 2 / iw, hh * 2 / ih
        matrix = np.array([[co * sx, -si * sy, cx - x0 - co * hw + si * hh], [si * sx, co * sy, cy - y0 - si * hw - co * hh]], np.float32)
        patch = cv2.warpAffine(image, matrix, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        dest = frame[y0:y1, x0:x1]
        if additive:
            dest += patch * opacity
        else:
            alpha = patch[..., 3:4] * opacity
            dest *= 1 - alpha
            dest += patch[..., :3] * opacity

    def render(self, t):
        t %= DURATION
        frame = self.background(t)
        self.stars(frame, t)
        objects = [(self.speed * ((obj["at"] - t) % DURATION), obj) for obj in self.objects]
        for z, obj in sorted(objects, key=lambda item: -item[0]):
            if z < 1:
                continue
            opacity = float(smoothstep(0, 100, self.depth - z)) * (0.30 + 0.70 * (1 - z / self.depth) ** 0.55)
            x, y = self.projection(obj["x"], obj["y"], z, t)
            radius = obj["r"] * self.focal / z
            if obj["kind"] == "sun":
                self.sprite(frame, self.sun, x, y, radius * 12, opacity, additive=True)
            elif obj["kind"] == "galaxy":
                self.sprite(frame, self.galaxy, x, y, radius, opacity * obj["gain"], ratio=obj["ratio"], angle=obj["tilt"], additive=True)
            else:
                planet, bounds = self.planets[obj["kind"]]
                self.sprite(frame, planet, x, y, radius * bounds, opacity)
        frame *= self.vignette
        return (np.clip(frame, 0, 1) * 255 + 0.5).astype(np.uint8)


def make_audio(path, sample_rate=48000):
    """Original, periodic stereo ambience: soft harmonic pad and passing air."""
    print("Synthesizing original ambient audio", flush=True)
    n = int(DURATION * sample_rate)
    t = np.arange(n, dtype=np.float64) / sample_rate
    cycle = TAU * t / DURATION
    stereo = np.zeros((n, 2), np.float64)
    # Frequencies quantized to one loop ensure phase continuity at the join.
    for k, (freq, volume) in enumerate([(36.6666667, 0.10), (55, 0.14), (73.3333333, 0.12), (110, 0.065), (146.6666667, 0.048), (220, 0.028), (293.3333333, 0.013), (440, 0.006)]):
        freq = round(freq * DURATION) / DURATION
        envelope = 0.76 + 0.20 * np.sin(cycle + k * 0.77)
        vibrato = 0.25 * np.sin(cycle * 2 + k)
        for channel in range(2):
            stereo[:, channel] += volume * envelope * np.sin(TAU * freq * t + vibrato + k * 0.73 + channel * 0.19)
    rng = np.random.default_rng(482)
    frequencies = fft.rfftfreq(n, 1 / sample_rate)
    filter_curve = np.exp(-(frequencies / 600) ** 2) * (1 - np.exp(-(frequencies / 95) ** 2))
    air = []
    for channel in range(2):
        noise = fft.irfft(fft.rfft(rng.standard_normal(n)) * filter_curve, n)
        noise /= np.std(noise)
        air.append(noise)
    for event, pan in [(2.0, -0.8), (8.0, 0.8), (14.0, -0.65), (20.0, 0.7), (26.0, -0.5)]:
        distance = ((t - event + DURATION / 2) % DURATION) - DURATION / 2
        envelope = 0.015 * np.exp(-0.5 * (distance / 1.7) ** 2)
        stereo[:, 0] += air[0] * envelope * (1 - pan * 0.45)
        stereo[:, 1] += air[1] * envelope * (1 + pan * 0.45)
    # Restrained level, no abrupt introductory or closing fade.
    stereo *= 0.44 / np.max(np.abs(stereo))
    pcm = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(pcm.tobytes())


def render_video(width, height, fps, output, silent=False):
    if width % 2 or height % 2:
        raise ValueError("Width and height must be even for H.264/yuv420p")
    output.parent.mkdir(parents=True, exist_ok=True)
    flight = Flight(width, height)
    audio = CACHE / "ambience.wav"
    if not silent:
        make_audio(audio)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-"]
    if not silent:
        cmd += ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "20", "-maxrate", "12M", "-bufsize", "24M", "-threads", "2", "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.2", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-movflags", "+faststart", "-t", str(DURATION), "-metadata", "title=Viaje infinito", "-metadata", "comment=Original animated space flight. Seamless 30-second visual loop.", str(output)]
    process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    start = time.monotonic()
    total = round(DURATION * fps)
    try:
        for index in range(total):
            frame = flight.render(index / fps)
            process.stdin.write(frame.tobytes())
            if index % fps == 0:
                elapsed = time.monotonic() - start
                print(f"Frame {index:03}/{total} · {index/fps:02.0f}s / 30s · elapsed {elapsed:.1f}s", flush=True)
            if index == round(fps * 27.0):
                Image.fromarray(frame).save(output.with_suffix(".jpg"), quality=93)
        process.stdin.close()
        code = process.wait()
        if code:
            raise RuntimeError(f"FFmpeg exited with {code}")
    except BaseException:
        if process.poll() is None:
            process.kill()
            process.wait()
        output.unlink(missing_ok=True)
        raise
    print(f"Completed: {output} ({output.stat().st_size / 1e6:.1f} MB), {time.monotonic()-start:.1f}s", flush=True)


def preview():
    flight = Flight(432, 768)
    moments = [0, 4, 8, 12, 16, 20, 24, 28]
    sheet = Image.new("RGB", (432 * 4, 810 * 2), "#050610")
    draw = ImageDraw.Draw(sheet)
    for i, moment in enumerate(moments):
        frame = flight.render(moment)
        tile = Image.fromarray(frame)
        tile.save(CACHE / f"frame-{moment:02}.jpg", quality=95)
        x, y = (i % 4) * 432, (i // 4) * 810
        sheet.paste(tile, (x, y))
        draw.text((x + 14, y + 780), f"{moment:02}s", fill="white")
    sheet.save(CACHE / "contact-sheet.jpg", quality=93)
    first, loop = flight.render(0), flight.render(30)
    assert np.array_equal(first, loop), "Visual loop must repeat exactly"
    last = flight.render(30 - 1 / FPS)
    adjacent = flight.render(1 / FPS)
    print("Loop verified: frame(0) == frame(30)")
    print("Average adjacent-frame delta:", float(np.abs(adjacent.astype(float) - first).mean()))
    print("Average loop-seam delta:", float(np.abs(last.astype(float) - first).mean()))
    print(CACHE / "contact-sheet.jpg")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true", help="Render a contact sheet and verify the loop")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--output", type=Path, default=EXPORT / "viaje-infinito.mp4")
    args = parser.parse_args()
    if args.preview:
        preview()
    else:
        render_video(args.width, args.height, args.fps, args.output.resolve(), args.silent)
