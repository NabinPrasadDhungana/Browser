import tkinter
import dukpy
from browser import URL, HTMLParser, CSSParser, style, cascade_priority
import tkinter.font
from browser import Text, Element
import urllib.parse

WIDTH = 800
HEIGHT = 600 

HSTEP = 13
VSTEP = 18
SCROLL_STEP = 35
INPUT_WIDTH_PX = 200
DEFAULT_STYLE_SHEET = CSSParser(open("browser.css").read()).parse()
RUNTIME_JS = open("runtime.js").read()
EVENT_DISPATCH_JS = "new Node(dukpy.handle).dispatchEvent(dukpy.type)"

def tree_to_list(tree, list):
    list.append(tree)
    for child in tree.children:
        tree_to_list(child, list)
    return list

def parse_font_size(font_size_str):
    """Parse font-size string and return size in pixels."""
    import re
    match = re.match(r'^([\d.]+)(px|rem|em|pt)?$', font_size_str)
    if match:
        value = float(match.group(1))
        unit = match.group(2) or 'px'
        if unit == 'px':
            return int(value * 0.75)
        elif unit == 'rem' or unit == 'em':
            return int(value * 16 * 0.75)  # 1rem = 16px default
        elif unit == 'pt':
            return int(value)  # pt is roughly equivalent to pixels for fonts
    return 12  # fallback default size

def parse_font_weight(weight_str):
    """Convert CSS font-weight to tkinter weight (normal or bold)."""
    if weight_str in ("bold", "bolder", "900", "800", "700", "600"):
        return "bold"
    return "normal"

class JSContext:
    def __init__(self, tab):
        self.tab = tab
        self.interp = dukpy.JSInterpreter()
        self.node_to_handle = {}
        self.handle_to_node = {}
        self.interp.export_function("log", print)
        self.interp.export_function("querySelectorAll", self.querySelectorAll)
        self.interp.export_function("getAttribute", self.getAttribute)
        self.interp.export_function("innerHTML_set", self.innerHTML_set)
        self.interp.evaljs(RUNTIME_JS)

    def run(self,script, code):
        try:
            return self.interp.evaljs(code)
        except dukpy.JSRuntimeError as e:
            print("Script", script, "crashed", e)

    def XMLHttpRequest_send(self, method, url, body):
        full_url = self.tab.url.resolve(url)
        headers, out = full_url.request(self.tab.url, body)
        if full_url.origin() != self.tab.url.origin():
            raise Exception("Cross-origin XHR request not allowed")
        return out

    def querySelectorAll(self, selector_text):
        selector = CSSParser(selector_text).selector()
        nodes = [node for node
                in tree_to_list(self.tab.nodes, [])
                if selector.matches(node)]
        return [self.get_handle(node) for node in nodes]
    
    def get_handle(self, elt):
        if elt not in self.node_to_handle:
            handle = len(self.node_to_handle)
            self.node_to_handle[elt] = handle
            self.handle_to_node[handle] = elt
        else:
            handle = self.node_to_handle[elt]
        return handle
    
    def getAttribute(self, handle, attr):
        elt = self.handle_to_node[handle]
        attr_value = elt.attributes.get(attr, None)
        return attr_value if attr_value is not None else None
    
    def dispatch_event(self, type, elt):
        handle = self.node_to_handle.get(elt, -1)

        do_default = self.interp.evaljs(EVENT_DISPATCH_JS, type=type, handle=handle)
        return do_default

    def innerHTML_set(self, handle, s):
        doc = HTMLParser("<html><body>" + s + "</body></html>").parse()
        new_nodes = doc.children[0].children
        elt = self.handle_to_node[handle]
        elt.children = new_nodes
        for child in elt.children:
            child.parent = elt
        self.tab.render()

class Rect:
    def __init__(self, left, top, right, bottom):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom

    def contains_point(self, x, y):
        return x>=self.left and x <self.right and y>=self.top and y<self.bottom

