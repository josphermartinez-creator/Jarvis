#!/usr/bin/env python3
"""30 seconds of a fluffy baby chick pecking grain in a grassy farmyard.

A continuous 2.5D animation from matching AI-generated feeding poses. Optical
flow interpolates the head movement; timed grain pickup, swallowing, blinks,
feather/grass motion and camera movement are composited separately.
"""
from __future__ import annotations

import argparse
import hashlib
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
ASSETS = ROOT / "assets" / "chick"
CACHE = ROOT / ".cache" / "chick"
EXPORT = ROOT / "exports"
DURATION, FPS = 30, 30
TAU = math.tau
PECKS = (0.95, 1.85, 2.55, 4.45, 5.20, 5.95, 8.10, 8.85, 9.65,
         11.10, 11.90, 12.75, 15.05, 15.75, 16.55, 18.70, 19.40, 20.20,
         22.0, 22.75, 23.55, 26.20, 27.10, 27.80)
BLINKS = (3.45, 7.05, 10.50, 13.80, 17.75, 21.10, 24.85, 28.90)
POSE_STEPS = 49
cv2.setNumThreads(2)


def smoothstep(lo, hi, x):
    x = np.clip((x - lo) / (hi - lo), 0, 1)
    return x * x * (3 - 2 * x)


def feeding_state(t):
    """0 is head up, 1 is contact with the grain; dt tracks the nearest peck."""
    event = min(range(len(PECKS)), key=lambda i: abs(t - PECKS[i]))
    for i, moment in enumerate(PECKS):
        if -0.24 <= t - moment <= 0.40:
            event = i
            break
    dt = t - PECKS[event]
    pose = float(smoothstep(-0.24, -0.02, dt) * (1 - smoothstep(0.07, 0.40, dt)))
    grain = float(smoothstep(0.07, 0.13, dt) * (1 - smoothstep(0.29, 0.39, dt)))
    swallow = float(smoothstep(0.22, 0.37, dt)) if 0.07 < dt < 0.45 else 0.0
    return pose, grain, swallow, dt, event


def blink_state(t):
    return max(float(smoothstep(-0.13, -0.02, t - c) * (1 - smoothstep(0.06, 0.26, t - c))) for c in BLINKS)


def load_plate(name):
    path = ASSETS / name
    image = cv2.imread(str(path))
    if image is None:
        raise FileNotFoundError(path)
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


