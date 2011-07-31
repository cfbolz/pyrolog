class TraceWrapper():
    def __init__(self):
        self.tracing = False
        self.write = None
        self.getch = None
        self.skiplevel = 0

    def skip(self, depth, port):
        if self.skiplevel > 0:
            if self.skiplevel == depth and (port == "Exit" or port == "Fail"):
                self.skiplevel = 0
                return False
            return True
        else:
            return False
