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
        self.display_list = Layout(self.nodes, self.width).display_list
        self.draw()


    def draw(self):
        self.canvas.delete("all")
        for x, y, c, font in self.display_list:
            if y > self.scroll + self.height: continue
            if y + VSTEP < self.scroll: continue
            self.canvas.create_text(x, y - self.scroll, text=c, anchor="nw", font=font)
        
        self.draw_scrollbar()

    def draw_scrollbar(self):
        if not self.display_list:
            return
            
        content_height = self.display_list[-1][1] + VSTEP
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
        if not self.display_list:
            return
        max_y = self.display_list[-1][1]
        if self.scroll + self.height < max_y:
            self.scroll += SCROLL_STEP
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
            max_y = self.display_list[-1][1]
            if self.scroll + self.height < max_y:
                self.scroll += SCROLL_STEP
                self.draw()

    def on_configure(self, e):
        self.width = e.width
        self.height = e.height
        if hasattr(self, 'nodes'):
            self.display_list = Layout(self.nodes, self.width).display_list
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

class Layout:
    def __init__(self, tree, width):
        self.display_list = []
        self.cursor_x = HSTEP
        self.cursor_y = VSTEP
        self.weight = "normal"
        self.style = "roman"
        self.width = width
        self.size = 12
        self.line = []

        self.recurse(tree)
        self.flush()

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

        if self.cursor_x + w > self.width - HSTEP:
            self.flush()

        self.line.append((self.cursor_x, word, font))
        self.cursor_x += w + font.measure(" ")

    def flush(self):
        if not self.line: return
        metrics = [font.metrics() for x, word, font in self.line]
        max_ascent = max([metric["ascent"] for metric in metrics])
        baseline = self.cursor_y + 1.25 * max_ascent
        for x, word, font in self.line:
            y = baseline - font.metrics("ascent")
            self.display_list.append((x, y, word, font))
        max_descent = max([metric["descent"] for metric in metrics])
        self.cursor_y = baseline + 1.25 * max_descent

        self.cursor_x = HSTEP
        self.line = []

if __name__ == '__main__':
    import sys
    Browser().load(URL(sys.argv[1]))
    tkinter.mainloop()

