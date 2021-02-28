# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

import os
import sys
QIPLIBPATH = os.path.dirname(__file__)
# Remove QIPLIBPATH to allow running tools of that directory or within
# Just import qip early
sys.path = [e for e in sys.path if e != QIPLIBPATH]
