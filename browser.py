import socket
import ssl
import os

INHERITED_PROPERTIES = {
    "font-size": "16px",
    "font-style": "normal",
    "font-weight": "normal",
    "color": "black",
    "text-align": "left",
}

class URL:
    def __init__(self, url):
        self.fragment = None
        try:
            if url == "about:blank":
                self.scheme = "about"
                self.path = "blank"
                return

            if url.startswith("data:"):
                self.scheme, url = url.split(":", 1)
                if "#" in url:
                    url, self.fragment = url.rsplit("#", 1)
                self.path = url
                return

            if "#" in url:
                url, self.fragment = url.rsplit("#", 1)

            self.scheme, url = url.split('://', 1)
            if self.scheme not in ('http', 'https', 'file'):
                raise ValueError(f"Unsupported scheme: {self.scheme}")

            if self.scheme == 'file':
                self.path = url
                self.host = None
                self.port = None
                return

            if self.scheme == 'http':
                self.port = 80
            elif self.scheme == 'https':
                self.port = 443
            
            if '/' in url:
                self.host, url = url.split('/', 1)
                self.path = '/' + url
            else:
                self.host = url
                self.path = '/'

            if ':' in self.host:
                self.host, port = self.host.split(':', 1)
                self.port = int(port)

            print(f"protocol is: {self.scheme}, host is: {self.host}, path is: {self.path}")
        except Exception:
            self.scheme = "about"
            self.path = "blank"

    def request(self, payload=None):
        method = "POST" if payload else "GET"
        if self.scheme == "file":
            path = self.path
            if os.path.isfile(path):
                with open(path, "r", encoding="utf8") as f:
                    return f.read()
            elif os.path.isdir(path):
                return self.generate_directory_listing(path)
            else:
                return f"<html><body><h1>Error</h1><p>Path not found: {path}</p></body></html>"
        
        if self.scheme == "data":
            return self.path.split(",", 1)[1]

        if self.scheme == "about":
            return ""

        s = socket.socket()

        s.connect((self.host, self.port))

        if self.scheme == 'https':
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)
        
        request = f"{method} {self.path} HTTP/1.0\r\n"
        request += f"HOST: {self.host}\r\n"
        if payload:
            length = len(payload.encode("utf8"))
            request += f"Content-Length: {length}\r\n"
        request += "Connection: close\r\n"
        request += "User-Agent: Nabin\r\n"
        request += "\r\n"
        if payload:
            request += payload
        s.send(request.encode("utf8"))

        response = s.makefile("r", encoding="utf8", newline="\r\n")

        statusline = response.readline()
        version, status, explanation = statusline.split(" ", 2)

        print(f"version: {version}, status: {status} and explanation: {explanation}")

        response_headers = {}

        while True:
            line = response.readline()
            if line == "\r\n":
                break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers

        content = response.read()
        s.close()

        return content

    def generate_directory_listing(self, path):
        path = os.path.abspath(path)
        
        html = f"<html><head><title>Directory: {path}</title></head><body>"
        html += f"<h1>Index of {path}</h1>"
        html += "<hr>"
        html += "<ul>"
        
        # Add parent directory link (if not at root)
        parent = os.path.dirname(path)
        if parent and parent != path:
            html += f'<li><a href="file://{parent}">..</a> (Parent Directory)</li>'
        
        try:
            entries = sorted(os.listdir(path))
            for entry in entries:
                full_path = os.path.join(path, entry)
                if os.path.isdir(full_path):
                    html += f'<li><a href="file://{full_path}">{entry}/</a></li>'
                else:
                    html += f'<li><a href="file://{full_path}">{entry}</a></li>'
        except PermissionError:
            html += "<li>Permission denied</li>"
        
        html += "</ul>"
        html += "<hr>"
        html += "</body></html>"
        
        return html
    
    def resolve(self, url):
        # Handle fragment-only URLs
        if url.startswith("#"):
            new_url = URL(str(self))
            new_url.fragment = url[1:]
            return new_url
        
        if "://" in url: return URL(url)
        
        if self.scheme == "file":
            if url.startswith("/"):
                return URL(f"file://{url}")
            else:
                if os.path.isfile(self.path):
                    base_dir = os.path.dirname(self.path)
                else:
                    base_dir = self.path
                new_path = os.path.normpath(os.path.join(base_dir, url))
                return URL(f"file://{new_path}")
        
        if not url.startswith("/"):
            dir, _ = self.path.rsplit("/", 1)
            while url.startswith("../"):
                _, url = url.split("/", 1)
                if "/" in dir:
                    dir, _ = dir.rsplit("/", 1)
            url = dir + "/" + url
        
        # Include port in resolved URL
        port_part = ""
        if self.scheme == "https" and self.port != 443:
            port_part = ":" + str(self.port)
        elif self.scheme == "http" and self.port != 80:
            port_part = ":" + str(self.port)
        return URL(self.scheme + "://" + self.host + port_part + url)
    
    def __str__(self):
        fragment_part = "#" + self.fragment if self.fragment else ""
        if self.scheme == "file":
            return f"file://{self.path}{fragment_part}"
        if self.scheme == "data":
            return f"data:{self.path}{fragment_part}"
        if self.scheme == "about":
            return f"about:{self.path}{fragment_part}"
        
        port_part = ":" + str(self.port)
        if self.scheme == "https" and self.port == 443:
            port_part = ""
        if self.scheme == "http" and self.port == 80:
            port_part = ""
        return self.scheme + "://" + self.host + port_part + self.path + fragment_part
    
