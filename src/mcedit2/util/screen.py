"""
    screen
"""

import logging
from mcedit2.qt import QtGui, QtCore

log = logging.getLogger(__name__)

def centerWidgetInScreen(widget, resize=None):
    """

    :param widget:
    :type widget:
    :param resize: Fraction of screen width/height to resize widget to
    :type resize:
    :return:
    :rtype:
    """
    parent = widget.parent()
    if parent is not None:
        screen = parent.screen()
    else:
        screen = None
    if screen is None:
        screen = QtGui.QApplication.primaryScreen()
    screenGeometry = screen.availableGeometry()
    w = screenGeometry.width()
    h = screenGeometry.height()
    r = widget.geometry()
    if resize is not None:
        w2 = w * resize * 0.5
        h2 = h * resize * 0.5
    else:
        w2 = r.width() * 0.5
        h2 = r.height() * 0.5
    r = QtCore.QRect(int(screenGeometry.x() + w * 0.5 - w2),
                     int(screenGeometry.y() + h * 0.5 - h2),
                     int(2 * w2),
                     int(2 * h2))

    widget.setGeometry(r)
