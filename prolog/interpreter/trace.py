
class TraceWrapper():
    def __init__(self):
        from prolog.interpreter.translatedmain import getch, printmessage
        self.tracing = False
        self.write = printmessage
        self.getch = getch
        self.skiplevel = 0
        self.leash_options = {
                "call":None,"exit":None,"fail":None,"redo":None,"exception":None}

    def skip(self, depth, port):
        if self.skiplevel > 0:
            if self.skiplevel == depth and (port == "Exit" or port == "Fail"):
                self.skiplevel = 0
                return False
            return True
        else:
            return False
