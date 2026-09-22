"""Terminal-independent events and console interface, following pyrepl."""


class Event(object):
    # Text events contain UTF-8 byte strings.
    def __init__(self, evt, data=''):
        self.evt = evt
        self.data = data


class Console(object):
    width = 80
    height = 24

    def prepare(self):
        raise NotImplementedError

    def restore(self):
        raise NotImplementedError

    def get_event(self):
        raise NotImplementedError

    def refresh(self, screen, cxy):
        raise NotImplementedError

    def finish(self):
        raise NotImplementedError
