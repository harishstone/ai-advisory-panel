import os
import httpx
from dotenv import load_dotenv
from core.config_model import ApplianceConfig

load_dotenv()


class QuoteImporter:
    """
    Fetches a quote from the Product Configurator API and maps it to ApplianceConfig.

    _map_to_config() is a stub — it cannot be implemented until the API response
    JSON structure is confirmed with Athar. The fetch logic is complete.
    """

    API_URL = os.environ.get(
        "QUOTE_API_URL",
        "https://staging.stonefly.com/api/quote_config_json.php"
    )
    API_TOKEN = os.environ.get("QUOTE_API_TOKEN", "")

    async def fetch_and_map(self, quote_number: str) -> ApplianceConfig:
        """Fetch quote from the Product Configurator API and return an ApplianceConfig."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                self.API_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.API_TOKEN}"
                },
                json={"quote_number": quote_number}
            )
            response.raise_for_status()
            data = response.json()

        return self._map_to_config(data)

    def _map_to_config(self, api_data: dict) -> ApplianceConfig:
        """
        Map the Product Configurator API response to ApplianceConfig.

        !! BLOCKED — waiting on Athar to share the API response JSON structure !!

        Once the field names from quote_config_json.php are known, implement
        the mapping here. Pattern:

            return ApplianceConfig(
                profile=ApplianceProfile(
                    appliance_type=api_data.get("appliance_type"),
                    total_usable_capacity_tb=api_data.get("usable_capacity_tb"),
                    ...
                ),
                storage_media=StorageMediaConfig(
                    primary_disk_type=api_data.get("disk_type"),
                    primary_disk_count=api_data.get("disk_count"),
                    ...
                ),
                ...
            )
        """
        raise NotImplementedError(
            "Quote field mapping not yet implemented. "
            "Inspect the API response from Athar and complete _map_to_config()."
        )
