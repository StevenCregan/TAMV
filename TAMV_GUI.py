#!/usr/bin/env python3

# TAMV version 2.0RC1
# Python Script to align multiple tools on Jubilee printer with Duet3d Controller
# Using images from USB camera and finding circles in those images
#
# TAMV originally Copyright (C) 2020 Danal Estes all rights reserved.
# TAMV 2.0 Copyright (C) 2021 Haytham Bennani all rights reserved.
# Released under The MIT License. Full text available via https://opensource.org/licenses/MIT
#
# Requires OpenCV to be installed on Pi
# Requires running via the OpenCV installed python (that is why no shebang)
# Requires network connection to Duet based printer running Duet/RepRap V2 or V3
#

# Imports
# import pstats
# from tkinter.tix import Tree
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDesktopWidget,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    # QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    # QMenuBar,
    QMessageBox,
    QPushButton,
    QButtonGroup,
    QSlider,
    QSpinBox,
    QStatusBar,
    QStyle,
    QTabWidget,
    # QTableWidget,
    QSpacerItem,
    QSizePolicy,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget
)
from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QIcon, QFont
from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt, QThread, QMutex, QPoint, QSize

# Core imports
import os
import sys
import cv2
import numpy as np
import math
import DuetWebAPI as DWA
from time import sleep, time
import datetime
import json
import time
import copy
import argparse
import traceback

# graphing imports
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.patches as patches
from matplotlib.ticker import FormatStrFormatter

#logging import
import logging
# Create main application _logger
global _logger

# styles
global style_green, style_red, style_disabled, style_orange
style_green = 'background-color: green; color: white;'
style_red = 'background-color: red; color: white;'
style_disabled = 'background-color: #cccccc; color: #999999; border-style: solid;'
style_orange = 'background-color: dark-grey; color: orange;'
style_default = 'background-color: rgba(0,0,0,0); color: black;'

# debug flags
debugging_small_display = False

# timeout duration in seconds
_tamvTimeout = 300
# default move speed in feedrate/min
_moveSpeed = 6000

##############################################################################################################################################################
# Debug window dialog box
class DebugDialog(QDialog):
    def __init__(self,parent=None, message='' ):
        super(DebugDialog,self).__init__(parent=parent)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint,False)
        self.setWindowTitle( 'Debug Information' )
        # Set layout details
        self.layout = QGridLayout()
        self.layout.setSpacing(3)
        
        # text area
        self.textarea = QTextEdit()
        self.textarea.setAcceptRichText(False)
        self.textarea.setReadOnly(True)
        self.layout.addWidget(self.textarea,0,0)
        # apply layout
        self.setLayout(self.layout)
        temp_text = ''
        try:
            if self.parent().video_thread.isRunning():
                temp_text += 'Video thread running\n'
        except Exception:
            _logger.error( 'Debug window error: \n' + traceback.format_exc() )
        if len(message) > 0:
            temp_text += '\nCalibration Debug Messages:\n' + message
        self.textarea.setText(temp_text)

##############################################################################################################################################################
# Configuration settings dialog box
class SettingsDialog(QDialog):
    # add signal to trigger saving settings to file
    update_settings = pyqtSignal(object)

    def __init__(self,parent=None, addPrinter=False ):
        # Set up settings window
        super(SettingsDialog,self).__init__(parent=parent)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint,False)
        self.setWindowTitle( 'TAMV Configuration Settings' )
        
        # Fetch settings object from parent
        self.settingsObject = copy.deepcopy(self.parent().options)
        self.originalSettingsObject = copy.deepcopy(self.parent().options)
        
        # Set layout details
        self.layout = QVBoxLayout()
        self.layout.setSpacing(3)
        
        ############# TAB SETUP #############
        # Create tabs layout
        self.tabs = QTabWidget()
        # Tab 1: Settings
        self.settingsTab = QWidget()
        self.settingsTab.layout = QVBoxLayout()
        self.settingsTab.setLayout( self.settingsTab.layout )
        
        # Tab 2: Cameras
        self.camerasTab = QWidget()
        self.camerasTab.layout = QVBoxLayout()
        self.camerasTab.setLayout( self.camerasTab.layout )
        
        # add tabs to tabs layout
        self.tabs.addTab( self.settingsTab, 'Machines' )
        if( addPrinter is False ):
            self.tabs.addTab( self.camerasTab, 'Cameras' )
        
        # Add tabs layout to window
        self.layout.addWidget(self.tabs)
        # apply layout
        self.setLayout( self.layout )
        
        ############# POPULATE TABS
        # Create camera items
        if( addPrinter is False ):
            self.createCameraItems()
        # Create machine items
        self.createMachineItems(newPrinter=addPrinter)
        
        ############# MAIN BUTTONS
        # Save button
        if( addPrinter is False ):
            self.save_button = QPushButton( 'Save' )
            self.save_button.setToolTip( 'Save current parameters to settings.json file' )
            self.save_button.clicked.connect(self.updatePrinterObjects)
        else:
            self.save_button = QPushButton( 'Save and connect..')
            self.save_button.clicked.connect(self.saveNewPrinter)
        self.save_button.setObjectName( 'active' )
        # Close button
        self.close_button = QPushButton( 'Cancel' )
        self.close_button.setToolTip( 'Cancel changes and return to main program.' )
        self.close_button.clicked.connect(self.close)
        self.close_button.setObjectName( 'terminate' )
        
        # WINDOW BUTTONS
        self.layout.addWidget(self.save_button)
        self.layout.addWidget(self.close_button)
        
        # OK Cancel buttons
        #self.layout.addWidget(self.buttonBox)
        pass

    def createCameraItems( self ):
        ############# CAMERAS TAB #############
        # Get current camera settings from video thread
        try:
            (brightness_input, contrast_input, saturation_input, hue_input) = self.parent().video_thread.getProperties()
            # Get current source from global variable
            global video_src
            currentSrc = video_src
        except Exception:
            self.updateStatusbar( 'Error fetching camera parameters.' )
            _logger.error( 'Camera Error 0x00: \n' + traceback.format_exc() )
    
        ############# CAMERA TAB: ITEMS
        # Camera Combobox
        self.camera_combo = QComboBox()
        for camera in self.settingsObject['camera']:
            if( camera['default'] == 1 ):
                camera_description = '* ' + str(video_src) + ': ' \
                    + str(self.parent().video_thread.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) \
                    + 'x' + str(self.parent().video_thread.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) + ' @ ' \
                    + str(self.parent().video_thread.cap.get(cv2.CAP_PROP_FPS)) + 'fps'
            else:
                camera_description = str(camera['video_src']) + ': ' + str(camera['display_width']) + 'x' + str(camera['display_height'])
            self.camera_combo.addItem(camera_description)
        
        #HBHBHBHB: need to pass actual video source string object from parameter helper function!!!
        #self.camera_combo.currentIndexChanged.connect(self.parent().video_thread.changeVideoSrc)
        
        # Get cameras button
        self.camera_button = QPushButton( 'Get cameras' )
        self.camera_button.clicked.connect(self.getCameras)
        if self.parent().video_thread.alignment:
            self.camera_button.setDisabled(True)
        else: self.camera_button.setDisabled(False)
        #self.getCameras()
        # Brightness slider
        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setMinimum(0)
        self.brightness_slider.setMaximum(255)
        self.brightness_slider.setValue(int(brightness_input))
        self.brightness_slider.valueChanged.connect(self.changeBrightness)
        self.brightness_slider.setTickPosition(QSlider.TicksBelow)
        self.brightness_slider.setTickInterval(1)
        self.brightness_label = QLabel(str(int(brightness_input)))
        # Contrast slider
        self.contrast_slider = QSlider(Qt.Horizontal)
        self.contrast_slider.setMinimum(0)
        self.contrast_slider.setMaximum(255)
        self.contrast_slider.setValue(int(contrast_input))
        self.contrast_slider.valueChanged.connect(self.changeContrast)
        self.contrast_slider.setTickPosition(QSlider.TicksBelow)
        self.contrast_slider.setTickInterval(1)
        self.contrast_label = QLabel(str(int(contrast_input)))
        # Saturation slider
        self.saturation_slider = QSlider(Qt.Horizontal)
        self.saturation_slider.setMinimum(0)
        self.saturation_slider.setMaximum(255)
        self.saturation_slider.setValue(int(saturation_input))
        self.saturation_slider.valueChanged.connect(self.changeSaturation)
        self.saturation_slider.setTickPosition(QSlider.TicksBelow)
        self.saturation_slider.setTickInterval(1)
        self.saturation_label = QLabel(str(int(saturation_input)))
        # Hue slider
        self.hue_slider = QSlider(Qt.Horizontal)
        self.hue_slider.setMinimum(0)
        self.hue_slider.setMaximum(8)
        self.hue_slider.setValue(int(hue_input))
        self.hue_slider.valueChanged.connect(self.changeHue)
        self.hue_slider.setTickPosition(QSlider.TicksBelow)
        self.hue_slider.setTickInterval(1)
        self.hue_label = QLabel(str(int(hue_input)))
        # Reset button
        self.reset_button = QPushButton("Reset to defaults")
        self.reset_button.setToolTip( 'Reset camera settings to defaults.' )
        self.reset_button.clicked.connect(self.resetDefaults)
        
        # Camera drop-down
        self.camera_box = QGroupBox( 'Active camera source' )
        self.camerasTab.layout.addWidget(self.camera_box)
        cmbox = QHBoxLayout()
        self.camera_box.setLayout(cmbox)
        cmbox.addWidget(self.camera_combo)
        cmbox.addWidget(self.camera_button)
        
        # Brightness
        self.brightness_box =QGroupBox( 'Brightness' )
        self.camerasTab.layout.addWidget(self.brightness_box)
        bvbox = QHBoxLayout()
        self.brightness_box.setLayout(bvbox)
        bvbox.addWidget(self.brightness_slider)
        bvbox.addWidget(self.brightness_label)
        # Contrast
        self.contrast_box =QGroupBox( 'Contrast' )
        self.camerasTab.layout.addWidget(self.contrast_box)
        cvbox = QHBoxLayout()
        self.contrast_box.setLayout(cvbox)
        cvbox.addWidget(self.contrast_slider)
        cvbox.addWidget(self.contrast_label)
        # Saturation
        self.saturation_box =QGroupBox( 'Saturation' )
        self.camerasTab.layout.addWidget(self.saturation_box)
        svbox = QHBoxLayout()
        self.saturation_box.setLayout(svbox)
        svbox.addWidget(self.saturation_slider)
        svbox.addWidget(self.saturation_label)
        # Hue
        self.hue_box =QGroupBox( 'Hue' )
        self.camerasTab.layout.addWidget(self.hue_box)
        hvbox = QHBoxLayout()
        self.hue_box.setLayout(hvbox)
        hvbox.addWidget(self.hue_slider)
        hvbox.addWidget(self.hue_label)

    def createMachineItems( self, newPrinter=False ):
        ############# MACHINES TAB #############
        if( newPrinter is False ):
            # Get machines as defined in the config
            # Printer combo box
            self.printer_combo = QComboBox()
            self.default_printer = None
            self.defaultIndex = 0
            for i, device in enumerate(self.settingsObject['printer']):
                if( device['default'] == 1 ):
                    printer_description = '(default) ' + device['nickname']
                    self.default_printer = device
                    self.defaultIndex = i
                else:
                    printer_description = device['nickname']
                self.printer_combo.addItem(printer_description)
            # set default printer as the selected index
            self.printer_combo.setCurrentIndex(self.defaultIndex)
            if( self.default_printer is None ):
                self.default_printer = self.settingsObject['printer'][0]
            
            # Create a layout for the printer combo box, and the add and delete buttons
            topbox = QGroupBox()
            toplayout = QHBoxLayout()
            topbox.setLayout( toplayout )
            toplayout.addWidget( self.printer_combo )

            # Add button
            self.add_printer_button = QPushButton('+')
            self.add_printer_button.setStyleSheet('background-color: green')
            self.add_printer_button.clicked.connect(self.addProfile)
            self.add_printer_button.setToolTip('Add a new profile..')
            self.add_printer_button.setFixedWidth(30)
            toplayout.addWidget(self.add_printer_button)

            # Delete button
            self.delete_printer_button = QPushButton('X')
            self.delete_printer_button.setStyleSheet('background-color: red')
            self.delete_printer_button.clicked.connect(self.deleteProfile)
            self.delete_printer_button.setToolTip('Delete current profile..')
            self.delete_printer_button.setFixedWidth(30)
            toplayout.addWidget(self.delete_printer_button)
            
            # add printer combo box to layout
            self.settingsTab.layout.addWidget( topbox )
        
        # Printer default checkbox
        self.printerDefault = QCheckBox("&Default", self)
        if( newPrinter is False ):
            self.printerDefault.setChecked(True)
            self.printerDefault.stateChanged.connect( self.checkDefaults )
        self.defaultBox = QGroupBox()
        self.settingsTab.layout.addWidget(self.defaultBox)
        
        dfbox = QHBoxLayout()
        dfbox.setAlignment(Qt.AlignLeft)
        self.defaultBox.setLayout(dfbox)
        dfbox.addWidget(self.printerDefault)
        
        # Printer nickname
        if( newPrinter is False ):
            self.printerNickname = QLineEdit( self.default_printer['nickname'] )
        else: 
            self.printerNickname = QLineEdit()
        self.printerNickname.setPlaceholderText('Enter an alias for your printer')
        self.printerNickname_label = QLabel('Nickname: ')
        self.printerNickname_box =QGroupBox()
        self.settingsTab.layout.addWidget(self.printerNickname_box)
        nnbox = QHBoxLayout()
        self.printerNickname_box.setLayout(nnbox)
        nnbox.addWidget(self.printerNickname_label)
        nnbox.addWidget(self.printerNickname)
        
        # Printer address
        if( newPrinter is False ):
            self.printerAddress = QLineEdit( self.default_printer['address'] )
        else:
            self.printerAddress = QLineEdit()
        self.printerAddress.setPlaceholderText('Enter printer interface or IP')
        self.printerAddress_label = QLabel('Address: ')
        self.printerAddress_box =QGroupBox()
        self.settingsTab.layout.addWidget(self.printerAddress_box)
        adbox = QHBoxLayout()
        self.printerAddress_box.setLayout(adbox)
        adbox.addWidget(self.printerAddress_label)
        adbox.addWidget(self.printerAddress)
        
        # Printer password
        if( newPrinter is False ):
            self.printerPassword = QLineEdit( self.default_printer['password'] )
        else:
            self.printerPassword = QLineEdit()
        self.printerPassword.setPlaceholderText('Password')
        self.printerPassword.setToolTip('(optional): password used to connect to printer')
        self.printerPassword_label = QLabel('Password: ')
        adbox.addWidget( self.printerPassword_label )
        adbox.addWidget( self.printerPassword )

        # Printer controller
        self.controllerName = QComboBox()
        self.controllerName.setToolTip( 'Machine firmware family/category')
        self.controllerName.addItem('RRF/Duet')
        self.controllerName.addItem('klipper')
        if( newPrinter is False ):
            if( self.default_printer['controller'] == "RRF/Duet" ):
                self.controllerName.setCurrentIndex(0)
            else:
                self.controllerName.setCurrentIndex(1)
        else:
            self.controllerName.setCurrentIndex(0)
        self.controllerName_label = QLabel('Controller Type: ')
        self.controllerName_box =QGroupBox()
        self.settingsTab.layout.addWidget(self.controllerName_box)
        cnbox = QHBoxLayout()
        self.controllerName_box.setLayout(cnbox)
        cnbox.addWidget(self.controllerName_label)
        cnbox.addWidget(self.controllerName)

        # Printer name
        if( newPrinter is False ):
            self.printerName = QLineEdit( self.default_printer['name'] )
        else:
            self.printerName = QLineEdit()
        self.printerName.setPlaceholderText('(pulled from machine..)')
        self.printerName.setStyleSheet('font: italic')
        self.printerName.setEnabled(False)
        self.printerName_label = QLabel('Name: ')
        self.printerName_box =QGroupBox()
        self.settingsTab.layout.addWidget(self.printerName_box)
        if( newPrinter is True ):
            self.printerName_box.setVisible(False)
        pnbox = QHBoxLayout()
        self.printerName_box.setLayout(pnbox)
        pnbox.addWidget(self.printerName_label)
        pnbox.addWidget(self.printerName)
        
        # Printer firmware version identifier
        if( newPrinter is False ):
            self.versionName = QLineEdit( self.default_printer['version'] )
        else:
            self.versionName = QLineEdit()
        self.versionName.setPlaceholderText("(pulled from machine..)")
        self.versionName.setStyleSheet('font: italic')
        self.versionName.setEnabled(False)
        self.versionName_label = QLabel('Firmware version: ')
        self.versionName_box =QGroupBox()
        self.settingsTab.layout.addWidget(self.versionName_box)
        if( newPrinter is True ):
            self.versionName_box.setVisible(False)
        fnbox = QHBoxLayout()
        self.versionName_box.setLayout(fnbox)
        fnbox.addWidget(self.versionName_label)
        fnbox.addWidget(self.versionName)
        
        if( newPrinter is False ):
            # handle selecting a new machine from the dropdown
            self.printer_combo.activated.connect(self.refreshPrinters)
            self.printerAddress.editingFinished.connect(self.updateAttributes)
            self.printerPassword.editingFinished.connect(self.updateAttributes)
            self.printerName.editingFinished.connect(self.updateAttributes)
            self.printerNickname.editingFinished.connect(self.updateAttributes)
            self.controllerName.activated.connect(self.updateAttributes)
            self.versionName.editingFinished.connect(self.updateAttributes)
            self.printerDefault.stateChanged.connect(self.updateAttributes)

    def checkDefaults( self ):
        if( self.printerDefault.isChecked() ):
            index = self.printer_combo.currentIndex()
            for i,machine in enumerate(self.settingsObject['printer']):
                machine['default'] = 0
                self.printer_combo.setItemText( i, self.settingsObject['printer'][i]['nickname'])
            self.settingsObject['printer'][index]['default']=1
            self.printer_combo.setItemText(index,'(default) ' + self.settingsObject['printer'][index]['nickname'])
        else:
            # User de-selected default machine
            index = self.printer_combo.currentIndex()
            if( index > -1 ):
                self.printer_combo.setItemText(self.printer_combo.currentIndex(),self.settingsObject['printer'][self.printer_combo.currentIndex()]['nickname'])

    def addProfile(self):
        # Create a new printer profile object
        newPrinter = { 
            'address': '',
            'password': 'repap',
            'name': '',
            'nickname': 'New printer..',
            'controller' : 'RRF/Duet', 
            'version': '',
            'default': 0,
            'tools': [
                { 
                    'number': 0, 
                    'name': 'Tool 0', 
                    'nozzleSize': 0.4, 
                    'offsets': [0,0,0] 
                } ]
            }
        # Add new profile to settingsObject list
        self.settingsObject['printer'].append( newPrinter )
        # enable all text fields
        self.printerDefault.setDisabled(False)
        self.printerAddress.setDisabled(False)
        self.printerPassword.setDisabled(False)
        self.printerNickname.setDisabled(False)
        self.controllerName.setDisabled(False)
        self.delete_printer_button.setDisabled(False)
        self.delete_printer_button.setStyleSheet('background-color: red')
        # update combobox
        self.printer_combo.addItem('New printer..')
        self.printer_combo.setCurrentIndex( len(self.settingsObject['printer'])-1 )
        self.refreshPrinters( self.printer_combo.currentIndex() )

    def deleteProfile( self ):
        index = self.printer_combo.currentIndex()
        if( self.settingsObject['printer'][index]['default'] == 1 ):
            wasDefault = True
        else:
            wasDefault = False
        del self.settingsObject['printer'][index]
        self.printer_combo.removeItem(index)
        index = self.printer_combo.currentIndex()
        if( index > -1 and len(self.settingsObject['printer']) > 0):
            if( wasDefault ):
                self.settingsObject['printer'][0]['default'] = 1
            self.refreshPrinters(self.printer_combo.currentIndex())
        else:
            # no more profiles found, display empty fields
            self.printerDefault.setChecked(False)
            self.printerAddress.setText('')
            self.printerPassword.setText('')
            self.printerName.setText('')
            self.printerNickname.setText('')
            self.controllerName.setCurrentIndex(0)
            self.versionName.setText('')
            # disable all fields
            self.printerDefault.setDisabled(True)
            self.printerAddress.setDisabled(True)
            self.printerPassword.setDisabled(True)
            self.printerName.setDisabled(True)
            self.printerNickname.setDisabled(True)
            self.controllerName.setDisabled(True)
            self.versionName.setDisabled(True)
            self.printer_combo.addItem('+++ Add a new profile --->')
            self.printer_combo.setCurrentIndex(0)
            self.delete_printer_button.setDisabled(True)
            self.delete_printer_button.setStyleSheet('background-color: none')
        pass

    def refreshPrinters( self, index ):
        if( index >= 0 ):
            if( len(self.settingsObject['printer'][index]['address']) > 0 ):
                self.printerAddress.setText(self.settingsObject['printer'][index]['address'])
            else:
                self.printerAddress.clear()
            if( len(self.settingsObject['printer'][index]['password']) > 0 ):
                self.printerPassword.setText(self.settingsObject['printer'][index]['password'])
            else:
                self.printerPassword.clear()
            if( len(self.settingsObject['printer'][index]['name']) > 0):
                self.printerName.setText(self.settingsObject['printer'][index]['name'])
            else:
                self.printerName.clear()
            if( len(self.settingsObject['printer'][index]['nickname']) > 0 ):
                self.printerNickname.setText(self.settingsObject['printer'][index]['nickname'])
            else:
                self.printerNickname.clear()
            if( self.settingsObject['printer'][index]['controller'] == 'RRF/Duet' ):
                self.controllerName.setCurrentIndex(0)
            else:
                self.controllerName.setCurrentIndex(1)
            if( len(self.settingsObject['printer'][index]['version']) > 0 ):
                self.versionName.setText(self.settingsObject['printer'][index]['version'])
            else:
                self.versionName.clear()
            if( self.settingsObject['printer'][index]['default'] == 1 ):
                self.printerDefault.setChecked(True)
            else:
                self.printerDefault.setChecked(False)

    def updateAttributes( self ):
        index = self.printer_combo.currentIndex()
        if( index > -1 ):
            self.settingsObject['printer'][index]['address'] = self.printerAddress.text()
            self.settingsObject['printer'][index]['password'] = self.printerPassword.text()
            self.settingsObject['printer'][index]['name'] = self.printerName.text()
            self.settingsObject['printer'][index]['nickname'] = self.printerNickname.text()
            self.settingsObject['printer'][index]['controller'] = self.controllerName.itemText(self.controllerName.currentIndex())
            self.settingsObject['printer'][index]['version'] = self.versionName.text()
            if( self.printerDefault.isChecked() ):
                self.settingsObject['printer'][index]['default'] = 1
            else:
                self.settingsObject['printer'][index]['default'] = 0

    def resetDefaults(self):
        self.parent().video_thread.resetProperties()
        (brightness_input, contrast_input, saturation_input, hue_input) = self.parent().video_thread.getProperties()
        
        brightness_input = int(brightness_input)
        contrast_input = int(contrast_input)
        saturation_input = int(saturation_input)
        hue_input = int(hue_input)
        self.brightness_slider.setValue(brightness_input)
        self.brightness_label.setText(str(brightness_input))
        self.contrast_slider.setValue(contrast_input)
        self.contrast_label.setText(str(contrast_input))
        self.saturation_slider.setValue(saturation_input)
        self.saturation_label.setText(str(saturation_input))
        self.hue_slider.setValue(hue_input)
        self.hue_label.setText(str(hue_input))

    def changeBrightness(self):
        parameter = int(self.brightness_slider.value())
        try:
            self.parent().video_thread.setProperty(brightness=parameter)
        except:
            None
        self.brightness_label.setText(str(parameter))

    def changeContrast(self):
        parameter = int(self.contrast_slider.value())
        try:
            self.parent().video_thread.setProperty(contrast=parameter)
        except:
            None
        self.contrast_label.setText(str(parameter))

    def changeSaturation(self):
        parameter = int(self.saturation_slider.value())
        try:
            self.parent().video_thread.setProperty(saturation=parameter)
        except:
            None
        self.saturation_label.setText(str(parameter))

    def changeHue(self):
        parameter = int(self.hue_slider.value())
        try:
            self.parent().video_thread.setProperty(hue=parameter)
        except:
            None
        self.hue_label.setText(str(parameter))

    def getCameras(self):
        #HBHBHB: Clean up the handling of this function to the saved list of objects!
        #           to be applied when you save the settings!!
        # checks the first 6 indexes.
        i = 6
        index = 0
        self.camera_combo.clear()
        _cameras = []
        original_camera_description = '* ' + str(video_src) + ': ' \
            + str(self.parent().video_thread.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) \
            + 'x' + str(self.parent().video_thread.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) + ' @ ' \
            + str(self.parent().video_thread.cap.get(cv2.CAP_PROP_FPS)) + 'fps'
        _cameras.append(original_camera_description)
        while i > 0:
            if index != video_src:
                tempCap = cv2.VideoCapture(index)
                if tempCap.read()[0]:
                    api = tempCap.getBackendName()
                    camera_description = str(index) + ': ' \
                        + str(tempCap.get(cv2.CAP_PROP_FRAME_WIDTH)) \
                        + 'x' + str(tempCap.get(cv2.CAP_PROP_FRAME_HEIGHT)) + ' @ ' \
                        + str(tempCap.get(cv2.CAP_PROP_FPS)) + 'fps'
                    _cameras.append(camera_description)
                    tempCap.release()
            index += 1
            i -= 1
        #cameras = [line for line in allOutputs if float(line['propmode']) > -1 ]
        _cameras.sort()
        for camera in _cameras:
            self.camera_combo.addItem(camera)
        self.camera_combo.setCurrentText(original_camera_description)

    def updatePrinterObjects(self):
        defaultSet = False
        multipleDefaults = False
        defaultMessage = "More than one connection is set as the default option.\n\nPlease review the connections for:\n\n"
        # Do some data cleaning
        for machine in self.settingsObject['printer']:
            # Check if user forgot a nickname, default to printer address
            if( machine['nickname'] is None or machine['nickname'] == "" ):
                machine['nickname'] = machine['address']
            # Do some checking to catch multiple default printers set at the same time
            if( machine['default'] == 1 ):
                defaultMessage += "  - " + machine['nickname'] + "\n"
                if( defaultSet ):
                    multipleDefaults = True
                else:
                    defaultSet = True
        # More than one profile is set as the default. Alert user, don't save, and return to the settings screen
        if( multipleDefaults ):
            msgBox = QMessageBox()
            msgBox.setIcon( QMessageBox.Warning )
            msgBox.setText( defaultMessage )
            msgBox.setWindowTitle('ERROR: Too many default connections')
            msgBox.setStandardButtons( QMessageBox.Ok )
            msgBox.exec()
            return
        # No default printed was defined, so set first item to default
        if( defaultSet is False and len(self.settingsObject['printer']) > 0 ):
            self.settingsObject['printer'][0]['default'] = 1
        elif( len(self.settingsObject['printer']) == 0 ):
            # All profiles have been cleared. Add a dummy template
            #HBHBHBHB
            self.settingsObject['printer'] = [
                { 
                'address': 'http://localhost',
                'password': 'reprap',
                'name': '',
                'nickname': 'Default profile',
                'controller' : 'RRF/Duet', 
                'version': '',
                'default': 1,
                'tools': [
                    { 
                        'number': 0, 
                        'name': 'Tool 0', 
                        'nozzleSize': 0.4, 
                        'offsets': [0,0,0] 
                    } ]
                }
            ]
            pass
        self.update_settings.emit( self.settingsObject )
        self.accept()

    def saveNewPrinter( self ):
        _logger.info('Saving printer information..')
        newPrinter = { 
                'address': self.printerAddress.text(),
                'password': self.printerPassword.text(),
                'name': '',
                'nickname': self.printerNickname.text(),
                'controller' : str(self.controllerName.currentText()), 
                'version': '',
                'default': int(self.printerDefault.isChecked()),
                'tools': [
                    { 
                        'number': 0, 
                        'name': 'Tool 0', 
                        'nozzleSize': 0.4, 
                        'offsets': [0,0,0] 
                    } ]
                }
        if( self.printerDefault.isChecked() ):
            # new default printer, clear other objects
            for machine in self.settingsObject['printer']:
                machine['default'] = 0
        self.settingsObject['printer'].append( newPrinter )
        self.update_settings.emit( self.settingsObject )
        self.accept()

    def closeEvent(self, event):
        self.parent().updateStatusbar( 'Changes to settings discarded.' )
        self.settingsObject = self.originalSettingsObject
        self.reject()

