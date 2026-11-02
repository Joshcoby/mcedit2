"""
    modern

    A BlockTypeSet for Minecraft 1.13+ worlds.

    Modern worlds identify blocks by name and properties rather than by numeric ID and 4-bit metadata, and
    there are far more than 16 states per block. To let the existing ID-based editing, lighting and rendering
    code work unchanged, this set assigns every blockstate it meets a *runtime ID* (meta is always 0). Runtime
    IDs live only in memory; they are translated back to names and properties whenever a chunk is saved, so
    they never reach disk and may differ between sessions.

    Block properties (opacity, brightness, ...) for 1.13+ blocks are not shipped with MCEdit yet, so they are
    guessed from the block's name. This is good enough for lighting vanilla terrain; exact values will come from
    a client's data reports in a later phase.
"""
from __future__ import absolute_import, division, print_function

import re

from mceditlib.blockstates import BlockState
from mceditlib.blocktypes import BlockType, BlockTypeSet, itemtypes

ID_LIMIT = 65536

_AIR = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}

# Name -> light emitted
_EMISSIVE = {
    "torch": 14, "wall_torch": 14, "soul_torch": 10, "soul_wall_torch": 10, "redstone_torch": 7,
    "redstone_wall_torch": 7, "lantern": 15, "soul_lantern": 10, "glowstone": 15, "sea_lantern": 15,
    "shroomlight": 15, "jack_o_lantern": 15, "fire": 15, "soul_fire": 10, "lava": 15, "beacon": 15,
    "end_rod": 14, "campfire": 15, "soul_campfire": 10, "magma_block": 3, "conduit": 15,
    "ochre_froglight": 15, "verdant_froglight": 15, "pearlescent_froglight": 15, "end_portal": 15,
    "nether_portal": 11, "enchanting_table": 7, "brewing_stand": 1, "ender_chest": 7, "sea_pickle": 6,
    "crying_obsidian": 10, "respawn_anchor": 0, "light": 0,
}

# Blocks that let light through undimmed and aren't full cubes.
_CLEAR_SUFFIXES = (
    "_slab", "_stairs", "_fence", "_fence_gate", "_wall", "_door", "_trapdoor", "_sign", "_wall_sign",
    "_hanging_sign", "_button", "_pressure_plate", "_carpet", "_pane", "_torch", "_banner", "_bed",
    "_sapling", "_rail", "_head", "_skull", "_candle", "_coral", "_coral_fan", "_coral_wall_fan",
    "_flower", "_roots", "_vine", "_mushroom", "_fungus", "_propagule", "_stem", "_amethyst_bud",
)
_CLEAR_NAMES = {
    "glass", "short_grass", "grass", "tall_grass", "fern", "large_fern", "dead_bush", "seagrass",
    "tall_seagrass", "kelp", "kelp_plant", "vine", "dandelion", "poppy", "blue_orchid", "allium",
    "azure_bluet", "oxeye_daisy", "cornflower", "lily_of_the_valley", "wither_rose", "sunflower",
    "lilac", "rose_bush", "peony", "torch", "redstone_wire", "lever", "tripwire", "tripwire_hook",
    "ladder", "snow", "cobweb", "iron_bars", "chain", "lantern", "soul_lantern", "flower_pot",
    "rail", "powered_rail", "detector_rail", "activator_rail", "end_rod", "lightning_rod", "sugar_cane",
    "bamboo", "fire", "soul_fire", "wheat", "carrots", "potatoes", "beetroots", "nether_wart",
    "sweet_berry_bush", "cave_vines", "cave_vines_plant", "glow_lichen", "sculk_vein", "hanging_roots",
    "moss_carpet", "pointed_dripstone", "light", "barrier", "structure_void", "comparator", "repeater",
    "cake", "scaffolding", "glass_pane", "tinted_glass", "small_amethyst_bud", "cocoa",
}


def _shortName(state):
    return state.name.split(":", 1)[-1]


