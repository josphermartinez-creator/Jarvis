"""Small deterministic checks for the seamless animation."""
import unittest

import numpy as np

from render_video import DURATION, Flight, smoothstep


class FlightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.flight = Flight(216, 384)

    def test_exact_visual_period(self):
        for moment in (0, 2.5, 14.75):
            np.testing.assert_array_equal(
                self.flight.render(moment), self.flight.render(moment + DURATION)
            )

    def test_movement_is_not_a_still_image(self):
        first = self.flight.render(1).astype(np.float32)
        later = self.flight.render(2).astype(np.float32)
        self.assertGreater(float(np.abs(first - later).mean()), 1.0)

    def test_loop_join_has_no_cut(self):
        first = self.flight.render(0).astype(np.float32)
        previous = self.flight.render(DURATION - 1 / 30).astype(np.float32)
        following = self.flight.render(1 / 30).astype(np.float32)
        seam = float(np.abs(previous - first).mean())
        step = float(np.abs(following - first).mean())
        self.assertLess(seam, step * 1.8 + 0.1)

    def test_frames_have_valid_size_and_pixels(self):
        for moment in (0, 6, 12, 18, 24, 29.99):
            frame = self.flight.render(moment)
            self.assertEqual(frame.shape, (384, 216, 3))
            self.assertEqual(frame.dtype, np.uint8)
            self.assertGreater(int(frame.max()), 150)
            self.assertGreater(float(frame.mean()), 3)

    def test_fades_are_bounded(self):
        result = smoothstep(0, 100, np.array([-10, 0, 50, 100, 1000]))
        np.testing.assert_array_equal(result, [0, 0, 0.5, 1, 1])


if __name__ == "__main__":
    unittest.main()
