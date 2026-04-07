"""
Tests for core/calibration.py

Verifies that the CalibrationEngine produces correct warnings and
degradation factors for known input configurations.
"""

import pytest

from core.calibration import CalibrationEngine
from core.config_model import (
    ApplianceConfig,
    NetworkConfig,
    ComputeConfig,
    StorageConfig,
    VeeamConfig,
    RaidLevel,
    NicSpeed,
)


@pytest.fixture
def engine():
    return CalibrationEngine()


# ─── No Config ────────────────────────────────────────────────────────────────

def test_empty_config_returns_only_assumptions(engine):
    """With no config at all, calibration must return assumptions only — no warnings."""
    ctx = engine.build_calibration_context(ApplianceConfig())
    assert isinstance(ctx["warnings"], list)
    assert isinstance(ctx["assumptions"], list)
    assert isinstance(ctx["degradation_factors"], dict)
    # No warnings without any config to evaluate
    assert len(ctx["warnings"]) == 0
    # Peak-hour assumption is always injected
    assert any("p99" in a or "tail" in a.lower() for a in ctx["assumptions"])


# ─── Network Calibration ──────────────────────────────────────────────────────

def test_shared_network_produces_warning_and_factor(engine):
    config = ApplianceConfig(
        network=NetworkConfig(
            nic_speed=NicSpeed.GBE_10,
            dedicated_storage_network=False,
            jumbo_frames_mtu9000=True,
        )
    )
    ctx = engine.build_calibration_context(config)
    assert "shared_network" in ctx["degradation_factors"]
    assert ctx["degradation_factors"]["shared_network"] == 0.80
    assert any("shared" in w.lower() or "contention" in w.lower() for w in ctx["warnings"])


def test_no_jumbo_frames_produces_warning_and_factor(engine):
    config = ApplianceConfig(
        network=NetworkConfig(
            nic_speed=NicSpeed.GBE_10,
            dedicated_storage_network=True,
            jumbo_frames_mtu9000=False,
        )
    )
    ctx = engine.build_calibration_context(config)
    assert "no_jumbo_frames" in ctx["degradation_factors"]
    assert ctx["degradation_factors"]["no_jumbo_frames"] == 0.90
    assert any("jumbo" in w.lower() or "mtu" in w.lower() for w in ctx["warnings"])


def test_ideal_network_produces_no_warnings(engine):
    config = ApplianceConfig(
        network=NetworkConfig(
            nic_speed=NicSpeed.GBE_25,
            dedicated_storage_network=True,
            jumbo_frames_mtu9000=True,
            bonding_mode="lacp_802_3ad",
        )
    )
    ctx = engine.build_calibration_context(config)
    assert "shared_network" not in ctx["degradation_factors"]
    assert "no_jumbo_frames" not in ctx["degradation_factors"]


def test_no_network_config_adds_assumption(engine):
    config = ApplianceConfig()
    ctx = engine.build_calibration_context(config)
    assert any("network" in a.lower() for a in ctx["assumptions"])


# ─── CPU Calibration ──────────────────────────────────────────────────────────

def test_high_cpu_reservation_produces_warning(engine):
    config = ApplianceConfig(
        compute=ComputeConfig(cpu_reservation_pct=25)
    )
    ctx = engine.build_calibration_context(config)
    assert any("reservation" in w.lower() or "cpu" in w.lower() for w in ctx["warnings"])


def test_low_cpu_reservation_no_warning(engine):
    config = ApplianceConfig(
        compute=ComputeConfig(cpu_reservation_pct=10)
    )
    ctx = engine.build_calibration_context(config)
    # Low reservation (10%) must not trigger the CPU warning
    assert not any("cpu_reservation" in w.lower() for w in ctx["warnings"])


# ─── I/O Calibration ──────────────────────────────────────────────────────────

def test_write_through_produces_warning_and_60pct_factor(engine):
    config = ApplianceConfig(
        storage_config=StorageConfig(write_back_policy="write_through")
    )
    ctx = engine.build_calibration_context(config)
    assert "write_through" in ctx["degradation_factors"]
    assert ctx["degradation_factors"]["write_through"] == 0.60
    assert any("write-through" in w.lower() or "write_through" in w.lower() for w in ctx["warnings"])


def test_write_back_no_io_warning(engine):
    config = ApplianceConfig(
        storage_config=StorageConfig(write_back_policy="write_back")
    )
    ctx = engine.build_calibration_context(config)
    assert "write_through" not in ctx["degradation_factors"]


def test_raid6_parity_assumption(engine):
    config = ApplianceConfig(
        storage_config=StorageConfig(raid_level=RaidLevel.RAID6)
    )
    ctx = engine.build_calibration_context(config)
    assert any("raid6" in a.lower() or "parity" in a.lower() for a in ctx["assumptions"])


# ─── Veeam Calibration ────────────────────────────────────────────────────────

def test_3_concurrent_jobs_produces_warning(engine):
    config = ApplianceConfig(
        veeam=VeeamConfig(concurrent_backup_jobs=3)
    )
    ctx = engine.build_calibration_context(config)
    assert "concurrent_jobs" in ctx["degradation_factors"]
    assert ctx["degradation_factors"]["concurrent_jobs"] == 0.75
    assert any("concurrent" in w.lower() or "job" in w.lower() for w in ctx["warnings"])


def test_4_concurrent_jobs_factor(engine):
    config = ApplianceConfig(
        veeam=VeeamConfig(concurrent_backup_jobs=4)
    )
    ctx = engine.build_calibration_context(config)
    assert ctx["degradation_factors"]["concurrent_jobs"] == 0.65


def test_5_concurrent_jobs_factor(engine):
    config = ApplianceConfig(
        veeam=VeeamConfig(concurrent_backup_jobs=5)
    )
    ctx = engine.build_calibration_context(config)
    assert ctx["degradation_factors"]["concurrent_jobs"] == 0.55


def test_6_concurrent_jobs_clamps_to_5_plus(engine):
    """6 jobs should use the jobs_5_plus factor (0.55)."""
    config = ApplianceConfig(
        veeam=VeeamConfig(concurrent_backup_jobs=6)
    )
    ctx = engine.build_calibration_context(config)
    assert ctx["degradation_factors"]["concurrent_jobs"] == 0.55


def test_2_concurrent_jobs_no_factor(engine):
    """2 concurrent jobs is normal — no degradation factor applied."""
    config = ApplianceConfig(
        veeam=VeeamConfig(concurrent_backup_jobs=2)
    )
    ctx = engine.build_calibration_context(config)
    assert "concurrent_jobs" not in ctx["degradation_factors"]


def test_encryption_enabled_adds_factor(engine):
    config = ApplianceConfig(
        veeam=VeeamConfig(backup_encryption=True)
    )
    ctx = engine.build_calibration_context(config)
    assert "encryption_overhead" in ctx["degradation_factors"]
    # Factor = 1 - (10/100) = 0.90
    assert abs(ctx["degradation_factors"]["encryption_overhead"] - 0.90) < 0.001


def test_encryption_disabled_no_factor(engine):
    config = ApplianceConfig(
        veeam=VeeamConfig(backup_encryption=False)
    )
    ctx = engine.build_calibration_context(config)
    assert "encryption_overhead" not in ctx["degradation_factors"]


# ─── Peak Hour Context ────────────────────────────────────────────────────────

def test_peak_hour_assumption_always_present(engine):
    """Peak-hour tail latency assumption must always be injected."""
    ctx = engine.build_calibration_context(ApplianceConfig())
    assert any("p99" in a or "tail" in a.lower() or "peak" in a.lower()
               for a in ctx["assumptions"])
