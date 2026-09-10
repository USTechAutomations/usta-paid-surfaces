"""Synthetic regression for the real public delivery copy loop."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import build_site

PAGE='<meta name="robots" content="noindex,nofollow"><h1>Synthetic public page</h1>'
class PublicBuildTests(unittest.TestCase):
    def test_private_excluded_public_return_and_catalog_retained(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);pdir=root/'p';out=root/'dist'
            for name in ('thanks','UN1993','a'*20):
                (pdir/name).mkdir(parents=True)
                (pdir/name/'index.html').write_text(PAGE)
            original=Path.read_text
            def guarded(path,*args,**kwargs):
                if path.parent.name=='a'*20: raise AssertionError('buyer bytes read')
                return original(path,*args,**kwargs)
            with patch.object(Path,'read_text',guarded):
                build_site.copy_public_delivery_pages(pdir,out)
            self.assertEqual(sorted(p.name for p in out.iterdir()),['UN1993','thanks'])
            self.assertEqual((out/'thanks'/'index.html').read_text(),PAGE)
            self.assertEqual((out/'UN1993'/'index.html').read_text(),PAGE)
    def test_symlink_escape_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);(root/'p').mkdir();(root/'outside').mkdir()
            (root/'p'/'thanks').symlink_to(root/'outside',target_is_directory=True)
            with self.assertRaises(ValueError):build_site.copy_public_delivery_pages(root/'p',root/'dist')
    def test_source_file_symlink_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);(root/'p'/'thanks').mkdir(parents=True);(root/'outside').write_text(PAGE)
            (root/'p'/'thanks'/'index.html').symlink_to(root/'outside')
            with self.assertRaises(ValueError):build_site.copy_public_delivery_pages(root/'p',root/'dist')
    def test_indexing_requirement_preserved(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);(root/'p'/'thanks').mkdir(parents=True)
            (root/'p'/'thanks'/'index.html').write_text('<h1>Missing marker</h1>')
            with self.assertRaises(ValueError):build_site.copy_public_delivery_pages(root/'p',root/'dist')
if __name__=='__main__':unittest.main()
