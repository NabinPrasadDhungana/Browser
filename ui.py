import tkinter
from browser import URL, HTMLParser
import tkinter.font
from browser import Text, Element

WIDTH = 800
HEIGHT = 600 

HSTEP = 13
VSTEP = 18
SCROLL_STEP = 35

def tree_to_list(tree, list):
    list.append(tree)
    for child in tree.children:
        tree_to_list(child, list)
    return list

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

        self.address_rect = Rect(
            self.back_rect.top + self.padding,
            self.urlbar_top + self.padding,
            WIDTH - self.padding,
            self.urlbar_bottom - self.padding)
        self.focus = None
        self.address_bar = ""

    def key_press(self, char):
        if self.focus == "address bar":
            self.address_bar += char

    def enter(self):
        if self.focus == "address bar":
            self.browser.active_tab.load(URL(self.address_bar))
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
        self.focus = None
        if self.newtab_rect.contains_point(x, y):
            self.browser.new_tab(URL("https://browser.engineering/"))
        elif self.back_rect.contains_point(x, y):
            self.browser.active_tab.go_back()
        elif self.address_rect.contains_point(x, y):
            self.focus = "address bar"
            self.address_bar = ""
        else:
            for i, tab in enumerate(self.browser.tabs):
                if self.tab_rect(i).contains_point(x, y):
                    self.browser.active_tab = tab
                    break
    
    def paint(self):
        cmds = []
        cmds.append(DrawOutline(self.newtab_rect, "black", 1))
        cmds.append(DrawText(
            self.newtab_rect.left + self.padding,
            self.newtab_rect.top,
            "+",
            self.font,
            "black"
        ))
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
                    bounds.right, bounds.bottom, WIDTH, bounds.bottom, "black", 1))
            cmds.append(DrawRect(
                Rect(0, 0, WIDTH, self.bottom), "white"))
            cmds.append(DrawLine(
                0, self.bottom, WIDTH, self.bottom, "black", 1))
            cmds.append(DrawOutline(self.back_rect, "black", 1))
            cmds.append(DrawText(
                self.back_rect.left + self.padding,
                self.back_rect.top,
                "<", self.font, "black"))
            
            if self.focus == "address bar":
                cmds.append(DrawText(
                    self.address_rect.left + self.padding,
                    self.address_rect.top,
                    self.address_bar ,
                    self.font,
                    "black"))
                w = self.font.measure(self.address_bar)
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
        self.canvas = tkinter.Canvas(self.window, width=WIDTH, height=HEIGHT)
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

        self.chrome = Chrome(self)

    def handle_enter(self, e):
        self.chrome.enter()
        self.draw()

    def handle_key(self, e):
        if len(e.char) == 0: return
        if not (0x20 <= ord(e.char) < 0x7f): return
        self.chrome.keypress(e.char)
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
            self.chrome.click(e.x, e.y)
        else:
            tab_y = e.y - self.chrome.bottom
            self.active_tab.click(e.x, tab_y)
        self.draw()

    def handle_configure(self, e):
        self.width = e.width
        self.height = e.height
        if self.active_tab:
            self.active_tab.resize(e.width, e.height - self.chrome.bottom)
        self.draw()

    def draw(self):
        self.canvas.delete("all")
        self.active_tab.draw(self.canvas, self.chrome.bottom)
        for cmd in self.chrome.paint():
            cmd.execute(0, self.canvas)

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

    def load(self, url):
        self.history.append(url)
        self.url = url
        body = url.request()
        self.nodes = HTMLParser(body).parse()
        self.document = DocumentLayout(self.nodes)
        self.document.layout()
        self.display_list = []
        paint_tree(self.document, self.display_list)

    def go_back(self):
        if len(self.history) > 1:
            self.history.pop()
            back = self.history.pop()
            self.load(back)

    def draw(self, canvas, offset):
        for cmd in self.display_list:
            if cmd.rect.top > self.scroll + self.tab_height: continue
            if cmd.rect.bottom < self.scroll: continue
            cmd.execute(self.scroll - offset, canvas)
        
        self.draw_scrollbar()

    def draw_scrollbar(self):
        if not self.display_list:
            return
            
        content_height = self.display_list[-1].bottom + VSTEP
        if content_height <= self.tab_height:
            return
            
        scrollbar_width = 12
        scrollbar_height = (self.tab_height / content_height) * self.tab_height
        scrollbar_y = (self.scroll / content_height) * self.tab_height
        
        self.canvas.create_rectangle(
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
            self.document = DocumentLayout(self.nodes)
            self.document.layout()
            self.display_list = []
            paint_tree(self.document, self.display_list)

    def click(self, x, y):
        y += self.scroll

        objs = [obj for obj in tree_to_list(self.document, []) if obj.x <= x < obj.x + obj.width and obj.y <= y < obj.y + obj.height]

        if not objs: return
        elt = objs[-1].node
        while elt:
            if isinstance(elt, Text):
                pass
            elif elt.tag == "a" and "href" in elt.attributes:
                url = self.url.resolve(elt.attributes["href"])
                return self.load(url)
            elt = elt.parent

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

    def execute(self, scroll, canvas):
        canvas.create_text(
            self.left, self.top - scroll,
            text=self.text,
            font=self.font,
            anchor='nw',
            fill=self.color)
    
class DrawRect:
    def __init__(self, rect, color):
        # self.top = y1
        # self.left = x1
        # self.bottom = y2
        # self.right = x2
        self.rect = rect
        self.color = color

    def execute(self, scroll, canvas):
        canvas.create_rectangle(
            self.left, self.top - scroll,
            self.right, self.bottom - scroll,
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
        # self.display_list = []

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
                next = BlockLayout(child, self, previous)
                self.children.append(next)
                previous = next
            for child in self.children:
                child.layout()
            self.height = sum([child.height for child in self.children])
        else:
            self.new_line()
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
        elif self.node.children:
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
            self.open_tag(node.tag)
            for child in node.children:
                self.recurse(child)
            self.close_tag(node.tag)
    
    def word(self, node, word):
        font = get_font(self.weight, self.style, self.size)
        line = self.children[-1]
        previous_word = line.children[-1] if line.children else None
        text = TextLayout(node, word, line, previous_word)#, font, self.color)
        line.children.append(text)
        w = font.measure(word)
        if self.cursor_x + w > self.width:
            self.new_line()
        self.cursor_x += w + font.measure(" ")

    def new_line(self):
        self.cursor_x = 0
        last_line = self.children[-1] if self.children else None
        new_line = LineLayout(self.node, self, last_line)
        self.children.append(new_line)

    def paint(self):
        cmds = []
        if isinstance(self.node, Element) and self.node.tag == "pre":
            x2, y2 = self.x + self.width, self.y + self.height
            rect = DrawRect(self.x, self.y, x2, y2, "gray")
            cmds.append(rect)

        bgcolor = self.node.style.get("background-color", "transparent")

        if bgcolor != "transparent":
            rect = DrawRect(self.self_rect(), bgcolor)
            cmds.append(rect)

        return cmds

def paint_tree(layout_object, display_list):
        display_list.extend(layout_object.paint())

        for child in layout_object.children:
            paint_tree(child, display_list)

class DocumentLayout:
    def __init__(self, node):
        self.node = node
        self.parent = None
        self.children = []
        

    def layout(self):
        self.x = HSTEP
        self.y = VSTEP
        self.width = WIDTH - 2*HSTEP
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

    def paint(self):
        return []

class TextLayout:
    def __init__(self, node, word, parent, previous,):# font, color):
        self.node = node
        self.word = word
        self.parent = parent
        self.previous = previous
        self.children = []
        # self.font = font
        # self.color = color

    def layout(self):
        # weight = self.node.style["font-weight"]
        # style = self.node.style["font-style"]
        # if style == "normal": style = "roman"
        # size = int(float(self.node.style["font-size"][:-2]) * .75)
        # self.font = get_font(size, weight, style)

        self.width = self.font.measure(self.word)
        if self.previous:
            space = self.previous.font.measure(" ")
            self.x = self.previous.x + self.previous.width + space
        else:
            self.x = self.parent.x

        self.height = self.font.metrics("linespace")

    def paint(self):
        return [DrawText(self.x, self.y, self.word, self.font, self.color)]
        

if __name__ == '__main__':
    import sys
    Browser().new_tab(URL(sys.argv[1]))
    tkinter.mainloop()

