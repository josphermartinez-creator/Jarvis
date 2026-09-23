#!/usr/bin/env python3
"""Photographic-style, 30-second portrait of a giraffe calf chewing acacia.

This is a 2.5D animation of AI-generated photographic plates, not wildlife
footage. A fixed camera, a restricted mandible mask and local eyelid patches
keep the calf's anatomy, coat pattern and background consistent. The only
intentional action is quiet chewing, with a few incidental natural blinks.
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
ASSETS = ROOT / "assets" / "giraffe"
CACHE = ROOT / ".cache" / "giraffe"
EXPORT = ROOT / "exports"
DURATION, FPS = 30, 30
TAU = math.tau
JAW_STEPS = 41
BLINKS = (4.4, 10.6, 17.35, 24.2)
cv2.setNumThreads(2)


def smoothstep(lo, hi, x):
    x = np.clip((x - lo) / (hi - lo), 0, 1)
    return x * x * (3 - 2 * x)


def chewing_state(t):
    """A gently variable, elliptical ruminant chew, periodic over 30 seconds."""
    t = float(t % DURATION)
    turn = TAU * t / DURATION
    phase = 25 * turn + 0.80 * math.sin(3 * turn) + 0.22 * math.sin(5 * turn) + 0.8
    amplitude = 0.87 + 0.09 * math.sin(2 * turn + 0.4)
    opening = (0.5 - 0.5 * math.cos(phase)) ** 0.96 * amplitude
    lateral = 3.6 * math.sin(phase) * (0.91 + 0.09 * math.sin(2 * turn))
    return opening, lateral, phase, turn


def blink_state(t):
    t = float(t % DURATION)
    return max(float(smoothstep(-0.12, -0.01, t - c) * (1 - smoothstep(0.065, 0.235, t - c))) for c in BLINKS)


def load_plate(name):
    path = ASSETS / name
    image = cv2.imread(str(path))
    if image is None:
        raise FileNotFoundError(path)
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


class GiraffeFilm:
    def __init__(self, width=1080, height=1920):
        if width <= 0 or height <= 0 or width % 2 or height % 2:
            raise ValueError("Output dimensions must be positive even integers")
        CACHE.mkdir(parents=True, exist_ok=True)
        self.width, self.height = width, height
        self.rest = load_plate("calf-rest.png")
        self.chew = load_plate("calf-chew.png")
        self.blink = load_plate("calf-blink.png")
        if self.rest.shape != self.chew.shape or self.rest.shape != self.blink.shape:
            raise ValueError("All giraffe plates must have exactly matching dimensions")
        self.h, self.w = self.rest.shape[:2]
        if (self.w, self.h) != (768, 1376):
            raise ValueError("Local anatomy masks require the supplied 768 x 1376 images")
        self.y, self.x = np.mgrid[:self.h, :self.w].astype(np.float32)
        # The fixed rectangle only supplies texture to the masked lower face.
        self.jaw_box = (370, 700, 631, 844)
        x0, y0, x1, y1 = self.jaw_box
        self.jy, self.jx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        radius = np.sqrt(((self.jx - 513) / 108) ** 2 + ((self.jy - 776) / 51) ** 2)
        self.jaw_mask = (1 - smoothstep(0.69, 1.13, radius))[..., None]
        self.jaw_poses = self.build_jaw_poses()
        self.lateral_weight = (smoothstep(749, 775, self.y) * (1 - smoothstep(820, 842, self.y))
                               * smoothstep(410, 458, self.x) * (1 - smoothstep(589, 626, self.x)))
        # The leaf spray bends gently about the point held between the lips.
        self.leaf_weight = (smoothstep(591, 627, self.x) * smoothstep(662, 698, self.y)
                            * (1 - smoothstep(995, 1031, self.y)))
        self.eyes = []
        for cx, cy, rx, ry in ((318, 574, 49, 32), (522, 572, 22, 30)):
            ex0, ex1 = max(0, int(cx - rx * 1.45)), min(self.w, int(cx + rx * 1.45 + 1))
            ey0, ey1 = max(0, int(cy - ry * 1.55)), min(self.h, int(cy + ry * 1.55 + 1))
            xx, yy = self.x[ey0:ey1, ex0:ex1], self.y[ey0:ey1, ex0:ex1]
            r = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
            mask = 1 - smoothstep(0.80, 1.22, r)
            original = self.rest[ey0:ey1, ex0:ex1].astype(np.float32)
            target = self.blink[ey0:ey1, ex0:ex1].astype(np.float32)
            edge = (r > 1.17) & (r < 1.42)
            target += np.median(original[edge] - target[edge], axis=0)
            self.eyes.append((ex0, ex1, ey0, ey1, cx, cy, rx, ry, xx, yy, mask, np.clip(target, 0, 255)))
        # A fixed cover transform: no pans, zooms, cuts, or clipped ears/horns.
        scale = max(width / self.w, height / self.h)
        self.camera_matrix = np.array([[scale, 0, (width - self.w * scale) / 2],
                                       [0, scale, (height - self.h * scale) / 2]], np.float32)

    def build_jaw_poses(self):
        """Precompute only the small jaw patch, with atomically published cache."""
        x0, y0, x1, y1 = self.jaw_box
        a = self.rest[y0:y1, x0:x1]
        b = self.chew[y0:y1, x0:x1]
        digest = hashlib.sha256(b"giraffe-local-jaw-v1-41")
        digest.update(a.tobytes())
        digest.update(b.tobytes())
        path = CACHE / f"jaw-{digest.hexdigest()[:14]}.npy"
        if path.is_file():
            return np.load(path, mmap_mode="r")
        print("Preparing subtle mandibular motion", flush=True)
        # Calculate flow with a little context so nostrils and the upper skull
        # are stable references. They are never copied into the moving patch.
        pad = 48
        px0, py0 = x0 - pad, y0 - pad
        px1, py1 = x1 + pad, y1 + pad
        ca = self.rest[py0:py1, px0:px1]
        cb = self.chew[py0:py1, px0:px1]
        dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        dis.setFinestScale(0)
        forward = dis.calc(cv2.cvtColor(ca, cv2.COLOR_RGB2GRAY), cv2.cvtColor(cb, cv2.COLOR_RGB2GRAY), None)
        backward = dis.calc(cv2.cvtColor(cb, cv2.COLOR_RGB2GRAY), cv2.cvtColor(ca, cv2.COLOR_RGB2GRAY), None)
        yy, xx = np.mgrid[:ca.shape[0], :ca.shape[1]].astype(np.float32)
        temporary = path.with_suffix(".partial.npy")
        bank = np.lib.format.open_memmap(temporary, mode="w+", dtype=np.uint8,
                                         shape=(JAW_STEPS, y1 - y0, x1 - x0, 3))
        for index, amount in enumerate(np.linspace(0, 1, JAW_STEPS)):
            amount = float(amount)
            ax, ay, bx, by = xx.copy(), yy.copy(), xx.copy(), yy.copy()
            for _ in range(3):
                fa = cv2.remap(forward, ax, ay, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
                fb = cv2.remap(backward, bx, by, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
                ax, ay = xx - amount * fa[..., 0], yy - amount * fa[..., 1]
                bx, by = xx - (1 - amount) * fb[..., 0], yy - (1 - amount) * fb[..., 1]
            aa = cv2.remap(ca, ax, ay, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
            bb = cv2.remap(cb, bx, by, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
            mixed = cv2.addWeighted(aa, 1 - amount, bb, amount, 0)
            bank[index] = mixed[pad:pad + y1 - y0, pad:pad + x1 - x0]
        bank.flush()
        del bank
        temporary.replace(path)
        return np.load(path, mmap_mode="r")

    def mouth(self, frame, opening):
        value = float(np.clip(opening, 0, 1)) * (JAW_STEPS - 1)
        low, high = int(value), min(JAW_STEPS - 1, int(value) + 1)
        patch = cv2.addWeighted(self.jaw_poses[low], 1 - (value - low), self.jaw_poses[high], value - low, 0)
        x0, y0, x1, y1 = self.jaw_box
        original = frame[y0:y1, x0:x1].astype(np.float32)
        composite = original * (1 - self.jaw_mask) + patch.astype(np.float32) * self.jaw_mask
        frame[y0:y1, x0:x1] = np.clip(composite + 0.5, 0, 255).astype(np.uint8)

    def eyelids(self, frame, closure):
        if closure <= 0.0001:
            return
        for x0, x1, y0, y1, cx, cy, rx, ry, xx, yy, mask, target in self.eyes:
            lid = cy - ry * 1.5 + ry * 3.1 * closure
            lid -= 2.0 * ((xx - cx) / rx) ** 2 * (1 - closure)
            shutter = 1 - smoothstep(lid - 2.6, lid + 2.6, yy)
            alpha = (mask * shutter * min(1, closure * 6))[..., None]
            roi = frame[y0:y1, x0:x1].astype(np.float32)
            frame[y0:y1, x0:x1] = np.clip(roi * (1 - alpha) + target * alpha + 0.5, 0, 255).astype(np.uint8)

    def native_frame(self, t):
        t = float(t % DURATION)
        opening, lateral, phase, turn = chewing_state(t)
        frame = self.rest.copy()
        self.mouth(frame, opening)
        self.eyelids(frame, blink_state(t))
        # A lateral lower-mandible stroke, not whole-head wobble or lip-sync.
        dx = self.lateral_weight * (-lateral)
        dy = self.lateral_weight * (0.33 * math.sin(phase + 0.25))
        angle = 0.0038 * math.sin(phase - 0.20) + 0.0007 * math.sin(3 * turn)
        dx += self.leaf_weight * (self.y - 745) * angle
        dy -= self.leaf_weight * (self.x - 593) * angle
        return cv2.remap(frame, self.x + dx, self.y + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)

    def render(self, t):
        frame = self.native_frame(t)
        return cv2.warpAffine(frame, self.camera_matrix, (self.width, self.height),
                              flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT_101)


def make_savanna_audio(path, sample_rate=48000):
    """Very quiet original wind/leaf ambience. No voice, music or animal calls."""
    print("Synthesizing restrained savanna ambience", flush=True)
    n = DURATION * sample_rate
    t = np.arange(n, dtype=np.float64) / sample_rate
    turn = TAU * t / DURATION
    rng = np.random.default_rng(31728)
    frequency = fft.rfftfreq(n, 1 / sample_rate)
    wind_shape = np.exp(-(frequency / 1100) ** 1.25) * (1 - np.exp(-(frequency / 85) ** 2))
    leaf_shape = np.exp(-(frequency / 4500) ** 1.2) * (1 - np.exp(-(frequency / 700) ** 2))
    phase = 25 * turn + 0.80 * np.sin(3 * turn) + 0.22 * np.sin(5 * turn) + 0.8
    stereo = np.zeros((n, 2), np.float64)
    for channel in range(2):
        wind = fft.irfft(fft.rfft(rng.standard_normal(n)) * wind_shape, n)
        wind /= max(1e-8, float(np.std(wind)))
        leaf = fft.irfft(fft.rfft(rng.standard_normal(n)) * leaf_shape, n)
        leaf /= max(1e-8, float(np.std(leaf)))
        breeze = 0.0075 * (0.83 + 0.12 * np.sin(2 * turn + channel * 0.2))
        tiny_rustle = 0.0018 * (0.25 + 0.75 * np.maximum(0, np.cos(phase - 0.7)) ** 4)
        stereo[:, channel] = wind * breeze + leaf * tiny_rustle
    pcm = (np.clip(stereo * 2.0, -0.9, 0.9) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm.tobytes())


def render_video(output, width=1080, height=1920, fps=30, silent=False):
    if fps <= 0:
        raise ValueError("FPS must be positive")
    CACHE.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    film = GiraffeFilm(width, height)
    audio = CACHE / "savanna.wav"
    if not silent:
        make_savanna_audio(audio)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-"]
    if not silent:
        command += ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "192k"]
    command += ["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-maxrate", "12M", "-bufsize", "24M", "-threads", "2", "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.2", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-movflags", "+faststart", "-t", str(DURATION), "-metadata", "title=Jirafa bebe - Hojas de acacia", "-metadata", "comment=AI-generated photographic-style animation. Not real wildlife footage. Original subtle wind and leaf ambience.", str(output)]
    encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
    start = time.monotonic()
    try:
        total = DURATION * fps
        for index in range(total):
            image = film.render(index / fps)
            encoder.stdin.write(image.tobytes())
            if index % fps == 0:
                print(f"Frame {index:03d}/{total} · {index/fps:02.0f}s / 30s · elapsed {time.monotonic()-start:.1f}s", flush=True)
            if index == 0:
                Image.fromarray(image).save(output.with_suffix(".jpg"), quality=96)
        encoder.stdin.close()
        if encoder.wait() != 0:
            raise RuntimeError("Video encoding failed")
    except BaseException:
        if encoder.poll() is None:
            encoder.kill()
            encoder.wait()
        output.unlink(missing_ok=True)
        raise
    print(f"Completed: {output} · {output.stat().st_size/1e6:.1f} MB · {time.monotonic()-start:.1f}s", flush=True)


def preview():
    film = GiraffeFilm(432, 768)
    moments = (0, 0.36, 0.72, 4.42, 12.2, 24.22)
    sheet = Image.new("RGB", (432 * 3, 800 * 2), "#292d26")
    draw = ImageDraw.Draw(sheet)
    for index, moment in enumerate(moments):
        image = Image.fromarray(film.render(moment))
        x, y = index % 3 * 432, index // 3 * 800
        sheet.paste(image, (x, y))
        draw.text((x + 12, y + 778), f"{moment:.2f} s", fill="#e5e6d9")
    target = CACHE / "contact-sheet.jpg"
    sheet.save(target, quality=95)
    detail = Image.new("RGB", (700 * 3, 470), "#292d26")
    for index, moment in enumerate((0, 0.36, 0.72)):
        frame = Image.fromarray(film.native_frame(moment))
        detail.paste(frame.crop((285, 637, 635, 862)).resize((700, 450), Image.Resampling.LANCZOS), (index * 700, 0))
    detail.save(CACHE / "chewing-details.jpg", quality=96)
    np.testing.assert_array_equal(film.render(0), film.render(30))
    print("Exact 30-second visual loop verified")
    print(target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--output", type=Path, default=EXPORT / "jirafa-bebe.mp4")
    args = parser.parse_args()
    if args.preview:
        preview()
    else:
        render_video(args.output.resolve(), args.width, args.height, args.fps, args.silent)
