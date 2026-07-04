import os
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.abspath("."))

from app_desktop.window import ExtrapolationWindow

QApplication.instance() or QApplication([])
win = ExtrapolationWindow()
win._apply_language("zh")

schema_keyed_widgets = []
for obj in [win, *win.findChildren(QObject)]:
    key = obj.property("datalab_schema_key")
    if key:
        schema_keyed_widgets.append((key, obj))

print(f"Total schema keyed widgets: {len(schema_keyed_widgets)}")
types_found = {}
for key, w in schema_keyed_widgets:
    t = type(w).__name__
    if t not in types_found:
        types_found[t] = []
    types_found[t].append(key)

for t, keys in sorted(types_found.items()):
    print(f"{t}: {len(keys)}")
    for k in sorted(keys)[:5]:
        print(f"  {k}")
    if len(keys) > 5:
        print("  ...")

