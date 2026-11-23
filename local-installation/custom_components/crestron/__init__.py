"""The Crestron Integration Component"""

from __future__ import annotations

import logging
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import TrackTemplate, async_track_template_result
from homeassistant.helpers.template import Template
from homeassistant.helpers.script import Script
from homeassistant.core import callback, Context
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
    EVENT_CALL_SERVICE,
    CONF_VALUE_TEMPLATE,
    CONF_ATTRIBUTE,
    CONF_ENTITY_ID,
    STATE_ON,
    STATE_OFF,
    CONF_SERVICE,
    CONF_SERVICE_DATA,
)

from .crestron import CrestronXsig
from .const import (
    CONF_PORT,
    HUB,
    DOMAIN,
    CONF_JOIN,
    CONF_SCRIPT,
    CONF_TO_HUB,
    CONF_FROM_HUB,
)

_LOGGER = logging.getLogger(__name__)

TO_JOINS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_JOIN): cv.string,
        vol.Optional(CONF_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_ATTRIBUTE): cv.string,
        vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
    }
)

FROM_JOINS_SCHEMA = vol.Schema(
    vol.All(
        {
            vol.Required(CONF_JOIN): cv.string,
            vol.Optional(CONF_SCRIPT): cv.SCRIPT_SCHEMA,
            # Optional service form (kept for backward compat if you use it)
            vol.Optional(CONF_SERVICE): cv.string,
            vol.Optional(CONF_SERVICE_DATA): dict,
        },
        lambda value: value
        if CONF_SCRIPT in value or CONF_SERVICE in value
        else vol.Invalid(f"Must contain either {CONF_SCRIPT} or {CONF_SERVICE}"),
    )
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_PORT): cv.port,
                vol.Optional(CONF_TO_HUB): vol.All(cv.ensure_list, [TO_JOINS_SCHEMA]),
                vol.Optional(CONF_FROM_HUB): vol.All(cv.ensure_list, [FROM_JOINS_SCHEMA]),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass, config):
    """Set up the Crestron component.

    IMPORTANT:
    Do NOT manually load platforms here.
    Home Assistant will load the YAML platforms (switch/cover/climate/etc.)
    and pass each platform its own config block correctly.
    """
    conf = config.get(DOMAIN)
    if not conf:
        return True

    hass.data.setdefault(DOMAIN, {})

    hub = CrestronHub(hass, conf)
    await hub.start()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, hub.stop)
    return True


