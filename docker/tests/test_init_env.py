import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("init_env", Path(__file__).parents[1] / "init_env.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class InitializationTest(unittest.TestCase):
    def test_new_install_and_rerun_preserve_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / ".env"
            self.assertTrue(module.initialize(target))
            original = target.read_bytes()
            values = dict(line.split("=", 1) for line in original.decode().splitlines() if not line.startswith("#"))
            self.assertEqual(values["ANALYSIS_FLAVOR"], "full")
            self.assertEqual(values["APP_UID"], str(os.getuid() or 10001))
            self.assertEqual(values["APP_GID"], str(os.getgid() or 10001))
            self.assertEqual(values["APP_STORAGE_USER"], "zhengqinyun")
            self.assertEqual(values["APP_DOCKERFILE"], "docker/app/Dockerfile.analysis")
            self.assertEqual(values["HTTP_BIND"], "127.0.0.1")
            credentials = [values[key] for key in ("SECRET_KEY", "MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD", "MONGO_PASSWORD")]
            self.assertEqual(len(set(credentials)), 4)
            self.assertTrue(all(len(value) == 64 for value in credentials))
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertFalse(module.initialize(target))
            self.assertEqual(target.read_bytes(), original)

    def test_existing_configuration_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / ".env"
            original = b"ANALYSIS_FLAVOR=core\nSECRET_KEY=existing-private-value\n"
            target.write_bytes(original)
            self.assertFalse(module.initialize(target))
            self.assertEqual(target.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
