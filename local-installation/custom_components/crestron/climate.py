"""Platform for Crestron Thermostat integration."""

from __future__ import annotations

import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature
from homeassistant.components.climate.const import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    FAN_AUTO,
    FAN_ON,
    HVACAction,
    HVACMode,
)

from homeassistant.const import CONF_NAME

from .const import (
    HUB,
    DOMAIN,
    CONF_HEAT_SP_JOIN,
    CONF_COOL_SP_JOIN,
    CONF_REG_TEMP_JOIN,
    CONF_MODE_HEAT_JOIN,
    CONF_MODE_COOL_JOIN,
    CONF_MODE_AUTO_JOIN,
    CONF_MODE_OFF_JOIN,
    CONF_FAN_ON_JOIN,
    CONF_FAN_AUTO_JOIN,
    CONF_H1_JOIN,
    CONF_H2_JOIN,
    CONF_C1_JOIN,
    CONF_C2_JOIN,
    CONF_FA_JOIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_HEAT_SP_JOIN): cv.positive_int,
        vol.Required(CONF_COOL_SP_JOIN): cv.positive_int,
        vol.Required(CONF_REG_TEMP_JOIN): cv.positive_int,
        vol.Required(CONF_MODE_HEAT_JOIN): cv.positive_int,
        vol.Required(CONF_MODE_COOL_JOIN): cv.positive_int,
        vol.Required(CONF_MODE_AUTO_JOIN): cv.positive_int,
        vol.Required(CONF_MODE_OFF_JOIN): cv.positive_int,
        vol.Required(CONF_FAN_ON_JOIN): cv.positive_int,
        vol.Required(CONF_FAN_AUTO_JOIN): cv.positive_int,
        vol.Required(CONF_H1_JOIN): cv.positive_int,
        vol.Optional(CONF_H2_JOIN): cv.positive_int,
        vol.Required(CONF_C1_JOIN): cv.positive_int,
        vol.Optional(CONF_C2_JOIN): cv.positive_int,
        vol.Required(CONF_FA_JOIN): cv.positive_int,
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    if not config or CONF_NAME not in config:
        _LOGGER.error("Crestron climate platform received invalid config: %s", config)
        return
    hub = hass.data[DOMAIN][HUB]
    unit = hass.config.units.temperature_unit
    async_add_entities([CrestronThermostat(hub, config, unit)])

