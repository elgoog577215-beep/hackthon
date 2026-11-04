"""Run with: python -m unittest discover -s scripts -p test_ui_development_startup.py."""
import io
import json
import unittest
from unittest.mock import patch

import run_ui_development as launcher


class Response(io.BytesIO):
    status = 200

    def __init__(self, payload, content_type='application/json'):
        super().__init__(payload.encode())
        self.headers = {'Content-Type': content_type}


class StartupTests(unittest.TestCase):
    def test_missing_config_prevents_any_child_process(self):
        with patch.object(launcher.sys, 'argv', ['run', '--state-dir', '/tmp/lingzhi-startup-test']), \
             patch.dict(launcher.os.environ, {}, clear=True), \
             patch.object(launcher, 'dotenv_values', return_value={}), \
             patch.object(launcher.shutil, 'which', return_value='/usr/bin/npm'), \
             patch.object(launcher.socket, 'socket'), \
             patch.object(launcher.Path, 'mkdir'), \
             patch.object(launcher.subprocess, 'Popen') as spawn, \
             patch.object(launcher.webbrowser, 'open') as browser, \
             patch.object(launcher.sys, 'stderr', io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                launcher.main()
            self.assertEqual(raised.exception.code, 2)
            spawn.assert_not_called()
            browser.assert_not_called()

    def test_html_success_is_not_an_api_success(self):
        with patch.object(launcher.urllib.request, 'urlopen', return_value=Response('<html>maintenance</html>', 'text/html')):
            self.assertFalse(launcher.check_ready('http://localhost/api/study/auth/config', {'development_identity': True}))

    def test_wrong_identity_is_not_ready(self):
        with patch.object(launcher.urllib.request, 'urlopen', return_value=Response(json.dumps({'development_identity': False}))):
            self.assertFalse(launcher.check_ready('http://localhost/api/study/auth/config', {'development_identity': True}))

    def test_student_identity_is_required(self):
        expected = {'id': 'local-student:development', 'role': 'student'}
        with patch.object(launcher.urllib.request, 'urlopen', return_value=Response(json.dumps(expected))):
            self.assertTrue(launcher.check_ready('http://localhost/api/study/auth/me', expected))

    def test_connection_failure_is_not_ready(self):
        with patch.object(launcher.urllib.request, 'urlopen', side_effect=OSError('connection refused')):
            self.assertFalse(launcher.check_ready('http://localhost/api/study/auth/config', {}))


if __name__ == '__main__':
    unittest.main()
