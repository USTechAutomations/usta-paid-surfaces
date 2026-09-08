"""Namespace-tolerant helpers over xml.etree.ElementTree.

Real IRS AIR transmissions declare an XML namespace; test files and hand-built
XML often do not. These helpers match elements by their *local* name (the part
after a `}` in a Clark-notation tag) so the same rule code works either way.
"""
from __future__ import annotations

from xml.etree.ElementTree import Element


def local(tag: str) -> str:
    """Strip a namespace off a tag: '{urn:x}Foo' -> 'Foo'."""
    return tag.split("}", 1)[1] if "}" in tag else tag


def children_local(elem: Element | None, name: str) -> list[Element]:
    if elem is None:
        return []
    return [c for c in list(elem) if local(c.tag) == name]


def child_local(elem: Element | None, name: str) -> Element | None:
    if elem is None:
        return None
    for c in list(elem):
        if local(c.tag) == name:
            return c
    return None


def descendants_local(elem: Element | None, name: str) -> list[Element]:
    if elem is None:
        return []
    return [e for e in elem.iter() if local(e.tag) == name]


def text(elem: Element | None, default: str = "") -> str:
    if elem is None or elem.text is None:
        return default
    return elem.text.strip()


def child_text(elem: Element | None, name: str, default: str = "") -> str:
    return text(child_local(elem, name), default)
