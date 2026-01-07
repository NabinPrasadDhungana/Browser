import ctypes
import skia
import sdl2
import dukpy
from browser import URL, HTMLParser, CSSParser, style, cascade_priority
from browser import Text, Element
import urllib.parse
import math

WIDTH = 800
HEIGHT = 600 

HSTEP = 13
VSTEP = 18
SCROLL_STEP = 35
INPUT_WIDTH_PX = 200
DEFAULT_STYLE_SHEET = CSSParser(open("browser.css").read()).parse()
RUNTIME_JS = open("runtime.js").read()
EVENT_DISPATCH_JS = "new Node(dukpy.handle).dispatchEvent(dukpy.type)"

NAMED_COLORS = {
    "black": "#000000",
    "white": "#ffffff",
    "red":   "#ff0000",
    "green": "#00ff00",
    "blue":  "#0000ff",
    "lightblue": "#add8e6",
    "orange": "#ffa500",
    "gray":  "#808080",
    "grey":  "#808080",
    "transparent": "#00000000",
}

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

def parse_length(length_str):
    """Parse length string and return size in pixels."""
    import re
    if length_str == "0": return 0
    match = re.match(r'^([\d.]+)(px|rem|em|pt)?$', length_str)
    if match:
        value = float(match.group(1))
        unit = match.group(2) or 'px'
        if unit == 'px':
            return int(value)
        elif unit == 'rem' or unit == 'em':
            return int(value * 16)
    return 0

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
        self.interp.export_function("XMLHttpRequest_send", self.XMLHttpRequest_send)
        self.interp.evaljs(RUNTIME_JS)

    def run(self,script, code):
        try:
            return self.interp.evaljs(code)
        except dukpy.JSRuntimeError as e:
            print("Script", script, "crashed", e)

    def XMLHttpRequest_send(self, method, url, body):
        full_url = self.tab.url.resolve(url)
        if not self.tab.js.allowed_request(full_url):
            raise Exception("Cross-origin XHR blocked by CSP")
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

