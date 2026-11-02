"""
    qglcontext

    OpenGL context setup and validation.

    Qt 6 has no QGLWidget; MCEdit2's views are QOpenGLWidgets. A QOpenGLWidget only gets a GL context
    once it has been shown, but MCEdit2 uploads textures and buffers (and deallocates them) at times
    when no view is visible. To support this, we keep one offscreen QOpenGLContext that shares its
    objects (textures, buffers, display lists) with every widget context. This relies on
    Qt.AA_ShareOpenGLContexts being set before the QApplication is created (see mcedit2.main).
"""
from __future__ import absolute_import, division, print_function
from OpenGL import GL
from mcedit2.qt import QtCore, QtGui
import logging
import re

log = logging.getLogger(__name__)

_lastAcquiredContextInfo = None

_sharedContext = None
_offscreenSurface = None


def getContextInfo():
    return _lastAcquiredContextInfo


def setDefaultFormat():
    """
    Request a legacy-compatible OpenGL context (MCEdit2's renderer uses the fixed-function pipeline
    and client-side vertex arrays). No profile is requested, so desktop drivers that offer a
    compatibility profile give us the highest available compatibility context.
    """
    fmt = QtGui.QSurfaceFormat()
    fmt.setRenderableType(QtGui.QSurfaceFormat.RenderableType.OpenGL)
    fmt.setVersion(2, 1)
    fmt.setProfile(QtGui.QSurfaceFormat.OpenGLContextProfile.NoProfile)
    fmt.setDepthBufferSize(24)
    fmt.setSwapBehavior(QtGui.QSurfaceFormat.SwapBehavior.DoubleBuffer)
    QtGui.QSurfaceFormat.setDefaultFormat(fmt)


def _ensureSharedContext():
    global _sharedContext, _offscreenSurface
    if _sharedContext is not None:
        return
    context = QtGui.QOpenGLContext()
    shareContext = QtGui.QOpenGLContext.globalShareContext()
    if shareContext is not None:
        context.setShareContext(shareContext)
    context.setFormat(QtGui.QSurfaceFormat.defaultFormat())
    if not context.create():
        raise RuntimeError("Could not create an OpenGL context.")
    surface = QtGui.QOffscreenSurface()
    surface.setFormat(context.format())
    surface.create()
    _sharedContext = context
    _offscreenSurface = surface


def makeSharedContextCurrent():
    """
    Make the offscreen shared context current. Use when no widget context is available yet.
    """
    _ensureSharedContext()
    if not _sharedContext.makeCurrent(_offscreenSurface):
        raise RuntimeError("Could not make the shared OpenGL context current.")


def doneSharedContext():
    if _sharedContext is not None:
        _sharedContext.doneCurrent()


def _decode(s):
    return s.decode("latin-1") if isinstance(s, bytes) else s


def validateCurrentContext():
    """
    Validate the currently-current OpenGL context, log its details, and show an error
    (then exit) if it can't be used.
    """
    context = QtGui.QOpenGLContext.currentContext()
    actualFormat = context.format()

    # Check GL_VERSION itself rather than the QSurfaceFormat's reported version, which is not reliable on all platforms.
    version = _decode(GL.glGetString(GL.GL_VERSION))
    match = re.match(r'^(\d+)\.(\d+)', version)
    major, minor = (int(x) for x in match.groups())

    detailedText = "Obtained a GL context with this format:\n"
    detailedText += "Valid: %s\n" % (context.isValid(),)
    detailedText += "Version: %s.%s\n" % (actualFormat.majorVersion(), actualFormat.minorVersion())
    detailedText += "Depth buffer: %s\n" % (actualFormat.depthBufferSize(), )
    detailedText += "Swap behavior: %s\n" % (actualFormat.swapBehavior(), )
    detailedText += "Rendering profile: %s\n" % (actualFormat.profile(), )
    detailedText += "\n"
    detailedText += "Driver info:\n"
    detailedText += "GL_VERSION: %s (%s, %s)\n" % (version, major, minor)
    detailedText += "GL_VENDOR: %r\n" % _decode(GL.glGetString(GL.GL_VENDOR))
    detailedText += "GL_RENDERER: %r\n" % _decode(GL.glGetString(GL.GL_RENDERER))

    log.info("%s", detailedText)
    global _lastAcquiredContextInfo
    _lastAcquiredContextInfo = detailedText

    if not context.isValid() or (major, minor) < (1, 3):
        app = QtGui.QApplication.instance()
        msgBox = QtGui.QMessageBox()
        msgBox.setWindowTitle(app.tr("OpenGL Error"))
        msgBox.setStandardButtons(QtGui.QMessageBox.StandardButton.Close)
        msgBox.setText(app.tr("OpenGL 1.3 or greater is required. MCEdit was unable to start up OpenGL."))
        msgBox.setInformativeText(
            app.tr("Could not create a usable OpenGL context. Verify that your "
                   "graphics drivers are installed correctly.")
        )

        msgBox.setDetailedText(detailedText)

        msgBox.setIcon(QtGui.QMessageBox.Icon.Critical)

        msgBox.setMinimumWidth(300)
        msgBox.setSizeGripEnabled(True)
        msgBox.exec()

        raise SystemExit
