"""Buttons driving blinds (covers): a press steps them, a long press moves while held."""

from __future__ import annotations

import asyncio

import pytest

from custom_components.switch_control.const import DOMAIN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

BUTTON = "binary_sensor.button"
BLIND = "cover.blind"
LAMP = "light.lamp"
FEATURES = 15  # open, close, set position, stop


class Blind:
    """A blind that moves when told and remembers the calls."""

    def __init__(self, hass: HomeAssistant, features: int = FEATURES) -> None:
        self.hass = hass
        self.calls: list[str] = []
        self.features = features
        for service in ("open_cover", "close_cover", "stop_cover"):
            hass.services.async_register("cover", service, self._handle)
        for service in ("turn_on", "turn_off"):
            hass.services.async_register("light", service, self._light)

    def set(self, state: str, position: int | None) -> None:
        attrs = {"supported_features": self.features}
        if position is not None:
            attrs["current_position"] = position
        self.hass.states.async_set(BLIND, state, attrs)

    async def _handle(self, call) -> None:
        self.calls.append(call.service)
        position = self.hass.states.get(BLIND).attributes.get("current_position")
        if call.service == "open_cover":
            self.set("opening", position)
        elif call.service == "close_cover":
            self.set("closing", position)
        else:
            self.set("open", position)  # stopped part-way

    async def _light(self, call) -> None:
        self.calls.append(f"light.{call.service}")
        self.hass.states.async_set(LAMP, "on" if call.service == "turn_on" else "off")


async def setup(hass: HomeAssistant, outputs, **switch) -> str:
    hass.states.async_set(BUTTON, "off")
    config = {
        "name": "Panel",
        "sensor_entity_id": BUTTON,
        "output_entity_ids": outputs,
        "long_press_action": "none",
        "long_press_output_entity_ids": [],
        "double_press_action": "none",
        "double_press_output_entity_ids": [],
        **switch,
    }
    entry = MockConfigEntry(
        domain=DOMAIN, title="Panel", data={"name": "Panel", "switch_count": 1, "switches": [config]}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return next(e for e in hass.states.async_entity_ids("switch"))


async def press(hass: HomeAssistant, hold: float = 0.05) -> None:
    hass.states.async_set(BUTTON, "on")
    await asyncio.sleep(hold)
    hass.states.async_set(BUTTON, "off")
    await asyncio.sleep(0.5)  # past the double-press window
    await hass.async_block_till_done()


@pytest.fixture
async def blind(hass: HomeAssistant) -> Blind:
    return Blind(hass)


async def test_press_cycles_close_stop_open(hass, blind):
    blind.set("open", 100)
    await setup(hass, [BLIND])
    await press(hass)
    assert blind.calls == ["close_cover"]
    await press(hass)  # while closing: stop
    assert blind.calls[-1] == "stop_cover"
    blind.set("open", 40)
    await press(hass)  # stopped part-way after closing: go back up
    assert blind.calls[-1] == "open_cover"
    await press(hass)
    assert blind.calls[-1] == "stop_cover"
    blind.set("open", 70)
    await press(hass)  # stopped part-way after opening: go down
    assert blind.calls[-1] == "close_cover"


async def test_closed_blind_opens(hass, blind):
    blind.set("closed", 0)
    await setup(hass, [BLIND])
    await press(hass)
    assert blind.calls == ["open_cover"]


async def test_direction_follows_moves_made_elsewhere(hass, blind):
    blind.set("open", 50)
    await setup(hass, [BLIND])
    blind.set("opening", 50)  # from the app
    await hass.async_block_till_done()
    blind.set("open", 60)  # stopped from the app
    await hass.async_block_till_done()
    await press(hass)
    assert blind.calls == ["close_cover"]


async def test_hold_moves_and_release_stops(hass, blind):
    blind.set("closed", 0)
    await setup(
        hass, [], long_press_action="cover_move", long_press_output_entity_ids=[BLIND]
    )
    hass.states.async_set(BUTTON, "on")
    await asyncio.sleep(0.8)
    await hass.async_block_till_done()
    assert blind.calls == ["open_cover"]
    hass.states.async_set(BUTTON, "off")
    await asyncio.sleep(0.6)
    await hass.async_block_till_done()
    assert blind.calls == ["open_cover", "stop_cover"]


async def test_switch_shows_blind_open_as_on(hass, blind):
    blind.set("open", 100)
    switch = await setup(hass, [BLIND])
    assert hass.states.get(switch).state == "on"
    blind.set("closed", 0)
    await hass.async_block_till_done()
    assert hass.states.get(switch).state == "off"
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    await hass.async_block_till_done()
    assert blind.calls[-1] == "open_cover"


async def test_blind_without_stop_reverses_instead(hass):
    blind = Blind(hass, features=3)  # open/close only
    blind.set("closing", 50)
    await setup(hass, [BLIND])
    await press(hass)
    assert blind.calls == ["open_cover"]


async def test_lights_still_toggle(hass, blind):
    hass.states.async_set(LAMP, "off")
    await setup(hass, [LAMP])
    await press(hass)
    assert blind.calls == ["light.turn_on"]
    await press(hass)
    assert blind.calls == ["light.turn_on", "light.turn_off"]
