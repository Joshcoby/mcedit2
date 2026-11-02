"""
    json_resources
"""

import json
import logging
import os
from os.path import join
import traceback

log = logging.getLogger(__name__)

_cachedJsons = {}

def openResource(filename):
    path = join(os.path.dirname(__file__), filename)
    if not os.path.exists(path):
        # zipped/frozen installs
        from importlib import resources
        return resources.files(__package__).joinpath(filename).open("r", encoding="utf-8")

    return open(path, encoding="utf-8")

def getJsonFile(filename):
    if filename in _cachedJsons:
        return _cachedJsons[filename]

    f = openResource(filename)
    try:
        s = f.read()
        entries = json.loads(s)
        _cachedJsons[filename] = entries
        return entries
    except EnvironmentError as e:
        log.error("Exception while loading JSON from %s: %s", f, e)
        traceback.print_exc()