def guessBlockProperties(state):
    """
    Return a dict of block properties guessed from a BlockState's name.
    Keys follow the blockJson attributes used by BlockTypeSet.
    """
    short = _shortName(state)
    props = {}

    if state.name in _AIR:
        props.update(opacity=0, opaqueCube=0, normalCube=0)
        return props

    light = _EMISSIVE.get(short)
    if light is not None:
        props["brightness"] = light

    # Lit lamps/furnaces/redstone ore and similar use a `lit` property.
    sd = state.propertyDict
    if sd.get("lit") == "true" and short in ("redstone_lamp", "furnace", "smoker", "blast_furnace",
                                            "redstone_ore", "deepslate_redstone_ore", "campfire"):
        props["brightness"] = 15 if short != "furnace" else 13
    if short == "candle" or short.endswith("_candle"):
        if sd.get("lit") == "true":
            props["brightness"] = 3 * int(sd.get("candles", "1"))

    if short in ("water", "bubble_column", "ice", "frosted_ice"):
        props.update(opacity=3 if short in ("water", "bubble_column") else 1, opaqueCube=0, normalCube=0)
        if short in ("water", "bubble_column"):
            props["materialLiquid"] = 1
    elif short == "lava":
        props.update(opacity=1, opaqueCube=0, normalCube=0, materialLiquid=1)
    elif short.endswith("_leaves") or short == "leaves":
        props.update(opacity=1, opaqueCube=0, normalCube=0)
    elif short in _CLEAR_NAMES or short.endswith(_CLEAR_SUFFIXES) or "glass" in short:
        props.update(opacity=0, opaqueCube=0, normalCube=0)

    return props


def prettyName(state):
    return " ".join(w.capitalize() for w in _shortName(state).split("_"))


class ModernBlockTypeSet(BlockTypeSet):
    """
    Blocktype set for 1.13+ worlds. Block states are registered on demand and receive sequential runtime IDs.
    """

    def __init__(self, itemStackVersion=None):
        super(ModernBlockTypeSet, self).__init__(idLimit=ID_LIMIT)
        self.name = "Modern"
        self.itemStackVersion = itemStackVersion
        self.itemTypes = itemtypes.PCItemTypeSet()
        self._nextID = 0
        self._stateCache = {}   # runtime ID -> BlockState
        self.registerState(BlockState("minecraft:air"))

    def registerState(self, state):
        """
        Return the runtime ID for the given BlockState, assigning a new one if the state hasn't been seen.
        """
        key = str(state)
        found = self.IDsByState.get(key)
        if found is not None:
            return found[0]

        ID = self._nextID
        if ID >= self.id_limit:
            raise OverflowError("Too many distinct blockstates (limit %d)" % self.id_limit)
        self._nextID += 1

        nameAndState = key
        self.IDsByState[nameAndState] = (ID, 0)
        self.statesByID[(ID, 0)] = nameAndState
        self.IDsByName.setdefault(state.name, ID)
        self.namesByID[ID] = state.name
        self._stateCache[ID] = state

        bracket = nameAndState.find("[")
        blockState = nameAndState[bracket:] if bracket >= 0 else ""
        self.defaultBlockstates.setdefault(state.name, blockState)

        guessed = guessBlockProperties(state)
        blockJson = {
            "internalName": state.name,
            "blockState": blockState,
            "displayName": prettyName(state),
        }
        blockJson.update(guessed)
        self.blockJsons[nameAndState] = blockJson

        # Guessed properties that live in per-ID arrays
        self.opacity[ID] = guessed.get("opacity", self.defaults["opacity"])
        self.brightness[ID] = guessed.get("brightness", self.defaults["brightness"])
        self.opaqueCube[ID] = guessed.get("opaqueCube", self.defaults["opaqueCube"])
        self.normalCube[ID] = guessed.get("normalCube", self.defaults["normalCube"])
        self.materialLiquid[ID] = guessed.get("materialLiquid", 0)

        self.allBlocks.add(BlockType(ID, 0, self))
        return ID

    def stateForID(self, ID):
        return self._stateCache[int(ID)]

    def __getitem__(self, nameAndState):
        # Strings and (name, state) tuples register the state if it is new.
        if isinstance(nameAndState, str):
            if ":" not in nameAndState:
                nameAndState = self.namePrefix + nameAndState
            self.registerState(BlockState.parse(nameAndState))
            ID, meta = self.IDsByState[str(BlockState.parse(nameAndState))]
            return BlockType(ID, meta, self)
        return super(ModernBlockTypeSet, self).__getitem__(nameAndState)