class CrestronHub:
    """Wrapper for the CrestronXsig library."""

    def __init__(self, hass, config):
        self.hass = hass
        self.hub = hass.data[DOMAIN][HUB] = CrestronXsig()
        self.hub.unique_id_prefix = f"{DOMAIN}-{config[CONF_PORT]}"
        self.port = config.get(CONF_PORT)
        self.context = Context()

        self.to_hub: dict[str, Template] = {}
        self.template_to_join: dict[int, str] = {}
        self.button_joins: dict[str, str] = {}
        self.from_hub = config.get(CONF_FROM_HUB, [])
        self.tracker = None
        self.button_listener_remove = None

        self.hub.register_sync_all_joins_callback(self.sync_joins_to_hub)

        if CONF_TO_HUB in config:
            track_templates = []

            for entity in config[CONF_TO_HUB]:
                template = None

                if CONF_VALUE_TEMPLATE in entity:
                    template = entity[CONF_VALUE_TEMPLATE]

                elif CONF_ATTRIBUTE in entity and CONF_ENTITY_ID in entity:
                    template = Template(
                        "{{ state_attr('%s','%s') }}"
                        % (entity[CONF_ENTITY_ID], entity[CONF_ATTRIBUTE]),
                        hass,
                    )

                elif CONF_ENTITY_ID in entity:
                    entity_id = entity[CONF_ENTITY_ID]

                    if entity_id.startswith("input_button."):
                        self.button_joins[entity_id] = entity[CONF_JOIN]
                        continue

                    template = Template("{{ states('%s') }}" % entity_id, hass)

                if template is not None:
                    join = entity[CONF_JOIN]
                    self.to_hub[join] = template
                    self.template_to_join[id(template)] = join
                    track_templates.append(TrackTemplate(template, None))

            if track_templates:
                self.tracker = async_track_template_result(
                    self.hass,
                    track_templates,
                    self.template_change_callback,
                )

        if self.button_joins:
            self.button_listener_remove = self.hass.bus.async_listen(
                EVENT_CALL_SERVICE, self.handle_button_press
            )

        if self.from_hub:
            self.hub.register_callback(self.join_change_callback)

    async def start(self):
        await self.hub.listen(self.port)

    async def stop(self, event):
        """Clean shutdown."""
        try:
            self.hub.remove_callback(self.join_change_callback)
            if self.tracker is not None:
                tracker, self.tracker = self.tracker, None
                tracker.async_remove()
        finally:
            try:
                if self.button_listener_remove is not None:
                    remove, self.button_listener_remove = self.button_listener_remove, None
                    remove()
            finally:
                await self.hub.stop()

    @callback
    def handle_button_press(self, event):
        """Handle input_button presses and send pulse to Crestron."""
        if event.data.get("domain") != "input_button":
            return

        if event.data.get("service") != "press":
            return

        entity_id = event.data.get("service_data", {}).get("entity_id")
        if not entity_id:
            return

        # Handle list form
        if isinstance(entity_id, list):
            entity_ids = entity_id
        else:
            entity_ids = [entity_id]

        for eid in entity_ids:
            if eid not in self.button_joins:
                continue

            join = self.button_joins[eid]

            if join.startswith("d"):
                join_number = int(join[1:])

                # Send pulse
                self.hub.set_digital(join_number, True)

                # 200ms pulse
                self.hass.loop.call_later(
                    0.2,
                    lambda j=join_number: self.hub.set_digital(j, False),
                )

    async def join_change_callback(self, cbtype, value):
        """Call service/script for tracked join change (from_hub)."""
        for join in self.from_hub:
            if cbtype != join[CONF_JOIN]:
                continue

            # For digital joins, ignore on->off transitions (avoids double calls for momentary presses)
            if cbtype.startswith("d") and value == "0":
                continue

            if CONF_SERVICE in join and CONF_SERVICE_DATA in join:
                data = dict(join[CONF_SERVICE_DATA])
                domain, service = join[CONF_SERVICE].split(".")
                await self.hass.services.async_call(domain, service, data)

            elif CONF_SCRIPT in join:
                script = Script(self.hass, join[CONF_SCRIPT], "Crestron Join Change", DOMAIN)
                await script.async_run({"value": value}, self.context)

    @callback
    def template_change_callback(self, event, updates):
        """Set join from value_template (to_hub)."""
        for update in updates:
            result = update.result

            if result == "None":
                continue

            join = self.template_to_join.get(id(update.template))
            if join is None:
                continue

            self._set_join_value(join, result)

    async def sync_joins_to_hub(self):
        """Sync all tracked templates to control system."""
        _LOGGER.debug("Syncing joins to control system")

        for join, template in self.to_hub.items():
            result = template.async_render()

            if result == "None":
                continue

            self._set_join_value(join, result)

    def _set_join_value(self, join, result):
        """Dispatch a rendered template value to the correct Crestron join."""
        if join.startswith("d"):
            value = self._coerce_digital_value(result)
            if value is not None:
                self.hub.set_digital(int(join[1:]), value)

        elif join.startswith("a"):
            self.hub.set_analog(int(join[1:]), int(result))

        elif join.startswith("s"):
            self.hub.set_serial(int(join[1:]), str(result))

    @staticmethod
    def _coerce_digital_value(result):
        """Normalize Home Assistant state/template values to bool."""
        if isinstance(result, bool):
            return result

        if isinstance(result, str):
            result_lower = result.lower()
            if result_lower in (STATE_ON, "true", "1"):
                return True
            if result_lower in (STATE_OFF, "false", "0"):
                return False

        return None
