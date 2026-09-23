#!/usr/bin/env python3
"""Two stick figures practicing friendly martial arts.

A 30-second vertical animation, no blood, no text, no voice.
Each figure has a distinct color for clarity. The motion is procedural
with 2-bone IK for arms/legs, keyframed footwork and choreographed
punches, kicks, blocks, dodges and a bow. Includes subtle impact
effects and camera shake.

No external video model is used; all frames are drawn with OpenCV.
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

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".cache" / "stickmen"
EXPORT = ROOT / "exports"
DURATION, FPS = 30, 30
TAU = math.tau
cv2.setNumThreads(2)

# Colors BGR for OpenCV drawing
BG_WALL = (216, 229, 232)  # light
BG_TOP = (234, 243, 246)
FLOOR = (168, 201, 216)
MAT = (150, 184, 201)
MAT_LINE = (120, 160, 180)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
BLUE_BGR = (255, 127, 42)   # #2a7fff -> BGR
RED_BGR = (48, 59, 255)     # #ff3b30
BLUE_LIGHT = (255, 180, 120)
RED_LIGHT = (120, 120, 255)
YELLOW = (0, 255, 255)

# Fighter config - enlarged for vertical readability
HEAD_R = 38
TORSO_LEN = 185
UPPER_ARM = 82
FOREARM = 76
THIGH = 98
SHIN = 96
GROUND_Y_RATIO = 0.73
GROUND_Y = int(1920 * GROUND_Y_RATIO)  # will be scaled with height
PELVIS_GROUND_OFFSET = 175

def smoothstep(lo, hi, x):
    if hi <= lo:
        return 0.0 if x < lo else 1.0
    t = (x - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)

def lerp(a, b, t):
    return a + (b - a) * t

def lerp_point(p1, p2, t):
    return (lerp(p1[0], p2[0], t), lerp(p1[1], p2[1], t))

def smooth_lerp(a, b, t):
    return lerp(a, b, smoothstep(0, 1, t))

# Footwork keyframes (time, x) for 1080 width reference, will be scaled
BLUE_X_KF = [
    (0.0, 340), (1.5, 380), (2.8, 440), (3.8, 380),
    (6.5, 380), (7.5, 460), (8.5, 380),
    (11.0, 380), (12.0, 420), (13.5, 380),
    (14.5, 460), (16.0, 380),
    (19.0, 440), (21.0, 380), (22.0, 450), (24.0, 380),
    (27.0, 380), (28.0, 380), (30.0, 340),
]
RED_X_KF = [
    (0.0, 740), (1.5, 700), (2.8, 700), (3.8, 700),
    (4.5, 640), (5.5, 700), (6.5, 700), (7.5, 700), (8.5, 700),
    (9.5, 620), (11.0, 700), (12.0, 660), (13.5, 700),
    (14.5, 700), (16.0, 700), (17.0, 640), (18.0, 700),
    (19.0, 640), (21.0, 700), (22.0, 660), (24.0, 700),
    (25.0, 630), (27.0, 700), (28.0, 700), (30.0, 740),
]

BLUE_Y_KF = [
    (0.0, 0), (6.2, 0), (6.7, 20), (7.2, 0),
    (14.7, 0), (15.2, 20), (15.7, 0),
    (16.2, 0), (16.5, -80), (17.0, 0),
    (18.7, 0), (19.2, -15), (20.0, 0),
    (30.0, 0),
]
RED_Y_KF = [
    (0.0, 0), (9.7, 0), (10.2, 20), (10.7, 0),
    (16.2, 0), (16.7, 20), (17.2, 0),
    (18.7, 0), (19.2, -15), (20.0, 0),
    (30.0, 0),
]

# Choreography events
EVENTS = [
    {"start": 2.0, "dur": 0.6, "attacker": "blue", "hand": "left", "type": "jab", "defender": "red", "defense": "block_high"},
    {"start": 4.0, "dur": 0.6, "attacker": "red", "hand": "right", "type": "jab", "defender": "blue", "defense": "block_high"},
    {"start": 6.0, "dur": 0.9, "attacker": "blue", "leg": "right", "type": "front_kick", "defender": "red", "defense": "step_back"},
    {"start": 8.5, "dur": 1.0, "attacker": "red", "leg": "left", "type": "roundhouse", "defender": "blue", "defense": "duck"},
    {"start": 11.0, "dur": 0.5, "attacker": "blue", "hand": "right", "type": "cross", "defender": "red", "defense": "block_high"},
    {"start": 11.5, "dur": 0.5, "attacker": "red", "hand": "left", "type": "cross", "defender": "blue", "defense": "block_high"},
    {"start": 12.0, "dur": 0.5, "attacker": "blue", "hand": "left", "type": "hook", "defender": "red", "defense": "block_high"},
    {"start": 12.5, "dur": 0.5, "attacker": "red", "hand": "right", "type": "hook", "defender": "blue", "defense": "block_high"},
    {"start": 13.5, "dur": 1.0, "attacker": "blue", "leg": "left", "type": "side_kick", "defender": "red", "defense": "block_low"},
    {"start": 16.0, "dur": 1.0, "attacker": "red", "leg": "right", "type": "sweep", "defender": "blue", "defense": "jump"},
    {"start": 18.5, "dur": 1.2, "attacker": "blue", "leg": "left", "type": "high_kick", "defender": "red", "defense": "dodge"},
    {"start": 18.5, "dur": 1.2, "attacker": "red", "leg": "right", "type": "high_kick", "defender": "blue", "defense": "dodge"},
    {"start": 21.0, "dur": 0.5, "attacker": "blue", "hand": "left", "type": "jab", "defender": "red", "defense": "block_high"},
    {"start": 21.4, "dur": 0.5, "attacker": "blue", "hand": "right", "type": "cross", "defender": "red", "defense": "block_high"},
    {"start": 21.9, "dur": 0.8, "attacker": "blue", "leg": "right", "type": "roundhouse", "defender": "red", "defense": "block_low"},
    {"start": 24.0, "dur": 0.5, "attacker": "red", "hand": "right", "type": "jab", "defender": "blue", "defense": "block_high"},
    {"start": 24.4, "dur": 0.5, "attacker": "red", "hand": "left", "type": "cross", "defender": "blue", "defense": "block_high"},
    {"start": 24.9, "dur": 0.8, "attacker": "red", "leg": "left", "type": "side_kick", "defender": "blue", "defense": "block_low"},
]

def interp_keyframes(kf, t):
    t = float(t % DURATION)
    # handle wrap
    for i in range(len(kf)-1):
        t0, v0 = kf[i]
        t1, v1 = kf[i+1]
        if t0 <= t < t1 or (i==len(kf)-2 and t>=t0):
            if t1 <= t0:
                return v0
            local = (t - t0) / (t1 - t0)
            local = smoothstep(0, 1, local)
            return lerp(v0, v1, local)
    return kf[-1][1]

def get_base_x(fighter, t, width_scale):
    kf = BLUE_X_KF if fighter == "blue" else RED_X_KF
    # scale x from 1080 reference
    base_1080 = interp_keyframes(kf, t)
    return base_1080 * width_scale

def get_base_y_offset(fighter, t):
    kf = BLUE_Y_KF if fighter == "blue" else RED_Y_KF
    return interp_keyframes(kf, t)

def active_events_at(t):
    t = float(t % DURATION)
    out = []
    for ev in EVENTS:
        if ev["start"] <= t < ev["start"] + ev["dur"]:
            out.append(ev)
    return out

def two_bone_ik(ax, ay, tx, ty, L1, L2):
    dx = tx - ax
    dy = ty - ay
    d = math.hypot(dx, dy)
    if d < 1e-6:
        return ax + L1, ay, ax + L1*0.5, ay
    d_clamped = max(abs(L1 - L2) + 1e-3, min(L1 + L2 - 1e-3, d))
    # angle to target
    ang = math.atan2(dy, dx)
    cos_a = (L1*L1 + d_clamped*d_clamped - L2*L2) / (2 * L1 * d_clamped)
    cos_a = max(-1.0, min(1.0, cos_a))
    a = math.acos(cos_a)
    # two solutions
    e1x = ax + L1 * math.cos(ang + a)
    e1y = ay + L1 * math.sin(ang + a)
    e2x = ax + L1 * math.cos(ang - a)
    e2y = ay + L1 * math.sin(ang - a)
    return (e1x, e1y, e2x, e2y)

def choose_elbow_arm(ax, ay, tx, ty, L1, L2):
    e1x, e1y, e2x, e2y = two_bone_ik(ax, ay, tx, ty, L1, L2)
    # choose more down (larger y)
    if e1y > e2y:
        return e1x, e1y
    else:
        return e2x, e2y

def choose_knee_leg(ax, ay, tx, ty, L1, L2, facing):
    e1x, e1y, e2x, e2y = two_bone_ik(ax, ay, tx, ty, L1, L2)
    # choose more forward in facing direction
    if facing > 0:
        # larger x is forward
        if e1x > e2x:
            return e1x, e1y
        else:
            return e2x, e2y
    else:
        if e1x < e2x:
            return e1x, e1y
        else:
            return e2x, e2y

class StickFightFilm:
    def __init__(self, width=1080, height=1920):
        if width <= 0 or height <= 0 or width % 2 or height % 2:
            raise ValueError("Output dimensions must be positive even integers")
        self.width = width
        self.height = height
        self.width_scale = width / 1080.0
        self.height_scale = height / 1920.0
        self.ground_y = int(height * GROUND_Y_RATIO)
        self.head_r = max(12, int(HEAD_R * self.width_scale))
        self.torso_len = int(TORSO_LEN * self.height_scale)
        self.upper_arm = int(UPPER_ARM * self.width_scale)
        self.forearm = int(FOREARM * self.width_scale)
        self.thigh = int(THIGH * self.height_scale)
        self.shin = int(SHIN * self.height_scale)
        self.thickness = max(6, int(10 * self.width_scale))
        self.outline = max(3, int(4 * self.width_scale))
        CACHE.mkdir(parents=True, exist_ok=True)

    def get_torso_lean(self, fighter, t):
        # base slight forward lean
        lean = 0.12
        for ev in active_events_at(t):
            if ev.get("attacker") == fighter:
                p = (t - ev["start"]) / ev["dur"]
                # punch -> lean forward
                if "hand" in ev:
                    if p < 0.6:
                        lean += 0.18 * smoothstep(0, 0.5, p)
                    else:
                        lean += 0.18 * (1 - smoothstep(0.6, 1.0, p))
                if "leg" in ev:
                    # kick -> lean back
                    if p < 0.7:
                        lean -= 0.38 * smoothstep(0, 0.6, p)
                    else:
                        lean -= 0.38 * (1 - smoothstep(0.7, 1.0, p))
            if ev.get("defender") == fighter:
                defense = ev.get("defense")
                p = (t - ev["start"]) / ev["dur"]
                if defense == "duck":
                    lean += 0.35 * smoothstep(0.2, 0.7, p) * (1 - smoothstep(0.7, 1.0, p)*0.5)
                elif defense in ("block_high", "block_low"):
                    lean -= 0.12 * smoothstep(0.2, 0.6, p)
                elif defense == "dodge":
                    lean -= 0.25 * smoothstep(0.2, 0.6, p)
                elif defense == "jump":
                    lean -= 0.15 * smoothstep(0.2, 0.6, p)
        return lean

    def get_pelvis(self, fighter, t):
        base_x = get_base_x(fighter, t, self.width_scale)
        y_offset = get_base_y_offset(fighter, t) * self.height_scale
        # default pelvis y = ground - offset
        pelvis_y = self.ground_y - PELVIS_GROUND_OFFSET * self.height_scale + y_offset
        # facing
        facing = 1 if fighter == "blue" else -1
        return base_x, pelvis_y, facing

    def get_torso_top(self, pelvis_x, pelvis_y, facing, lean):
        # lean forward positive
        top_x = pelvis_x + facing * math.sin(lean) * self.torso_len
        top_y = pelvis_y - math.cos(lean) * self.torso_len
        return top_x, top_y

    def get_hand_target(self, fighter, side, t, torso_top, facing):
        is_front = (fighter == "blue" and side == "left") or (fighter == "red" and side == "right")
        # guard
        if is_front:
            gx = torso_top[0] + facing * 45 * self.width_scale
            gy = torso_top[1] + 25 * self.height_scale
        else:
            gx = torso_top[0] + facing * 15 * self.width_scale
            gy = torso_top[1] + 15 * self.height_scale

        # attacker punch
        for ev in active_events_at(t):
            if ev.get("attacker") == fighter and ev.get("hand") == side:
                p = (t - ev["start"]) / ev["dur"]
                # pullback position
                pull_x = gx - facing * 20 * self.width_scale
                pull_y = gy + 10 * self.height_scale
                if ev["type"] == "jab":
                    tx = torso_top[0] + facing * 90 * self.width_scale
                    ty = torso_top[1] - 10 * self.height_scale
                elif ev["type"] == "cross":
                    tx = torso_top[0] + facing * 130 * self.width_scale
                    ty = torso_top[1] + 5 * self.height_scale
                elif ev["type"] == "hook":
                    tx = torso_top[0] + facing * 70 * self.width_scale
                    ty = torso_top[1] - 30 * self.height_scale
                else:
                    tx = torso_top[0] + facing * 100 * self.width_scale
                    ty = torso_top[1]
                if p < 0.2:
                    prog = smoothstep(0, 1, p/0.2)
                    return (lerp(gx, pull_x, prog), lerp(gy, pull_y, prog))
                elif p < 0.6:
                    prog = smoothstep(0, 1, (p-0.2)/0.4)
                    return (lerp(pull_x, tx, prog), lerp(pull_y, ty, prog))
                else:
                    prog = smoothstep(0, 1, (p-0.6)/0.4)
                    return (lerp(tx, gx, prog), lerp(ty, gy, prog))
        # defender block
        for ev in active_events_at(t):
            if ev.get("defender") == fighter:
                defense = ev.get("defense")
                if not is_front:
                    continue
                if defense in ("block_high", "block_low"):
                    p = (t - ev["start"]) / ev["dur"]
                    if defense == "block_high":
                        bx = torso_top[0] + facing * 65 * self.width_scale
                        by = torso_top[1] - 15 * self.height_scale
                    else:
                        bx = torso_top[0] + facing * 60 * self.width_scale
                        by = torso_top[1] + 35 * self.height_scale
                    if p < 0.3:
                        prog = smoothstep(0, 1, p/0.3)
                        return (lerp(gx, bx, prog), lerp(gy, by, prog))
                    elif p < 0.7:
                        return (bx, by)
                    else:
                        prog = smoothstep(0, 1, (p-0.7)/0.3)
                        return (lerp(bx, gx, prog), lerp(by, gy, prog))
        return (gx, gy)

    def get_foot_target(self, fighter, side, t, base_x, facing):
        is_front = (fighter == "blue" and side == "left") or (fighter == "red" and side == "right")
        # guard positions
        if is_front:
            gx = base_x + facing * 35 * self.width_scale
        else:
            gx = base_x - facing * 40 * self.width_scale
        gy = self.ground_y

        # check attacker kick
        for ev in active_events_at(t):
            if ev.get("attacker") == fighter and ev.get("leg") == side:
                p = (t - ev["start"]) / ev["dur"]
                # chamber
                chamber_x = base_x + facing * 5 * self.width_scale
                chamber_y = self.ground_y - 70 * self.height_scale  # knee up
                if ev["type"] == "front_kick":
                    tx = base_x + facing * 120 * self.width_scale
                    ty = self.ground_y - 80 * self.height_scale
                elif ev["type"] == "roundhouse":
                    tx = base_x + facing * 100 * self.width_scale
                    ty = self.ground_y - 120 * self.height_scale
                elif ev["type"] == "side_kick":
                    tx = base_x + facing * 130 * self.width_scale
                    ty = self.ground_y - 60 * self.height_scale
                elif ev["type"] == "sweep":
                    tx = base_x + facing * 90 * self.width_scale
                    ty = self.ground_y - 10 * self.height_scale
                elif ev["type"] == "high_kick":
                    tx = base_x + facing * 90 * self.width_scale
                    ty = self.ground_y - 160 * self.height_scale
                else:
                    tx = base_x + facing * 100 * self.width_scale
                    ty = self.ground_y - 80 * self.height_scale

                if p < 0.3:
                    prog = smoothstep(0, 1, p/0.3)
                    return (lerp(gx, chamber_x, prog), lerp(gy, chamber_y, prog))
                elif p < 0.6:
                    prog = smoothstep(0, 1, (p-0.3)/0.3)
                    return (lerp(chamber_x, tx, prog), lerp(chamber_y, ty, prog))
                else:
                    prog = smoothstep(0, 1, (p-0.6)/0.4)
                    return (lerp(tx, gx, prog), lerp(ty, gy, prog))
        # defender jump
        for ev in active_events_at(t):
            if ev.get("defender") == fighter and ev.get("defense") == "jump":
                p = (t - ev["start"]) / ev["dur"]
                if p < 0.2:
                    prog = smoothstep(0, 1, p/0.2)
                    return (gx, lerp(gy, gy - 5, prog))
                elif p < 0.5:
                    prog = smoothstep(0, 1, (p-0.2)/0.3)
                    # jump up
                    return (gx + facing * -5 * self.width_scale * prog, lerp(gy, gy - 60 * self.height_scale, prog))
                elif p < 0.8:
                    prog = smoothstep(0, 1, (p-0.5)/0.3)
                    return (gx + facing * -5 * self.width_scale * (1-prog), lerp(gy - 60 * self.height_scale, gy, prog))
                else:
                    return (gx, gy)
        return (gx, gy)

    def get_fighter_skeleton(self, fighter, t):
        pelvis_x, pelvis_y, facing = self.get_pelvis(fighter, t)
        lean = self.get_torso_lean(fighter, t)
        torso_top = self.get_torso_top(pelvis_x, pelvis_y, facing, lean)
        head_x = torso_top[0] + facing * math.sin(lean) * 15 * self.width_scale
        head_y = torso_top[1] - self.head_r - 8 * self.height_scale
        shoulder = (torso_top[0], torso_top[1] + 12 * self.height_scale)

        # hands
        left_hand = self.get_hand_target(fighter, "left", t, torso_top, facing)
        right_hand = self.get_hand_target(fighter, "right", t, torso_top, facing)
        # elbows via IK
        left_elbow = choose_elbow_arm(shoulder[0], shoulder[1], left_hand[0], left_hand[1], self.upper_arm, self.forearm)
        right_elbow = choose_elbow_arm(shoulder[0], shoulder[1], right_hand[0], right_hand[1], self.upper_arm, self.forearm)

        # feet
        left_foot = self.get_foot_target(fighter, "left", t, pelvis_x, facing)
        right_foot = self.get_foot_target(fighter, "right", t, pelvis_x, facing)
        # knees
        left_knee = choose_knee_leg(pelvis_x, pelvis_y, left_foot[0], left_foot[1], self.thigh, self.shin, facing)
        right_knee = choose_knee_leg(pelvis_x, pelvis_y, right_foot[0], right_foot[1], self.thigh, self.shin, facing)

        return {
            "fighter": fighter,
            "facing": facing,
            "pelvis": (pelvis_x, pelvis_y),
            "torso_top": torso_top,
            "head": (head_x, head_y),
            "shoulder": shoulder,
            "left_hand": left_hand,
            "right_hand": right_hand,
            "left_elbow": left_elbow,
            "right_elbow": right_elbow,
            "left_foot": left_foot,
            "right_foot": right_foot,
            "left_knee": left_knee,
            "right_knee": right_knee,
            "lean": lean,
        }

    def get_impacts(self, t):
        impacts = []
        skeletons = {
            "blue": self.get_fighter_skeleton("blue", t),
            "red": self.get_fighter_skeleton("red", t),
        }
        for ev in active_events_at(t):
            p = (t - ev["start"]) / ev["dur"]
            # impact window 0.35-0.65
            if not (0.35 <= p <= 0.65):
                continue
            intensity = 1.0 - abs(p - 0.5) / 0.15
            intensity = max(0.0, min(1.0, intensity))
            attacker = ev.get("attacker")
            defender = ev.get("defender")
            if not attacker or not defender:
                continue
            # if both attack high kick, no defender impact, show mid air clash
            if attacker == "blue" and defender == "red":
                atk_skel = skeletons[attacker]
                def_skel = skeletons[defender]
                if "hand" in ev:
                    hand = ev["hand"]
                    atk_hand = atk_skel["left_hand"] if hand == "left" else atk_skel["right_hand"]
                    # defender block hand
                    def_hand = def_skel["left_hand"] if def_skel["fighter"] == "blue" else def_skel["right_hand"]
                    # if defender blocking, impact at block hand
                    if ev.get("defense") in ("block_high", "block_low"):
                        # front hand of defender
                        front = "left" if defender == "blue" else "right"
                        bx = def_skel["left_hand"] if front == "left" else def_skel["right_hand"]
                        impacts.append((bx[0], bx[1], intensity, "block"))
                    else:
                        # impact near defender head/torso
                        impacts.append(((atk_hand[0] + def_skel["head"][0]) / 2, (atk_hand[1] + def_skel["head"][1]) / 2, intensity, "hit"))
                elif "leg" in ev:
                    leg = ev["leg"]
                    atk_foot = atk_skel["left_foot"] if leg == "left" else atk_skel["right_foot"]
                    if ev.get("defense") in ("block_low", "block_high"):
                        front = "left" if defender == "blue" else "right"
                        bx = def_skel["left_hand"] if front == "left" else def_skel["right_hand"]
                        impacts.append((bx[0], bx[1], intensity, "block"))
                    elif ev.get("defense") == "duck":
                        # no impact, dodge
                        pass
                    elif ev.get("defense") == "step_back":
                        pass
                    else:
                        impacts.append(((atk_foot[0] + def_skel["pelvis"][0]) / 2, (atk_foot[1] + def_skel["pelvis"][1]) / 2 - 20, intensity, "hit"))
            # handle simultaneous high kicks
            if ev["type"] == "high_kick" and ev["start"] == 18.5:
                # clash mid
                blue_foot = skeletons["blue"]["left_foot"]
                red_foot = skeletons["red"]["right_foot"]
                mid_x = (blue_foot[0] + red_foot[0]) / 2
                mid_y = (blue_foot[1] + red_foot[1]) / 2
                impacts.append((mid_x, mid_y, intensity * 0.8, "clash"))
        return impacts

    def render(self, t):
        t = float(t % DURATION)
        # base canvas BGR
        img = np.full((self.height, self.width, 3), BG_WALL, dtype=np.uint8)
        # gradient top
        # draw vertical gradient from BG_TOP to BG_WALL for top 70%
        for y in range(int(self.ground_y)):
            ratio = y / max(1, self.ground_y)
            b = int(lerp(BG_TOP[0], BG_WALL[0], ratio))
            g = int(lerp(BG_TOP[1], BG_WALL[1], ratio))
            r = int(lerp(BG_TOP[2], BG_WALL[2], ratio))
            img[y, :] = (b, g, r)
        # floor
        cv2.rectangle(img, (0, self.ground_y), (self.width, self.height), FLOOR, -1)
        # mat
        mat_left = int(self.width * 0.12)
        mat_right = int(self.width * 0.88)
        mat_top = self.ground_y + int(20 * self.height_scale)
        mat_bottom = self.height - int(40 * self.height_scale)
        cv2.rectangle(img, (mat_left, mat_top), (mat_right, mat_bottom), MAT, -1)
        cv2.rectangle(img, (mat_left, mat_top), (mat_right, mat_bottom), MAT_LINE, max(2, int(3*self.width_scale)))
        # inner mat lines
        cv2.line(img, (mat_left, mat_top + (mat_bottom-mat_top)//2), (mat_right, mat_top + (mat_bottom-mat_top)//2), MAT_LINE, 2)
        # dojo wall details - simple vertical wood lines
        for x in range(0, self.width, int(120*self.width_scale)):
            cv2.line(img, (x, 0), (x, self.ground_y), (200, 210, 215), 1)

        skeletons = {
            "blue": self.get_fighter_skeleton("blue", t),
            "red": self.get_fighter_skeleton("red", t),
        }

        # shadows
        for fid in ("blue", "red"):
            sk = skeletons[fid]
            for foot in (sk["left_foot"], sk["right_foot"]):
                if foot[1] >= self.ground_y - 10:
                    shadow_x, shadow_y = int(foot[0]), self.ground_y + 8
                    cv2.ellipse(img, (shadow_x, shadow_y), (int(30*self.width_scale), int(10*self.height_scale)), 0, 0, 360, (100, 120, 130), -1)

        # draw fighters - order by x (back first)
        order = sorted(skeletons.values(), key=lambda s: s["pelvis"][0])
        for sk in order:
            fighter = sk["fighter"]
            color = BLUE_BGR if fighter == "blue" else RED_BGR
            facing = sk["facing"]
            # legs
            # thigh
            self.draw_limb(img, sk["pelvis"], sk["left_knee"], color)
            self.draw_limb(img, sk["left_knee"], sk["left_foot"], color)
            self.draw_limb(img, sk["pelvis"], sk["right_knee"], color)
            self.draw_limb(img, sk["right_knee"], sk["right_foot"], color)
            # torso
            self.draw_limb(img, sk["pelvis"], sk["torso_top"], color, thick=self.thickness+2)
            # arms
            self.draw_limb(img, sk["shoulder"], sk["left_elbow"], color)
            self.draw_limb(img, sk["left_elbow"], sk["left_hand"], color)
            self.draw_limb(img, sk["shoulder"], sk["right_elbow"], color)
            self.draw_limb(img, sk["right_elbow"], sk["right_hand"], color)
            # hands/feet circles
            for pt in (sk["left_hand"], sk["right_hand"]):
                cv2.circle(img, (int(pt[0]), int(pt[1])), int(10*self.width_scale), BLACK, -1)
                cv2.circle(img, (int(pt[0]), int(pt[1])), int(7*self.width_scale), color, -1)
            for pt in (sk["left_foot"], sk["right_foot"]):
                cv2.circle(img, (int(pt[0]), int(pt[1])), int(11*self.width_scale), BLACK, -1)
                cv2.circle(img, (int(pt[0]), int(pt[1])), int(8*self.width_scale), color, -1)
            # head
            hx, hy = int(sk["head"][0]), int(sk["head"][1])
            cv2.circle(img, (hx, hy), self.head_r, BLACK, -1)
            cv2.circle(img, (hx, hy), self.head_r - self.outline, WHITE, -1)
            # eyes looking forward
            eye_offset_x = int(facing * 8 * self.width_scale)
            eye_y = hy + int(2 * self.height_scale)
            cv2.circle(img, (hx + eye_offset_x, eye_y), int(4*self.width_scale), BLACK, -1)
            # headband color
            cv2.ellipse(img, (hx, hy - int(self.head_r*0.3)), (self.head_r, int(self.head_r*0.4)), 0, 180, 360, color, -1)

        # impacts
        impacts = self.get_impacts(t)
        for ix, iy, inten, typ in impacts:
            if inten < 0.1:
                continue
            r = int(12 * self.width_scale + inten * 18 * self.width_scale)
            # outer flash
            cv2.circle(img, (int(ix), int(iy)), r, WHITE, -1)
            cv2.circle(img, (int(ix), int(iy)), r, YELLOW, 2)
            # radiating lines
            for ang in range(0, 360, 45):
                rad = math.radians(ang)
                x1 = int(ix + math.cos(rad) * (r+2))
                y1 = int(iy + math.sin(rad) * (r+2))
                x2 = int(ix + math.cos(rad) * (r+12*inten))
                y2 = int(iy + math.sin(rad) * (r+12*inten))
                cv2.line(img, (x1, y1), (x2, y2), BLACK, 2)
                cv2.line(img, (x1, y1), (x2, y2), YELLOW, 1)

        # camera shake on strong impact
        shake_x = 0
        shake_y = 0
        max_inten = max([i[2] for i in impacts], default=0)
        if max_inten > 0.6:
            # deterministic shake based on time
            shake_x = int((math.sin(t*50) * 6 + math.cos(t*73)*4) * max_inten)
            shake_y = int((math.cos(t*61) * 5) * max_inten)
            M = np.float32([[1, 0, shake_x], [0, 1, shake_y]])
            img = cv2.warpAffine(img, M, (self.width, self.height), borderMode=cv2.BORDER_REFLECT_101)

        # convert BGR to RGB for encoder
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return rgb

    def draw_limb(self, img, p1, p2, color, thick=None):
        if thick is None:
            thick = self.thickness
        p1i = (int(p1[0]), int(p1[1]))
        p2i = (int(p2[0]), int(p2[1]))
        cv2.line(img, p1i, p2i, BLACK, thick + self.outline*2, cv2.LINE_AA)
        cv2.line(img, p1i, p2i, color, thick, cv2.LINE_AA)

def make_dojo_audio(path, sample_rate=48000):
    print("Synthesizing dojo ambience", flush=True)
    n = DURATION * sample_rate
    rng = np.random.default_rng(91234)
    stereo = np.zeros((n, 2), dtype=np.float64)

    # low room tone
    t = np.arange(n) / sample_rate
    # subtle 60hz hum? no
    # whoosh and thud per event
    for ev in EVENTS:
        start = ev["start"]
        dur = ev["dur"]
        attacker = ev.get("attacker")
        # whoosh at 0.25*dur
        whoosh_t = start + dur * 0.28
        whoosh_idx = int(whoosh_t * sample_rate)
        whoosh_len = int(0.18 * sample_rate)
        if 0 <= whoosh_idx < n:
            env = np.sin(np.linspace(0, math.pi, whoosh_len)) ** 1.2
            noise = rng.standard_normal(whoosh_len) * env * 0.09
            # simple high-pass by diff
            noise = np.convolve(noise, [1, -0.9], mode='same')
            # pan
            if attacker == "blue":
                stereo[whoosh_idx:whoosh_idx+whoosh_len, 0] += noise * 1.0
                stereo[whoosh_idx:whoosh_idx+whoosh_len, 1] += noise * 0.4
            elif attacker == "red":
                stereo[whoosh_idx:whoosh_idx+whoosh_len, 0] += noise * 0.4
                stereo[whoosh_idx:whoosh_idx+whoosh_len, 1] += noise * 1.0
            else:
                stereo[whoosh_idx:whoosh_idx+whoosh_len, :] += (noise[:, None] * 0.7)

        # thud at 0.5*dur if not dodge/step_back
        defense = ev.get("defense")
        if defense in ("duck", "step_back"):
            continue
        thud_t = start + dur * 0.5
        thud_idx = int(thud_t * sample_rate)
        thud_len = int(0.12 * sample_rate)
        if 0 <= thud_idx < n:
            tt = np.arange(thud_len) / sample_rate
            freq = 90 if "leg" in ev else 140
            sine = np.sin(2*math.pi*freq*tt) * np.exp(-tt*18) * 0.32
            # add click
            sine[: int(0.005*sample_rate)] *= np.linspace(0,1,int(0.005*sample_rate))
            # pan slightly center
            stereo[thud_idx:thud_idx+thud_len, 0] += sine * 0.9
            stereo[thud_idx:thud_idx+thud_len, 1] += sine * 0.9

    # add very quiet air
    air = rng.standard_normal(n) * 0.004
    stereo[:, 0] += air * 0.5
    stereo[:, 1] += air * 0.5

    # normalize to avoid clipping
    max_abs = np.max(np.abs(stereo))
    if max_abs > 0.89:
        stereo *= 0.89 / max_abs

    pcm = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(pcm.tobytes())

def render_video(output, width=1080, height=1920, fps=30, silent=False):
    if fps <= 0:
        raise ValueError("FPS must be positive")
    CACHE.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    film = StickFightFilm(width, height)
    audio = CACHE / "dojo.wav"
    if not silent:
        make_dojo_audio(audio)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y",
           "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{width}x{height}", "-r", str(fps), "-i", "-"]
    if not silent:
        cmd += ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-maxrate", "12M", "-bufsize", "24M", "-threads", "2",
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.2",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
            "-movflags", "+faststart",
            "-t", str(DURATION),
            "-metadata", "title=Palitos - Artes Marciales",
            "-metadata", "comment=Procedural stickman martial arts animation. No blood. Friendly practice.",
            str(output)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    start = time.monotonic()
    try:
        total = DURATION * fps
        for i in range(total):
            frame = film.render(i / fps)
            proc.stdin.write(frame.tobytes())
            if i % fps == 0:
                print(f"Frame {i:03d}/{total} · {i/fps:02.0f}s / 30s · elapsed {time.monotonic()-start:.1f}s", flush=True)
            if i == 0:
                Image.fromarray(frame).save(output.with_suffix(".jpg"), quality=96)
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError("Video encoding failed")
    except BaseException:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        output.unlink(missing_ok=True)
        raise
    print(f"Completed: {output} · {output.stat().st_size/1e6:.1f} MB · {time.monotonic()-start:.1f}s", flush=True)

def preview():
    film = StickFightFilm(432, 768)
    moments = (0, 2.2, 6.4, 8.8, 13.8, 24.22)
    sheet = Image.new("RGB", (432*3, 800*2), "#e8e5d8")
    draw = ImageDraw.Draw(sheet)
    for idx, mom in enumerate(moments):
        img = Image.fromarray(film.render(mom))
        x, y = idx % 3 * 432, idx // 3 * 800
        sheet.paste(img, (x, y))
        draw.text((x+12, y+778), f"{mom:.2f} s", fill="#222222")
    target = CACHE / "contact-sheet.jpg"
    sheet.save(target, quality=95)
    # detail
    detail = Image.new("RGB", (400*3, 300), "#e8e5d8")
    for idx, mom in enumerate((11.2, 18.8, 22.2)):
        frame = Image.fromarray(film.render(mom))
        detail.paste(frame.crop((100, 600, 500, 900)).resize((400, 300), Image.Resampling.LANCZOS), (idx*400, 0))
    detail.save(CACHE / "fight-details.jpg", quality=96)
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
    parser.add_argument("--output", type=Path, default=EXPORT / "palitos-artes-marciales.mp4")
    args = parser.parse_args()
    if args.preview:
        preview()
    else:
        render_video(args.output.resolve(), args.width, args.height, args.fps, args.silent)
