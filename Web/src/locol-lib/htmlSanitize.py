# htmlSanitize.py - allowlist sanitizer for LLM-generated HTML shown in the UI
"""Make LLM-generated HTML safe to hand to st.markdown(..., unsafe_allow_html=True).

BackEnd's default system prompt (BackEnd/src/llm.py) *asks* the model to emit only
"p, b,i,em,u,a,ul,ol,br,h1,h2" elements, and that output is stored verbatim as
query_history.raw_output, then surfaced to us as an idea's `generated_content`.
A prompt is a request, not a guarantee - and prompt templates are user-editable in
Settings, so the system prompt itself can be replaced. This module enforces that
same tag contract on the display side, so rendering the content formatted doesn't
mean trusting the model with the browser.

Everything here is stdlib (html.parser + html.escape); no sanitizer dependency.
"""
import re
from html import escape
from html.parser import HTMLParser

# The tag set BackEnd/src/llm.py asks the LLM for, plus `li` (implied by ul/ol) and
# `strong` (BackEnd/src/quill_html_to_delta.py already treats it as a bold synonym).
ALLOWED_TAGS = {
    "p", "b", "i", "em", "strong", "u", "a", "ul", "ol", "li", "br", "h1", "h2",
}

# Never emit a closing tag for these.
VOID_TAGS = {"br"}

# Tags whose *contents* are dropped along with the tag, rather than kept as text.
DROP_CONTENT_TAGS = {"script", "style"}

# `href` on <a> is the one attribute worth keeping, and the one place a scheme
# check still matters once tags are allowlisted (javascript: URLs).
ALLOWED_URL_SCHEMES = ("http://", "https://", "mailto:")

# Mirrors extract_html() in BackEnd/src/quill_html_to_delta.py - Web is a separate
# package and can't import it. Keep the two in step.
_FENCE_RE = re.compile(r"```[ \t]*(?:html)?[ \t]*\r?\n(.*?)(?:```|\Z)", re.DOTALL | re.IGNORECASE)
_BLOCK_OPEN_RE = re.compile(r"<(?:h1|h2|p|ul|ol)\b", re.IGNORECASE)
_BLOCK_CLOSE_RE = re.compile(r"</(?:h1|h2|p|ul|ol)\s*>", re.IGNORECASE)


def _extract_html(raw):
    """Drop a preamble, code fence and trailing chatter around LLM-generated HTML."""
    text = str(raw).strip()

    fenced = _FENCE_RE.search(text)
    if fenced and _BLOCK_OPEN_RE.search(fenced.group(1)):
        text = fenced.group(1).strip()

    first_open = _BLOCK_OPEN_RE.search(text)
    if first_open:
        closes = list(_BLOCK_CLOSE_RE.finditer(text))
        end = closes[-1].end() if closes and closes[-1].end() > first_open.start() else len(text)
        text = text[first_open.start():end]

    return text


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._out = []
        self._open = []          # stack of allowed tags awaiting a close
        self._suppress_depth = 0  # >0 while inside a script/style subtree

    # -- output helpers ----------------------------------------------------

    def _emit(self, text):
        if not self._suppress_depth:
            self._out.append(text)

    def _link_attrs(self, attrs):
        """Keep only href/title on <a>, and only if href has a safe scheme."""
        kept = []
        for name, value in attrs:
            if value is None:
                continue
            if name == "href":
                if value.strip().lower().startswith(ALLOWED_URL_SCHEMES):
                    kept.append(f'href="{escape(value.strip(), quote=True)}"')
            elif name == "title":
                kept.append(f'title="{escape(value, quote=True)}"')
        # Links open a new tab; rel guards the opener from the new window.
        kept.append('target="_blank" rel="noopener noreferrer"')
        return " " + " ".join(kept)

    # -- HTMLParser hooks --------------------------------------------------

    def handle_starttag(self, tag, attrs):
        if tag in DROP_CONTENT_TAGS:
            self._suppress_depth += 1
            return
        if self._suppress_depth:
            return
        if tag not in ALLOWED_TAGS:
            return  # drop the tag, keep whatever text it wraps
        if tag in VOID_TAGS:
            self._emit("<br>")
            return
        self._emit(f"<{tag}{self._link_attrs(attrs) if tag == 'a' else ''}>")
        self._open.append(tag)

    def handle_startendtag(self, tag, attrs):
        # <br/> and friends - self-closing, so nothing to push onto the stack.
        if not self._suppress_depth and tag in ALLOWED_TAGS:
            if tag in VOID_TAGS:
                self._emit("<br>")
            else:
                self._emit(f"<{tag}{self._link_attrs(attrs) if tag == 'a' else ''}></{tag}>")

    def handle_endtag(self, tag):
        if tag in DROP_CONTENT_TAGS:
            self._suppress_depth = max(0, self._suppress_depth - 1)
            return
        if self._suppress_depth:
            return
        if tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return
        if tag not in self._open:
            return  # stray close with no matching open - ignore it
        # Close anything the model left open inside `tag`, innermost first.
        while self._open:
            open_tag = self._open.pop()
            self._emit(f"</{open_tag}>")
            if open_tag == tag:
                break

    def handle_data(self, data):
        self._emit(escape(data))

    # -- result ------------------------------------------------------------

    def result(self):
        self.close()
        # Auto-close anything still open at EOF so unbalanced markup can't bleed
        # into the rest of the page.
        while self._open:
            self._out.append(f"</{self._open.pop()}>")
        return "".join(self._out)


def sanitize_generated_html(raw):
    """Return `raw` reduced to the allowlisted tag set, safe to render as HTML.

    Handles both shapes `generated_content` arrives in: HTML for LLM-generated
    items, and plain text for items last saved by hand in the Content Editor
    (BackEnd/src/rag_run.py stores delta_to_plain_text() as raw_output there).
    """
    if not raw:
        return ""

    # LLMs routinely wrap their HTML in a preamble and a ```html fence. BackEnd now
    # strips both before storing, but rows written earlier still carry them - and a
    # surviving fence renders as a markdown code block, showing the HTML as source.
    stripped = _extract_html(raw)

    parser = _Sanitizer()
    parser.feed(stripped)
    cleaned = parser.result()

    # Plain-text content has no tags to carry its line breaks, and Markdown
    # collapses bare newlines - keep hand-edited drafts readable.
    if "<" not in cleaned:
        cleaned = cleaned.replace("\n", "<br>")

    return cleaned
