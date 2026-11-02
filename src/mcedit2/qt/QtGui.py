"""
QtGui + QtWidgets merged (Qt 4 layout), plus model classes that moved to QtCore in Qt 5.
"""
from PySide6.QtGui import *  # noqa: F401,F403
from PySide6.QtWidgets import *  # noqa: F401,F403
from PySide6 import QtCore as _QtCore

for _name in ("QSortFilterProxyModel", "QStringListModel", "QItemSelectionModel", "QItemSelection",
              "QAbstractProxyModel", "QIdentityProxyModel", "QItemSelectionRange"):
    globals()[_name] = getattr(_QtCore, _name)
del _name


def __getattr__(name):
    # `QtGui.qApp` existed in Qt 4 as a global; Qt 6 only has QApplication.instance()
    if name == "qApp":
        return QApplication.instance()  # noqa: F405
    raise AttributeError("module %r has no attribute %r" % (__name__, name))
