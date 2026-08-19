import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "app" / "templates"

# Matches any double-quoted HTML attribute value, tolerating the newlines
# some of our multi-line form tags use between attributes.
DOUBLE_QUOTED_ATTR = re.compile(r'="([^"]*)"', re.DOTALL)


def _double_quoted_attrs_with_tojson():
    for path in sorted(TEMPLATES_DIR.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        for match in DOUBLE_QUOTED_ATTR.finditer(text):
            if "tojson" in match.group(1):
                yield path.relative_to(TEMPLATES_DIR.parent.parent), match.group(1)


def test_no_tojson_inside_double_quoted_html_attributes():
    """`|tojson` renders a value already wrapped in literal double quotes
    (that's the JSON string delimiter). Embedding it inside attr="..." makes
    the HTML parser treat that first quote as the end of the attribute,
    silently truncating it (e.g. a delete confirmation's onsubmit handler
    breaks and the browser submits the form with no warning at all).

    Use a single-quoted attribute instead: onsubmit='return confirm({{ value|tojson }});'
    or move the value into a <script> block, which has no such conflict.
    """
    offenders = list(_double_quoted_attrs_with_tojson())
    assert not offenders, "Double-quoted HTML attribute(s) contain |tojson, which breaks at render time:\n" + "\n".join(
        f"  {path}: {value!r}" for path, value in offenders
    )
