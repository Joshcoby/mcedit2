import numpy
import pytest

from mceditlib.anvil.adapter import AnvilWorldAdapter
from mceditlib.anvil.modern_adapter import ModernWorldAdapter
from mceditlib.blockstates import BlockState
from mceditlib.findadapter import findAdapter
from mceditlib.worldeditor import WorldEditor


def makeWorld(tmpdir, name="Modern"):
    path = tmpdir.join(name)
    path.mkdir()
    ModernWorldAdapter(filename=path.strpath, create=True).close()
    return path.strpath


def test_find_adapter(tmpdir, pc_world):
    path = makeWorld(tmpdir)
    adapter = findAdapter(path)
    assert isinstance(adapter, ModernWorldAdapter)
    adapter.close()
    # legacy worlds must keep using the 1.12 adapter
    legacy = findAdapter(pc_world.adapter.filename, readonly=True)
    assert type(legacy) is AnvilWorldAdapter


def test_chunk_roundtrip(tmpdir):
    path = makeWorld(tmpdir)
    world = WorldEditor(path, adapterClass=ModernWorldAdapter)
    bt = world.blocktypes
    dim = world.getDimension()
    dim.createChunk(0, 0)
    chunk = dim.getChunk(0, 0)

    stairs = bt["oak_stairs[facing=north,half=top,shape=straight,waterlogged=false]"]
    stone = bt["stone"]
    deep = bt["deepslate"]
    sec0 = chunk.chunkData.getSection(0, create=True)
    secN = chunk.chunkData.getSection(-4, create=True)
    sec0.Blocks[1, 2, 3] = stairs.ID
    sec0.Blocks[15, 15, 15] = stone.ID
    secN.Blocks[0, 0, 0] = deep.ID
    chunk.dirty = True
    chunk.chunkData.dirty = True
    world.saveChanges()
    world.close()

    world = WorldEditor(path, adapterClass=ModernWorldAdapter)
    chunk = world.getDimension().getChunk(0, 0)
    bt2 = world.blocktypes
    s0 = chunk.chunkData.getSection(0)
    sN = chunk.chunkData.getSection(-4)
    assert bt2.stateForID(s0.Blocks[1, 2, 3]) == BlockState.parse(
        "oak_stairs[facing=north,half=top,shape=straight,waterlogged=false]")
    assert bt2.stateForID(s0.Blocks[15, 15, 15]) == BlockState("stone")
    assert bt2.stateForID(sN.Blocks[0, 0, 0]) == BlockState("deepslate")
    assert s0.Blocks[0, 0, 0] == 0
    world.close()


def test_block_properties_guess(tmpdir):
    path = makeWorld(tmpdir)
    world = WorldEditor(path, adapterClass=ModernWorldAdapter)
    bt = world.blocktypes
    assert bt["stone"].opacity == 15
    assert bt["oak_slab"].opacity == 0
    assert bt["glowstone"].brightness == 15
    assert bt["water"].opacity == 3
    assert bt["torch"].brightness == 14
    # arrays used by the relighter and renderer
    assert bt.opacity[bt["glowstone"].ID] == 15
    assert len(bt.opacity) == 65536
    world.close()
