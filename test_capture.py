import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import app

class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app.app)
        self.headers={'X-FormulaDrop-Capture':'1'}

    def test_requires_button_header(self):
        self.assertEqual(self.client.post('/api/capture').status_code,403)

    @patch('app.sys.platform','darwin')
    def test_success_and_temporary_cleanup(self):
        image=(Path(__file__).parent/'static/examples/2.png').read_bytes()
        paths=[]
        def capture(command,**kwargs):
            self.assertEqual(command[:4],['/usr/sbin/screencapture','-i','-s','-x'])
            paths.append(Path(command[-1]));paths[-1].write_bytes(image)
            return subprocess.CompletedProcess(command,0,b'',b'')
        with patch('app.subprocess.run',side_effect=capture):
            r=self.client.post('/api/capture',headers=self.headers)
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.content,image)
        self.assertFalse(paths[0].exists())
        self.assertFalse(app.capture_lock.locked())

    @patch('app.sys.platform','darwin')
    def test_cancel_permission_error_timeout(self):
        for result,code in [(subprocess.CompletedProcess([],1,b'',b''),204),(subprocess.CompletedProcess([],1,b'',b'could not create image'),403)]:
            with patch('app.subprocess.run',return_value=result):
                self.assertEqual(self.client.post('/api/capture',headers=self.headers).status_code,code)
        with patch('app.subprocess.run',side_effect=subprocess.TimeoutExpired('screencapture',120)):
            self.assertEqual(self.client.post('/api/capture',headers=self.headers).status_code,408)
        self.assertFalse(app.capture_lock.locked())

    def test_concurrent_capture(self):
        app.capture_lock.acquire()
        try:
            with patch('app.sys.platform','darwin'):
                self.assertEqual(self.client.post('/api/capture',headers=self.headers).status_code,409)
        finally:
            app.capture_lock.release()
