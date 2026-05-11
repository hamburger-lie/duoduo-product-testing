from __future__ import annotations

import json
from pathlib import Path

import jinja2

from app.ai.exceptions import AIPromptNotFound, AIPromptRenderFailed

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _tojson_filter(
    value: object,
    indent: int | None = None,
    ensure_ascii: bool = True,
) -> str:
    return json.dumps(value, indent=indent, ensure_ascii=ensure_ascii)


_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=False,
    keep_trailing_newline=True,
    undefined=jinja2.StrictUndefined,
)
_env.filters["tojson"] = _tojson_filter


def render_prompt(name: str, **context: object) -> tuple[str, str, str]:
    """Render a prompt template by name.

    Returns ``(rendered_text, prompt_name, versioned_name)`` where
    versioned_name follows the ``{name}@v{major}.{minor}.{patch}`` format.

    Raises:
        AIPromptNotFound: template file does not exist.
        AIPromptRenderFailed: Jinja2 rendering error.
    """

    filename = f"{name}.j2"
    try:
        template = _env.get_template(filename)
    except jinja2.TemplateNotFound as exc:
        raise AIPromptNotFound(f"Prompt template not found: {name}") from exc

    try:
        rendered = template.render(**context)
    except jinja2.TemplateError as exc:
        raise AIPromptRenderFailed(f"Failed to render prompt '{name}': {exc}") from exc

    versioned = f"{name}@v0.1.0"
    return rendered, name, versioned
