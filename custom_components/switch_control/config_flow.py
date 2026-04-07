"""Config flow for the Switch Control integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
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
    CONF_DOUBLE_PRESS_OUTPUT_ENTITY_IDS,
    CONF_LONG_PRESS_ACTION,
    CONF_LONG_PRESS_OUTPUT_ENTITY_IDS,
    CONF_NAME,
    CONF_OUTPUT_ENTITY_IDS,
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
            return await self.async_step_switch()

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
                    }
                )
                self._current_switch += 1

                if self._current_switch > self._switch_count:
                    return self.async_create_entry(
                        title=self._data[CONF_NAME],
                        data=self._data,
                    )

                return await self.async_step_switch()

        default_switch_name = f"Switch {self._current_switch}"
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=default_switch_name): TextSelector(),
                vol.Required(CONF_SENSOR_ENTITY_ID): EntitySelector(
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
