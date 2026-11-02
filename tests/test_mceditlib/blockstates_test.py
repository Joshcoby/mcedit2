import numpy
import pytest

from mceditlib import blockstates
from mceditlib.blockstates import BlockState, Palette, PaletteSection
from mceditlib.blocktypes import PCBlockTypeSet


@pytest.fixture(scope="module")
def blocktypes():
    return PCBlockTypeSet()


def test_parse_and_format():
    s = BlockState.parse("minecraft:oak_stairs[half=bottom,facing=north]")
    assert s.name == "minecraft:oak_stairs"
    assert s.propertyDict == {"facing": "north", "half": "bottom"}
    # canonical form sorts properties
    assert str(s) == "minecraft:oak_stairs[facing=north,half=bottom]"
    assert BlockState.parse(str(s)) == s
    assert BlockState.parse("stone") == BlockState("minecraft:stone")
    assert hash(BlockState.parse("a[x=1,y=2]")) == hash(BlockState.parse("a[y=2,x=1]"))


def test_palette_section_basics():
    sec = PaletteSection()
    stone = BlockState("stone")
    sec.setState(3, 4, 5, stone)
    assert sec.getState(3, 4, 5) == stone
    assert sec.getState(0, 0, 0) == BlockState("air")
    sec.fill(BlockState("dirt"))
    sec.compact()
    assert len(sec.palette) == 1
    assert sec.getState(1, 1, 1) == BlockState("dirt")


def test_legacy_roundtrip_random(blocktypes):
    rng = numpy.random.RandomState(1234)
    known = list(blocktypes.statesByID.keys())
    pairs = [known[i] for i in rng.randint(0, len(known), 200)]
    # add pairs the 1.12 mapping does not know about
    pairs += [(3000, 7), (200, 15)]
    blocks = numpy.zeros((16, 16, 16), dtype=numpy.uint16)
    data = numpy.zeros((16, 16, 16), dtype=numpy.uint8)
    choice = rng.randint(0, len(pairs), (16, 16, 16))
    for i, (ID, meta) in enumerate(pairs):
        mask = choice == i
        blocks[mask] = ID
        data[mask] = meta

    sec = PaletteSection.fromLegacy(blocks, data, blocktypes)
    assert len(sec.palette) <= len(pairs)
    b2, d2 = sec.toLegacy(blocktypes)
    assert (b2 == blocks).all()
    assert (d2 == data).all()


def test_legacy_names(blocktypes):
    blocks = numpy.full((16, 16, 16), 1, dtype=numpy.uint16)
    data = numpy.full((16, 16, 16), 1, dtype=numpy.uint8)
    sec = PaletteSection.fromLegacy(blocks, data, blocktypes)
    assert sec.getState(0, 0, 0) == BlockState("stone", {"variant": "granite"})


def test_unknown_state_uses_default(blocktypes):
    state = BlockState("stone", {"variant": "nonsense"})
    ID, meta = blockstates.stateToLegacy(state, blocktypes)
    assert (ID, meta) == (1, 0)
    with pytest.raises(KeyError):
        blockstates.stateToLegacy(BlockState("mod:thing"), blocktypes)


@pytest.mark.parametrize("n,expected", [(1, 4), (2, 4), (16, 4), (17, 5), (33, 6), (257, 9), (4096, 12)])
def test_bits_per_block(n, expected):
    assert blockstates.bitsPerBlock(n) == expected


@pytest.mark.parametrize("bits", [4, 5, 6, 7, 9, 12, 15])
@pytest.mark.parametrize("spanning", [False, True])
def test_pack_roundtrip(bits, spanning):
    rng = numpy.random.RandomState(bits)
    idx = rng.randint(0, 1 << bits, 4096).astype(numpy.uint16)
    longs = blockstates.packIndices(idx, bits, spanning)
    expectedLongs = (4096 * bits + 63) // 64 if spanning else -(-4096 // (64 // bits))
    assert len(longs) == expectedLongs
    assert longs.dtype == numpy.int64
    out = blockstates.unpackIndices(longs, bits, 4096, spanning)
    assert (out == idx).all()


def test_pack_known_vector():
    # 4 bits, non-spanning: value i at bit offset 4*i within each long. First long holds 0..15.
    idx = numpy.arange(4096, dtype=numpy.uint16) % 16
    longs = blockstates.packIndices(idx, 4)
    assert len(longs) == 256
    assert int(longs[0].view(numpy.uint64)) == 0xFEDCBA9876543210


def test_real_world_sections_roundtrip(pc_world):
    dim = pc_world.getDimension()
    bt = pc_world.blocktypes
    count = 0
    for cx, cz in list(dim.chunkPositions())[:6]:
        chunk = dim.getChunk(cx, cz)
        for cy in chunk.sectionPositions():
            sec = chunk.getSection(cy)
            ps = PaletteSection.fromLegacy(sec.Blocks, sec.Data, bt)
            b, d = ps.toLegacy(bt)
            assert (b == sec.Blocks).all() and (d == sec.Data).all()
            count += 1
    assert count
