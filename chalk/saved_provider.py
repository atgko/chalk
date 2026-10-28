"""The AI provider saved once for every course on this computer.

A professor with several courses used to enter their API key once per
course, because each project kept it in its own `.env` (UAT of PR #18).
Now the provider, model, endpoint, and key are saved together in the
operating system's credential store: Windows Credential Manager, or the
Keychain on a Mac. It's encrypted under the user's login and never sits
in a plain file. A project's own `.env` still wins when it has a
complete configuration (chalk/config.py `effective_env`).

The store can be missing or refuse (e.g. Linux without a keyring
service). Reading then finds nothing, and saving raises ChalkError so
the caller can fall back to the project's `.env`.
"""

from __future__ import annotations

import json
import logging

import keyring
from keyring.errors import KeyringError

from chalk.errors import ChalkError

SERVICE = "Chalk"
ENTRY = "ai-provider"
KEYS = ("LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")

logger = logging.getLogger(__name__)


class CredentialStoreError(ChalkError):
    """The operating system's credential store couldn't save the provider."""


def read_saved_provider() -> dict[str, str]:
    """The saved provider settings, or {} if none are saved (or the store
    can't be read, which is logged)."""
    try:
        stored = keyring.get_password(SERVICE, ENTRY)
    except KeyringError:
        logger.warning("Couldn't read the saved AI provider from the credential store.", exc_info=True)
        return {}
    if not stored:
        return {}
    try:
        values = json.loads(stored)
    except ValueError:
        logger.warning("The saved AI provider in the credential store isn't valid JSON; ignoring it.")
        return {}
    if not isinstance(values, dict):
        return {}
    return {key: str(values.get(key, "")) for key in KEYS}


def save_provider(values: dict[str, str]) -> None:
    """Save the four provider settings for every course. Raises
    CredentialStoreError if the store refuses."""
    try:
        keyring.set_password(SERVICE, ENTRY, json.dumps({key: values.get(key, "") for key in KEYS}))
    except KeyringError as exc:
        logger.warning("Couldn't save the AI provider to the credential store.", exc_info=True)
        raise CredentialStoreError(
            "Chalk couldn't save your key in this computer's password store, so it saved it in this "
            "course's folder only."
        ) from exc
