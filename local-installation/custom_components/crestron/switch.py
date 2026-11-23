"""Platform for Crestron Switch integration."""

import voluptuous as vol
import asyncio

import homeassistant.helpers.config_validation as cv
from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.const import CONF_DEVICE_CLASS, CONF_NAME
from .const import HUB, DOMAIN, CONF_SWITCH_JOIN, CONF_PULSED

_VALID_DEVICE_CLASSES = [device_class.value for device_class in SwitchDeviceClass]

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_PULSED): cv.boolean,
        vol.Optional(CONF_DEVICE_CLASS): vol.In(_VALID_DEVICE_CLASSES),
        vol.Required(CONF_SWITCH_JOIN): cv.positive_int,
    },
    extra=vol.ALLOW_EXTRA,
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hub = hass.data[DOMAIN][HUB]
    async_add_entities([CrestronSwitch(hub, config)])


class CrestronSwitch(SwitchEntity):
    def __init__(self, hub, config):
        self._hub = hub
        self._name = config[CONF_NAME]
        self._switch_join = config[CONF_SWITCH_JOIN]
        self._attr_device_class = config.get(CONF_DEVICE_CLASS)
        self._pulsed = config[CONF_PULSED]
        self._callback_join = f"d{self._switch_join}"

    async def async_added_to_hass(self):
        self._hub.register_callback(self.process_callback)

    async def async_will_remove_from_hass(self):
        self._hub.remove_callback(self.process_callback)

    async def process_callback(self, cbtype, value):
        if cbtype in (self._callback_join, "available"):
            self.async_write_ha_state()

    @property
    def available(self):
        return self._hub.is_available()

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return f"switch-{self._switch_join}"

    @property
    def should_poll(self):
        return False

    @property
    def is_on(self):
        return self._hub.get_digital(self._switch_join)

    async def async_turn_on(self, **kwargs):
        if self._pulsed:
            # Pulsed switches can only be switched by signal pulses
            # Therefore, must check if switch is not already on
            if not self.is_on:
                self._hub.set_digital(self._switch_join, True)
                await asyncio.sleep(0.5)
                self._hub.set_digital(self._switch_join, False)
        else:
            self._hub.set_digital(self._switch_join, True)

    async def async_turn_off(self, **kwargs):
        if self._pulsed:
            # Pulsed switches can only be switched by signal pulses
            # Therefore, must check if switch is not already off
            if self.is_on:
                self._hub.set_digital(self._switch_join, True)
                await asyncio.sleep(0.5)
                self._hub.set_digital(self._switch_join, False)
        else:
            self._hub.set_digital(self._switch_join, False)
