class URL:
    def __init__(self, url):
        self.scheme, url = url.split('://', 1)
        assert self.scheme == 'http'
        
        self.host, url = url.split('/', 1)
        self.path = '/' + url

        print(f"protocol is: {self.scheme}, host is: {self.host}, path is: {self.path}")

    def request(self):
        pass

url = URL("http://example.org/index.html")