"""Read/modify/write model for Mount & Blade II: Bannerlord scene.xscene files.

scene.xscene files are plain XML that the editor writes with:
  - <?xml version="1.0"?> declaration (double-quoted, no encoding attribute)
  - CRLF line endings
  - Tab indentation
  - Self-closing empty elements with no space before /> e.g. <level name="base"/>
  - Trailing blank line: file ends with </root>\\r\\n\\r\\n

Prefab XML files (Prefabs/*.xml) use the same game_entity schema but have no
XML declaration and start directly with <prefabs>.

The tree is kept as xml.etree.ElementTree source of truth.  All text/tail
whitespace from the original parse is preserved so that round-trips are
byte-identical to the original file.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Iterator


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------

def _escape_attrib(value: str) -> str:
    value = value.replace("&", "&amp;")
    value = value.replace("<", "&lt;")
    value = value.replace(">", "&gt;")
    value = value.replace('"', "&quot;")
    return value


def _serialize(elem: ET.Element, out: list[bytes]) -> None:
    """Recursively serialize *elem* into *out* using Bannerlord's XML style."""
    tag = elem.tag
    attribs = "".join(
        f' {k}="{_escape_attrib(v)}"' for k, v in elem.attrib.items()
    )
    children = list(elem)
    if not children and elem.text is None:
        # Self-closing — no space before /
        out.append(f"<{tag}{attribs}/>".encode())
    else:
        out.append(f"<{tag}{attribs}>".encode())
        if elem.text:
            # ET normalises CRLF -> LF when parsing; restore CRLF on output
            out.append(elem.text.replace("\n", "\r\n").encode())
        for child in children:
            _serialize(child, out)
            if child.tail:
                out.append(child.tail.replace("\n", "\r\n").encode())
        out.append(f"</{tag}>".encode())


def _write_tree(tree: ET.ElementTree, path: str, *, xml_declaration: bool) -> None:
    """Serialize *tree* to *path* in Bannerlord's canonical byte format."""
    root = tree.getroot()
    out: list[bytes] = []
    if xml_declaration:
        out.append(b'<?xml version="1.0"?>\r\n')
    _serialize(root, out)
    # All Bannerlord XML files end with an extra blank line after the root tag
    out.append(b"\r\n\r\n")
    with open(path, "wb") as fh:
        fh.writelines(out)


# ---------------------------------------------------------------------------
# Entity wrapper
# ---------------------------------------------------------------------------

class Entity:
    """Thin wrapper around a <game_entity> Element.

    The underlying Element is mutated directly; this object is a view.
    """

    def __init__(self, elem: ET.Element) -> None:
        self._elem = elem

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def prefab(self) -> str | None:
        """Prefab name (attribute 'prefab'), or None for inline entities."""
        return self._elem.get("prefab")

    @property
    def name(self) -> str | None:
        """Entity name (attribute 'name'), used by inline/named entities."""
        return self._elem.get("name")

    # ------------------------------------------------------------------
    # Transform
    # ------------------------------------------------------------------

    def _transform(self) -> ET.Element | None:
        return self._elem.find("transform")

    def _parse_floats(self, value: str) -> tuple[float, ...]:
        return tuple(float(x.strip()) for x in value.split(","))

    @property
    def position(self) -> tuple[float, float, float] | None:
        t = self._transform()
        if t is None:
            return None
        v = t.get("position")
        if v is None:
            return None
        vals = self._parse_floats(v)
        return (vals[0], vals[1], vals[2])

    @position.setter
    def position(self, value: tuple[float, float, float]) -> None:
        t = self._transform()
        if t is None:
            raise ValueError("Entity has no <transform> element")
        t.set("position", "%.3f, %.3f, %.3f" % value)

    @property
    def rotation_euler(self) -> tuple[float, float, float] | None:
        t = self._transform()
        if t is None:
            return None
        v = t.get("rotation_euler")
        if v is None:
            return None
        vals = self._parse_floats(v)
        return (vals[0], vals[1], vals[2])

    @rotation_euler.setter
    def rotation_euler(self, value: tuple[float, float, float]) -> None:
        t = self._transform()
        if t is None:
            raise ValueError("Entity has no <transform> element")
        t.set("rotation_euler", "%.3f, %.3f, %.3f" % value)

    @property
    def scale(self) -> tuple[float, float, float] | None:
        t = self._transform()
        if t is None:
            return None
        v = t.get("scale")
        if v is None:
            return None
        vals = self._parse_floats(v)
        return (vals[0], vals[1], vals[2])

    @scale.setter
    def scale(self, value: tuple[float, float, float]) -> None:
        t = self._transform()
        if t is None:
            raise ValueError("Entity has no <transform> element")
        t.set("scale", "%.3f, %.3f, %.3f" % value)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @property
    def level_names(self) -> list[str]:
        levels = self._elem.find("levels")
        if levels is None:
            return []
        return [lv.get("name", "") for lv in levels if lv.tag == "level"]

    @property
    def tag_names(self) -> list[str]:
        tags = self._elem.find("tags")
        if tags is None:
            return []
        return [tg.get("name", "") for tg in tags if tg.tag == "tag"]

    @property
    def script_names(self) -> list[str]:
        scripts = self._elem.find("scripts")
        if scripts is None:
            return []
        return [sc.get("name", "") for sc in scripts if sc.tag == "script"]

    @property
    def children(self) -> list["Entity"]:
        children_elem = self._elem.find("children")
        if children_elem is None:
            return []
        return [Entity(ch) for ch in children_elem if ch.tag == "game_entity"]

    # ------------------------------------------------------------------
    # Internal access for Scene
    # ------------------------------------------------------------------

    @property
    def _element(self) -> ET.Element:
        return self._elem


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------

_FMT = "%.3f"


