"""
    mcedit2.qt

    Compatibility layer that presents PySide6 with the module layout MCEdit2 was written
    against (PySide 1.x / Qt 4): QtGui here is QtGui + QtWidgets merged, and classes that moved
    from QtGui to QtCore in Qt 5 are re-exported from QtGui.

    Import as `from mcedit2.qt import QtCore, QtGui`.
"""
from __future__ import absolute_import, division, print_function

from . import QtCore, QtGui, QtNetwork, QtOpenGL, QtUiTools  # noqa: F401