class Chrome:
    def __init__(self, browser):
        self.width = WIDTH
        self.browser = browser
        self.font = get_font("normal", "roman", 20)
        self.font_height = self.font.metrics("linespace")
        self.padding = 5
        self.tabbar_top = 0
        self.tabbar_bottom = self.font_height + 2*self.padding
        plus_width = self.font.measure("+") + 2*self.padding
        self.newtab_rect = Rect(
            self.padding, 
            self.padding,
            self.padding + plus_width,
            self.padding + self.font_height
        )
        self.bottom = self.tabbar_bottom
        self.urlbar_top = self.tabbar_bottom
        self.urlbar_bottom = self.urlbar_top + self.font_height + 2*self.padding
        self.bottom = self.urlbar_bottom
        back_width = self.font.measure("<") + 2*self.padding
        self.back_rect = Rect(
            self.padding,
            self.urlbar_top + self.padding,
            self.padding + back_width,
            self.urlbar_bottom - self.padding)

        forward_width = self.font.measure(">") + 2*self.padding
        self.forward_rect = Rect(
            self.back_rect.right + self.padding,
            self.urlbar_top + self.padding,
            self.back_rect.right + self.padding + forward_width,
            self.urlbar_bottom - self.padding)

        self.address_rect = Rect(
            self.forward_rect.right + self.padding,
            self.urlbar_top + self.padding,
            WIDTH - self.padding,
            self.urlbar_bottom - self.padding)
        self.focus = None
        self.address_bar = ""
        self.cursor = 0
        self.selection_start = None
        self.selection_end = None

    def resize(self, width):
        self.address_rect.right = width - self.padding
        self.width = width

    def blur(self):
        self.focus = None

    def key_press(self, char):
        if self.focus == "address bar":
            self.delete_selection()
            self.address_bar = self.address_bar[:self.cursor] + char + self.address_bar[self.cursor:]
            self.cursor += 1
            return True
        return False

    def backspace(self):
        if self.focus == "address bar":
            if self.delete_selection():
                return True
            if self.cursor > 0:
                self.address_bar = self.address_bar[:self.cursor-1] + self.address_bar[self.cursor:]
                self.cursor -= 1
                return True
        return False

    def arrow_left(self, e):
        if self.focus == "address bar":
            if self.cursor > 0:
                self.cursor -= 1
                if e.state & 0x0001: # Shift key
                    if self.selection_start is None:
                        self.selection_start = self.cursor + 1
                    self.selection_end = self.cursor
                else:
                    self.selection_start = None
                    self.selection_end = None
                return True
        return False

    def arrow_right(self, e):
        if self.focus == "address bar":
            if self.cursor < len(self.address_bar):
                self.cursor += 1
                if e.state & 0x0001: # Shift key
                    if self.selection_start is None:
                        self.selection_start = self.cursor - 1
                    self.selection_end = self.cursor
                else:
                    self.selection_start = None
                    self.selection_end = None
                return True
        return False
    
    def delete_selection(self):
        if self.selection_start is not None:
            start = min(self.selection_start, self.selection_end)
            end = max(self.selection_start, self.selection_end)
            self.address_bar = self.address_bar[:start] + self.address_bar[end:]
            self.cursor = start
            self.selection_start = None
            self.selection_end = None
            return True
        return False

    def copy(self):
        if self.selection_start is not None:
            start = min(self.selection_start, self.selection_end)
            end = max(self.selection_start, self.selection_end)
            self.browser.window.clipboard_clear()
            self.browser.window.clipboard_append(self.address_bar[start:end])

    def paste(self):
        try:
            text = self.browser.window.clipboard_get()
        except:
            return
        self.delete_selection()
        self.address_bar = self.address_bar[:self.cursor] + text + self.address_bar[self.cursor:]
        self.cursor += len(text)

    def cut(self):
        self.copy()
        self.delete_selection()

    def is_url(self, text):
        if text.startswith("http://") or text.startswith("https://"):
            return True
        if "://" in text or text.startswith("data:"):
            return True
        if "." in text and " " not in text:
            return True
        return False

    def enter(self):
        if self.focus == "address bar":
            text = self.address_bar.strip()
            if self.is_url(text):
                if not ("://" in text or text.startswith("data:")):
                    text = "https://" + text
                self.browser.active_tab.load(URL(text))
            else:
                query = urllib.parse.quote_plus(text)
                search_url = "https://www.google.com/search?q=" + query
                self.browser.active_tab.load(URL(search_url))
            self.focus = None

    def tab_rect(self, i):
        tabs_start = self.newtab_rect.right + self.padding
        tab_width = self.font.measure("Tab X") + 2*self.padding
        return Rect(
            tabs_start + tab_width * i,
            self.tabbar_top,
            tabs_start + tab_width * (i+1),
            self.tabbar_bottom
        )
    
    def click(self, x, y):
        was_focused = self.focus == "address bar"
        self.focus = None
        if self.newtab_rect.contains_point(x, y):
            self.browser.new_tab(URL("about:blank"))
        elif self.back_rect.contains_point(x, y):
            self.browser.active_tab.go_back()
        elif self.forward_rect.contains_point(x, y):
            self.browser.active_tab.go_forward()
        elif self.address_rect.contains_point(x, y):
            self.focus = "address bar"
            if not was_focused:
                self.address_bar = str(self.browser.active_tab.url)
            
            self.cursor = len(self.address_bar)
            for i in range(len(self.address_bar)):
                w = self.font.measure(self.address_bar[:i+1])
                if self.address_rect.left + self.padding + w > x:
                    self.cursor = i
                    break
            self.selection_start = None
            self.selection_end = None
        else:
            for i, tab in enumerate(self.browser.tabs):
                if self.tab_rect(i).contains_point(x, y):
                    self.browser.active_tab = tab
                    break
    
    def paint(self):
        cmds = []
        
        # Draw the URL bar background FIRST (only covers URL bar, not tabs)
        cmds.append(DrawRect(
            Rect(0, self.urlbar_top, WIDTH, self.bottom), "white"))
        cmds.append(DrawLine(
            0, self.bottom, self.width, self.bottom, "black", 1))
        
        # Now draw the new tab button
        cmds.append(DrawOutline(self.newtab_rect, "black", 1))
        cmds.append(DrawText(
            self.newtab_rect.left + self.padding,
            self.newtab_rect.top,
            "+",
            self.font,
            "black"
        ))
        
        # Draw tabs
        for i, tab in enumerate(self.browser.tabs):
            bounds = self.tab_rect(i)
            cmds.append(DrawLine(
                bounds.left, 0, bounds.left, bounds.bottom,
                "black", 1))
            cmds.append(DrawLine(
                bounds.right, 0, bounds.right, bounds.bottom,
                "black", 1))
            cmds.append(DrawText(
                bounds.left + self.padding, bounds.top + self.padding,
                "Tab {}".format(i), self.font, "black"))
            
            if tab == self.browser.active_tab:
                cmds.append(DrawLine(
                    0, bounds.bottom, bounds.left, bounds.bottom, "black", 1))
                cmds.append(DrawLine(
                    bounds.right, bounds.bottom, self.width, bounds.bottom, "black", 1))

        # Draw back button (gray if can't go back)
        back_color = "black" if len(self.browser.active_tab.history) > 1 else "gray"
        cmds.append(DrawOutline(self.back_rect, back_color, 1))
        cmds.append(DrawText(
            self.back_rect.left + self.padding,
            self.back_rect.top,
            "<", self.font, back_color))
        
        # Draw forward button (gray if can't go forward)
        forward_color = "black" if len(self.browser.active_tab.forward_history) > 0 else "gray"
        cmds.append(DrawOutline(self.forward_rect, forward_color, 1))
        cmds.append(DrawText(
            self.forward_rect.left + self.padding,
            self.forward_rect.top,
            ">", self.font, forward_color))
        
        cmds.append(DrawOutline(self.address_rect, "black", 1))
        
        if self.focus == "address bar":
            if self.selection_start is not None:
                start = min(self.selection_start, self.selection_end)
                end = max(self.selection_start, self.selection_end)
                start_x = self.address_rect.left + self.padding + self.font.measure(self.address_bar[:start])
                end_x = self.address_rect.left + self.padding + self.font.measure(self.address_bar[:end])
                cmds.append(DrawRect(Rect(start_x, self.address_rect.top + self.padding, end_x, self.address_rect.bottom - self.padding), "lightblue"))

            cmds.append(DrawText(
                self.address_rect.left + self.padding,
                self.address_rect.top,
                self.address_bar,
                self.font,
                "black"))
            w = self.font.measure(self.address_bar[:self.cursor])
            cmds.append(DrawLine(
                self.address_rect.left + self.padding + w,
                self.address_rect.top,
                self.address_rect.left + self.padding + w,
                self.address_rect.bottom,
                "red", 1))
        else:
            url = str(self.browser.active_tab.url)
            cmds.append(DrawText(
                self.address_rect.left + self.padding,
                self.address_rect.top,
                url,
                self.font,
                "black"))

        return cmds
    
