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
from __future__ import absolute_import
from builtins import range
from builtins import object

# Use qgis.PyQt so the plugin works under both PyQt5 (QGIS 3) and PyQt6 (QGIS 4).
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtWidgets import QAction, QApplication, QProgressBar
from qgis.PyQt.QtGui import QIcon, QColor

# QVariant was dropped from PyQt6. QGIS 4 expects QMetaType.Type.* when
# creating fields. Fall back to QVariant for QGIS 3 / PyQt5.
try:
    from qgis.PyQt.QtCore import QMetaType
    _FIELD_TYPE_INT = QMetaType.Type.Int
    _USE_QMETATYPE = True
except (ImportError, AttributeError):
    from qgis.PyQt.QtCore import QVariant
    _FIELD_TYPE_INT = QVariant.Int
    _USE_QMETATYPE = False

# Import the code for the dialog
from .disconnected_islands_modified_dialog import DisconnectedIslandsModifiedDialog
import os.path


from qgis.core import (
    Qgis,
    QgsProject,
    QgsVectorDataProvider,
    QgsField,
    QgsSymbol,
    QgsRendererCategory,
    QgsCategorizedSymbolRenderer,
    QgsGeometry,
)
from secrets import randbelow


def _align_left_vcenter():
    """Return AlignLeft|AlignVCenter, tolerating Qt5's flat and Qt6's scoped enums."""
    try:
        # PyQt6 / Qt 6 scoped enums
        return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    except AttributeError:
        # PyQt5 fallback
        return Qt.AlignLeft | Qt.AlignVCenter


