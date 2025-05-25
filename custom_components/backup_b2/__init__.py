# ─────────────────────────────────────────────────────────────
# custom_components/b2_backup/__init__.py
# ─────────────────────────────────────────────────────────────
"""Setup & Config-Entry-Lifecycle für b2_backup."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .backup import DOMAIN, notify_backup_listeners

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Backblaze B2 Backup component."""
    _LOGGER.info("Setting up %s integration", DOMAIN)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Backblaze B2 Backup from a config entry."""
    _LOGGER.info("Setting up B2 backup config entry for bucket: %s", entry.data.get("bucket"))
    
    # Register update listener to notify backup system when config changes
    entry.async_on_unload(
        entry.add_update_listener(
            lambda *_: notify_backup_listeners(hass)
        )
    )
    
    # Notify backup system that a new agent is available
    notify_backup_listeners(hass)
    
    _LOGGER.info("Successfully set up B2 backup config entry")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading B2 backup config entry for bucket: %s", entry.data.get("bucket"))
    
    # Notify backup system that agent is being removed
    notify_backup_listeners(hass)
    
    return True
