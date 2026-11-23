"""Platform for Crestron Light integration."""
import asyncio

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.light import LightEntity, LightEntityFeature, ColorMode, ATTR_TRANSITION, ATTR_BRIGHTNESS
from homeassistant.const import CONF_NAME, CONF_TYPE
from .const import HUB, DOMAIN, CONF_JOIN

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_TYPE): vol.In(["brightness", "onoff"]),
        vol.Required(CONF_JOIN): cv.positive_int,
    },
    extra=vol.ALLOW_EXTRA,
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hub = hass.data[DOMAIN][HUB]
    entity = [CrestronLight(hub, config)]
    async_add_entities(entity)


class CrestronLight(LightEntity):
    def __init__(self, hub, config):
        self._hub = hub
        self._name = config[CONF_NAME]
        self._join = config[CONF_JOIN]

        if config[CONF_TYPE] == "brightness":
            self._color_mode = ColorMode.BRIGHTNESS
            self._callback_join = f"a{self._join}"
        else:
            self._color_mode = ColorMode.ONOFF
            self._callback_join = f"d{self._join}"

        self._attr_is_on = None
        self._attr_brightness = None
        self._attr_should_poll = False

    async def async_added_to_hass(self):
        self._hub.register_callback(self.process_callback)

    async def async_will_remove_from_hass(self):
        self._hub.remove_callback(self.process_callback)

    async def process_callback(self, cbtype, value):
        if cbtype in (self._callback_join, "available"):
            self._attr_is_on = None
            self._attr_brightness = None
            self.async_write_ha_state()

    @property
    def available(self):
        return self._hub.is_available()

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        if self._color_mode == ColorMode.BRIGHTNESS:
            return f"light-{self._join}"
        return f"toggle-light-{self._join}"

    @property
    def color_mode(self):
        return self._color_mode

    @property
    def supported_color_modes(self):
        if self._color_mode == ColorMode.BRIGHTNESS:
            return {ColorMode.BRIGHTNESS}
        else:
            return {ColorMode.ONOFF}

    @property
    def supported_features(self):
        return LightEntityFeature(0)

    @property
    def brightness(self):
        if self._color_mode == ColorMode.BRIGHTNESS:
            if self._attr_brightness is not None:
                return self._attr_brightness

            analog_value = self._hub.get_analog(self._join)
            return min(255, int((analog_value / 65535) * 255))
        return None

    @property
    def is_on(self):
        if self._attr_is_on is not None:
            return self._attr_is_on

        if self._color_mode == ColorMode.BRIGHTNESS:
            return self._hub.get_analog(self._join) > 0
        elif self._color_mode == ColorMode.ONOFF:
            return self._hub.get_digital(self._join)

    async def async_turn_on(self, **kwargs):
        if self._color_mode == ColorMode.ONOFF:
            self._attr_is_on = True
            self.async_write_ha_state()

            self._hub.set_digital(self._join, True)
            await asyncio.sleep(0.05)
            self._hub.set_digital(self._join, False)

        elif self._color_mode == ColorMode.BRIGHTNESS:
            ha_brightness = kwargs.get(ATTR_BRIGHTNESS, 255)

            self._attr_brightness = ha_brightness
            self._attr_is_on = ha_brightness > 0
            self.async_write_ha_state()

            scaled_brightness = int((ha_brightness / 255) * 65535)
            transition_time = int(kwargs.get(ATTR_TRANSITION, 2))

            self.hass.async_create_task(
                self.__transition(scaled_brightness, transition_time)
            )

    async def async_turn_off(self, **kwargs):
        if self._color_mode == ColorMode.ONOFF:
            self._attr_is_on = False
            self.async_write_ha_state()

            self._hub.set_digital(self._join, True)
            await asyncio.sleep(0.05)
            self._hub.set_digital(self._join, False)

        elif self._color_mode == ColorMode.BRIGHTNESS:
            self._attr_brightness = 0
            self._attr_is_on = False
            self.async_write_ha_state()

            transition_time = int(kwargs.get(ATTR_TRANSITION, 2))

            self.hass.async_create_task(
                self.__transition(0, transition_time)
            )

    async def __transition(self, brightness, transition_time):
        if transition_time == 0:
            self._hub.set_analog(self._join, int(brightness))
        else:
            current_brightness = self._hub.get_analog(self._join)
            steps = max(1, transition_time * 20)
            incr_per_step = (brightness - current_brightness) / steps

            for _ in range(steps):
                current_brightness += incr_per_step
                current_brightness = max(0, min(65535, current_brightness))
                self._hub.set_analog(self._join, int(current_brightness))
                await asyncio.sleep(0.05)