class Chrome:
    def __init__(self, browser):
        self.width = WIDTH
        self.browser = browser
        self.font = get_font("normal", "roman", 20)
        self.font_height = linespace(self.font)
        self.padding = 5
        self.tabbar_top = 0
        self.tabbar_bottom = self.font_height + 2*self.padding
        plus_width = self.font.measureText("+") + 2*self.padding
        self.newtab_rect = skia.Rect.MakeLTRB(
            self.padding, 
            self.padding,
            self.padding + plus_width,
            self.padding + self.font_height
        )
        self.bottom = self.tabbar_bottom
        self.urlbar_top = self.tabbar_bottom
        self.urlbar_bottom = self.urlbar_top + self.font_height + 2*self.padding
        self.bottom = self.urlbar_bottom
        back_width = self.font.measureText("<") + 2*self.padding
        self.back_rect = skia.Rect.MakeLTRB(
            self.padding,
            self.urlbar_top + self.padding,
            self.padding + back_width,
            self.urlbar_bottom - self.padding)

        forward_width = self.font.measureText(">") + 2*self.padding
        self.forward_rect = skia.Rect.MakeLTRB(
            self.back_rect.right() + self.padding,
            self.urlbar_top + self.padding,
            self.back_rect.right() + self.padding + forward_width,
            self.urlbar_bottom - self.padding)

        reload_width = self.font.measureText("R") + 2*self.padding
        self.reload_rect = skia.Rect.MakeLTRB(
            self.forward_rect.right() + self.padding,
            self.urlbar_top + self.padding,
            self.forward_rect.right() + self.padding + reload_width,
            self.urlbar_bottom - self.padding)

        self.address_rect = skia.Rect.MakeLTRB(
            self.reload_rect.right() + self.padding,
            self.urlbar_top + self.padding,
            WIDTH - self.padding,
            self.urlbar_bottom - self.padding)
        self.focus = None
        self.address_bar = ""
        self.cursor = 0
        self.selection_start = None
        self.selection_end = None

    def resize(self, width):
        self.address_rect.fRight = width - self.padding
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

    def arrow_left(self, mod):
        if self.focus == "address bar":
            if self.cursor > 0:
                self.cursor -= 1
                if mod & sdl2.KMOD_SHIFT:
                    if self.selection_start is None:
                        self.selection_start = self.cursor + 1
                    self.selection_end = self.cursor
                else:
                    self.selection_start = None
                    self.selection_end = None
                return True
        return False

    def arrow_right(self, mod):
        if self.focus == "address bar":
            if self.cursor < len(self.address_bar):
                self.cursor += 1
                if mod & sdl2.KMOD_SHIFT:
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
            text = self.address_bar[start:end]
            sdl2.SDL_SetClipboardText(text.encode())

    def paste(self):
        text = sdl2.SDL_GetClipboardText()
        if not text: return
        text = text.decode('utf8')
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
        tabs_start = self.newtab_rect.right() + self.padding
        tab_width = self.font.measureText("Tab X") + 2*self.padding
        return skia.Rect.MakeLTRB(
            tabs_start + tab_width * i,
            self.tabbar_top,
            tabs_start + tab_width * (i+1),
            self.tabbar_bottom
        )
    
    def click(self, x, y):
        was_focused = self.focus == "address bar"
        self.focus = None
        if self.newtab_rect.contains(x, y):
            self.browser.new_tab(URL("about:blank"))
        elif self.back_rect.contains(x, y):
            self.browser.active_tab.go_back()
        elif self.forward_rect.contains(x, y):
            self.browser.active_tab.go_forward()
        elif self.reload_rect.contains(x, y):
            self.browser.active_tab.reload()
        elif self.address_rect.contains(x, y):
            self.focus = "address bar"
            if not was_focused:
                self.address_bar = str(self.browser.active_tab.url)
            
            self.cursor = len(self.address_bar)
            for i in range(len(self.address_bar)):
                w = self.font.measureText(self.address_bar[:i+1])
                if self.address_rect.left() + self.padding + w > x:
                    self.cursor = i
                    break
            self.selection_start = None
            self.selection_end = None
        else:
            for i, tab in enumerate(self.browser.tabs):
                if self.tab_rect(i).contains(x, y):
                    self.browser.active_tab = tab
                    break
    
    def paint(self):
        cmds = []
        
        # Draw the URL bar background FIRST (only covers URL bar, not tabs)
        cmds.append(DrawRRect(
            skia.Rect.MakeLTRB(0, self.urlbar_top, self.width, self.bottom), 0, "white"))
        cmds.append(DrawLine(
            0, self.bottom, self.width, self.bottom, "black", 1))
        
        # Now draw the new tab button
        cmds.append(DrawOutline(self.newtab_rect, "black", 1))
        cmds.append(DrawText(
            self.newtab_rect.left() + self.padding,
            self.newtab_rect.top(),
            "+",
            self.font,
            "black"
        ))
        
        # Draw tabs
        for i, tab in enumerate(self.browser.tabs):
            bounds = self.tab_rect(i)
            cmds.append(DrawLine(
                bounds.left(), 0, bounds.left(), bounds.bottom(),
                "black", 1))
            cmds.append(DrawLine(
                bounds.right(), 0, bounds.right(), bounds.bottom(),
                "black", 1))
            cmds.append(DrawText(
                bounds.left() + self.padding, bounds.top() + self.padding,
                "Tab {}".format(i), self.font, "black"))
            
            if tab == self.browser.active_tab:
                cmds.append(DrawLine(
                    0, bounds.bottom(), bounds.left(), bounds.bottom(), "black", 1))
                cmds.append(DrawLine(
                    bounds.right(), bounds.bottom(), self.width, bounds.bottom(), "black", 1))

        # Draw back button (gray if can't go back)
        back_color = "black" if len(self.browser.active_tab.history) > 1 else "gray"
        cmds.append(DrawOutline(self.back_rect, back_color, 1))
        cmds.append(DrawText(
            self.back_rect.left() + self.padding,
            self.back_rect.top(),
            "<", self.font, back_color))
        
        # Draw forward button (gray if can't go forward)
        forward_color = "black" if len(self.browser.active_tab.forward_history) > 0 else "gray"
        cmds.append(DrawOutline(self.forward_rect, forward_color, 1))
        cmds.append(DrawText(
            self.forward_rect.left() + self.padding,
            self.forward_rect.top(),
            ">", self.font, forward_color))
        
        # Draw reload button
        cmds.append(DrawOutline(self.reload_rect, "black", 1))
        cmds.append(DrawText(
            self.reload_rect.left() + self.padding,
            self.reload_rect.top(),
            "R", self.font, "black"))

        cmds.append(DrawOutline(self.address_rect, "black", 1))
        
        if self.focus == "address bar":
            if self.selection_start is not None:
                start = min(self.selection_start, self.selection_end)
                end = max(self.selection_start, self.selection_end)
                start_x = self.address_rect.left() + self.padding + self.font.measureText(self.address_bar[:start])
                end_x = self.address_rect.left() + self.padding + self.font.measureText(self.address_bar[:end])
                cmds.append(DrawRRect(skia.Rect.MakeLTRB(start_x, self.address_rect.top() + self.padding, end_x, self.address_rect.bottom() - self.padding), 0, "lightblue"))

            cmds.append(DrawText(
                self.address_rect.left() + self.padding,
                self.address_rect.top(),
                self.address_bar,
                self.font,
                "black"))
            w = self.font.measureText(self.address_bar[:self.cursor])
            cmds.append(DrawLine(
                self.address_rect.left() + self.padding + w,
                self.address_rect.top(),
                self.address_rect.left() + self.padding + w,
                self.address_rect.bottom(),
                "red", 1))
        else:
            url = str(self.browser.active_tab.url)
            cmds.append(DrawText(
                self.address_rect.left() + self.padding,
                self.address_rect.top(),
                url,
                self.font,
                "black"))

        return cmds
    
