"""Switch platform for the Switch Control integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.const import STATE_ON, STATE_OFF

from .const import (
    CONF_NAME,
    CONF_OUTPUT_ENTITY_IDS,
    CONF_SENSOR_ENTITY_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Switch Control switch entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            SwitchControlEntity(
                entry=entry,
                name=data[CONF_NAME],
                sensor_entity_id=data[CONF_SENSOR_ENTITY_ID],
                output_entity_ids=data[CONF_OUTPUT_ENTITY_IDS],
            )
        ]
    )


class SwitchControlEntity(SwitchEntity):
    """Represents a switch controller that monitors a sensor and controls outputs."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        entry: ConfigEntry,
        name: str,
        sensor_entity_id: str,
        output_entity_ids: list[str],
    ) -> None:
        """Initialize the Switch Control entity."""
        self._entry = entry
        self._attr_name = name
        self._attr_unique_id = entry.entry_id
        self._sensor_entity_id = sensor_entity_id
        self._output_entity_ids = output_entity_ids
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        # Track the sensor state changes
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._sensor_entity_id],
                self._handle_sensor_state_change,
            )
        )

        # Sync state with current sensor state
        sensor_state = self.hass.states.get(self._sensor_entity_id)
        if sensor_state is not None:
            self._attr_is_on = sensor_state.state == STATE_ON
            self.async_write_ha_state()

    @callback
    def _handle_sensor_state_change(self, event: Any) -> None:
        """Handle sensor state changes and propagate to outputs."""
        new_state = event.data.get("new_state")
        if new_state is None:
            return

        is_on = new_state.state == STATE_ON
        self._attr_is_on = is_on
        self.async_write_ha_state()

        self.hass.async_create_task(self._apply_outputs(is_on))

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
        }
