import os

try:
    with open(os.path.join(os.path.dirname(__file__), "VERSION")) as f:
        VERSION = f.read().strip()
except OSError:
    VERSION = "?"