class DrawLine:
    def __init__(self, x1, y1, x2, y2, color, thickness):
        self.rect = skia.Rect.MakeLTRB(x1, y1, x2, y2)
        self.color = color
        self.thickness = thickness

    @property
    def bottom(self):
        return self.rect.bottom()

    def execute(self, scroll, canvas):
        path = skia.Path().moveTo(
            self.rect.left(), self.rect.top() - scroll) \
                .lineTo(self.rect.right(),
                    self.rect.bottom() - scroll)
        paint = skia.Paint(
            Color=parse_color(self.color),
            StrokeWidth=self.thickness,
            Style=skia.Paint.kStroke_Style,
        )
        canvas.drawPath(path, paint)
    
class DrawOutline:
    def __init__(self, rect, color, thickness):
        self.rect = rect
        self.color = color
        self.thickness = thickness

    @property
    def bottom(self):
        return self.rect.bottom()

    def execute(self, scroll, canvas):
        paint = skia.Paint(
            Color=parse_color(self.color),
            StrokeWidth=self.thickness,
            Style=skia.Paint.kStroke_Style,
        )
        canvas.drawRect(self.rect.makeOffset(0, -scroll), paint)

class Browser:
    def __init__(self):
        self.tabs = []
        self.active_tab = None
        self.sdl_window = sdl2.SDL_CreateWindow(b"Browser",
            sdl2.SDL_WINDOWPOS_CENTERED, sdl2.SDL_WINDOWPOS_CENTERED,
            WIDTH, HEIGHT, sdl2.SDL_WINDOW_SHOWN | sdl2.SDL_WINDOW_RESIZABLE)
        
        self.root_surface = skia.Surface.MakeRaster(
            skia.ImageInfo.Make(
                WIDTH, HEIGHT,
                ct=skia.kRGBA_8888_ColorType,
                at=skia.kUnpremul_AlphaType))
        
        if sdl2.SDL_BYTEORDER == sdl2.SDL_BIG_ENDIAN:
            self.RED_MASK = 0xff000000
            self.GREEN_MASK = 0x00ff0000
            self.BLUE_MASK = 0x0000ff00
            self.ALPHA_MASK = 0x000000ff
        else:
            self.RED_MASK = 0x000000ff
            self.GREEN_MASK = 0x0000ff00
            self.BLUE_MASK = 0x00ff0000
            self.ALPHA_MASK = 0xff000000
        
        self.width = WIDTH
        self.height = HEIGHT
        self.scroll = 0
        self.url = None
        self.chrome = Chrome(self)
        self.chrome_surface = skia.Surface(WIDTH, math.ceil(self.chrome.bottom))
        self.tab_surface = None

    def raster_tab(self):
        tab_height = math.ceil(self.active_tab.document.height + 2*VSTEP)
        if not self.tab_surface or tab_height != self.tab_surface.height():
            self.tab_surface = skia.Surface(WIDTH, tab_height)
        canvas = self.tab_surface.getCanvas()
        canvas.clear(skia.ColorWHITE)

    def raster_chrome(self):
        canvas = self.chrome_surface.getCanvas()
        canvas.clear(skia.ColorWHITE)

    def handle_quit(self):
        sdl2.SDL_DestroyWindow(self.sdl_window)

    def handle_enter(self):
        if self.chrome.focus == "address bar":
            self.chrome.enter()
        elif self.focus == "content":
            self.active_tab.enter()
        self.draw()

    def handle_backspace(self):
        if self.chrome.focus == "address bar":
            self.chrome.backspace()
        elif self.focus == "content":
            self.active_tab.backspace()
        self.draw()

    def handle_left(self, mod):
        if self.chrome.focus == "address bar":
            self.chrome.arrow_left(mod)
        elif self.focus == "content":
            self.active_tab.arrow_left(mod)
        self.draw()

    def handle_right(self, mod):
        if self.chrome.focus == "address bar":
            self.chrome.arrow_right(mod)
        elif self.focus == "content":
            self.active_tab.arrow_right(mod)
        self.draw()

    def handle_copy(self):
        if self.chrome.focus == "address bar":
            self.chrome.copy()
        elif self.focus == "content":
            self.active_tab.copy()

    def handle_paste(self):
        if self.chrome.focus == "address bar":
            self.chrome.paste()
        elif self.focus == "content":
            self.active_tab.paste()
        self.draw()

    def handle_cut(self):
        if self.chrome.focus == "address bar":
            self.chrome.cut()
        elif self.focus == "content":
            self.active_tab.cut()
        self.draw()

    def handle_key(self, char):
        if len(char) == 0: return
        if not (0x20 <= ord(char) < 0x7f): return
        if self.chrome.key_press(char):
            self.draw()
        elif self.focus == "content":
            self.active_tab.key_press(char)
            self.draw()

    def handle_down(self):
        self.active_tab.scrolldown()
        self.draw()

    def handle_up(self):
        self.active_tab.scrollup()
        self.draw()

    def handle_mousewheel(self, e):
        if self.active_tab:
            self.active_tab.mousewheel(e)
        self.draw()

    def handle_mousedown(self, e):
        if e.y < self.chrome.bottom:
            pass
        else:
            self.focus = "content"
            self.chrome.blur()
            tab_y = e.y - self.chrome.bottom
            self.active_tab.mousedown(e.x, tab_y)
        self.draw()

    def handle_mousemotion(self, e):
        if self.active_tab and self.active_tab.scrolling:
            tab_y = e.y - self.chrome.bottom
            self.active_tab.mousemotion(e.x, tab_y)
            self.draw()

    def handle_click(self, e):
        if e.y < self.chrome.bottom:
            self.focus = None
            self.chrome.click(e.x, e.y)
            self.raster_chrome()
        else:
            self.focus = "content"
            self.chrome.blur()
            url = self.active_tab.url
            tab_y = e.y - self.chrome.bottom
            self.active_tab.click(e.x, tab_y)
            if self.active_tab.url != url:
                self.raster_chrome()
            self.raster_tab()
        self.draw()

    def handle_configure(self, width, height):
        self.width = width
        self.height = height
        self.root_surface = skia.Surface.MakeRaster(
            skia.ImageInfo.Make(
                width, height,
                ct=skia.kRGBA_8888_ColorType,
                at=skia.kUnpremul_AlphaType))
        self.chrome.resize(width)
        if self.active_tab:
            self.active_tab.resize(width, height - self.chrome.bottom)
        self.draw()

    def draw(self):
        canvas = self.root_surface.getCanvas()
        canvas.clear(skia.ColorWHITE)

        tab_rect = skia.Rect.MakeLTRB(0, self.chrome.bottom, WIDTH, HEIGHT)
        tab_offset = self.chrome.bottom - self.active_tab.scroll
        canvas.save()
        canvas.clipRect(tab_rect)
        canvas.translate(0, tab_offset)
        self.tab_surface.draw(canvas, 0, 0)
        canvas.restore()

        chrome_rect = skia.Rect.MakeLTRB(0, 0, WIDTH, self.chrome.bottom)
        canvas.save()
        canvas.clipRect(chrome_rect)
        self.chrome_surface.draw(canvas, 0, 0)
        canvas.restore()
        
        self.active_tab.draw(canvas, self.chrome.bottom)
        for cmd in self.chrome.paint():
            cmd.execute(0, canvas)
        
        # Set window title from page's <title> element
        title = self.active_tab.get_title()
        if title:
            sdl2.SDL_SetWindowTitle(self.sdl_window, title.encode())
        else:
            sdl2.SDL_SetWindowTitle(self.sdl_window, str(self.active_tab.url).encode())

        skia_image = self.root_surface.makeImageSnapshot()
        skia_bytes = skia_image.tobytes()
        depth = 32 # Bits per pixel
        pitch = 4 * self.width # Bytes per row
        sdl_surface = sdl2.SDL_CreateRGBSurfaceFrom(
            skia_bytes, self.width, self.height, depth, pitch,
            self.RED_MASK, self.GREEN_MASK,
            self.BLUE_MASK, self.ALPHA_MASK)
        rect = sdl2.SDL_Rect(0, 0, self.width, self.height)
        window_surface = sdl2.SDL_GetWindowSurface(self.sdl_window)
        # SDL_BlitSurface is what actually does the copy.
        sdl2.SDL_BlitSurface(sdl_surface, rect, window_surface, rect)
        sdl2.SDL_UpdateWindowSurface(self.sdl_window)

    def new_tab(self, url):
        new_tab = Tab(HEIGHT - self.chrome.bottom)
        new_tab.load(url)
        self.active_tab = new_tab
        self.tabs.append(new_tab)
        self.raster_tab()
        self.raster_chrome()
        self.draw()