class CrestronThermostat(ClimateEntity):
    def __init__(self, hub, config, unit):
        self._hub = hub

        # Modern HA attributes (preferred)
        self._attr_name = config[CONF_NAME]
        self._attr_should_poll = False
        self._attr_temperature_unit = unit

        self._attr_hvac_modes = [
            HVACMode.HEAT_COOL,
            HVACMode.HEAT,
            HVACMode.COOL,
            HVACMode.OFF,
        ]
        self._attr_fan_modes = [FAN_ON, FAN_AUTO]
        self._attr_supported_features = (
            ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        )

        # Joins
        self._heat_sp_join = config[CONF_HEAT_SP_JOIN]
        self._cool_sp_join = config[CONF_COOL_SP_JOIN]
        self._reg_temp_join = config[CONF_REG_TEMP_JOIN]

        self._mode_heat_join = config[CONF_MODE_HEAT_JOIN]
        self._mode_cool_join = config[CONF_MODE_COOL_JOIN]
        self._mode_auto_join = config[CONF_MODE_AUTO_JOIN]
        self._mode_off_join = config[CONF_MODE_OFF_JOIN]

        self._fan_on_join = config[CONF_FAN_ON_JOIN]
        self._fan_auto_join = config[CONF_FAN_AUTO_JOIN]

        self._h1_join = config[CONF_H1_JOIN]
        self._h2_join = config.get(CONF_H2_JOIN)

        self._c1_join = config[CONF_C1_JOIN]
        self._c2_join = config.get(CONF_C2_JOIN)

        self._fa_join = config[CONF_FA_JOIN]
        self._callback_joins = {
            f"a{self._heat_sp_join}",
            f"a{self._cool_sp_join}",
            f"a{self._reg_temp_join}",
            f"d{self._mode_heat_join}",
            f"d{self._mode_cool_join}",
            f"d{self._mode_auto_join}",
            f"d{self._mode_off_join}",
            f"d{self._fan_on_join}",
            f"d{self._fan_auto_join}",
            f"d{self._h1_join}",
            f"d{self._c1_join}",
            f"d{self._fa_join}",
        }
        if self._h2_join is not None:
            self._callback_joins.add(f"d{self._h2_join}")
        if self._c2_join is not None:
            self._callback_joins.add(f"d{self._c2_join}")

    async def async_added_to_hass(self):
        self._hub.register_callback(self.process_callback)

    async def async_will_remove_from_hass(self):
        self._hub.remove_callback(self.process_callback)

    async def process_callback(self, cbtype, value):
        if cbtype in self._callback_joins or cbtype == "available":
            self.async_write_ha_state()

    @property
    def available(self):
        return self._hub.is_available()

    @property
    def unique_id(self):
        return f"climate-{self._reg_temp_join}"

    @property
    def current_temperature(self):
        return self._hub.get_analog(self._reg_temp_join) / 10

    @property
    def target_temperature_high(self):
        return self._hub.get_analog(self._cool_sp_join) / 10

    @property
    def target_temperature_low(self):
        return self._hub.get_analog(self._heat_sp_join) / 10

    @property
    def hvac_mode(self):
        if self._hub.get_digital(self._mode_auto_join):
            return HVACMode.HEAT_COOL
        if self._hub.get_digital(self._mode_heat_join):
            return HVACMode.HEAT
        if self._hub.get_digital(self._mode_cool_join):
            return HVACMode.COOL
        if self._hub.get_digital(self._mode_off_join):
            return HVACMode.OFF
        return HVACMode.OFF

    @property
    def fan_mode(self):
        if self._hub.get_digital(self._fan_auto_join):
            return FAN_AUTO
        if self._hub.get_digital(self._fan_on_join):
            return FAN_ON
        return FAN_AUTO

    @property
    def hvac_action(self):
        # If explicitly OFF, report OFF.
        if self._hub.get_digital(self._mode_off_join):
            return HVACAction.OFF

        # Optional joins may be None; guard them.
        h2 = bool(self._h2_join and self._hub.get_digital(self._h2_join))
        c2 = bool(self._c2_join and self._hub.get_digital(self._c2_join))

        if self._hub.get_digital(self._h1_join) or h2:
            return HVACAction.HEATING
        if self._hub.get_digital(self._c1_join) or c2:
            return HVACAction.COOLING

        return HVACAction.IDLE

    async def async_set_hvac_mode(self, hvac_mode: HVACMode):
        if hvac_mode == HVACMode.HEAT_COOL:
            self._hub.set_digital(self._mode_cool_join, False)
            self._hub.set_digital(self._mode_off_join, False)
            self._hub.set_digital(self._mode_heat_join, False)
            self._hub.set_digital(self._mode_auto_join, True)

        elif hvac_mode == HVACMode.HEAT:
            self._hub.set_digital(self._mode_auto_join, False)
            self._hub.set_digital(self._mode_cool_join, False)
            self._hub.set_digital(self._mode_off_join, False)
            self._hub.set_digital(self._mode_heat_join, True)

        elif hvac_mode == HVACMode.COOL:
            self._hub.set_digital(self._mode_auto_join, False)
            self._hub.set_digital(self._mode_off_join, False)
            self._hub.set_digital(self._mode_heat_join, False)
            self._hub.set_digital(self._mode_cool_join, True)

        elif hvac_mode == HVACMode.OFF:
            self._hub.set_digital(self._mode_auto_join, False)
            self._hub.set_digital(self._mode_cool_join, False)
            self._hub.set_digital(self._mode_heat_join, False)
            self._hub.set_digital(self._mode_off_join, True)

        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str):
        if fan_mode == FAN_AUTO:
            self._hub.set_digital(self._fan_on_join, False)
            self._hub.set_digital(self._fan_auto_join, True)

        elif fan_mode == FAN_ON:
            self._hub.set_digital(self._fan_auto_join, False)
            self._hub.set_digital(self._fan_on_join, True)

        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        """
        HA will pass ATTR_TARGET_TEMP_LOW/HIGH for range-capable devices.
        Be tolerant if older keys are present.
        """
        low = kwargs.get(ATTR_TARGET_TEMP_LOW, kwargs.get("target_temp_low"))
        high = kwargs.get(ATTR_TARGET_TEMP_HIGH, kwargs.get("target_temp_high"))

        if low is not None:
            self._hub.set_analog(self._heat_sp_join, int(float(low)) * 10)

        if high is not None:
            self._hub.set_analog(self._cool_sp_join, int(float(high)) * 10)

        self.async_write_ha_state()
