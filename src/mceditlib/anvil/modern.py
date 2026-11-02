"""
    modern

    Reader/writer for the chunk NBT layouts used by Minecraft 1.13 and later, built on
    `mceditlib.blockstates`.

    Three layouts are handled (selected by the chunk's DataVersion):

    * 1.13-1.15 (DataVersion < 2529): ``Level.Sections[].Palette`` + ``BlockStates``, values may span longs.
    * 1.16-1.17 (2529 <= DataVersion < 2825): same tags, values padded within each long.
    * 1.18+ (DataVersion >= 2825): no ``Level`` wrapper; ``sections[].block_states`` / ``biomes`` with
      ``palette`` + ``data``; sections may have negative Y (world height -64..319 and beyond).

    Only block (and, for 1.18+, biome) data is interpreted. Every other tag in the chunk -- heightmaps,
    lighting, block entities, entities, structures -- is carried through unchanged so a read/modify/write
    cycle doesn't discard data this module doesn't understand.
"""
from __future__ import absolute_import, division, print_function

import numpy

from mceditlib import nbt
from mceditlib.blockstates import (BlockState, Palette, PaletteSection, bitsPerBlock,
                                   packIndices, unpackIndices)

DV_1_16 = 2529   # first version with non-spanning long arrays
DV_1_18 = 2825   # first version with the flat chunk layout and paletted biomes

LONG_DTYPE = nbt.TAG_Long_Array.dtype


def layoutForDataVersion(dataVersion):
    if dataVersion >= DV_1_18:
        return "1.18"
    if dataVersion >= DV_1_16:
        return "1.16"
    return "1.13"


# --- palette <-> NBT -------------------------------------------------------------------------

def paletteFromTag(listTag):
    states = []
    for entry in listTag:
        props = {}
        if "Properties" in entry:
            props = {str(k): str(v.value) for k, v in entry["Properties"].items()}
        states.append(BlockState(entry["Name"].value, props))
    return Palette(states)


def paletteToTag(palette):
    out = nbt.TAG_List(list_type=nbt.TAG_Compound().tagID)
    for state in palette:
        entry = nbt.TAG_Compound()
        entry["Name"] = nbt.TAG_String(state.name)
        if state.properties:
            props = nbt.TAG_Compound()
            for k, v in state.properties:
                props[k] = nbt.TAG_String(v)
            entry["Properties"] = props
        out.append(entry)
    return out


def _longsToTag(longs):
    return nbt.TAG_Long_Array(numpy.asarray(longs, dtype=numpy.int64).astype(LONG_DTYPE))


def _longsFromTag(tag):
    return numpy.asarray(tag.value).astype(numpy.uint64).view(numpy.int64)


# --- sections ---------------------------------------------------------------------------------

class ModernSection(object):
    """
    One 16-high slab of a chunk.

    :ivar Y: section index (block y // 16); may be negative
    :ivar blocks: PaletteSection
    :ivar biomePalette: list of biome name strings (1.18+ only, else None)
    :ivar biomeIndices: uint16 array shape (4, 4, 4) [y, z, x] of 4x4x4-block cells (1.18+ only)
    :ivar extraTags: other tags of the section (lighting, ...), kept verbatim
    """

    def __init__(self, Y, blocks=None):
        self.Y = Y
        self.blocks = blocks if blocks is not None else PaletteSection()
        self.biomePalette = None
        self.biomeIndices = None
        self.extraTags = nbt.TAG_Compound()

    def isEmpty(self):
        return all(s.name in ("minecraft:air", "minecraft:cave_air", "minecraft:void_air")
                   for s in self.blocks.states())


def _readBlocks(palette, longs, layout):
    if len(palette) <= 1 and longs is None:
        return PaletteSection(palette if len(palette) else Palette([BlockState("air")]))
    bits = bitsPerBlock(len(palette))
    indices = unpackIndices(longs, bits, 4096, spanning=(layout == "1.13"))
    return PaletteSection(palette, indices.reshape(16, 16, 16))


def _sectionFromTag(tag, layout):
    sec = ModernSection(int(tag["Y"].value))
    extra = tag.copy()

    if layout == "1.18":
        bs = extra.pop("block_states")
        palette = paletteFromTag(bs["palette"])
        longs = _longsFromTag(bs["data"]) if "data" in bs else None
        sec.blocks = _readBlocks(palette, longs, layout)

        if "biomes" in extra:
            bm = extra.pop("biomes")
            sec.biomePalette = [t.value for t in bm["palette"]]
            if "data" in bm and len(sec.biomePalette) > 1:
                bits = (len(sec.biomePalette) - 1).bit_length()
                sec.biomeIndices = unpackIndices(_longsFromTag(bm["data"]), bits, 64).reshape(4, 4, 4)
            else:
                sec.biomeIndices = numpy.zeros((4, 4, 4), dtype=numpy.uint16)
    else:
        if "Palette" in extra:
            palette = paletteFromTag(extra.pop("Palette"))
            longs = _longsFromTag(extra.pop("BlockStates")) if "BlockStates" in extra else None
            sec.blocks = _readBlocks(palette, longs, layout)
        # sections with no Palette (only light data) are blank
    sec.extraTags = extra
    return sec


