# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Threshold3
                                 A QGIS plugin
 Creates a colored overlay using user-defined thresholds.
                              -------------------
        begin                : 2017-08-16
        git sha              : $Format:%H$
        copyright            : (C) 2017 by Ryan Joseph Constantino
        email                : ryan.constantino93@gmail.com
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
from qgis.core import *
from qgis.gui import *
from PyQt4.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, QTimer, QThread, Qt
from PyQt4.QtGui import *
# Initialize Qt resources from file resources.py
import resources
# Import the code for the dialog
from threshold_3_dialog import Threshold3Dialog
import os.path
import math
from worker import Worker

class Threshold3:
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
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'Threshold3_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Threshold3')

        self.color_picker = QColorDialog()
        self.color_picker.setOption(QColorDialog.ShowAlphaChannel, on=True)

        self.t_0_COLOR = QColor(0, 0, 255)
        self.t_1_COLOR = QColor(0, 255 ,0)
        self.t_2_COLOR = QColor(255, 0, 0)
        self.CLEAR = QColor(255, 255, 255, 0)

        self.layer = None
        self.fcn = None
        self.shader = None
        self.renderer = None
        self.MIN = float("inf")
        self.MAX = float("-inf")

        self.render_debounce_timer = QTimer()
        self.render_debounce_timer.timeout.connect(self.render)
        self.render_debounce_timer.setSingleShot(True)

        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'Threshold3')
        self.toolbar.setObjectName(u'Threshold3')

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
        return QCoreApplication.translate('Threshold3', message)

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
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        # Create the dialog (after translation) and keep reference
        self.dlg = Threshold3Dialog()

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
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/Threshold3/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(
                u'Add colored layers according to user-defined thresholds.'),
            callback=self.run,
            parent=self.iface.mainWindow())

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Threshold3'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

    def run(self):
        """Run method that performs all the real work"""
        # show the dialog
        self.dlg.show()
        self.toggle_widgets(False)

        self.layer = self.iface.activeLayer()
        if self.layer is None:
            self.dlg.header.setText("No layer selected.")
            self.dlg.header.setStyleSheet("color: #000000;")
        else:
            if isinstance(self.layer, QgsRasterLayer) is False:
                raise TypeError("Expected QgsRasterLayer, got {}".format(type(self.layer)))
            self.dlg.header.setText("") # Active layer 
            if not hasattr(self.layer, "hasFilter"):
                self.fcn = QgsColorRampShader()
                self.fcn.setColorRampType(QgsColorRampShader.INTERPOLATED)
                self.layer.hasFilter = True
            else:
                self.toggle_widgets(True)
        if self.MAX == float("-inf"):
            self.startWorker(self.iface, self.layer)
        # Run the dialog event loop

        self.set_values(True)

        result = self.dlg.exec_()

        self.dlg.threshold_0_button.clicked.disconnect()
        self.dlg.threshold_1_button.clicked.disconnect()
        self.dlg.threshold_2_button.clicked.disconnect()
        
        # See if OK was pressed
        if result:
            print("OK was pressed.")
            # Do something useful here - delete the line containing pass and
            # substitute with your code.
        else:
            print("CANCEL was pressed.")

    def set_values(self, connect = False):        

        self.dlg.precision_spinbox.setMinimum(1)
        self.dlg.precision_spinbox.setMaximum(5)
        self.dlg.precision_spinbox.setValue(2)
        if connect: self.dlg.precision_spinbox.valueChanged.connect(lambda: self.on_changed(None, "precision"))

        self.dlg.doubleSpinBox_b.setSingleStep(0.01)
        self.dlg.doubleSpinBox_1.setSingleStep(0.01)
        self.dlg.doubleSpinBox_2.setSingleStep(0.01)
        self.dlg.doubleSpinBox_3.setSingleStep(0.01)

        self.dlg.doubleSpinBox_b.setDecimals(5)
        self.dlg.doubleSpinBox_1.setDecimals(5)
        self.dlg.doubleSpinBox_2.setDecimals(5)
        self.dlg.doubleSpinBox_3.setDecimals(5)

        self.dlg.doubleSpinBox_b.setMinimum(0)
        self.dlg.doubleSpinBox_1.setMinimum(self.MIN)
        self.dlg.doubleSpinBox_2.setMinimum(self.MIN)
        self.dlg.doubleSpinBox_3.setMinimum(self.MIN)

        self.dlg.doubleSpinBox_b.setMaximum(abs(self.MAX - self.MIN))
        self.dlg.doubleSpinBox_1.setMaximum(self.MAX)
        self.dlg.doubleSpinBox_2.setMaximum(self.MAX)
        self.dlg.doubleSpinBox_3.setMaximum(self.MAX)

        if connect:
            self.dlg.doubleSpinBox_b.valueChanged.connect(lambda: self.on_changed(None, "box"))
            self.dlg.doubleSpinBox_1.valueChanged.connect(lambda: self.on_changed(0, "box"))
            self.dlg.doubleSpinBox_2.valueChanged.connect(lambda: self.on_changed(1, "box"))
            self.dlg.doubleSpinBox_3.valueChanged.connect(lambda: self.on_changed(2, "box"))

        self.dlg.alpha_0_slider.setMinimum(0)
        self.dlg.alpha_0_slider.setMaximum(255)
        self.dlg.alpha_1_slider.setMinimum(0)
        self.dlg.alpha_1_slider.setMaximum(255)
        self.dlg.alpha_2_slider.setMinimum(0)
        self.dlg.alpha_2_slider.setMaximum(255)

        self.dlg.alpha_0_slider.setValue(255)
        self.dlg.alpha_1_slider.setValue(255)
        self.dlg.alpha_2_slider.setValue(255)

        if connect:
            self.dlg.alpha_0_slider.valueChanged.connect(lambda: self.on_changed(None))
            self.dlg.alpha_1_slider.valueChanged.connect(lambda: self.on_changed(None))
            self.dlg.alpha_2_slider.valueChanged.connect(lambda: self.on_changed(None))

        self.dlg.base_slider.setMinimum(0)
        self.dlg.base_slider.setMaximum(abs(self.MAX - self.MIN))
        self.dlg.base_slider.setValue(0)

        self.dlg.threshold_0_slider.setMinimum(self.MIN)
        self.dlg.threshold_0_slider.setMaximum(self.MAX)
        self.dlg.threshold_1_slider.setMinimum(self.MIN)
        self.dlg.threshold_1_slider.setMaximum(self.MAX)
        self.dlg.threshold_2_slider.setMinimum(self.MIN)
        self.dlg.threshold_2_slider.setMaximum(self.MAX)

        if connect:
            self.dlg.base_slider.valueChanged.connect(lambda: self.on_changed("base"))
            self.dlg.threshold_0_slider.valueChanged.connect(lambda: self.on_changed(0))
            self.dlg.threshold_1_slider.valueChanged.connect(lambda: self.on_changed(1))
            self.dlg.threshold_2_slider.valueChanged.connect(lambda: self.on_changed(2))

        # Turn it on and off again... I don't know why but
        # connecting and disconnecting these listeners fixes
        # the double popup problem.
        
        self.dlg.threshold_0_button.clicked.connect(lambda: self.on_color_button_clicked(0))
        self.dlg.threshold_1_button.clicked.connect(lambda: self.on_color_button_clicked(1))
        self.dlg.threshold_2_button.clicked.connect(lambda: self.on_color_button_clicked(2))
        self.dlg.threshold_0_button.clicked.disconnect()
        self.dlg.threshold_1_button.clicked.disconnect()
        self.dlg.threshold_2_button.clicked.disconnect()
        self.dlg.threshold_0_button.clicked.connect(lambda: self.on_color_button_clicked(0))
        self.dlg.threshold_1_button.clicked.connect(lambda: self.on_color_button_clicked(1))
        self.dlg.threshold_2_button.clicked.connect(lambda: self.on_color_button_clicked(2))

        self.dlg.threshold_0_color_box.setStyleSheet("background-color: {}".format(self.t_0_COLOR.name()))
        self.dlg.threshold_1_color_box.setStyleSheet("background-color: {}".format(self.t_1_COLOR.name()))
        self.dlg.threshold_2_color_box.setStyleSheet("background-color: {}".format(self.t_2_COLOR.name()))
        pass
    
    def render(self):
        t_0 = self.dlg.threshold_0_slider.value()
        t_1 = self.dlg.threshold_1_slider.value()
        t_2 = self.dlg.threshold_2_slider.value()
        lst = [
            QgsColorRampShader.ColorRampItem(t_0 - self.dlg.base_slider.value(), self.CLEAR),
            QgsColorRampShader.ColorRampItem(t_0, self.t_0_COLOR),
            QgsColorRampShader.ColorRampItem(t_1, self.t_1_COLOR),
            QgsColorRampShader.ColorRampItem(t_2, self.t_2_COLOR),
            ]
        self.fcn = QgsColorRampShader()
        self.fcn.setColorRampType(QgsColorRampShader.INTERPOLATED) 
        self.fcn.setColorRampItemList(lst)
        self.shader = QgsRasterShader()
        
        self.shader.setRasterShaderFunction(self.fcn)

        self.renderer = QgsSingleBandPseudoColorRenderer(self.layer.dataProvider(), 1, self.shader)
        
        self.layer.setRenderer(self.renderer)
        self.layer.triggerRepaint()

    @QtCore.pyqtSlot(bool)
    def on_color_button_clicked(self, which):
        print(which)
        setattr(self, "t_{}_COLOR".format(which), self.color_picker.getColor(getattr(self, "t_{}_COLOR".format(which))))
        getattr(self.dlg, "threshold_{}_color_box".format(which)).setStyleSheet("background-color: {}".format(getattr(self, "t_{}_COLOR".format(which)).name()))
        self.render()

    def on_changed(self, which, source = ""):
        base = self.dlg.doubleSpinBox_b.value()
        t_0 = self.dlg.doubleSpinBox_1.value()  
        t_1 = self.dlg.doubleSpinBox_2.value()
        t_2 = self.dlg.doubleSpinBox_3.value()
        if source == "box":
            base = self.dlg.doubleSpinBox_b.value()
            t_0 = self.dlg.doubleSpinBox_1.value()  
            t_1 = self.dlg.doubleSpinBox_2.value()
            t_2 = self.dlg.doubleSpinBox_3.value()
        elif source == "precision":
            prec = self.dlg.precision_spinbox.value()
            figs = 1.0 / (10.0 ** prec)
            # self.dlg.doubleSpinBox_b.setDecimals(prec)
            # self.dlg.doubleSpinBox_1.setDecimals(prec)
            # self.dlg.doubleSpinBox_2.setDecimals(prec)
            # self.dlg.doubleSpinBox_3.setDecimals(prec)
            self.dlg.doubleSpinBox_b.setSingleStep(figs)
            self.dlg.doubleSpinBox_1.setSingleStep(figs)
            self.dlg.doubleSpinBox_2.setSingleStep(figs)
            self.dlg.doubleSpinBox_3.setSingleStep(figs) 
        else:
            base = self.dlg.base_slider.value()
            t_0 = self.dlg.threshold_0_slider.value()
            t_1 = self.dlg.threshold_1_slider.value()
            t_2 = self.dlg.threshold_2_slider.value()

        alpha_0 = self.dlg.alpha_0_slider.value()
        alpha_1 = self.dlg.alpha_1_slider.value()
        alpha_2 = self.dlg.alpha_2_slider.value()

        self.t_0_COLOR.setAlpha(alpha_0)
        self.t_1_COLOR.setAlpha(alpha_1)
        self.t_2_COLOR.setAlpha(alpha_2)

        #print("Which: {}".format(which))
        if which == 0:
            if t_0 > t_1:
                t_1 = t_0
                self.dlg.threshold_1_slider.setValue(t_1)
                self.dlg.doubleSpinBox_2.setValue(t_1)

            if t_1 > t_2:
                t_2 = t_1
                self.dlg.threshold_2_slider.setValue(t_2)
                self.dlg.doubleSpinBox_3.setValue(t_2)
        elif which == 1:
            if t_0 > t_1:
                t_0 = t_1
                self.dlg.threshold_0_slider.setValue(t_0)
                self.dlg.doubleSpinBox_1.setValue(t_0)

            if t_1 > t_2:
                t_2 = t_1
                self.dlg.threshold_2_slider.setValue(t_2)
                self.dlg.doubleSpinBox_3.setValue(t_2)

        elif which == 2:
            if t_0 > t_1:
                t_1 = t_0
                self.dlg.threshold_1_slider.setValue(t_1)
                self.dlg.doubleSpinBox_2.setValue(t_1)

            if t_1 > t_2:
                t_1 = t_2
                self.dlg.threshold_1_slider.setValue(t_1)
                self.dlg.doubleSpinBox_2.setValue(t_1)

        # if base > t_0:
        #     base = t_0
        #     self.dlg.base_slider.setValue(base)
        #     self.dlg.doubleSpinBox_b.setValue(base)
        self.dlg.base_slider.setValue(base)
        # self.dlg.base_value.setText(str(base))
        # self.dlg.threshold_0_value.setText(str(t_0))
        # self.dlg.threshold_1_value.setText(str(t_1))
        # self.dlg.threshold_2_value.setText(str(t_2))
        self.dlg.threshold_0_slider.setValue(t_0)
        self.dlg.threshold_1_slider.setValue(t_1)
        self.dlg.threshold_2_slider.setValue(t_2)
        self.dlg.doubleSpinBox_1.setValue(t_0)        
        self.dlg.doubleSpinBox_2.setValue(t_1)
        self.dlg.doubleSpinBox_3.setValue(t_2)       
        self.dlg.doubleSpinBox_b.setValue(base)

        self.dlg.alpha_0_value.setText(str(alpha_0))
        self.dlg.alpha_1_value.setText(str(alpha_1))
        self.dlg.alpha_2_value.setText(str(alpha_2))

        if source == "box":
            self.render_debounce_timer.start(25)
        else:
            self.render_debounce_timer.start(75)

    def toggle_widgets(self, value):
        self.dlg.doubleSpinBox_1.setEnabled(value)
        self.dlg.doubleSpinBox_2.setEnabled(value)
        self.dlg.doubleSpinBox_3.setEnabled(value)
        self.dlg.doubleSpinBox_b.setEnabled(value)
        self.dlg.threshold_0_slider.setEnabled(value)
        self.dlg.threshold_1_slider.setEnabled(value)
        self.dlg.threshold_2_slider.setEnabled(value)
        self.dlg.threshold_0_button.setEnabled(value)
        self.dlg.threshold_1_button.setEnabled(value)
        self.dlg.threshold_2_button.setEnabled(value)
        self.dlg.alpha_0_slider.setEnabled(value)
        self.dlg.alpha_1_slider.setEnabled(value)
        self.dlg.alpha_2_slider.setEnabled(value)
        self.dlg.precision_spinbox.setEnabled(value)


    def startWorker(self, iface, layer):
        self.dlg.header.setText("Calculating...")
        worker = Worker(iface, layer)
        messageBar = self.iface.messageBar().createMessage('Calculating range...', )
        progressBar = QProgressBar()
        progressBar.setAlignment(Qt.AlignLeft|Qt.AlignVCenter)
        cancelButton = QPushButton()
        cancelButton.setText('Cancel')
        cancelButton.clicked.connect(worker.kill)
        messageBar.layout().addWidget(progressBar)
        messageBar.layout().addWidget(cancelButton)
        self.iface.messageBar().pushWidget(messageBar, self.iface.messageBar().INFO)
        self.messageBar = messageBar

        #start the worker in a new thread
        thread = QThread()
        worker.moveToThread(thread)
        worker.finished.connect(self.workerFinished)
        worker.error.connect(self.workerError)
        worker.progress.connect(progressBar.setValue)
        thread.started.connect(worker.run)
        thread.start()
        self.thread = thread
        self.worker = worker
        pass

    def workerFinished(self, ret):
        self.dlg.header.setText("")
        # clean up the worker and thread
        self.worker.deleteLater()
        self.thread.quit()
        self.thread.wait()
        self.thread.deleteLater()
        # remove widget from message bar
        self.iface.messageBar().popWidget(self.messageBar)
        if ret is not None:
            # report the result
            _min, _max = ret
            self.MIN = _min
            self.MAX = _max
            self.set_values()
            self.toggle_widgets(True)

            # self.iface.messageBar().pushMessage('min: {}, max: {}'.format(_min, _max))
        else:
            # notify the user that something went wrong
            self.iface.messageBar().pushMessage('Something went wrong! See the message log for more information.', level=QgsMessageBar.CRITICAL, duration=3)
    
    def workerError(self, e, exception_string):
        raise Exception("workerError {}".format(exception_string))