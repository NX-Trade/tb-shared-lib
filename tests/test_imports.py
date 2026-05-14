import importlib
import pkgutil
import unittest

import tb_utils
import tb_utils.models
import tb_utils.schema


class TestSharedLibImports(unittest.TestCase):
    """
    Comprehensive import testing for tb-shared-lib.
    Ensures that all modules are discoverable and all public exports in __init__.py
    are actually present and importable.
    """

    def test_package_structure(self):
        """Test that the main package and core subpackages are present."""
        self.assertIsNotNone(tb_utils)
        self.assertIsNotNone(tb_utils.models)
        self.assertIsNotNone(tb_utils.schema)

    def test_recursive_module_imports(self):
        """Recursively test that EVERY module within tb_utils can be imported without error."""
        package = tb_utils
        for _, module_name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            # Skip tests directory if it accidentally gets included
            if ".tests" in module_name:
                continue
            with self.subTest(module=module_name):
                try:
                    module = importlib.import_module(module_name)
                    self.assertIsNotNone(module)
                except Exception as e:
                    self.fail(f"Failed to import module {module_name}: {e}")

    def test_top_level_exports(self):
        """Test that all members expected at the top-level tb_utils package are available."""
        expected_exports = [
            "DatabaseConfig",
            "db_settings",
            "get_db",
            "SessionLocal",
            "Base",
            "Instrument",
            "Candle",
            "OptionChain",
            "News",
        ]
        for name in expected_exports:
            with self.subTest(member=name):
                self.assertTrue(hasattr(tb_utils, name), f"tb_utils missing export: {name}")

    def test_models_all_exports(self):
        """Verify all items in tb_utils.models.__all__ are importable from the package."""
        self.assertTrue(hasattr(tb_utils.models, "__all__"), "tb_utils.models missing __all__")
        for name in tb_utils.models.__all__:
            with self.subTest(model=name):
                member = getattr(tb_utils.models, name, None)
                self.assertIsNotNone(
                    member, f"Model {name} listed in __all__ but not found in tb_utils.models"
                )

    def test_schema_all_exports(self):
        """Verify all items in tb_utils.schema.__all__ are importable from the package."""
        self.assertTrue(hasattr(tb_utils.schema, "__all__"), "tb_utils.schema missing __all__")
        for name in tb_utils.schema.__all__:
            with self.subTest(schema=name):
                member = getattr(tb_utils.schema, name, None)
                self.assertIsNotNone(
                    member, f"Schema {name} listed in __all__ but not found in tb_utils.schema"
                )


if __name__ == "__main__":
    unittest.main()
