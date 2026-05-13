import importlib
import pkgutil
import unittest

import tb_utils.models
import tb_utils.schema


class TestSharedLibImports(unittest.TestCase):
    def test_import_all_models(self):
        """Recursively test that all model modules can be imported."""

        package = tb_utils.models
        for _, module_name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                self.assertIsNotNone(module)

    def test_import_all_schemas(self):
        """Recursively test that all schema modules can be imported."""

        package = tb_utils.schema
        for _, module_name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                self.assertIsNotNone(module)


if __name__ == "__main__":
    unittest.main()
