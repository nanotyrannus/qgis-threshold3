from qgis.core import *
from PyQt4 import QtCore, QtGui
import traceback
import time, math

class Worker(QtCore.QObject):
    def __init__(self, iface, layer):
        QtCore.QObject.__init__(self)
        if isinstance(layer, QgsRasterLayer) is False:
            raise TypeError("Worker expected QgsRasterLayer, got '{}'".format(type(layer)))
        self.layer = layer
        self.killed = False
        self.iface = iface

    def run(self):
        ret = None
        try:   
            # self.iface.messageBar().pushMessage("Entered try block")
            provider = self.layer.dataProvider()
            extent = provider.extent()
            rows = self.layer.height()
            cols = self.layer.width()
            block = provider.block(1, extent, cols, rows)
            
            _min = float("inf")
            _max = float("-inf")
            pos_inf = float("inf")
            neg_inf = float("-inf")
            
            total_pixels = rows*cols
            steps = total_pixels // 1000
            current_step = 0
            search_step = 10
            # self.iface.messageBar().pushMessage("Recieved: {} {} {} {}".format(rows, cols, total_pixels, steps))

            for i in range(0, rows, search_step):
                if self.killed:
                    break
                for j in range(0, cols, search_step):
                    val = block.value(i, j)
                    # print "got a value {}".format(val)
                    if val != pos_inf and val != neg_inf and not math.isnan(val):
                        if _min > val:
                            _min = val
                        elif _max < val:
                            _max = val
                    current_step = current_step + 1
                    if current_step % 10000 == 0:
                        self.progress.emit(current_step * search_step * 1000 / float(total_pixels))
            if self.killed is False:
                self.progress.emit(100)
            ret = (_min, _max)
        except Exception, e:
            # raise e
            self.error.emit(e, traceback.format_exc())
        self.finished.emit(ret)

    def kill(self):
        self.killed = True

    finished = QtCore.pyqtSignal(tuple)
    error = QtCore.pyqtSignal(Exception, basestring)
    progress = QtCore.pyqtSignal(float)