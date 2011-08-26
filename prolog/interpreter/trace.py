
class TraceWrapper():
    def __init__(self):
        from prolog.interpreter.translatedmain import getch, printmessage
        self.tracing = False
        self.write = printmessage
        self.getch = getch
        self.skip_from_level = 0
        self.leash_options = {'all':None}
        self.show_info = True

    def add_leash_option(self, option):
        if not 'all' in self.leash_options:
            if option == 'all':
                self.leash_options.clear()
            self.leash_options[option] = None
        l = list(self.leash_options)
        l.sort()
        if l == ['call','exception','exit','fail','redo']:
            self.add_leash_option('all')

    def remove_leash_option(self, option):
        if option == "all":
            self.leash_options.clear()
            return
        elif 'all' in self.leash_options:
            self.leash_options.clear()
            self.leash_options = {'call':None,'exception':None,'exit':None,'fail':None,'redo':None}

        if option in self.leash_options:
            del self.leash_options[option]

    def is_leashed(self, port):
        if 'all' in self.leash_options or port in self.leash_options:
            return True
        return False

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