##############################################################################################################################################################
# Connection dialog box
class ConnectionDialog(QDialog):
    # signal to trigger creating a new connection profile
    new_printer = pyqtSignal()
    # signal to connect to machine
    connect_printer = pyqtSignal(int)

    def __init__(self,parent=None, addPrinter=False ):
        # Set up settings window
        super(ConnectionDialog,self).__init__(parent=parent)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint,False)
        self.setWindowTitle( 'Connect to a machine' )
        
        # Fetch settings object from parent
        self.csettingsObject = copy.deepcopy(self.parent().options)

        # Set layout details
        self.layout = QVBoxLayout()
        self.layout.setSpacing(3)
        self.setLayout( self.layout )

        # Get machines as defined in the config
        # Printer combo box
        self.cprinter_combo = QComboBox()
        self.cdefault_printer = {}
        for i, device in enumerate(self.csettingsObject['printer']):
            printer_description = device['nickname'] + ' / ' + device['address']
            if( device['default'] == 1 ):
                self.cdefault_printer = device
                self.cdefault_printer['index'] = i
            self.cprinter_combo.addItem(printer_description)
        # handle selecting a new machine
        # set default printer as the selected index
        self.cprinter_combo.setCurrentIndex(self.cdefault_printer['index'])

        # add final option to add a new printer
        self.cprinter_combo.addItem('+++ Add a new machine..')
        self.cprinter_combo.currentIndexChanged.connect(self.addPrinter)

        # add printer combo box to layout
        self.layout.addWidget( self.cprinter_combo )

        self.csave_button = QPushButton( 'Connect..')
        self.csave_button.clicked.connect(self.startConnection)
        self.csave_button.setObjectName( 'active' )
        # Close button
        self.cclose_button = QPushButton( 'Cancel' )
        self.cclose_button.setToolTip( 'Cancel changes and return to main program.' )
        self.cclose_button.clicked.connect(self.reject)
        self.cclose_button.setObjectName( 'terminate' )

        # WINDOW BUTTONS
        self.layout.addWidget(self.csave_button)
        self.layout.addWidget(self.cclose_button)

    def startConnection( self ):
        index = self.cprinter_combo.currentIndex()
        if( index < len(self.csettingsObject['printer'])):
            self.connect_printer.emit(index)
            self.accept()
        else:
            self.new_printer.emit()
            self.reject()

    def addPrinter( self, index ):
        if( index == len(self.csettingsObject['printer'])):
            self.csave_button.setText('Create new profile..')
        else:
            self.csave_button.setText('Connect..')


##############################################################################################################################################################
# Overlay labels for status bar right corner
class OverlayLabel(QLabel):
    def __init__(self):
        super(OverlayLabel, self).__init__()
        self.display_text = 'Welcome to TAMV. Enter your printer address and click \"Connect..\" to start.'

    def paintEvent(self, event):
        super(OverlayLabel, self).paintEvent(event)
        pos = QPoint(10, 470)
        painter = QPainter(self)
        painter.setBrush(QColor(204,204,204,230))
        painter.setPen(QColor(255, 255, 255,0))
        painter.drawRect(0,450,640,50)
        painter.setPen(QColor(0, 0, 0))
        painter.drawText(pos, self.display_text)
    
    def setText(self, textToDisplay):
        self.display_text = textToDisplay

