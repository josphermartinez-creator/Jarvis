"""The hippo is animated locally; only its eyelids use the blink plates."""
import unittest

import numpy as np

from render_hippo import HippoFilm, SCENES, blink_amount


class HippoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.film = HippoFilm(216, 384)

    def test_blinks_close_and_reopen(self):
        for settings in SCENES:
            for center in settings['blink_times']:
                self.assertEqual(blink_amount(center, [center]), 1)
                self.assertEqual(blink_amount(center - 0.5, [center]), 0)
                self.assertEqual(blink_amount(center + 0.5, [center]), 0)
                for offset in np.linspace(-0.3, 0.4, 15):
                    self.assertTrue(0 <= blink_amount(center + offset, [center]) <= 1)

    def test_closed_plate_does_not_replace_background(self):
        scene = self.film.scenes[0]
        frame = scene.open.copy()
        scene.eyelids(frame, 0, override=1)
        difference = np.max(np.abs(frame - scene.open), axis=2)
        allowed = np.zeros_like(difference, dtype=bool)
        for patch in scene.eye_patches:
            x0, x1, y0, y1 = patch[:4]
            allowed[y0:y1, x0:x1] = True
        self.assertEqual(float(difference[~allowed].max()), 0)
        self.assertGreater(float(difference[allowed].max()), 30)

    def test_all_three_shots_render(self):
        for moment in (0, 5, 10, 15, 20, 25, 29.9667, 30):
            frame = self.film.render(moment)
            self.assertEqual(frame.shape, (384, 216, 3))
            self.assertEqual(frame.dtype, np.uint8)
            self.assertGreater(float(frame.mean()), 35)

    def test_each_shot_has_motion(self):
        for scene in self.film.scenes:
            t = scene.cfg['start'] + 1
            first = scene.render(t).astype(np.float32)
            next_frame = scene.render(t + 1).astype(np.float32)
            self.assertGreater(float(np.abs(next_frame - first).mean()), 0.5)

    def test_transitions_are_dissolves_not_hard_cuts(self):
        for index, t in enumerate((10, 20)):
            left = self.film.render(t - 1 / 60).astype(np.float32)
            right = self.film.render(t + 1 / 60).astype(np.float32)
            unblended_left = self.film.scenes[index].render(t).astype(np.float32)
            unblended_right = self.film.scenes[index + 1].render(t).astype(np.float32)
            transition_delta = float(np.abs(right - left).mean())
            hard_cut_delta = float(np.abs(unblended_right - unblended_left).mean())
            self.assertLess(transition_delta, hard_cut_delta * 0.2 + 1)

    def test_dimensions_are_validated(self):
        for width, height in ((0, 100), (101, 100), (100, -2)):
            with self.assertRaises(ValueError):
                HippoFilm(width, height)


if __name__ == '__main__':
    unittest.main()
