"""Feeding motion, grain pickup, eyelid isolation and valid output frames."""
import unittest

import numpy as np

from render_chick import BLINKS, PECKS, POSE_STEPS, ChickFilm, blink_state, feeding_state


class ChickTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.film = ChickFilm(216, 384)

    def test_feeding_pose_reaches_food_and_returns(self):
        for moment in PECKS:
            self.assertAlmostEqual(feeding_state(moment)[0], 1)
            self.assertAlmostEqual(feeding_state(moment - 0.25)[0], 0, places=5)
            self.assertAlmostEqual(feeding_state(moment + 0.41)[0], 0, places=5)
            self.assertEqual(feeding_state(moment)[1], 0)
            self.assertGreater(feeding_state(moment + 0.18)[1], 0.9)
            self.assertEqual(feeding_state(moment + 0.40)[1], 0)

    def test_pose_bank_is_complete_and_not_a_partial_cache(self):
        self.assertEqual(self.film.poses.shape, (POSE_STEPS, 1264, 848, 3))
        self.assertNotIn('.partial.', str(self.film.poses.filename))
        self.assertGreater(float(self.film.poses[0].mean()), 40)
        self.assertGreater(float(self.film.poses[-1].mean()), 40)
        delta = np.abs(self.film.poses[0].astype(float) - self.film.up)
        self.assertLess(float(delta.mean()), 0.6)

    def test_peck_changes_head_position(self):
        raised = self.film.pose_frame(0)[450:930, 380:745]
        lowered = self.film.pose_frame(1)[450:930, 380:745]
        self.assertGreater(float(np.abs(raised - lowered).mean()), 5)

    def test_blinks_only_use_the_eye_patch(self):
        frame = self.film.up.astype(np.float32)
        self.film.apply_blink(frame, 1)
        difference = np.max(np.abs(frame - self.film.up), axis=2)
        x0, x1, y0, y1 = self.film.eye_patch[:4]
        allowed = np.zeros(difference.shape, bool)
        allowed[y0:y1, x0:x1] = True
        self.assertEqual(float(difference[~allowed].max()), 0)
        self.assertGreater(float(difference[allowed].max()), 30)
        for moment in BLINKS:
            self.assertEqual(blink_state(moment), 1)
            self.assertLess(feeding_state(moment)[0], 0.05)

    def test_frames_are_valid_throughout_movie(self):
        for moment in (0, 0.95, 1.20, 7.05, 14.5, 22, 28.9, 29.9667, 30):
            frame = self.film.render(moment)
            self.assertEqual(frame.shape, (384, 216, 3))
            self.assertEqual(frame.dtype, np.uint8)
            self.assertGreater(float(frame.mean()), 40)
            self.assertGreater(float(frame[0].mean()), 20)

    def test_motion_continues_between_pecks(self):
        first = self.film.render(6.6).astype(float)
        later = self.film.render(7.6).astype(float)
        self.assertGreater(float(np.abs(first - later).mean()), 0.5)

    def test_even_positive_output_dimensions(self):
        for width, height in ((0, 100), (101, 100), (100, -2)):
            with self.assertRaises(ValueError):
                ChickFilm(width, height)


if __name__ == '__main__':
    unittest.main()