##############################################################################################################################################################
# Nozzle detection and alignment class - main algorithms here
class CalibrateNozzles(QThread):
    # Signals
    status_update = pyqtSignal(str)
    message_update = pyqtSignal(str)
    change_pixmap_signal = pyqtSignal(np.ndarray)
    calibration_complete = pyqtSignal()
    detection_error = pyqtSignal(str)
    result_update = pyqtSignal(object)
    crosshair_display = pyqtSignal(bool)
    update_cpLabel = pyqtSignal(object)

    alignment = False
    _running = False
    display_crosshair = False
    detection_on = False
    align_endstop = False

    def __init__( self, parentTh=None, numTools=0, cycles=1, align=False ):
        super(QThread,self).__init__(parent=parentTh)
        # transformation matrix
        self.transform_matrix = []
        # interface toggles
        self.xray = False
        self.loose = False
        self.altProcessor = False
        self.detector_changed = False
        # setup detector parameters
        self.detectParamsStandard()
        self.numTools = numTools
        self.cycles = cycles
        self.alignment = align
        self.message_update.emit( 'Detector created, waiting for tool..' )

        # start with detection off
        self.display_crosshair = False
        self.detection_on = False

        # Video Parameters
        self.brightness_default = 0
        self.contrast_default = 0
        self.saturation_default = 0
        self.hue_default = 0
        self.brightness = -1
        self.contrast = -1
        self.saturation = -1
        self.hue = -1

        # Start Video feed
        self.cap = cv2.VideoCapture(video_src)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_height)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
        #self.cap.set(cv2.CAP_PROP_FPS,25)
        self.brightness_default = self.cap.get(cv2.CAP_PROP_BRIGHTNESS)
        self.contrast_default = self.cap.get(cv2.CAP_PROP_CONTRAST)
        self.saturation_default = self.cap.get(cv2.CAP_PROP_SATURATION)
        self.hue_default = self.cap.get(cv2.CAP_PROP_HUE)

        self.ret, self.cv_img = self.cap.read()
        if self.ret:
            local_img = self.cv_img
            self.change_pixmap_signal.emit(local_img)
        else:
            self.cap.open(video_src)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera_width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_height)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
            #self.cap.set(cv2.CAP_PROP_FPS,25)
            self.ret, self.cv_img = self.cap.read()
            local_img = self.cv_img
            self.change_pixmap_signal.emit(local_img)

    def toggleXray(self):
        if self.xray:
            self.xray = False
        else: self.xray = True

    def toggleLoose(self):
        self.detector_changed = True
        if self.loose:
            self.detectParamsStandard()
            self.loose = False
        else: 
            self.detectParamsLoose()
            self.loose = True

    def toggleAlgorithm(self):
        if self.altProcessor:
            self.altProcessor = False
        else:
            self.altProcessor = True

    def setProperty(self,brightness=-1, contrast=-1, saturation=-1, hue=-1):
        try:
            if int(brightness) >= 0:
                self.brightness = brightness
                self.cap.set(cv2.CAP_PROP_BRIGHTNESS,self.brightness)
        except Exception as b1: 
            _logger.warning( 'Brightness exception: ' + str(b1) )
        try:
            if int(contrast) >= 0:
                self.contrast = contrast
                self.cap.set(cv2.CAP_PROP_CONTRAST,self.contrast)
        except Exception as c1:
            _logger.warning( 'Contrast exception: ' + str(c1) )
        try:
            if int(saturation) >= 0:
                self.saturation = saturation
                self.cap.set(cv2.CAP_PROP_SATURATION,self.saturation)
        except Exception as s1:
            _logger.warning( 'Saturation exception: ' + str(s1) )
        try:
            if int(hue) >= 0:
                self.hue = hue
                self.cap.set(cv2.CAP_PROP_HUE,self.hue)
        except Exception as h1:
            _logger.warning( 'Hue exception: '  + str(h1) )

    def getProperties(self):
        return (self.brightness_default, self.contrast_default, self.saturation_default,self.hue_default)

    def resetProperties(self):
        self.setProperty(brightness=self.brightness_default, contrast = self.contrast_default, saturation=self.saturation_default, hue=self.hue_default)

    def detectParamsStandard(self):
        # Thresholds
        self.detect_th1 = 1
        self.detect_th2 = 50
        self.detect_thstep = 1
        # Area
        self.detect_filterByArea = True
        self.detect_minArea = 400
        self.detect_maxArea = 900
        # Circularity
        self.detect_filterByCircularity = True
        self.detect_minCircularity = 0.8
        self.detect_maxCircularity= 1
        # Convexity
        self.detect_filterByConvexity = True
        self.detect_minConvexity = 0.3
        self.detect_maxConvexity = 1
        # Inertia
        self.detect_filterByInertia = True
        self.detect_minInertiaRatio = 0.3
        return

    def detectParamsLoose(self):
        # Thresholds
        self.detect_th1 = 1
        self.detect_th2 = 50
        self.detect_thstep = 1
        # Area
        self.detect_filterByArea = True
        self.detect_minArea = 600
        self.detect_maxArea = 15000
        # Circularity
        self.detect_filterByCircularity = True
        self.detect_minCircularity = 0.6
        self.detect_maxCircularity= 1
        # Convexity
        self.detect_filterByConvexity = True
        self.detect_minConvexity = 0.1
        self.detect_maxConvexity = 1
        # Inertia
        self.detect_filterByInertia = True
        self.detect_minInertiaRatio = 0.3
        return

    def run(self):
        _logger.debug( 'Alignment thread starting' )
        self.createDetector()
        _logger.debug( 'Alignment detector created.' )
        while True:
            if self.detection_on:
                if self.alignment:
                    _logger.debug( 'Alignment active' )
                    try:
                        _logger.debug( 'Setting parameters for nozzle detection alignment algorithm..' )
                        # HB: Detector stuff
                        if self.detector_changed:
                            self.createDetector()
                            self.detector_changed = False
                        self._running = True
                        _logger.debug( 'Algorithm parameters set, commencing calibration..' )
                        while self._running:
                            self.cycles = self.parent().cycles
                            for rep in range(self.cycles):
                                for ptool in self.parent().printerObject['tools']:
                                # for tool in range(self.parent().num_tools):
                                    _logger.debug( 'Processing events before tool' )
                                    # process GUI events
                                    app.processEvents()
                                    # Update status bar
                                    self.status_update.emit( 'Calibrating T' + str(ptool['number']) + ', cycle: ' + str(rep+1) + '/' + str(self.cycles))
                                    # Load next tool for calibration
                                    _logger.debug( 'Sending tool pickup to printer..' )
                                    self.parent().displayStandby()
                                    _logger.debug( str(self.parent().printer.getJSON()) )
                                    self.parent().printer.loadTool(int(ptool['number']))
                                    # Move tool to CP coordinates
                                    _logger.debug( 'XX - Jogging tool to calibration set point..' )
                                    self.parent().printer.moveAbsolute( moveSpeed=_moveSpeed, X=str(self.parent().cp_coords['X']) )
                                    self.parent().printer.moveAbsolute( moveSpeed=_moveSpeed, Y=str(self.parent().cp_coords['Y']) )
                                    self.parent().printer.moveAbsolute( moveSpeed=_moveSpeed, Z=str(self.parent().cp_coords['Z']) )
                                    _logger.debug( 'XX - Tool moved to calibration point.' )
                                    # Wait for moves to complete
                                    while self.parent().printer.getStatus() not in 'idle':
                                        _logger.debug( 'XX - Waiting for printer idle status' )
                                        # process GUI events
                                        app.processEvents()
                                        _logger.debug( 'XX - Fetching frame.' )
                                        self.ret, self.cv_img = self.cap.read()
                                        if self.ret:
                                            local_img = self.cv_img
                                            # self.change_pixmap_signal.emit(local_img)
                                        else:
                                            _logger.debug( 'XX - Video source invalid, resetting.' )
                                            self.cap.open(video_src)
                                            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera_width)
                                            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_height)
                                            self.cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
                                            #self.cap.set(cv2.CAP_PROP_FPS,25)
                                            self.ret, self.cv_img = self.cap.read()
                                            local_img = self.cv_img
                                            # self.change_pixmap_signal.emit(local_img)
                                            continue
                                    # Update message bar
                                    self.message_update.emit( 'Searching for nozzle..' )
                                    # Process runtime algorithm changes
                                    
                                    # Check if detection parameters changed from user input
                                    if self.detector_changed:
                                        self.createDetector()
                                        self.detector_changed = False
                                    # Analyze frame for blobs
                                    _logger.debug( 'alignment analyzing frame..' )
                                    (c, transform, mpp) = self.calibrateTool(int(ptool['number']), rep)
                                    _logger.debug( 'alignment analyzing frame complete' )
                                    # process GUI events
                                    app.processEvents()
                                    # apply offsets to machine
                                    self.parent().printer.setToolOffsets( tool=str(ptool['number']), X=str(c['X']), Y=str(c['Y']) )
                            # signal end of execution
                            self._running = False
                        # Update status bar
                        self.status_update.emit( 'Calibration complete: Resetting machine.' )
                        # HBHBHB
                        # Update debug window with results
                        # self.parent().debugString += '\nCalibration output:\n'
                        self.parent().displayStandby()
                        self.parent().printer.unloadTools()
                        self.parent().printer.moveAbsolute(moveSpeed=_moveSpeed, X=str(self.parent().cp_coords['X']))
                        self.parent().printer.moveAbsolute(moveSpeed=_moveSpeed, Y=str(self.parent().cp_coords['Y']))
                        self.parent().printer.moveAbsolute(moveSpeed=_moveSpeed, Z=str(self.parent().cp_coords['Z']))
                        self.status_update.emit( 'Calibration complete: Done.' )
                        self.alignment = False
                        self.detection_on = False
                        self.display_crosshair = False
                        self.crosshair_display.emit(self.display_crosshair)
                        self._running = False
                        self.calibration_complete.emit()
                    except Exception:
                        self.alignment = False
                        self.detection_on = False
                        self.display_crosshair = False
                        self.crosshair_display.emit(self.display_crosshair)
                        self._running = False
                        self.detection_error.emit( 'Error 0x00: unhandled exception' )
                        _logger.error( 'Error 0x00: \n' + traceback.format_exc() )
                        self.cap.release()
                else:
                    # don't run alignment - fetch frames and detect only
                    try:
                        self._running = True
                        while self._running and self.detection_on:
                            # Update status bar
                            #self.status_update.emit( 'Detection mode: ON' )
                            # Process runtime algorithm changes
                            if self.detector_changed:
                                self.createDetector()
                                self.detector_changed = False
                            # Run detection and update output
                            self.analyzeFrame()
                            # process GUI events
                            app.processEvents()
                    except Exception:
                        self._running = False
                        self.detection_error.emit( 'Error 0x01: unhandled exception' )
                        _logger.error( 'Error 0x01: \n' + traceback.format_exc() )
                        self.cap.release()
            elif self.align_endstop:
                _logger.debug( 'Starting auto-CP detection..' )
                self.status_update.emit( 'Starting auto-CP detection..' )
                self.parent().printer.unloadTools()
                self._running = True
                while self._running:
                    # process GUI events
                    app.processEvents()
                    # Update status bar
                    self.status_update.emit( 'Self-calibrating CP...' )
                    # Unload tool to start and restore starting position
                    self.cp_coords = self.parent().printer.getCoordinates()
                    # Update message bar
                    self.message_update.emit( 'Searching for endstop..' )
                    # Process runtime algorithm changes
                    # Analyze frame for blobs
                    self.calibrateTool(ctool='endstop', rep=1)
                    # process GUI events
                    app.processEvents()
                    _logger.debug( 'Ending CP Auto calibration.' )
                    # Capture CP coordinates 
                    self.cp_coords = self.parent().printer.getCoordinates()
                    self._running = False
                    self.align_endstop = False
                # Update GUI elements
                self.status_update.emit( 'CP: X' + str(self.cp_coords['X']) + ' Y' + str(self.cp_coords['Y']) )
                self.display_crosshair = False
                self.crosshair_display.emit(self.display_crosshair)
                self.update_cpLabel.emit(self.cp_coords)
                # Send log output
                _logger.info( '  .. set Control Point: X' + str(self.cp_coords['X']) + ' Y' + str(self.cp_coords['Y']) )
                # Move machine to new CP coordinates
                self.parent().printer.moveAbsolute( moveSpeed=_moveSpeed, X=str(self.cp_coords['X']) )
                self.parent().printer.moveAbsolute( moveSpeed=_moveSpeed, Y=str(self.cp_coords['Y']) )
                self.parent().printer.moveAbsolute( moveSpeed=_moveSpeed, Z=str(self.cp_coords['Z']) )
                # Flag end of detection thread
                self._running = False
                _logger.info( '  .. ready for tool alignment!' )
            else:
                while not self.detection_on and not self.align_endstop:
                    try:
                        self.ret, self.cv_img = self.cap.read()
                        if self.ret:
                            local_img = self.cv_img
                            self.change_pixmap_signal.emit(local_img)
                        else:
                            # reset capture
                            self.cap.open(video_src)
                            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera_width)
                            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_height)
                            self.cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
                            #self.cap.set(cv2.CAP_PROP_FPS,25)
                            self.ret, self.cv_img = self.cap.read()
                            if self.ret:
                                local_img = self.cv_img
                                self.change_pixmap_signal.emit(local_img)
                            continue
                        app.processEvents()
                    except Exception:
                        self.status_update( 'Error 0x02: Unhandled exception' )
                        _logger.error( 'Error 0x02: \n' + traceback.format_exc() )
                        self.cap.release()
                        self.detection_on = False
                        self._running = False
                        exit()
                    app.processEvents()
                app.processEvents()
                continue
        self.cap.release()

    def analyzeFrame(self):
        _logger.debug( 'Starting analyzeFrame' )
        # Placeholder coordinates
        xy = [0,0]
        # Counter of frames with no circle.
        nocircle = 0
        # Random time offset
        rd = int(round(time.time()*1000))

        while True and self.detection_on:
            _logger.debug( 'Processing events.' )
            app.processEvents()
            _logger.debug( 'Reading frame from camera.' )
            self.ret, self.frame = self.cap.read()
            _logger.debug( 'Frame loaded.' )
            if not self.ret:
                # reset capture
                _logger.debug( 'Resetting camera capture!' )
                self.cap.open(video_src)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera_width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_height)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
                _logger.debug( 'Camera source reset.' )
                continue
            #if self.alignment:
            _logger.debug( 'starting detection steps..' )
            try:
                # capture tool location in machine space before processing
                toolCoordinates = self.parent().printer.getCoordinates()
            except Exception:
                toolCoordinates = None
                _logger.error( 'Error 0x03 (Tool coordinates cannot be determined) \n' + traceback.format_exc() )
            # capture first clean frame for display
            cleanFrame = self.frame
            # apply nozzle detection algorithm
            #   - Preprocessor algorithm 1:
            #       gamma correction -> use Y channel from YUV -> GaussianBlur (7,7),6 -> adaptive threshold
            #   - Preprocessor algorithm 2:
            #       gamma correction -> change to greyscale -> apply binary triangle threshold to frame -> GaussianBlur (7,7),6

            # Adjust image gamma
            gammaInput = 1.2
            _logger.debug( 'adjusting image gamma levels' )
            self.frame = self.adjust_gamma(image=self.frame, gamma=gammaInput)

            # Check which preprocessor to use
            if( self.altProcessor is False ):
                # Preprocessor 1
                yuv = cv2.cvtColor(self.frame, cv2.COLOR_BGR2YUV)
                yuvPlanes = cv2.split(yuv)
                yuvPlanes[0] = cv2.GaussianBlur(yuvPlanes[0],(7,7),6)
                yuvPlanes[0] = cv2.adaptiveThreshold(yuvPlanes[0],255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,35,1)
                self.frame = cv2.cvtColor(yuvPlanes[0],cv2.COLOR_GRAY2BGR)
            else:
                # Preprocessor algorithm 2:
                # METHOD 2: triangleBinary threshold
                self.frame=cv2.cvtColor( self.frame, cv2.COLOR_BGR2GRAY )
                thr_val, self.frame = cv2.threshold( self.frame, 127, 255, cv2.THRESH_BINARY|cv2.THRESH_TRIANGLE )
                self.frame =cv2.GaussianBlur( self.frame, (7,7), 6 )
                self.frame = cv2.cvtColor( self.frame, cv2.COLOR_GRAY2BGR )
            _logger.debug( 'Image adjustment complete.' )
            target = [int(np.around(self.frame.shape[1]/2)),int(np.around(self.frame.shape[0]/2))]
            # Process runtime algorithm changes
            
            # HB: Detector stuff
            if self.detector_changed:
                self.createDetector()
                self.detector_changed = False
            # run nozzle detection for keypoints
            keypoints = self.detector.detect(self.frame)
            # draw the timestamp on the frame AFTER the circle detector! Otherwise it finds the circles in the numbers.
            if self.xray:
                cleanFrame = self.frame
            # check if we are displaying a crosshair
            if self.display_crosshair:
                self.frame = cv2.line(cleanFrame, (target[0],    target[1]-25), (target[0],    target[1]+25), (0, 255, 0), 1)
                self.frame = cv2.line(self.frame, (target[0]-25, target[1]   ), (target[0]+25, target[1]   ), (0, 255, 0), 1)
            else: self.frame = cleanFrame
            _logger.debug( 'Image processing and display done.' )
            # update image
            local_img = self.frame
            self.change_pixmap_signal.emit(local_img)
            if(nocircle> 25):
                _logger.debug( 'Error detecting nozzle.' )
                self.message_update.emit( 'Error in detecting nozzle.' )
                nocircle = 0
                continue
            num_keypoints=len(keypoints)
            if (num_keypoints == 0):
                if (25 < (int(round(time.time() * 1000)) - rd)):
                    _logger.debug( 'No circles found.' )
                    nocircle += 1
                    self.frame = self.putText(self.frame,'No circles found',offsety=3)
                    self.message_update.emit( 'No circles found.' )
                    local_img = self.frame
                    self.crosshair_display.emit(False)
                    self.change_pixmap_signal.emit(local_img)
                continue
            if (num_keypoints > 1):
                if (25 < (int(round(time.time() * 1000)) - rd)):
                    _logger.debug( 'Too many circles found.' )
                    self.message_update.emit( 'Too many circles found. Please stop and clean the nozzle.' )
                    self.frame = self.putText(self.frame,'Too many circles found '+str(num_keypoints),offsety=3, color=(255,255,255))
                    self.frame = self.drawKeypoints(self.frame, keypointsArray=keypoints, color=(0,255,255) )
                    local_img = self.frame
                    self.crosshair_display.emit(False)
                    self.change_pixmap_signal.emit(local_img)
                continue
            # Found one and only one circle.  Put it on the frame.
            _logger.debug( 'Nozzle detected successfully.' )
            nocircle = 0 
            xy = np.around(keypoints[0].pt)
            r = np.around(keypoints[0].size/2)
            # draw the blobs that look circular
            _logger.debug( 'Drawing keypoints.' )
            self.frame = self.drawKeypoints(self.frame, keypointsArray=keypoints, color=(255,0, 0) )
            # Note its radius and position
            ts =  'U{0:3.0f} V{1:3.0f} R{2:2.0f}'.format(xy[0],xy[1],r)
            xy = np.uint16(xy)
            #self.frame = self.putText(self.frame, ts, offsety=2, color=(0, 255, 0), stroke=2)
            self.crosshair_display.emit(True)
            self.message_update.emit(ts)
            # show the frame
            _logger.debug( 'Displaying detected nozzle.' )
            local_img = self.frame
            self.change_pixmap_signal.emit(local_img)
            rd = int(round(time.time() * 1000))
            #end the loop
            break
        # and tell our parent.
        if self.detection_on:
            _logger.debug( 'Nozzle detection complete, exiting' )
            return (xy, target, toolCoordinates, r)
        else:
            _logger.debug( 'AnaylzeFrame completed.' )
            return

    def drawKeypoints( self, img, keypointsArray, color=(0,0,255) ):
        originalFrame = img.copy()
        for interest in keypointsArray:
            (x,y) = np.around(interest.pt)
            x = int(x)
            y = int(y)
            r = int(interest.size/2)
            # draw the blobs that look circular
            circles = cv2.circle(
                originalFrame, 
                ( x, y ),
                r, 
                color,
                -1
            )
            img = cv2.addWeighted(circles, 0.4, img, 0.6, 0)
            img = cv2.circle( img, ( x, y ), r, (0,0,0), 1 )
            img = cv2.line( img, (x-5, y), (x+5, y), ( 255, 255, 255 ), 2 )
            img = cv2.line( img, (x, y-5), (x, y+5), ( 255, 255, 255 ), 2 )
        return( img )
    
    def analyzeEndstop(self):
        # Placeholder coordinates
        xy = [0,0]
        # Counter of frames with no circle.
        nocircle = 0
        # Random time offset
        rd = int(round(time.time()*1000))
        while True:
            app.processEvents()
            self.ret, self.frame = self.cap.read()
            if not self.ret:
                # reset capture
                self.cap.open(video_src)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera_width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_height)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
                continue
                # HBHBHBHBHB
                # # capture tool location in machine space before processing
                # toolCoordinates = self.parent().printer.getCoordinates()
            # capture first clean frame for display
            cleanFrame = self.frame
            # apply endstop detection algorithm
            yuv = cv2.cvtColor(cleanFrame, cv2.COLOR_BGR2YUV)
            yuvPlanes = cv2.split(yuv)
            still = yuvPlanes[0]
            
            black = np.zeros((still.shape[0],still.shape[1]), np.uint8)
            black2 = black.copy()
            kernel = np.ones((5,5),np.uint8)

            img_blur = cv2.GaussianBlur(still, (9, 9), 3)
            img_canny = cv2.Canny(img_blur, 50, 190)
            img_dilate = cv2.morphologyEx(img_canny, cv2.MORPH_DILATE, kernel, iterations=3)

            cnt, hierarchy = cv2.findContours(img_dilate, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
            black = cv2.drawContours(black, cnt, -1, (255, 0, 255), -1)
            black = cv2.morphologyEx(black, cv2.MORPH_DILATE, kernel, iterations=2)
            cnt2, hierarchy2 = cv2.findContours(black, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
            if len(cnt2) > 0:
                myContours = []
                for k in range(len(cnt2)):
                    if hierarchy2[0][k][3] > -1:
                        myContours.append(cnt2[k])
                if len(myContours) > 0:
                    blobContours = max(myContours, key=lambda el: cv2.contourArea(el))
                    if len(blobContours) > 0:
                        M = cv2.moments(blobContours)
                        center = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
                        self.frame = cv2.circle(self.frame, center, 150, (255,0,0), 5)
                        self.frame = cv2.circle(self.frame, center, 5, (255,0,255), 2)
                        self.change_pixmap_signal.emit(self.frame)
                        try:
                            return ( center, self.parent().printer.getCoordinates() )
                        except:
                            return None
            else:
                self.parent().updateStatusbar( 'Cannot find endstop! Cancel.' )
                self.change_pixmap_signal.emit(self.frame)
            continue

    def calibrateTool(self, ctool, rep):
        # timestamp for caluclating tool calibration runtime
        self.startTime = time.time()
        # average location of keypoints in frame
        self.average_location=[0,0]
        # current location
        self.current_location = {'X':0,'Y':0}
        # guess position used for camera calibration
        self.guess_position  = [1,1]
        # current keypoint location
        self.xy = [0,0]
        # previous keypoint location
        self.oldxy  = self.xy
        # Tracker flag to set which state algorithm is running in
        self.state = 0
        # detected blob counter
        self.detect_count = 0
        # Save CP coordinates to local class
        self.cp_coordinates = self.parent().cp_coords
        # number of average position loops
        self.position_iterations = 5
        # calibration move set (0.5mm radius circle over 10 moves)
        self.calibrationCoordinates = [ [0,-0.5], [0.294,-0.405], [0.476,-0.155], [0.476,0.155], [0.294,0.405], [0,0.5], [-0.294,0.405], [-0.476,0.155], [-0.476,-0.155], [-0.294,-0.405] ]

        # Check if camera calibration matrix is already defined
        if len(self.transform_matrix) > 1:
            # set state flag to Step 2: nozzle alignment stage
            self.state = 200
            if str(ctool) not in "endstop":
                self.parent().debugString += '\nCalibrating T'+str(ctool)+':C'+str(rep)+': '
        
        # Space coordinates
        self.space_coordinates = []
        self.camera_coordinates = []
        self.calibration_moves = 0

        while True:
            _logger.debug( 'Running calibrate tool..' )
            if str(ctool) not in "endstop":
                (self.xy, self.target, self.tool_coordinates, self.radius) = self.analyzeFrame()
                _logger.debug( 'Captured reference for tool alignment.' )
            else:
                (self.xy, self.tool_coordinates) = self.analyzeEndstop()
                _logger.debug( 'Captured reference for endstop auto-alignment.' )
            # analyzeFrame has returned our target coordinates, average its location and process according to state
            self.average_location[0] += self.xy[0]
            self.average_location[1] += self.xy[1]
            
            self.detect_count += 1

            # check if we've reached our number of detections for average positioning
            if self.detect_count >= self.position_iterations:
                # calculate average X Y position from detection
                self.average_location[0] /= self.detect_count
                self.average_location[1] /= self.detect_count
                # round to 3 decimal places
                self.average_location = np.around(self.average_location,3)
                # get another detection validated
                if str(ctool) not in "endstop":
                    (self.xy, self.target, self.tool_coordinates, self.radius) = self.analyzeFrame()
                else:
                    (self.xy, self.tool_coordinates) = self.analyzeEndstop()
                
                #### Step 1: camera calibration and transformation matrix calculation
                if self.state == 0:
                    _logger.info( '  .. calibrating camera..' )
                    _logger.debug( 'Calibrating rotation.. (10%)' )
                    self.parent().debugString += 'Calibrating camera...\n'
                    # Update GUI thread with current status and percentage complete
                    self.status_update.emit( 'Calibrating camera..' )
                    self.message_update.emit( 'Calibrating rotation.. (10%)' )
                    # Save position as previous location
                    self.oldxy = self.xy
                    # Reset space and camera coordinates
                    self.space_coordinates = []
                    self.camera_coordinates = []
                    # save machine coordinates for detected nozzle
                    self.space_coordinates.append( (self.tool_coordinates['X'], self.tool_coordinates['Y']) )
                    # save camera coordinates
                    self.camera_coordinates.append( (self.xy[0],self.xy[1]) )
                    # move carriage for calibration
                    self.offsetX = self.calibrationCoordinates[0][0]
                    self.offsetY = self.calibrationCoordinates[0][1]
                    _logger.debug( 'Moving carriage for initial camera alignment..' )
                    self.parent().printer.moveRelative( moveSpeed=3000, X=str(self.offsetX), Y=str(self.offsetY) )
                    # Update state tracker to second nozzle calibration move
                    self.state = 1
                    continue
                # Check if camera is still being calibrated
                elif self.state >= 1 and self.state < len(self.calibrationCoordinates):
                    _logger.debug( 'Continuing camera alignment: ' + str(self.state) + '/' + str(len(self.calibrationCoordinates)) )
                    # Update GUI thread with current status and percentage complete
                    self.status_update.emit( 'Calibrating camera..' )
                    self.message_update.emit( 'Calibrating rotation.. ( ' + str(self.state*10) + '%)' )
                    # check if we've already moved, and calculate mpp value
                    if self.state == 1:
                        self.mpp = np.around(0.5/self.getDistance(self.oldxy[0],self.oldxy[1],self.xy[0],self.xy[1]),4)
                    # save position as previous position
                    self.oldxy = self.xy
                    # save machine coordinates for detected nozzle
                    self.space_coordinates.append( (self.tool_coordinates['X'], self.tool_coordinates['Y']) )
                    # save camera coordinates
                    self.camera_coordinates.append( (self.xy[0],self.xy[1]) )
                    # return carriage to relative center of movement
                    self.offsetX = -1*self.offsetX
                    self.offsetY = -1*self.offsetY
                    self.parent().printer.moveRelative( moveSpeed=3000, X=str(self.offsetX), Y=str(self.offsetY) )
                    _logger.debug( 'Moving carriage again: X' + str(self.offsetX) + ' Y' + str(self.offsetY) +' F3000' )
                    # move carriage a random amount in X&Y to collect datapoints for transform matrix
                    self.offsetX = self.calibrationCoordinates[self.state][0]
                    self.offsetY = self.calibrationCoordinates[self.state][1]
                    _logger.debug( 'Moving carriage again: send gCode again..' )
                    self.parent().printer.moveRelative( moveSpeed=3000, X=str(self.offsetX), Y=str(self.offsetY) )
                    _logger.debug( 'Finished: X' + str(self.offsetX) + ' Y' + str(self.offsetY) +' F3000' )
                    # increment state tracker to next calibration move
                    self.state += 1
                    _logger.debug( 'Moving carriage next step..' )
                    continue
                # check if final calibration move has been completed
                elif self.state == len(self.calibrationCoordinates):
                    _logger.debug( 'Camera calibration finalizing..' )
                    calibration_time = np.around(time.time() - self.startTime,1)
                    self.parent().debugString += 'Camera calibration completed in ' + str(calibration_time) + ' seconds.\n'
                    self.parent().debugString += 'Millimeters per pixel: ' + str(self.mpp) + '\n\n'
                    _logger.info( '  .. calibration completed ( ' + str(calibration_time) + 's)' )
                    _logger.info(  '  .. resolution: ' + str(self.mpp) + '/pixel' )
                    # Update GUI thread with current status and percentage complete
                    self.message_update.emit( 'Calibrating rotation.. (100%) - MPP = ' + str(self.mpp))
                    if str(ctool) not in "endstop":
                        self.status_update.emit( 'Calibrating T' + str(ctool) + ', cycle: ' + str(rep+1) + '/' + str(self.cycles))
                    # save position as previous position
                    self.oldxy = self.xy
                    # save machine coordinates for detected nozzle
                    self.space_coordinates.append( (self.tool_coordinates['X'], self.tool_coordinates['Y']) )
                    # save camera coordinates
                    self.camera_coordinates.append( (self.xy[0],self.xy[1]) )
                    # calculate camera transformation matrix
                    self.transform_input = [(self.space_coordinates[i], self.normalize_coords(camera)) for i, camera in enumerate(self.camera_coordinates)]
                    self.transform_matrix, self.transform_residual = self.least_square_mapping(self.transform_input)
                    # define camera center in machine coordinate space
                    self.newCenter = self.transform_matrix.T @ np.array([0, 0, 0, 0, 0, 1])
                    self.guess_position[0]= np.around(self.newCenter[0],3)
                    self.guess_position[1]= np.around(self.newCenter[1],3)
                    _logger.debug( 'Camera calibration matrix has been calculated.' )
                    self.parent().printer.moveAbsolute( moveSpeed=1000, X=self.guess_position[0], Y=self.guess_position[1] )
                    # update state tracker to next phase
                    self.state = 200
                    # start tool calibration timer
                    self.startTime = time.time()
                    if str(ctool) not in "endstop":
                        self.parent().debugString += '\nCalibrating T'+str(ctool)+':C'+str(rep)+': '
                    else:
                        self.parent().debugString += '\nCP Autocalibration..'
                    continue
                #### Step 2: nozzle alignment stage
                elif self.state == 200:
                    _logger.debug( 'Nozzle alignment start..' )
                    # Update GUI thread with current status and percentage complete
                    if str(ctool) not in "endstop":
                        self.message_update.emit( 'Tool calibration move #' + str(self.calibration_moves))
                        self.status_update.emit( 'Calibrating T' + str(ctool) + ', cycle: ' + str(rep+1) + '/' + str(self.cycles))
                    else:
                        self.message_update.emit( 'CP calibration move #' + str(self.calibration_moves))
                    # increment moves counter
                    self.calibration_moves += 1
                    # nozzle detected, frame rotation is set, start
                    self.cx,self.cy = self.normalize_coords(self.xy)
                    self.v = [self.cx**2, self.cy**2, self.cx*self.cy, self.cx, self.cy, 0]
                    self.offsets = -1*(0.55*self.transform_matrix.T @ self.v)
                    self.offsets[0] = np.around(self.offsets[0],3)
                    self.offsets[1] = np.around(self.offsets[1],3)
                    # Add rounding handling for endstop alignment
                    if( str(ctool) in "endstop" ):
                        if( abs(self.offsets[0]) < 0.05 and abs(self.offsets[1]) < 0.05 ):
                            self.offsets[0] = 0.0
                            self.offsets[1] = 0.0
                            _logger.debug( 'Endstop close enough, truncating moves.' )
                    else:
                        # Move it a bit
                        _logger.debug( 'Moving nozzle for detection..' )
                        self.parent().printer.limitAxes()
                        self.parent().printer.moveRelative( moveSpeed=1000, X=self.offsets[0], Y=self.offsets[1] )
                        _logger.debug( 'Nozzle movement complete X{0:-1.3f} Y{1:-1.3f} F1000 '.format(self.offsets[0],self.offsets[1]))
                    # save position as previous position
                    self.oldxy = self.xy
                    if ( self.offsets[0] == 0.0 and self.offsets[1] == 0.0 ):
                        _logger.debug( 'Updating GUI..' )
                        self.parent().debugString += str(self.calibration_moves) + ' moves.\n'
                        self.parent().printer.moveAbsolute( moveSpeed=13200 )
                        # Update GUI with progress
                        # calculate final offsets and return results
                        if str(ctool) not in "endstop":
                            self.tool_offsets = self.parent().printer.getToolOffset(ctool)
                        else:
                            #HBHBHB: TODO ADD PROBE OFFSETS TO THIS CALCULATION
                            self.tool_offsets = {
                                'X' : 0,
                                'Y' : 0,
                                'Z' : 0
                            }
                        if str(ctool) not in "endstop":
                            _logger.debug( 'Calculating offsets.' )
                            final_x = np.around( (self.cp_coordinates['X'] + self.tool_offsets['X']) - self.tool_coordinates['X'], 3 )
                            final_y = np.around( (self.cp_coordinates['Y'] + self.tool_offsets['Y']) - self.tool_coordinates['Y'], 3 )
                            string_final_x = "{:.3f}".format(final_x)
                            string_final_y = "{:.3f}".format(final_y)
                            # Save offset to output variable
                            # HBHBHBHB
                            _return = {}
                            _return['X'] = final_x
                            _return['Y'] = final_y
                            _return['MPP'] = self.mpp
                            _return['time'] = np.around(time.time() - self.startTime,1)
                            self.message_update.emit( 'Nozzle calibrated: offset coordinates X' + str(_return['X']) + ' Y' + str(_return['Y']) )
                            self.parent().debugString += 'T' + str(ctool) + ', cycle ' + str(rep+1) + ' completed in ' + str(_return['time']) + ' seconds.\n'
                            self.message_update.emit( 'T' + str(ctool) + ', cycle ' + str(rep+1) + ' completed in ' + str(_return['time']) + ' seconds.' )
                            _logger.debug( 'T' + str(ctool) + ', cycle ' + str(rep+1) + ' completed in ' + str(_return['time']) + 's and ' + str(self.calibration_moves) + ' movements.' )
                            _logger.info( 'Tool ' + str(ctool) +' offsets are X' + str(_return['X']) + ' Y' + str(_return['Y']) )
                        else:
                            self.message_update.emit( 'CP auto-calibrated.' )
                        self.parent().printer.moveAbsolute( moveSpeed=13200 )

                        if str(ctool) not in "endstop":
                            _logger.debug( 'Generating G10 commands.' )
                            self.parent().debugString += 'G10 P' + str(ctool) + ' X' + string_final_x + ' Y' + string_final_y + '\n'
                            x_tableitem = QTableWidgetItem(string_final_x)
                            x_tableitem.setBackground(QColor(100,255,100,255))
                            y_tableitem = QTableWidgetItem(string_final_y)
                            y_tableitem.setBackground(QColor(100,255,100,255))
                            #self.parent().offsets_table.setItem(tool,0,x_tableitem)
                            #self.parent().offsets_table.setItem(tool,1,y_tableitem)

                            self.result_update.emit({
                                'tool': str(ctool),
                                'cycle': str(rep),
                                'mpp': str(self.mpp),
                                'X': string_final_x,
                                'Y': string_final_y
                            })
                            return(_return, self.transform_matrix, self.mpp)
                        else: return
                    else:
                        self.state = 200
                        continue
                self.avg = [0,0]
                self.location = {'X':0,'Y':0}
                self.count = 0

    def normalize_coords(self,coords):
        xdim, ydim = camera_width, camera_height
        return (coords[0] / xdim - 0.5, coords[1] / ydim - 0.5)

    def least_square_mapping(self,calibration_points):
        # Compute a 2x2 map from displacement vectors in screen space to real space.
        n = len(calibration_points)
        real_coords, pixel_coords = np.empty((n,2)),np.empty((n,2))
        for i, (r,p) in enumerate(calibration_points):
            real_coords[i] = r
            pixel_coords[i] = p
        x,y = pixel_coords[:,0],pixel_coords[:,1]
        A = np.vstack([x**2,y**2,x * y, x,y,np.ones(n)]).T
        transform = np.linalg.lstsq(A, real_coords, rcond = None)
        return transform[0], transform[1].mean()

    def getDistance(self, x1, y1, x0, y0 ):
        x1_float = float(x1)
        x0_float = float(x0)
        y1_float = float(y1)
        y0_float = float(y0)
        x_dist = (x1_float - x0_float) ** 2
        y_dist = (y1_float - y0_float) ** 2
        retVal = np.sqrt((x_dist + y_dist))
        return np.around(retVal,3)

    def stop(self):
        self._running = False
        self.detection_on = False
        # try:
        #     tempCoords = self.printer.getCoordinates()
        #     if self.printer.isIdle():
        #         self.parent().printer.unloadTools()
        #         self.parent().printer.moveAbsolute( moveSpeed=_moveSpeed, X=str(tempCoords['X']), Y=str(tempCoords['Y']) )
        #         timeoutChecker = 0
        #         while self.parent().printer.getStatus() not in 'idle' and timeoutChecker <= _tamvTimeout:
        #             timeoutChecker += 1
        #             time.sleep(1)
        # except: None
        self.cap.release()
        self.exit()

    def createDetector(self):
        # Setup SimpleBlobDetector parameters.
        params = cv2.SimpleBlobDetector_Params()
        # Thresholds
        params.minThreshold = self.detect_th1
        params.maxThreshold = self.detect_th2
        params.thresholdStep = self.detect_thstep

        # Area
        params.filterByArea = True         # Filter by Area.
        params.minArea = self.detect_minArea
        params.maxArea = self.detect_maxArea

        # Circularity
        params.filterByCircularity = True  # Filter by Circularity
        params.minCircularity = self.detect_minCircularity
        params.maxCircularity= 1

        # Convexity
        params.filterByConvexity = True    # Filter by Convexity
        params.minConvexity = 0.3
        params.maxConvexity = 1

        # Inertia
        params.filterByInertia = True      # Filter by Inertia
        params.minInertiaRatio = 0.3

        # create detector
        self.detector = cv2.SimpleBlobDetector_create(params)

    def adjust_gamma(self, image, gamma=1.2):
        # build a lookup table mapping the pixel values [0, 255] to
        # their adjusted gamma values
        invGamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** invGamma) * 255
            for i in np.arange(0, 256)]).astype( 'uint8' )
        # apply gamma correction using the lookup table
        return cv2.LUT(image, table)

    def putText(self, frame, text,color=(0, 0, 255), offsetx=0, offsety=0, stroke=2):  # Offsets are in character box size in pixels. 
        if (text == 'timestamp' ): text = datetime.datetime.now().strftime( '%m-%d-%Y %H:%M:%S' )
        fontScale = 1
        if (frame.shape[1] > 640): fontScale = stroke = 2
        if (frame.shape[1] < 640):
            fontScale = 0.8
            stroke = 1
        offpix = cv2.getTextSize( 'A',   cv2.FONT_HERSHEY_SIMPLEX ,fontScale, stroke)
        textpix = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX ,fontScale, stroke)
        offsety=max(offsety, (-frame.shape[0]/2 + offpix[0][1])/offpix[0][1]) # Let offsety -99 be top row
        offsetx=max(offsetx, (-frame.shape[1]/2 + offpix[0][0])/offpix[0][0]) # Let offsetx -99 be left edge
        offsety=min(offsety,  (frame.shape[0]/2 - offpix[0][1])/offpix[0][1]) # Let offsety  99 be bottom row. 
        offsetx=min(offsetx,  (frame.shape[1]/2 - offpix[0][0])/offpix[0][0]) # Let offsetx  99 be right edge.
        bottomLeftX = int(offsetx * offpix[0][0]) + int(frame.shape[1]/2) - int(textpix[0][0]/2)
        bottomLeftY = int(offsety * offpix[0][1]) + int(frame.shape[0]/2) + int(textpix[0][1]/2)
        rectangle = frame.copy()
        rectangle = cv2.rectangle( rectangle, (bottomLeftX-5, bottomLeftY+5), ( bottomLeftX+textpix[0][0]+5, bottomLeftY-textpix[0][1]-5 ), (255-color[0],255-color[1],255-color[2]), -1 )
        frame = cv2.addWeighted(rectangle, 0.8, frame, 0.2, 0)
        cv2.putText(frame, text, (bottomLeftX, bottomLeftY),
            cv2.FONT_HERSHEY_SIMPLEX, fontScale, color, stroke)
        return(frame)

    def changeVideoSrc(self, newSrc=-1):
        self.cap.release()
        video_src = newSrc
        # Start Video feed
        self.cap.open(video_src)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_height)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
        #self.cap.set(cv2.CAP_PROP_FPS,25)
        self.brightness_default = self.cap.get(cv2.CAP_PROP_BRIGHTNESS)
        self.contrast_default = self.cap.get(cv2.CAP_PROP_CONTRAST)
        self.saturation_default = self.cap.get(cv2.CAP_PROP_SATURATION)
        self.hue_default = self.cap.get(cv2.CAP_PROP_HUE)

        self.ret, self.cv_img = self.cap.read()
        if self.ret:
            local_img = self.cv_img
            self.change_pixmap_signal.emit(local_img)
        else:
            self.cap.open(video_src)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera_width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_height)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
            #self.cap.set(cv2.CAP_PROP_FPS,25)
            self.ret, self.cv_img = self.cap.read()
            local_img = self.cv_img
            self.change_pixmap_signal.emit(local_img)

