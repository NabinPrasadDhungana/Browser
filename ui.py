import tkinter
from browser import URL, HTMLParser
import tkinter.font
from browser import Text, Element

WIDTH = 800
HEIGHT = 600 

HSTEP = 13
VSTEP = 18
SCROLL_STEP = 35

class Browser:
    def __init__(self):
        self.window = tkinter.Tk()
        self.width = WIDTH
        self.height = HEIGHT
        self.canvas = tkinter.Canvas(self.window, width=WIDTH, height=HEIGHT)
        self.canvas.pack(fill=tkinter.BOTH , expand=1)
        self.scroll = 0
        self.window.bind('<Down>', self.scrolldown)
        self.window.bind('<Up>', self.scrollup)
        self.window.bind('<MouseWheel>', self.mousewheel)
        self.window.bind('<Button-4>', self.mousewheel)
        self.window.bind('<Button-5>', self.mousewheel)
        self.window.bind('<Configure>', self.on_configure)

    def load(self, url):
        body = url.request()
        self.nodes = HTMLParser(body).parse()
        self.document = DocumentLayout(self.nodes, width=self.width)
        self.document.layout()
        self.display_list = []
        paint_tree(self.document, self.display_list)
        self.draw()


    def draw(self):
        self.canvas.delete("all")
        for cmd in self.display_list:
            if cmd.top > self.scroll + HEIGHT: continue
            if cmd.bottom < self.scroll: continue
            cmd.execute(self.scroll, self.canvas)
        
        self.draw_scrollbar()

    def draw_scrollbar(self):
        if not self.display_list:
            return
            
        content_height = self.display_list[-1].bottom + VSTEP
        if content_height <= self.height:
            return
            
        scrollbar_width = 12
        scrollbar_height = (self.height / content_height) * self.height
        scrollbar_y = (self.scroll / content_height) * self.height
        
        self.canvas.create_rectangle(
            self.width - scrollbar_width, scrollbar_y,
            self.width, scrollbar_y + scrollbar_height,
            fill="blue", outline=""
        )

    def scrolldown(self, e):
        max_y = max(self.document.height + 2*VSTEP - HEIGHT, 0)
        self.scroll = min(self.scroll + SCROLL_STEP, max_y)
        self.draw()

    def scrollup(self, e):
        if not self.scroll <= 0:
            self.scroll -= SCROLL_STEP
            self.draw()

    def mousewheel(self, e):
        if not self.display_list:
            return
        if e.num == 4 or e.delta > 0:
            if not self.scroll <=0:
                self.scroll -= SCROLL_STEP
                self.draw()
        elif e.num == 5 or e.delta < 0:
            max_y = self.display_list[-1].bottom
            if self.scroll + self.height < max_y:
                self.scroll += SCROLL_STEP
                self.draw()

    def on_configure(self, e):
        self.width = e.width
        self.height = e.height
        if hasattr(self, 'nodes'):
            self.document = DocumentLayout(self.nodes, width=self.width)
            self.document.layout()
            self.display_list = []
            paint_tree(self.document, self.display_list)
            self.draw()

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
    def __init__(self, x1, y1, text, font):
        self.top = y1
        self.left = x1
        self.text = text
        self.font = font
        self.bottom = y1 + font.metrics("linespace")

    def execute(self, scroll, canvas):
        canvas.create_text(
            self.left, self.top - scroll,
            text=self.text,
            font=self.font,
            anchor='nw')
    
class DrawRect:
    def __init__(self, x1, y1, x2, y2, color):
        self.top = y1
        self.left = x1
        self.bottom = y2
        self.right = x2
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
        self.display_list = []

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
            self.cursor_x = 0
            self.cursor_y = 0
            self.weight = "normal"
            self.style = "roman"
            self.size = 12

            self.line = []
            self.recurse(self.node)
            self.flush()
            self.height = self.cursor_y

    def layout_intermediate(self):
        previous = None
        for child in self.node.children:
            next = BlockLayout(child, self, previous)
            self.children.append(next)
            previous = next

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
            self.flush()

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
            self.flush()
            self.cursor_y += VSTEP

    def recurse(self, tree):
        if isinstance(tree, Text):
            for word in tree.text.split():
                self.word(word)
        else:
            self.open_tag(tree.tag)
            for child in tree.children:
                self.recurse(child)
            self.close_tag(tree.tag)
    
    def word(self, word):
        font = get_font(self.weight, self.style, self.size)
        w = font.measure(word)
                
        if word == '\n':
            self.flush()
            self.cursor_y += VSTEP
            return

        if self.cursor_x + w > self.width:
            self.flush()

        self.line.append((self.cursor_x, word, font))
        self.cursor_x += w + font.measure(" ")

    def flush(self):
        if not self.line: return
        metrics = [font.metrics() for x, word, font in self.line]
        max_ascent = max([metric["ascent"] for metric in metrics])
        baseline = self.cursor_y + 1.25 * max_ascent
        for rel_x, word, font in self.line:
            x = self.x + rel_x
            y = self.y + baseline - font.metrics("ascent")
            self.display_list.append((x, y, word, font))
        max_descent = max([metric["descent"] for metric in metrics])
        self.cursor_y = baseline + 1.25 * max_descent

        self.cursor_x = 0
        self.line = []

    def paint(self):
        cmds = []
        if isinstance(self.node, Element) and self.node.tag == "pre":
            x2, y2 = self.x + self.width, self.y + self.height
            rect = DrawRect(self.x, self.y, x2, y2, "gray")
            cmds.append(rect)

        if self.layout_mode() == "inline":
            for x, y, word, font in self.display_list:
                cmds.append(DrawText(x, y, word, font))
        return cmds

def paint_tree(layout_object, display_list):
        display_list.extend(layout_object.paint())

        for child in layout_object.children:
            paint_tree(child, display_list)

class DocumentLayout:
    def __init__(self, node, width=WIDTH):
        self.node = node
        self.parent = None
        self.children = []
        self.x = HSTEP
        self.y = VSTEP
        self.width = width - 2*HSTEP

    def layout(self):
        child = BlockLayout(self.node, self, None)
        self.children.append(child)
        child.layout()
        self.display_list = child.display_list

    def paint(self):
        return []

if __name__ == '__main__':
    import sys
    Browser().load(URL(sys.argv[1]))
    tkinter.mainloop()

