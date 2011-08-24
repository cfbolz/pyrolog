
class TraceWrapper():
    def __init__(self):
        from prolog.interpreter.translatedmain import getch, printmessage
        self.tracing = False
        self.write = printmessage
        self.getch = getch
        self.skip_from_level = 0
        self.leash_options = {
                "call":None,"exit":None,"fail":None,"redo":None,"exception":None}
        self.show_info = True

    def skip(self, depth, port):
        if self.skip_from_level > 0:
            if self.skip_from_level == depth and (port == "Exit" or port == "Fail"):
                self.skip_from_level = 0
                return False
            return True
        else:
            return False

    def info(self, string):
        if self.show_info:
            self.write(string)
