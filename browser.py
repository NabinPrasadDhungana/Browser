import socket
import ssl
import os

class URL:
    def __init__(self, url):
        try:
            if url == "about:blank":
                self.scheme = "about"
                self.path = "blank"
                return

            if url.startswith("data:"):
                self.scheme, url = url.split(":", 1)
                self.path = url
                return

            self.scheme, url = url.split('://', 1)
            if self.scheme not in ('http', 'https', 'file'):
                raise ValueError(f"Unsupported scheme: {self.scheme}")

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

    def request(self):
        if self.scheme == "file":
            if os.path.isdir(self.path):
                return "\n".join(os.listdir(self.path))
            with open(self.path, "r", encoding="utf8") as f:
                return f.read()
        
        if self.scheme == "data":
            return self.path.split(",", 1)[1]

        if self.scheme == "about":
            return ""

        s = socket.socket()

        s.connect((self.host, self.port))

        if self.scheme == 'https':
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)
        
        request = f"GET {self.path} HTTP/1.0\r\n"
        request += f"HOST: {self.host}\r\n"
        request += "Connection: close\r\n"
        request += "User-Agent: Nabin\r\n"
        request += "\r\n"
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
    
def lex(body):
    in_tag = False
    text = ""
    for c in body:
        if c == "<":
            in_tag = True
        elif c == ">":
            in_tag = False
        elif not in_tag:
            text += c
    return text

def load(url):
    body = url.request()
    lex(body)

if __name__ == "__main__":
    import sys
    load(URL(sys.argv[1]))