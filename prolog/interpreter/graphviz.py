
def _dot(self, seen):
    if self in seen:
        return
    seen.add(self)
    yield '%s [label="%s", shape=box]' % (id(self), repr(self)[:50])
    for key, value in self.__dict__.iteritems():
        if hasattr(value, "_dot"):
            yield "%s -> %s [label=%s]" % (id(self), id(value), key)
            for line in value._dot(seen):
                yield line

def view(*objects, **names):
    from dotviewer import graphclient
    content = ["digraph G{"]
    seen = set()
    for obj in list(objects) + names.values():
        content.extend(obj._dot(seen))
    for key, value in names.items():
        content.append("%s -> %s" % (key, id(value)))
    content.append("}")
    p = py.test.ensuretemp("prolog").join("temp.dot")
    p.write("\n".join(content))
    graphclient.display_dot_file(str(p))

