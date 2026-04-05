"""Config flow for the Switch Control integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
)

from .const import (
    CONF_NAME,
    CONF_OUTPUT_ENTITY_IDS,
    CONF_SENSOR_ENTITY_ID,
    DEFAULT_NAME,
    DOMAIN,
)


class SwitchControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Switch Control."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input[CONF_NAME]
            sensor_entity_id = user_input[CONF_SENSOR_ENTITY_ID]
            output_entity_ids = user_input[CONF_OUTPUT_ENTITY_IDS]

            ent_reg = er.async_get(self.hass)

            # Validate sensor entity exists in registry or state machine
            if not ent_reg.async_get(sensor_entity_id) and not self.hass.states.get(
                sensor_entity_id
            ):
                errors[CONF_SENSOR_ENTITY_ID] = "sensor_not_found"

            # Validate at least one output entity
            if not output_entity_ids:
                errors[CONF_OUTPUT_ENTITY_IDS] = "no_outputs"

            if not errors:
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_NAME: name,
                        CONF_SENSOR_ENTITY_ID: sensor_entity_id,
                        CONF_OUTPUT_ENTITY_IDS: output_entity_ids,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): TextSelector(),
                vol.Required(CONF_SENSOR_ENTITY_ID): EntitySelector(
                    EntitySelectorConfig(domain=SENSOR_DOMAIN)
                ),
                vol.Required(CONF_OUTPUT_ENTITY_IDS): EntitySelector(
                    EntitySelectorConfig(
                        domain=["switch", "light"],
                        multiple=True,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
