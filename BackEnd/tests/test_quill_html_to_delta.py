"""extract_html(): reducing an LLM reply to the HTML content it was asked for."""

from quill_html_to_delta import extract_html, html_to_delta

BODY = "<h1>Title</h1>\n\n<p>I shipped it.</p>"


def test_preamble_and_fence_are_dropped():
    raw = f"Here's a Reddit post draft ready for your series.\n\n```html\n{BODY}\n```"
    assert extract_html(raw) == BODY


def test_trailing_chatter_after_fence_is_dropped():
    raw = f"```html\n{BODY}\n```\n\nWant me to make it shorter?"
    assert extract_html(raw) == BODY


def test_unclosed_fence_keeps_its_content():
    raw = f"Sure!\n```html\n{BODY}"
    assert extract_html(raw) == BODY


def test_preamble_without_fence_is_dropped():
    raw = f"Here's the post:\n\n{BODY}\n\nLet me know what you think."
    assert extract_html(raw) == BODY


def test_clean_html_is_unchanged():
    assert extract_html(BODY) == BODY


def test_plain_text_is_unchanged():
    assert extract_html("Just some text, no tags.") == "Just some text, no tags."


def test_empty_input():
    assert extract_html(None) == ""
    assert extract_html("") == ""


def test_delta_has_no_preamble_or_fence_text():
    raw = f"Here's a draft.\n\n```html\n{BODY}\n```"
    text = "".join(op["insert"] for op in html_to_delta(raw) if isinstance(op.get("insert"), str))
    assert "Here's a draft" not in text
    assert "```" not in text
    assert text.startswith("Title")
