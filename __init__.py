from __future__ import annotations
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry

from .backup import B2BackupAgent

DOMAIN = "backup_b2"

# ───── helper: agent-provider requested by core backup subsystem ──────────
async def async_get_backup_agents(hass: HomeAssistant) -> list[B2BackupAgent]:
    """Return one agent per config-entry."""
    return [B2BackupAgent(hass, entry.data) for entry in hass.config_entries.async_entries(DOMAIN)]

# ───── classic HA init stubs (no YAML needed anymore) ─────────────────────
async def async_setup(hass: HomeAssistant, _):
    return True  # nothing to do

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    # nothing extra – agent list is generated on demand
    @callback
    def _reload_agents(_ev=None):
        # tell HA that agents changed
        hass.bus.async_fire("backup_b2_reload")

    entry.async_on_unload(
        entry.add_update_listener(lambda *_: _reload_agents())
    )
    _reload_agents()
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    return True
