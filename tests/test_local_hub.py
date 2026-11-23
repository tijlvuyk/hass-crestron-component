"""Shutdown regressions for the installed variant's extra button listener."""

from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock

from test_hub_lifecycle import load_component


class LocalHubTests(IsolatedAsyncioTestCase):
    def setUp(self):
        component = load_component(
            Path(__file__).resolve().parents[1] / "local-installation"
        )
        hass = SimpleNamespace(data={component.DOMAIN: {}})
        self.hub = component.CrestronHub(hass, {component.CONF_PORT: 12345})
        self.hub.hub.stop = AsyncMock()
        self.tracker = Mock()
        self.remove_button = Mock()
        self.hub.tracker = self.tracker
        self.hub.button_listener_remove = self.remove_button

    async def test_repeated_shutdown_removes_listeners_once(self):
        await self.hub.stop(None)
        await self.hub.stop(None)
        self.tracker.async_remove.assert_called_once_with()
        self.remove_button.assert_called_once_with()
        self.assertIsNone(self.hub.tracker)
        self.assertIsNone(self.hub.button_listener_remove)
        self.assertEqual(self.hub.hub.stop.await_count, 2)

    async def test_tracker_failure_still_removes_button_and_stops(self):
        self.tracker.async_remove.side_effect = RuntimeError("tracker failed")
        with self.assertRaisesRegex(RuntimeError, "tracker failed"):
            await self.hub.stop(None)
        self.remove_button.assert_called_once_with()
        self.hub.hub.stop.assert_awaited_once_with()

    async def test_button_cleanup_failure_still_stops_transport(self):
        self.remove_button.side_effect = RuntimeError("button listener failed")
        with self.assertRaisesRegex(RuntimeError, "button listener failed"):
            await self.hub.stop(None)
        self.hub.hub.stop.assert_awaited_once_with()
        self.assertIsNone(self.hub.button_listener_remove)

    async def test_shutdown_without_optional_listeners(self):
        self.hub.tracker = None
        self.hub.button_listener_remove = None
        await self.hub.stop(None)
        self.hub.hub.stop.assert_awaited_once_with()