# functions
def style(node, rules):
    node.style = {}
    for property, default_value in INHERITED_PROPERTIES.items():
        if node.parent:
            node.style[property] = node.parent.style[property]
        else:
            node.style[property] = default_value

    for selector, body in rules:
        if not selector.matches(node): continue
        for property, value in body.items():
            node.style[property] = value

    if isinstance(node, Element) and "style" in node.attributes:
        pairs = CSSParser(node.attributes["style"]).body()
        for property, value in pairs.items():
            node.style[property] = value

    if node.style["font-size"].endswith("%"):
        if node.parent:
            parent_font_size = node.parent.style["font-size"]
        else:
            parent_font_size = INHERITED_PROPERTIES["font-size"]
        node_pct =float(node.style["font-size"][:-1]) / 100
        parent_px = float(parent_font_size[:-2])
        node.style["font-size"] = str(node_pct * parent_px) + "px"

    for child in node.children:
            style(child, rules)

def cascade_priority(rule):
    selector, body = rule
    return selector.priority

    
class CSSParser:
    def __init__(self, s):
        self.s = s
        self.i = 0

    def whitespace(self):
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def word(self):
        start = self.i
        while self.i < len(self.s):
            if self.s[self.i].isalnum() or self.s[self.i] in "#-.%":
                self.i += 1
            else:
                break
        if not (self.i > start):
            raise Exception("Parsing error")
        return self.s[start:self.i]
    
    def literal(self, literal):
        if not (self.i < len(self.s) and self.s[self.i] == literal):
            raise Exception("Parsing error")
        self.i += 1

    def pair(self):
        prop = self.word()
        self.whitespace()
        self.literal(":")
        self.whitespace()
        val = self.word()
        return prop.casefold(), val
    
    def body(self):
        pairs = {}
        while self.i < len(self.s) and self.s[self.i] != "}":
            try:
                prop, val = self.pair()
                pairs[prop] = val
                self.whitespace()
                self.literal(";")
                self.whitespace()
            except Exception:
                why = self.ignore_until([";", "}"])
                if why == ";":
                    self.literal(";")
                    self.whitespace()
                else:
                    break
        return pairs
    
    def ignore_until(self, chars):
        while self.i < len(self.s):
            if self.s[self.i] in chars:
                return self.s[self.i]
            else:
                self.i += 1
        return None
    
    def selector(self):
        out = TagSelector(self.word().casefold())
        self.whitespace()
        while self.i < len(self.s) and self.s[self.i] != "{":
            tag = self.word()
            descendant = TagSelector(tag.casefold())
            out = DescendantSelector(out, descendant)
            self.whitespace()
        return out
    
    def parse(self):
        rules = []
        while self.i < len(self.s):
            try:
                self.whitespace()
                selector = self.selector()
                self.literal("{")
                self.whitespace()
                body = self.body()
                self.literal("}")
                rules.append((selector, body))
            except Exception:
                why = self.ignore_until(["}"])
                if why == "}":
                    self.literal("}")
                    self.whitespace()
                else:
                    break
        return rules
    
