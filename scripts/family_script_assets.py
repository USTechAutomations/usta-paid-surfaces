"""Copy only explicitly referenced public, local JavaScript into a family build."""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit


class _Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []
        self.module_sources = []

    def handle_starttag(self, tag, attrs):
        if tag != 'script':
            return
        values = [value for name, value in attrs if name == 'src']
        if len(values) > 1:
            raise ValueError('script has ambiguous source attributes')
        if values:
            self.sources.append(values[0])
            if dict(attrs).get('type', '').lower() == 'module':
                self.module_sources.append(values[0])


def copy_local_scripts(source_page: Path, output_dir: Path) -> list[str]:
    """Never recurse into buyer directories or copy unreferenced source files."""
    parsed = _Scripts()
    parsed.feed(source_page.read_text(encoding='utf-8'))
    names = set()
    local_modules = set()
    for src in parsed.sources:
        if not isinstance(src, str) or not src:
            raise ValueError('script source is missing')
        url = urlsplit(src)
        if url.scheme in {'http', 'https'} or (not url.scheme and url.netloc):
            continue  # An explicitly external script is not a local artifact.
        name = url.path.removeprefix('./')
        if url.scheme or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.js', name):
            raise ValueError('local script must be a top-level JavaScript filename')
        names.add(name)
        if src in parsed.module_sources:
            local_modules.add(name)
    # Module dependencies are an explicit public package, not guessed from JS
    # text or discovered by recursively copying a family/buyer directory.
    manifest = source_page.parent / 'public-scripts.json'
    if manifest.is_symlink():
        raise ValueError('public script manifest is unsafe')
    if manifest.exists():
        declared = json.loads(manifest.read_text(encoding='utf-8'))
        if (not isinstance(declared, list) or len(declared) > 64 or
                any(not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.js', name)
                    for name in declared)):
            raise ValueError('public script manifest must contain top-level JavaScript filenames')
        if not local_modules.issubset(declared):
            raise ValueError('public script manifest omits a module entry point')
        names.update(declared)
    elif local_modules:
        raise ValueError('local script modules require an explicit public script manifest')
    # Validate the complete set before copying any bytes.
    for name in sorted(names):
        source = source_page.parent / name
        destination = output_dir / name
        if source.is_symlink() or not source.is_file():
            raise ValueError('referenced local script is missing or unsafe')
        if destination.is_symlink() or output_dir.is_symlink():
            raise ValueError('script destination is unsafe')
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in sorted(names):
        shutil.copyfile(source_page.parent / name, output_dir / name)
    return sorted(names)
