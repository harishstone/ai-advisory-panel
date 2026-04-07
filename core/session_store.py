from typing import Optional
from core.config_model import ApplianceConfig


class SessionStore:
    """
    In-memory store for the current session's appliance configuration.
    One config per session. Resets on server restart.
    """
    _instance: Optional['SessionStore'] = None
    _config: Optional[ApplianceConfig] = None

    @classmethod
    def get(cls) -> 'SessionStore':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_config(self, config: ApplianceConfig) -> None:
        self._config = config

    def get_config(self) -> Optional[ApplianceConfig]:
        return self._config

    def clear(self) -> None:
        self._config = None

    def has_config(self) -> bool:
        return self._config is not None

    def update_section(self, section_name: str, section_data: dict) -> None:
        """Update a single section of the config without replacing everything."""
        if self._config is None:
            self._config = ApplianceConfig()
        current = self._config.model_dump()
        current[section_name] = section_data
        self._config = ApplianceConfig(**current)