def _fmt3(v: tuple[float, float, float]) -> str:
    return "%s, %s, %s" % (_FMT % v[0], _FMT % v[1], _FMT % v[2])


def _make_entity_element(
    prefab: str,
    position: tuple[float, float, float],
    rotation_euler: tuple[float, float, float],
    scale: tuple[float, float, float] | None,
    levels: list[str] | None,
    *,
    indent: int,
) -> ET.Element:
    """Build a new <game_entity> Element with tab-indented text/tail."""
    tab = "\t" * indent

    ge = ET.Element("game_entity", prefab=prefab)
    ge.text = "\n" + tab + "\t"

    xform_attrib: dict[str, str] = {
        "position": _fmt3(position),
        "rotation_euler": _fmt3(rotation_euler),
    }
    if scale is not None:
        xform_attrib["scale"] = _fmt3(scale)
    xform = ET.SubElement(ge, "transform", **xform_attrib)

    if levels:
        xform.tail = "\n" + tab + "\t"
        lvls_elem = ET.SubElement(ge, "levels")
        lvls_elem.text = "\n" + tab + "\t\t"
        for i, lv in enumerate(levels):
            lv_elem = ET.SubElement(lvls_elem, "level", name=lv)
            lv_elem.tail = "\n" + tab + "\t\t" if i < len(levels) - 1 else "\n" + tab + "\t"
        lvls_elem.tail = "\n" + tab
        ge.text = "\n" + tab + "\t"
    else:
        xform.tail = "\n" + tab

    return ge


class Scene:
    """Read/modify/write model for a Bannerlord scene.xscene file."""

    def __init__(self, tree: ET.ElementTree, path: str | None = None) -> None:
        self._tree = tree
        self._path = path
        self._root = tree.getroot()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str) -> "Scene":
        """Parse a scene.xscene file from *path*."""
        tree = ET.parse(path)
        return cls(tree, path)

    # ------------------------------------------------------------------
    # Basic accessors
    # ------------------------------------------------------------------

    @property
    def scene_name(self) -> str:
        return self._root.get("name", "")

    @property
    def levels(self) -> list[str]:
        levels_elem = self._root.find("levels")
        if levels_elem is None:
            return []
        return [lv.get("name", "") for lv in levels_elem if lv.tag == "level"]

    # ------------------------------------------------------------------
    # Entity access
    # ------------------------------------------------------------------

    @property
    def _entities_elem(self) -> ET.Element:
        ent = self._root.find("entities")
        if ent is None:
            raise RuntimeError("<entities> element not found in scene")
        return ent

    @property
    def entities(self) -> list[Entity]:
        """All top-level <game_entity> elements inside <entities>."""
        return [Entity(e) for e in self._entities_elem if e.tag == "game_entity"]

    def find_entities(
        self,
        prefab: str | None = None,
        tag: str | None = None,
        name_contains: str | None = None,
    ) -> list[Entity]:
        """Filter top-level entities by prefab, tag, and/or name substring."""
        results: list[Entity] = []
        for ent in self.entities:
            if prefab is not None and ent.prefab != prefab:
                continue
            if tag is not None and tag not in ent.tag_names:
                continue
            if name_contains is not None:
                pname = ent.prefab or ent.name or ""
                if name_contains not in pname:
                    continue
            results.append(ent)
        return results

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_entity(
        self,
        prefab: str,
        position: tuple[float, float, float],
        rotation_euler: tuple[float, float, float] = (0.0, 0.0, 0.0),
        scale: tuple[float, float, float] | None = None,
        levels: list[str] | None = None,
    ) -> Entity:
        """Append a new <game_entity> to <entities> and return its wrapper."""
        ent_elem = self._entities_elem
        children = list(ent_elem)

        # Indentation: <entities> children sit at depth 2 (two tabs).
        indent = 2

        new_elem = _make_entity_element(
            prefab, position, rotation_euler, scale, levels, indent=indent
        )

        if children:
            # The previously-last child's tail was '\n\t' (points at </entities>).
            # Now that a new entity follows it, update it to the normal
            # inter-child spacing '\n\t\t'.
            children[-1].tail = "\n\t\t"

        ent_elem.append(new_elem)

        # New last child's tail — leads to the </entities> closing tag (1 tab).
        new_elem.tail = "\n\t"

        return Entity(new_elem)

    def remove_entity(self, entity: Entity) -> None:
        """Remove *entity* from <entities>.

        Raises ValueError if the entity is not a direct child of <entities>.
        """
        ent_elem = self._entities_elem
        children = list(ent_elem)
        target = entity._element
        if target not in children:
            raise ValueError("Entity is not a direct child of <entities>")

        idx = children.index(target)
        ent_elem.remove(target)

        # If we removed the last child, fix the new last child's tail
        # so </entities> indentation is correct.
        remaining = list(ent_elem)
        if remaining and idx == len(children) - 1:
            # The previously second-to-last is now last; it should have the
            # same tail the removed element had.
            remaining[-1].tail = target.tail

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------

    def save(self, path: str | None = None) -> None:
        """Write the scene to *path* (or the original path if omitted)."""
        dest = path or self._path
        if dest is None:
            raise ValueError("No path specified")
        _write_tree(self._tree, dest, xml_declaration=True)


# ---------------------------------------------------------------------------
# Prefab file loader
# ---------------------------------------------------------------------------

def load_prefabs(path: str) -> list[Entity]:
    """Load entity wrappers from a <prefabs> root XML file.

    These files share the game_entity schema but have no XML declaration and
    use <prefabs> as the root instead of <scene>.
    """
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag != "prefabs":
        raise ValueError(f"Expected <prefabs> root, got <{root.tag}>")
    return [Entity(e) for e in root if e.tag == "game_entity"]