class Tab:
    def __init__(self, tab_height):
        self.tab_height = tab_height
        self.history = []
        self.forward_history = []
        self.scroll = 0
        self.width = WIDTH
        self.focus = None
        self.url = None
        self.allowed_origins = None
        self.scrolling = False

    def load(self, url, payload=None, from_navigation=False):
        if not from_navigation:
            self.forward_history.clear()
        headers, body = url.request(self.url, payload)
        self.history.append(url)
        self.url = url
        self.nodes = HTMLParser(body).parse()
        rules = DEFAULT_STYLE_SHEET.copy()

        if "content-security-policy" in headers:
            csp = headers["content-security-policy"].split()
            if len(csp) > 0 and csp[0] == "default-src":
                self.allowed_origins = []
                for origin in csp[1:]:
                    if origin == "'self'":
                        self.allowed_origins.append(url.origin())
                    else:
                        self.allowed_origins.append(URL(origin).origin())

        for node in tree_to_list(self.nodes, []):
            if isinstance(node, Element):
                # Handle external CSS files linked via <link>
                if node.tag == "link" and \
                   node.attributes.get("rel") == "stylesheet" and \
                   "href" in node.attributes:
                    try:
                        style_url = url.resolve(node.attributes["href"])
                        if not self.allowed_request(style_url):
                            continue
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

                # Handle textarea input
                elif node.tag == "textarea":
                    if not "value" in node.attributes:
                        text_content = ""
                        for child in node.children:
                            if isinstance(child, Text):
                                text_content += child.text
                        node.attributes["value"] = text_content
                        node.children = []

        scripts = [node.attributes["src"] for node
                   in tree_to_list(self.nodes, [])
                   if isinstance(node, Element)
                   and node.tag == "script"
                   and "src" in node.attributes]
        
        self.js = JSContext(self)
        for script in scripts:
            script_url = url.resolve(script)
            if not self.allowed_request(script_url):
                continue
            try:
                header, body = script_url.request(url)
            except:
                continue
            self.js.run(script_url, body)
        
        self.rules = rules
        self.render()
        self.scroll_to_fragment()

    def allowed_request(self, target_url):
        if self.allowed_origins is None:
            return True
        return target_url.origin() in self.allowed_origins

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

    def reload(self):
        if not self.url:
            return
        # Avoid duplicating the current entry in history on reload
        if self.history and self.history[-1] is self.url:
            self.history.pop()
        self.load(self.url, from_navigation=True)

    def draw(self, canvas, offset):
        canvas.save()
        canvas.translate(0, offset)
        canvas.clipRect(skia.Rect.MakeLTRB(0, 0, self.width, self.tab_height))
        for cmd in self.display_list:
            if cmd.rect.top() > self.scroll + self.tab_height: continue
            if cmd.rect.bottom() < self.scroll: continue
            cmd.execute(self.scroll, canvas)
        
        self.draw_scrollbar(canvas, 0)
        canvas.restore()

    def draw_scrollbar(self, canvas, offset):
        if not self.display_list:
            return
            
        content_height = self.display_list[-1].bottom + VSTEP
        if content_height <= self.tab_height:
            return
            
        scrollbar_width = 12
        scrollbar_height = (self.tab_height / content_height) * self.tab_height
        scrollbar_y = (self.scroll / content_height) * self.tab_height + offset
        
        rect = skia.Rect.MakeLTRB(
            self.width - scrollbar_width, scrollbar_y,
            self.width, scrollbar_y + scrollbar_height)
        paint = skia.Paint(Color=skia.ColorBLUE)
        canvas.drawRect(rect, paint)

    def scrolldown(self):
        max_y = max(self.document.height + 2*VSTEP - self.tab_height, 0)
        self.scroll = min(self.scroll + SCROLL_STEP, max_y)

    def scrollup(self):
        if not self.scroll <= 0:
            self.scroll -= SCROLL_STEP

    def mousewheel(self, e):
        if not self.display_list:
            return
        if e.y > 0:
            self.scrollup()
        elif e.y < 0:
            self.scrolldown()

    def resize(self, width, height):
        self.width = width
        self.tab_height = height
        if hasattr(self, 'nodes'):
            self.document = DocumentLayout(self.nodes, self.width)
            self.document.layout()
            self.display_list = []
            paint_tree(self.document, self.display_list)

    def mousedown(self, x, y):
        if not self.display_list: return
        content_height = self.display_list[-1].bottom + VSTEP
        if content_height <= self.tab_height: return
        
        scrollbar_width = 12
        scrollbar_height = (self.tab_height / content_height) * self.tab_height
        scrollbar_y = (self.scroll / content_height) * self.tab_height
        
        if self.width - scrollbar_width <= x <= self.width:
            if scrollbar_y <= y <= scrollbar_y + scrollbar_height:
                self.scrolling = True
                self.scroll_start_y = y
                self.scroll_start_scroll = self.scroll

    def mousemotion(self, x, y):
        if self.scrolling:
            content_height = self.display_list[-1].bottom + VSTEP
            dy = y - self.scroll_start_y
            scroll_dy = dy * (content_height / self.tab_height)
            self.scroll = self.scroll_start_scroll + scroll_dy
            
            max_y = max(content_height - self.tab_height, 0)
            self.scroll = max(0, min(self.scroll, max_y))

    def click(self, x, y):
        if self.scrolling:
            self.scrolling = False
            return
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
            elif elt.tag == "input" or elt.tag == "textarea":
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
                current = elt
                while current:
                    if current.tag == "form" and "action" in current.attributes:
                        return self.submit_form(current)
                    current = current.parent
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

    def arrow_left(self, mod):
        if self.focus:
            value = self.focus.attributes.get("value", "")
            cursor = getattr(self.focus, "cursor", len(value))
            if cursor > 0:
                self.focus.cursor = cursor - 1
                if mod & sdl2.KMOD_SHIFT:
                    if getattr(self.focus, "selection_start", None) is None:
                        self.focus.selection_start = cursor
                    self.focus.selection_end = self.focus.cursor
                else:
                    self.focus.selection_start = None
                    self.focus.selection_end = None
                self.render()

    def arrow_right(self, mod):
        if self.focus:
            value = self.focus.attributes.get("value", "")
            cursor = getattr(self.focus, "cursor", len(value))
            if cursor < len(value):
                self.focus.cursor = cursor + 1
                if mod & sdl2.KMOD_SHIFT:
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
                sdl2.SDL_SetClipboardText(value[start:end].encode())

    def paste(self):
        if self.focus:
            text = sdl2.SDL_GetClipboardText()
            if not text: return
            text = text.decode('utf8')
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
                  and (node.tag == "input" or node.tag == "textarea")
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