##############################################################################################################################################################
##############################################################################################################################################################
## GUI application class
class App(QMainWindow):
### Class attributes
    cp_coords = {}
    numTools = 0
    current_frame = np.ndarray
    mutex = QMutex()
    debugString = ''
    calibrationResults = []
    # standby image
    standbyImage = None
    # settings.json options variable
    options = {}
    # state flag for defining a new connection
    newPrinter = False
    # Set state flags to initial values
    flag_CP_setup = False
    # main printer class
    printer = None


### Initialize class
    def __init__(self, parent=None):
        # output greeting to log
        _logger.info( 'Launching application.. ' )
        super().__init__()
### #  setup class attributes
        self.standbyImage = QPixmap('./standby.jpg')
        self.printer = None
### #  setup window properties
        self.setWindowFlag(Qt.WindowContextHelpButtonHint,False)
        self.setWindowTitle( 'TAMV' )
        self.setWindowIcon(QIcon( 'jubilee.png' ))
### #  handle screen mode based on resolution
        global display_width, display_height
        screen = QDesktopWidget().availableGeometry()
        self.small_display = False
        # HANDLE DIFFERENT DISPLAY SIZES
        # 800x600 display - fullscreen app
        if int(screen.width()) >= 800 and int(screen.height()) >= 550 and int(screen.height() < 600):
            self.small_display = True
            _logger.info( '800x600 desktop detected' )
            display_width = 512
            display_height = 384
            self.setWindowFlag(Qt.FramelessWindowHint)
            self.showFullScreen()
            self.setGeometry(0,0,700,500)
            app_screen = self.frameGeometry()
        # 848x480 display - fullscreen app
        elif int(screen.width()) >= 800 and int(screen.height()) < 550:
            self.small_display = True
            _logger.info( '848x480 desktop detected' )
            display_width = 448
            display_height = 336
            self.setWindowFlag(Qt.FramelessWindowHint)
            self.showFullScreen()
            self.setGeometry(0,0,700,400)
            app_screen = self.frameGeometry()
        # larger displays - normal window
        else:
            if debugging_small_display:
                self.small_display = True
                _logger.info( '800x600 desktop detected' )
                display_width = 512
                display_height = 384
                self.setWindowFlag(Qt.FramelessWindowHint)
                self.showFullScreen()
                self.setGeometry(0,0,700,500)
                app_screen = self.frameGeometry()
            else:
                self.small_display = False
                display_width = 640
                display_height = 480
                self.setGeometry(QStyle.alignedRect(Qt.LeftToRight,Qt.AlignHCenter,QSize(800,600),screen))
                app_screen = self.frameGeometry()
                app_screen.moveCenter(screen.center())
                self.move(app_screen.topLeft())
