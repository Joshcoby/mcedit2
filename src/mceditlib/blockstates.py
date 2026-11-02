"""
    blockstates

    Palette-based block storage, the in-memory model used by Minecraft 1.13+ worlds.

    A `BlockState` is a block name plus a set of string properties, e.g.
    ``minecraft:oak_stairs[facing=north,half=bottom]``. A `PaletteSection` stores a 16x16x16 volume as a
    small `Palette` of distinct BlockStates plus an array of palette indices.

    The 1.12-and-earlier world format stores numeric block IDs and 4-bit "meta" values. `fromLegacy` and
    `toLegacy` convert between those arrays and a PaletteSection using a `BlockTypeSet`'s ID mapping. The
    conversion is lossless: (ID, meta) pairs the mapping doesn't know become states of the placeholder block
    ``mcedit:legacy[id=N,meta=M]`` and convert back to the same (ID, meta).

    The packed-long-array codecs (`packIndices` / `unpackIndices`) read and write the on-disk section
    format used by 1.13+ worlds.
"""
from __future__ import absolute_import, division, print_function

import numpy

LEGACY_NAME = "mcedit:legacy"
AIR = "minecraft:air"


class BlockState(object):
    """
    Immutable (name, properties) pair. Hashable and comparable; the canonical string form sorts
    properties by key, so property order never matters.
    """
    __slots__ = ("name", "properties", "_hash")

    def __init__(self, name, properties=None):
        if ":" not in name:
            name = "minecraft:" + name
        self.name = name
        self.properties = tuple(sorted((properties or {}).items()))
        self._hash = hash((self.name, self.properties))

    @classmethod
    def parse(cls, nameAndState):
        """
        >>> BlockState.parse("stone[variant=granite]").properties
        (('variant', 'granite'),)
        """
        if "[" in nameAndState:
            idx = nameAndState.index("[")
            name, state = nameAndState[:idx], nameAndState[idx:]
            if not state.endswith("]"):
                raise ValueError("Malformed blockstate: %r" % (nameAndState,))
            props = dict(pair.split("=", 1) for pair in state[1:-1].split(",") if pair)
        else:
            name, props = nameAndState, {}
        return cls(name, props)

    @property
    def propertyDict(self):
        return dict(self.properties)

    def with_(self, **props):
        d = self.propertyDict
        d.update(props)
        return BlockState(self.name, d)

    def __str__(self):
        if not self.properties:
            return self.name
        return "%s[%s]" % (self.name, ",".join("%s=%s" % kv for kv in self.properties))

    def __repr__(self):
        return "BlockState(%r)" % str(self)

    def __eq__(self, other):
        return (isinstance(other, BlockState)
                and self.name == other.name
                and self.properties == other.properties)

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return self._hash

    def __lt__(self, other):
        return (self.name, self.properties) < (other.name, other.properties)

    @classmethod
    def legacy(cls, ID, meta):
        return cls(LEGACY_NAME, {"id": str(int(ID)), "meta": str(int(meta))})

    def legacyIDMeta(self):
        """Return (ID, meta) if this is a placeholder legacy state, else None."""
        if self.name != LEGACY_NAME:
            return None
        d = self.propertyDict
        return int(d["id"]), int(d["meta"])


class Palette(object):
    """
    Ordered list of distinct BlockStates; a state's position is its palette index.
    """

    def __init__(self, states=()):
        self._states = []
        self._index = {}
        for s in states:
            self.add(s)

    def add(self, state):
        """Return the index of `state`, appending it if it is new."""
        idx = self._index.get(state)
        if idx is None:
            idx = len(self._states)
            self._states.append(state)
            self._index[state] = idx
        return idx

    def index(self, state):
        return self._index[state]

    def __getitem__(self, idx):
        return self._states[idx]

    def __len__(self):
        return len(self._states)

    def __iter__(self):
        return iter(self._states)

    def __contains__(self, state):
        return state in self._index

    def copy(self):
        return Palette(self._states)


