#!/usr/bin/env python3
"""A 30-second, three-shot animated portrait of a baby hippo by an African river.

AI-generated still plates are animated with local deformation fields, eyelid
matting, moving water, breathing, ear twitches, subtle camera moves and ripples.
This is a stylized 2.5D animation, not recorded wildlife footage.
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
ASSETS = ROOT / "assets" / "hippo"
CACHE = ROOT / ".cache" / "hippo"
EXPORT = ROOT / "exports"
DURATION = 30
FPS = 30
TAU = math.tau
cv2.setNumThreads(2)


def smoothstep(lo, hi, value):
    x = np.clip((value - lo) / (hi - lo), 0, 1)
    return x * x * (3 - 2 * x)


# Coordinates are in the native 768 x 1376 plates, not output pixels.
HEAD_OUTLINE = [(336, 505), (355, 543), (379, 507), (424, 491), (493, 494), (535, 517), (551, 485), (571, 480), (580, 496), (580, 527), (586, 551), (590, 580), (592, 603), (625, 633), (650, 663), (654, 704), (641, 738), (625, 765), (587, 785)]
SCENES = [
    dict(name="river-baby", title="En la orilla", start=0,
         eyes=[(405, 576, 30, 40), (581, 560, 17, 30)],
         head=(477, 650, 190, 190), pivot=(457, 797), body=(331, 803, 214, 220),
         ears=[(337, 533, 37, 41, 356, 553), (561, 507, 27, 37, 554, 533)],
         nose=(539, 674, 120, 87), paw=(351, 1029, 60, 80),
         rings=[(351, 1102, 0.0), (490, 1072, 1.3), (198, 995, 2.1)],
         outline=HEAD_OUTLINE + [(559, 817), (562, 852), (545, 895), (536, 949), (541, 995), (545, 1031), (540, 1051), (511, 1067), (472, 1067), (447, 1051), (437, 1024), (438, 968), (414, 951), (410, 974), (413, 1021), (416, 1056), (405, 1078), (384, 1092), (334, 1092), (302, 1081), (292, 1057), (283, 998), (267, 983), (241, 992), (196, 997), (177, 986), (168, 955), (161, 907), (150, 880), (128, 821), (113, 761), (115, 709), (133, 657), (158, 622), (192, 605), (234, 587), (273, 580), (312, 573), (328, 560), (316, 554), (312, 524), (320, 510)],
         water=[(0, 420), (768, 420), (768, 1157), (649, 1143), (556, 1144), (497, 1120), (439, 1117), (362, 1120), (278, 1150), (182, 1178), (76, 1164), (0, 1160)],
         camera=(1.025, 1.135, 461, 646), blink_times=[2.65, 6.55, 7.08, 9.25],
         ear_times=[1.3, 5.0, 8.1], paw_time=4.65),
    dict(name="river-close", title="De cerquita", start=10,
         eyes=[(274, 522, 41, 54), (565, 516, 28, 45)],
         head=(413, 650, 265, 253), pivot=(406, 901), body=(379, 822, 288, 303),
         ears=[(194, 440, 50, 58, 234, 472), (578, 429, 42, 58, 546, 467)],
         nose=(453, 709, 176, 124), paw=(255, 1106, 70, 90),
         rings=[(251, 1193, 0.3), (505, 1190, 1.8)],
         outline=[(158, 425), (165, 404), (190, 387), (215, 398), (237, 437), (277, 416), (337, 392), (414, 389), (475, 403), (527, 435), (551, 399), (574, 379), (599, 391), (614, 418), (612, 454), (593, 474), (574, 481), (583, 527), (593, 574), (618, 607), (646, 665), (656, 718), (651, 760), (671, 788), (677, 844), (657, 899), (625, 946), (610, 985), (593, 1027), (590, 1083), (588, 1142), (579, 1177), (552, 1189), (485, 1186), (449, 1169), (432, 1120), (431, 1081), (411, 1052), (365, 1052), (341, 1087), (333, 1148), (322, 1178), (300, 1191), (240, 1189), (195, 1174), (178, 1142), (177, 1097), (169, 1044), (145, 1008), (117, 965), (97, 915), (84, 854), (79, 791), (86, 711), (103, 648), (130, 598), (169, 552), (194, 500), (171, 477)],
         water=[(0, 454), (768, 454), (768, 1376), (0, 1376)],
         camera=(1.02, 1.115, 414, 636), blink_times=[11.25, 14.9, 18.1, 18.65],
         ear_times=[12.0, 16.6, 19.3], paw_time=16.0),
    dict(name="river-rest", title="Un pequeño descanso", start=20,
         eyes=[(405, 576, 31, 41), (581, 560, 17, 32)],
         head=(480, 658, 189, 188), pivot=(456, 806), body=(332, 797, 258, 172),
         ears=[(337, 533, 36, 42, 356, 553), (561, 507, 27, 37, 554, 533)],
         nose=(539, 678, 120, 88), paw=(457, 995, 86, 67),
         rings=[(448, 1074, 0.0), (628, 1029, 1.7), (228, 972, 0.9)],
         outline=HEAD_OUTLINE + [(558, 826), (578, 865), (599, 897), (626, 945), (647, 974), (653, 998), (641, 1016), (581, 1018), (550, 1010), (524, 1030), (491, 1051), (437, 1054), (414, 1034), (378, 1000), (342, 978), (289, 964), (227, 956), (177, 941), (137, 920), (108, 902), (82, 881), (75, 828), (71, 750), (98, 688), (125, 651), (166, 627), (212, 604), (268, 597), (314, 581), (330, 559), (317, 551), (312, 524), (320, 510)],
         water=[(0, 427), (768, 427), (768, 1376), (0, 1376)],
         camera=(1.11, 1.025, 451, 710), blink_times=[21.3, 24.45, 27.6, 29.3],
         ear_times=[20.6, 23.9, 27.9], paw_time=23.5),
]


def blink_amount(t, times):
    """Quick close, a tiny closed hold, slower opening. No constant blinking."""
    amount = 0.0
    for center in times:
        dt = t - center
        close = float(smoothstep(-0.15, -0.025, dt))
        opening = 1 - float(smoothstep(0.075, 0.28, dt))
        amount = max(amount, close * opening)
    return amount


class RiverScene:
    def __init__(self, settings, width, height):
        self.cfg, self.width, self.height = settings, width, height
        path = ASSETS / f"{settings['name']}-open.jpg"
        raw = cv2.imread(str(path))
        closed = cv2.imread(str(ASSETS / f"{settings['name']}-closed.jpg"))
        if raw is None or closed is None:
            raise FileNotFoundError(f"Missing open/closed plates for {settings['name']}")
        self.open = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB).astype(np.float32)
        self.h, self.w = self.open.shape[:2]
        if (self.w, self.h) != (768, 1376):
            raise ValueError("Landmarks require the supplied 768 x 1376 plates")
        closed = cv2.resize(closed, (self.w, self.h), interpolation=cv2.INTER_CUBIC)
        self.closed = cv2.cvtColor(closed, cv2.COLOR_BGR2RGB).astype(np.float32)
        self.y, self.x = np.mgrid[:self.h, :self.w].astype(np.float32)
        self.body = self.weight(settings["body"], power=4)
        self.head = self.weight(settings["head"], power=4)
        self.nose = self.weight(settings["nose"], power=4)
        self.paw = self.weight(settings["paw"])
        self.ears = [(self.weight(ear[:4]), ear[4], ear[5]) for ear in settings["ears"]]
        animal = np.zeros((self.h, self.w), np.uint8)
        cv2.fillPoly(animal, [np.array(settings["outline"], np.int32)], 255)
        protected = cv2.dilate(animal, np.ones((27, 27), np.uint8))
        protected = cv2.GaussianBlur(protected.astype(np.float32) / 255, (0, 0), 6)
        water = np.zeros((self.h, self.w), np.uint8)
        cv2.fillPoly(water, [np.array(settings["water"], np.int32)], 255)
        water = cv2.GaussianBlur(water.astype(np.float32) / 255, (0, 0), 10)
        self.water = water * (1 - protected)
        # For the resting shot the little sand patch is not liquid.
        if settings["name"] == "river-rest":
            sand = np.zeros_like(water)
            cv2.ellipse(sand, (506, 1070), (184, 52), -3, 0, 360, 1, -1, cv2.LINE_AA)
            self.water *= 1 - cv2.GaussianBlur(sand, (0, 0), 12)
        self.water_depth = smoothstep(380, 1330, self.y)
        self.wind = (1 - protected) * (np.abs(self.x - 384) / 384) ** 2 * smoothstep(150, 850, self.y)
        self.eye_patches = []
        for cx, cy, rx, ry in settings["eyes"]:
            x0, x1 = int(cx - rx * 1.5), int(cx + rx * 1.5 + 1)
            y0, y1 = int(cy - ry * 1.5), int(cy + ry * 1.5 + 1)
            gx, gy = self.x[y0:y1, x0:x1], self.y[y0:y1, x0:x1]
            radial = np.sqrt(((gx - cx) / (rx * 1.24)) ** 2 + ((gy - cy) / (ry * 1.22)) ** 2)
            mask = 1 - smoothstep(0.72, 1.04, radial)
            target = self.closed[y0:y1, x0:x1].copy()
            original = self.open[y0:y1, x0:x1]
            rim = (radial > 0.94) & (radial < 1.25)
            # Local color matching hides tiny regeneration differences around lids.
            offset = np.median(original[rim] - target[rim], axis=0)
            target = np.clip(target + offset, 0, 255)
            self.eye_patches.append((x0, x1, y0, y1, cx, cy, rx, ry, gx, gy, mask, target))
        rng = np.random.default_rng(430 + settings["start"])
        self.motes = np.column_stack([rng.uniform(25, self.w - 25, 25), rng.uniform(235, 650, 25), rng.uniform(0.6, 1.8, 25), rng.uniform(0, TAU, 25)])
        self.glints = np.column_stack([rng.uniform(20, self.w - 20, 65), rng.uniform(745, 1335, 65), rng.uniform(0, TAU, 65)])
        vignette = ((self.x - self.w / 2) / self.w) ** 2 + ((self.y - self.h / 2) / self.h) ** 2
        self.vignette = (1 - 0.14 * vignette)[..., None]

    def weight(self, ellipse, power=2):
        cx, cy, rx, ry = ellipse
        return np.exp(-(np.abs((self.x - cx) / rx) ** power + np.abs((self.y - cy) / ry) ** power)).astype(np.float32)

    def eyelids(self, frame, t, override=None):
        closure = blink_amount(t, self.cfg["blink_times"]) if override is None else override
        if closure <= 0.0001:
            return
        for x0, x1, y0, y1, cx, cy, rx, ry, gx, gy, mask, target in self.eye_patches:
            # A descending curved eyelid rather than a full-frame dissolve.
            lid_y = cy - ry * 1.45 + ry * 2.95 * closure
            curved_lid = lid_y - ((gx - cx) / rx) ** 2 * 5 * (1 - closure)
            shutter = 1 - smoothstep(curved_lid - 2.5, curved_lid + 2.5, gy)
            matte = (mask * shutter * min(1, closure * 5))[..., None]
            roi = frame[y0:y1, x0:x1]
            roi *= 1 - matte
            roi += target * matte

    def deform(self, frame, t):
        cfg = self.cfg
        breath = math.sin(TAU * t / 4.65)
        bx, by, _, _ = cfg["body"]
        dx = -(self.x - bx) * self.body * (0.0085 * breath)
        dy = -(self.y - by) * self.body * (0.0045 * breath)
        # Head shifts and a tiny curious tilt, pinned softly at the neck.
        tilt = math.radians(1.15) * math.sin(TAU * (t - cfg["start"]) / 8.8 - 0.7)
        if cfg["name"] == "river-close":
            tilt += math.radians(1.2) * math.exp(-((t - 14.6) / 1.7) ** 2)
        pivot_x, pivot_y = cfg["pivot"]
        dx += self.head * ((self.y - pivot_y) * tilt - 3.2 * math.sin(TAU * t / 6.4))
        dy += self.head * (-(self.x - pivot_x) * tilt - 3.5 * math.sin(TAU * t / 5.6 + 0.35))
        for i, (mask, ex, ey) in enumerate(self.ears):
            twitch = 0.0
            for center in cfg["ear_times"]:
                dt = t - center - i * 0.13
                twitch += math.sin(dt * 23) * math.exp(-(dt / 0.24) ** 2)
            rotation = twitch * 0.14 * (1 if i == 0 else -1)
            dx += mask * (self.y - ey) * rotation
            dy -= mask * (self.x - ex) * rotation
        sniff = math.sin(TAU * t * 2.7) * math.exp(-((t - (cfg["start"] + 5.3)) / 0.45) ** 2)
        dy -= self.nose * (sniff * 1.5 + breath * 0.7)
        paw_move = math.exp(-((t - cfg["paw_time"]) / 0.55) ** 2)
        dy += self.paw * paw_move * 4.7
        dx -= self.paw * paw_move * 2.2
        # Refraction is restricted to water and never distorts the hippo's face.
        strength = self.water * (0.15 + self.water_depth * 1.5)
        dx += strength * (np.sin(self.y * 0.065 - t * 1.8) + np.sin(self.x * 0.021 + self.y * 0.029 + t * 1.15) * 0.43)
        dy += strength * np.cos(self.y * 0.071 + self.x * 0.014 - t * 1.25) * 0.20
        dx += self.wind * np.sin(self.y * 0.006 + t * 0.8) * 1.55
        return cv2.remap(frame, self.x + dx, self.y + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)

    def water_effects(self, frame, t):
        ripple = np.zeros((self.h, self.w), np.uint8)
        for index, (cx, cy, phase) in enumerate(self.cfg["rings"]):
            for extra in (0, 0.48):
                p = ((t + phase + extra * 3.4) / 3.4) % 1
                radius = 13 + 145 * p
                fade = math.sin(math.pi * p) ** 1.6 * 0.6
                center = (int(cx * 16), int(cy * 16))
                axes = (int(radius * 16), int(radius * 0.20 * 16))
                cv2.ellipse(ripple, center, axes, -3 + index * 3, 0, 360, int(fade * 255), 1, cv2.LINE_AA, 4)
        ripple = cv2.GaussianBlur(ripple, (0, 0), 0.45)
        light = ripple.astype(np.float32) / 255 * self.water * 0.22
        frame += (255 - frame) * light[..., None]
        glints = np.zeros_like(ripple)
        for x, y, phase in self.glints:
            value = max(0, math.sin(t * 2.8 + phase)) ** 12
            if value < 0.025 or self.water[int(y), int(x)] < 0.5:
                continue
            cv2.ellipse(glints, (int(x * 16), int(y * 16)), (31, 9), 0, 0, 360, int(value * 210), -1, cv2.LINE_AA, 4)
        amount = glints.astype(np.float32) / 255 * 0.55
        frame += (255 - frame) * amount[..., None]
        # Sparse sunlit motes in the soft background, not a glitter overlay.
        pollen = np.zeros((self.h, self.w), np.float32)
        for x, y, radius, phase in self.motes:
            xx = x + math.sin(t * 0.48 + phase) * 9 + t * 0.55
            yy = y + math.cos(t * 0.34 + phase) * 7
            if xx > self.w - 5:
                continue
            if self.head[int(yy), int(xx)] > 0.07:
                continue
            value = 0.035 + 0.027 * math.sin(t * 1.2 + phase)
            cv2.circle(pollen, (int(xx * 16), int(yy * 16)), max(7, int(radius * 16)), value, -1, cv2.LINE_AA, 4)
        pollen = cv2.GaussianBlur(pollen, (0, 0), 0.9)
        frame += (np.array([255, 248, 219], np.float32) - frame) * pollen[..., None]
        return frame

    def camera(self, frame, t):
        progress = float(smoothstep(0, 10, t - self.cfg["start"]))
        start_zoom, end_zoom, focus_x, focus_y = self.cfg["camera"]
        zoom = start_zoom + (end_zoom - start_zoom) * progress
        base_scale = max(self.width / self.w, self.height / self.h)
        scale = base_scale * zoom
        center_x = self.w / 2 + (focus_x - self.w / 2) * (1 - 1 / zoom)
        center_y = self.h / 2 + (focus_y - self.h / 2) * (1 - 1 / zoom)
        center_x += math.sin(t * 0.23) * 3.0
        center_y += math.sin(t * 0.17 + 1) * 3.0
        visible_x, visible_y = self.width / scale / 2, self.height / scale / 2
        center_x = float(np.clip(center_x, visible_x + 0.5, self.w - visible_x - 0.5))
        center_y = float(np.clip(center_y, visible_y + 0.5, self.h - visible_y - 0.5))
        matrix = np.array([[scale, 0, self.width / 2 - center_x * scale], [0, scale, self.height / 2 - center_y * scale]], np.float32)
        return cv2.warpAffine(frame, matrix, (self.width, self.height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)

    def render(self, t, blink_override=None):
        frame = self.open.copy()
        self.eyelids(frame, t, blink_override)
        frame = self.deform(frame, t)
        frame = self.water_effects(frame, t)
        frame *= self.vignette
        # A very restrained warm, film-like grade.
        frame = np.clip(frame, 0, 255).astype(np.uint8)
        return self.camera(frame, t)


class HippoFilm:
    def __init__(self, width=1080, height=1920):
        if width <= 0 or height <= 0 or width % 2 or height % 2:
            raise ValueError("Output width and height must be positive even numbers")
        self.width, self.height = width, height
        self.scenes = [RiverScene(settings, width, height) for settings in SCENES]

    def render(self, t):
        t = min(float(DURATION), max(0.0, float(t)))
        for index, boundary in enumerate((10, 20)):
            if boundary - 0.35 <= t <= boundary + 0.35:
                alpha = float(smoothstep(boundary - 0.35, boundary + 0.35, t))
                first = self.scenes[index].render(t)
                second = self.scenes[index + 1].render(t)
                return cv2.addWeighted(first, 1 - alpha, second, alpha, 0)
        index = min(2, int(t // 10))
        return self.scenes[index].render(t)


def make_river_audio(path, sample_rate=48000):
    """Original, quiet river-like sound design with synthesized distant birds."""
    print("Synthesizing river ambience", flush=True)
    n = DURATION * sample_rate
    t = np.arange(n, dtype=np.float64) / sample_rate
    rng = np.random.default_rng(3310)
    frequencies = fft.rfftfreq(n, 1 / sample_rate)
    # Soft flowing-water texture, with low-frequency wind filtered out.
    shape = np.exp(-frequencies / 3500) * (1 - np.exp(-(frequencies / 300) ** 2))
    stereo = np.zeros((n, 2), np.float64)
    for channel in range(2):
        noise = fft.irfft(fft.rfft(rng.standard_normal(n)) * shape, n)
        noise /= max(1e-8, np.std(noise))
        envelope = 0.012 * (0.8 + 0.13 * np.sin(t * 0.69 + channel) + 0.07 * np.sin(t * 1.13))
        stereo[:, channel] += noise * envelope
    # Small, quiet liquid drops; all synthesized rather than sampled recordings.
    for moment in [0.9, 3.6, 4.85, 7.5, 10.6, 13.3, 16.25, 18.9, 21.2, 23.75, 26.1, 28.6]:
        duration = 0.32
        start, length = int(moment * sample_rate), int(duration * sample_rate)
        tt = np.arange(length) / sample_rate
        freq = rng.uniform(180, 310) + 420 * np.exp(-tt * 21)
        phase = np.cumsum(freq) * TAU / sample_rate
        envelope = np.exp(-tt * 16) * (1 - np.exp(-tt * 180))
        drop = np.sin(phase) * envelope * 0.035
        pan = rng.uniform(-0.65, 0.65)
        stereo[start:start + length, 0] += drop * (1 - pan * 0.5)
        stereo[start:start + length, 1] += drop * (1 + pan * 0.5)
    for index, moment in enumerate([1.65, 2.0, 6.8, 7.2, 11.5, 11.85, 17.6, 21.7, 22.1, 26.4, 26.75, 28.4]):
        length = int(sample_rate * (0.23 + 0.09 * (index % 3)))
        tt = np.arange(length) / sample_rate
        progress = tt / tt[-1]
        freq = 1950 + 840 * np.sin(progress * math.pi * 0.7 + index * 0.3) + 85 * np.sin(tt * 75)
        phase = np.cumsum(freq) * TAU / sample_rate
        chirp = (np.sin(phase) + np.sin(phase * 2) * 0.075) * np.sin(progress * math.pi) ** 2 * 0.021
        start = int(moment * sample_rate)
        pan = -0.7 if index % 4 < 2 else 0.65
        stereo[start:start + length, 0] += chirp * (1 - pan * 0.5)
        stereo[start:start + length, 1] += chirp * (1 + pan * 0.5)
    stereo *= smoothstep(0, 0.30, t)[:, None] * (1 - smoothstep(29.35, 30, t))[:, None]
    stereo *= 0.32 / max(0.32, np.max(np.abs(stereo)))
    # The intentionally quiet ambience should sit behind the visual, not dominate.
    pcm = (np.clip(stereo * 2.5, -1, 1) * 32767).astype("<i2")
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
    movie = HippoFilm(width, height)
    audio = CACHE / "river.wav"
    if not silent:
        make_river_audio(audio)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-"]
    if not silent:
        command += ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "192k"]
    command += ["-c:v", "libx264", "-preset", "fast", "-crf", "19", "-maxrate", "10M", "-bufsize", "20M", "-threads", "2", "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.2", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-movflags", "+faststart", "-t", str(DURATION), "-metadata", "title=Pequeno del rio - Hipopotamo bebe", "-metadata", "comment=Original 2.5D animation from AI-generated plates. Original synthesized river ambience.", str(output)]
    encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
    start = time.monotonic()
    try:
        total = DURATION * fps
        for index in range(total):
            image = movie.render(index / fps)
            encoder.stdin.write(image.tobytes())
            if index % fps == 0:
                print(f"Frame {index:03d}/{total} · {index/fps:02.0f}s / 30s · elapsed {time.monotonic()-start:.1f}s", flush=True)
            if index == fps * 12:
                Image.fromarray(image).save(output.with_suffix(".jpg"), quality=94)
        encoder.stdin.close()
        if encoder.wait() != 0:
            raise RuntimeError("Video encoder failed")
    except BaseException:
        if encoder.poll() is None:
            encoder.kill()
            encoder.wait()
        output.unlink(missing_ok=True)
        raise
    print(f"Completed: {output} · {output.stat().st_size/1e6:.1f} MB · {time.monotonic()-start:.1f}s", flush=True)


def preview():
    CACHE.mkdir(parents=True, exist_ok=True)
    film = HippoFilm(360, 640)
    moments = [0, 2.67, 6, 12, 14.94, 17, 21, 24.48, 28]
    sheet = Image.new("RGB", (360 * 3, 672 * 3), "#18221b")
    draw = ImageDraw.Draw(sheet)
    for index, moment in enumerate(moments):
        image = Image.fromarray(film.render(moment))
        x, y = index % 3 * 360, index // 3 * 672
        sheet.paste(image, (x, y))
        draw.text((x + 12, y + 648), f"{moment:.2f} s", fill="#edf1e6")
    path = CACHE / "contact-sheet.jpg"
    sheet.save(path, quality=94)
    print(path)
    for index, scene in enumerate(film.scenes):
        frame = Image.fromarray(scene.render(scene.cfg["start"] + 2, blink_override=1))
        frame.save(CACHE / f"blink-{index}.jpg", quality=95)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--output", type=Path, default=EXPORT / "hipopotamo-bebe.mp4")
    args = parser.parse_args()
    if args.preview:
        preview()
    else:
        render_video(args.output.resolve(), args.width, args.height, args.fps, args.silent)