class DisconnectedIslandsModified(object):
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')
        if locale:
            locale = locale[0:2]
        else:
            locale = ''
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'DisconnectedIslandsModified_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            # qVersion() string compare against '4.3.3' was a relic from the
            # Qt 4 / Qt 5 transition. Qt is well past that now, so just install.
            QCoreApplication.installTranslator(self.translator)

        # Create the dialog (after translation) and keep reference
        self.dlg = DisconnectedIslandsModifiedDialog()

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Disconnected Islands Modified')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'DisconnectedIslandsModified')
        self.toolbar.setObjectName(u'DisconnectedIslandsModified')

        self.checkNetworkXModule()

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('DisconnectedIslandsModified', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar."""

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToVectorMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        # Load the icon directly from disk. The old Qt resource system
        # (resources.py compiled with pyrcc5) is not supported by PyQt6,
        # so we no longer rely on ':/plugins/DisconnectedIslands/icon.png'.
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.add_action(
            icon_path,
            text=self.tr(u'Check for Disconnected Islands Modified'),
            callback=self.run,
            parent=self.iface.mainWindow())


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginVectorMenu(
                self.tr(u'&Disconnected Islands Modified'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

    def getAttributeIndex(self, lineLayer):
        """Find the attribute index, adding a new Int column, if necessary"""
        attrName = self.dlg.attributeNameEditBox.text()
        # TODO: If attrName is longer than 10, something fails later.  Move validation to a signal that checks storageType in the UI.
        if len(attrName) > 10 and lineLayer.storageType() == 'ESRI Shapefile':
            self.iface.messageBar().pushMessage("Error", "For ESRI Shapefiles, the maximum length of any attribute name is 10. Please choose a shorter attribute name.", level=Qgis.Critical)
            return -3
        attrIdx = lineLayer.dataProvider().fieldNameIndex(attrName)
        if attrIdx == -1:  # attribute doesn't exist, so create it
            caps = lineLayer.dataProvider().capabilities()
            if caps & QgsVectorDataProvider.AddAttributes:
                # QgsField accepts either a QVariant.Type (Qt5) or a
                # QMetaType.Type (Qt6) depending on the QGIS build.
                res = lineLayer.dataProvider().addAttributes(
                    [QgsField(attrName, _FIELD_TYPE_INT)]
                )
                attrIdx = lineLayer.dataProvider().fieldNameIndex(attrName)
                lineLayer.updateFields()
                if attrIdx == -1:
                    self.iface.messageBar().pushMessage("Error", "Failed to create attribute!", level=Qgis.Critical)
                    return -1
            else:
                self.iface.messageBar().pushMessage("Error", "Failed to add attribute!", level=Qgis.Critical)
                return -1
        else:
            # Maybe delete? Script doesnt work if overwrite is not checked
            if not self.dlg.overwriteCheckBox.isChecked():
                self.iface.messageBar().pushMessage("Error", "Attribute already exists - please tick Overwrite to confirm!", level=Qgis.Critical)
                return -2
        return attrIdx

    def checkNetworkXModule(self):
        """check for NetworkX module (especially for Mac) and prompt for install if missing."""

        try:
            import networkx  # noqa: F401
        except ImportError:
            self.iface.messageBar().pushMessage(
                "Error in plugin disconnected-islands-modified",
                "NetworkX module is required and missing. Please install it manually, e.g. 'pip install networkx' in the QGIS Python environment, then restart QGIS.",
                level=Qgis.Critical,
            )
            return -1
        return 0
    
    def distanceFromPointToLine(self, point0, point1, point2):
        import math
        x0=point0[0]
        x1=point1[0]
        x2=point2[0]
        y0=point0[1]
        y1=point1[1]
        y2=point2[1]
        
        #Proof: https://en.wikipedia.org/wiki/Distance_from_a_point_to_a_line
        upperPartEq = abs((y2-y1)*x0-(x2-x1)*y0+x2*y1-y2*x1)
        underPartEq = math.sqrt((y2-y1)**2+(x2-x1)**2)
        distance = upperPartEq/underPartEq
        return distance
        
    def distanceBetweenPoints(self, point1, point2):
        import math
        x1=point1[0]
        x2=point2[0]
        y1=point1[1]
        y2=point2[1]
        
        # Proof: https://en.wikipedia.org/wiki/Euclidean_distance
        distance = math.sqrt((x2-x1)**2+(y2-y1)**2)
        return distance

    # TODO: Let user decide the max tolerance for converging
    # This method WILL change the data, make sure to create, or use on Duplicate data
    def manipulateLineGeometryToStopAtPoints(self, lineLayer, pointLayer, maxDistanceForChange):
        from qgis.core import QgsGeometry, QgsPointXY
        
        lineLayer.beginEditCommand("Change to Lines that overlap, within a tolerance to converge and stop at point...")
        # Check each line against all points, with the euclidean distance formula
        # IF the line is close enough, change the closest point of the line, to have the cords of the stopping point
       
        # Make points once (its faster)
        points = []
        for pointFeat in pointLayer.getFeatures():
            pointGeom = pointFeat.geometry()
            QgsGeometry.convertToSingleType(pointGeom)
            point = pointGeom.asPoint()
            points.append(point)
        
        max_sqr_dist = maxDistanceForChange**2
        
        for lineFeat in lineLayer.getFeatures():
            lineGeom = lineFeat.geometry()
            QgsGeometry.convertToSingleType(lineGeom)       # QGIS 3.x seems to load single LineString as MultiLineString??
            line = lineGeom.asPolyline()
            if not line:
                continue
              
            for point in points:
                sqrDist, minDistPoint, afterVertex, _ = lineGeom.closestSegmentWithContext(point)
                
                if sqrDist <= max_sqr_dist:
                    firstPointDist = line[0].distance(point)
                    lastPointDist = line[1].distance(point)
                    if firstPointDist < lastPointDist:
                        line = [point] + line[afterVertex:]
                    else:
                        line = line[:afterVertex] + [point]
                    newGeom = QgsGeometry.fromPolylineXY(line)
                    lineLayer.changeGeometry(lineFeat.id(), newGeom)
                    break
        return 0

    def run(self):
        """Run method that performs all the real work"""

        layers = self.iface.mapCanvas().layers()
        layer_list = []
        self.dlg.layerRoadComboBox.clear()
        for layer in layers:
            layer_list.append(layer.name())
        self.dlg.layerRoadComboBox.addItems(layer_list)
        self.dlg.layerPointComboBox.addItems(layer_list)
        # TODO: Make the active layer the selected item in combo box  lineLayer = qgis.utils.iface.activeLayer()

        # TODO: Add signal to update toleranceSpinBox.suffix (Degrees) from layerRoadComboBox.crs.mapUnits when layer is selected:
        # my_UnitType = { 0: 'Meters', 1: 'Feet', 2: 'Degrees', 7: 'NauticalMiles', 8: 'Kilometers', 9: 'Yards', 10: 'Miles', 3: 'UnknownUnit'}
        # suffix = my_UnitType[lineLayer.crs().mapUnits()]

        # show the dialog
        self.dlg.show()
        # Run the dialog event loop. PyQt6 dropped the trailing underscore on exec_();
        # QDialog.exec() exists in both Qt5 (>=5.x) and Qt6.
        result = self.dlg.exec()
        # See if OK was pressed
        if result:
            if self.checkNetworkXModule() < 0:
                return -4
            import networkx as nx
            
            #Formerly (aLayer)
            lineName = self.dlg.layerRoadComboBox.currentText()
            # Point layer for converging line points
            pointName = self.dlg.layerPointComboBox.currentText()
            try:
                lineLayer = QgsProject.instance().mapLayersByName(lineName)[0]
                pointLayer = QgsProject.instance().mapLayersByName(pointName)[0]
            except Exception:
                self.iface.messageBar().pushMessage("Error", "Failed to load one of the layers!", level=Qgis.Critical)
                return -1

            try:
                previousEditingMode = True
                if not lineLayer.isEditable():
                    #Create duplication of the selected line layer
                    newLineLayer = self.iface.addVectorLayer(lineLayer.source(), lineLayer.name() + "_modfied", "ogr")
                    newLineLayer.startEditing()
                    previousEditingMode = False

                attrIdx = self.getAttributeIndex(newLineLayer)
                if attrIdx < 0:
                    return -3

                progressMessageBar = self.iface.messageBar().createMessage("Creating network graph...")
                progress = QProgressBar()
                progress.setMaximum(newLineLayer.featureCount())
                progress.setAlignment(_align_left_vcenter())
                progressMessageBar.layout().addWidget(progress)
                self.iface.messageBar().pushWidget(progressMessageBar, Qgis.Info)
                
                minDist = self.dlg.minDistSpinBox.value()
                # Manipulate the lines first
                self.manipulateLineGeometryToStopAtPoints(newLineLayer, pointLayer, minDist)
                
                G = nx.Graph()

                newLineLayer.beginEditCommand("Clear group attribute, create graph")
                # construct undirected graph
                tolerance = self.dlg.toleranceSpinBox.value()
                if tolerance == 0:
                    tolerance = 0.000001
                count = 0
                for feat in newLineLayer.getFeatures():
                    count += 1
                    progress.setValue(count)
                    done = newLineLayer.changeAttributeValue(feat.id(), attrIdx, -1)
                    geom = feat.geometry()
                    QgsGeometry.convertToSingleType(geom)       # QGIS 3.x seems to load single LineString as MultiLineString??
                    line = geom.asPolyline()

                    if self.dlg.startEndRadioButton.isChecked():
                        G.add_edges_from([((int(line[0][0]/tolerance), int(line[0][1]/tolerance)), (int(line[-1][0]/tolerance), int(line[-1][1]/tolerance)),
                                          {'fid': feat.id()})])     # first scale by tolerance, then convert to int.  Before doing this, there were problems (in NetworkX v1) with floats not equating, thus creating disconnects that weren't there.
                    elif self.dlg.allRadioButton.isChecked():
                        for i in range(len(line)-1):
                            G.add_edges_from([((int(line[i][0]/tolerance), int(line[i][1]/tolerance)), (int(line[i+1][0]/tolerance), int(line[i+1][1]/tolerance)),
                                              {'fid': feat.id()})])     # first scale by tolerance, then convert to int.  Before doing this, there were problems (in NetworkX v1) with floats not equating, thus creating disconnects that weren't there.
                    if count % 100 == 0:
                        QApplication.processEvents()      # keep the UI responsive, every 100 features
                        # TODO: check to see if Esc pressed

                newLineLayer.endEditCommand()

                self.iface.messageBar().pushMessage("Finding connected subgraphs, please wait...",  level=Qgis.Warning)     # WARNING - to highlight the next stage, where we cannot show progress
                QApplication.processEvents()
                connected_components = list(G.subgraph(c) for c in nx.connected_components(G))    # this takes a long time.  TODO: how to show progress?
                self.iface.messageBar().pushMessage("Updating group attribute...",  level=Qgis.Info)
                QApplication.processEvents()

                # gather edges and components to which they belong
                fid_comp = {}
                for i, graph in enumerate(connected_components):
                    for edge in graph.edges(data=True):
                        fid_comp[edge[2].get('fid', None)] = i

                newLineLayer.beginEditCommand("Update group attribute")
                for (fid, group) in fid_comp.items():
                    done = newLineLayer.changeAttributeValue(fid, attrIdx, group)
                newLineLayer.endEditCommand()

                groups = list(set(fid_comp.values()))
                if self.dlg.stylingCheckBox.isChecked():
                    newLineLayer.beginEditCommand("Update layer styling")
                    categories = []
                    firstCat = True
                    for cat in groups:
                        symbol = QgsSymbol.defaultSymbol(newLineLayer.geometryType())
                        symbol.setColor(QColor(randbelow(256), randbelow(256), randbelow(256))) # nosec
                        if firstCat:
                            firstCat = False
                        else:
                            symbol.setWidth(symbol.width()*5)
                        category = QgsRendererCategory(cat, symbol, "%d" % cat)
                        categories.append(category)

                    field = self.dlg.attributeNameEditBox.text()
                    renderer = QgsCategorizedSymbolRenderer(field, categories)
                    newLineLayer.setRenderer(renderer)

                    newLineLayer.triggerRepaint()
                    newLineLayer.endEditCommand()

                self.iface.messageBar().clearWidgets()
                self.iface.messageBar().pushMessage("Found main network and %d disconnected islands modified in layer %s" % (len(groups)-1, newLineLayer.name()),  level=Qgis.Success)

                newLineLayer.commitChanges()

            except Exception as e:
                self.iface.messageBar().pushMessage("Error", "Exception caught: %s.  Please report an issue to the author of the plugin." % repr(e), level=Qgis.Critical)
