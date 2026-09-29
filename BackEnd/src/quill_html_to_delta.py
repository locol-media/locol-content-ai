import re
from bs4 import BeautifulSoup
from quill_delta import Delta

BLOCK_TAGS = {"p", "h1", "h2", "ul", "ol"}

# A markdown code fence anywhere in the reply, optionally tagged html. An unclosed
# fence (reply cut off mid-block) runs to the end of the text.
_FENCE_RE = re.compile(r"```[ \t]*(?:html)?[ \t]*\r?\n(.*?)(?:```|\Z)", re.DOTALL | re.IGNORECASE)
_BLOCK_OPEN_RE = re.compile(r"<(?:h1|h2|p|ul|ol)\b", re.IGNORECASE)
_BLOCK_CLOSE_RE = re.compile(r"</(?:h1|h2|p|ul|ol)\s*>", re.IGNORECASE)


def extract_html(raw):
    """Reduce an LLM reply to the HTML content it was asked for.

    Models routinely wrap their HTML in chatter - "Here's a Reddit post draft..." -
    and a ```html fence. Left in, the fence survives as a markdown code block on the
    Web idea card (raw tags shown as source) and the preamble lands in the editor.
    Only replies that actually contain block tags are trimmed; plain text passes
    through untouched.
    """
    if not raw:
        return ""
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


def html_to_delta(html):
    soup = BeautifulSoup(extract_html(html), "html.parser")
    delta = Delta()

    def is_blank_text(node):
        return node.name is None and str(node).strip() == "" and "\n" in str(node)

    def is_empty_block(node):
        return node.name in BLOCK_TAGS and node.get_text(strip=True) == ""

    def process_children(children, attributes):
        prev_was_block = False
        for child in children:
            if is_blank_text(child) or is_empty_block(child):
                continue  # ignore pretty-printing whitespace and empty blocks alike
            is_block = child.name in BLOCK_TAGS
            if is_block and prev_was_block:
                delta.insert("\n")  # exactly one blank line between consecutive block elements
            parse_element(child, attributes.copy())
            prev_was_block = is_block

    def parse_element(element, attributes=None):
        attributes = attributes or {}

        if element.name is None:  # Text node
            text = str(element)
            if text.strip() == "" and "\n" in text:
                return  # skip HTML pretty-printing whitespace between block-level tags
            delta.insert(element.string, **attributes)

        elif element.name in ("html", "header", "body"):
            process_children(element.contents, attributes)

        elif element.name == "li":
            for child in element.contents:
                parse_element(child, attributes.copy())
            delta.insert("\n")  # Newline to separate this list item from the next

        elif element.name == "b" or element.name == "strong" or element.name == "title":
            attributes["bold"] = True
            for child in element.contents:
                parse_element(child, attributes.copy())
        
        elif element.name == "i" or element.name == "em":
            attributes["italic"] = True
            for child in element.contents:
                parse_element(child, attributes.copy())

        elif element.name == "u":
            attributes["underline"] = True
            for child in element.contents:
                parse_element(child, attributes.copy())

        elif element.name == "a":
            attributes["link"] = element.get("href", "")
            for child in element.contents:
                parse_element(child, attributes.copy())

        elif element.name in ["ul", "ol"]:  # Lists
            list_type = "ordered" if element.name == "ol" else "bullet"
            for li in element.find_all("li", recursive=False):
                parse_element(li, {"list": list_type})

        elif element.name == "p":
            for child in element.contents:
                parse_element(child, attributes.copy())
            delta.insert("\n")  # Newline for paragraph separation

        elif element.name == "br":
            delta.insert("\n")  # Line break

        elif element.name == "h1":
            for child in element.contents:
                parse_element(child, {"header": 1})
            delta.insert("\n")

        elif element.name == "h2":
            for child in element.contents:
                parse_element(child, {"header": 2})
            delta.insert("\n")

    process_children(soup.contents, {})

    return delta.ops

