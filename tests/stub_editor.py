"""Stand-in editor: appends its arguments to the file named by $STUB_LOG."""
import os
import sys

with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as f:
    f.write(" ".join(sys.argv[1:]) + "\n")
