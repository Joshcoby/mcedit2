import numpy
import pytest

from mceditlib import nbt
from mceditlib.anvil import modern
from mceditlib.anvil.modern import ModernChunkData
from mceditlib.blockstates import BlockState


def makeRoot(layout):
    root = nbt.TAG_Compound()
    dv = {"1.13": 1976, "1.16": 2586, "1.18": 3465}[layout]
    root["DataVersion"] = nbt.TAG_Int(dv)
    root["marker"] = nbt.TAG_String("kept")
    if layout == "1.18":
        root["xPos"] = nbt.TAG_Int(2)
        root["zPos"] = nbt.TAG_Int(-3)
        root["yPos"] = nbt.TAG_Int(-4)
        root["sections"] = nbt.TAG_List(list_type=nbt.TAG_Compound().tagID)
    else:
        level = nbt.TAG_Compound()
        level["xPos"] = nbt.TAG_Int(2)
        level["zPos"] = nbt.TAG_Int(-3)
        level["Sections"] = nbt.TAG_List(list_type=nbt.TAG_Compound().tagID)
        root["Level"] = level
    return root


def fillChunk(chunk, rng, ys):
    states = [BlockState("stone"), BlockState("oak_stairs", {"facing": "north", "half": "bottom"}),
              BlockState("redstone_wire", {"power": "7", "north": "side"}), BlockState("dirt"),
              BlockState("water", {"level": "3"})]
    expected = {}
    for y in ys:
        for _ in range(60):
            x, yy, z = rng.randint(0, 16), rng.randint(0, 16) + y * 16, rng.randint(0, 16)
            s = states[rng.randint(0, len(states))]
            chunk.setState(x, yy, z, s)
            expected[(x, yy, z)] = s
    return expected


@pytest.mark.parametrize("layout", ["1.13", "1.16", "1.18"])
def test_roundtrip(layout):
    rng = numpy.random.RandomState(7)
    chunk = ModernChunkData(makeRoot(layout))
    ys = [-4, 0, 3] if layout == "1.18" else [0, 3]
    expected = fillChunk(chunk, rng, ys)

    tag = chunk.buildNBTTag()
    # serialize to bytes and back, as the region file would
    buf = tag.save(compressed=False)
    reloaded = ModernChunkData(nbt.load(buf=buf))

    assert reloaded.layout == layout
    assert reloaded.sectionPositions == sorted(ys)
    for (x, y, z), s in expected.items():
        assert reloaded.getState(x, y, z) == s
    assert reloaded.getState(15, 5 * 16 + 15, 15) == BlockState("air")
    assert reloaded.rootTag["marker"].value == "kept"


def test_negative_y_and_height():
    chunk = ModernChunkData(makeRoot("1.18"))
    chunk.setState(1, -64, 1, BlockState("bedrock"))
    chunk.setState(1, 319, 1, BlockState("stone"))
    assert chunk.getState(1, -64, 1) == BlockState("bedrock")
    assert chunk.getState(1, -1, 1) == BlockState("air")
    assert chunk.minSectionY == -4 and chunk.maxSectionY == 19


def test_single_palette_section_has_no_data():
    chunk = ModernChunkData(makeRoot("1.18"))
    sec = chunk.getSection(0, create=True)
    sec.blocks.fill(BlockState("stone"))
    tag = chunk.buildNBTTag()
    st = tag["sections"][0]["block_states"]
    assert "data" not in st
    assert len(st["palette"]) == 1
    again = ModernChunkData(tag)
    assert again.getState(7, 7, 7) == BlockState("stone")


def test_biomes_roundtrip():
    chunk = ModernChunkData(makeRoot("1.18"))
    sec = chunk.getSection(0, create=True)
    sec.biomePalette = ["minecraft:plains", "minecraft:desert", "minecraft:river"]
    idx = (numpy.arange(64) % 3).astype(numpy.uint16).reshape(4, 4, 4)
    sec.biomeIndices = idx
    again = ModernChunkData(nbt.load(buf=chunk.buildNBTTag().save(compressed=False)))
    s2 = again.getSection(0)
    assert s2.biomePalette == sec.biomePalette
    assert (s2.biomeIndices == idx).all()


def test_light_tags_preserved():
    chunk = ModernChunkData(makeRoot("1.18"))
    sec = chunk.getSection(0, create=True)
    sec.extraTags["SkyLight"] = nbt.TAG_Byte_Array(numpy.full(2048, 0xff, dtype=numpy.uint8))
    again = ModernChunkData(chunk.buildNBTTag())
    assert (again.getSection(0).extraTags["SkyLight"].value == 0xff).all()


def test_pre118_drops_empty_sections():
    chunk = ModernChunkData(makeRoot("1.16"))
    chunk.getSection(2, create=True)  # all air
    chunk.setState(0, 0, 0, BlockState("stone"))
    tag = chunk.buildNBTTag()
    assert [int(s["Y"].value) for s in tag["Level"]["Sections"]] == [0]
