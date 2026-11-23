"""Platform for Crestron binary sensor integration."""

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import CONF_DEVICE_CLASS, CONF_NAME

from .const import CONF_INVERTED, CONF_IS_ON_JOIN, DOMAIN, HUB

_VALID_DEVICE_CLASSES = [device_class.value for device_class in BinarySensorDeviceClass]

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_IS_ON_JOIN): cv.positive_int,
        vol.Optional(CONF_DEVICE_CLASS): vol.In(_VALID_DEVICE_CLASSES),
        vol.Optional(CONF_INVERTED, default=False): cv.boolean,
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hub = hass.data[DOMAIN][HUB]
    async_add_entities([CrestronBinarySensor(hub, config)])


class CrestronBinarySensor(BinarySensorEntity):
    def __init__(self, hub, config):
        self._hub = hub
        self._name = config[CONF_NAME]
        self._join = config[CONF_IS_ON_JOIN]
        self._inverted = config[CONF_INVERTED]
        self._attr_device_class = config.get(CONF_DEVICE_CLASS)
        self._callback_join = f"d{self._join}"

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
        return f"binary-sensor-{self._join}"

    @property
    def should_poll(self):
        return False

    @property
    def is_on(self):
        is_on = self._hub.get_digital(self._join)
        return not is_on if self._inverted else is_on
