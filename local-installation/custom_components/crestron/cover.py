"""Platform for Crestron Shades integration."""

from __future__ import annotations

import asyncio
import logging
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.cover import (
    CoverEntity,
    CoverDeviceClass,
    CoverEntityFeature,
)
from homeassistant.const import CONF_NAME, CONF_TYPE

from .const import (
    HUB,
    DOMAIN,
    CONF_IS_OPENING_JOIN,
    CONF_IS_OPENED_JOIN,
    CONF_IS_CLOSING_JOIN,
    CONF_IS_CLOSED_JOIN,
    CONF_STOP_JOIN,
    CONF_POS_JOIN,
    CONF_IS_MOVING_JOIN,
    CONF_OPEN_FULL_JOIN,
    CONF_CLOSE_FULL_JOIN,
    CONF_MAIN_ENGINE_JOIN,
    CONF_IR_SENSOR_JOIN,
    CONF_UP_SET_JOIN,
    CONF_UP_RESET_JOIN,
    CONF_DOWN_SET_JOIN,
    CONF_DOWN_RESET_JOIN,
)

_LOGGER = logging.getLogger(__name__)

_DIGITAL_COVER_REQUIRED_JOINS = (
    CONF_IS_MOVING_JOIN,
    CONF_OPEN_FULL_JOIN,
    CONF_CLOSE_FULL_JOIN,
)
_ELEVATOR_REQUIRED_JOINS = (
    CONF_IS_OPENED_JOIN,
    CONF_IS_CLOSED_JOIN,
    CONF_UP_SET_JOIN,
    CONF_UP_RESET_JOIN,
    CONF_DOWN_SET_JOIN,
    CONF_DOWN_RESET_JOIN,
    CONF_MAIN_ENGINE_JOIN,
)
_ANALOG_SHADE_REQUIRED_JOINS = (CONF_POS_JOIN,)

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_TYPE): vol.In(
            ["analog_shade", "digital_shade", "digital_curtain", "elevator"]
        ),
        vol.Required(CONF_IS_OPENING_JOIN): cv.positive_int,
        vol.Required(CONF_IS_CLOSING_JOIN): cv.positive_int,
        vol.Optional(CONF_STOP_JOIN): cv.positive_int,
        vol.Optional(CONF_IS_MOVING_JOIN): cv.positive_int,
        vol.Optional(CONF_IS_CLOSED_JOIN): cv.positive_int,
        vol.Optional(CONF_IS_OPENED_JOIN): cv.positive_int,
        vol.Optional(CONF_POS_JOIN): cv.positive_int,
        vol.Optional(CONF_OPEN_FULL_JOIN): cv.positive_int,
        vol.Optional(CONF_CLOSE_FULL_JOIN): cv.positive_int,
        vol.Optional(CONF_MAIN_ENGINE_JOIN): cv.positive_int,
        vol.Optional(CONF_IR_SENSOR_JOIN): cv.positive_int,
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hub = hass.data[DOMAIN][HUB]

    if CONF_TYPE not in config:
        _LOGGER.error("Crestron cover missing required 'type' in configuration")
        return

    cover_type = config[CONF_TYPE]
    if cover_type == "elevator":
        required_joins = _ELEVATOR_REQUIRED_JOINS
    elif cover_type == "analog_shade":
        required_joins = _ANALOG_SHADE_REQUIRED_JOINS
    else:
        required_joins = _DIGITAL_COVER_REQUIRED_JOINS

    missing = [join for join in required_joins if join not in config]
    if missing:
        _LOGGER.error(
            "Crestron cover '%s' missing required joins for type '%s': %s",
            config[CONF_NAME],
            cover_type,
            ", ".join(missing),
        )
        return

    if cover_type == "elevator":
        entity = CrestronElevator(hub, config)
    else:
        entity = CrestronShade(hub, config)

    async_add_entities([entity])
# ============================================================
# SHADE
# ============================================================