class DrawLine:
    def __init__(self, x1, y1, x2, y2, color, thickness):
        self.rect = Rect(x1, y1, x2, y2)
        self.color = color
        self.thickness = thickness

    def execute(self, scroll, canvas):
        canvas.create_line(
            self.rect.left, self.rect.top - scroll,
            self.rect.right, self.rect.bottom - scroll,
            fill=self.color, width=self.thickness
        )
    
class DrawOutline:
    def __init__(self, rect, color, thickness):
        self.rect = rect
        self.color = color
        self.thickness = thickness

    def execute(self, scroll, canvas):
        canvas.create_rectangle(
            self.rect.left,
            self.rect.top - scroll,
            self.rect.right,
            self.rect.bottom - scroll,
            width = self.thickness,
            outline = self.color
        )

class Browser:
    def __init__(self):
        self.tabs = []
        self.active_tab = None
        self.window = tkinter.Tk()
        self.width = WIDTH
        self.height = HEIGHT
        self.canvas = tkinter.Canvas(self.window, width=WIDTH, height=HEIGHT, bg="white")
        self.canvas.pack(fill=tkinter.BOTH , expand=1)
        self.scroll = 0
        self.url = None
        self.window.bind('<Down>', self.handle_down)
        self.window.bind('<Up>', self.handle_up)
        self.window.bind('<MouseWheel>', self.handle_mousewheel)
        self.window.bind('<Button-4>', self.handle_mousewheel)
        self.window.bind('<Button-5>', self.handle_mousewheel)
        self.window.bind('<Configure>', self.handle_configure)
        self.window.bind("<Button-1>", self.handle_click)
        self.window.bind("<Key>", self.handle_key)
        self.window.bind("<Return>", self.handle_enter)
        self.window.bind("<BackSpace>", self.handle_backspace)
        self.window.bind("<Left>", self.handle_left)
        self.window.bind("<Right>", self.handle_right)
        self.window.bind("<Control-c>", self.handle_copy)
        self.window.bind("<Control-v>", self.handle_paste)
        self.window.bind("<Control-x>", self.handle_cut)

        self.chrome = Chrome(self)

    def handle_enter(self, e):
        if self.chrome.focus == "address bar":
            self.chrome.enter()
        elif self.focus == "content":
            self.active_tab.enter()
        self.draw()

    def handle_backspace(self, e):
        if self.chrome.focus == "address bar":
            self.chrome.backspace()
        elif self.focus == "content":
            self.active_tab.backspace()
        self.draw()

    def handle_left(self, e):
        if self.chrome.focus == "address bar":
            self.chrome.arrow_left(e)
        elif self.focus == "content":
            self.active_tab.arrow_left(e)
        self.draw()

    def handle_right(self, e):
        if self.chrome.focus == "address bar":
            self.chrome.arrow_right(e)
        elif self.focus == "content":
            self.active_tab.arrow_right(e)
        self.draw()

    def handle_copy(self, e):
        if self.chrome.focus == "address bar":
            self.chrome.copy()
        elif self.focus == "content":
            self.active_tab.copy()

    def handle_paste(self, e):
        if self.chrome.focus == "address bar":
            self.chrome.paste()
        elif self.focus == "content":
            self.active_tab.paste()
        self.draw()

    def handle_cut(self, e):
        if self.chrome.focus == "address bar":
            self.chrome.cut()
        elif self.focus == "content":
            self.active_tab.cut()
        self.draw()

    def handle_key(self, e):
        if len(e.char) == 0: return
        if not (0x20 <= ord(e.char) < 0x7f): return
        if self.chrome.key_press(e.char):
            self.draw()
        elif self.focus == "content":
            self.active_tab.key_press(e.char)
            self.draw()

    def handle_down(self, e):
        self.active_tab.scrolldown()
        self.draw()

    def handle_up(self, e):
        self.active_tab.scrollup()
        self.draw()

    def handle_mousewheel(self, e):
        self.active_tab.mousewheel(e)
        self.draw()

    def handle_click(self, e):
        if e.y < self.chrome.bottom:
            self.focus = None
            self.chrome.click(e.x, e.y)
        else:
            self.focus = "content"
            self.chrome.blur()
            tab_y = e.y - self.chrome.bottom
            self.active_tab.click(e.x, tab_y)
        self.draw()

    def handle_configure(self, e):
        self.width = e.width
        self.height = e.height
        self.chrome.resize(e.width)
        if self.active_tab:
            self.active_tab.resize(e.width, e.height - self.chrome.bottom)
        self.draw()

    def draw(self):
        self.canvas.delete("all")
        self.active_tab.draw(self.canvas, self.chrome.bottom)
        for cmd in self.chrome.paint():
            cmd.execute(0, self.canvas)
        
        # Set window title from page's <title> element
        title = self.active_tab.get_title()
        if title:
            self.window.title(title)
        else:
            self.window.title(str(self.active_tab.url))

    def new_tab(self, url):
        new_tab = Tab(HEIGHT - self.chrome.bottom)
        new_tab.load(url)
        self.active_tab = new_tab
        self.tabs.append(new_tab)
        self.draw()

