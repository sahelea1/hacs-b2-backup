# ─────────────────────────────────────────────────────────────
# custom_components/b2_backup/backup.py
# ─────────────────────────────────────────────────────────────
"""Backblaze B2 Backup Platform."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from io import BytesIO
from pathlib import Path
from typing import Any

from b2sdk.v2 import B2Api, InMemoryAccountInfo, exception as b2e

from homeassistant.components.backup import (
    AgentBackup,
    BackupAgent,
    BackupNotFound,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback

DOMAIN = "b2_backup"
DATA_BACKUP_AGENT_LISTENERS = f"{DOMAIN}_backup_agent_listeners"

# Config keys
CONF_KEY_ID = "application_key_id"
CONF_KEY = "application_key"
CONF_BUCKET = "bucket"
CONF_ENDPOINT = "endpoint"
CONF_PREFIX = "prefix"

_LOGGER = logging.getLogger(__name__)


class B2BackupAgent(BackupAgent):
    """Backblaze B2 backup agent."""

    domain = DOMAIN

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        """Initialize the B2 backup agent."""
        self.hass = hass
        self._bucket_name = config[CONF_BUCKET]
        self._prefix = config.get(CONF_PREFIX, "ha-backup")
        self.name = f"Backblaze B2 ({self._bucket_name})"
        self.unique_id = f"{DOMAIN}_{self._bucket_name}"

        # Initialize B2 API
        info = InMemoryAccountInfo()
        self._api = B2Api(info)
        self._bucket_obj = None
        self._authorized = False
        
        # Store config for authorization
        self._config = config

    async def _ensure_authorized(self) -> None:
        """Ensure the B2 API is authorized."""
        if not self._authorized:
            await self.hass.async_add_executor_job(
                self._api.authorize_account,
                self._config.get(CONF_ENDPOINT, "production"),
                self._config[CONF_KEY_ID],
                self._config[CONF_KEY],
            )
            self._authorized = True

    def _get_bucket(self):
        """Get the B2 bucket object."""
        if self._bucket_obj is None:
            self._bucket_obj = self._api.get_bucket_by_name(self._bucket_name)
        return self._bucket_obj

    async def async_upload_backup(
        self,
        *,
        open_stream: Callable[[], Coroutine[Any, Any, AsyncIterator[bytes]]],
        backup: AgentBackup,
        **kwargs,
    ) -> None:
        """Upload a backup to B2."""
        _LOGGER.info("Starting B2 backup upload for %s", backup.backup_id)
        await self._ensure_authorized()
        
        stream = await open_stream()
        buf = BytesIO()
        async for chunk in stream:
            buf.write(chunk)
        buf.seek(0)
        
        filename = f"{self._prefix}/{backup.backup_id}.tar"

        def _upload():
            return self._get_bucket().upload_bytes(buf.getvalue(), filename)

        await asyncio.get_running_loop().run_in_executor(None, _upload)
        _LOGGER.info("Successfully uploaded backup %s to B2", backup.backup_id)

    async def async_list_backups(self, **kwargs) -> list[AgentBackup]:
        """List all backups in B2."""
        await self._ensure_authorized()

        def _list_backups() -> list[AgentBackup]:
            backups: list[AgentBackup] = []
            try:
                for file_version in self._get_bucket().ls():
                    if file_version.file_name.startswith(self._prefix):
                        # Extract backup ID from filename
                        backup_id = Path(file_version.file_name).stem
                        backups.append(
                            AgentBackup(
                                backup_id=backup_id,
                                name=Path(file_version.file_name).name,
                                created=file_version.upload_timestamp,
                                size=file_version.size,
                            )
                        )
                _LOGGER.debug("Found %d backups in B2", len(backups))
            except Exception as err:
                _LOGGER.error("Error listing B2 backups: %s", err)
                raise
            return backups

        return await asyncio.get_running_loop().run_in_executor(None, _list_backups)

    async def async_download_backup(
        self, backup_id: str, **kwargs
    ) -> AsyncIterator[bytes]:
        """Download a backup from B2."""
        await self._ensure_authorized()

        def _download():
            try:
                # Find the file by backup_id
                for file_version in self._get_bucket().ls():
                    if file_version.file_name.startswith(self._prefix) and backup_id in file_version.file_name:
                        return self._get_bucket().download_file_by_id(file_version.id_).read()
                raise BackupNotFound(f"Backup {backup_id} not found")
            except b2e.B2Error as err:
                raise BackupNotFound from err

        data = await asyncio.get_running_loop().run_in_executor(None, _download)
        yield data

    async def async_delete_backup(self, backup_id: str, **kwargs) -> None:
        """Delete a backup from B2."""
        await self._ensure_authorized()

        def _delete():
            try:
                # Find and delete the file by backup_id
                for file_version in self._get_bucket().ls():
                    if file_version.file_name.startswith(self._prefix) and backup_id in file_version.file_name:
                        self._get_bucket().delete_file_version(file_version.id_, file_version.file_name)
                        return
                raise BackupNotFound(f"Backup {backup_id} not found")
            except b2e.B2Error as err:
                raise BackupNotFound from err

        await asyncio.get_running_loop().run_in_executor(None, _delete)


# ============================================================================
# Required functions for Home Assistant to discover backup agents
# ============================================================================

async def async_get_backup_agents(hass: HomeAssistant) -> list[BackupAgent]:
    """Return a list of backup agents.
    
    This function is called by Home Assistant to discover available backup agents.
    """
    _LOGGER.debug("async_get_backup_agents called for domain %s", DOMAIN)
    
    # Check if we have any loaded config entries for this domain
    loaded_entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not loaded_entries:
        _LOGGER.debug("No loaded config entries found for %s", DOMAIN)
        return []
    
    agents = []
    for entry in loaded_entries:
        if entry.state is ConfigEntryState.LOADED:
            try:
                agent = B2BackupAgent(hass, entry.data)
                agents.append(agent)
                _LOGGER.info(
                    "Created B2 backup agent '%s' for bucket: %s", 
                    agent.unique_id, 
                    entry.data[CONF_BUCKET]
                )
            except Exception as err:
                _LOGGER.error(
                    "Failed to create B2 backup agent for %s: %s", 
                    entry.data.get(CONF_BUCKET), 
                    err
                )
    
    _LOGGER.info("Returning %d B2 backup agents", len(agents))
    return agents


@callback
def async_register_backup_agents_listener(
    hass: HomeAssistant,
    *,
    listener: Callable[[], None],
    **kwargs: Any,
) -> Callable[[], None]:
    """Register a listener to be called when agents are added or removed.
    
    This function is called by Home Assistant's backup manager to register
    a callback that should be called whenever backup agents change.
    """
    _LOGGER.debug("Registering backup agents listener for %s", DOMAIN)
    
    # Initialize the listeners list if it doesn't exist
    hass.data.setdefault(DATA_BACKUP_AGENT_LISTENERS, [])
    hass.data[DATA_BACKUP_AGENT_LISTENERS].append(listener)

    @callback
    def remove_listener() -> None:
        """Remove the listener."""
        if DATA_BACKUP_AGENT_LISTENERS in hass.data:
            try:
                hass.data[DATA_BACKUP_AGENT_LISTENERS].remove(listener)
                _LOGGER.debug("Removed backup agents listener for %s", DOMAIN)
            except ValueError:
                _LOGGER.warning("Listener not found in list for %s", DOMAIN)

    return remove_listener


def notify_backup_listeners(hass: HomeAssistant) -> None:
    """Notify all registered backup listeners that agents may have changed."""
    listeners = hass.data.get(DATA_BACKUP_AGENT_LISTENERS, [])
    _LOGGER.debug("Notifying %d backup listeners for %s", len(listeners), DOMAIN)
    
    for listener in listeners:
        try:
            listener()
        except Exception as err:
            _LOGGER.error("Error calling backup agent listener: %s", err)
