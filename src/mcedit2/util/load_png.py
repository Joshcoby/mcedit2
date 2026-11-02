import functools
import os
from OpenGL import GL
from mcedit2.qt import QtGui
from mcedit2.qt import QtGui
import numpy
from mcedit2.util import glutils
from mcedit2.util.resources import resourcePath

__author__ = 'Rio'


def loadPNGTexture(filename, *a, **kw):
    try:
        w, h, ndata = loadPNGFile(filename)
        tex = glutils.Texture(name=os.path.basename(filename), image=ndata.ravel(),
                              width=w, height=h, *a, **kw)
        return tex
    except Exception as e:
        print(("Exception loading ", filename, ": ", repr(e)))
        return glutils.Texture()


def loadPNGImage(img):
    # Same conversion QGLWidget.convertToGLFormat did: RGBA byte order, rows flipped to GL's bottom-up order
    glImg = img.convertToFormat(QtGui.QImage.Format.Format_RGBA8888).mirrored(False, True)
    if glImg.isNull():
        raise ValueError("Loading png file %s: Conversion to GL format failed." % img)

    w = glImg.width()
    h = glImg.height()
    b = glImg.depth() // 8
    ndata = numpy.frombuffer(glImg.constBits(), dtype='uint8')[:w * h * b].copy()

    assert len(ndata) == w * h * b
    return w, h, ndata.reshape((h, w, b))


def loadPNGData(data):
    img = QtGui.QImage.fromData(data)
    return loadPNGImage(img)


def loadPNGFile(filename):
    img = QtGui.QImage()
    if not os.path.isabs(filename):
        filename = resourcePath("mcedit2/assets/mcedit2/textures/%s" % filename)

    if not img.load(filename):
        raise IOError("Failed to read PNG file " + filename)
    return loadPNGImage(img)