class Tab:
    def __init__(self, tab_height):
        self.tab_height = tab_height
        self.history = []
        self.forward_history = []
        self.scroll = 0
        self.width = WIDTH
        self.focus = None

    def load(self, url, payload=None, from_navigation=False):
        if not from_navigation:
            self.forward_history.clear()
        headers, body = url.request(self.url, payload)
        self.history.append(url)
        self.url = url
        body = url.request(payload)
        self.nodes = HTMLParser(body).parse()
        rules = DEFAULT_STYLE_SHEET.copy()

        for node in tree_to_list(self.nodes, []):
            if isinstance(node, Element):
                # Handle external CSS files linked via <link>
                if node.tag == "link" and \
                   node.attributes.get("rel") == "stylesheet" and \
                   "href" in node.attributes:
                    try:
                        style_url = url.resolve(node.attributes["href"])
                        header, body = style_url.request(url)
                        rules.extend(CSSParser(body).parse())
                    except:
                        continue
                
                # Handle internal CSS blocks inside <style>
                elif node.tag == "style":
                    style_content = ""
                    for child in node.children:
                        if isinstance(child, Text):
                            style_content += child.text
                    if style_content:
                        rules.extend(CSSParser(style_content).parse())

        scripts = [node.attributes["src"] for node
                   in tree_to_list(self.nodes, [])
                   if isinstance(node, Element)
                   and node.tag == "script"
                   and "src" in node.attributes]
        
        self.js = JSContext(self)
        for script in scripts:
            script_url = url.resolve(script)
            try:
                header, body = script_url.request(url)
            except:
                continue
            self.js.run(script_url, body)
        
        self.rules = rules
        self.render()
        self.scroll_to_fragment()

    def scroll_to_fragment(self):
        if not self.url.fragment:
            return
        
        for node in tree_to_list(self.nodes, []):
            if isinstance(node, Element) and node.attributes.get("id") == self.url.fragment:
                # Find the layout object for this node
                for obj in tree_to_list(self.document, []):
                    if hasattr(obj, 'node') and obj.node == node:
                        self.scroll = obj.y
                        return
                break

    def render(self):
        style(self.nodes, sorted(self.rules, key=cascade_priority))
        self.document = DocumentLayout(self.nodes, self.width)
        self.document.layout()
        self.display_list = []
        paint_tree(self.document, self.display_list)

    def get_title(self):
        for node in tree_to_list(self.nodes, []):
            if isinstance(node, Element) and node.tag == "title":
                if node.children and isinstance(node.children[0], Text):
                    return node.children[0].text
        return None

    def go_back(self):
        if len(self.history) > 1:
            current = self.history.pop()
            self.forward_history.append(current)
            back = self.history.pop()
            self.load(back, from_navigation=True)

    def go_forward(self):
        if len(self.forward_history) > 0:
            forward = self.forward_history.pop()
            self.load(forward, from_navigation=True)

    def draw(self, canvas, offset):
        for cmd in self.display_list:
            if cmd.rect.top > self.scroll + self.tab_height: continue
            if cmd.rect.bottom < self.scroll: continue
            cmd.execute(self.scroll - offset, canvas)
        
        self.draw_scrollbar(canvas, offset)

    def draw_scrollbar(self, canvas, offset):
        if not self.display_list:
            return
            
        content_height = self.display_list[-1].bottom + VSTEP
        if content_height <= self.tab_height:
            return
            
        scrollbar_width = 12
        scrollbar_height = (self.tab_height / content_height) * self.tab_height
        scrollbar_y = (self.scroll / content_height) * self.tab_height + offset
        
        canvas.create_rectangle(
            self.width - scrollbar_width, scrollbar_y,
            self.width, scrollbar_y + scrollbar_height,
            fill="blue", outline=""
        )

    def scrolldown(self):
        max_y = max(self.document.height + 2*VSTEP - self.tab_height, 0)
        self.scroll = min(self.scroll + SCROLL_STEP, max_y)

    def scrollup(self):
        if not self.scroll <= 0:
            self.scroll -= SCROLL_STEP

    def mousewheel(self, e):
        if not self.display_list:
            return
        if e.num == 4 or e.delta > 0:
            if not self.scroll <=0:
                self.scroll -= SCROLL_STEP
        elif e.num == 5 or e.delta < 0:
            max_y = self.display_list[-1].bottom
            if self.scroll + self.tab_height < max_y:
                self.scroll += SCROLL_STEP

    def resize(self, width, height):
        self.width = width
        self.tab_height = height
        if hasattr(self, 'nodes'):
            self.document = DocumentLayout(self.nodes, self.width)
            self.document.layout()
            self.display_list = []
            paint_tree(self.document, self.display_list)

    def click(self, x, y):
        if self.focus:
            self.focus.is_focused = False
        y += self.scroll

        objs = [obj for obj in tree_to_list(self.document, []) if obj.x <= x < obj.x + obj.width and obj.y <= y < obj.y + obj.height]

        if not objs: return
        elt = objs[-1].node
        while elt:
            if isinstance(elt, Text):
                pass
            elif elt.tag == "a" and "href" in elt.attributes:
                self.js.dispatch_event("click", elt)
                href = elt.attributes["href"]
                if href.startswith("#"):
                    self.url.fragment = href[1:]
                    self.scroll_to_fragment()
                    return
                url = self.url.resolve(href)
                return self.load(url)
            elif elt.tag == "input":
                self.js.dispatch_event("click", elt)
                self.focus = elt
                elt.is_focused = True
                if not hasattr(elt, "cursor"):
                    elt.cursor = len(elt.attributes.get("value", ""))
                elt.selection_start = None
                elt.selection_end = None
                return self.render()
            elif elt.tag == "button":
                self.js.dispatch_event("click", elt)
                while elt:
                    if elt.tag == "form" and "action" in elt.attributes:
                        return self.submit_form(elt)
                    elt = elt.parent
            elt = elt.parent if elt.parent else None
        self.render()

    def key_press(self, char):
        if self.focus:
            if self.js.dispatch_event("keydown", self.focus): return
            self.delete_selection(self.focus)
            value = self.focus.attributes.get("value", "")
            cursor = getattr(self.focus, "cursor", len(value))
            self.focus.attributes["value"] = value[:cursor] + char + value[cursor:]
            self.focus.cursor = cursor + 1
            self.render()

    def backspace(self):
        if self.focus:
            if self.delete_selection(self.focus):
                self.render()
                return
            value = self.focus.attributes.get("value", "")
            cursor = getattr(self.focus, "cursor", len(value))
            if cursor > 0:
                self.focus.attributes["value"] = value[:cursor-1] + value[cursor:]
                self.focus.cursor = cursor - 1
                self.render()

    def arrow_left(self, e):
        if self.focus:
            value = self.focus.attributes.get("value", "")
            cursor = getattr(self.focus, "cursor", len(value))
            if cursor > 0:
                self.focus.cursor = cursor - 1
                if e.state & 0x0001:
                    if getattr(self.focus, "selection_start", None) is None:
                        self.focus.selection_start = cursor
                    self.focus.selection_end = self.focus.cursor
                else:
                    self.focus.selection_start = None
                    self.focus.selection_end = None
                self.render()

    def arrow_right(self, e):
        if self.focus:
            value = self.focus.attributes.get("value", "")
            cursor = getattr(self.focus, "cursor", len(value))
            if cursor < len(value):
                self.focus.cursor = cursor + 1
                if e.state & 0x0001:
                    if getattr(self.focus, "selection_start", None) is None:
                        self.focus.selection_start = cursor
                    self.focus.selection_end = self.focus.cursor
                else:
                    self.focus.selection_start = None
                    self.focus.selection_end = None
                self.render()

    def enter(self):
        if self.focus:
             pass

    def delete_selection(self, elt):
        start_sel = getattr(elt, "selection_start", None)
        end_sel = getattr(elt, "selection_end", None)
        if start_sel is not None and end_sel is not None:
            start = min(start_sel, end_sel)
            end = max(start_sel, end_sel)
            value = elt.attributes.get("value", "")
            elt.attributes["value"] = value[:start] + value[end:]
            elt.cursor = start
            elt.selection_start = None
            elt.selection_end = None
            return True
        return False

    def copy(self):
        if self.focus:
            start_sel = getattr(self.focus, "selection_start", None)
            end_sel = getattr(self.focus, "selection_end", None)
            if start_sel is not None and end_sel is not None:
                start = min(start_sel, end_sel)
                end = max(start_sel, end_sel)
                value = self.focus.attributes.get("value", "")
                try:
                    root = tkinter._default_root
                    root.clipboard_clear()
                    root.clipboard_append(value[start:end])
                except:
                    pass

    def paste(self):
        if self.focus:
            try:
                root = tkinter._default_root
                text = root.clipboard_get()
            except:
                return
            self.delete_selection(self.focus)
            value = self.focus.attributes.get("value", "")
            cursor = getattr(self.focus, "cursor", len(value))
            self.focus.attributes["value"] = value[:cursor] + text + value[cursor:]
            self.focus.cursor = cursor + len(text)
            self.render()

    def cut(self):
        if self.focus:
            self.copy()
            self.delete_selection(self.focus)
            self.render()

    def submit_form(self, elt):
        if self.js.dispatch_event("submit", elt): return
        inputs = [node for node in tree_to_list(elt, [])
                  if isinstance(node, Element)
                  and node.tag == "input"
                  and "name" in node.attributes]
        body = ""
        for input in inputs:
            name = input.attributes["name"]
            value = input.attributes.get("value", "")
            name = urllib.parse.quote(name)
            value = urllib.parse.quote(value)
            body += "&" + name + "=" + value
        body = body[1:]
        url = self.url.resolve(elt.attributes["action"])
        self.load(url, payload=body)

