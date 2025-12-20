import tkinter
from browser import URL, lex

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
        self.text = lex(body)
        self.display_list = layout(self.text, self.width)
        self.draw()

    def draw(self):
        self.canvas.delete("all")
        for x, y, c in self.display_list:
            if y > self.scroll + self.height: continue
            if y + VSTEP < self.scroll: continue
            self.canvas.create_text(x, y - self.scroll, text=c)

    def scrolldown(self, e):
        print(self.display_list[-1][1], self.scroll + self.height)
        if self.scroll + self.height < self.display_list[-1][1]:
            self.scroll += SCROLL_STEP
            self.draw()

    def scrollup(self, e):
        if not self.scroll <= 0:
            self.scroll -= SCROLL_STEP
            self.draw()

    def mousewheel(self, e):
        if e.num == 4 or e.delta > 0:
            if not self.scroll <=0:
                self.scroll -= SCROLL_STEP
                self.draw()
        elif e.num == 5 or e.delta < 0:
            if self.scroll + self.height < self.display_list[-1][1]:
                self.scroll += SCROLL_STEP
                self.draw()

    def on_configure(self, e):
        self.width = e.width
        self.height = e.height
        if hasattr(self, 'text'):
            self.display_list = layout(self.text, self.width)
            self.draw()

def layout(text, width):
    display_list = []
    cursor_x, cursor_y = HSTEP, VSTEP
    for c in text:
        if c == '\n':
            cursor_y += VSTEP * 2
            cursor_x = HSTEP
            continue

        display_list.append((cursor_x, cursor_y, c))   
        cursor_x += HSTEP
        if cursor_x >= width - HSTEP:
            cursor_y += VSTEP
            cursor_x = HSTEP

    return display_list

if __name__ == '__main__':
    import sys
    Browser().load(URL(sys.argv[1]))
    tkinter.mainloop()

