"""
   biome_types.py

   Definitions for biome names, climate info, water color, and more.
"""

from collections import namedtuple
from importlib import resources
import csv

_BiomeType = namedtuple("BiomeType", "ID name temperature rainfall")

class BiomeType(_BiomeType):
    pass


class BiomeTypes(object):
    def __init__(self):
        self.types = {}

        with resources.files(__package__).joinpath("biomes.csv").open("r", encoding="utf-8", newline="") as io:
            self._load(csv.reader(io))

    def _load(self, c):
        for record in c:
            if record[0] == "ID":
                # headers: ID,Name,Temperature,Rainfall
                continue

            ID, name, temp, rain = record[:4]
            self.types[int(ID)] = BiomeType(int(ID), name, float(temp), float(rain))

