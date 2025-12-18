import socket

class URL:
    def __init__(self, url):
        if not url.endswith('/'):
            url += '/'
        self.scheme, url = url.split('://', 1)
        assert self.scheme == 'http'
        
        self.host, url = url.split('/', 1)
        self.path = '/' + url

        print(f"protocol is: {self.scheme}, host is: {self.host}, path is: {self.path}")

    def request(self):
        s = socket.socket()

        s.connect((self.host, 80))
        
        request = f"GET {self.path} HTTP/1.0\r\n"
        request += f"HOST: {self.host}\r\n"
        request += "\r\n"
        s.send(request.encode("utf8"))

        response = s.makefile("r", encoding="utf8", newline="\r\n")

        statusline = response.readline()
        version, status, explanation = statusline.split(" ", 2)

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
    
def show(body):
    in_tag = False
    for c in body:
        if c == "<":
            in_tag = True
        elif c == ">":
            in_tag = False
        elif not in_tag:
            print(c, end="")

def load(url):
    body = url.request()
    show(body)

if __name__ == "__main__":
    import sys
    load(URL(sys.argv[1]))