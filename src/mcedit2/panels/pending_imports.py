"""
    pending_imports
"""

from mcedit2.qt import QtGui
import logging

log = logging.getLogger(__name__)

class PendingImportsWidget(QtGui.QWidget):
    def __init__(self):
        super(PendingImportsWidget, self).__init__()
        self.importsListWidget = QtGui.QListView()
        self.importsListModel = QtGui.QStandardItemModel()
        self.importsListWidget.setModel(self.importsListModel)
        self.importsListWidget.clicked.connect(self.listClicked)
        self.importsListWidget.doubleClicked.connect(self.listDoubleClicked)
