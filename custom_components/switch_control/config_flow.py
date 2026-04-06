"""Config flow for the Switch Control integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    CONF_NAME,
    CONF_OUTPUT_ENTITY_IDS,
    CONF_SENSOR_ENTITY_ID,
    CONF_SWITCH_COUNT,
    CONF_SWITCHES,
    DEFAULT_NAME,
    DOMAIN,
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

