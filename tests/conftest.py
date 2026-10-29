import os

# A shell launched from the frozen app (it spawns terminals) inherits TCL_LIBRARY and
# TK_LIBRARY pointing into that app's temporary PyInstaller extraction dir. The dir is
# not a complete Tk install, so Tk() fails intermittently; use the interpreter's own.
for _var in ("TCL_LIBRARY", "TK_LIBRARY"):
    if "_MEI" in os.environ.get(_var, ""):
        del os.environ[_var]
