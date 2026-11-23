from __future__ import annotations
"""Platform for Crestron Media Player integration."""
"""Modernized for current Home Assistant"""



import asyncio
import logging
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerDeviceClass,
    MediaPlayerEntityFeature,
)
from homeassistant.const import STATE_ON, STATE_OFF, CONF_NAME

from .const import (
    HUB,
    DOMAIN,
    CONF_MUTE_JOIN,
    CONF_VOLUME_JOIN,
    CONF_VOLUME_UP_JOIN,
    CONF_VOLUME_DOWN_JOIN,
    CONF_OFF_JOIN,
    CONF_SOURCE_NUM_JOIN,
)

_LOGGER = logging.getLogger(__name__)


PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_MUTE_JOIN): cv.positive_int,
        vol.Required(CONF_SOURCE_NUM_JOIN): cv.positive_int,
        vol.Required(CONF_VOLUME_UP_JOIN): cv.positive_int,
        vol.Required(CONF_VOLUME_DOWN_JOIN): cv.positive_int,
        vol.Required(CONF_OFF_JOIN): cv.positive_int,
        vol.Required(CONF_VOLUME_JOIN): cv.positive_int,
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hub = hass.data[DOMAIN][HUB]
    async_add_entities([CrestronRoom(hub, config)])


class CrestronRoom(MediaPlayerEntity):
    def __init__(self, hub, config):
        self._hub = hub

        self._attr_name = config[CONF_NAME]
        self._attr_device_class = MediaPlayerDeviceClass.SPEAKER
        self._attr_should_poll = False

        self._attr_supported_features = (
            MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.VOLUME_STEP
        )

        self._mute_join = config[CONF_MUTE_JOIN]
        self._volume_up_join = config[CONF_VOLUME_UP_JOIN]
        self._volume_down_join = config[CONF_VOLUME_DOWN_JOIN]
        self._volume_level_join = config[CONF_VOLUME_JOIN]
        self._source_number_join = config[CONF_SOURCE_NUM_JOIN]
        self._off_join = config[CONF_OFF_JOIN]
        self._callback_joins = {
            f"a{self._volume_level_join}",
            f"d{self._mute_join}",
            f"d{self._off_join}",
            f"d{self._source_number_join}",
        }

    async def async_added_to_hass(self):
        self._hub.register_callback(self.process_callback)

    async def async_will_remove_from_hass(self):
        self._hub.remove_callback(self.process_callback)

    async def process_callback(self, cbtype, value):
        if cbtype in self._callback_joins or cbtype == "available":
            self.async_write_ha_state()

    @property
    def unique_id(self):
        return f"media-player-{self._source_number_join}"

    @property
    def available(self):
        return self._hub.is_available()

    @property
    def state(self):
        if self._hub.get_digital(self._off_join) == 0:
            return STATE_OFF
        return STATE_ON

    @property
    def is_volume_muted(self):
        return bool(self._hub.get_digital(self._mute_join))

    @property
    def volume_level(self):
        return self._hub.get_analog(self._volume_level_join) / 65535

    async def async_mute_volume(self, mute: bool):
        self._hub.set_digital(self._mute_join, 1)
        await asyncio.sleep(0.05)
        self._hub.set_digital(self._mute_join, 0)

    async def async_turn_on(self):
        self._hub.set_digital(self._source_number_join, 1)
        await asyncio.sleep(0.05)
        self._hub.set_digital(self._source_number_join, 0)

    async def async_turn_off(self):
        self._hub.set_digital(self._off_join, 1)
        await asyncio.sleep(0.05)
        self._hub.set_digital(self._off_join, 0)

    async def async_volume_up(self):
        self._hub.set_digital(self._volume_up_join, 1)
        await asyncio.sleep(0.05)
        self._hub.set_digital(self._volume_up_join, 0)

    async def async_volume_down(self):
        self._hub.set_digital(self._volume_down_join, 1)
        await asyncio.sleep(0.05)
        self._hub.set_digital(self._volume_down_join, 0)
