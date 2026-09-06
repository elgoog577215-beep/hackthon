import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release_targets import changed_paths, targets


class ReleaseTargetsTest(unittest.TestCase):
    def test_docs_never_release(self):
        self.assertEqual(targets(["README.md", "apps/lingzhi/docs/a.md", "apps/qizhi/docs/b.md"]),
                         {"tuotu": False, "zju": False, "zju_services": []})

    def test_portal_only_releases_zju_website(self):
        self.assertEqual(targets(["apps/qizhi/client/website/src/App.vue"]),
                         {"tuotu": False, "zju": True, "zju_services": ["website"]})

    def test_lingzhi_releases_both_instances(self):
        self.assertEqual(targets(["apps/lingzhi/backend/main.py"]),
                         {"tuotu": True, "zju": True, "zju_services": ["lingzhi"]})

    def test_identity_releases_zju_consumers_together(self):
        result = targets(["apps/qizhi/server/routers/user.py"])
        self.assertFalse(result["tuotu"])
        self.assertEqual(result["zju_services"], ["lingzhi", "server", "website"])

    def test_deleted_source_and_shared_build_tool_are_not_skipped(self):
        self.assertTrue(targets(["apps/lingzhi/backend/deleted.py"])["tuotu"])
        self.assertEqual(targets(["scripts/release_targets.py"])["zju_services"], ["lingzhi", "server", "website"])

    def test_independent_deployment_config(self):
        self.assertFalse(targets(["deploy/zju/docker-compose.yml"])["tuotu"])
        self.assertFalse(targets(["deploy/tuotu/build.sh"])["zju"])

    def test_identical_git_revisions_do_not_release(self):
        paths = changed_paths("HEAD", "HEAD")
        self.assertEqual(paths, [])
        self.assertEqual(targets(paths), {"tuotu": False, "zju": False, "zju_services": []})
