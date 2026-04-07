from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


# ─── Section 1: Appliance Selection & Use Case Profile ───────────────────────

class ApplianceType(str, Enum):
    HYPERCONVERGED = "hyperconverged_compute"
    BACKUP_DR = "backup_dr"
    BAREMETAL_STORAGE = "baremetal_storage"


class WorkloadType(str, Enum):
    VEEAM_BACKUP = "veeam_backup_jobs"
    VEEAM_BACKUP_COPY = "veeam_backup_copy_jobs"
    VEEAM_REPLICATION = "veeam_replication_jobs"
    VEEAM_RESTORE = "veeam_restore_operations"
    VEEAM_SYNTHETIC = "veeam_synthetic_operations"
    VM_GENERAL = "general_vm_workloads"
    DATABASE = "database_workloads"
    FILE_SHARING = "file_sharing_nas"
    OBJECT_STORAGE = "object_storage_s3"
    BLOCK_STORAGE = "block_storage_iscsi"


class ApplianceProfile(BaseModel):
    appliance_type: Optional[ApplianceType] = None
    protocols: Optional[List[str]] = None           # ["iscsi", "nas_cifs", "nas_nfs", "s3"]
    primary_workloads: Optional[List[WorkloadType]] = None  # top 3
    total_usable_capacity_tb: Optional[float] = None
    avg_dataset_size_gb: Optional[float] = None
    concurrent_workloads: Optional[int] = None
    annual_growth_rate_pct: Optional[float] = None


# ─── Section 2: Hardware Specifications ──────────────────────────────────────

class ComputeConfig(BaseModel):
    cpu_model: Optional[str] = None
    total_physical_cores: Optional[int] = None
    total_logical_processors: Optional[int] = None
    cpu_reservation_pct: Optional[float] = None
    total_ram_gb: Optional[int] = None
    ram_storage_controller_gb: Optional[int] = None
    ram_vms_gb: Optional[int] = None


class DiskType(str, Enum):
    SAS_HDD = "sas_hdd"
    SATA_HDD = "sata_hdd"
    SSD_SATA_SAS = "ssd_sata_sas"
    NVME_SSD = "nvme_ssd"


class StorageMediaConfig(BaseModel):
    primary_disk_type: Optional[DiskType] = None
    primary_disk_capacity_tb: Optional[float] = None
    primary_disk_count: Optional[int] = None
    primary_disk_rpm: Optional[int] = None          # HDD only
    fast_tier_type: Optional[str] = None            # "nvme_ssd", "sata_ssd", "none"
    fast_tier_capacity_gb: Optional[float] = None
    controller_model: Optional[str] = None
    controller_cache_gb: Optional[int] = None
    cache_protection: Optional[str] = None          # "battery", "capacitor", "none"
    max_stripe_size_kb: Optional[int] = None


# ─── Section 3: Storage Configuration & RAID ─────────────────────────────────

class RaidLevel(str, Enum):
    RAID1 = "raid1"
    RAID5 = "raid5"
    RAID6 = "raid6"
    RAID10 = "raid10"
    RAID50 = "raid50"
    RAID60 = "raid60"
    ERASURE_CODING = "erasure_coding"
    JBOD = "jbod"


class VolumeIOProfile(BaseModel):
    volume_purpose: Optional[str] = None
    block_size: Optional[str] = None                # "4k", "8k", "16k", "32k", "64k", "mixed"
    read_write_ratio_read_pct: Optional[int] = None # 70 = 70% read
    access_pattern: Optional[str] = None            # "random", "sequential", "mixed"
    random_pct: Optional[int] = None                # if mixed
    queue_depth: Optional[int] = None


class StorageConfig(BaseModel):
    raid_level: Optional[RaidLevel] = None
    raid_groups_count: Optional[int] = None
    stripe_size_kb: Optional[int] = Field(default=64)
    hot_spare: Optional[str] = None                 # "none", "per_group", "global"
    global_spares_count: Optional[int] = None
    write_back_policy: Optional[str] = None         # "write_through", "write_back", "always_write_back"
    io_profiles: Optional[List[VolumeIOProfile]] = None
    thin_provisioning: Optional[bool] = None
    deduplication_enabled: Optional[bool] = None
    dedup_ratio: Optional[float] = None             # e.g., 2.5 for 2.5:1
    compression_enabled: Optional[bool] = None
    compression_algorithm: Optional[str] = None


# ─── Section 4: Network Configuration ────────────────────────────────────────

class NicSpeed(str, Enum):
    GBE_1 = "1gbe"
    GBE_10 = "10gbe"
    GBE_25 = "25gbe"
    GBE_40 = "40gbe"
    GBE_100 = "100gbe"


class NetworkConfig(BaseModel):
    nic_speed: Optional[NicSpeed] = None
    active_data_ports: Optional[int] = None
    bonding_mode: Optional[str] = None              # "none", "lacp_802_3ad", "active_passive", "other"
    lacp_active_links: Optional[int] = None
    switch_model: Optional[str] = None
    jumbo_frames_mtu9000: Optional[bool] = None
    dedicated_storage_network: Optional[bool] = None
    expected_latency_ms: Optional[float] = None
    # iSCSI
    iscsi_multipathing: Optional[bool] = None
    iscsi_chap: Optional[bool] = None
    # NAS
    smb_version: Optional[str] = None
    nfs_version: Optional[str] = None
    nas_async_io: Optional[bool] = None
    # S3
    s3_object_size_distribution: Optional[str] = None
    s3_concurrent_ops: Optional[int] = None


# ─── Section 5: Veeam-Specific Parameters ────────────────────────────────────

class VeeamConfig(BaseModel):
    veeam_version: Optional[str] = None
    proxy_location: Optional[str] = None            # "on_appliance", "external_windows", "external_linux"
    transport_mode: Optional[str] = None            # "direct_storage", "virtual_appliance", "network"
    repository_type: Optional[str] = None           # "performance_optimized", "capacity_optimized"
    per_vm_backup_files: Optional[bool] = None
    backup_encryption: Optional[bool] = None
    daily_change_rate_pct: Optional[float] = None
    backup_window_hours: Optional[float] = None
    concurrent_backup_jobs: Optional[int] = None
    synthetic_full_frequency: Optional[str] = None  # "weekly", "monthly", "never"
    backup_copy_enabled: Optional[bool] = None
    backup_copy_target: Optional[str] = None
    restore_type: Optional[str] = None              # "file_level", "image_level", "instant_vm"
    restore_target: Optional[str] = None            # "original", "alternate", "cloud"
    concurrent_restores: Optional[int] = None


# ─── Section 6: Environmental & Operational Factors ──────────────────────────

class EnvironmentConfig(BaseModel):
    ambient_temp_celsius: Optional[float] = None
    power_redundancy: Optional[str] = None          # "single_psu", "dual_psu", "dual_psu_ups"
    uptime_requirement_pct: Optional[float] = None  # e.g., 99.9
    use_stonefly_scvm: Optional[bool] = None
    external_monitoring: Optional[bool] = None
    alert_threshold_pct: Optional[float] = None


# ─── Master Config Model ──────────────────────────────────────────────────────

class ApplianceConfig(BaseModel):
    """
    Master configuration model. All sections are optional — the advisory engine
    will note any missing fields that are relevant to a specific question.
    """
    profile: Optional[ApplianceProfile] = None
    compute: Optional[ComputeConfig] = None
    storage_media: Optional[StorageMediaConfig] = None
    storage_config: Optional[StorageConfig] = None
    network: Optional[NetworkConfig] = None
    veeam: Optional[VeeamConfig] = None
    environment: Optional[EnvironmentConfig] = None
