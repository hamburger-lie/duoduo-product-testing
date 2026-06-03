from __future__ import annotations

from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent / "product_image_extract.j2"


def render_prompt(*, target_fields: list[str], locale: str) -> str:
    """Render the image extraction prompt template.

    Used by real vision backends; MockVisionClient bypasses this.
    """

    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_PATH.parent)), autoescape=False)
    template = env.get_template(TEMPLATE_PATH.name)
    return template.render(target_fields=target_fields, locale=locale)
