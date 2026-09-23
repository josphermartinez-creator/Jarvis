"""Realism constraints: fixed anatomy/background and local chewing only."""
import unittest

import numpy as np

from render_giraffe import BLINKS, GiraffeFilm, blink_state, chewing_state


class GiraffeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.film = GiraffeFilm(216, 384)

    def test_head_neck_and_coat_do_not_deform(self):
        original = self.film.rest
        for moment in (0.36, 4.4, 10.6, 17.35, 25.3):
            frame = self.film.native_frame(moment)
            # Ossicones, ears and upper skull stay unchanged.
            np.testing.assert_array_equal(frame[300:510, 105:620], original[300:510, 105:620])
            # Nostrils/upper muzzle and neck markings remain fixed.
            np.testing.assert_array_equal(frame[642:700, 484:562], original[642:700, 484:562])
            np.testing.assert_array_equal(frame[858:1376, 150:469], original[858:1376, 150:469])

    def test_only_local_mouth_eyes_and_held_leaves_can_change(self):
        allowed = np.zeros((self.film.h, self.film.w), bool)
        x0, y0, x1, y1 = self.film.jaw_box
        allowed[y0:y1, x0:x1] = True
        allowed |= self.film.leaf_weight > 0
        for eye in self.film.eyes:
            ex0, ex1, ey0, ey1 = eye[:4]
            allowed[ey0:ey1, ex0:ex1] = True
        for moment in (0.36, 4.4, 17.35):
            frame = self.film.native_frame(moment)
            np.testing.assert_array_equal(frame[~allowed], self.film.rest[~allowed])

    def test_chewing_is_visible_and_lateral(self):
        first = self.film.native_frame(0)[730:824, 440:605].astype(float)
        second = self.film.native_frame(0.36)[730:824, 440:605].astype(float)
        self.assertGreater(float(np.abs(first - second).mean()), 1.0)
        values = [chewing_state(float(t)) for t in np.linspace(0, 30, 300)]
        self.assertTrue(all(0 <= item[0] <= 1 for item in values))
        self.assertTrue(any(item[1] < -2 for item in values))
        self.assertTrue(any(item[1] > 2 for item in values))

    def test_visual_loop_is_exact(self):
        for moment in (0, 2.5, 14.75):
            np.testing.assert_array_equal(self.film.render(moment), self.film.render(moment + 30))

    def test_incidental_blinks_close_and_reopen(self):
        for moment in BLINKS:
            self.assertEqual(blink_state(moment), 1)
            self.assertEqual(blink_state(moment - 0.5), 0)
            self.assertEqual(blink_state(moment + 0.5), 0)

    def test_valid_bright_frames_without_borders(self):
        for moment in (0, 0.36, 4.4, 12.1, 24.2, 29.9667):
            frame = self.film.render(moment)
            self.assertEqual(frame.shape, (384, 216, 3))
            self.assertEqual(frame.dtype, np.uint8)
            self.assertGreater(float(frame.mean()), 40)
            self.assertGreater(float(frame[0].mean()), 30)

    def test_positive_even_dimensions(self):
        for width, height in ((0, 100), (101, 100), (100, -2)):
            with self.assertRaises(ValueError):
                GiraffeFilm(width, height)


if __name__ == '__main__':
    unittest.main()