def _sectionToTag(sec, layout):
    tag = sec.extraTags.copy()
    tag["Y"] = nbt.TAG_Byte(sec.Y)
    blocks = PaletteSection(sec.blocks.palette.copy(), sec.blocks.indices.copy()).compact()
    palette, indices = blocks.palette, blocks.indices

    if layout == "1.18":
        bs = nbt.TAG_Compound()
        bs["palette"] = paletteToTag(palette)
        if len(palette) > 1:
            bs["data"] = _longsToTag(packIndices(indices, bitsPerBlock(len(palette)), spanning=False))
        tag["block_states"] = bs

        if sec.biomePalette is not None:
            bm = nbt.TAG_Compound()
            bm["palette"] = nbt.TAG_List([nbt.TAG_String(n) for n in sec.biomePalette],
                                         list_type=nbt.TAG_String("").tagID)
            if len(sec.biomePalette) > 1:
                bits = (len(sec.biomePalette) - 1).bit_length()
                bm["data"] = _longsToTag(packIndices(sec.biomeIndices, bits, spanning=False))
            tag["biomes"] = bm
    else:
        tag["Palette"] = paletteToTag(palette)
        tag["BlockStates"] = _longsToTag(
            packIndices(indices, bitsPerBlock(len(palette)), spanning=(layout == "1.13")))
    return tag


# --- chunks -----------------------------------------------------------------------------------

class ModernChunkData(object):
    """
    A chunk in a 1.13+ world.

    :ivar dataVersion: the chunk's DataVersion
    :ivar layout: "1.13", "1.16" or "1.18"
    :ivar sections: dict mapping section Y (may be negative) -> ModernSection
    :ivar rootTag: the chunk's root tag minus its sections (everything else is preserved)
    """

    def __init__(self, rootTag, dataVersion=None):
        self.rootTag = rootTag
        if dataVersion is None:
            dataVersion = rootTag["DataVersion"].value
        self.dataVersion = dataVersion
        self.layout = layoutForDataVersion(dataVersion)
        self.sections = {}
        self._load()

    @property
    def _container(self):
        """The compound holding Sections: the root itself in 1.18+, ``Level`` before that."""
        return self.rootTag if self.layout == "1.18" else self.rootTag["Level"]

    @property
    def _sectionsKey(self):
        return "sections" if self.layout == "1.18" else "Sections"

    def _load(self):
        container = self._container
        key = self._sectionsKey
        for tag in container.pop(key, []):
            sec = _sectionFromTag(tag, self.layout)
            self.sections[sec.Y] = sec

    @property
    def sectionPositions(self):
        return sorted(self.sections)

    @property
    def minSectionY(self):
        return min(self.sections) if self.sections else 0

    @property
    def maxSectionY(self):
        return max(self.sections) if self.sections else 0

    def getSection(self, cy, create=False):
        sec = self.sections.get(cy)
        if sec is None and create:
            sec = ModernSection(cy)
            if self.layout == "1.18":
                sec.biomePalette = ["minecraft:plains"]
                sec.biomeIndices = numpy.zeros((4, 4, 4), dtype=numpy.uint16)
            self.sections[cy] = sec
        return sec

    def getState(self, x, y, z):
        sec = self.sections.get(y >> 4)
        if sec is None:
            return BlockState("air")
        return sec.blocks.getState(x, y, z)

    def setState(self, x, y, z, state):
        self.getSection(y >> 4, create=True).blocks.setState(x, y, z, state)

    def buildNBTTag(self):
        """Return a new root tag with this chunk's sections written back in. Empty sections are dropped."""
        root = self.rootTag.copy()
        container = root if self.layout == "1.18" else root["Level"]
        out = nbt.TAG_List(list_type=nbt.TAG_Compound().tagID)
        for cy in self.sectionPositions:
            sec = self.sections[cy]
            # In pre-1.18 worlds, empty sections are omitted; in 1.18+ every section in range is stored.
            if self.layout != "1.18" and sec.isEmpty() and "BlockLight" not in sec.extraTags \
                    and "SkyLight" not in sec.extraTags:
                continue
            out.append(_sectionToTag(sec, self.layout))
        container[self._sectionsKey] = out
        return root
