"""Switch platform for the Switch Control integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.const import STATE_ON, STATE_OFF

from .const import (
    CONF_LONG_PRESS_ACTION,
    CONF_NAME,
    CONF_OUTPUT_ENTITY_IDS,
    CONF_SENSOR_ENTITY_ID,
    CONF_SWITCHES,
    DOMAIN,
    EVENT_BUTTON_PRESSED,
    EVENT_LONG_PRESS,
    EVENT_LONG_PRESS_RELEASED,
    LONG_PRESS_ACTION_NONE,
    LONG_PRESS_ACTION_TOGGLE,
    LONG_PRESS_ACTION_TURN_OFF,
    LONG_PRESS_ACTION_TURN_ON,
    LONG_PRESS_THRESHOLD,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Switch Control switch entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchControlEntity] = []

    if CONF_SWITCHES in data:
        # Multi-switch format: create one entity per configured switch input.
        for i, switch_cfg in enumerate(data[CONF_SWITCHES]):
            entities.append(
                SwitchControlEntity(
                    entry=entry,
                    name=switch_cfg[CONF_NAME],
                    sensor_entity_id=switch_cfg[CONF_SENSOR_ENTITY_ID],
                    output_entity_ids=switch_cfg[CONF_OUTPUT_ENTITY_IDS],
                    unique_id=f"{entry.entry_id}_switch_{i + 1}",
                    long_press_action=switch_cfg.get(
                        CONF_LONG_PRESS_ACTION, LONG_PRESS_ACTION_NONE
                    ),
                )
            )
    else:
        # Legacy single-switch format: preserve backward compatibility.
        entities.append(
            SwitchControlEntity(
                entry=entry,
                name=data[CONF_NAME],
                sensor_entity_id=data[CONF_SENSOR_ENTITY_ID],
                output_entity_ids=data[CONF_OUTPUT_ENTITY_IDS],
                unique_id=entry.entry_id,
                long_press_action=data.get(CONF_LONG_PRESS_ACTION, LONG_PRESS_ACTION_NONE),
            )
        )

    async_add_entities(entities)


class SwitchControlEntity(SwitchEntity, RestoreEntity):
    """Represents a switch controller that monitors a sensor and controls outputs."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        entry: ConfigEntry,
        name: str,
        sensor_entity_id: str,
        output_entity_ids: list[str],
        unique_id: str,
        long_press_action: str = LONG_PRESS_ACTION_NONE,
    ) -> None:
        """Initialize the Switch Control entity."""
        self._entry = entry
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._sensor_entity_id = sensor_entity_id
        self._output_entity_ids = output_entity_ids
        self._long_press_action = long_press_action
        self._attr_is_on = False
        self._long_press_task: asyncio.Task | None = None
        self._long_press_fired: bool = False

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        # Restore the previous switch state so toggle works correctly after restart
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_on = last_state.state == STATE_ON

        # Track the sensor state changes
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._sensor_entity_id],
                self._handle_sensor_state_change,
            )
        )

        self.async_write_ha_state()

    @callback
    def _handle_sensor_state_change(self, event: Any) -> None:
        """Handle sensor state changes and propagate to outputs."""
        new_state = event.data.get("new_state")
        if new_state is None:
            return

        is_on = new_state.state == STATE_ON

        if is_on:
            # Button pressed: toggle the output state immediately
            self._long_press_fired = False
            self._attr_is_on = not self._attr_is_on
            self.async_write_ha_state()
            self.hass.async_create_task(self._apply_outputs(self._attr_is_on))

            # Notify listeners that the button was pressed
            self.hass.bus.async_fire(
                EVENT_BUTTON_PRESSED,
                {"entity_id": self.entity_id},
            )

            # Start long-press detection
            self._long_press_task = self.hass.async_create_task(
                self._detect_long_press()
            )
        else:
            # Button released: cancel any pending long-press timer
            if self._long_press_task is not None and not self._long_press_task.done():
                self._long_press_task.cancel()
                # Schedule awaiting the cancellation so cleanup completes properly
                self.hass.async_create_task(self._await_cancel(self._long_press_task))
            self._long_press_task = None

            # If a long press was active, fire the release event
            if self._long_press_fired:
                self.hass.bus.async_fire(
                    EVENT_LONG_PRESS_RELEASED,
                    {"entity_id": self.entity_id},
                )
                self._long_press_fired = False

    async def _await_cancel(self, task: asyncio.Task) -> None:
        """Await a cancelled task, suppressing the CancelledError."""
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _detect_long_press(self) -> None:
        """Wait for the long-press threshold and fire the long-press event."""
        try:
            await asyncio.sleep(LONG_PRESS_THRESHOLD)
        except asyncio.CancelledError:
            raise
        self._long_press_fired = True
        self.hass.bus.async_fire(
            EVENT_LONG_PRESS,
            {"entity_id": self.entity_id},
        )

        if self._long_press_action == LONG_PRESS_ACTION_TURN_ON:
            self._attr_is_on = True
            await self._apply_outputs(True)
            self.async_write_ha_state()
        elif self._long_press_action == LONG_PRESS_ACTION_TURN_OFF:
            self._attr_is_on = False
            await self._apply_outputs(False)
            self.async_write_ha_state()
        elif self._long_press_action == LONG_PRESS_ACTION_TOGGLE:
            self._attr_is_on = not self._attr_is_on
            await self._apply_outputs(self._attr_is_on)
            self.async_write_ha_state()

    async def _apply_outputs(self, turn_on: bool) -> None:
        """Turn all output entities on or off."""
        for entity_id in self._output_entity_ids:
            domain = entity_id.split(".")[0]
            service = "turn_on" if turn_on else "turn_off"
            await self.hass.services.async_call(
                domain,
                service,
                {"entity_id": entity_id},
                blocking=False,
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the controller and all outputs."""
        self._attr_is_on = True
        self.async_write_ha_state()
        await self._apply_outputs(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the controller and all outputs."""
        self._attr_is_on = False
        self.async_write_ha_state()
        await self._apply_outputs(False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "sensor_entity_id": self._sensor_entity_id,
            "output_entity_ids": self._output_entity_ids,
            "long_press_action": self._long_press_action,
        }