FONTS = {}

def get_font(weight, slant, size):
    key = (weight, slant, size)
    if key not in FONTS:
        font = tkinter.font.Font(size=size, weight=weight,
            slant=slant)
        label = tkinter.Label(font=font)
        FONTS[key] = (font, label)
    return FONTS[key][0]

class DrawText:
    def __init__(self, x1, y1, text, font, color):
        self.top = y1
        self.left = x1
        self.text = text
        self.font = font
        self.color = color
        self.bottom = y1 + font.metrics("linespace")
        self.rect = Rect(x1, y1, x1 + font.measure(text), self.bottom)

    def execute(self, scroll, canvas):
        canvas.create_text(
            self.left, self.top - scroll,
            text=self.text,
            font=self.font,
            anchor='nw',
            fill=self.color)
    
class DrawRect:
    def __init__(self, rect, color):
        self.rect = rect
        self.color = color

    def execute(self, scroll, canvas):
        canvas.create_rectangle(
            self.rect.left, self.rect.top - scroll,
            self.rect.right, self.rect.bottom - scroll,
            width=0,
            fill=self.color)

class BlockLayout:
    def __init__(self, node, parent, previous):
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children = []
        self.x = None
        self.y = None
        self.width = None
        self.height = None
        self.weight = "normal"
        self.style = "roman"
        self.size = 16
        self.color = "black"
        self.line = []
        self.display_list = []

    def self_rect(self):
        return Rect(self.x, self.y,
            self.x + self.width, self.y + self.height)

    def layout(self):
        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y
        self.x = self.parent.x
        self.width = self.parent.width
        mode = self.layout_mode()
        if mode == "block":
            previous = None
            for child in self.node.children:
                if isinstance(child, Element) and child.tag in ["head", "script", "style", "title", "meta"]:
                    continue
                next = BlockLayout(child, self, previous)
                self.children.append(next)
                previous = next
            for child in self.children:
                child.layout()
            self.height = sum([child.height for child in self.children])
        else:
            self.new_line()
            self.cursor_x = 0
            self.cursor_y = 0
            self.recurse(self.node)
            for child in self.children:
                child.layout()
            self.height = sum([child.height for child in self.children])

    def layout_mode(self):
        BLOCK_ELEMENTS = [
            "html", "body", "article", "section", "nav", "aside",
            "h1", "h2", "h3", "h4", "h5", "h6", "hgroup", "header",
            "footer", "address", "p", "hr", "pre", "blockquote",
            "ol", "ul", "menu", "li", "dl", "dt", "dd", "figure",
            "figcaption", "main", "div", "table", "form", "fieldset",
            "legend", "details", "summary"
        ]
    
        if isinstance(self.node, Text):
            return "inline"
        elif any([isinstance(child, Element) and child.tag in BLOCK_ELEMENTS for child in self.node.children]):
            return "block"
        elif self.node.children or self.node.tag == "input":
            return "inline"
        else:
            return "block"

    def open_tag(self, tag):
        if tag == "i":
            self.style = "italic"
        elif tag == "b":
            self.weight = "bold"
        elif tag == "small":
            self.size -= 2
        elif tag == "big":
            self.size += 4
        elif tag == "br":
            self.new_line()
        elif tag == "a":
            self.color = "blue"

    def close_tag(self, tag):
        if tag == "i":
            self.style = "roman"
        elif tag == "b":
            self.weight = "normal"
        elif tag == "small":
            self.size += 2
        elif tag == "big":
            self.size -= 4
        elif tag == "p":
            self.new_line()
            self.new_line()
        elif tag == "a":
            self.color = "black"

    def recurse(self, node):
        if isinstance(node, Text):
            for word in node.text.split():
                self.word(node, word)
        else:
            if node.tag in ["script", "style", "head", "title", "meta"]:
                return
            if node.tag == "br":
                self.new_line()
            elif node.tag == "input" or node.tag == "button":
                self.input(node)
            else:
                for child in node.children:
                    self.recurse(child)
    
    def word(self, node, word):
        color = node.style["color"]
        weight = parse_font_weight(node.style["font-weight"])
        style = node.style["font-style"]
        if style == "normal": style = "roman"
        size = parse_font_size(node.style["font-size"])
        font = get_font(weight, style, size)
        w = font.measure(word)
        if self.cursor_x + w > self.width:
            self.new_line()
        self.line.append((self.cursor_x, word, font, color))
        line = self.children[-1]
        previous_word = line.children[-1] if line.children else None
        text = TextLayout(node, word, line, previous_word, font, color)
        line.children.append(text)
        self.cursor_x += w + font.measure(" ")

    def input(self, node):
        w = INPUT_WIDTH_PX
        if self.cursor_x + w > self.width:
            self.new_line()
        line = self.children[-1]
        previous_word = line.children[-1] if line.children else None

        weight = parse_font_weight(node.style["font-weight"])
        style = node.style["font-style"]
        if style == "normal": style = "roman"
        size = parse_font_size(node.style["font-size"])
        font = get_font(size=size, weight=weight, slant=style)

        input = InputLayout(node, line, previous_word, font)
        line.children.append(input)

        self.cursor_x += w + font.measure(" ")

    def flush(self):
        if not self.line: return
        metrics = [font.metrics() for x, word, font, color in self.line]
        max_ascent = max([metric["ascent"] for metric in metrics])
        baseline = self.cursor_y + 1.25 * max_ascent
        for rel_x, word, font, color in self.line:
            x = self.x + rel_x
            y = self.y + baseline - font.metrics("ascent")
            self.display_list.append((x, y, word, font, color))
        max_descent = max([metric["descent"] for metric in metrics])
        self.cursor_y = baseline + 1.25 * max_descent
        self.cursor_x = 0
        self.line = []

    def new_line(self):
        self.cursor_x = 0
        last_line = self.children[-1] if self.children else None
        new_line = LineLayout(self.node, self, last_line)
        self.children.append(new_line)

    def should_paint(self):
        return isinstance(self.node, Text) or \
            (self.node.tag != "input" and self.node.tag !=  "button")

    def paint(self):
        cmds = []
        if isinstance(self.node, Element) and self.node.tag == "pre":
            x2, y2 = self.x + self.width, self.y + self.height
            rect = DrawRect(self.self_rect(), "gray")
            cmds.append(rect)

        bgcolor = self.node.style.get("background-color", "transparent")

        if bgcolor != "transparent":
            rect = DrawRect(self.self_rect(), bgcolor)
            cmds.append(rect)

        if self.layout_mode() == "inline":
            for x, y, word, font, color in self.display_list:
                cmds.append(DrawText(x, y , word, font, color))

        return cmds

