"""
    modern_adapter

    World adapter for Minecraft 1.13+ Anvil worlds.

    Chunks are read with `mceditlib.anvil.modern` and presented to the rest of MCEdit through the same
    interface as `AnvilChunkData`: each section exposes ``Blocks`` (uint16), ``Data``, ``BlockLight`` and
    ``SkyLight`` arrays. ``Blocks`` holds *runtime IDs* assigned by a `ModernBlockTypeSet` (``Data`` is always
    zero); they are converted back to names and properties on save.

    Current limitations (tracked in the port plan):
      * biomes, heightmaps and entities are not yet exposed. Biomes and heightmaps are left untouched in
        the chunk; entities (stored in a separate ``entities`` region folder since 1.17) are not read.
      * the editor treats world height as starting at 0, so editing below y=0 is not yet supported even
        though such chunks can be read and saved.
"""
from __future__ import absolute_import, division, print_function

import logging
import sys
import zlib

import numpy

from mceditlib import nbt
from mceditlib.anvil.adapter import (AnvilWorldAdapter, AnvilChunkFormatError, unpackNibbleArray,
                                     packNibbleArray)
from mceditlib.anvil.modern import ModernChunkData, ModernSection, layoutForDataVersion, DV_1_18
from mceditlib.blockstates import Palette, PaletteSection
from mceditlib.blocktypes.modern import ModernBlockTypeSet
from mceditlib.exceptions import ChunkNotPresent
from mceditlib.selection import BoundingBox

log = logging.getLogger(__name__)

DV_1_13 = 1519
DV_1_18_2 = 2975


def readDataVersion(levelDatBytes):
    """Return the DataVersion in raw level.dat bytes, or 0 if absent."""
    root = nbt.load(buf=levelDatBytes)
    return root["Data"].get("DataVersion", nbt.TAG_Int(0)).value


class ModernCompatSection(object):
    """
    Legacy-shaped view of a ModernSection: ID/light arrays indexed [y, z, x].
    """

    def __init__(self, modernSection, blocktypes):
        self.modern = modernSection
        self.Y = modernSection.Y
        ps = modernSection.blocks
        idLut = numpy.array([blocktypes.registerState(s) for s in ps.palette], dtype=numpy.uint16)
        self.Blocks = idLut[ps.indices]
        self.Data = numpy.zeros((16, 16, 16), dtype=numpy.uint8)

        extra = modernSection.extraTags
        self._hadSky = "SkyLight" in extra
        self._hadBlock = "BlockLight" in extra
        self.SkyLight = self._unpackLight(extra.get("SkyLight"), 15)
        self.BlockLight = self._unpackLight(extra.get("BlockLight"), 0)

    @staticmethod
    def _unpackLight(tag, default):
        if tag is None or len(tag.value) != 2048:
            return numpy.full((16, 16, 16), default, dtype=numpy.uint8)
        return unpackNibbleArray(numpy.array(tag.value, dtype=numpy.uint8).reshape(16, 16, 8))

    @classmethod
    def blank(cls, Y, blocktypes):
        return cls(ModernSection(Y), blocktypes)

    def isDefault(self):
        return (not self.Blocks.any()
                and not self.BlockLight.any()
                and (self.SkyLight == 15).all())

    def toModernSection(self, blocktypes):
        """Write this view's arrays back into the underlying ModernSection and return it."""
        sec = self.modern
        sec.Y = self.Y
        used, inverse = numpy.unique(self.Blocks, return_inverse=True)
        palette = Palette([blocktypes.stateForID(i) for i in used])
        indices = inverse.reshape(16, 16, 16).astype(numpy.uint16)
        sec.blocks = PaletteSection(palette, indices)

        if self._hadSky or (self.SkyLight != 15).any():
            sec.extraTags["SkyLight"] = nbt.TAG_Byte_Array(packNibbleArray(self.SkyLight).astype("uint8"))
        if self._hadBlock or self.BlockLight.any():
            sec.extraTags["BlockLight"] = nbt.TAG_Byte_Array(packNibbleArray(self.BlockLight).astype("uint8"))
        return sec


