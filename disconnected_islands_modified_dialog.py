# -*- coding: utf-8 -*-
"""
/***************************************************************************
 DisconnectedIslandsModified
                                 A QGIS plugin
 Finds disconnected "islands" in a road network layer, so that a routing tool will work between all nodes. A tolerance field allows for imperfect topology.
                             -------------------
        begin                : 2026-11-02
        copyright            : (C) 2026 by Magnus Jespersgaard / OG Author Peter Smythe - AfriGIS
        email                : ffmaje@forsyningen.dk
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os

# qgis.PyQt is the QGIS-provided shim that points at PyQt5 in QGIS 3
# and PyQt6 in QGIS 4, so this single import works on both.
from qgis.PyQt import uic
from qgis.PyQt import QtWidgets

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'disconnected_islands_modified_dialog_base.ui'))


class DisconnectedIslandsModifiedDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        """Constructor."""
        super(DisconnectedIslandsModifiedDialog, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots.
        self.setupUi(self)
