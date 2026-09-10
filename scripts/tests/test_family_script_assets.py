import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'family_script_assets.py'
spec = importlib.util.spec_from_file_location('family_script_assets', MODULE)
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)


class LocalScriptAssets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = self.root / 'family'
        self.src.mkdir()
        self.page = self.src / 'index.html'
        self.out = self.root / 'dist'

    def test_exact_public_script_bytes_and_no_private_recursion(self):
        self.page.write_text('<script src="./tool.js"></script><script src="https://example.invalid/tracker.js"></script>')
        script = b'"use strict";\n/* exact original bytes */\n'
        (self.src / 'tool.js').write_bytes(script)
        (self.src / 'private.js').write_text('not referenced')
        (self.src / 'p').mkdir()
        (self.src / 'p' / 'buyer.js').write_text('buyer artifact')
        self.assertEqual(assets.copy_local_scripts(self.page, self.out), ['tool.js'])
        self.assertEqual((self.out / 'tool.js').read_bytes(), script)
        self.assertEqual([p.name for p in self.out.iterdir()], ['tool.js'])

    def test_missing_asset_fails_before_partial_copy(self):
        self.page.write_text('<script src="a.js"></script><script src="missing.js"></script>')
        (self.src / 'a.js').write_text('present')
        with self.assertRaises(ValueError):
            assets.copy_local_scripts(self.page, self.out)
        self.assertFalse(self.out.exists())

    def test_traversal_absolute_encoded_and_non_js_sources_refused(self):
        for src in ('../private.js', '/private.js', '%2e%2e/private.js', 'p/buyer.js', 'data:text/javascript,alert(1)', 'key.json', ''):
            with self.subTest(src=src):
                self.page.write_text('<script src="' + src + '"></script>')
                with self.assertRaises(ValueError):
                    assets.copy_local_scripts(self.page, self.out)

    def test_symlink_and_ambiguous_source_refused(self):
        outside = self.root / 'outside.js'
        outside.write_text('outside')
        (self.src / 'tool.js').symlink_to(outside)
        self.page.write_text('<script src="tool.js"></script>')
        with self.assertRaises(ValueError):
            assets.copy_local_scripts(self.page, self.out)

    def test_module_dependencies_are_explicit_and_exact(self):
        self.page.write_text('<script type="module" src="./app.js"></script>')
        (self.src / 'app.js').write_text('import {identify} from "./lookup.js";')
        (self.src / 'lookup.js').write_text('export const identify = () => "fixture";')
        with self.assertRaises(ValueError):
            assets.copy_local_scripts(self.page, self.out)
        (self.src / 'public-scripts.json').write_text('["app.js", "lookup.js"]')
        self.assertEqual(assets.copy_local_scripts(self.page, self.out), ['app.js', 'lookup.js'])
        for name in ('app.js', 'lookup.js'):
            self.assertEqual((self.src / name).read_bytes(), (self.out / name).read_bytes())

    def test_unsafe_manifest_never_copies_private_paths(self):
        self.page.write_text('<script type="module" src="app.js"></script>')
        for body in ('["../key.js"]', '["app.js", "p/buyer.js"]', '{}', '[null]'):
            with self.subTest(body=body):
                (self.src / 'public-scripts.json').write_text(body)
                with self.assertRaises(ValueError):
                    assets.copy_local_scripts(self.page, self.out)
        self.page.write_text('<script src="a.js" src="b.js"></script>')
        with self.assertRaises(ValueError):
            assets.copy_local_scripts(self.page, self.out)


if __name__ == '__main__':
    unittest.main()
