# ─────────────────────────────────────────────────────────────
# custom_components/b2_backup/__init__.py
# ─────────────────────────────────────────────────────────────
"""Setup & Config-Entry-Lifecycle für b2_backup."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .backup import DOMAIN


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Backblaze B2 Backup component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Backblaze B2 Backup from a config entry."""
    # Forward the setup to the backup platform
    await hass.config_entries.async_forward_entry_setups(entry, ["backup"])
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, ["backup"])