class ChickFilm:
    def __init__(self, width=1080, height=1920):
        if width <= 0 or height <= 0 or width % 2 or height % 2:
            raise ValueError("Dimensions must be positive even numbers")
        CACHE.mkdir(parents=True, exist_ok=True)
        self.width, self.height = width, height
        self.up = load_plate("feeding-up.jpg")
        self.down = load_plate("feeding-down.jpg")
        self.closed = load_plate("feeding-closed.jpg")
        if self.up.shape != self.down.shape or self.up.shape != self.closed.shape:
            raise ValueError("Feeding plates must have matching dimensions")
        self.h, self.w = self.up.shape[:2]
        if (self.w, self.h) != (848, 1264):
            raise ValueError("Animation landmarks require the supplied 848 x 1264 plates")
        self.y, self.x = np.mgrid[:self.h, :self.w].astype(np.float32)
        self.poses = self.build_poses()
        self.body = self.weight(365, 679, 207, 185, power=4)
        self.wing = self.weight(269, 663, 112, 94)
        self.head = self.weight(552, 664, 173, 202, power=4)
        self.tail = self.weight(292, 510, 106, 69)
        self.jaw = self.weight(589, 837, 39, 29)
        # Preserve the feet and feed while giving the clover a light breeze.
        plant_edges = (np.abs(self.x - self.w / 2) / (self.w / 2)) ** 3
        self.grass = plant_edges * smoothstep(490, 950, self.y)
        self.grass *= 1 - np.maximum(self.body, self.head)
        cx, cy, rx, ry = 544, 731, 61, 69
        x0, x1, y0, y1 = cx - 87, cx + 88, cy - 98, cy + 99
        gx, gy = self.x[y0:y1, x0:x1], self.y[y0:y1, x0:x1]
        radius = np.sqrt(((gx - cx) / rx) ** 2 + ((gy - cy) / ry) ** 2)
        eye_mask = 1 - smoothstep(0.80, 1.16, radius)
        target = self.closed[y0:y1, x0:x1].astype(np.float32)
        original = self.up[y0:y1, x0:x1].astype(np.float32)
        annulus = (radius > 1.10) & (radius < 1.38)
        target += np.median(original[annulus] - target[annulus], axis=0)
        self.eye_patch = (x0, x1, y0, y1, gx, gy, eye_mask, np.clip(target, 0, 255))
        rng = np.random.default_rng(8412)
        self.motes = np.column_stack([rng.uniform(30, self.w - 30, 22), rng.uniform(240, 470, 22), rng.uniform(0.8, 1.9, 22), rng.uniform(0, TAU, 22)])
        r = ((self.x - self.w / 2) / self.w) ** 2 + ((self.y - self.h / 2) / self.h) ** 2
        self.vignette = (1 - r * 0.16)[..., None]

    def weight(self, cx, cy, rx, ry, power=2):
        return np.exp(-(np.abs((self.x - cx) / rx) ** power + np.abs((self.y - cy) / ry) ** power)).astype(np.float32)

    def build_poses(self):
        digest = hashlib.sha256(b"chick-pose-bank-v5-49")
        digest.update(self.up.tobytes())
        digest.update(self.down.tobytes())
        cache = CACHE / f"poses-{digest.hexdigest()[:14]}.npy"
        if cache.exists():
            return np.load(cache, mmap_mode="r")
        print("Building motion-interpolated feeding poses", flush=True)
        dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        dis.setFinestScale(0)
        ga = cv2.cvtColor(self.up, cv2.COLOR_RGB2GRAY)
        gb = cv2.cvtColor(self.down, cv2.COLOR_RGB2GRAY)
        forward = dis.calc(ga, gb, None)
        backward = dis.calc(gb, ga, None)
        # Only the moving chick changes pose. Background and food stay stable.
        matte = np.zeros((self.h, self.w), np.float32)
        cv2.rectangle(matte, (317, 425), (773, 958), 1, -1)
        matte = cv2.GaussianBlur(matte, (0, 0), 16)[..., None]
        temporary = cache.with_suffix(".partial.npy")
        bank = np.lib.format.open_memmap(temporary, mode="w+", dtype=np.uint8,
                                         shape=(POSE_STEPS, self.h, self.w, 3))
        for index, amount in enumerate(np.linspace(0, 1, POSE_STEPS)):
            amount = float(amount)
            ax, ay = self.x.copy(), self.y.copy()
            bx, by = self.x.copy(), self.y.copy()
            # Fixed-point inverse transport prevents the double outlines caused
            # by simply dissolving two different head positions.
            for _ in range(4):
                fa = cv2.remap(forward, ax, ay, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
                fb = cv2.remap(backward, bx, by, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
                ax = self.x - amount * fa[..., 0]
                ay = self.y - amount * fa[..., 1]
                bx = self.x - (1 - amount) * fb[..., 0]
                by = self.y - (1 - amount) * fb[..., 1]
            a = cv2.remap(self.up, ax, ay, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
            b = cv2.remap(self.down, bx, by, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
            mix = float(smoothstep(0.10, 0.90, amount))
            moving = cv2.addWeighted(a, 1 - mix, b, mix, 0).astype(np.float32)
            bank[index] = np.clip(moving * matte + self.up.astype(np.float32) * (1 - matte), 0, 255).astype(np.uint8)
        bank.flush()
        del bank
        temporary.replace(cache)
        return np.load(cache, mmap_mode="r")

    def pose_frame(self, amount):
        value = float(np.clip(amount, 0, 1)) * (POSE_STEPS - 1)
        left = int(value)
        right = min(POSE_STEPS - 1, left + 1)
        return cv2.addWeighted(self.poses[left], 1 - (value - left), self.poses[right], value - left, 0).astype(np.float32)

    def apply_blink(self, frame, amount):
        if amount <= 0.0001:
            return
        x0, x1, y0, y1, gx, gy, mask, target = self.eye_patch
        lid = 731 - 69 * 1.45 + 69 * 3.0 * amount
        # A curved eyelid descends over the eye during the blink.
        lid = lid + (gx - 544) * 0.35
        shutter = 1 - smoothstep(lid - 3, lid + 3, gy)
        alpha = (mask * shutter * min(1, amount * 6))[..., None]
        roi = frame[y0:y1, x0:x1]
        roi *= 1 - alpha
        roi += target * alpha

    @staticmethod
    def grain(layer, x, y, radius=4.0, angle=0, opacity=1.0):
        if opacity <= 0:
            return
        center = (int(x * 16), int(y * 16))
        axes = (max(10, int(radius * 16)), max(8, int(radius * 0.62 * 16)))
        dark = tuple(float(v * opacity) for v in (115, 69, 24, 255))
        light = tuple(float(v * opacity) for v in (222, 173, 79, 255))
        cv2.ellipse(layer, center, axes, angle, 0, 360, dark, -1, cv2.LINE_AA, 4)
        inner = (int((x - 0.55) * 16), int((y - 0.7) * 16))
        cv2.ellipse(layer, inner, (max(8, axes[0] - 12), max(6, axes[1] - 9)), angle, 0, 360, light, -1, cv2.LINE_AA, 4)

    def food(self, frame, pose, grain_amount, swallow, dt, event):
        if grain_amount <= 0 and not (0.09 < dt < 0.48 and event % 3 != 1):
            return
        layer = np.zeros((self.h, self.w, 4), np.float32)
        if grain_amount > 0:
            x = 600 - pose * 6 - swallow * 15
            y = 849 + pose * 49 - swallow * 17
            self.grain(layer, x, y, 4.1, event * 37 + swallow * 75, grain_amount)
        # One or two tiny grains bounce near the pile as the beak picks one up.
        if 0.09 < dt < 0.48 and event % 3 != 1:
            p = (dt - 0.09) / 0.39
            x = 599 + p * (13 + event % 4 * 3)
            y = 906 - math.sin(math.pi * p) * 12 + p * 4
            self.grain(layer, x, y, 2.1, event * 31 + p * 100, math.sin(math.pi * p) ** 0.55 * 0.75)
        alpha = np.clip(layer[..., 3:4] / 255, 0, 1)
        frame *= 1 - alpha
        frame += layer[..., :3]

    def life_motion(self, frame, t, pose, dt):
        breath = math.sin(TAU * t / 3.1)
        dx = -(self.x - 352) * self.body * (0.0048 * breath)
        dy = -(self.y - 779) * self.body * (0.0038 * breath)
        dy -= self.head * (0.60 * math.sin(TAU * t / 5.2)) * (1 - pose)
        ruffle = sum(math.sin((t - c) * 25) * math.exp(-((t - c) / 0.26) ** 2) for c in (4.0, 10.8, 16.95, 25.2))
        angle = ruffle * 0.03
        dx += self.wing * (self.y - 680) * angle
        dy -= self.wing * (self.x - 311) * angle
        dy += self.tail * math.sin(t * 1.5 + 0.7) * 0.9
        # A tiny jaw movement after pickup, not a talking/mammalian chewing loop.
        swallow_motion = math.sin(max(0, dt - 0.32) * 30) * math.exp(-((dt - 0.43) / 0.12) ** 2)
        dy += self.jaw * swallow_motion * 1.2
        dx += self.grass * np.sin(self.y * 0.010 + t * 0.82) * 1.25
        dy += self.grass * np.sin(self.x * 0.018 + t * 0.68) * 0.40
        return cv2.remap(frame, self.x + dx, self.y + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)

    def light(self, frame, t):
        specks = np.zeros((self.h, self.w), np.float32)
        for x, y, radius, phase in self.motes:
            xx = x + math.sin(t * 0.38 + phase) * 10 + t * 0.3
            yy = y + math.cos(t * 0.42 + phase) * 7
            if xx >= self.w - 5:
                continue
            amount = 0.03 + 0.018 * math.sin(t + phase)
            cv2.circle(specks, (int(xx * 16), int(yy * 16)), int(radius * 16), amount, -1, cv2.LINE_AA, 4)
        specks = cv2.GaussianBlur(specks, (0, 0), 0.85)
        frame += (np.array([255, 244, 207], np.float32) - frame) * specks[..., None]
        frame *= self.vignette
        return frame

    def camera(self, frame, t):
        # Continuous gentle move closer, then back out; no scene cuts or black fades.
        zoom = 1.035 + 0.23 * (math.sin(math.pi * t / DURATION) ** 2)
        scale = max(self.width / self.w, self.height / self.h) * zoom
        cx = self.w / 2 + 22 + (532 - self.w / 2) * (1 - 1 / zoom)
        cy = self.h / 2 + 20 + (754 - self.h / 2) * (1 - 1 / zoom)
        cx += 2.2 * math.sin(t * 0.18)
        cy += 2.0 * math.sin(t * 0.15 + 1)
        half_x, half_y = self.width / scale / 2, self.height / scale / 2
        cx = float(np.clip(cx, half_x + 0.5, self.w - half_x - 0.5))
        cy = float(np.clip(cy, half_y + 0.5, self.h - half_y - 0.5))
        matrix = np.array([[scale, 0, self.width / 2 - cx * scale], [0, scale, self.height / 2 - cy * scale]], np.float32)
        return cv2.warpAffine(frame, matrix, (self.width, self.height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)

    def render(self, t):
        t = float(np.clip(t, 0, DURATION))
        pose, grain, swallow, dt, event = feeding_state(t)
        frame = self.pose_frame(pose)
        self.apply_blink(frame, blink_state(t) * (1 - float(smoothstep(0.015, 0.12, pose))))
        self.food(frame, pose, grain, swallow, dt, event)
        frame = self.life_motion(frame, t, pose, dt)
        frame = self.light(frame, t)
        return self.camera(np.clip(frame, 0, 255).astype(np.uint8), t)


def make_farm_audio(path, sample_rate=48000):
    """Quiet original farmyard sound design: soft breeze, peeps and seed taps."""
    print("Synthesizing farmyard ambience", flush=True)
    n = DURATION * sample_rate
    t = np.arange(n, dtype=np.float64) / sample_rate
    rng = np.random.default_rng(1603)
    frequencies = fft.rfftfreq(n, 1 / sample_rate)
    shape = np.exp(-frequencies / 2200) * (1 - np.exp(-(frequencies / 130) ** 2))
    stereo = np.zeros((n, 2), np.float64)
    for channel in range(2):
        noise = fft.irfft(fft.rfft(rng.standard_normal(n)) * shape, n)
        noise /= max(1e-8, float(np.std(noise)))
        amplitude = 0.008 * (0.82 + 0.14 * np.sin(t * 0.55 + channel * 0.8))
        stereo[:, channel] += noise * amplitude
    for i, moment in enumerate(PECKS):
        length = int(0.055 * sample_rate)
        tt = np.arange(length) / sample_rate
        dry_noise = rng.standard_normal(length)
        click = (dry_noise * 0.7 + np.sin(tt * TAU * 1850) * 0.3) * np.exp(-tt * 110) * (1 - np.exp(-tt * 700)) * 0.011
        start = int(moment * sample_rate)
        stereo[start:start + length, 0] += click * 0.85
        stereo[start:start + length, 1] += click
    # Gentle original cheeps during feeding pauses, not speech or sampled music.
    chirps = (0.22, 0.49, 3.32, 3.62, 6.88, 7.20, 10.30, 13.70, 14.05, 17.52, 17.85, 20.98, 24.75, 25.04, 28.78, 29.16)
    for index, moment in enumerate(chirps):
        duration = 0.16 + (index % 3) * 0.035
        length = int(duration * sample_rate)
        tt = np.arange(length) / sample_rate
        p = tt / tt[-1]
        freq = 2650 + 950 * np.sin(p * math.pi * 0.9) - p * 650 + 50 * np.sin(tt * 72)
        phase = np.cumsum(freq) * TAU / sample_rate
        chirp = (np.sin(phase) + 0.045 * np.sin(phase * 2)) * np.sin(math.pi * p) ** 2 * 0.031
        start = int(moment * sample_rate)
        stereo[start:start + length, 0] += chirp * 0.87
        stereo[start:start + length, 1] += chirp
    stereo *= smoothstep(0, 0.18, t)[:, None] * (1 - smoothstep(29.40, 30, t))[:, None]
    pcm = (np.clip(stereo * 2.2, -0.95, 0.95) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(pcm.tobytes())


def render_video(output, width=1080, height=1920, fps=30, silent=False):
    if fps <= 0:
        raise ValueError("FPS must be positive")
    CACHE.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    film = ChickFilm(width, height)
    audio = CACHE / "farmyard.wav"
    if not silent:
        make_farm_audio(audio)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-"]
    if not silent:
        command += ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "192k"]
    command += ["-c:v", "libx264", "-preset", "fast", "-crf", "19", "-maxrate", "10M", "-bufsize", "20M", "-threads", "2", "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.2", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-movflags", "+faststart", "-t", str(DURATION), "-metadata", "title=Un pequeno banquete - Pollito comiendo", "-metadata", "comment=Original 2.5D chick feeding animation with AI-generated plates and synthesized farmyard ambience.", str(output)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    start = time.monotonic()
    try:
        total = DURATION * fps
        for index in range(total):
            image = film.render(index / fps)
            process.stdin.write(image.tobytes())
            if index % fps == 0:
                print(f"Frame {index:03d}/{total} · {index/fps:02.0f}s / 30s · elapsed {time.monotonic()-start:.1f}s", flush=True)
            if index == round(fps * 12.25):
                Image.fromarray(image).save(output.with_suffix(".jpg"), quality=94)
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("Video encoding failed")
    except BaseException:
        if process.poll() is None:
            process.kill()
            process.wait()
        output.unlink(missing_ok=True)
        raise
    print(f"Completed: {output} · {output.stat().st_size/1e6:.1f} MB · {time.monotonic()-start:.1f}s", flush=True)


def preview():
    film = ChickFilm(360, 640)
    moments = (0.4, 0.95, 1.20, 7.08, 11.9, 12.2, 20.2, 24.88, 29.5)
    sheet = Image.new("RGB", (360 * 3, 672 * 3), "#30281b")
    draw = ImageDraw.Draw(sheet)
    for index, moment in enumerate(moments):
        frame = Image.fromarray(film.render(moment))
        x, y = index % 3 * 360, index // 3 * 672
        sheet.paste(frame, (x, y))
        draw.text((x + 12, y + 648), f"{moment:.2f} s", fill="#f6eacb")
    target = CACHE / "contact-sheet.jpg"
    sheet.save(target, quality=94)
    print(target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--output", type=Path, default=EXPORT / "pollito-comiendo.mp4")
    args = parser.parse_args()
    if args.preview:
        preview()
    else:
        render_video(args.output.resolve(), args.width, args.height, args.fps, args.silent)
