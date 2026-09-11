import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

VOID_ELEMENTS = {
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
    'meta', 'param', 'source', 'track', 'wbr',
}
EXCLUDED_TAGS = {'script', 'style', 'nav', 'footer'}
CHECKOUT_HOSTS = {'buy.stripe.com', 'checkout.stripe.com'}
SAMPLE_EXTENSIONS = ('.csv', '.zip', '.json')
SAMPLE_WORDS = ('sample', 'example')
_WS_RE = re.compile(r'\s+')


class _Node:
    __slots__ = ('tag', 'attrs', 'children')

    def __init__(self, tag, attrs):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node('#root', [])
        self._stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs)
        self._stack[-1].children.append(node)
        if tag not in VOID_ELEMENTS:
            self._stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self._stack[-1].children.append(_Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                return

    def handle_data(self, data):
        self._stack[-1].children.append(data)


def _find_first(node, tag):
    for child in node.children:
        if isinstance(child, str):
            continue
        if child.tag == tag:
            return child
        found = _find_first(child, tag)
        if found is not None:
            return found
    return None


def _normalize_ws(s):
    return _WS_RE.sub(' ', s).strip()


def _get_text(node):
    parts = []

    def rec(n):
        for c in n.children:
            if isinstance(c, str):
                parts.append(c)
            elif c.tag not in EXCLUDED_TAGS:
                rec(c)

    rec(node)
    return _normalize_ws(' '.join(parts))


def _is_rejected(href):
    raw = href.strip()
    if not raw or raw.startswith('#'):
        return True
    return urlparse(raw).scheme.lower() in ('javascript', 'data')


def _dedupe(items):
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _collect(node, h1_out, anchor_out, text_parts):
    for child in node.children:
        if isinstance(child, str):
            text_parts.append(child)
            continue
        if child.tag in EXCLUDED_TAGS:
            continue
        if child.tag == 'h1':
            h1_out.append(_get_text(child))
        if child.tag == 'a':
            anchor_out.append(child)
        _collect(child, h1_out, anchor_out, text_parts)


def parse_page(html, base_url):
    builder = _TreeBuilder()
    builder.feed(html)
    root = builder.root

    region = _find_first(root, 'main') or _find_first(root, 'body') or root

    h1_list = []
    anchors = []
    text_parts = []
    _collect(region, h1_list, anchors, text_parts)
    text = _normalize_ws(' '.join(text_parts))

    all_links = []
    checkout_links = []
    contact_links = []
    sample_links = []

    for anchor in anchors:
        href = anchor.attrs.get('href')
        if href is None or _is_rejected(href):
            continue
        resolved = urljoin(base_url, href.strip())
        parsed = urlparse(resolved)
        all_links.append(resolved)

        if parsed.hostname in CHECKOUT_HOSTS:
            checkout_links.append(resolved)

        if parsed.scheme.lower() == 'mailto' or parsed.path.rstrip('/') == '/partner':
            contact_links.append(resolved)

        anchor_text = _get_text(anchor).lower()
        path_lower = parsed.path.lower()
        is_sample_text = any(word in anchor_text for word in SAMPLE_WORDS)
        is_sample_file = path_lower.endswith(SAMPLE_EXTENSIONS)
        if is_sample_text or is_sample_file:
            sample_links.append(resolved)

    return {
        'h1': h1_list,
        'text': text,
        'checkout_links': _dedupe(checkout_links),
        'contact_links': _dedupe(contact_links),
        'sample_links': _dedupe(sample_links),
        'all_links': _dedupe(all_links),
    }
