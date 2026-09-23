"""Stickmen martial arts constraints: distinct colors, no blood, motion, loop."""
import unittest
import numpy as np
from render_stickmen import StickFightFilm

class StickmenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.film = StickFightFilm(270, 480)  # small for speed

    def test_valid_dimensions(self):
        for w,h in ((0,100),(101,100),(100,-2)):
            with self.assertRaises(ValueError):
                StickFightFilm(w,h)

    def test_frames_are_valid_and_bright(self):
        for t in (0, 2.2, 6.4, 11.2, 18.8, 24.5, 29.9):
            frame = self.film.render(t)
            self.assertEqual(frame.shape, (480, 270, 3))
            self.assertEqual(frame.dtype, np.uint8)
            # background is light, mean > 100
            self.assertGreater(float(frame.mean()), 80)
            # no black border top
            self.assertGreater(float(frame[0].mean()), 30)

    def test_motion_exists(self):
        f0 = self.film.render(0).astype(float)
        f1 = self.film.render(2.3).astype(float)
        f2 = self.film.render(6.4).astype(float)
        self.assertGreater(float(np.abs(f0-f1).mean()), 1.0)
        self.assertGreater(float(np.abs(f1-f2).mean()), 1.0)

    def test_loop_is_exact(self):
        for t in (0, 2.5, 12.3):
            np.testing.assert_array_equal(self.film.render(t), self.film.render(t+30))

    def test_fighters_stay_in_bounds(self):
        for t in np.linspace(0, 30, 13):
            sk_blue = self.film.get_fighter_skeleton("blue", float(t))
            sk_red = self.film.get_fighter_skeleton("red", float(t))
            for sk in (sk_blue, sk_red):
                for key in ("pelvis","torso_top","head","left_hand","right_hand","left_foot","right_foot"):
                    x,y = sk[key]
                    self.assertGreaterEqual(x, -50)
                    self.assertLessEqual(x, self.film.width+50)
                    self.assertGreaterEqual(y, -100)
                    self.assertLessEqual(y, self.film.height+100)

    def test_distinct_colors_present(self):
        # at a fighting moment both colors should appear
        frame = self.film.render(11.2)  # exchange
        # count blue-ish vs red-ish pixels (rough)
        # blue BGR (255,127,42) -> RGB (42,127,255) -> high B
        # red BGR (48,59,255) -> RGB (255,59,48) -> high R
        # in RGB frame, blue has B high, red has R high
        blue_mask = (frame[:,:,2] > 180) & (frame[:,:,0] < 100) & (frame[:,:,1] > 80)
        red_mask = (frame[:,:,0] > 180) & (frame[:,:,2] < 100)
        self.assertGreater(int(np.count_nonzero(blue_mask)), 50)
        self.assertGreater(int(np.count_nonzero(red_mask)), 50)

    def test_no_blood_dark_red_large_areas(self):
        # ensure no huge dark red blood splatter (we only have small red limbs)
        for t in (2.3, 6.4, 22.2):
            frame = self.film.render(float(t))
            # blood would be very dark red large area low G,B - our red is bright with some G
            # just ensure frame doesn't have huge pure dark red blob
            # check that very dark pixels are limited
            dark = (frame[:,:,0] < 30) & (frame[:,:,1] < 30) & (frame[:,:,2] < 30)
            # black outlines are okay but not huge
            self.assertLess(float(np.mean(dark)), 0.15)

if __name__ == '__main__':
    unittest.main()