def newRootTag(cx, cz, dataVersion):
    root = nbt.TAG_Compound()
    root.name = ""
    root["DataVersion"] = nbt.TAG_Int(dataVersion)
    status = "minecraft:full" if dataVersion >= DV_1_18_2 else "full"
    if layoutForDataVersion(dataVersion) == "1.18":
        root["xPos"] = nbt.TAG_Int(cx)
        root["zPos"] = nbt.TAG_Int(cz)
        root["yPos"] = nbt.TAG_Int(-4)
        root["Status"] = nbt.TAG_String(status)
        root["LastUpdate"] = nbt.TAG_Long(0)
        root["InhabitedTime"] = nbt.TAG_Long(0)
        root["sections"] = nbt.TAG_List(list_type=nbt.TAG_Compound().tagID)
        root["block_entities"] = nbt.TAG_List(list_type=nbt.TAG_Compound().tagID)
    else:
        level = nbt.TAG_Compound()
        level["xPos"] = nbt.TAG_Int(cx)
        level["zPos"] = nbt.TAG_Int(cz)
        level["Status"] = nbt.TAG_String(status)
        level["LastUpdate"] = nbt.TAG_Long(0)
        level["InhabitedTime"] = nbt.TAG_Long(0)
        level["Sections"] = nbt.TAG_List(list_type=nbt.TAG_Compound().tagID)
        level["TileEntities"] = nbt.TAG_List(list_type=nbt.TAG_Compound().tagID)
        level["Entities"] = nbt.TAG_List(list_type=nbt.TAG_Compound().tagID)
        root["Level"] = level
    return root


class ModernAnvilChunkData(object):
    """
    Chunk data backing a WorldEditorChunk for a 1.13+ world. Same interface as AnvilChunkData.
    """

    def __init__(self, adapter, cx, cz, dimName, rootTag=None, create=False):
        self.cx = cx
        self.cz = cz
        self.dimName = dimName
        self.adapter = adapter
        self.dirty = False

        if create:
            rootTag = newRootTag(cx, cz, adapter.dataVersion)
            self.dirty = True

        self.data = ModernChunkData(rootTag)
        self.rootTag = self.data.rootTag
        self._sections = {}
        for cy, msec in self.data.sections.items():
            self._sections[cy] = ModernCompatSection(msec, adapter.blocktypes)

        # Transient views of data this adapter doesn't interpret yet. These are not written back.
        self._entities = nbt.TAG_List()
        self._tileTicks = nbt.TAG_List()
        self._biomes = numpy.full((16, 16), 255, dtype=numpy.uint8)
        self._heightMap = None

    # --- sections ---

    def sectionPositions(self):
        return list(self._sections.keys())

    def getSection(self, cy, create=False):
        if (cy << 4) >= self.adapter.maxHeight or (cy << 4) < self.adapter.minHeight:
            return None
        section = self._sections.get(cy)
        if section is None:
            if not create:
                return None
            section = ModernCompatSection.blank(cy, self.adapter.blocktypes)
            self._sections[cy] = section
        return section

    @property
    def bounds(self):
        return BoundingBox((self.cx << 4, self.adapter.minHeight, self.cz << 4),
                           (16, self.adapter.maxHeight - self.adapter.minHeight, 16))

    @property
    def blocktypes(self):
        return self.adapter.blocktypes

    # --- tags ---

    @property
    def _container(self):
        return self.rootTag if self.data.layout == "1.18" else self.rootTag["Level"]

    @property
    def Entities(self):
        if self.data.layout == "1.18":
            return self._entities
        return self._container["Entities"]

    @property
    def TileEntities(self):
        key = "block_entities" if self.data.layout == "1.18" else "TileEntities"
        container = self._container
        if key not in container:
            container[key] = nbt.TAG_List()
        return container[key]

    @property
    def TileTicks(self):
        if self.data.layout == "1.18":
            return self._tileTicks
        container = self._container
        if "TileTicks" not in container:
            container["TileTicks"] = nbt.TAG_List()
        return container["TileTicks"]

    @property
    def Biomes(self):
        return self._biomes

    @property
    def HeightMap(self):
        if self._heightMap is None:
            hm = numpy.zeros((16, 16), dtype=numpy.uint32)
            for cy in sorted(self._sections):
                nonAir = self._sections[cy].Blocks != 0   # [y, z, x]
                if not nonAir.any():
                    continue
                ys = numpy.arange(16)[:, None, None] + (cy << 4) + 1
                top = (nonAir * ys).max(axis=0)
                hm = numpy.maximum(hm, numpy.clip(top, 0, None).astype(numpy.uint32))
            self._heightMap = hm
        return self._heightMap

    @property
    def TerrainPopulated(self):
        return True

    @TerrainPopulated.setter
    def TerrainPopulated(self, val):
        self.dirty = True

    # --- saving ---

    def buildNBTTag(self):
        """Return the root tag for this chunk. Does not recalculate light."""
        blocktypes = self.adapter.blocktypes
        modernSections = {}
        for cy, section in self._sections.items():
            if section.isDefault() and self.data.layout != "1.18":
                continue
            modernSections[cy] = section.toModernSection(blocktypes)
        self.data.sections = modernSections
        tag = self.data.buildNBTTag()

        if self.dirty:
            # Cached heightmaps would be stale after an edit; Minecraft rebuilds missing ones on load.
            container = tag if self.data.layout == "1.18" else tag["Level"]
            for key in ("Heightmaps", "HeightMap"):
                if key in container:
                    del container[key]
        return tag


