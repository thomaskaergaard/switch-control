"""Config flow for the Switch Control integration."""
from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    ActionSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

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
    CONF_PRESS_ACTIONS,
    CONF_RELEASED_ACTIONS,
    CONF_SENSOR_ENTITY_ID,
    CONF_SWITCH_COUNT,
    CONF_SWITCHES,
    DEFAULT_NAME,
    DIM_AUTO_THRESHOLD,
    DOMAIN,
    DOUBLE_PRESS_ACTION_NONE,
    DOUBLE_PRESS_ACTION_OPTIONS,
    LONG_PRESS_ACTION_NONE,
    LONG_PRESS_ACTION_OPTIONS,
    SWITCH_COUNT_OPTIONS,
)


class SwitchControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Switch Control."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._switch_count: int = 0
        self._current_switch: int = 0
        self._detected_sensor: str | None = None
        self._detect_task: asyncio.Task | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SwitchControlOptionsFlow:
        """Create the options flow handler."""
        return SwitchControlOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: name and number of switches."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data[CONF_NAME] = user_input[CONF_NAME]
            self._switch_count = int(user_input[CONF_SWITCH_COUNT])
            self._data[CONF_SWITCH_COUNT] = self._switch_count
            self._data[CONF_SWITCHES] = []
            self._current_switch = 1
            return await self.async_step_switch_detect()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): TextSelector(),
                vol.Required(CONF_SWITCH_COUNT): SelectSelector(
                    SelectSelectorConfig(
                        options=SWITCH_COUNT_OPTIONS,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_switch_detect(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a progress screen while listening for a physical button press."""
        if self._detect_task is None:
            self._detected_sensor = None
            self._detect_task = self.hass.async_create_task(
                self._async_detect_sensor_input()
            )

        if not self._detect_task.done():
            return self.async_show_progress(
                step_id="switch_detect",
                progress_action="detecting_input",
                progress_task=self._detect_task,
                description_placeholders={
                    "switch_num": str(self._current_switch),
                    "switch_count": str(self._switch_count),
                },
            )

        self._detect_task = None
        return self.async_show_progress_done(next_step_id="switch")

    async def _async_detect_sensor_input(self) -> None:
        """Listen for a state-change event to auto-detect the input sensor entity."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()

        @callback
        def _listener(event: Event) -> None:
            entity_id: str = event.data.get("entity_id", "")
            domain = entity_id.split(".")[0] if "." in entity_id else ""
            if domain in (BINARY_SENSOR_DOMAIN, SENSOR_DOMAIN) and not future.done():
                future.set_result(entity_id)

        unsub = self.hass.bus.async_listen(EVENT_STATE_CHANGED, _listener)
        try:
            self._detected_sensor = await asyncio.wait_for(future, timeout=30.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._detected_sensor = None
        finally:
            unsub()

    async def async_step_switch(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle configuration of an individual switch input."""
        errors: dict[str, str] = {}

        if user_input is not None:
            sensor_entity_id = user_input[CONF_SENSOR_ENTITY_ID]
            output_entity_ids = user_input[CONF_OUTPUT_ENTITY_IDS]

            ent_reg = er.async_get(self.hass)

            if not ent_reg.async_get(sensor_entity_id) and not self.hass.states.get(
                sensor_entity_id
            ):
                errors[CONF_SENSOR_ENTITY_ID] = "sensor_not_found"
            else:
                used_sensor_ids: set[str] = set()
                for entry in self.hass.config_entries.async_entries(DOMAIN):
                    for sw in entry.data.get(CONF_SWITCHES, []):
                        used_sensor_ids.add(sw[CONF_SENSOR_ENTITY_ID])
                for sw in self._data.get(CONF_SWITCHES, []):
                    used_sensor_ids.add(sw[CONF_SENSOR_ENTITY_ID])
                if sensor_entity_id in used_sensor_ids:
                    errors[CONF_SENSOR_ENTITY_ID] = "sensor_already_in_use"

            if not errors:
                self._data[CONF_SWITCHES].append(
                    {
                        CONF_NAME: user_input[CONF_NAME],
                        CONF_SENSOR_ENTITY_ID: sensor_entity_id,
                        CONF_OUTPUT_ENTITY_IDS: output_entity_ids,
                        CONF_LONG_PRESS_ACTION: user_input.get(
                            CONF_LONG_PRESS_ACTION, LONG_PRESS_ACTION_NONE
                        ),
                        CONF_LONG_PRESS_OUTPUT_ENTITY_IDS: user_input.get(
                            CONF_LONG_PRESS_OUTPUT_ENTITY_IDS, []
                        ),
                        CONF_DIM_AUTO_THRESHOLD: user_input.get(
                            CONF_DIM_AUTO_THRESHOLD, DIM_AUTO_THRESHOLD
                        ),
                        CONF_DOUBLE_PRESS_ACTION: user_input.get(
                            CONF_DOUBLE_PRESS_ACTION, DOUBLE_PRESS_ACTION_NONE
                        ),
                        CONF_DOUBLE_PRESS_OUTPUT_ENTITY_IDS: user_input.get(
                            CONF_DOUBLE_PRESS_OUTPUT_ENTITY_IDS, []
                        ),
                        CONF_PRESS_ACTIONS: user_input.get(CONF_PRESS_ACTIONS, []),
                        CONF_RELEASED_ACTIONS: user_input.get(CONF_RELEASED_ACTIONS, []),
                        CONF_DOUBLE_PRESS_ACTIONS: user_input.get(CONF_DOUBLE_PRESS_ACTIONS, []),
                        CONF_LONG_PRESS_ACTIONS: user_input.get(CONF_LONG_PRESS_ACTIONS, []),
                        CONF_LONG_PRESS_RELEASED_ACTIONS: user_input.get(
                            CONF_LONG_PRESS_RELEASED_ACTIONS, []
                        ),
                    }
                )
                self._current_switch += 1

                if self._current_switch > self._switch_count:
                    return self.async_create_entry(
                        title=self._data[CONF_NAME],
                        data=self._data,
                    )

                return await self.async_step_switch_detect()

        detected = self._detected_sensor
        self._detected_sensor = None
        default_switch_name = f"Switch {self._current_switch}"
        sensor_field = (
            vol.Required(CONF_SENSOR_ENTITY_ID, default=detected)
            if detected
            else vol.Required(CONF_SENSOR_ENTITY_ID)
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=default_switch_name): TextSelector(),
                sensor_field: EntitySelector(
                    EntitySelectorConfig(domain=[BINARY_SENSOR_DOMAIN, SENSOR_DOMAIN])
                ),
                vol.Optional(CONF_OUTPUT_ENTITY_IDS, default=[]): EntitySelector(
                    EntitySelectorConfig(
                        domain=["switch", "light"],
                        multiple=True,
                    )
                ),
                vol.Optional(
                    CONF_LONG_PRESS_ACTION, default=LONG_PRESS_ACTION_NONE
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=LONG_PRESS_ACTION_OPTIONS,
                        mode=SelectSelectorMode.LIST,
                        translation_key=CONF_LONG_PRESS_ACTION,
                    )
                ),
                vol.Optional(CONF_LONG_PRESS_OUTPUT_ENTITY_IDS, default=[]): EntitySelector(
                    EntitySelectorConfig(
                        domain=["switch", "light"],
                        multiple=True,
                    )
                ),
                vol.Optional(
                    CONF_DIM_AUTO_THRESHOLD, default=DIM_AUTO_THRESHOLD
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=100,
                        step=1,
                        unit_of_measurement="%",
                        mode=NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Optional(
                    CONF_DOUBLE_PRESS_ACTION, default=DOUBLE_PRESS_ACTION_NONE
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=DOUBLE_PRESS_ACTION_OPTIONS,
                        mode=SelectSelectorMode.LIST,
                        translation_key=CONF_DOUBLE_PRESS_ACTION,
                    )
                ),
                vol.Optional(CONF_DOUBLE_PRESS_OUTPUT_ENTITY_IDS, default=[]): EntitySelector(
                    EntitySelectorConfig(
                        domain=["switch", "light"],
                        multiple=True,
                    )
                ),
                vol.Optional(CONF_PRESS_ACTIONS, default=[]): ActionSelector(),
                vol.Optional(CONF_RELEASED_ACTIONS, default=[]): ActionSelector(),
                vol.Optional(CONF_DOUBLE_PRESS_ACTIONS, default=[]): ActionSelector(),
                vol.Optional(CONF_LONG_PRESS_ACTIONS, default=[]): ActionSelector(),
                vol.Optional(CONF_LONG_PRESS_RELEASED_ACTIONS, default=[]): ActionSelector(),
            }
        )

        return self.async_show_form(
            step_id="switch",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "switch_num": str(self._current_switch),
                "switch_count": str(self._switch_count),
            },
        )


class SwitchControlOptionsFlow(OptionsFlow):
    """Handle options for an existing Switch Control entry."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._current_switch_index: int = 0

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a selector for which switch input to reconfigure."""
        switches = self.config_entry.data.get(CONF_SWITCHES, [])

        if user_input is not None:
            self._current_switch_index = int(user_input["switch_index"])
            return await self.async_step_switch()

        options = [
            {"value": str(i), "label": f"Switch {i + 1}: {sw[CONF_NAME]}"}
            for i, sw in enumerate(switches)
        ]

        schema = vol.Schema(
            {
                vol.Required("switch_index"): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_switch(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow the user to edit the selected switch's settings."""
        errors: dict[str, str] = {}
        switches = list(self.config_entry.data.get(CONF_SWITCHES, []))
        current = switches[self._current_switch_index]

        if user_input is not None:
            sensor_entity_id = user_input[CONF_SENSOR_ENTITY_ID]
            ent_reg = er.async_get(self.hass)

            if not ent_reg.async_get(sensor_entity_id) and not self.hass.states.get(
                sensor_entity_id
            ):
                errors[CONF_SENSOR_ENTITY_ID] = "sensor_not_found"
            else:
                used_sensor_ids: set[str] = set()
                for entry in self.hass.config_entries.async_entries(DOMAIN):
                    for i, sw in enumerate(entry.data.get(CONF_SWITCHES, [])):
                        if (
                            entry.entry_id == self.config_entry.entry_id
                            and i == self._current_switch_index
                        ):
                            continue
                        used_sensor_ids.add(sw[CONF_SENSOR_ENTITY_ID])
                if sensor_entity_id in used_sensor_ids:
                    errors[CONF_SENSOR_ENTITY_ID] = "sensor_already_in_use"

            if not errors:
                switches[self._current_switch_index] = {
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_SENSOR_ENTITY_ID: sensor_entity_id,
                    CONF_OUTPUT_ENTITY_IDS: user_input.get(CONF_OUTPUT_ENTITY_IDS, []),
                    CONF_LONG_PRESS_ACTION: user_input.get(
                        CONF_LONG_PRESS_ACTION, LONG_PRESS_ACTION_NONE
                    ),
                    CONF_LONG_PRESS_OUTPUT_ENTITY_IDS: user_input.get(
                        CONF_LONG_PRESS_OUTPUT_ENTITY_IDS, []
                    ),
                    CONF_DIM_AUTO_THRESHOLD: user_input.get(
                        CONF_DIM_AUTO_THRESHOLD, DIM_AUTO_THRESHOLD
                    ),
                    CONF_DOUBLE_PRESS_ACTION: user_input.get(
                        CONF_DOUBLE_PRESS_ACTION, DOUBLE_PRESS_ACTION_NONE
                    ),
                    CONF_DOUBLE_PRESS_OUTPUT_ENTITY_IDS: user_input.get(
                        CONF_DOUBLE_PRESS_OUTPUT_ENTITY_IDS, []
                    ),
                    CONF_PRESS_ACTIONS: user_input.get(CONF_PRESS_ACTIONS, []),
                    CONF_RELEASED_ACTIONS: user_input.get(CONF_RELEASED_ACTIONS, []),
                    CONF_DOUBLE_PRESS_ACTIONS: user_input.get(CONF_DOUBLE_PRESS_ACTIONS, []),
                    CONF_LONG_PRESS_ACTIONS: user_input.get(CONF_LONG_PRESS_ACTIONS, []),
                    CONF_LONG_PRESS_RELEASED_ACTIONS: user_input.get(
                        CONF_LONG_PRESS_RELEASED_ACTIONS, []
                    ),
                }
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, CONF_SWITCHES: switches},
                )
                return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=current[CONF_NAME]): TextSelector(),
                vol.Required(
                    CONF_SENSOR_ENTITY_ID, default=current[CONF_SENSOR_ENTITY_ID]
                ): EntitySelector(
                    EntitySelectorConfig(domain=[BINARY_SENSOR_DOMAIN, SENSOR_DOMAIN])
                ),
                vol.Optional(
                    CONF_OUTPUT_ENTITY_IDS,
                    default=current.get(CONF_OUTPUT_ENTITY_IDS, []),
                ): EntitySelector(
                    EntitySelectorConfig(
                        domain=["switch", "light"],
                        multiple=True,
                    )
                ),
                vol.Optional(
                    CONF_LONG_PRESS_ACTION,
                    default=current.get(CONF_LONG_PRESS_ACTION, LONG_PRESS_ACTION_NONE),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=LONG_PRESS_ACTION_OPTIONS,
                        mode=SelectSelectorMode.LIST,
                        translation_key=CONF_LONG_PRESS_ACTION,
                    )
                ),
                vol.Optional(
                    CONF_LONG_PRESS_OUTPUT_ENTITY_IDS,
                    default=current.get(CONF_LONG_PRESS_OUTPUT_ENTITY_IDS, []),
                ): EntitySelector(
                    EntitySelectorConfig(
                        domain=["switch", "light"],
                        multiple=True,
                    )
                ),
                vol.Optional(
                    CONF_DIM_AUTO_THRESHOLD,
                    default=current.get(CONF_DIM_AUTO_THRESHOLD, DIM_AUTO_THRESHOLD),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=100,
                        step=1,
                        unit_of_measurement="%",
                        mode=NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Optional(
                    CONF_DOUBLE_PRESS_ACTION,
                    default=current.get(CONF_DOUBLE_PRESS_ACTION, DOUBLE_PRESS_ACTION_NONE),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=DOUBLE_PRESS_ACTION_OPTIONS,
                        mode=SelectSelectorMode.LIST,
                        translation_key=CONF_DOUBLE_PRESS_ACTION,
                    )
                ),
                vol.Optional(
                    CONF_DOUBLE_PRESS_OUTPUT_ENTITY_IDS,
                    default=current.get(CONF_DOUBLE_PRESS_OUTPUT_ENTITY_IDS, []),
                ): EntitySelector(
                    EntitySelectorConfig(
                        domain=["switch", "light"],
                        multiple=True,
                    )
                ),
                vol.Optional(
                    CONF_PRESS_ACTIONS,
                    default=current.get(CONF_PRESS_ACTIONS, []),
                ): ActionSelector(),
                vol.Optional(
                    CONF_RELEASED_ACTIONS,
                    default=current.get(CONF_RELEASED_ACTIONS, []),
                ): ActionSelector(),
                vol.Optional(
                    CONF_DOUBLE_PRESS_ACTIONS,
                    default=current.get(CONF_DOUBLE_PRESS_ACTIONS, []),
                ): ActionSelector(),
                vol.Optional(
                    CONF_LONG_PRESS_ACTIONS,
                    default=current.get(CONF_LONG_PRESS_ACTIONS, []),
                ): ActionSelector(),
                vol.Optional(
                    CONF_LONG_PRESS_RELEASED_ACTIONS,
                    default=current.get(CONF_LONG_PRESS_RELEASED_ACTIONS, []),
                ): ActionSelector(),
            }
        )

        return self.async_show_form(
            step_id="switch",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "switch_num": str(self._current_switch_index + 1),
                "switch_count": str(len(switches)),
            },
        )
