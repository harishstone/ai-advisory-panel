"""
Quote Import Module

The Product Configurator API returns a flat list of product line-item descriptions:
    {
        "success": true,
        "data": {
            "configuration": [
                {"name": "Upgrade to 128GB High Speed ... Memory", "quantity": 1},
                {"name": "Dual 10Gb RJ-45 Ports ...", "quantity": 1},
                ...
            ]
        }
    }

All specs (CPU, RAM, NIC speed, drives, etc.) are embedded as human-readable text
inside the `name` strings. _map_to_config() parses these strings with regex to
extract structured data and populate ApplianceConfig.
"""

import os
import re
import httpx
from typing import Optional
from dotenv import load_dotenv

from core.config_model import (
    ApplianceConfig,
    ApplianceProfile,
    ApplianceType,
    WorkloadType,
    ComputeConfig,
    StorageMediaConfig,
    StorageConfig,
    NetworkConfig,
    VeeamConfig,
    EnvironmentConfig,
    DiskType,
    NicSpeed,
)

load_dotenv()


class QuoteImporter:
    """
    Fetches a quote from the Product Configurator API and maps it to ApplianceConfig.
    The API returns unstructured product description strings — we parse them with regex.
    """

    API_URL = "https://staging.stonefly.com/api/quote_config_json.php"

    async def fetch_and_map(self, quote_number: str) -> ApplianceConfig:
        """Fetch quote from the Product Configurator API and return an ApplianceConfig."""
        url = os.environ.get("QUOTE_API_URL", self.API_URL)
        token = os.environ.get("QUOTE_API_TOKEN", "")

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                url,
                headers=headers,
                json={"quote_number": quote_number}
            )
            response.raise_for_status()
            data = response.json()

        if not data.get("success"):
            raise ValueError(f"Quote API returned success=false: {data}")

        return self._map_to_config(data)

    # ─── Main Mapper ──────────────────────────────────────────────────────────

    def _map_to_config(self, api_data: dict) -> ApplianceConfig:
        """
        Parse the flat list of product description strings into ApplianceConfig.
        Fields that cannot be determined from the text are left as None.
        """
        items = [
            str(item.get("name", ""))
            for item in api_data.get("data", {}).get("configuration", [])
        ]
        # Full text blob for cross-field searches
        text = "\n".join(items)

        return ApplianceConfig(
            profile=self._parse_profile(items, text),
            compute=self._parse_compute(items, text),
            storage_media=self._parse_storage_media(items, text),
            storage_config=self._parse_storage_config(items, text),
            network=self._parse_network(items, text),
            veeam=self._parse_veeam(items, text),
            environment=self._parse_environment(items, text),
        )

    # ─── Profile ─────────────────────────────────────────────────────────────

    def _parse_profile(self, items: list, text: str) -> Optional[ApplianceProfile]:
        appliance_type = None
        if re.search(r'backup.{0,30}disaster recovery|dr365v', text, re.I):
            appliance_type = ApplianceType.BACKUP_DR
        elif re.search(r'hyperconverged', text, re.I):
            appliance_type = ApplianceType.HYPERCONVERGED
        elif re.search(r'baremetal|bare.metal', text, re.I):
            appliance_type = ApplianceType.BAREMETAL_STORAGE

        protocols = []
        if re.search(r'\biscsi\b', text, re.I):
            protocols.append("iscsi")
        if re.search(r'\bnfs\b', text, re.I):
            protocols.append("nas_nfs")
        if re.search(r'\bcifs\b|\bsmb\b', text, re.I):
            protocols.append("nas_cifs")
        if re.search(r'\bs3\b|object.storage', text, re.I):
            protocols.append("s3")

        workloads = []
        if re.search(r'veeam', text, re.I):
            workloads.append(WorkloadType.VEEAM_BACKUP)
        if re.search(r'proxmox|vmware|hyperconverged|hyper-v', text, re.I):
            workloads.append(WorkloadType.VM_GENERAL)

        # Usable capacity: "120TB usable" or "120 TB usable"
        capacity = None
        m = re.search(r'(\d+(?:\.\d+)?)\s*TB\s+usable', text, re.I)
        if m:
            capacity = float(m.group(1))

        if not any([appliance_type, protocols, workloads, capacity]):
            return None

        return ApplianceProfile(
            appliance_type=appliance_type,
            protocols=protocols or None,
            primary_workloads=workloads or None,
            total_usable_capacity_tb=capacity,
        )

    # ─── Compute ─────────────────────────────────────────────────────────────

    def _parse_compute(self, items: list, text: str) -> Optional[ComputeConfig]:
        cpu_model = None
        cores = None
        logical = None
        ram_gb = None

        # CPU: "20-Core 2.3GHz 3rd Gen Scalable Xeon Silver Processor"
        m = re.search(r'(\d+)-Core\s+([\d.]+)GHz[^,\n]*?(Xeon\s+\w+)', text, re.I)
        if m:
            cores = int(m.group(1))
            freq = m.group(2)
            brand = m.group(3)
            cpu_model = f"Intel {brand} {freq}GHz"
            logical = cores * 2  # Assume Hyper-Threading

        # RAM: "128GB High Speed ... Memory"
        m = re.search(r'(?:to\s+)?(\d+)GB[^,\n]*?(?:system\s+)?memory', text, re.I)
        if m:
            ram_gb = int(m.group(1))

        if not any([cpu_model, cores, ram_gb]):
            return None

        return ComputeConfig(
            cpu_model=cpu_model,
            total_physical_cores=cores,
            total_logical_processors=logical,
            total_ram_gb=ram_gb,
        )

    # ─── Storage Media ────────────────────────────────────────────────────────

    def _parse_storage_media(self, items: list, text: str) -> Optional[StorageMediaConfig]:
        disk_type = None
        disk_count = None
        fast_tier_type = None
        fast_tier_gb = None
        controller_model = None
        cache_protection = None

        # Fast tier NVMe: "960GB PCI-E Based NVMe SSD for Virtualization"
        m = re.search(r'(\d+)GB[^,\n]*NVMe\s+SSD', text, re.I)
        if m:
            fast_tier_type = "nvme_ssd"
            fast_tier_gb = float(m.group(1))

        # Primary disk type from chassis description or explicit drive entries
        if re.search(r'3\.5["\s]+SAS|SAS\s+HDD|SAS\s+drive', text, re.I):
            disk_type = DiskType.SAS_HDD
        elif re.search(r'SATA\s+SSD|2\.5["\s]+SSD', text, re.I):
            disk_type = DiskType.SSD_SATA_SAS
        elif re.search(r'NVMe.*primary|primary.*NVMe', text, re.I):
            disk_type = DiskType.NVME_SSD

        # Disk count: look for standalone numeric entries in items list
        # The API sometimes puts a bare number like "9" as a line-item name
        # which represents the number of drives ordered
        numeric_items = [int(i) for i in items if re.fullmatch(r'\d{1,3}', i.strip()) and int(i) > 1]
        if numeric_items:
            # Largest plausible value (1–60) is likely the drive count
            candidates = [n for n in numeric_items if 2 <= n <= 60]
            if candidates:
                disk_count = max(candidates)

        # RAID controller
        m = re.search(r'(\d+Gb\s+SAS[^,\n]*RAID[^,\n]*Controller)', text, re.I)
        if m:
            controller_model = m.group(1).strip()
            # Flash Backup = capacitor-backed cache
            if re.search(r'flash\s+backup', text, re.I):
                cache_protection = "capacitor"
            elif re.search(r'battery', text, re.I):
                cache_protection = "battery"

        if not any([disk_type, disk_count, fast_tier_type, controller_model]):
            return None

        return StorageMediaConfig(
            primary_disk_type=disk_type,
            primary_disk_count=disk_count,
            fast_tier_type=fast_tier_type,
            fast_tier_capacity_gb=fast_tier_gb,
            controller_model=controller_model,
            cache_protection=cache_protection,
        )

    # ─── Storage Config ───────────────────────────────────────────────────────

    def _parse_storage_config(self, items: list, text: str) -> Optional[StorageConfig]:
        # RAID level is not explicitly stated in the product description text.
        # Write-back is the correct policy when flash backup is present on controller.
        write_back = None
        if re.search(r'flash\s+backup', text, re.I):
            write_back = "write_back"

        thin = None
        if re.search(r'thin\s+provisioning', text, re.I):
            thin = True

        if not any([write_back, thin]):
            return None

        return StorageConfig(
            write_back_policy=write_back,
            thin_provisioning=thin,
        )

    # ─── Network ─────────────────────────────────────────────────────────────

    def _parse_network(self, items: list, text: str) -> Optional[NetworkConfig]:
        nic_speed = None
        ports = None

        # NIC speed: "Dual 10Gb RJ-45 Ports" or "Quad 25Gb SFP28"
        m = re.search(r'(Dual|Quad|Single|2x|4x)\s+(\d+)Gb', text, re.I)
        if m:
            count_word = m.group(1).lower()
            speed_gb = int(m.group(2))

            port_map = {"dual": 2, "2x": 2, "quad": 4, "4x": 4, "single": 1}
            ports = port_map.get(count_word, None)

            speed_map = {1: NicSpeed.GBE_1, 10: NicSpeed.GBE_10,
                         25: NicSpeed.GBE_25, 40: NicSpeed.GBE_40, 100: NicSpeed.GBE_100}
            nic_speed = speed_map.get(speed_gb)

        if not any([nic_speed, ports]):
            return None

        return NetworkConfig(
            nic_speed=nic_speed,
            active_data_ports=ports,
        )

    # ─── Veeam ────────────────────────────────────────────────────────────────

    def _parse_veeam(self, items: list, text: str) -> Optional[VeeamConfig]:
        if not re.search(r'veeam', text, re.I):
            return None

        # Veeam version
        version = None
        m = re.search(r'Veeam[^,\n]*?v?(\d+(?:\.\d+)?)', text, re.I)
        if m:
            version = m.group(1)

        # Proxy location — if Veeam is on the appliance itself
        proxy = "on_appliance" if re.search(r'veeam.*appliance|appliance.*veeam', text, re.I) else None

        return VeeamConfig(
            veeam_version=version,
            proxy_location=proxy,
        )

    # ─── Environment ─────────────────────────────────────────────────────────

    def _parse_environment(self, items: list, text: str) -> Optional[EnvironmentConfig]:
        power_redundancy = None
        use_scvm = None

        # Redundant PSU: "Redundant ... Power Supply"
        if re.search(r'redundant[^,\n]*power supply', text, re.I):
            power_redundancy = "dual_psu"

        # SCVM license present
        if re.search(r'\bscvm\b', text, re.I):
            use_scvm = True

        if not any([power_redundancy, use_scvm]):
            return None

        return EnvironmentConfig(
            power_redundancy=power_redundancy,
            use_stonefly_scvm=use_scvm,
        )
