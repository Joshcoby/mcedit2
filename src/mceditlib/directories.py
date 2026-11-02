"""
   directories.py

   On initialization, finds the default location for Minecraft saves
   and stores it in saveFileDir.
"""



import sys
import os
from mceditlib import util

if sys.platform == "win32":
    appDataDir = util.win32_appdata()
    minecraftDir = os.path.join(appDataDir, ".minecraft")
    appSupportDir = os.path.join(appDataDir, "mceditlib")

elif sys.platform == "darwin":
    appDataDir = os.path.expanduser("~/Library/Application Support")
    minecraftDir = os.path.join(appDataDir, "minecraft")
    appSupportDir = os.path.expanduser("~/Library/Application Support/mceditlib/")

else:
    appDataDir = os.path.expanduser("~")
    minecraftDir = os.path.expanduser("~/.minecraft")
    appSupportDir = os.path.expanduser("~/.mceditlib")

saveFileDir = os.path.join(minecraftDir, "saves")