def get_font(weight, style, size):
    key = (weight, style)
    if key not in FONTS:
        if weight == "bold":
            skia_weight = skia.FontStyle.kBold_Weight
        else:
            skia_weight = skia.FontStyle.kNormal_Weight
        if style == "italic":
            skia_style = skia.FontStyle.kItalic_Slant
        else:
            skia_style = skia.FontStyle.kUpright_Slant
        skia_width = skia.FontStyle.kNormal_Width
        style_info = skia.FontStyle(skia_weight, skia_width, skia_style)
        font = skia.Typeface('Arial', style_info)
        FONTS[key] = font
    return skia.Font(FONTS[key], size)

class DrawText:
    def __init__(self, x1, y1, text, font, color):
        self.top = y1
        self.left = x1
        self.text = text
        self.font = font
        self.color = color
        self.bottom = y1 + linespace(font)
        self.rect = skia.Rect.MakeLTRB(
            x1, y1,
            x1 + font.measureText(text),
            self.bottom)

    def execute(self, scroll, canvas):
        paint = skia.Paint(
            AntiAlias=True,
            Color=parse_color(self.color),
        )
        baseline = self.rect.top() - scroll - self.font.getMetrics().fAscent
        canvas.drawString(self.text, float(self.rect.left()),
            baseline, self.font, paint)
    