### #  create stylehseets
        self.setStyleSheet(
            '\
            QLabel#instructions_text {\
                background-color: yellow;\
            }\
            QPushButton {\
                border: 1px solid #adadad;\
                border-style: outset;\
                border-radius: 4px;\
                font: 14px;\
                padding: 6px;\
            }\
            QPushButton#calibrating:enabled {\
                background-color: orange;\
                color: white;\
            }\
            QPushButton#completed:enabled {\
                background-color: blue;\
                color: white;\
            }\
            QPushButton:hover,QPushButton:enabled:hover,QPushButton:enabled:!checked:hover,QPushButton#completed:enabled:hover {\
                background-color: #27ae60;\
                border: 1px solid #aaaaaa;\
            }\
            QPushButton:pressed,QPushButton:enabled:pressed,QPushButton:enabled:checked,QPushButton#completed:enabled:pressed {\
                background-color: #ae2776;\
                border: 1px solid #aaaaaa;\
            }\
            QPushButton:enabled {\
                background-color: green;\
                color: white;\
            }\
            QLabel#labelPlus {\
                font: 20px;\
                padding: 0px;\
            }\
            QPushButton#plus:enabled {\
                font: 20px;\
                padding: 0px;\
                background-color: #eeeeee;\
                color: #000000;\
            }\
            QPushButton#plus:enabled:hover {\
                font: 20px;\
                padding: 0px;\
                background-color: green;\
                color: #000000;\
            }\
            QPushButton#plus:enabled:pressed {\
                font: 20px;\
                padding: 0px;\
                background-color: #FF0000;\
                color: #222222;\
            }\
            QPushButton#debug,QMessageBox > #debug {\
                background-color: blue;\
                color: white;\
            }\
            QPushButton#debug:hover, QMessageBox > QAbstractButton#debug:hover {\
                background-color: green;\
                color: white;\
            }\
            QPushButton#debug:pressed, QMessageBox > QAbstractButton#debug:pressed {\
                background-color: #ae2776;\
                border-style: inset;\
                color: white;\
            }\
            QPushButton#active, QMessageBox > QAbstractButton#active {\
                background-color: green;\
                color: white;\
            }\
            QPushButton#active:pressed,QMessageBox > QAbstractButton#active:pressed {\
                background-color: #ae2776;\
            }\
            QPushButton#terminate {\
                background-color: red;\
                color: white;\
            }\
            QPushButton#terminate:pressed {\
                background-color: #c0392b;\
            }\
            QPushButton:disabled, QPushButton#terminate:disabled {\
                background-color: #cccccc;\
                color: #999999;\
            }\
            QInputDialog QDialogButtonBox > QPushButton:enabled, QDialog QPushButton:enabled,QPushButton[checkable="true"]:enabled {\
                background-color: none;\
                color: black;\
                border: 1px solid #adadad;\
                border-style: outset;\
                border-radius: 4px;\
                font: 14px;\
                padding: 6px;\
            }\
            QPushButton:enabled:checked {\
                background-color: #ae2776;\
                border: 1px solid #aaaaaa;\
            }\
            QInputDialog QDialogButtonBox > QPushButton:pressed, QDialog QPushButton:pressed {\
                background-color: #ae2776;\
            }\
            QInputDialog QDialogButtonBox > QPushButton:hover:!pressed, QDialog QPushButton:hover:!pressed {\
                background-color: #27ae60;\
            }\
            '
        )
### #  load user parameters
        global camera_width, camera_height, video_src
        try:
            with open( 'settings.json','r' ) as inputfile:
                self.options = json.load(inputfile)
            _logger.info( '  .. reading settings.json..' )
            # Fetch defined cameras
            camera_settings = self.options['camera'][0]
            defaultCameraDefined = False
            for source in self.options['camera']:
                try:
                    if( source['default'] == 1 ):
                        camera_settings = source
                        defaultCameraDefined = True
                    else:
                        continue
                except KeyError as ke:
                    # no default field detected - create a default if not already done
                    if( defaultCameraDefined is False ):
                        # Set default camera since none exist so far
                        source['default'] = 1
                        defaultCameraDefined = True
                    else:
                        source['default'] = 0
                    pass
            camera_height = int( camera_settings['display_height'] )
            camera_width = int( camera_settings['display_width'] )
            video_src = camera_settings['video_src']
            if len(str(video_src)) == 1: 
                video_src = int(video_src)
            # Fetch defined machines
            tempURL = self.options['printer'][0]['address']
            defaultPrinterDefined = False
            for machine in self.options['printer']:
                # Find default printer first
                try:
                    if( machine['default'] == 1 ):
                        tempURL = machine['address']
                except KeyError as ke:
                    # no default field detected - create a default if not already done
                    if( defaultPrinterDefined is False ):
                        machine['default'] = 1
                        defaultPrinterDefined = True
                    else:
                        machine['default'] = 0
                # Check if password doesn't exist
                try:
                    temp = machine['password']
                except KeyError:
                    machine['password'] = 'reprap'
                # Check if nickname doesn't exist
                try:
                    temp = machine['nickname']
                except KeyError:
                    machine['nickname'] = machine['name']
                # Check if controller doesn't exist
                try:
                    temp = machine['controller']
                except KeyError:
                    machine['controller'] = 'RRF/Duet'
                # Check if version doesn't exist
                try:
                    temp = machine['version']
                except KeyError:
                    machine['version'] = ''
                # Check if tools doesn't exist
                try:
                    temp = machine['tools']
                except KeyError:
                    machine['tools'] = [ { 'number': 0, 'name': 'Tool 0', 'nozzleSize': 0.4, 'offsets': [0,0,0] } ]
            ( _errCode, _errMsg, self.printerURL ) = self.sanitizeURL(tempURL)
            if _errCode > 0:
                # invalid input
                _logger.error( 'Invalid printer URL detected in settings.json' )
                _logger.info( 'Defaulting to \"http://localhost\"...' )
                self.printerURL = 'http://localhost'
        except FileNotFoundError:
            # No settings file defined, create a new one
            _logger.info( '  .. creating new settings.json..' )
            # create parameter file with standard parameters
            
            # create a camera array
            self.options['camera'] = []
            self.options['camera'].append( {
                'video_src': 0,
                'display_width': '640',
                'display_height': '480',
                'default': 1
            } )
            # Create a printer array
            self.options['printer'] = [
                { 
                'address': 'http://localhost',
                'password': 'reprap',
                'name': 'My Duet',
                'nickname': 'Default',
                'controller' : 'RRF/Duet', 
                'version': '',
                'default': 1,
                'tools': [
                    { 
                        'number': 0, 
                        'name': 'Tool 0', 
                        'nozzleSize': 0.4, 
                        'offsets': [0,0,0] 
                    } ]
                }
            ]
            try:
                camera_width = 640
                camera_height = 480
                video_src = 1
                with open( 'settings.json','w' ) as outputfile:
                    json.dump(self.options, outputfile)
            except Exception as e1:
                _logger.error( 'Error reading user settings file.' + str(e1) )
### #  create GUI elements
### ## Menubar
        if not self.small_display:
            self.menubar = self.menuBar()
### ### File menu
            fileMenu = QMenu( '&File', self)
            self.menubar.addMenu(fileMenu)
### ### # Settings..
            self.settingsAction = QAction(self)
            self.settingsAction.setText( '&Settings..' )
            self.settingsAction.triggered.connect(self.displaySettings)
            fileMenu.addAction(self.settingsAction)
### ### # Debug info
            self.debugAction = QAction(self)
            self.debugAction.setText( '&Debug info' )
            self.debugAction.triggered.connect(self.displayDebug)
            fileMenu.addAction(self.debugAction)
            fileMenu.addSeparator()
### ### # Save current settings
            self.saveAction = QAction(self)
            self.saveAction.setText( 'S&ave current settings' )
            self.saveAction.triggered.connect(self.saveUserSettings)
            fileMenu.addAction(self.saveAction)
### ### # Quit
            self.quitAction = QAction(self)
            self.quitAction.setText( '&Quit' )
            self.quitAction.triggered.connect(self.close)
            fileMenu.addSeparator()
            fileMenu.addAction(self.quitAction)
### ### Analysis menu
            self.analysisMenu = QMenu( '&Analyze',self)
            self.menubar.addMenu(self.analysisMenu)
            self.analysisMenu.setDisabled(True)
### ### # Graph calibration data..
            self.graphAction = QAction(self)
            self.graphAction.setText( '&Graph calibration data..' )
            self.graphAction.triggered.connect(lambda: self.analyzeResults(graph=True))
            self.analysisMenu.addAction(self.graphAction)
### ### # Export analysis..
            self.exportAction = QAction(self)
            self.exportAction.setText( '&Export analysis..' )
            self.exportAction.triggered.connect(lambda: self.analyzeResults(export=True))
            self.analysisMenu.addAction(self.exportAction)
        self.centralWidget = QWidget()
        self.setCentralWidget(self.centralWidget)
        
### ##  Statusbar
        self.statusBar = QStatusBar()
        self.statusBar.showMessage( 'Loading up video feed and libraries..',5000)
        self.setStatusBar( self.statusBar )
        # CP location on statusbar
        self.cp_label = QLabel( '<b>CP:</b> <i>undef</i>' )
        self.statusBar.addPermanentWidget(self.cp_label)
        self.cp_label.setStyleSheet(style_red)
        # Connection status on statusbar
        self.connection_status = QLabel( 'Disconnected' )
        self.connection_status.setStyleSheet(style_red)
        self.statusBar.addPermanentWidget(self.connection_status)
### ##  Main interface
### ### image_label (camera display)
        self.image_label = OverlayLabel()
        self.image_label.setFixedSize( display_width, display_height )
        self.image_label.setScaledContents(True)
        pixmap = QPixmap( display_width, display_height )
        self.image_label.setPixmap(pixmap)
### ### connect button
        self.connect_button = QPushButton( 'Connect..' )
        self.connect_button.setToolTip( 'Connect to a Duet machine..' )
        self.connect_button.clicked.connect(self.connectToPrinter)
        self.connect_button.setFixedWidth(170)
### ### disconnect button
        self.disconnect_button = QPushButton( 'STOP / DISCONNECT' )
        self.disconnect_button.setToolTip( 'End current operation,\nunload tools, and return carriage to CP\nthen disconnect.' )
        self.disconnect_button.clicked.connect(self.disconnectFromPrinter)
        self.disconnect_button.setFixedWidth(170)
        self.disconnect_button.setObjectName( 'terminate' )
        self.disconnect_button.setDisabled(True)
### ### controlPoint button
        self.controlPoint_button = QPushButton( 'Set Control Point..' )
        self.controlPoint_button.setToolTip( 'Define your origin point\nto calculate all tool offsets from.' )
        self.controlPoint_button.clicked.connect(self.setupCP)
        self.controlPoint_button.setFixedWidth(170)
        self.controlPoint_button.setDisabled(True)
### ### calibration button
        self.calibration_button = QPushButton( 'Start Tool Alignment' )
        self.calibration_button.setToolTip( 'Start alignment process.\nMAKE SURE YOUR CARRIAGE IS CLEAR TO MOVE ABOUT WITHOUT COLLISIONS!' )
        self.calibration_button.clicked.connect(self.runCalibration)
        self.calibration_button.setDisabled(True)
        self.calibration_button.setFixedWidth(170)
### ### debugInfo button
        self.debugInfo_button = QPushButton( 'Debug Information' )
        self.debugInfo_button.setToolTip( 'Display current debug info for troubleshooting\nand to display final G10 commands' )
        self.debugInfo_button.clicked.connect(self.displayDebug)
        self.debugInfo_button.setFixedWidth(170)
        self.debugInfo_button.setObjectName( 'debug' )
### ### exit button
        self.exit_button = QPushButton( 'Quit' )
        self.exit_button.setToolTip( 'Unload tools, disconnect, and quit TAMV.' )
        self.exit_button.clicked.connect(self.close)
        self.exit_button.setFixedWidth(170)
### ### autoCalibrateEndstop button
        self.autoCalibrateEndstop_button = QPushButton( 'Automated capture' )
        self.autoCalibrateEndstop_button.setFixedWidth(170)
        self.autoCalibrateEndstop_button.clicked.connect(self.startAutoCPCapture)
        self.autoCalibrateEndstop_button.setDisabled(True)
### ### manualAlignment button
        self.manualAlignment_button = QPushButton( 'Capture' )
        self.manualAlignment_button.setToolTip( 'After jogging tool to the correct position in the window, capture and calculate offset.' )
        self.manualAlignment_button.clicked.connect(self.captureOffset)
        self.manualAlignment_button.setDisabled(True)
        self.manualAlignment_button.setFixedWidth(170)
### ### cycles spinbox
        self.cycles_label = QLabel( 'Cycles: ' )
        self.cycles_label.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        self.cycles_spinbox = QSpinBox()
        self.cycles_spinbox.setValue(1)
        self.cycles_spinbox.setMinimum(1)
        self.cycles_spinbox.setSingleStep(1)
        self.cycles_spinbox.setDisabled(True)
### ### toolButtons groupbox
        self.toolBox_boxlayout = QHBoxLayout()
        self.toolBox_boxlayout.setSpacing(1)
        self.toolButtons_box = QGroupBox()
        self.toolBox_boxlayout.setContentsMargins(0,0,0,0)
        self.toolButtons_box.setLayout(self.toolBox_boxlayout)
        self.toolButtons_box.setVisible(False)
        self.toolButtons = []
### ### xray checkbox
        self.xray_checkbox = QCheckBox( 'X-ray' )
        self.xray_checkbox.setChecked(False)
        self.xray_checkbox.stateChanged.connect(self.toggle_xray)
        self.xray_checkbox.setDisabled(True)
        self.xray_checkbox.setVisible(False)
### ### relaxedDetection checkbox
        self.relaxedDetection_checkbox = QCheckBox( 'Relaxed' )
        self.relaxedDetection_checkbox.setChecked(False)
        self.relaxedDetection_checkbox.stateChanged.connect(self.toggle_relaxed)
        self.relaxedDetection_checkbox.setDisabled(True)
        self.relaxedDetection_checkbox.setVisible(False)
### ### altAlgorithm checkbox
        self.altAlgorithm_checkbox = QCheckBox( 'bTriangle' )
        self.altAlgorithm_checkbox.setChecked(False)
        self.altAlgorithm_checkbox.stateChanged.connect(self.toggle_algorithm)
        self.altAlgorithm_checkbox.setDisabled(True)
        self.altAlgorithm_checkbox.setVisible(False)
### ### detectOn checkbox
        self.detectOn_checkbox = QCheckBox( 'Detect ON' )
        self.detectOn_checkbox.setChecked(False)
        self.detectOn_checkbox.stateChanged.connect(self.toggle_detection)
        self.detectOn_checkbox.setDisabled(True)
### ### instructionsPanel box
        self.instructionsPanel_layout = QGridLayout()
        self.instructionsPanel_layout.setSpacing(0)
        self.instructionsPanel_layout.setContentsMargins(0,10,0,0)
        self.instructionsPanel_layout.setColumnMinimumWidth(0,180)
        self.instructionsPanel_layout.setColumnStretch(0,0)
        self.instructionsPanel_box = QGroupBox( 'Instructions' )
        self.instructionsPanel_box.setObjectName( 'instructionsPanel_box' )
        self.instructionsPanel_box.setContentsMargins(0,0,0,0)
        self.instructionsPanel_box.setLayout(self.instructionsPanel_layout)
        self.instructions_text = QLabel( 'Welcome to TAMV.<br>Please connect to your printer.',objectName="instructions_text")
        self.instructions_text.setContentsMargins(12,5,12,5)
        self.instructions_text.setWordWrap(True)
        self.instructionsPanel_layout.addWidget(self.instructions_text, 0, 0)
### ### mainSidebar panel
        self.mainSidebar_panel = QTabWidget()
        self.mainSidebar_panel.setDisabled(True)
        self.mainSidebar_panel.setCurrentIndex(0)
### ### # jogPanel tab
        self.jogPanel_tab = QGroupBox( 'Jog Panel' )
        self.jogPanel_tab.layout = QGridLayout()
        self.buttons_layout = QGridLayout()
        self.buttons_layout.setSpacing(1)
        self.jogPanel_tab.setLayout(self.buttons_layout)
        self.mainSidebar_panel.addTab( self.jogPanel_tab, "Jog Panel" )
### ### ## setup button properties
        # Set font size
        self.panel_font = QFont()
        self.panel_font.setPixelSize(35)
        # set button sizing
        self.button_width = 50
        self.button_height = 50
        if self.small_display:
            self.button_height = 50
            self.button_width = 50
### ### ## create jogPanel buttons
### ### ### increment size
        self.button_1 = QPushButton( '1' )
        self.button_1.setFixedSize(self.button_width,self.button_height)
        self.button_1.setMaximumHeight( self.button_height )
        self.button_1.setFont( self.panel_font )
        self.button_01 = QPushButton( '0.1' )
        self.button_01.setFixedSize(self.button_width,self.button_height)
        self.button_01.setMaximumHeight( self.button_height )
        self.button_01.setFont( self.panel_font )
        self.button_001 = QPushButton( '0.01' )
        self.button_001.setFixedSize(self.button_width,self.button_height)
        self.button_001.setMaximumHeight( self.button_height )
        self.button_001.setFont( self.panel_font )
        self.incrementButtonGroup = QButtonGroup()
        self.incrementButtonGroup.addButton(self.button_1)
        self.incrementButtonGroup.addButton(self.button_01)
        self.incrementButtonGroup.addButton(self.button_001)
        self.incrementButtonGroup.setExclusive(True)
        self.button_1.setCheckable(True)
        self.button_01.setCheckable(True)
        self.button_001.setCheckable(True)
        self.button_1.setChecked(True)
### ### ### X movement
        self.button_x_left = QPushButton( '-', objectName='plus' )
        self.button_x_left.setFixedSize(self.button_width,self.button_height)
        self.button_x_left.setMaximumHeight( self.button_height )
        self.button_x_left.setFont( self.panel_font )
        self.button_x_right = QPushButton( '+', objectName='plus' )
        self.button_x_right.setFixedSize(self.button_width,self.button_height)
        self.button_x_right.setMaximumHeight( self.button_height )
        self.button_x_right.setFont( self.panel_font )
        self.button_x_left.clicked.connect(lambda: self.jogPanelButton_clickHandler( 'x_left' ))
        self.button_x_right.clicked.connect(lambda: self.jogPanelButton_clickHandler( 'x_right' ))
        self.x_label = QLabel( 'X' )
        self.x_label.setObjectName( 'labelPlus' )
        self.x_label.setAlignment(Qt.AlignCenter |Qt.AlignVCenter)
### ### ### Y movement
        self.button_y_left = QPushButton( '-', objectName='plus' )
        self.button_y_left.setFixedSize(self.button_width,self.button_height)
        self.button_y_left.setMaximumHeight( self.button_height )
        self.button_y_left.setFont( self.panel_font )
        self.button_y_right = QPushButton( '+', objectName='plus' )
        self.button_y_right.setFixedSize(self.button_width,self.button_height)
        self.button_y_right.setMaximumHeight( self.button_height )
        self.button_y_right.setFont( self.panel_font )
        self.button_y_left.clicked.connect(lambda: self.jogPanelButton_clickHandler( 'y_left' ))
        self.button_y_right.clicked.connect(lambda: self.jogPanelButton_clickHandler( 'y_right' ))
        self.y_label = QLabel( 'Y' )
        self.y_label.setObjectName( 'labelPlus' )
        self.y_label.setAlignment(Qt.AlignCenter |Qt.AlignVCenter)
