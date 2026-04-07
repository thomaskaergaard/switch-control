"""Switch platform for the Switch Control integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.const import STATE_ON, STATE_OFF

from .const import (
    CONF_DOUBLE_PRESS_ACTION,
    CONF_DOUBLE_PRESS_OUTPUT_ENTITY_IDS,
    CONF_LONG_PRESS_ACTION,
    CONF_LONG_PRESS_OUTPUT_ENTITY_IDS,
    CONF_NAME,
    CONF_OUTPUT_ENTITY_IDS,
    CONF_SENSOR_ENTITY_ID,
    CONF_SWITCHES,
    DIM_INTERVAL,
    DIM_STEP_PCT,
    DOMAIN,
    DOUBLE_PRESS_ACTION_NONE,
    DOUBLE_PRESS_ACTION_TOGGLE,
    DOUBLE_PRESS_ACTION_TURN_OFF,
    DOUBLE_PRESS_ACTION_TURN_ON,
    DOUBLE_PRESS_THRESHOLD,
    EVENT_BUTTON_PRESSED,
    EVENT_BUTTON_RELEASED,
    EVENT_DOUBLE_PRESS,
    EVENT_HOLD,
    EVENT_LONG_PRESS,
    EVENT_LONG_PRESS_RELEASED,
    HOLD_REPEAT_INTERVAL,
    LONG_PRESS_ACTION_DIM_DOWN,
    LONG_PRESS_ACTION_DIM_UP,
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
                    switch_index=i,
                    long_press_action=switch_cfg.get(
                        CONF_LONG_PRESS_ACTION, LONG_PRESS_ACTION_NONE
                    ),
                    long_press_output_entity_ids=switch_cfg.get(
                        CONF_LONG_PRESS_OUTPUT_ENTITY_IDS, []
                    ),
                    double_press_action=switch_cfg.get(
                        CONF_DOUBLE_PRESS_ACTION, DOUBLE_PRESS_ACTION_NONE
                    ),
                    double_press_output_entity_ids=switch_cfg.get(
                        CONF_DOUBLE_PRESS_OUTPUT_ENTITY_IDS, []
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
                switch_index=None,
                long_press_action=data.get(CONF_LONG_PRESS_ACTION, LONG_PRESS_ACTION_NONE),
                long_press_output_entity_ids=data.get(CONF_LONG_PRESS_OUTPUT_ENTITY_IDS, []),
                double_press_action=data.get(CONF_DOUBLE_PRESS_ACTION, DOUBLE_PRESS_ACTION_NONE),
                double_press_output_entity_ids=data.get(CONF_DOUBLE_PRESS_OUTPUT_ENTITY_IDS, []),
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
        switch_index: int | None = None,
        long_press_action: str = LONG_PRESS_ACTION_NONE,
        long_press_output_entity_ids: list[str] | None = None,
        double_press_action: str = DOUBLE_PRESS_ACTION_NONE,
        double_press_output_entity_ids: list[str] | None = None,
    ) -> None:
        """Initialize the Switch Control entity."""
        self._entry = entry
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._sensor_entity_id = sensor_entity_id
        self._output_entity_ids = output_entity_ids
        self._switch_index = switch_index
        self._long_press_action = long_press_action
        self._long_press_output_entity_ids: list[str] = long_press_output_entity_ids or []
        self._double_press_action = double_press_action
        self._double_press_output_entity_ids: list[str] = double_press_output_entity_ids or []
        self._attr_is_on = False
        self._long_press_task: asyncio.Task | None = None
        self._long_press_fired: bool = False
        self._dim_task: asyncio.Task | None = None
        self._press_count: int = 0
        self._double_press_window_task: asyncio.Task | None = None
        self._remove_sensor_listener: Callable[[], None] | None = None
        self._pre_press_state: bool = False

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to group all switch entities under one panel device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.data.get(CONF_NAME, self._entry.title),
            manufacturer="Switch Control",
            model="Switch Panel",
        )

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        # Restore the previous switch state so toggle works correctly after restart
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_on = last_state.state == STATE_ON

        # Track the sensor state changes; store cancel function for re-registration
        self._remove_sensor_listener = async_track_state_change_event(
            self.hass,
            [self._sensor_entity_id],
            self._handle_sensor_state_change,
        )
        self.async_on_remove(self._cleanup_sensor_listener)

        # Listen for config entry changes and update settings in-place
        self.async_on_remove(
            self._entry.add_update_listener(self._async_config_updated)
        )

        self.async_write_ha_state()

    def _cleanup_sensor_listener(self) -> None:
        """Cancel the sensor state-change listener."""
        if self._remove_sensor_listener is not None:
            self._remove_sensor_listener()
            self._remove_sensor_listener = None

    def _get_switch_config(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Return the config dict for this entity from entry data, or None if unavailable."""
        if self._switch_index is None:
            # Legacy single-switch format: config lives at the top level
            return data
        if CONF_SWITCHES in data and self._switch_index < len(data[CONF_SWITCHES]):
            return data[CONF_SWITCHES][self._switch_index]
        return None

    async def _async_config_updated(
        self, hass: HomeAssistant, entry: ConfigEntry
    ) -> None:
        """Update entity settings in-place when the config entry is changed."""
        sw = self._get_switch_config(entry.data)
        if sw is None:
            return

        new_sensor = sw[CONF_SENSOR_ENTITY_ID]
        new_outputs = sw[CONF_OUTPUT_ENTITY_IDS]
        new_long = sw.get(CONF_LONG_PRESS_ACTION, LONG_PRESS_ACTION_NONE)
        new_long_outputs = sw.get(CONF_LONG_PRESS_OUTPUT_ENTITY_IDS, [])
        new_double = sw.get(CONF_DOUBLE_PRESS_ACTION, DOUBLE_PRESS_ACTION_NONE)
        new_double_outputs = sw.get(CONF_DOUBLE_PRESS_OUTPUT_ENTITY_IDS, [])
        new_name = sw[CONF_NAME]

        # Re-register the sensor listener if the sensor entity has changed
        if new_sensor != self._sensor_entity_id:
            self._cleanup_sensor_listener()
            self._sensor_entity_id = new_sensor
            self._remove_sensor_listener = async_track_state_change_event(
                self.hass,
                [self._sensor_entity_id],
                self._handle_sensor_state_change,
            )

        self._output_entity_ids = new_outputs
        self._long_press_action = new_long
        self._long_press_output_entity_ids = new_long_outputs
        self._double_press_action = new_double
        self._double_press_output_entity_ids = new_double_outputs
        self._attr_name = new_name
        self.async_write_ha_state()

    def _get_long_press_outputs(self) -> list[str]:
        """Return the output entities to use for long press/hold actions.

        Falls back to the main output list when no long-press-specific list is configured.
        """
        return self._long_press_output_entity_ids or self._output_entity_ids

    def _get_double_press_outputs(self) -> list[str]:
        """Return the output entities to use for double press actions.

        Falls back to the main output list when no double-press-specific list is configured.
        """
        return self._double_press_output_entity_ids or self._output_entity_ids

    @callback
    def _handle_sensor_state_change(self, event: Any) -> None:
        """Handle sensor state changes and propagate to outputs."""
        new_state = event.data.get("new_state")
        if new_state is None:
            return

        is_on = new_state.state == STATE_ON

        if is_on:
            self._press_count += 1

            if self._press_count == 1:
                # First press: toggle the output state immediately
                self._long_press_fired = False
                self._pre_press_state = self._attr_is_on
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

                # Start the double-press detection window
                self._double_press_window_task = self.hass.async_create_task(
                    self._reset_press_count()
                )

            elif self._press_count == 2:
                # Second press within the window — double press detected.
                # Cancel the double-press window timer.
                if (
                    self._double_press_window_task is not None
                    and not self._double_press_window_task.done()
                ):
                    self._double_press_window_task.cancel()
                    self.hass.async_create_task(
                        self._await_cancel(self._double_press_window_task)
                    )
                self._double_press_window_task = None
                self._press_count = 0

                # Also cancel any pending long-press timer from the first press.
                if (
                    self._long_press_task is not None
                    and not self._long_press_task.done()
                ):
                    self._long_press_task.cancel()
                    self.hass.async_create_task(self._await_cancel(self._long_press_task))
                self._long_press_task = None

                # Fire the double-press event.
                self.hass.bus.async_fire(
                    EVENT_DOUBLE_PRESS,
                    {"entity_id": self.entity_id},
                )

                if self._double_press_action == DOUBLE_PRESS_ACTION_NONE:
                    # No specific action: treat the second press as a normal toggle.
                    self._attr_is_on = not self._attr_is_on
                    self.async_write_ha_state()
                    self.hass.async_create_task(self._apply_outputs(self._attr_is_on))
                else:
                    # Apply the configured action directly, overriding the second press.
                    self.hass.async_create_task(self._apply_double_press_action())
        else:
            # Button released: cancel any pending long-press timer
            if self._long_press_task is not None and not self._long_press_task.done():
                self._long_press_task.cancel()
                # Schedule awaiting the cancellation so cleanup completes properly
                self.hass.async_create_task(self._await_cancel(self._long_press_task))
            self._long_press_task = None

            # Cancel any active dim loop
            if self._dim_task is not None and not self._dim_task.done():
                self._dim_task.cancel()
                self.hass.async_create_task(self._await_cancel(self._dim_task))
            self._dim_task = None

            # If a long press was active, fire the release event
            if self._long_press_fired:
                self.hass.bus.async_fire(
                    EVENT_LONG_PRESS_RELEASED,
                    {"entity_id": self.entity_id},
                )
                self._long_press_fired = False

            # Always fire a button released event so automations can react to any release
            self.hass.bus.async_fire(
                EVENT_BUTTON_RELEASED,
                {"entity_id": self.entity_id},
            )

    async def _reset_press_count(self) -> None:
        """Reset the press counter after the double-press detection window expires."""
        await asyncio.sleep(DOUBLE_PRESS_THRESHOLD)
        self._press_count = 0

    async def _await_cancel(self, task: asyncio.Task) -> None:
        """Await a cancelled task, suppressing the CancelledError."""
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _detect_long_press(self) -> None:
        """Wait for the long-press threshold, fire the long-press event, then hold."""
        try:
            await asyncio.sleep(LONG_PRESS_THRESHOLD)
        except asyncio.CancelledError:
            raise
        self._long_press_fired = True

        # Revert the initial press toggle so the long press action starts from
        # the pre-press state, not the already-toggled state.
        self._attr_is_on = self._pre_press_state
        await self._apply_outputs(self._pre_press_state)
        self.async_write_ha_state()

        self.hass.bus.async_fire(
            EVENT_LONG_PRESS,
            {"entity_id": self.entity_id},
        )

        if self._long_press_action == LONG_PRESS_ACTION_TURN_ON:
            self._attr_is_on = True
            await self._apply_outputs(True, self._get_long_press_outputs())
            self.async_write_ha_state()
        elif self._long_press_action == LONG_PRESS_ACTION_TURN_OFF:
            self._attr_is_on = False
            await self._apply_outputs(False, self._get_long_press_outputs())
            self.async_write_ha_state()
        elif self._long_press_action == LONG_PRESS_ACTION_TOGGLE:
            # Toggle from the pre-press state (already restored above).
            target = not self._pre_press_state
            self._attr_is_on = target
            await self._apply_outputs(target, self._get_long_press_outputs())
            self.async_write_ha_state()
        elif self._long_press_action in (LONG_PRESS_ACTION_DIM_UP, LONG_PRESS_ACTION_DIM_DOWN):
            self._dim_task = self.hass.async_create_task(self._apply_dim_loop())

        # Continue firing hold events at regular intervals while the button remains
        # pressed.  The task is cancelled when the sensor turns off, which causes
        # the loop to exit via CancelledError.
        while True:
            self.hass.bus.async_fire(
                EVENT_HOLD,
                {"entity_id": self.entity_id},
            )
            await asyncio.sleep(HOLD_REPEAT_INTERVAL)

    async def _apply_dim_loop(self) -> None:
        """Repeatedly step brightness up or down while the button is held."""
        step = (
            DIM_STEP_PCT
            if self._long_press_action == LONG_PRESS_ACTION_DIM_UP
            else -DIM_STEP_PCT
        )
        while True:
            for entity_id in self._get_long_press_outputs():
                if entity_id.split(".")[0] == "light":
                    await self.hass.services.async_call(
                        "light",
                        "turn_on",
                        {"entity_id": entity_id, "brightness_step_pct": step},
                        blocking=False,
                    )
            await asyncio.sleep(DIM_INTERVAL)

    async def _apply_double_press_action(self) -> None:
        """Apply the configured double-press action to all output entities."""
        if self._double_press_action == DOUBLE_PRESS_ACTION_TURN_ON:
            self._attr_is_on = True
            await self._apply_outputs(True, self._get_double_press_outputs())
            self.async_write_ha_state()
        elif self._double_press_action == DOUBLE_PRESS_ACTION_TURN_OFF:
            self._attr_is_on = False
            await self._apply_outputs(False, self._get_double_press_outputs())
            self.async_write_ha_state()
        elif self._double_press_action == DOUBLE_PRESS_ACTION_TOGGLE:
            # Toggle from the state that was active before the first press so that
            # the initial press-toggle and the double-press toggle don't cancel each other out.
            target = not self._pre_press_state
            if self._attr_is_on != target:
                self._attr_is_on = target
                await self._apply_outputs(target, self._get_double_press_outputs())
                self.async_write_ha_state()

    async def _apply_outputs(self, turn_on: bool, entity_ids: list[str] | None = None) -> None:
        """Turn output entities on or off.

        Uses ``entity_ids`` when provided, otherwise falls back to the main
        ``_output_entity_ids`` list (press/default outputs).
        """
        targets = entity_ids if entity_ids is not None else self._output_entity_ids
        for entity_id in targets:
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
            "long_press_output_entity_ids": self._long_press_output_entity_ids,
            "double_press_action": self._double_press_action,
            "double_press_output_entity_ids": self._double_press_output_entity_ids,
        }