class DrawRRect:
    def __init__(self, rect, radius, color):
        self.rect = rect
        self.rrect = skia.RRect.MakeRectXY(rect, radius, radius)
        self.color = color

    @property
    def bottom(self):
        return self.rect.bottom()

    def execute(self, scroll, canvas):
        paint = skia.Paint(
            Color=parse_color(self.color),
        )
        rrect = skia.RRect.MakeRectXY(self.rect.makeOffset(0, -scroll), self.rrect.radii(skia.RRect.kUpperLeft_Corner).x(), self.rrect.radii(skia.RRect.kUpperLeft_Corner).y())
        canvas.drawRRect(rrect, paint)

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

    def self_rect(self):
        return skia.Rect.MakeLTRB(self.x, self.y,
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
        elif self.node.children or self.node.tag == "input" or self.node.tag == "textarea":
            return "inline"
        else:
            return "block"

    def recurse(self, node):
        if isinstance(node, Text):
            if isinstance(self.node, Element) and self.node.tag == "pre":
                lines = node.text.split("\n")
                for i, line in enumerate(lines):
                    if line:
                        self.word(node, line)
                    if i < len(lines) - 1:
                        self.new_line()
            else:
                for word in node.text.split():
                    self.word(node, word)
        else:
            if node.tag in ["script", "style", "head", "title", "meta"]:
                return
            if node.tag == "br":
                self.new_line()
            elif node.tag == "input" or node.tag == "button" or node.tag == "textarea":
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
        w = font.measureText(word)
        if self.cursor_x + w > self.width and not (isinstance(self.node, Element) and self.node.tag == "pre"):
            self.new_line()
        line = self.children[-1]
        previous_word = line.children[-1] if line.children else None
        text = TextLayout(node, word, line, previous_word, font, color)
        line.children.append(text)
        self.cursor_x += w
        if not (isinstance(self.node, Element) and self.node.tag == "pre"):
            self.cursor_x += font.measureText(" ")

    def input(self, node):
        if node.tag == "input" and node.attributes.get("type", "").casefold() == "hidden":
            return
        w = INPUT_WIDTH_PX
        if self.cursor_x + w > self.width:
            self.new_line()
        line = self.children[-1]
        previous_word = line.children[-1] if line.children else None

        weight = parse_font_weight(node.style["font-weight"])
        style = node.style["font-style"]
        if style == "normal": style = "roman"
        size = parse_font_size(node.style["font-size"])
        font = get_font(size=size, weight=weight, style=style)

        input = InputLayout(node, line, previous_word, font)
        line.children.append(input)

        self.cursor_x += w + font.measureText(" ")

    def new_line(self):
        self.cursor_x = 0
        last_line = self.children[-1] if self.children else None
        new_line = LineLayout(self.node, self, last_line)
        self.children.append(new_line)

    def should_paint(self):
        return isinstance(self.node, Text) or \
            (self.node.tag != "input" and self.node.tag !=  "button" and self.node.tag != "textarea")

    def paint_effects(self, cmds):
        cmds = paint_visual_effects(self.node, cmds, self.self_rect())
        return cmds

    def paint(self):
        cmds = []
        if isinstance(self.node, Element) and self.node.tag == "pre":
            x2, y2 = self.x + self.width, self.y + self.height
            rect = DrawRRect(self.self_rect(), 0, "gray")
            cmds.append(rect)

        bgcolor = self.node.style.get("background-color", "transparent")

        if bgcolor != "transparent":
            radius = parse_length(self.node.style.get("border-radius", "0px"))
            rect = DrawRRect(self.self_rect(), radius, bgcolor)
            cmds.append(rect)

        return cmds

def paint_tree(layout_object, display_list):
        if layout_object.should_paint():
            cmds = layout_object.paint()
        else:
            cmds = []

        for child in layout_object.children:
            paint_tree(child, cmds)

        if layout_object.should_paint():
            cmds = layout_object.paint_effects(cmds)
            
        display_list.extend(cmds)

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
        self.height = child.height

    def paint(self):
        return []

    def paint_effects(self, cmds):
        return cmds
    
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

        max_ascent = max([-word.font.getMetrics().fAscent for word in self.children])
        baseline = self.y + 1.25 * max_ascent
        for word in self.children:
            word.y = baseline + word.font.getMetrics().fAscent
        max_descent = max([word.font.getMetrics().fDescent for word in self.children])

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

    def paint_effects(self, cmds):
        return cmds

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
        self.width = self.font.measureText(self.word)
        if self.previous:
            space = self.previous.font.measureText(" ")
            if isinstance(self.parent.node, Element) and self.parent.node.tag == "pre":
                space = 0
            self.x = self.previous.x + self.previous.width + space
        else:
            self.x = self.parent.x

        self.height = linespace(self.font)

    def paint(self):
        return [DrawText(self.x, self.y, self.word, self.font, self.color)]

    def paint_effects(self, cmds):
        return cmds

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
        return skia.Rect.MakeLTRB(self.x, self.y,
            self.x + self.width, self.y + self.height)

    def layout(self):
        self.width = INPUT_WIDTH_PX
        if self.previous:
            space = self.previous.font.measureText(" ")
            self.x = self.previous.x + self.previous.width + space
        else:
            self.x = self.parent.x

        self.height = linespace(self.font)

    def paint(self):
        cmds = []
        
        # Draw input/button border
        cmds.append(DrawOutline(self.self_rect(), "black", 1))
        
        bgcolor = self.node.style.get("background-color", "transparent")
        if bgcolor != "transparent":
            rect = DrawRRect(self.self_rect(), 0, bgcolor)
            cmds.append(rect)

        if self.node.tag == "input" or self.node.tag == "textarea":
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
                start_x = self.x + self.font.measureText(text[:start])
                end_x = self.x + self.font.measureText(text[:end])
                cmds.append(DrawRRect(skia.Rect.MakeLTRB(start_x, self.y, end_x, self.y + self.height), 0, "lightblue"))

            cursor = getattr(self.node, "cursor", len(text))
            cx = self.x + self.font.measureText(text[:cursor])
            cmds.append(DrawLine(
                cx, self.y, cx, self.y + self.height, "black", 1))

        color = self.node.style["color"]
        cmds.append(DrawText(self.x, self.y, text, self.font, color))
        return cmds

    def paint_effects(self, cmds):
        cmds = paint_visual_effects(self.node, cmds, self.self_rect())
        return cmds
    
class Opacity:
    def __init__(self, opacity, children):
        self.opacity = opacity
        self.children = children
        self.rect = skia.Rect.MakeEmpty()
        for cmd in self.children:
            self.rect.join(cmd.rect)

    @property
    def bottom(self):
        return self.rect.bottom()

    def execute(self, scroll, canvas):
        paint = skia.Paint(Alphaf=self.opacity)
        if self.opacity < 1.0:
            canvas.saveLayer(None, paint)
        for cmd in self.children:
            cmd.execute(scroll, canvas)
        if self.opacity < 1:
            canvas.restore()

class Blend:
    def __init__(self, opacity, blend_mode, children):
        self.blend_mode = blend_mode
        self.opacity = opacity
        self.should_save = self.blend_mode or self.opacity < 1

        self.children = children
        self.rect = skia.Rect.MakeEmpty()
        for cmd in self.children:
            self.rect.join(cmd.rect)

    @property
    def bottom(self):
        return self.rect.bottom()

    def execute(self, scroll, canvas):
        paint = skia.Paint(
            Alphaf=self.opacity,
            BlendMode=parse_blend_mode(self.blend_mode),
        )
        if self.should_save:
            canvas.saveLayer(None, paint)
        for cmd in self.children:
            cmd.execute(scroll, canvas)
        if self.should_save:
            canvas.restore()

def parse_blend_mode(blend_mode_str):
    if blend_mode_str == "multiply":
        return skia.BlendMode.kMultiply
    elif blend_mode_str == "difference":
        return skia.BlendMode.kDifference
    elif blend_mode_str == "destination-in":
        return skia.BlendMode.kDstIn
    elif blend_mode_str == "source-over":
        return skia.BlendMode.kSrcOver
    else:
        return skia.BlendMode.kSrcOver

def paint_visual_effects(node, cmds, rect):
    opacity = float(node.style.get("opacity", "1.0"))
    blend_mode = node.style.get("mix-blend-mode")
    if node.style.get("overflow", "visible") == "clip":
        if not blend_mode:
            blend_mode = "source-over"
        border_radius = float(node.style.get("border-radius", "0px")[:-2])
        cmds.append(Blend(1.0, "destination-in", [
            DrawRRect(rect, border_radius, "white")
        ]))

    return [Blend(opacity, blend_mode, cmds)]

def linespace(font):
    metrics = font.getMetrics()
    return metrics.fDescent - metrics.fAscent
    
def parse_color(color):
    if color.startswith("#"):
        if len(color) == 7:
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)
            return skia.Color(r, g, b)
        elif len(color) == 9:
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)
            a = int(color[7:9], 16)
            return skia.Color(r, g, b, a)
        elif len(color) == 4:
            r = int(color[1]*2, 16)
            g = int(color[2]*2, 16)
            b = int(color[3]*2, 16)
            return skia.Color(r, g, b)
    elif color.startswith("rgb"):
        import re
        match = re.match(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)', color)
        if match:
            r = int(match.group(1))
            g = int(match.group(2))
            b = int(match.group(3))
            a = 255
            if match.group(4):
                a = int(float(match.group(4)) * 255)
            return skia.Color(r, g, b, a)
    elif color in NAMED_COLORS:
        return parse_color(NAMED_COLORS[color])
    else:
        return skia.ColorBLACK
    
