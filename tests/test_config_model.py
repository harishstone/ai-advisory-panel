"""
Tests for core/config_model.py

Verifies Pydantic model validation, partial configs, serialization,
and enum handling.
"""

import pytest
from pydantic import ValidationError

from core.config_model import (
    ApplianceConfig,
    ApplianceProfile,
    ComputeConfig,
    StorageMediaConfig,
    StorageConfig,
    NetworkConfig,
    VeeamConfig,
    EnvironmentConfig,
    ApplianceType,
    DiskType,
    RaidLevel,
    NicSpeed,
)


# ─── Partial Config ────────────────────────────────────────────────────────────

def test_empty_config_is_valid():
    """ApplianceConfig with no sections at all must be valid — all optional."""
    config = ApplianceConfig()
    assert config.profile is None
    assert config.compute is None
    assert config.storage_media is None


def test_partial_config_loads():
    """Config with only storage_media populated must load without error."""
    config = ApplianceConfig(
        storage_media=StorageMediaConfig(
            primary_disk_type=DiskType.SAS_HDD,
            primary_disk_count=12,
            primary_disk_capacity_tb=4.0
        )
    )
    assert config.storage_media.primary_disk_count == 12
    assert config.compute is None
    assert config.veeam is None


def test_full_config_from_sample():
    """Full config dict (mirrors full_config.json) must deserialise without error."""
    raw = {
        "profile": {
            "appliance_type": "hyperconverged_compute",
            "protocols": ["iscsi", "nas_nfs", "s3"],
            "total_usable_capacity_tb": 200,
            "concurrent_workloads": 50,
            "annual_growth_rate_pct": 20
        },
        "compute": {
            "cpu_model": "Intel Xeon Silver 4314",
            "total_physical_cores": 32,
            "total_logical_processors": 64,
            "cpu_reservation_pct": 15,
            "total_ram_gb": 256
        },
        "storage_media": {
            "primary_disk_type": "sas_hdd",
            "primary_disk_count": 24,
            "primary_disk_capacity_tb": 8.0,
            "primary_disk_rpm": 7200
        },
        "storage_config": {
            "raid_level": "raid60",
            "stripe_size_kb": 64,
            "deduplication_enabled": True,
            "dedup_ratio": 2.5
        },
        "network": {
            "nic_speed": "25gbe",
            "active_data_ports": 4,
            "bonding_mode": "lacp_802_3ad",
            "jumbo_frames_mtu9000": True,
            "dedicated_storage_network": True
        },
        "veeam": {
            "concurrent_backup_jobs": 5,
            "backup_encryption": False,
            "daily_change_rate_pct": 8
        },
        "environment": {
            "power_redundancy": "dual_psu_ups",
            "uptime_requirement_pct": 99.9
        }
    }
    config = ApplianceConfig(**raw)
    assert config.profile.appliance_type == ApplianceType.HYPERCONVERGED
    assert config.storage_media.primary_disk_count == 24
    assert config.storage_config.raid_level == RaidLevel.RAID60
    assert config.network.nic_speed == NicSpeed.GBE_25
    assert config.veeam.concurrent_backup_jobs == 5


# ─── Enum Validation ───────────────────────────────────────────────────────────

def test_invalid_disk_type_raises():
    with pytest.raises(ValidationError):
        StorageMediaConfig(primary_disk_type="quantum_tape")


def test_invalid_raid_level_raises():
    with pytest.raises(ValidationError):
        StorageConfig(raid_level="raid999")


def test_invalid_nic_speed_raises():
    with pytest.raises(ValidationError):
        NetworkConfig(nic_speed="1tbe")


# ─── Serialization ─────────────────────────────────────────────────────────────

def test_model_dump_excludes_none():
    """model_dump(exclude_none=True) should not include unset optional fields."""
    config = ApplianceConfig(
        compute=ComputeConfig(total_ram_gb=128)
    )
    dumped = config.model_dump(exclude_none=True)
    assert "compute" in dumped
    assert dumped["compute"]["total_ram_gb"] == 128
    assert "profile" not in dumped
    assert "storage_media" not in dumped
    # No None values anywhere in the output
    def has_none(obj):
        if isinstance(obj, dict):
            return any(v is None or has_none(v) for v in obj.values())
        if isinstance(obj, list):
            return any(has_none(i) for i in obj)
        return False
    assert not has_none(dumped)


def test_model_dump_full_roundtrip():
    """Config serialised then re-loaded must produce identical object."""
    original = ApplianceConfig(
        storage_media=StorageMediaConfig(
            primary_disk_type=DiskType.NVME_SSD,
            primary_disk_count=8,
            primary_disk_capacity_tb=2.0
        ),
        storage_config=StorageConfig(
            raid_level=RaidLevel.RAID10,
            stripe_size_kb=128
        )
    )
    roundtripped = ApplianceConfig(**original.model_dump())
    assert roundtripped.storage_media.primary_disk_type == DiskType.NVME_SSD
    assert roundtripped.storage_config.raid_level == RaidLevel.RAID10


# ─── Stripe Size Default ───────────────────────────────────────────────────────

def test_stripe_size_default():
    """StorageConfig stripe_size_kb must default to 64."""
    sc = StorageConfig()
    assert sc.stripe_size_kb == 64