### ### ### Z movement
        self.button_z_down = QPushButton( '-', objectName='plus' )
        self.button_z_down.setFont(self.panel_font)
        self.button_z_down.setFixedSize(self.button_width,self.button_height)
        self.button_z_down.setMaximumHeight( self.button_height )
        self.button_z_up = QPushButton( '+', objectName='plus' )
        self.button_z_up.setFont(self.panel_font)
        self.button_z_up.setFixedSize(self.button_width,self.button_height)
        self.button_z_up.setMaximumHeight( self.button_height )
        self.button_z_down.clicked.connect(lambda: self.jogPanelButton_clickHandler( 'z_down' ))
        self.button_z_up.clicked.connect(lambda: self.jogPanelButton_clickHandler( 'z_up' ))
        self.z_label = QLabel( 'Z' )
        self.z_label.setObjectName( 'labelPlus' )
        self.z_label.setAlignment(Qt.AlignCenter |Qt.AlignVCenter) 
### ### ## layout jogPanel buttons
        self.buttons_layout.addWidget(self.x_label,1,0)
        self.buttons_layout.addWidget(self.y_label,2,0)
        self.buttons_layout.addWidget(self.z_label,3,0)
        # add increment buttons
        self.buttons_layout.addWidget(self.button_001,0,0)
        self.buttons_layout.addWidget(self.button_01,0,1)
        self.buttons_layout.addWidget(self.button_1,0,2)
        # add X movement buttons
        self.buttons_layout.addWidget(self.button_x_left,1,1)
        self.buttons_layout.addWidget(self.button_x_right,1,2)
        # add Y movement buttons
        self.buttons_layout.addWidget(self.button_y_left,2,1)
        self.buttons_layout.addWidget(self.button_y_right,2,2)
        # add Z movement buttons
        self.buttons_layout.addWidget(self.button_z_down,3,1)
        self.buttons_layout.addWidget(self.button_z_up,3,2)
### ### # toolInfo tab
        self.toolInfo_tab =QWidget()
        self.mainSidebar_panel.addTab( self.toolInfo_tab, "Tools")

### # Layout GUI elements
        # create a grid box layout
        grid = QGridLayout()
        grid.setSpacing(3)
        
        ################################################### ELEMENT POSITIONING ###################################################
        # row, col, rowSpan, colSpan, alignment
        ###################################################
        # Spacers        
        grid.addItem( QSpacerItem( 1, 1, QSizePolicy.Preferred, QSizePolicy.Expanding  ), 0, 1 )
        grid.addItem( QSpacerItem( 1, 1, QSizePolicy.Preferred, QSizePolicy.Expanding  ), 7+2, 1 )
        grid.addItem( QSpacerItem( 1, 1, QSizePolicy.Preferred, QSizePolicy.Expanding  ), 1, 0 )
        grid.addItem( QSpacerItem( 1, 1, QSizePolicy.Preferred, QSizePolicy.Expanding  ), 1, 7+2 )

        ###################################################
        # First container
        # connect button
        grid.addWidget( self.connect_button,     1,  1,  1,  1,  Qt.AlignLeft )
        # detect checkbox
        grid.addWidget( self.detectOn_checkbox,            1,  2,  1,  1,  Qt.AlignLeft )
        # xray checkbox
        grid.addWidget( self.xray_checkbox,              1,  3,  1,  1,  Qt.AlignLeft )
        # loose detection checkbox
        grid.addWidget( self.relaxedDetection_checkbox,             1,  4,  1,  1,  Qt.AlignLeft )
        # Alternative algorithm checkbox
        grid.addWidget( self.altAlgorithm_checkbox,         1,  6,  1,  -1,  Qt.AlignLeft )
        # disconnect button
        grid.addWidget( self.disconnect_button,  1,  7,  1,  1, Qt.AlignCenter )
        
        ###################################################
        # Second container
        # main image viewer
        grid.addWidget( self.image_label,           2,  1,  5,  6,  Qt.AlignLeft )
        # Jog Panel
        grid.addWidget(self.mainSidebar_panel,              2,  7,  1,  1,  Qt.AlignCenter | Qt.AlignTop )
        # tool selection table
        grid.addWidget( self.toolButtons_box,              3,  7,  1,  1,  Qt.AlignCenter | Qt.AlignTop )
        # instruction box
        grid.addWidget( self.instructionsPanel_box,      4,  7,  1,  1,  Qt.AlignCenter | Qt.AlignTop )
        # conditional exit button
        if self.small_display:
            grid.addWidget( self.exit_button,       5,  7,  1,  1,  Qt.AlignCenter | Qt.AlignBottom )
        # debug window button
        grid.addWidget( self.debugInfo_button,          6,  7,  1,  1,  Qt.AlignCenter | Qt.AlignBottom )
        
        ###################################################
        # Third container
        # set control point button
        grid.addWidget( self.controlPoint_button,             7,  1,  1,  1,  Qt.AlignLeft )
        # start calibration button
        grid.addWidget( self.calibration_button,    7,  2,  1,  1,  Qt.AlignLeft )
        # cycle repeat label
        grid.addWidget( self.cycles_label,          7,  3,  1,  1,  Qt.AlignLeft )
        # cycle repeat selector
        grid.addWidget( self.cycles_spinbox,         7,  4,  1,  1,  Qt.AlignLeft )
        # manual alignment button
        grid.addWidget( self.manualAlignment_button,         7,  6,  1,  1,  Qt.AlignLeft )
        # CP auto calibration button
        grid.addWidget( self.autoCalibrateEndstop_button, 7,  7,  1,  1,  Qt.AlignRight )
        ################################################# END ELEMENT POSITIONING #################################################

        # set the grid layout as the widgets layout
        self.centralWidget.setLayout(grid)
        
### # Start video thread
        self.startVideo()
        # flag to draw circle
        self.crosshair = False
        self.crosshair_alignment = False

### # Output welcome message
        print()
        print( '  Welcome to TAMV!' )
        print()


### main action functions
### # connect to printer
    def connectToPrinter(self):
        # temporarily suspend GUI and display status message
        self.image_label.setText( 'Waiting to connect..' )
        self.updateStatusbar( 'Please enter machine IP address or name prefixed with http(s)://' )
        self.connect_button.setDisabled(True)
        self.disconnect_button.setDisabled(True)
        self.calibration_button.setDisabled(True)
        self.controlPoint_button.setDisabled(True)
        self.mainSidebar_panel.setDisabled(True)
        self.mainSidebar_panel.setCurrentIndex(0)
        self.connection_status.setText( 'Connecting..' )
        self.connection_status.setStyleSheet(style_orange)
        self.cp_label.setText( '<b>CP:</b> <i>undef</i>' )
        self.cp_label.setStyleSheet(style_orange)
        self.cycles_spinbox.setDisabled(True)
        self.xray_checkbox.setDisabled(True)
        self.xray_checkbox.setChecked(False)
        self.xray_checkbox.setVisible(False)
        self.relaxedDetection_checkbox.setDisabled(True)
        self.relaxedDetection_checkbox.setChecked(False)
        self.relaxedDetection_checkbox.setVisible(False)
        self.altAlgorithm_checkbox.setDisabled(True)
        self.altAlgorithm_checkbox.setChecked(False)
        self.altAlgorithm_checkbox.setVisible(False)
        self.repaint()
        try:
            # check if printerURL has already been defined (user reconnecting)
            if len(self.printerURL) > 0:
                None
        except Exception:
            # printerURL initalization to defaults
            self.printerURL = 'http://localhost'
        # Prompt user for machine connection address
        # text, ok = QInputDialog.getText(self, 'Machine URL','Machine IP address or hostname: ', QLineEdit.Normal, self.printerURL)

        self.connection_dialog = ConnectionDialog(parent=self)
        self.connection_dialog.connect_printer.connect( self.updatePrinterURL )
        self.connection_dialog.new_printer.connect( self.createNewConnection )
        ok = self.connection_dialog.exec()
        if( self.newPrinter ):
            self.newPrinter = False
            self.settings_dialog = SettingsDialog(parent=self, addPrinter=True)
            self.settings_dialog.update_settings.connect( self.updateSettings )
            ok = self.settings_dialog.exec()
            if( ok ):
                text = self.options['printer'][(len(self.options['printer'])-1)]['address']
            else:
                text = ''
        else:
            text = self.printerURL

        # Handle clicking OK/Connect
        if ok and text != '' and len(text) > 5:
            ( _errCode, _errMsg, tempURL ) = self.sanitizeURL(text)
            while _errCode != 0:
                # Invalid URL detected, pop-up window to correct this
                text, ok = QInputDialog.getText(self, 'Machine URL', _errMsg + '\nMachine IP address or hostname: ', QLineEdit.Normal, text)
                if ok:
                    ( _errCode, _errMsg, tempURL ) = self.sanitizeURL(text)
                else:
                    self.updateStatusbar( 'Connection request cancelled.' )
                    self.resetConnectInterface()
                    return
            # input has been parsed and is clean, proceed
            self.printerURL = tempURL
        # Handle clicking cancel
        elif not ok:
            self.updateStatusbar( 'Connection request cancelled.' )
            self.resetConnectInterface()
            return
        # Handle invalid input
        elif len(text) < 6 or text[:4] not in ['http']:
            message = 'Invalid IP address or hostname: \"' + text +'\". Add http(s):// to try again.'
            self.updateStatusbar(message)
            self.instructions_text.setText(message)
            self.resetConnectInterface()
            return
        # Update user with new state
        self.statusBar.showMessage( 'Attempting to connect to: ' + self.printerURL )
        _logger.info( 'Attempting to connect to: ' + self.printerURL )
        # Attempt connecting to the Duet controller
        try:
            self.printer = DWA.DuetWebAPI(self.printerURL)
            if not self.printer.isIdle():
                # connection failed for some reason
                self.updateStatusbar( 'Device at '+self.printerURL+' either did not respond or is not a Duet V2 or V3 printer.' )
                _logger.info( 'Device at '+self.printerURL+' either did not respond or is not a Duet V2 or V3 printer.' )
                self.resetConnectInterface()
                return
            else:
                # connection succeeded, update objects accordingly
                _logger.info( '  .. fetching tool information..' )
                self._connected_flag = True
                self.num_tools = self.printer.getNumTools()
                self.video_thread.numTools = self.num_tools
                self.printerObject = self.printer.getJSON()
                # highest tool number storage
                numTools = max( self.printerObject['tools'], key= lambda x:int(x['number']) )['number']
                _logger.debug( 'Highest tool number is: ' + str(numTools) )
                for tool in range(numTools+1):
                    # check if current index exists in tool numbers from machine
                    # add tool buttons
                    toolButton = QPushButton( 'T' + str(tool) )
                    if( any( d.get('number', -1 ) == tool for d in self.printerObject['tools'] ) ):
                        # tool exists
                        toolButton.setToolTip( 'Fetch T' +  str(tool) + ' to current machine position.' )
                        toolButton.setObjectName( 'tool' )
                    else:
                        # tool doesn't exist, hide button
                        toolButton.setVisible(False)
                    self.toolButtons.append(toolButton)
                _logger.debug( 'Tool data and interface created successfully.' )
        except Exception as conn1:
            self.updateStatusbar( 'Cannot connect to: ' + self.printerURL )
            _logger.error( 'Cannot connect to machine: ' + str(conn1) )
            self.resetConnectInterface()
            return
        # Get active tool
        _active = self.printer.getCurrentTool()
        # Display toolbox
        for i,button in enumerate(self.toolButtons):
            button.setCheckable(True)
            if int(_active) == i:
                button.setChecked(True)
            else: 
                button.setChecked(False)
            button.clicked.connect(self.callTool)
            self.toolBox_boxlayout.addWidget(button)
        self.toolButtons_box.setVisible(True)
        # Connection succeeded, update GUI first
        self.updateStatusbar( 'Connected to a Duet V'+str(self.printer.getPrinterType()) )
        self.connect_button.setText( 'Online: ' + self.printerURL[self.printerURL.rfind( '/' )+1:])
        self.statusBar.showMessage( 'Connected to printer at ' + self.printerURL, 5000)
        self.connection_status.setText( 'Connected.' )
        self.image_label.setText( 'Set your Control Point to continue.' )
        # enable/disable buttons
        self.connect_button.setDisabled(True)
        self.calibration_button.setDisabled(True)
        self.autoCalibrateEndstop_button.setDisabled(True)
        self.disconnect_button.setDisabled(False)
        self.controlPoint_button.setDisabled(False)
        self.mainSidebar_panel.setDisabled(False)
        self.mainSidebar_panel.setCurrentIndex(0)
        
        # Issue #25: fullscreen mode menu error: can't disable items
        if not self.small_display:
            self.analysisMenu.setDisabled(True)

        # update connection status indicator to green
        self.connection_status.setStyleSheet(style_green)
        self.cp_label.setStyleSheet(style_red)

        # Update instructions box
        self.instructions_text.setText("Place endstop near center of preview window, and set your control point.")
        _logger.info( '  .. connection successful!' )
### # save user settings.json
    def saveUserSettings(self):
        global video_src
        try:
            with open( 'settings.json','w' ) as outputfile:
                json.dump(self.options, outputfile)
            new_video_src = 0
            for machine in self.options['printer']:
                try:
                    if( machine['default'] == 1 ):
                        new_video_src = machine['video_src']
                        self.video_thread.changeVideoSrc( newSrc=new_video_src )
                        video_src = new_video_src
                        break
                except KeyError as ke:
                    # No default camera defined
                    pass
            _logger.info( 'User preferences saved to settings.json' )
            self.updateStatusbar( 'User preferences saved to settings.json' )
        except Exception as e1:
            _logger.error( 'Error saving user settings file.' + str(e1) )
            self.updateStatusbar( 'Error saving user settings file.' )
### # prepare for CP capture
    def setupCP(self):
        # Check if machine is ready for movement
        if( self.checkMachine() is False ):
            # Machine isn't ready, don't do anything.
            app.processEvents()
            return
        # disable buttons for CP capture run
        self.disableButtonsCP()
        # handle scenario where machine is busy and user tries to select a tool.
        if not self.printer.isIdle():
            self.updateStatusbar( 'Machine is not idle, cannot select tool.' )
            return
        # display crosshair on video feed at center of image
        self.crosshair = True
        self.calibration_button.setDisabled(True)

        if len(self.cp_coords) > 0:
            self.printer.unloadTools()
            self.printer.moveAbsolute( moveSpeed=_moveSpeed, X=str(self.cp_coords['X']), Y=str(self.cp_coords['Y']), Z=str(self.cp_coords['Z']))
        # Enable automated button
        self.autoCalibrateEndstop_button.setDisabled(False)
        # Enable capture button
        self.manualAlignment_button.setDisabled(False)
        # Update instructions box
        self.instructions_text.setText( 'To auto-align, click \"Automated Capture\". Otherwise, use jog panel to center on crosshair and then click Capture.' )
        # wait for user to conclude with state flag
        self.flag_CP_setup = True
        return
### # start automatic CP capture
    def startAutoCPCapture(self):
        _logger.info( 'Starting automated CP capture..' )
        self.video_thread.align_endstop = True
        while self.video_thread.align_endstop and self.video_thread._running:
            app.processEvents()
        self.readyToCalibrate()
### # capture CP coordinates
    def captureControlPoint(self):
        # reset state flag
        self.flag_CP_setup = False
        # When user confirms everything is done, capture CP values and store
        self.cp_coords = self.printer.getCoordinates()
        self.cp_string = '( ' + str(self.cp_coords['X']) + ', ' + str(self.cp_coords['Y']) + ' )'
        self.cp_label.setText( '<b>CP:</b> ' + self.cp_string)
        _logger.info( 'Set Control Point: ' + self.cp_string )
        _logger.info( 'Ready for tool alignment!' )
        # Disable crosshair
        self.crosshair = False
        # Setup GUI for next step
        self.readyToCalibrate()
        # Move printer to CP to prepare for next step
        self.printer.moveAbsolute( moveSpeed=_moveSpeed, X=str(self.cp_coords['X']), Y=str(self.cp_coords['Y']) )
### # manually capture tool offset
    def captureOffset(self):
        # Check if performing CP setup
        if self.flag_CP_setup:
            try:
                self.captureControlPoint()
            except Exception:
                _logger.error( 'Capture Offset error: \n' + traceback.format_exc() )
                self.statusBar.showMessage( 'Error 1 in manual capture. Check logs.' )
                return
        else:
            # tool capture
            try:
                _logger.debug( 'Manual offset calculation starting..' )
                currentPosition = self.printer.getCoordinates()
                curr_x = currentPosition['X']
                curr_y = currentPosition['Y']
                # Get active tool
                _active = int(self.printer.getCurrentTool())
                #get tool offsets
                self.tool_offsets = self.printer.getToolOffset(_active)
                # calculate X and Y coordinates
                final_x = np.around( (self.cp_coords['X'] + self.tool_offsets['X']) - curr_x, 3 )
                final_y = np.around( (self.cp_coords['Y'] + self.tool_offsets['Y']) - curr_y, 3 )
                offsetString  = 'Tool ' + str(_active) + ' offsets:  X' + str(final_x) + ' Y' + str(final_y)
                _logger.info(offsetString)
                self.printer.setToolOffsets(tool=str(_active), X=str(final_x), Y=str(final_y) )
            except Exception:
                self.statusBar.showMessage( 'Error 2 in manual capture. Check logs.' )
                _logger.error( 'Capture Offset error 2: \n' + traceback.format_exc() )
            _logger.debug( 'Manual offset calculation ending..' )
            self.toolButtons[_active].setObjectName( 'completed' )
            self.toolButtons[_active].setStyle(self.toolButtons[_active].style())
        self.crosshair_alignment = False
        return
### # run automated tool calibration
    def runCalibration(self):
        _logger.debug( 'Calibration setup method starting.' )
        # reset debugString
        self.debugString = ''
        # prompt for user to apply results
        msgBox = QMessageBox(parent=self)
        msgBox.setIcon(QMessageBox.Information)
        msgBox.setText( 'Do you want to start automated tool alignment?' )
        msgBox.setWindowTitle( 'Start Calibration' )
        yes_button = msgBox.addButton( 'Start calibration..',QMessageBox.YesRole)
        yes_button.setObjectName( 'active' )
        yes_button.setStyleSheet(style_green)
        no_button = msgBox.addButton( 'Cancel',QMessageBox.NoRole)

        returnValue = msgBox.exec_()
        if msgBox.clickedButton() == no_button:
            return
        # close camera settings dialog so it doesn't crash
        try:
            if self.settings_dialog.isVisible():
                self.settings_dialog.reject()
        except: None
        # update GUI
        self.controlPoint_button.setDisabled(True)
        self.mainSidebar_panel.setDisabled(True)
        self.mainSidebar_panel.setCurrentIndex(0)
        self.calibration_button.setDisabled(True)
        self.xray_checkbox.setDisabled(False)
        self.xray_checkbox.setChecked(False)
        self.xray_checkbox.setVisible(True)
        self.relaxedDetection_checkbox.setDisabled(False)
        self.relaxedDetection_checkbox.setChecked(False)
        self.relaxedDetection_checkbox.setVisible(True)
        self.altAlgorithm_checkbox.setDisabled(False)
        self.altAlgorithm_checkbox.setChecked(False)
        self.altAlgorithm_checkbox.setVisible(True)
        self.toolButtons_box.setVisible(False)
        self.detectOn_checkbox.setVisible(False)
        self.autoCalibrateEndstop_button.setDisabled(True)
        _logger.debug( 'Updating tool interface..' )
        # for tool in self.printerObject['tools']:
        #     current_tool = self.printer.getToolOffset( tool['number'] ) 
        #     x_tableitem = QTableWidgetItem("{:.3f}".format(current_tool['X']))
        #     y_tableitem = QTableWidgetItem("{:.3f}".format(current_tool['Y']))
        #     x_tableitem.setBackground(QColor(255,255,255,255))
        #     y_tableitem.setBackground(QColor(255,255,255,255))
            # self.offsets_table.setVerticalHeaderItem(i,QTableWidgetItem( 'T'+str(i)))
            # self.offsets_table.setItem(i,0,x_tableitem)
            # self.offsets_table.setItem(i,1,y_tableitem)
        # get number of repeat cycles
        self.cycles_spinbox.setDisabled(True)
        self.cycles = self.cycles_spinbox.value()

        # create the Nozzle detection capture thread
        _logger.debug( 'Launching calibration threads..' )
        self.video_thread.display_crosshair = True
        self.video_thread.detection_on = True
        self.video_thread.xray = False
        self.video_thread.loose = False
        self.video_thread.alignment = True
        _logger.debug( 'Calibration setup method exiting.' )