class CrestronShade(CoverEntity):
    def __init__(self, hub, config):
        self._hub = hub
        self._type = config[CONF_TYPE]
        self._attr_name = config[CONF_NAME]
        self._attr_should_poll = False

        self._is_opening_join = config[CONF_IS_OPENING_JOIN]
        self._is_closing_join = config[CONF_IS_CLOSING_JOIN]
        self._stop_join = config.get(CONF_STOP_JOIN)
        self._callback_joins = {
            f"d{self._is_opening_join}",
            f"d{self._is_closing_join}",
        }
        if self._stop_join is not None:
            self._callback_joins.add(f"d{self._stop_join}")

        self._manual_stop = False

        # -------- ANALOG SHADE --------
        if self._type == "analog_shade":
            self._digital = False
            self._attr_device_class = CoverDeviceClass.SHADE
            self._pos_join = config[CONF_POS_JOIN]
            self._is_closed_join = config.get(CONF_IS_CLOSED_JOIN)
            self._callback_joins.add(f"a{self._pos_join}")
            if self._is_closed_join is not None:
                self._callback_joins.add(f"d{self._is_closed_join}")

            self._attr_supported_features = (
                CoverEntityFeature.OPEN
                | CoverEntityFeature.CLOSE
                | CoverEntityFeature.STOP
                | CoverEntityFeature.SET_POSITION
            )

        # -------- DIGITAL SHADE / CURTAIN --------
        else:
            self._digital = True

            if self._type == "digital_curtain":
                self._attr_device_class = CoverDeviceClass.CURTAIN
            else:
                self._attr_device_class = CoverDeviceClass.SHADE

            self._is_moving_join = config[CONF_IS_MOVING_JOIN]
            self._open_full_join = config[CONF_OPEN_FULL_JOIN]
            self._close_full_join = config[CONF_CLOSE_FULL_JOIN]
            self._callback_joins.add(f"d{self._is_moving_join}")

            self._attr_supported_features = (
                CoverEntityFeature.OPEN
                | CoverEntityFeature.CLOSE
                | CoverEntityFeature.STOP
            )

    async def async_added_to_hass(self):
        self._hub.register_callback(self.process_callback)

    async def async_will_remove_from_hass(self):
        self._hub.remove_callback(self.process_callback)

    async def process_callback(self, cbtype, value):
        if cbtype in self._callback_joins or cbtype == "available":
            self.async_write_ha_state()

    @property
    def unique_id(self):
        return f"cover-{self._is_opening_join}-{self._is_closing_join}"

    @property
    def available(self):
        return self._hub.is_available()

    @property
    def current_cover_position(self):
        if not self._digital and self._pos_join:
            return self._hub.get_analog(self._pos_join) / 655.35
        return None

    @property
    def is_opening(self):
        if self._digital:
            return (
                self._hub.get_digital(self._is_opening_join)
                and self._hub.get_digital(self._is_moving_join)
            )
        return self._hub.get_digital(self._is_opening_join)

    @property
    def is_closing(self):
        if self._digital:
            return (
                self._hub.get_digital(self._is_closing_join)
                and self._hub.get_digital(self._is_moving_join)
            )
        return self._hub.get_digital(self._is_closing_join)

    @property
    def is_closed(self):
        if self._digital:
            if self._manual_stop:
                return None
            return (
                self._hub.get_digital(self._is_closing_join)
                and not self._hub.get_digital(self._is_moving_join)
            )
        if self._is_closed_join:
            return self._hub.get_digital(self._is_closed_join)
        return None

    async def async_set_cover_position(self, **kwargs):
        if not self._digital and self._pos_join:
            self._hub.set_analog(self._pos_join, int(kwargs["position"]) * 655)
            self._manual_stop = False

    async def async_open_cover(self, **kwargs):
        self._manual_stop = False

        if self._digital:
            self._hub.set_digital(self._open_full_join, 1)
            await asyncio.sleep(0.2)
            self._hub.set_digital(self._open_full_join, 0)
        else:
            self._hub.set_analog(self._pos_join, 0xFFFF)

    async def async_close_cover(self, **kwargs):
        self._manual_stop = False

        if self._digital:
            self._hub.set_digital(self._close_full_join, 1)
            await asyncio.sleep(0.2)
            self._hub.set_digital(self._close_full_join, 0)
        else:
            self._hub.set_analog(self._pos_join, 0)

    async def async_stop_cover(self, **kwargs):
        self._manual_stop = True
        if self._stop_join:
            self._hub.set_digital(self._stop_join, 1)
            await asyncio.sleep(0.2)
            self._hub.set_digital(self._stop_join, 0)


