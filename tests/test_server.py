"""Playback/download routes and mobile byte-range behavior."""
import http.client
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
import unittest

from serve_video import ROOT, VideoHandler


class QuietHandler(VideoHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless((ROOT / 'exports/viaje-infinito.mp4').is_file(), 'Render the video first')
class PlayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.size = (ROOT / 'exports/viaje-infinito.mp4').stat().st_size

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, method='GET', headers=None):
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            client.request(method, path, headers=headers or {})
            response = client.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            client.close()

    def test_player_is_html_with_video(self):
        status, headers, body = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn('text/html', headers['Content-Type'])
        self.assertIn(b'<video ', body)
        self.assertIn(b'href="/giraffe/download"', body)

    def test_previous_chick_player_remains_available(self):
        status, headers, body = self.request('/pollito')
        self.assertEqual(status, 200)
        self.assertIn(b'href="/chick/download"', body)

    @unittest.skipUnless((ROOT / 'exports/jirafa-bebe.mp4').is_file(), 'Render the giraffe video first')
    def test_giraffe_range_and_download(self):
        status, headers, body = self.request('/giraffe/video.mp4', headers={'Range': 'bytes=0-31'})
        self.assertEqual(status, 206)
        self.assertEqual(len(body), 32)
        self.assertEqual(body[4:8], b'ftyp')
        status, headers, body = self.request('/giraffe/download', 'HEAD')
        self.assertEqual(status, 200)
        self.assertIn('jirafa-bebe.mp4', headers['Content-Disposition'])

    def test_previous_hippo_player_remains_available(self):
        status, headers, body = self.request('/hipopotamo')
        self.assertEqual(status, 200)
        self.assertIn(b'href="/hippo/download"', body)

    @unittest.skipUnless((ROOT / 'exports/pollito-comiendo.mp4').is_file(), 'Render the chick video first')
    def test_chick_range_and_download(self):
        status, headers, body = self.request('/chick/video.mp4', headers={'Range': 'bytes=0-31'})
        self.assertEqual(status, 206)
        self.assertEqual(len(body), 32)
        self.assertEqual(body[4:8], b'ftyp')
        status, headers, body = self.request('/chick/download', 'HEAD')
        self.assertEqual(status, 200)
        self.assertIn('pollito-comiendo.mp4', headers['Content-Disposition'])

    def test_previous_space_player_remains_available(self):
        status, headers, body = self.request('/universo')
        self.assertEqual(status, 200)
        self.assertIn(b'href="/download"', body)
        self.assertIn(b'Viaje', body)

    @unittest.skipUnless((ROOT / 'exports/hipopotamo-bebe.mp4').is_file(), 'Render the hippo video first')
    def test_hippo_range_and_download(self):
        status, headers, body = self.request('/hippo/video.mp4', headers={'Range': 'bytes=0-31'})
        self.assertEqual(status, 206)
        self.assertEqual(len(body), 32)
        self.assertEqual(body[4:8], b'ftyp')
        status, headers, body = self.request('/hippo/download', 'HEAD')
        self.assertEqual(status, 200)
        self.assertIn('hipopotamo-bebe.mp4', headers['Content-Disposition'])

    def test_video_head(self):
        status, headers, body = self.request('/video.mp4', 'HEAD')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'video/mp4')
        self.assertEqual(int(headers['Content-Length']), self.size)
        self.assertEqual(body, b'')

    def test_initial_range(self):
        status, headers, body = self.request('/video.mp4', headers={'Range': 'bytes=0-1023'})
        self.assertEqual(status, 206)
        self.assertEqual(len(body), 1024)
        self.assertEqual(headers['Content-Range'], f'bytes 0-1023/{self.size}')
        self.assertEqual(body[4:8], b'ftyp')

    def test_suffix_range(self):
        status, headers, body = self.request('/video.mp4', headers={'Range': 'bytes=-100'})
        self.assertEqual(status, 206)
        self.assertEqual(len(body), 100)
        self.assertEqual(headers['Content-Range'], f'bytes {self.size-100}-{self.size-1}/{self.size}')

    def test_invalid_ranges(self):
        for value in ['bytes=-0', 'bytes=10-2', 'bytes=-', 'bytes=99999999999-', 'bytes=0-1,5-9']:
            status, headers, body = self.request('/video.mp4', headers={'Range': value})
            self.assertEqual(status, 416, value)
            self.assertEqual(headers['Content-Range'], f'bytes */{self.size}')

    def test_download_has_attachment_name(self):
        status, headers, body = self.request('/download', 'HEAD')
        self.assertEqual(status, 200)
        self.assertIn('attachment;', headers['Content-Disposition'])
        self.assertIn('viaje-infinito.mp4', headers['Content-Disposition'])

    def test_repository_and_traversal_are_not_exposed(self):
        for path in ['/.git/config', '/render_video.py', '/../README.md', '/%2e%2e/README.md']:
            status, headers, body = self.request(path)
            self.assertEqual(status, 404, path)


if __name__ == '__main__':
    unittest.main()