### # apply calibration results
    def applyCalibration(self):
        # update GUI
        self.readyToCalibrate()
        # close camera settings dialog so it doesn't crash
        try:
            if self.settings_dialog.isVisible():
                self.settings_dialog.reject()
        except: None
        # prompt for user to apply results
        msgBox = QMessageBox(parent=self)
        msgBox.setIcon(QMessageBox.Information)
        msgBox.setText( 'Do you want to save the new offsets to your machine?' )
        msgBox.setWindowTitle( 'Calibration Results' )
        yes_button = msgBox.addButton( 'Apply offsets and save (M500)',QMessageBox.ApplyRole)
        yes_button.setStyleSheet(style_green)
        cancel_button = msgBox.addButton( 'Apply offsets',QMessageBox.NoRole)
        
        # Update debug string
        self.debugString += '\nCalibration results:\n'
        for result in self.calibrationResults:
            calibrationCode = 'G10 P' + str(result['tool']) + ' X' + str(result['X']) + ' Y' + str(result['Y'])
            self.debugString += calibrationCode + '\n'

        # Prompt user
        returnValue = msgBox.exec()
        if msgBox.clickedButton() == yes_button:
            for result in self.calibrationResults:
                self.printer.setToolOffsets(tool=str(result['tool']), X=str(result['X']), Y=str(result['Y']))
                self.printer.saveOffsetsToFirmware() # because of Rene.
            self.statusBar.showMessage( 'Offsets applied and stored using M500.' )
            _logger.info( 'Offsets applied to machine and stored using M500.' )
        else:
            self.statusBar.showMessage( 'Temporary offsets applied. You must manually save these offsets.' )
        # Clean up threads and detection
        self.video_thread.alignment = False
        self.video_thread.detect_on = False
        self.video_thread.display_crosshair = False
        # run stats
        self.analyzeResults()
### # disconnect from printer
    def disconnectFromPrinter(self):
        _logger.info( 'Terminating connection to machine.. ' )
        # temporarily suspend GUI and display status message
        self.image_label.setText( 'Restoring machine to initial state..' )
        self.updateStatusbar( 'Restoring machine and disconnecting...' )
        self.connect_button.setText( 'Pending..' )
        self.connect_button.setDisabled(True)
        self.disconnect_button.setDisabled(True)
        self.calibration_button.setDisabled(True)
        self.controlPoint_button.setDisabled(True)
        self.controlPoint_button.setText( 'Pending..' )
        self.mainSidebar_panel.setDisabled(True)
        self.mainSidebar_panel.setCurrentIndex(0)
        self.connection_status.setText( 'Disconnecting..' )
        self.connection_status.setStyleSheet(style_orange)
        self.cp_label.setText( '<b>CP:</b> <i>undef</i>' )
        self.cp_label.setStyleSheet(style_orange)
        self.cycles_spinbox.setDisabled(True)
        self.xray_checkbox.setDisabled(True)
        self.xray_checkbox.setChecked(False)
        self.relaxedDetection_checkbox.setDisabled(True)
        self.altAlgorithm_checkbox.setDisabled(True)
        self.toolButtons_box.setVisible(False)
        self.autoCalibrateEndstop_button.setDisabled(True)
        self.repaint()
        # End video threads and restart default thread
        # Clean up threads and detection
        # Video thread
        self.video_thread.alignment = False
        self.video_thread._running = False
        self.video_thread.detection_on = False
        self.video_thread.display_crosshair = False
        self.detectOn_checkbox.setChecked(False)
        self.detectOn_checkbox.setVisible(True)

        # update status 
        self.updateStatusbar( 'Unloading tools and disconnecting from machine..' )
        _logger.info( ' .. unloading tools..' )
        # Wait for printer to stop moving and unload tools
        _ret_error = 0
        printerDisconnected = False
        while( not printerDisconnected ):
            if self.printer.isIdle() is True:
                self.printer.flushMovementBuffer()
                tempCoords = self.printer.getCoordinates()
                if( self.printer.isHomed() ):
                    self.printer.unloadTools()
                    # return carriage to control point position
                    _logger.info( ' .. restoring position..' )
                    if len(self.cp_coords) > 0:
                        self.printer.moveAbsolute( moveSpeed=_moveSpeed, X=str(self.cp_coords['X']) )
                        self.printer.moveAbsolute( moveSpeed=_moveSpeed, Y=str(self.cp_coords['Y']) )
                        self.printer.moveAbsolute( moveSpeed=_moveSpeed, Z=str(self.cp_coords['Z']) )
                    else:
                        self.printer.moveAbsolute( moveSpeed=_moveSpeed, X=str(tempCoords['X']) )
                        self.printer.moveAbsolute( moveSpeed=_moveSpeed, Y=str(tempCoords['Y']) )
                        self.printer.moveAbsolute( moveSpeed=_moveSpeed, Z=str(tempCoords['Z']) )
                else:
                    break
                printerDisconnected = True
            else:
                _logger.debug( 'Sleeping to retry disconnect..' )
                time.sleep(0.5)
                continue
        # update status with disconnection state
        if _ret_error == 0:
            self.updateStatusbar( 'Disconnected.' )
            self.image_label.setText( 'Disconnected.' )
            self.statusBar.setStyleSheet(style_default)
            _logger.info( ' .. connection terminated.' )
        else: 
            # handle unforeseen disconnection error (power loss?)
            _logger.error('Disconnect: error communicating with machine.')
            self.statusBar.showMessage( 'Disconnect: error communicating with machine.' )
            self.statusBar.setStyleSheet(style_red)
        # Reinitialize printer object
        self.printer = None
        
        # Tools unloaded, reset GUI
        self.instructions_text.setText( 'Welcome to TAMV. Enter your printer address and click \"Connect..\" to start.' )
        self.image_label.setText( 'Welcome to TAMV. Enter your printer address and click \"Connect..\" to start.' )
        self.connect_button.setText( 'Connect..' )
        self.connect_button.setDisabled(False)
        self.disconnect_button.setDisabled(True)
        self.calibration_button.setDisabled(True)
        self.controlPoint_button.setDisabled(True)
        self.controlPoint_button.setText( 'Set Control Point..' )
        self.mainSidebar_panel.setDisabled(True)
        self.mainSidebar_panel.setCurrentIndex(0)
        self.manualAlignment_button.setDisabled(True)
        self.connection_status.setText( 'Disconnected.' )
        self.connection_status.setStyleSheet(style_red)
        self.cp_label.setText( '<b>CP:</b> <i>undef</i>' )
        self.cp_label.setStyleSheet(style_red)
        self.cycles_spinbox.setDisabled(True)
        self.xray_checkbox.setDisabled(True)
        self.relaxedDetection_checkbox.setDisabled(True)
        self.altAlgorithm_checkbox.setDisabled(True)
        self.resetConnectInterface()


### Utility functions
### # check if machine is ready to move
    def checkMachine(self):
        if( self.printer.isHomed() is False ):
            # Update status bar
            self.updateStatusbar( "One or more axes are not homed. Please re-home machine." )
            self.updateMessagebar("")
            self.statusBar.setStyleSheet(style_red)
            # Update instruction box
            self.instructions_text.setText("One or more axes are not homed. Please home your machine and retry.")
            return False
        else:
            self.statusBar.setStyleSheet(style_default)
        return True
### # load tool into machine
    def callTool(self):
        # Check if machine is ready for movement
        if( self.checkMachine() is False ):
            # Machine is not homed, don't do anything and return
            return
        self.manualAlignment_button.setDisabled(False)
        # handle scenario where machine is busy and user tries to select a tool.
        if not self.printer.isIdle():
            self.updateStatusbar( 'Machine is not idle, cannot select tool.' )
            return
        # check if machine is homed or not
        if( self.printer.isHomed() is False ):
            self.updateStatusbar( 'Machine axes have not been homed. Please re-home your machine.' )
            return
        # get current active tool
        _active = self.printer.getCurrentTool()      
        # get requested tool number
        sender = self.sender()
        # update buttons to new status
        for button in self.toolButtons:
            button.setChecked(False)
        self.toolButtons[int(self.sender().text()[1:])].setChecked(True)
        # handle tool already active on printer
        if int(_active) == int(sender.text()[1:]):
            msg = QMessageBox()
            status = msg.question( self, 'Unload ' + sender.text(), 'Unload ' + sender.text() + ' and return carriage to the current position?',QMessageBox.Yes | QMessageBox.No  )
            if status == QMessageBox.Yes:
                self.displayStandby()
                self.toolButtons[int(self.sender().text()[1:])].setChecked(False)
                if len(self.cp_coords) > 0:
                    self.printer.unloadTools()
                    self.printer.moveAbsolute( moveSpeed=_moveSpeed, X=str(self.cp_coords['X']) )
                    self.printer.moveAbsolute( moveSpeed=_moveSpeed, Y=str(self.cp_coords['Y']) )
                    self.printer.moveAbsolute( moveSpeed=_moveSpeed, Z=str(self.cp_coords['Z']) )
                else:
                    tempCoords = self.printer.getCoordinates()
                    self.printer.unloadTools()
                    self.printer.moveAbsolute( moveSpeed=_moveSpeed, X=str(tempCoords['X']) )
                    self.printer.moveAbsolute( moveSpeed=_moveSpeed, Y=str(tempCoords['Y']) )
                    self.printer.moveAbsolute( moveSpeed=_moveSpeed, Z=str(tempCoords['Z']) )
                # End video threads and restart default thread
                self.video_thread.alignment = False
                # Update GUI for unloading carriage
                self.calibration_button.setDisabled(False)
                self.controlPoint_button.setDisabled(False)
                self.updateMessagebar( 'Ready.' )
                self.updateStatusbar( 'Ready.' )
                self.displayToolLoaded(tool=-1)
            else:
                # User cancelled, do nothing
                return
        else:
            # Requested tool is different from active tool
            msg = QMessageBox()
            status = msg.question( self, 'Confirm loading ' + sender.text(), 'Load ' + sender.text() + ' and move to current position?',QMessageBox.Yes | QMessageBox.No  )
            
            if status == QMessageBox.Yes:
                self.displayStandby()
                # return carriage to control point position
                if len(self.cp_coords) > 0:
                    self.printer.unloadTools()
                    self.printer.loadTool( toolIndex=int(sender.text()[1:]) )
                    self.printer.moveAbsolute( moveSpeed=_moveSpeed, X=str(self.cp_coords['X']) )
                    self.printer.moveAbsolute( moveSpeed=_moveSpeed, Y=str(self.cp_coords['Y']) )
                    self.printer.moveAbsolute( moveSpeed=_moveSpeed, Z=str(self.cp_coords['Z']) )
                else:
                    tempCoords = self.printer.getCoordinates()
                    self.printer.unloadTools()
                    self.printer.loadTool( toolIndex=int(sender.text()[1:]) )
                    self.printer.moveAbsolute( moveSpeed=_moveSpeed, X=str(tempCoords['X']) )
                    self.printer.moveAbsolute( moveSpeed=_moveSpeed, Y=str(tempCoords['Y']) )
                    self.printer.moveAbsolute( moveSpeed=_moveSpeed, Z=str(tempCoords['Z']) )
                # START DETECTION THREAD HANDLING
                # close camera settings dialog so it doesn't crash
                try:
                    if self.settings_dialog.isVisible():
                        self.settings_dialog.reject()
                except: None
                # update GUI
                self.controlPoint_button.setDisabled(True)
                self.mainSidebar_panel.setDisabled(False)
                self.mainSidebar_panel.setCurrentIndex(0)
                self.calibration_button.setDisabled(True)
                self.cycles_spinbox.setDisabled(True)
                self.displayToolLoaded(tool=int(sender.text()[1:]))
            else:
                self.toolButtons[int(self.sender().text()[1:])].setChecked(False)
        app.processEvents()
### # convert image to Pixmap datatype
    def convert_cv_qt(self, cv_img):
        # Convert from an opencv image to QPixmap
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_Qt_format = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        p = convert_to_Qt_format.scaled(display_width, display_height, Qt.KeepAspectRatio)
        return QPixmap.fromImage(p)
### # add a new offset to calibration results
    def addCalibrationResult(self, result={}):
        self.calibrationResults.append(result)
### # event handler: jog panel click
    def jogPanelButton_clickHandler(self, buttonName):
        # Check if machine is ready for movement
        if( self.checkMachine() is False ):
            # Machine is not homed, don't do anything and return
            return
        increment_amount = 1
        # fetch current increment value
        if self.button_1.isChecked():
            increment_amount = 1
        elif self.button_01.isChecked():
            increment_amount = 0.1
        elif self.button_001.isChecked():
            increment_amount = 0.01
        # Call corresponding axis gcode command
        if buttonName == 'x_left':
            self.printer.moveRelative( moveSpeed=_moveSpeed, X=str(-1*increment_amount) )
        elif buttonName == 'x_right':
            self.printer.moveRelative( moveSpeed=_moveSpeed, X=str(increment_amount) )
        elif buttonName == 'y_left':
            self.printer.moveRelative( moveSpeed=_moveSpeed, Y=str(-1*increment_amount) )
        elif buttonName == 'y_right':
            self.printer.moveRelative( moveSpeed=_moveSpeed, Y=str(increment_amount) )
        elif buttonName == 'z_down':
            self.printer.moveRelative( moveSpeed=_moveSpeed, Z=str(-1*increment_amount) )
        elif buttonName == 'z_up':
            self.printer.moveRelative( moveSpeed=_moveSpeed, Z=str(increment_amount) )
        return
### # sanitize printer URL
    def sanitizeURL(self, inputString='http://localhost' ):
        _errCode = 0
        _errMsg = ''
        _printerURL = 'http://localhost'
        from urllib.parse import urlparse
        u = urlparse(inputString)
        scheme = u[0]
        netlocation = u[1]
        if len(scheme) < 4 or scheme.lower() not in ['http']:
            _errCode = 1
            _errMsg = 'Invalid scheme. Please only use http connections.'
        elif len(netlocation) < 1:
            _errCode = 2
            _errMsg = 'Invalid IP/network address.'
        elif scheme.lower() in ['https']:
            _errCode = 3
            _errMsg = 'Cannot use https connections for Duet controllers'
        else:
            _printerURL = scheme + '://' + netlocation
        return( _errCode, _errMsg, _printerURL )
### # display settings dialog
    def displaySettings(self):
        self.settings_dialog = SettingsDialog(parent=self, addPrinter=False)
        self.settings_dialog.update_settings.connect( self.updateSettings )
        self.settings_dialog.exec()
### # display debug dialog
    def displayDebug(self):
        dbg = DebugDialog(parent=self,message=self.debugString)
        if dbg.exec_():
            None
### # analyze calibration results
    def analyzeResults(self, graph=False, export=False):
        if len(self.calibrationResults) < 1:
            self.updateStatusbar( 'No calibration data found.' )
            return
        if graph or export:
            # get data as 3 dimensional array [tool][axis][datapoints] normalized around mean of each axis
            (numTools, totalRuns, toolData) = self.parseData(self.calibrationResults)
        else:
            # display stats to terminal
            self.stats()
        if graph:
            matplotlib.use( 'Qt5Agg',force=True)
            # set up color and colormap arrays
            colorMap = ["Greens","Oranges","Blues", "Reds"] #["Blues", "Reds","Greens","Oranges"]
            colors = ['blue','red','green','orange']
            # initiate graph data - 1 tool per column
            # Row 0: scatter plot with standard deviation box
            # Row 1: histogram of X axis data
            # Row 2: histogram of Y axis data
            
            # Set backend (if needed)
            #plt.switch_backend( 'Qt4Agg' )
            fig, axes = plt.subplots(ncols=3,nrows=numTools,constrained_layout=False)
            for i, data in enumerate(toolData):
                # create a color array the length of the number of tools in the data
                color = np.arange(len(data[0]))
                # Axis formatting
                # Major ticks
                axes[i][0].xaxis.set_major_formatter(FormatStrFormatter( '%.3f' ))
                axes[i][0].yaxis.set_major_formatter(FormatStrFormatter( '%.3f' ))
                # Minor ticks
                axes[i][0].xaxis.set_minor_formatter(FormatStrFormatter( '%.3f' ))
                axes[i][0].yaxis.set_minor_formatter(FormatStrFormatter( '%.3f' ))
                # Draw 0,0 lines
                axes[i][0].axhline()
                axes[i][0].axvline()
                # x&y std deviation box
                x_sigma = np.around(np.std(data[0]),3)
                y_sigma = np.around(np.std(data[1]),3)
                axes[i][0].add_patch(patches.Rectangle((-1*x_sigma,-1*y_sigma), 2*x_sigma, 2*y_sigma, color="green",fill=False, linestyle='dotted' ))
                axes[i][0].add_patch(patches.Rectangle((-2*x_sigma,-2*y_sigma), 4*x_sigma, 4*y_sigma, color="red",fill=False, linestyle='-.' ))
                
                # scatter plot for tool data
                axes[i][0].scatter(data[0], data[1], c=color, cmap=colorMap[i])
                axes[i][0].autoscale = True
                
                # Histogram data setup
                # Calculate number of bins per axis
                x_intervals = int(np.around(math.sqrt(len(data[0])),0)+1)
                y_intervals = int(np.around(math.sqrt(len(data[1])),0)+1)
                
                # plot histograms
                x_kwargs = dict(alpha=0.5, bins=x_intervals,rwidth=.92, density=True)
                n, bins, hist_patches = axes[i][1].hist([data[0],data[1]],**x_kwargs, color=[colors[0],colors[1]], label=['X','Y'])
                axes[i][2].hist2d(data[0], data[1], bins=x_intervals, cmap='Blues' )
                axes[i][1].legend()
                # add a 'best fit' line
                # calculate mean and std deviation per axis
                x_mean = np.mean(data[0])
                y_mean = np.mean(data[1])
                x_sigma = np.around(np.std(data[0]),3)
                y_sigma = np.around(np.std(data[1]),3)
                # calculate function lines for best fit
                x_best = ((1 / (np.sqrt(2 * np.pi) * x_sigma)) *
                    np.exp(-0.5 * (1 / x_sigma * (bins - x_mean))**2))
                y_best = ((1 / (np.sqrt(2 * np.pi) * y_sigma)) *
                    np.exp(-0.5 * (1 / y_sigma * (bins - y_mean))**2))
                # add best fit line to plots
                axes[i][1].plot(bins, x_best, '-.',color=colors[0])
                axes[i][1].plot(bins, y_best, '--',color=colors[1])
                x_count = int(sum( p == True for p in ((data[0] >= (x_mean - x_sigma)) & (data[0] <= (x_mean + x_sigma))) )/len(data[0])*100)
                y_count = int(sum( p == True for p in ((data[1] >= (y_mean - y_sigma)) & (data[1] <= (y_mean + y_sigma))) )/len(data[1])*100)
                # annotate std dev values
                annotation_text = "Xσ: " + str(x_sigma) + " ("+str(x_count) + "%)"
                if x_count < 68:
                    x_count = int(sum( p == True for p in ((data[0] >= (x_mean - 2*x_sigma)) & (data[0] <= (x_mean + 2*x_sigma))) )/len(data[0])*100) 
                    annotation_text += " --> 2σ: " + str(x_count) + "%"
                    if x_count < 95 and x_sigma*2 > 0.1:
                        annotation_text += " -- check axis!"
                    else: annotation_text += " -- OK"
                annotation_text += "\nYσ: " + str(y_sigma) + " ("+str(y_count) + "%)"
                if y_count < 68: 
                    y_count = int(sum( p == True for p in ((data[1] >= (y_mean - 2*y_sigma)) & (data[1] <= (y_mean + 2*y_sigma))) )/len(data[1])*100) 
                    annotation_text += " --> 2σ: " + str(y_count) + "%"
                    if y_count < 95 and y_sigma*2 > 0.1:
                        annotation_text += " -- check axis!"
                    else: annotation_text += " -- OK"
                axes[i][0].annotate(annotation_text, (10,10),xycoords='axes pixels' )
                axes[i][0].annotate( 'σ',(1.1*x_sigma,-1.1*y_sigma),xycoords='data',color='green' )
                axes[i][0].annotate( '2σ',(1.1*2*x_sigma,-1.1*2*y_sigma),xycoords='data',color='red' )
                # # place title for graph
                axes[i][0].set_ylabel("Tool " + str(i) + "\nY")
                axes[i][0].set_xlabel("X")
                axes[i][2].set_ylabel("Y")
                axes[i][2].set_xlabel("X")
                
                if i == 0:
                    axes[i][0].set_title( 'Scatter Plot' )
                    axes[i][1].set_title( 'Histogram' )
                    axes[i][2].set_title( '2D Histogram' )
            plt.tight_layout()
            figManager = plt.get_current_fig_manager()
            figManager.window.showMaximized()
            plt.ion()
            plt.show()
        if export:
            # export JSON data to file
            try:
                self.calibrationResults.append({ "printer":self.printerURL, "datetime":datetime.now() })
                with open( 'output.json','w' ) as outputfile:
                    json.dump(self.calibrationResults, outputfile)
            except Exception as e1:
                _logger.error( 'Failed to export alignment data:' + str(e1) )
                self.updateStatusbar( 'Error exporting data, please check terminal for details.' )
