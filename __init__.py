# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Threshold3
                                 A QGIS plugin
 Creates a colored overlay using user-defined thresholds.
                             -------------------
        begin                : 2017-08-16
        copyright            : (C) 2017 by Ryan Joseph Constantino
        email                : ryan.constantino93@gmail.com
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
 This script initializes the plugin, making it known to QGIS.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load Threshold3 class from file Threshold3.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .threshold_3 import Threshold3
    return Threshold3(iface)