def paint_tree(layout_object, display_list):
        if layout_object.should_paint():
            display_list.extend(layout_object.paint())

        for child in layout_object.children:
            paint_tree(child, display_list)

class DocumentLayout:
    def __init__(self, node, width=WIDTH):
        self.node = node
        self.parent = None
        self.children = []
        self._width = width

    def should_paint(self):
        return True

    def layout(self):
        self.x = HSTEP
        self.y = VSTEP
        self.width = self._width - 2*HSTEP
        child = BlockLayout(self.node, self, None)
        self.children.append(child)
        child.layout()
        self.display_list = child.display_list
        self.height = child.height

    def paint(self):
        return []
    
class LineLayout:
    def __init__(self, node, parent, previous):
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children = []

    def should_paint(self):
        return True

    def layout(self):
        self.width = self.parent.width
        self.x = self.parent.x

        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y

        for word in self.children:
            word.layout()

        if not self.children:
            self.height = 0
            return

        max_ascent = max([word.font.metrics("ascent") for word in self.children])
        baseline = self.y + 1.25 * max_ascent
        for word in self.children:
            word.y = baseline - word.font.metrics('ascent')
        max_descent = max([word.font.metrics("descent") for word in self.children])

        self.height = 1.25 * (max_ascent + max_descent)

        max_word = self.children[-1]
        line_width = max_word.x + max_word.width - self.x
        
        align = self.node.style.get("text-align", "left")
        if align == "center":
            offset = (self.width - line_width) / 2
        elif align == "right":
            offset = self.width - line_width
        else:
            offset = 0
            
        for word in self.children:
            word.x += offset

    def paint(self):
        return []

