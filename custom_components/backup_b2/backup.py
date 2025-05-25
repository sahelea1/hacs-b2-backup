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
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

DOMAIN = "b2_backup"

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

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the B2 backup agent."""
        self.hass = hass
        self._entry = entry
        self._bucket_name = entry.data[CONF_BUCKET]
        self._prefix = entry.data.get(CONF_PREFIX, "ha-backup")
        self.name = f"Backblaze B2 ({self._bucket_name})"
        self.unique_id = f"{DOMAIN}_{entry.entry_id}"

        # Initialize B2 API
        info = InMemoryAccountInfo()
        self._api = B2Api(info)
        self._bucket_obj = None
        self._authorized = False

    async def _ensure_authorized(self) -> None:
        """Ensure the B2 API is authorized."""
        if not self._authorized:
            await self.hass.async_add_executor_job(
                self._api.authorize_account,
                self._entry.data.get(CONF_ENDPOINT, "production"),
                self._entry.data[CONF_KEY_ID],
                self._entry.data[CONF_KEY],
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up B2 backup platform."""
    # Create the backup agent
    agent = B2BackupAgent(hass, entry)
    
    # Register the backup agent with the backup component
    backup_component = hass.data.get("backup")
    if backup_component is not None:
        await backup_component.async_add_backup_agent(agent)
    else:
        _LOGGER.error("Backup component not found")