def mainloop(browser):
    event = sdl2.SDL_Event()
    while True:
        while sdl2.SDL_PollEvent(ctypes.byref(event)) != 0:
            if event.type == sdl2.SDL_QUIT:
                browser.handle_quit()
                sdl2.SDL_Quit()
                sys.exit()
            elif event.type == sdl2.SDL_MOUSEBUTTONUP:
                browser.handle_click(event.button)
            elif event.type == sdl2.SDL_MOUSEBUTTONDOWN:
                browser.handle_mousedown(event.button)
            elif event.type == sdl2.SDL_MOUSEMOTION:
                browser.handle_mousemotion(event.motion)
            elif event.type == sdl2.SDL_MOUSEWHEEL:
                browser.handle_mousewheel(event.wheel)
            elif event.type == sdl2.SDL_WINDOWEVENT:
                if event.window.event == sdl2.SDL_WINDOWEVENT_SIZE_CHANGED:
                    browser.handle_configure(event.window.data1, event.window.data2)
            elif event.type == sdl2.SDL_KEYDOWN:
                if event.key.keysym.sym == sdl2.SDLK_RETURN:
                    browser.handle_enter()
                elif event.key.keysym.sym == sdl2.SDLK_DOWN:
                    browser.handle_down()
                elif event.key.keysym.sym == sdl2.SDLK_UP:
                    browser.handle_up()
                elif event.key.keysym.sym == sdl2.SDLK_BACKSPACE:
                    browser.handle_backspace()
                elif event.key.keysym.sym == sdl2.SDLK_LEFT:
                    browser.handle_left(event.key.keysym.mod)
                elif event.key.keysym.sym == sdl2.SDLK_RIGHT:
                    browser.handle_right(event.key.keysym.mod)
                elif event.key.keysym.sym == sdl2.SDLK_c and (event.key.keysym.mod & sdl2.KMOD_CTRL):
                    browser.handle_copy()
                elif event.key.keysym.sym == sdl2.SDLK_v and (event.key.keysym.mod & sdl2.KMOD_CTRL):
                    browser.handle_paste()
                elif event.key.keysym.sym == sdl2.SDLK_x and (event.key.keysym.mod & sdl2.KMOD_CTRL):
                    browser.handle_cut()
            elif event.type == sdl2.SDL_TEXTINPUT:
                browser.handle_key(event.text.text.decode('utf8'))

if __name__ == '__main__':
    import sys
    sdl2.SDL_Init(sdl2.SDL_INIT_EVENTS)
    default_url = "file:///home/"
    url = sys.argv[1] if len(sys.argv) > 1 else default_url
    browser = Browser()
    browser.new_tab(URL(url))
    mainloop(browser)

