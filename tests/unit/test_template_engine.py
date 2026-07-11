import pytest

from app.services.template_engine import TemplateRenderError, render_template


def test_render_template_substitutes_single_variable():
    result = render_template("Hello {{name}}", {"name": "Ada"})
    assert result == "Hello Ada"


def test_render_template_substitutes_multiple_variables():
    result = render_template(
        "Hello {{name}}, your order {{order_id}} has shipped.",
        {"name": "Ada", "order_id": "ORD-1"},
    )
    assert result == "Hello Ada, your order ORD-1 has shipped."


def test_render_template_handles_whitespace_inside_braces():
    result = render_template("Hi {{ name }}", {"name": "Ada"})
    assert result == "Hi Ada"


def test_render_template_no_placeholders_returns_original():
    assert render_template("Plain text", {}) == "Plain text"


def test_render_template_missing_variable_raises():
    with pytest.raises(TemplateRenderError, match="order_id"):
        render_template("Order {{order_id}}", {})


def test_render_template_coerces_non_string_values():
    result = render_template("Count: {{count}}", {"count": 5})
    assert result == "Count: 5"
