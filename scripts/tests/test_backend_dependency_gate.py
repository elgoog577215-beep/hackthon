"""Keep backend dependency cycles out of backup and release branches."""
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'backend_dependency_audit',
    ROOT / 'apps/lingzhi/scripts/audit_backend_dependencies.py',
)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class BackendDependencyGate(unittest.TestCase):
    def test_production_import_graph_has_no_cycles(self):
        graph = AUDIT.dependency_graph(AUDIT.backend_modules())
        self.assertEqual(AUDIT.cyclic_groups(graph), [])
