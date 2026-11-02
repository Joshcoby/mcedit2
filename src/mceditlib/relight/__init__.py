"""
    __init__
"""

import logging

log = logging.getLogger(__name__)

updateLightsByCoord = updateLightsInSelection = NotImplemented


def setMethod(name):
    if name == "pure":
        from mceditlib.relight import pure_python
        setModule(pure_python)
    if name == "cython":
        from mceditlib.relight import with_cython
        setModule(with_cython)
    if name == "setBlocks":
        from mceditlib.relight import with_setblocks
        setModule(with_setblocks)
    if name == "sections":
        from mceditlib.relight import with_sections
        setModule(with_sections)


def setModule(mod):
    global updateLightsByCoord, updateLightsInSelection
    updateLightsByCoord = mod.updateLightsByCoord
    updateLightsInSelection = mod.updateLightsInSelection

try:
    setMethod("cython")
except ImportError:
    # The Cython relighter is disabled on the Python 3 / Cython 3 port until it is rewritten
    # for the palette-based block model. Fall back to the slower pure-Python implementation.
    setMethod("setBlocks")
