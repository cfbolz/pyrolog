
class LRUHistogram(object):
    def __init__(self, n=5):
        self.n = n
        self.counts = [0] * n
        self.objects = [None] * n
        self.usage = [n - 1] * n

    def see(self, obj):
        try:
            i = self.objects.index(obj)
        except ValueError:
            # use either an empty place, or evict an object
            i = self.usage.index(self.n - 1)
            self.objects[i] = obj
        self.counts[i] += 1
        oldusage = self.usage[i]
        for j in range(self.n):
            if -1 < self.usage[j] < oldusage:
                self.usage[j] += 1
        self.usage[i] = 0
        return self.counts[i]

    def get_usage(self, obj):
        return self.counts[self.objects.index(obj)]
