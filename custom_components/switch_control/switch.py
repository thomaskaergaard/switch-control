"""Switch platform for the Switch Control integration."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Callable

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.script import Script
from homeassistant.const import STATE_ON, STATE_OFF

from .const import (
    CONF_DIM_AUTO_THRESHOLD,
    CONF_DOUBLE_PRESS_ACTION,
    CONF_DOUBLE_PRESS_ACTIONS,
    CONF_DOUBLE_PRESS_OUTPUT_ENTITY_IDS,
    CONF_LONG_PRESS_ACTION,
    CONF_LONG_PRESS_ACTIONS,
    CONF_LONG_PRESS_OUTPUT_ENTITY_IDS,
    CONF_LONG_PRESS_RELEASED_ACTIONS,
    CONF_NAME,
    CONF_OUTPUT_ENTITY_IDS,
    CONF_PLAY_MODE_ENABLED,
    CONF_PLAY_MODE_FINISHED_ACTIONS,
    CONF_PLAY_MODE_ROUND_DELAY,
    CONF_PLAY_MODE_ROUND_TIMEOUT,
    CONF_PLAY_MODE_ROUNDS,
    CONF_PRESS_ACTIONS,
    CONF_RELEASED_ACTIONS,
    CONF_SENSOR_ENTITY_ID,
    CONF_SWITCHES,
    DIM_AUTO_THRESHOLD,
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
    EVENT_PLAY_MODE_CORRECT_PRESS,
    EVENT_PLAY_MODE_FINISHED,
    EVENT_PLAY_MODE_INCORRECT_PRESS,
    EVENT_PLAY_MODE_ROUND_STARTED,
    EVENT_PLAY_MODE_ROUND_TIMEOUT,
    EVENT_PLAY_MODE_STARTED,
    EVENT_PLAY_MODE_STOPPED,
    HOLD_REPEAT_INTERVAL,
    LONG_PRESS_ACTION_DIM_AUTO,
    LONG_PRESS_ACTION_DIM_DOWN,
    LONG_PRESS_ACTION_DIM_UP,
    LONG_PRESS_ACTION_NONE,
    LONG_PRESS_ACTION_TOGGLE,
    LONG_PRESS_ACTION_TURN_OFF,
    LONG_PRESS_ACTION_TURN_ON,
    LONG_PRESS_THRESHOLD,
    PLAY_MODE_DEFAULT_ENABLED,
    PLAY_MODE_DEFAULT_ROUND_DELAY,
    PLAY_MODE_DEFAULT_ROUND_TIMEOUT,
    PLAY_MODE_DEFAULT_ROUNDS,
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
    play_manager = PanelPlayModeManager(hass, entry, data)

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
                    dim_auto_threshold=switch_cfg.get(
                        CONF_DIM_AUTO_THRESHOLD, DIM_AUTO_THRESHOLD
                    ),
                    press_actions=switch_cfg.get(CONF_PRESS_ACTIONS, []),
                    released_actions=switch_cfg.get(CONF_RELEASED_ACTIONS, []),
                    double_press_actions=switch_cfg.get(CONF_DOUBLE_PRESS_ACTIONS, []),
                    long_press_actions=switch_cfg.get(CONF_LONG_PRESS_ACTIONS, []),
                    long_press_released_actions=switch_cfg.get(
                        CONF_LONG_PRESS_RELEASED_ACTIONS, []
                    ),
                    play_manager=play_manager,
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
                dim_auto_threshold=data.get(CONF_DIM_AUTO_THRESHOLD, DIM_AUTO_THRESHOLD),
                play_manager=play_manager,
            )
        )

    services_registered_key = f"{DOMAIN}_entity_services_registered"
    if not hass.data.get(services_registered_key):
        platform = entity_platform.async_get_current_platform()
        platform.async_register_entity_service("start_play_mode", {}, "async_start_play_mode")
        platform.async_register_entity_service("stop_play_mode", {}, "async_stop_play_mode")
        hass.data[services_registered_key] = True

    async_add_entities(entities)


class PanelPlayModeManager:
    """Shared play mode state and flow for all switches in one panel."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, data: dict[str, Any]) -> None:
        """Initialize panel-level play mode state."""
        self._hass = hass
        self._entry = entry
        self._entities: list[SwitchControlEntity] = []
        self._active = False
        self._target_entity: SwitchControlEntity | None = None
        self._score = 0
        self._attempts = 0
        self._timeout_task: asyncio.Task | None = None
        self._next_round_task: asyncio.Task | None = None
        self._last_target_unique_id: str | None = None
        self._started_at: float | None = None
        self._update_config(data)

    def _update_config(self, data: dict[str, Any]) -> None:
        """Refresh play mode settings from config entry data."""
        self._enabled = data.get(CONF_PLAY_MODE_ENABLED, PLAY_MODE_DEFAULT_ENABLED)
        self._goal = int(data.get(CONF_PLAY_MODE_ROUNDS, PLAY_MODE_DEFAULT_ROUNDS))
        self._round_timeout = int(
            data.get(CONF_PLAY_MODE_ROUND_TIMEOUT, PLAY_MODE_DEFAULT_ROUND_TIMEOUT)
        )
        self._round_delay = int(
            data.get(CONF_PLAY_MODE_ROUND_DELAY, PLAY_MODE_DEFAULT_ROUND_DELAY)
        )
        self._finished_actions: list[dict] = data.get(CONF_PLAY_MODE_FINISHED_ACTIONS, [])

    @property
    def is_active(self) -> bool:
        """Return True when a play mode session is currently running."""
        return self._active

    @property
    def enabled(self) -> bool:
        """Return True when play mode is enabled for this panel."""
        return self._enabled

    @property
    def goal(self) -> int:
        """Return the configured number of correct switches to find."""
        return self._goal

    @property
    def score(self) -> int:
        """Return the current number of correctly found switches."""
        return self._score

    @property
    def target_entity_id(self) -> str | None:
        """Return entity_id for the current target switch, if any."""
        return self._target_entity.entity_id if self._target_entity else None

    def register_entity(self, entity: SwitchControlEntity) -> None:
        """Register a switch entity under this panel manager."""
        if entity not in self._entities:
            self._entities.append(entity)

    def unregister_entity(self, entity: SwitchControlEntity) -> None:
        """Unregister a switch entity from this panel manager."""
        if entity in self._entities:
            self._entities.remove(entity)

    async def async_config_updated(self, data: dict[str, Any]) -> None:
        """Update manager config and stop active game if play mode disabled."""
        was_enabled = self._enabled
        self._update_config(data)
        if was_enabled and not self._enabled and self._active:
            await self.async_stop_game("disabled")

    async def async_start_game(self) -> None:
        """Start a new play mode game."""
        if not self._enabled:
            _LOGGER.debug("Play mode ignored for %s: disabled", self._entry.entry_id)
            return

        available_entities = [entity for entity in self._entities if entity.has_outputs]
        if not available_entities:
            _LOGGER.warning("Play mode ignored for %s: no outputs configured", self._entry.entry_id)
            return

        await self._cancel_internal_tasks()
        self._active = True
        self._score = 0
        self._attempts = 0
        self._target_entity = None
        self._last_target_unique_id = None
        self._started_at = time.monotonic()

        self._hass.bus.async_fire(
            EVENT_PLAY_MODE_STARTED,
            {
                "entry_id": self._entry.entry_id,
                "goal": self._goal,
                "round_timeout": self._round_timeout,
                "round_delay": self._round_delay,
            },
        )
        self._async_write_entities_state()
        await self._async_start_round()

    async def async_stop_game(self, reason: str = "stopped") -> None:
        """Stop the active play mode game and clean up outputs."""
        if not self._active:
            return

        elapsed_time = self._get_elapsed_time()
        await self._cancel_internal_tasks()
        self._active = False
        self._target_entity = None
        await self._async_turn_off_all_outputs()
        self._hass.bus.async_fire(
            EVENT_PLAY_MODE_STOPPED,
            {
                "entry_id": self._entry.entry_id,
                "reason": reason,
                "score": self._score,
                "goal": self._goal,
                "attempts": self._attempts,
                "elapsed_time": elapsed_time,
                "time_used": elapsed_time,
            },
        )
        self._started_at = None
        self._async_write_entities_state()

    async def async_handle_press(self, pressed_entity: SwitchControlEntity) -> None:
        """Handle a switch press during play mode."""
        if not self._active or self._target_entity is None:
            return

        self._attempts += 1
        if pressed_entity is self._target_entity:
            self._score += 1
            self._hass.bus.async_fire(
                EVENT_PLAY_MODE_CORRECT_PRESS,
                {
                    "entry_id": self._entry.entry_id,
                    "pressed_entity_id": pressed_entity.entity_id,
                    "target_entity_id": self._target_entity.entity_id,
                    "score": self._score,
                    "goal": self._goal,
                    "attempts": self._attempts,
                },
            )
            await self._cancel_timeout_task()
            if self._score >= self._goal:
                await self._async_finish_game()
                return

            if self._round_delay > 0:
                self._next_round_task = self._hass.async_create_task(
                    self._async_start_round_after_delay()
                )
            else:
                await self._async_start_round()
            self._async_write_entities_state()
            return

        self._hass.bus.async_fire(
            EVENT_PLAY_MODE_INCORRECT_PRESS,
            {
                "entry_id": self._entry.entry_id,
                "pressed_entity_id": pressed_entity.entity_id,
                "target_entity_id": self._target_entity.entity_id,
                "score": self._score,
                "goal": self._goal,
                "attempts": self._attempts,
            },
        )

    async def _async_start_round_after_delay(self) -> None:
        """Start the next target round after configured delay."""
        try:
            await asyncio.sleep(self._round_delay)
        except asyncio.CancelledError:
            return
        await self._async_start_round()

    async def _async_start_round(self) -> None:
        """Select a new target and update outputs for the current round."""
        if not self._active:
            return

        await self._cancel_timeout_task()
        target = self._select_target_entity()
        if target is None:
            await self._async_finish_game()
            return

        self._target_entity = target
        self._last_target_unique_id = target.unique_id
        await self._async_turn_off_all_outputs()
        await self._async_apply_outputs(True, target.output_entity_ids)

        self._hass.bus.async_fire(
            EVENT_PLAY_MODE_ROUND_STARTED,
            {
                "entry_id": self._entry.entry_id,
                "target_entity_id": target.entity_id,
                "round": self._score + 1,
                "goal": self._goal,
                "score": self._score,
                "attempts": self._attempts,
            },
        )
        self._async_write_entities_state()

        if self._round_timeout > 0:
            self._timeout_task = self._hass.async_create_task(
                self._async_round_timeout(target.unique_id)
            )

    def _select_target_entity(self) -> SwitchControlEntity | None:
        """Pick a target entity from configured panel switches."""
        candidates = [entity for entity in self._entities if entity.has_outputs]
        if not candidates:
            return None

        if len(candidates) > 1 and self._last_target_unique_id is not None:
            non_repeating = [
                entity for entity in candidates if entity.unique_id != self._last_target_unique_id
            ]
            if non_repeating:
                candidates = non_repeating
        return random.choice(candidates)

    async def _async_round_timeout(self, target_unique_id: str) -> None:
        """Handle timeout for the current target round."""
        try:
            await asyncio.sleep(self._round_timeout)
        except asyncio.CancelledError:
            return

        if (
            not self._active
            or self._target_entity is None
            or self._target_entity.unique_id != target_unique_id
        ):
            return

        self._hass.bus.async_fire(
            EVENT_PLAY_MODE_ROUND_TIMEOUT,
            {
                "entry_id": self._entry.entry_id,
                "target_entity_id": self._target_entity.entity_id,
                "round": self._score + 1,
                "goal": self._goal,
                "score": self._score,
                "attempts": self._attempts,
            },
        )
        await self._async_start_round()

    async def _async_finish_game(self) -> None:
        """Finish game after reaching the configured goal."""
        elapsed_time = self._get_elapsed_time()
        await self._cancel_internal_tasks()
        self._active = False
        await self._async_turn_off_all_outputs()
        self._hass.bus.async_fire(
            EVENT_PLAY_MODE_FINISHED,
            {
                "entry_id": self._entry.entry_id,
                "score": self._score,
                "goal": self._goal,
                "attempts": self._attempts,
                "elapsed_time": elapsed_time,
                "time_used": elapsed_time,
            },
        )
        if self._finished_actions:
            await self._run_finished_actions(
                elapsed_time=elapsed_time,
                score=self._score,
                goal=self._goal,
                attempts=self._attempts,
            )
        self._started_at = None
        self._target_entity = None
        self._async_write_entities_state()

    def _get_elapsed_time(self) -> float:
        """Return the elapsed play mode time in seconds."""
        if self._started_at is None:
            return 0.0
        return round(max(0.0, time.monotonic() - self._started_at), 1)

    async def _run_finished_actions(
        self,
        *,
        elapsed_time: float,
        score: int,
        goal: int,
        attempts: int,
    ) -> None:
        """Run configured actions for play mode finish."""
        script = Script(
            self._hass,
            self._finished_actions,
            f"{self._entry.title} play mode finished",
            DOMAIN,
        )
        try:
            await script.async_run(
                {
                    "entry_id": self._entry.entry_id,
                    "score": score,
                    "goal": goal,
                    "attempts": attempts,
                    "elapsed_time": elapsed_time,
                    "time_used": elapsed_time,
                }
            )
        except Exception:
            _LOGGER.exception(
                "Error running play mode finished actions for entry %s",
                self._entry.entry_id,
            )
        finally:
            await script.async_stop()

    async def _async_turn_off_all_outputs(self) -> None:
        """Turn off all outputs referenced by panel switch entities."""
        outputs: set[str] = set()
        for entity in self._entities:
            outputs.update(entity.output_entity_ids)
        if outputs:
            await self._async_apply_outputs(False, list(outputs))

    async def _async_apply_outputs(self, turn_on: bool, entity_ids: list[str]) -> None:
        """Apply on/off service call to a list of entity IDs."""
        service = "turn_on" if turn_on else "turn_off"
        for entity_id in entity_ids:
            domain = entity_id.split(".")[0]
            await self._hass.services.async_call(
                domain,
                service,
                {"entity_id": entity_id},
                blocking=False,
            )

    async def _cancel_timeout_task(self) -> None:
        """Cancel active round timeout task."""
        if self._timeout_task is None or self._timeout_task.done():
            self._timeout_task = None
            return
        self._timeout_task.cancel()
        await self._await_task_cancel(self._timeout_task)
        self._timeout_task = None

    async def _cancel_internal_tasks(self) -> None:
        """Cancel all manager-owned pending tasks."""
        await self._cancel_timeout_task()
        if self._next_round_task is None or self._next_round_task.done():
            self._next_round_task = None
            return
        self._next_round_task.cancel()
        await self._await_task_cancel(self._next_round_task)
        self._next_round_task = None

    async def _await_task_cancel(self, task: asyncio.Task) -> None:
        """Await cancellation of a task owned by the manager."""
        try:
            await task
        except asyncio.CancelledError:
            pass

    def _async_write_entities_state(self) -> None:
        """Push updated manager-dependent attributes to all panel entities."""
        for entity in self._entities:
            entity.async_write_ha_state()


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
        dim_auto_threshold: int = DIM_AUTO_THRESHOLD,
        press_actions: list[dict] | None = None,
        released_actions: list[dict] | None = None,
        double_press_actions: list[dict] | None = None,
        long_press_actions: list[dict] | None = None,
        long_press_released_actions: list[dict] | None = None,
        play_manager: PanelPlayModeManager | None = None,
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
        self._dim_auto_threshold = dim_auto_threshold
        self._press_actions: list[dict] = press_actions or []
        self._released_actions: list[dict] = released_actions or []
        self._double_press_actions: list[dict] = double_press_actions or []
        self._long_press_actions: list[dict] = long_press_actions or []
        self._long_press_released_actions: list[dict] = long_press_released_actions or []
        self._play_manager = play_manager
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
        if self._play_manager is not None:
            self._play_manager.register_entity(self)
            self.async_on_remove(lambda: self._play_manager.unregister_entity(self))

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
        new_dim_auto_threshold = sw.get(CONF_DIM_AUTO_THRESHOLD, DIM_AUTO_THRESHOLD)
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
        self._dim_auto_threshold = new_dim_auto_threshold
        self._press_actions = sw.get(CONF_PRESS_ACTIONS, [])
        self._released_actions = sw.get(CONF_RELEASED_ACTIONS, [])
        self._double_press_actions = sw.get(CONF_DOUBLE_PRESS_ACTIONS, [])
        self._long_press_actions = sw.get(CONF_LONG_PRESS_ACTIONS, [])
        self._long_press_released_actions = sw.get(CONF_LONG_PRESS_RELEASED_ACTIONS, [])
        self._attr_name = new_name
        if self._play_manager is not None:
            await self._play_manager.async_config_updated(entry.data)
        self.async_write_ha_state()

    @property
    def output_entity_ids(self) -> list[str]:
        """Return primary output entities for this switch."""
        return self._output_entity_ids

    @property
    def has_outputs(self) -> bool:
        """Return True when this switch has output entities configured."""
        return len(self._output_entity_ids) > 0

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
        if self._play_manager is not None and self._play_manager.is_active:
            if is_on:
                self.hass.async_create_task(self._play_manager.async_handle_press(self))
            return

        if is_on:
            self._press_count += 1

            if self._press_count == 1:
                # First press: record the pre-press state but defer the output
                # toggle until the double-press detection window expires.  This
                # prevents a single-press action from firing when the user is
                # actually performing a double press.
                self._long_press_fired = False
                self._pre_press_state = self._attr_is_on

                # Notify listeners that the button was pressed
                self.hass.bus.async_fire(
                    EVENT_BUTTON_PRESSED,
                    {"entity_id": self.entity_id},
                )

                # Run any configured press actions
                if self._press_actions:
                    self.hass.async_create_task(
                        self._run_actions(self._press_actions, "press")
                    )

                # Start long-press detection
                self._long_press_task = self.hass.async_create_task(
                    self._detect_long_press()
                )

                # The double-press detection window is started on the first
                # RELEASE (see the release handler below) so that the 0.4 s
                # window is measured from the end of the first press rather
                # than from its start.  This gives the user a full 0.4 s gap
                # between releasing the first press and starting the second.

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

                # Run any configured double press actions
                if self._double_press_actions:
                    self.hass.async_create_task(
                        self._run_actions(self._double_press_actions, "double press")
                    )

                if self._double_press_action == DOUBLE_PRESS_ACTION_NONE:
                    # No specific action: fire the event only, leave outputs unchanged.
                    pass
                else:
                    # Apply the configured action directly.
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
                # Run any configured long press released actions
                if self._long_press_released_actions:
                    self.hass.async_create_task(
                        self._run_actions(self._long_press_released_actions, "long press released")
                    )
                self._long_press_fired = False
                # Reset press counter so the next press starts a fresh cycle
                # instead of being treated as a (spurious) second press.
                self._press_count = 0
            elif self._press_count == 1:
                # Short first press released — start the double-press detection
                # window.  If a second press arrives within DOUBLE_PRESS_THRESHOLD
                # seconds the window task is cancelled and the double-press action
                # fires.  If not, the window task applies the single-press toggle.
                self._double_press_window_task = self.hass.async_create_task(
                    self._apply_single_press_after_window()
                )

            # Always fire a button released event so automations can react to any release
            self.hass.bus.async_fire(
                EVENT_BUTTON_RELEASED,
                {"entity_id": self.entity_id},
            )

            # Run any configured released actions
            if self._released_actions:
                self.hass.async_create_task(
                    self._run_actions(self._released_actions, "released")
                )

    async def _apply_single_press_after_window(self) -> None:
        """Apply the single-press toggle once the double-press window expires.

        Started on the first button RELEASE so the 0.4 s window is measured
        from the end of the first press rather than from its start.  If a
        second press arrives before the window expires this task is cancelled
        and the double-press action fires instead, with no prior single-press
        toggle having been applied.
        """
        await asyncio.sleep(DOUBLE_PRESS_THRESHOLD)
        # No second press arrived within the window: apply the single-press toggle.
        # Reset the press counter first so that any press arriving while the
        # outputs are being applied is treated as a fresh first press, not as
        # a (spurious) double-press with already-modified state.
        self._press_count = 0
        self._attr_is_on = not self._pre_press_state
        self.async_write_ha_state()
        await self._apply_outputs(self._attr_is_on)

    async def _run_actions(self, actions: list[dict], label: str) -> None:
        """Execute a sequence of Home Assistant automation actions.

        Creates a transient Script instance, runs it once, then stops it.
        Actions are defined using the standard Home Assistant action format
        (the same syntax used in automation ``action:`` blocks).
        Callers are responsible for only calling this when ``actions`` is non-empty.
        """
        script = Script(
            self.hass,
            actions,
            f"{self._attr_name} {label}",
            DOMAIN,
        )
        try:
            await script.async_run()
        except Exception:
            _LOGGER.exception(
                "Error running %s actions for %s", label, self.entity_id
            )
        finally:
            await script.async_stop()

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

        self.hass.bus.async_fire(
            EVENT_LONG_PRESS,
            {"entity_id": self.entity_id},
        )

        # Run any configured long press actions
        if self._long_press_actions:
            self.hass.async_create_task(
                self._run_actions(self._long_press_actions, "long press")
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
            # Toggle from the state before the first press.
            target = not self._pre_press_state
            self._attr_is_on = target
            await self._apply_outputs(target, self._get_long_press_outputs())
            self.async_write_ha_state()
        elif self._long_press_action in (LONG_PRESS_ACTION_DIM_UP, LONG_PRESS_ACTION_DIM_DOWN, LONG_PRESS_ACTION_DIM_AUTO):
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
        if self._long_press_action == LONG_PRESS_ACTION_DIM_AUTO:
            step = self._determine_dim_auto_step()
        else:
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

    def _determine_dim_auto_step(self) -> int:
        """Determine dim direction based on the current brightness of the first active light.

        Returns a positive step value to dim up, or a negative step value to dim down.
        If the brightness is above the configured threshold, dims down; otherwise dims up.
        Falls back to dim up when no brightness information is available.
        """
        for entity_id in self._get_long_press_outputs():
            if entity_id.split(".")[0] == "light":
                state = self.hass.states.get(entity_id)
                if state is not None and state.state == "on":
                    brightness = state.attributes.get("brightness")
                    if brightness is not None:
                        brightness_pct = brightness / 255 * 100
                        if brightness_pct > self._dim_auto_threshold:
                            return -DIM_STEP_PCT  # dim down
                        return DIM_STEP_PCT  # dim up
        return DIM_STEP_PCT  # default to dim up

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
            # Toggle from the state that was active before the first press.
            target = not self._pre_press_state
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

    async def async_start_play_mode(self) -> None:
        """Start play mode for this panel."""
        if self._play_manager is None:
            return
        await self._play_manager.async_start_game()

    async def async_stop_play_mode(self) -> None:
        """Stop play mode for this panel."""
        if self._play_manager is None:
            return
        await self._play_manager.async_stop_game()

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
            "dim_auto_threshold": self._dim_auto_threshold,
            "play_mode_enabled": (
                self._play_manager.enabled if self._play_manager is not None else False
            ),
            "play_mode_active": (
                self._play_manager.is_active if self._play_manager is not None else False
            ),
            "play_mode_rounds": (
                self._play_manager.goal if self._play_manager is not None else 0
            ),
            "play_mode_score": (
                self._play_manager.score if self._play_manager is not None else 0
            ),
            "play_mode_target_entity_id": (
                self._play_manager.target_entity_id if self._play_manager is not None else None
            ),
        }