### # parse raw data for analysis
    def parseData( self, rawData ):
        # create empty output array
        toolDataResult = []
        # get number of tools
        _numTools = np.max([ int(line['tool']) for line in rawData ]) + 1
        _cycles = np.max([ int(line['cycle']) for line in rawData ])
        
        for i in range(_numTools):
            x = [float(line['X']) for line in rawData if int(line['tool']) == i]
            y = [float(line['Y']) for line in rawData if int(line['tool']) == i]
            # variable to hold return data coordinates per tool formatted as a 2D array [x_value, y_value]
            tempPairs = []

            # calculate stats
            # mean values
            x_mean = np.around(np.mean(x),3)
            y_mean = np.around(np.mean(y),3)
            # median values
            x_median = np.around(np.median(x),3)
            y_median = np.around(np.median(y),3)
            # ranges (max - min per axis)
            x_range = np.around(np.max(x) - np.min(x),3)
            y_range = np.around(np.max(y) - np.min(y),3)
            # standard deviations
            x_sig = np.around(np.std(x),3)
            y_sig = np.around(np.std(y),3)

            # normalize data around mean
            x -= x_mean
            y -= y_mean
            
            # temporary object to append coordinate pairs into return value
            tempPairs.append(x)
            tempPairs.append(y)

            # add data to return object
            toolDataResult.append(tempPairs)
        # return dataset
        return ( _numTools, _cycles, toolDataResult )
### # format stats output
    def stats(self):
        ###################################################################################
        # Report on repeated executions
        ###################################################################################
        print( '' )
        print( 'Repeatability statistics for '+str(self.cycles)+' repeats:' )
        print( '+-------------------------------------------------------------------------------------------------------+' )
        print( '|   |                   X                             |                        Y                        |' )
        print( '| T |   Avg   |   Max   |   Min   |  StdDev |  Range  |   Avg   |   Max   |   Min   |  StdDev |  Range  |' )
        for myTool in self.printerObject['tools']:
            # create array of results for current tool
            _rawCalibrationData = [line for line in self.calibrationResults if line['tool'] == str(myTool['number'])]
            x_array = [float(line['X']) for line in _rawCalibrationData]
            y_array = [float(line['Y']) for line in _rawCalibrationData]
            mpp_value = np.average([float(line['mpp']) for line in _rawCalibrationData])
            cycles = np.max(
                [float(line['cycle']) for line in _rawCalibrationData]
            )
            x_avg = np.average(x_array)
            y_avg = np.average(y_array)
            x_min = np.min(x_array)
            y_min = np.min(y_array)
            x_max = np.max(x_array)
            y_max = np.max(y_array)
            x_std = np.std(x_array)
            y_std = np.std(y_array)
            x_ran = x_max - x_min
            y_ran = y_max - y_min
            print( '| {0:1.0f} '.format(int(myTool['number'])) 
                + '| {0:7.3f} '.format(x_avg)
                + '| {0:7.3f} '.format(x_max)
                + '| {0:7.3f} '.format(x_min)
                + '| {0:7.3f} '.format(x_std)
                + '| {0:7.3f} '.format(x_ran)
                + '| {0:7.3f} '.format(y_avg)
                + '| {0:7.3f} '.format(y_max)
                + '| {0:7.3f} '.format(y_min)
                + '| {0:7.3f} '.format(y_std)
                + '| {0:7.3f} '.format(y_ran)
                + '|'
            )        
        print( '+-------------------------------------------------------------------------------------------------------+' )
        print( 'Note: Repeatability cannot be better than one pixel (MPP=' + str(mpp_value) + ' ).' )


### GUI update helper functions
### # reset connection to default state
    def resetConnectInterface(self):
        self.connect_button.setDisabled(False)
        self.disconnect_button.setDisabled(True)
        self.calibration_button.setDisabled(True)
        self.controlPoint_button.setDisabled(True)
        self.mainSidebar_panel.setDisabled(True)
        self.mainSidebar_panel.setCurrentIndex(0)
        self.connection_status.setText( 'Disconnected' )
        self.connection_status.setStyleSheet(style_red)
        self.cp_label.setText( '<b>CP:</b> <i>undef</i>' )
        self.cp_label.setStyleSheet(style_red)
        self.cycles_spinbox.setDisabled(True)
        if not self.small_display:
            self.analysisMenu.setDisabled(True)
        self.detectOn_checkbox.setChecked(False)
        self.detectOn_checkbox.setDisabled(True)
        self.xray_checkbox.setDisabled(True)
        self.xray_checkbox.setChecked(False)
        self.xray_checkbox.setVisible(False)
        self.relaxedDetection_checkbox.setDisabled(True)
        self.relaxedDetection_checkbox.setChecked(False)
        self.relaxedDetection_checkbox.setVisible(False)
        self.altAlgorithm_checkbox.setDisabled(True)
        self.altAlgorithm_checkbox.setChecked(False)
        self.altAlgorithm_checkbox.setVisible(False)
        self.video_thread.detection_on = False
        self.video_thread.loose = False
        self.video_thread.xray = False
        self.video_thread.alignment = False
        self.autoCalibrateEndstop_button.setDisabled(True)
        self.crosshair = False
        self.statusBar.setStyleSheet(style_default)
        self.instructions_text.setText("Please enter your printer address and click \"Connect..\" to start.")
        index = self.toolBox_boxlayout.count()-1
        while index >= 0:
            curWidget = self.toolBox_boxlayout.itemAt(index).widget()
            curWidget.setParent(None)
            index -= 1
        self.toolButtons_box.setVisible(False)
        self.toolButtons = []
        self.repaint()
### # disable CP buttons
    def disableButtonsCP(self):
        for item in self.toolButtons:
            item.setDisabled(True)
        self.controlPoint_button.setDisabled(True)
### # apply interface ready to calibrate state
    def readyToCalibrate(self):
        for item in self.toolButtons:
            item.setDisabled(False)
        self.manualAlignment_button.setDisabled(True)
        self.statusBar.showMessage( 'Control Point coordinates saved.',3000)
        self.image_label.setText( 'Control Point set. Click \"Start Tool Alignment\" to calibrate..' )
        self.controlPoint_button.setText( 'Set new control point.. ' )
        #self.cp_label.setText( '<b>CP:</b> ' + self.cp_string)
        self.cp_label.setStyleSheet(style_green)
        self.detectOn_checkbox.setChecked(False)
        self.detectOn_checkbox.setDisabled(False)
        self.detectOn_checkbox.setVisible(True)
        self.xray_checkbox.setDisabled(True)
        self.xray_checkbox.setChecked(False)
        self.xray_checkbox.setVisible(False)
        self.relaxedDetection_checkbox.setDisabled(True)
        self.relaxedDetection_checkbox.setChecked(False)
        self.relaxedDetection_checkbox.setVisible(False)
        self.altAlgorithm_checkbox.setDisabled(True)
        self.altAlgorithm_checkbox.setChecked(False)
        self.altAlgorithm_checkbox.setVisible(False)
        self.video_thread.detection_on = False
        self.video_thread.loose = False
        self.video_thread.xray = False
        self.video_thread.alignment = False
        self.calibration_button.setDisabled(False)
        self.controlPoint_button.setDisabled(False)
        self.autoCalibrateEndstop_button.setDisabled(True)

        self.toolButtons_box.setVisible(True)
        self.cycles_spinbox.setDisabled(False)

        if len(self.calibrationResults) > 1:
            # Issue #25: fullscreen mode menu error: can't disable items
            if not self.small_display:
                self.analysisMenu.setDisabled(False)
        else:
            # Issue #25: fullscreen mode menu error: can't disable items
            if not self.small_display:
                self.analysisMenu.setDisabled(True)
### # toggle detection
    def toggle_detection(self):
        self.video_thread.display_crosshair = not self.video_thread.display_crosshair
        self.video_thread.detection_on = not self.video_thread.detection_on
        self.crosshair_alignment = not self.crosshair_alignment
        if self.video_thread.detection_on:
            self.xray_checkbox.setDisabled(False)
            self.xray_checkbox.setVisible(True)
            self.relaxedDetection_checkbox.setDisabled(False)
            self.relaxedDetection_checkbox.setVisible(True)
            self.altAlgorithm_checkbox.setDisabled(False)
            self.altAlgorithm_checkbox.setVisible(True)
        else:
            self.xray_checkbox.setDisabled(True)
            self.xray_checkbox.setVisible(False)
            self.relaxedDetection_checkbox.setDisabled(True)
            self.relaxedDetection_checkbox.setVisible(False)
            self.altAlgorithm_checkbox.setDisabled(True)
            self.altAlgorithm_checkbox.setVisible(False)
            self.updateStatusbar( 'Detection: OFF' )
### # enable xray output
    def toggle_xray(self):
        try:
            self.video_thread.toggleXray()
        except Exception as e1:
            self.updateStatusbar( 'Detection thread not running.' )
            _logger.error( 'Detection thread error in XRAY: ' +  str(e1) )
### # toggle relaxed detection
    def toggle_relaxed(self):
        try:
            self.video_thread.toggleLoose()
        except Exception as e1:
            self.updateStatusbar( 'Detection thread not running.' )
            _logger.error( 'Detection thread error in LOOSE: ' + str(e1) )
### # toggle alternative algorithm
    def toggle_algorithm( self ):
        try:
            self.video_thread.toggleAlgorithm()
        except Exception as e1:
            self.updateStatusbar('Alternative detection algorithm not active.')
            _logger.error('Alternative algorithm error: ' + str(e1) )
### # display standby image
    def displayStandby( self ):
        self.image_label.setPixmap(self.standbyImage)
        standbyMessage = 'Changing tools, please stand by..'
        self.updateStatusbar( standbyMessage )
        self.image_label.setText( standbyMessage )
        app.processEvents()
        return
### # display tool number on GUI
    def displayToolLoaded( self, tool ):
        if( tool == -1 ):
            standbyMessage = 'Tools unloaded from machine.'
        else:
            standbyMessage = 'T' + str(tool) + ' loaded.'
        self.updateStatusbar( standbyMessage )
        self.updateMessagebar( standbyMessage )
        app.processEvents()
        return


### slot/signal handlers
### # update statusBar
    @pyqtSlot(str)
    def updateStatusbar(self, statusCode ):
        self.statusBar.showMessage(statusCode)
### # update MessageBar
    @pyqtSlot(str)
    def updateMessagebar(self, statusCode ):
        self.image_label.setText(statusCode)
### # switch crosshair
    @pyqtSlot(bool)
    def updateCrosshairDisplay( self, crosshair_flag ):
        self.crosshair_alignment = crosshair_flag
        self.crosshair = crosshair_flag
### # update image display
    @pyqtSlot(np.ndarray)
    def update_image(self, cv_img):
        #self.mutex.lock()
        self.current_frame = cv_img
        # Draw crosshair alignment circle on image if required
        if( self.crosshair or self.crosshair_alignment ):
            alpha = 0.8
            beta = 1-alpha
            center = ( int(camera_width/2), int(camera_height/2) )
            overlayCircle = cv2.circle( 
                cv_img.copy(), 
                center, 
                6, 
                (0,255,0), 
                int( camera_width/1.75 )
            )
            overlayCircle = cv2.circle( 
                overlayCircle.copy(), 
                center, 
                5, 
                (0,0,255), 
                2
            )
            for i in range(0,8):
                overlayCircle = cv2.circle( 
                overlayCircle.copy(), 
                center, 
                25*i, 
                (0,0,0), 
                1
            )
            cv_img = cv2.addWeighted(overlayCircle, beta, cv_img, alpha, 0)
            cv_img = cv2.line(cv_img, (center[0],center[1]-int( camera_width/3 )), (center[0],center[1]+int( camera_width/3 )), (128, 128, 128), 1)
            cv_img = cv2.line(cv_img, (center[0]-int( camera_width/3 ),center[1]), (center[0]+int( camera_width/3 ),center[1]), (128, 128, 128), 1)
            cv_img = cv2.addWeighted(cv_img, 1, cv_img, 0, 0)
        
        # Updates the image_label with a new opencv image
        qt_img = self.convert_cv_qt(cv_img)
        self.image_label.setPixmap(qt_img)
        #self.mutex.unlock()
### # update CP label
    @pyqtSlot(object)
    def update_cpLabel( self, newCoords ):
        self.cp_coords = newCoords
        self.cp_string = '( ' + str(self.cp_coords['X']) + ', ' + str(self.cp_coords['Y']) + ' )'
        self.cp_label.setText( '<b>CP:</b> ' + self.cp_string)
### # update saved settings.json
    @pyqtSlot( object )
    def updateSettings( self, settingOptions ):
        self.options = settingOptions
        self.saveUserSettings()
### # update active printer URL
    @pyqtSlot( int )
    def updatePrinterURL( self, index ):
        self.printerURL = self.options['printer'][index]['address']
        _logger.info('URL updated to: ' + self.options['printer'][index]['address'])
### # create a new connection profile from ConnectionSettings event
    @pyqtSlot()
    def createNewConnection( self ):
        _logger.info('Create a new connection')
        self.newPrinter = True


### thread control functions
### # start video thread
    def startVideo(self):
        _logger.info( '  .. starting video feed.. ' )
        # create the video capture thread
        self.video_thread = CalibrateNozzles(parentTh=self,numTools=0, cycles=1, align=False)
        # connect its signal to the update_image slot
        self.video_thread.detection_error.connect(self.updateStatusbar)
        self.video_thread.status_update.connect(self.updateStatusbar)
        self.video_thread.message_update.connect(self.updateMessagebar)
        self.video_thread.change_pixmap_signal.connect(self.update_image)
        self.video_thread.calibration_complete.connect(self.applyCalibration)
        self.video_thread.result_update.connect(self.addCalibrationResult)
        self.video_thread.crosshair_display.connect(self.updateCrosshairDisplay)
        self.video_thread.update_cpLabel.connect(self.update_cpLabel)
        # start the thread
        self.video_thread.start()
### # stop video thread
    def stopVideo(self):
        _logger.info( ' .. stopping video feed..' )
        try:
            if self.video_thread.isRunning():
                self.video_thread.stop()
        except Exception as vs2:
            self.updateStatusbar( 'Error 0x03: cannot stop video.' )
            _logger.error( 'Cannot stop video capture: ' + str(vs2) )
            _logger.error( 'Capture Offset error: \n' + traceback.format_exc() )
### # stop program and exit
    def closeEvent(self, event):
        try:
            if( self.printer is not None ):
                self.disconnectFromPrinter()
        except Exception:
            _logger.critical( 'Close event error: \n' + traceback.format_exc() )
        _logger.debug( 'Terminating video thread..' )
        self.video_thread.terminate()
        _logger.debug( 'Waiting for video thread to exit..' )
        self.video_thread.wait()
        _logger.debug( 'TAMV exiting..' )
        print()
        print( 'Thank you for using TAMV!' )
        print( 'Check out www.jubilee3d.com' )
        event.accept()
        sys.exit(0)
##############################################################################################################################################################
##############################################################################################################################################################
## Main program
if __name__=='__main__':
### - Setup global debugging flags for imports
    os.putenv("QT_LOGGING_RULES","qt5ct.debug=false")
    matplotlib.use('Qt5Agg',force=True)

### Setup argmument parser
    # Setup CLI argument parsers
    parser = argparse.ArgumentParser(description='Program to allign multiple tools on Duet/klipper based printers, using machine vision.', allow_abbrev=False)
    parser.add_argument('-d','--debug',action='store_true',help='Enable debug output to terminal')
    # Execute argument parser
    args=vars(parser.parse_args())
    
### Setup logging
    _logger = logging.getLogger("TAMV")
    _logger.setLevel(logging.DEBUG)
### # file handler logging
    file_formatter = logging.Formatter( '%(asctime)s - %(levelname)s - %(name)s - %(funcName)s (%(lineno)d) - %(message)s' )
    fh = logging.FileHandler( 'TAMV.log' )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(file_formatter)
    _logger.addHandler(fh)
### # console handler logging
    console_formatter = logging.Formatter(fmt='%(levelname)-9s: %(message)s' )
    ch = logging.StreamHandler()
    if( args['debug'] ):
        ch.setLevel(logging.DEBUG)
    else:
        ch.setLevel(logging.INFO)
    ch.setFormatter(console_formatter)
    _logger.addHandler(ch)
    
### # log startup messages
    _logger.debug( 'TAMV starting..' )
    _logger.warning( 'This is an alpha release. Always use only when standing next to your machine and ready to hit EMERGENCY STOP.')
    
### start GUI application
    app = QApplication(sys.argv)
    a = App()
    a.show()
    sys.exit(app.exec_())
