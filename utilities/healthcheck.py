#!/usr/bin/env python3
# TAMV prerequisites testing script
#
# Used to check python environment for issues with TAMV dependencies
#
# TAMV originally Copyright (C) 2020 Danal Estes all rights reserved.
# TAMV 2.0 Copyright (C) 2021 Haytham Bennani all rights reserved.
# Released under The MIT License. Full text available via https://opensource.org/licenses/MIT
#
# Requires running via the OpenCV installed python (that is why no shebang)

# Imports

# Core imports
import os
import sys
import cv2
import numpy as np
import math
from time import sleep, time
import datetime
import json
import time

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