class ModernWorldAdapter(AnvilWorldAdapter):
    """
    Adapter for Minecraft 1.13 and later (DataVersion >= 1519) Java Edition worlds.
    """
    minHeight = -64
    maxHeight = 320

    def loadBlockMapping(self):
        self.blocktypes = ModernBlockTypeSet()
        self.dataVersion = self.metadata.rootTag.get("DataVersion", nbt.TAG_Int(DV_1_18)).value

    def _createMetadataTag(self, random_seed=None):
        super(ModernWorldAdapter, self)._createMetadataTag(random_seed)
        self.metadata.rootTag["DataVersion"] = nbt.TAG_Int(DV_1_18)

    @classmethod
    def canOpenFile(cls, filename):
        if not super(ModernWorldAdapter, cls).canOpenFile(filename):
            return False
        import os
        folder = filename if os.path.isdir(filename) else os.path.dirname(filename)
        for name in ("level.dat", "level.dat_old"):
            path = os.path.join(folder, name)
            if os.path.exists(path):
                try:
                    with open(path, "rb") as f:
                        return readDataVersion(f.read()) >= DV_1_13
                except Exception:
                    return False
        return False

    def readChunk(self, cx, cz, dimName):
        try:
            data = self.selectedRevision.readChunkBytes(cx, cz, dimName)
            chunkTag = nbt.load(buf=data)
            return ModernAnvilChunkData(self, cx, cz, dimName, chunkTag)
        except ChunkNotPresent:
            raise
        except (KeyError, IndexError, zlib.error, UnicodeError, ValueError) as e:
            raise AnvilChunkFormatError("Error loading chunk: %r" % e, None, sys.exc_info()[2])

    def createChunk(self, cx, cz, dimName):
        if self.selectedRevision.containsChunk(cx, cz, dimName):
            raise ValueError("Chunk %s already exists in dim %r" % ((cx, cz), dimName))
        chunk = ModernAnvilChunkData(self, cx, cz, dimName, create=True)
        self.selectedRevision.writeChunkBytes(cx, cz, dimName, chunk.buildNBTTag().save(compressed=False))
        return chunk
