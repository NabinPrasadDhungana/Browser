import socket
import ssl

class URL:
    def __init__(self, url):
        self.scheme, url = url.split('://', 1)
        if self.scheme not in ('http', 'https'):
            raise ValueError(f"Unsupported scheme: {self.scheme}")

        if self.scheme == 'http':
            self.port = 80
        else:
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

    def request(self):
        s = socket.socket()

        s.connect((self.host, self.port))

        if self.scheme == 'https':
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)
        
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