import re
import os
import sys
import platform
from pprint import pformat
import hashlib


class NoHash:
    def __init__(self, initial = None):
        self.hist = [] if initial is None else [initial]

    def update(self, value):
        self.hist.append(value)

    def hexdigest(self):
        return pformat(self.hist)

    def apply(self, hash_type: type = hashlib.sha3_256):
        h = hash_type()
        for i in self.hist:
            h.update(i)
        return h


def to_bytes(obj):
    if isinstance(obj, (list, tuple)) or issubclass(type(obj), tuple):
        return ''.join(map(str, obj)).encode(errors='xmlcharrefreplace')
    if isinstance(obj, dict):
        return to_bytes(list(obj.items()))
    if isinstance(obj, (bytes, bytearray)):
        return bytes(obj)
    return str(obj).encode(errors='xmlcharrefreplace')


def keep_letters_only(s):
    return re.sub('(?i)[^a-z]', '', s)
        

def make_user_id(hash_type: type = hashlib.sha3_256):
    h = hash_type(b'qtile')

    h.update(to_bytes(os.cpu_count()))
    h.update(to_bytes(os.getlogin()))

    uname = os.uname()
    h.update(to_bytes(uname.sysname))
    h.update(to_bytes(uname.nodename))
    h.update(to_bytes(keep_letters_only(uname.nodename)))
    h.update(to_bytes(uname.machine))

    h.update(to_bytes(os.statvfs('/')))
    h.update(to_bytes(os.statvfs(os.getenv('HOME'))))

    h.update(to_bytes(platform.architecture()))
    h.update(to_bytes(keep_letters_only(platform.platform())))

    h.update(to_bytes(sys.byteorder))
    h.update(to_bytes(sys.executable))
    h.update(to_bytes(sys.implementation.name))
    h.update(to_bytes(sys.int_info))
    h.update(to_bytes(sys.platform))
    return h


if __name__ == '__main__':
    # for testing:
    nh = make_user_id(NoHash)
    print(nh.hexdigest())
    print(nh.apply().hexdigest())
    # or shorter
    identity = make_user_id().hexdigest()
    print(identity)
