from bs4 import BeautifulSoup
from quill_delta import Delta 

BLOCK_TAGS = {"p", "h1", "h2", "ul", "ol"}

def html_to_delta(html):
    stripHTML = html.removeprefix("```html\n").removesuffix("```")
    soup = BeautifulSoup(stripHTML, "html.parser")
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

