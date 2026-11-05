"""Rendering for templates written by project members (rubrics, prompts)."""
from __future__ import annotations

from typing import Any

from jinja2.sandbox import ImmutableSandboxedEnvironment

# Templates are tenant input: a plain Jinja environment lets them reach
# os.environ and run commands on the server.
_env = ImmutableSandboxedEnvironment(autoescape=False)


def render_template(template: str, context: dict[str, Any]) -> str:
    return _env.from_string(template).render(context)


def check_template(template: str) -> None:
    """Raise ``jinja2.TemplateSyntaxError`` when ``template`` cannot compile."""
    _env.parse(template)
