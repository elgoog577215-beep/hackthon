"""The public source must resolve deployment state from the environment."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from sqlalchemy.engine import make_url


class PublicConfigurationTest(unittest.TestCase):
    def load_settings(self):
        path = Path(__file__).resolve().parents[1] / "common/config.py"
        spec = importlib.util.spec_from_file_location("qizhi_test_settings", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.Settings()

    def test_prod_uses_explicit_database_and_preserves_special_characters(self):
        with patch.dict(os.environ, {
            "PYTHON_DOTENV_DISABLED": "1", "ENV": "PROD",
            "DATABASE_HOST": "database.example.invalid", "DATABASE_PORT": "5433",
            "DATABASE_USER": "teacher", "DATABASE_NAME": "course_test",
            "DATABASE_PASSWORD": "test@password:/?#",
        }, clear=True):
            settings = self.load_settings()
            for value in (settings.SYNC_DATABASE_URL, settings.ASYNC_DATABASE_URL):
                url = make_url(value)
                self.assertEqual(url.host, "database.example.invalid")
                self.assertEqual(url.port, 5433)
                self.assertEqual(url.database, "course_test")
                self.assertEqual(url.password, "test@password:/?#")

    def test_explicit_driver_urls_override_component_defaults(self):
        with patch.dict(os.environ, {
            "PYTHON_DOTENV_DISABLED": "1",
            "SYNC_DATABASE_URL": "postgresql+psycopg://example.invalid/sync_test",
            "ASYNC_DATABASE_URL": "postgresql+asyncpg://example.invalid/async_test",
        }, clear=True):
            settings = self.load_settings()
            self.assertEqual(settings.SYNC_DATABASE_URL, os.environ["SYNC_DATABASE_URL"])
            self.assertEqual(settings.ASYNC_DATABASE_URL, os.environ["ASYNC_DATABASE_URL"])

    def test_missing_deployment_configuration_does_not_select_remote_state(self):
        with patch.dict(os.environ, {"PYTHON_DOTENV_DISABLED": "1", "ENV": "PROD"}, clear=True):
            settings = self.load_settings()
            self.assertEqual(make_url(settings.SYNC_DATABASE_URL).host, "127.0.0.1")
            self.assertEqual(make_url(settings.ASYNC_DATABASE_URL).host, "127.0.0.1")
            self.assertEqual(settings.LOCAL_ANALYSIS_API_KEY, "")


if __name__ == "__main__":
    unittest.main()