class TagSelector:
    def __init__(self, tag):
        self.tag = tag
        self.priority = 1

    def matches(self, node):
        return isinstance(node, Element) and self.tag == node.tag
    
class DescendantSelector:
    def __init__(self, ancestor, descendant):
        self.ancestor = ancestor
        self.descendant = descendant
        self.priority = ancestor.priority + descendant.priority

    def matches(self, node):
        if not self.descendant.matches(node): return False
        while node.parent:
            if self.ancestor.matches(node.parent): return True
            node = node.parent
        return False
    
class HTMLParser:
    SELF_CLOSING_TAGS = [
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    ]

    HEAD_TAGS = [
        "base", "basefont", "bgsound", "noscript",
        "link", "meta", "title", "style", "script",
    ]

    def __init__(self, body):
        self.body = body
        self.unfinished = []

    def parse(self):
        text = ""
        in_tag = False
        for c in self.body:
            if c == "<":
                in_tag = True
                if text: self.add_text(text)
                text = ""
            elif c == ">":
                in_tag = False
                self.add_tag(text)
                text = ""
            else:
                text += c
        if not in_tag and text:
            self.add_text(text)
        return self.finish()
    
    def add_text(self, text):
        if text.isspace(): return

        self.implicit_tags(None)
        parent = self.unfinished[-1]
        node = Text(text, parent)
        parent.children.append(node)

    def add_tag(self, tag):
        tag, attributes = self.get_attributes(tag)

        if tag.startswith('!'): return
        self.implicit_tags(tag)

        if tag.startswith('/'):
            if len(self.unfinished) == 1: return
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        elif tag in self.SELF_CLOSING_TAGS:
            parent = self.unfinished[-1]
            node = Element(tag, attributes, parent)
            parent.children.append(node)
        else:
            parent = self.unfinished[-1] if self.unfinished else None
            node = Element(tag, attributes, parent)
            self.unfinished.append(node)

    def get_attributes(self, text):
        parts = text.split()
        tag = parts[0].casefold()
        attributes = {}
        for attrpair in parts[1:]:
            if "=" in attrpair:
                key, value = attrpair.split("=", 1)
                if len(value) > 2 and value[0] in ["'", "\""]:
                    value = value[1:-1]
                attributes[key.casefold()] = value
            else:
                attributes[attrpair.casefold()] = ""
        return tag, attributes

    def implicit_tags(self, tag):
        while True:
            open_tags = [node.tag for node in self.unfinished]
            if open_tags == [] and tag != "html":
                self.add_tag("html")
            elif open_tags == ["html"] and tag not in ["head", "body", "/html"]:
                if tag in self.HEAD_TAGS:
                    self.add_tag("head")
                else:
                    self.add_tag("body")
            elif open_tags == ["html", "head"] and tag not in ["/head"] + self.HEAD_TAGS:
                self.add_tag("/head")
            else:
                break

    def finish(self):
        if not self.unfinished:
            self.implicit_tags(None)

        while len(self.unfinished) > 1:
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        return self.unfinished.pop()
    
def print_tree(node, indent=0):
    print(" " * indent, node)
    for child in node.children:
        print_tree(child, indent + 2)

def load(url):
    body = url.request()
    HTMLParser(body)

class Text:
    def __init__(self, text, parent):
        self.text = text
        self.children = []
        self.parent = parent
        self.is_focused = False

    def __repr__(self):
        return repr(self.text)

class Element:
    def __init__(self, tag, attributes, parent):
        self.tag = tag
        self.attributes = attributes
        self.children = []
        self.parent = parent
        self.is_focused = False

    def __repr__(self):
        return "<" + self.tag + ">"

if __name__ == "__main__":
    import sys
    # load(URL(sys.argv[1]))
    body = URL(sys.argv[1]).request()
    nodes = HTMLParser(body).parse()
    print_tree(nodes)