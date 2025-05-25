# ─────────────────────────────────────────────────────────────
# custom_components/b2_backup/config_flow.py
# ─────────────────────────────────────────────────────────────
"""Config flow for Backblaze B2 Backup integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from b2sdk.v2 import B2Api, InMemoryAccountInfo

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .backup import (
    CONF_BUCKET,
    CONF_ENDPOINT,
    CONF_KEY,
    CONF_KEY_ID,
    CONF_PREFIX,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_DEFAULTS = {CONF_ENDPOINT: "production", CONF_PREFIX: "ha-backup"}


class B2BackupConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Backblaze B2 Backup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate the credentials
            try:
                await self.hass.async_add_executor_job(
                    self._validate_credentials, user_input
                )
                
                # Check if already configured for this bucket
                await self.async_set_unique_id(user_input[CONF_BUCKET])
                self._abort_if_unique_id_configured()

                _LOGGER.info("Creating B2 backup config entry for bucket: %s", user_input[CONF_BUCKET])
                return self.async_create_entry(
                    title=f"Backblaze B2 ({user_input[CONF_BUCKET]})",
                    data=user_input,
                )
                
            except ValueError as err:
                _LOGGER.error("B2 credentials validation failed: %s", err)
                errors["base"] = "invalid_auth"
            except Exception as err:
                _LOGGER.exception("Unexpected error validating B2 credentials: %s", err)
                errors["base"] = "unknown"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_KEY_ID): str,
                vol.Required(CONF_KEY): str,
                vol.Required(CONF_BUCKET): str,
                vol.Optional(
                    CONF_ENDPOINT, default=_DEFAULTS[CONF_ENDPOINT]
                ): str,
                vol.Optional(CONF_PREFIX, default=_DEFAULTS[CONF_PREFIX]): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    def _validate_credentials(self, data: dict[str, Any]) -> None:
        """Validate the user credentials and bucket access."""
        try:
            # Test B2 API authorization
            api = B2Api(InMemoryAccountInfo())
            api.authorize_account(
                data[CONF_ENDPOINT], data[CONF_KEY_ID], data[CONF_KEY]
            )
            
            # Test bucket access
            bucket = api.get_bucket_by_name(data[CONF_BUCKET])
            if bucket is None:
                raise ValueError(f"Bucket '{data[CONF_BUCKET]}' not found or not accessible")
                
            _LOGGER.info("Successfully validated B2 credentials and bucket access")
            
        except Exception as err:
            _LOGGER.error("B2 validation failed: %s", err)
            raise ValueError("Failed to connect to B2 or access bucket") from err