class PaletteSection(object):
    """
    A 16x16x16 volume of blocks. ``indices`` is a uint16 array indexed [y, z, x] (the same order as
    Minecraft's 1.13+ on-disk layout) holding indices into ``palette``.
    """

    def __init__(self, palette=None, indices=None):
        if palette is None:
            palette = Palette([BlockState(AIR)])
        if indices is None:
            indices = numpy.zeros((16, 16, 16), dtype=numpy.uint16)
        self.palette = palette
        self.indices = indices

    def getState(self, x, y, z):
        return self.palette[int(self.indices[y & 15, z & 15, x & 15])]

    def setState(self, x, y, z, state):
        self.indices[y & 15, z & 15, x & 15] = self.palette.add(state)

    def fill(self, state):
        self.indices[:] = self.palette.add(state)

    def states(self):
        """Return a list of the distinct states actually used in the volume."""
        used = numpy.unique(self.indices)
        return [self.palette[int(i)] for i in used]

    def compact(self):
        """Drop unused palette entries and renumber indices. Returns self."""
        used, inverse = numpy.unique(self.indices, return_inverse=True)
        self.palette = Palette([self.palette[int(i)] for i in used])
        self.indices = inverse.reshape(self.indices.shape).astype(numpy.uint16)
        return self

    def blockStatesEqual(self, other):
        """Compare contents by state, ignoring palette ordering."""
        mine = numpy.array([hash(s) for s in self.palette], dtype=numpy.int64)[self.indices]
        theirs = numpy.array([hash(s) for s in other.palette], dtype=numpy.int64)[other.indices]
        return bool((mine == theirs).all())

    # --- 1.12 and earlier -------------------------------------------------------------------

    @classmethod
    def fromLegacy(cls, blocks, data, blocktypes):
        """
        Build a PaletteSection from 1.12-style ID/meta arrays (indexed [y, z, x], as in AnvilSection).

        :param blocks: block IDs, shape (16, 16, 16)
        :param data: 4-bit meta values, shape (16, 16, 16)
        :type blocktypes: mceditlib.blocktypes.BlockTypeSet
        """
        combined = (blocks.astype(numpy.uint32) << 4) | (data.astype(numpy.uint32) & 0xf)
        uniq, inverse = numpy.unique(combined, return_inverse=True)

        palette = Palette()
        remap = numpy.zeros(len(uniq), dtype=numpy.uint16)
        for i, key in enumerate(uniq):
            ID, meta = int(key) >> 4, int(key) & 0xf
            remap[i] = palette.add(legacyToState(ID, meta, blocktypes))

        return cls(palette, remap[inverse.reshape(combined.shape)])

    def toLegacy(self, blocktypes):
        """
        Return (blocks, data) uint16/uint8 arrays. States with no (ID, meta) in `blocktypes` raise KeyError.
        """
        idLut = numpy.zeros(len(self.palette), dtype=numpy.uint16)
        metaLut = numpy.zeros(len(self.palette), dtype=numpy.uint8)
        for i, state in enumerate(self.palette):
            idLut[i], metaLut[i] = stateToLegacy(state, blocktypes)
        return idLut[self.indices], metaLut[self.indices]


def legacyToState(ID, meta, blocktypes):
    nameAndState = blocktypes.statesByID.get((ID, meta))
    if nameAndState is None:
        return BlockState.legacy(ID, meta)
    return BlockState.parse(nameAndState)


def stateToLegacy(state, blocktypes):
    placeholder = state.legacyIDMeta()
    if placeholder is not None:
        return placeholder
    try:
        return blocktypes.IDsByState[str(state)]
    except KeyError:
        pass
    # Properties don't match a known 1.12 state; fall back to the block's default state.
    default = blocktypes.defaultBlockstates.get(state.name)
    if default is not None:
        try:
            return blocktypes.IDsByState[state.name + default]
        except KeyError:
            pass
    raise KeyError("No legacy (ID, meta) for blockstate %s" % (state,))


# --- 1.13+ packed long arrays ------------------------------------------------------------------

def bitsPerBlock(paletteLength):
    """Bits per index used on disk for a palette of this length (minimum 4)."""
    return max(4, (max(paletteLength - 1, 1)).bit_length())


def packIndices(indices, bits, spanning=False):
    """
    Pack a 4096-entry index array (flattened in [y, z, x] order) into int64 longs.

    :param spanning: True for the 1.13-1.15 layout in which values may cross long boundaries;
                     False for the 1.16+ layout, which pads the end of each long.
    :return: numpy int64 array
    """
    flat = numpy.asarray(indices, dtype=numpy.uint64).reshape(-1)
    n = len(flat)
    if spanning:
        nLongs = (n * bits + 63) // 64
        out = numpy.zeros(nLongs, dtype=numpy.uint64)
        for i, v in enumerate(flat.tolist()):
            bitPos = i * bits
            li, off = divmod(bitPos, 64)
            out[li] |= numpy.uint64((v << off) & 0xFFFFFFFFFFFFFFFF)
            if off + bits > 64:
                out[li + 1] |= numpy.uint64(v >> (64 - off))
        return out.view(numpy.int64)

    perLong = 64 // bits
    nLongs = (n + perLong - 1) // perLong
    padded = numpy.zeros(nLongs * perLong, dtype=numpy.uint64)
    padded[:n] = flat
    padded = padded.reshape(nLongs, perLong)
    shifts = (numpy.arange(perLong, dtype=numpy.uint64) * numpy.uint64(bits))
    out = (padded << shifts).sum(axis=1, dtype=numpy.uint64)
    return out.view(numpy.int64)


def unpackIndices(longs, bits, count=4096, spanning=False):
    """Inverse of packIndices. Returns a uint16 array of `count` entries."""
    arr = numpy.asarray(longs).astype(numpy.int64, copy=False).view(numpy.uint64)
    mask = (1 << bits) - 1
    if spanning:
        out = numpy.empty(count, dtype=numpy.uint16)
        words = arr.tolist()
        for i in range(count):
            li, off = divmod(i * bits, 64)
            v = words[li] >> off
            if off + bits > 64:
                v |= words[li + 1] << (64 - off)
            out[i] = v & mask
        return out

    perLong = 64 // bits
    shifts = numpy.arange(perLong, dtype=numpy.uint64) * numpy.uint64(bits)
    expanded = (arr[:, None] >> shifts[None, :]) & numpy.uint64(mask)
    return expanded.reshape(-1)[:count].astype(numpy.uint16)