# ============================================================
# ELEVATOR
# ============================================================

class CrestronElevator(CoverEntity):
    def __init__(self, hub, config):
        self._hub = hub

        self._attr_name = config[CONF_NAME]
        self._attr_should_poll = False
        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
        )

        self._is_opening_join = config[CONF_IS_OPENING_JOIN]
        self._is_opened_join = config[CONF_IS_OPENED_JOIN]
        self._is_closing_join = config[CONF_IS_CLOSING_JOIN]
        self._is_closed_join = config[CONF_IS_CLOSED_JOIN]

        self._up_set_join = config[CONF_UP_SET_JOIN]
        self._up_reset_join = config[CONF_UP_RESET_JOIN]
        self._down_set_join = config[CONF_DOWN_SET_JOIN]
        self._down_reset_join = config[CONF_DOWN_RESET_JOIN]

        self._main_engine_join = config[CONF_MAIN_ENGINE_JOIN]
        self._ir_sensor_join = config.get(CONF_IR_SENSOR_JOIN)
        self._callback_joins = {
            f"d{self._is_opening_join}",
            f"d{self._is_opened_join}",
            f"d{self._is_closing_join}",
            f"d{self._is_closed_join}",
            f"d{self._main_engine_join}",
        }
        if self._ir_sensor_join is not None:
            self._callback_joins.add(f"d{self._ir_sensor_join}")

    async def async_added_to_hass(self):
        self._hub.register_callback(self.process_callback)

    async def async_will_remove_from_hass(self):
        self._hub.remove_callback(self.process_callback)

    async def process_callback(self, cbtype, value):
        if cbtype in self._callback_joins or cbtype == "available":
            self.async_write_ha_state()

    @property
    def unique_id(self):
        return f"elevator-{self._is_opening_join}-{self._is_closing_join}"

    @property
    def available(self):
        return self._hub.is_available()

    @property
    def is_opening(self):
        return (
            self._hub.get_digital(self._is_opening_join)
            and self._hub.get_digital(self._main_engine_join)
        )

    @property
    def is_closing(self):
        return (
            self._hub.get_digital(self._is_closing_join)
            and self._hub.get_digital(self._main_engine_join)
        )

    @property
    def is_closed(self):
        if self._hub.get_digital(self._is_closed_join):
            return True
        if self._hub.get_digital(self._is_opened_join):
            return False
        return None

    async def async_open_cover(self, **kwargs):
        self._hub.set_digital(self._down_reset_join, 1)
        self._hub.set_digital(self._up_set_join, 1)
        await asyncio.sleep(0.2)
        self._hub.set_digital(self._down_reset_join, 0)
        self._hub.set_digital(self._up_set_join, 0)

    async def async_close_cover(self, **kwargs):
        self._hub.set_digital(self._up_reset_join, 1)
        self._hub.set_digital(self._down_set_join, 1)
        await asyncio.sleep(0.2)
        self._hub.set_digital(self._up_reset_join, 0)
        self._hub.set_digital(self._down_set_join, 0)

    async def async_stop_cover(self, **kwargs):
        self._hub.set_digital(self._up_reset_join, 1)
        self._hub.set_digital(self._down_reset_join, 1)
        await asyncio.sleep(0.2)
        self._hub.set_digital(self._up_reset_join, 0)
        self._hub.set_digital(self._down_reset_join, 0)