class TextLayout:
    def __init__(self, node, word, parent, previous, font, color):
        self.node = node
        self.word = word
        self.parent = parent
        self.previous = previous
        self.children = []
        self.font = font
        self.color = color

    def should_paint(self):
        return True

    def layout(self):
        self.width = self.font.measure(self.word)
        if self.previous:
            space = self.previous.font.measure(" ")
            self.x = self.previous.x + self.previous.width + space
        else:
            self.x = self.parent.x

        self.height = self.font.metrics("linespace")

    def paint(self):
        return [DrawText(self.x, self.y, self.word, self.font, self.color)]

class InputLayout:
    def __init__(self, node, parent, previous, font):
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children = []
        self.font = font

    def should_paint(self):
        return True

    def self_rect(self):
        return Rect(self.x, self.y,
            self.x + self.width, self.y + self.height)

    def layout(self):
        self.width = INPUT_WIDTH_PX
        if self.previous:
            space = self.previous.font.measure(" ")
            self.x = self.previous.x + self.previous.width + space
        else:
            self.x = self.parent.x

        self.height = self.font.metrics("linespace")

    def paint(self):
        cmds = []
        
        # Draw input/button border
        cmds.append(DrawOutline(self.self_rect(), "black", 1))
        
        bgcolor = self.node.style.get("background-color", "transparent")
        if bgcolor != "transparent":
            rect = DrawRect(self.self_rect(), bgcolor)
            cmds.append(rect)

        if self.node.tag == "input":
            text = self.node.attributes.get("value", "")
        elif self.node.tag == "button":
            if len(self.node.children) == 1 and isinstance(self.node.children[0], Text):
                text = self.node.children[0].text
            else:
                # print("Ignoring contents inside button!")
                text = ""

        if self.node.is_focused:
            # Draw selection
            start_sel = getattr(self.node, "selection_start", None)
            end_sel = getattr(self.node, "selection_end", None)
            if start_sel is not None and end_sel is not None:
                start = min(start_sel, end_sel)
                end = max(start_sel, end_sel)
                start_x = self.x + self.font.measure(text[:start])
                end_x = self.x + self.font.measure(text[:end])
                cmds.append(DrawRect(Rect(start_x, self.y, end_x, self.y + self.height), "lightblue"))

            cursor = getattr(self.node, "cursor", len(text))
            cx = self.x + self.font.measure(text[:cursor])
            cmds.append(DrawLine(
                cx, self.y, cx, self.y + self.height, "black", 1))

        color = self.node.style["color"]
        cmds.append(DrawText(self.x, self.y, text, self.font, color))
        return cmds

if __name__ == '__main__':
    import sys
    default_url = "file:///home/"
    url = sys.argv[1] if len(sys.argv) > 1 else default_url
    Browser().new_tab(URL(url))
    tkinter.mainloop()

