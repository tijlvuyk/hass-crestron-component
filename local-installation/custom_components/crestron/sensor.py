"""Platform for Crestron Sensor integration."""

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import CONF_DEVICE_CLASS, CONF_NAME, CONF_UNIT_OF_MEASUREMENT

from .const import HUB, DOMAIN, CONF_VALUE_JOIN, CONF_DIVISOR

_VALID_DEVICE_CLASSES = [device_class.value for device_class in SensorDeviceClass]

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_VALUE_JOIN): cv.positive_int,
        vol.Optional(CONF_DEVICE_CLASS): vol.In(_VALID_DEVICE_CLASSES),
        vol.Required(CONF_UNIT_OF_MEASUREMENT): cv.string,
        vol.Required(CONF_DIVISOR): int,
    },
    extra=vol.ALLOW_EXTRA,
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hub = hass.data[DOMAIN][HUB]
    async_add_entities([CrestronSensor(hub, config)])


class CrestronSensor(SensorEntity):
    def __init__(self, hub, config):
        self._hub = hub
        self._name = config[CONF_NAME]
        self._join = config[CONF_VALUE_JOIN]
        self._attr_device_class = config.get(CONF_DEVICE_CLASS)
        self._attr_native_unit_of_measurement = config[CONF_UNIT_OF_MEASUREMENT]
        self._divisor = config.get(CONF_DIVISOR, 1)
        self._callback_join = f"a{self._join}"

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
        return f"sensor-{self._join}"

    @property
    def should_poll(self):
        return False

    @property
    def native_value(self):
        return self._hub.get_analog(self._join) / self._divisor
