import re

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class TemplateRenderError(Exception):
    pass


def render_template(text: str, variables: dict) -> str:
    """Substitute {{var}} placeholders. Raises if a placeholder has no matching variable."""

    def replace(match: re.Match) -> str:
        key = match.group(1)
        if key not in variables:
            raise TemplateRenderError(f"Missing template variable: '{key}'")
        return str(variables[key])

    return _PLACEHOLDER_RE.sub(replace, text)
