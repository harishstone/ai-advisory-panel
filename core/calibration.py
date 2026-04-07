import json
from pathlib import Path
from typing import Dict, Any
from core.config_model import ApplianceConfig


class CalibrationEngine:
    """
    Applies real-world degradation factors to theoretical performance estimates.
    Produces a CalibrationContext dict that is injected into advisory prompts.
    """

    def __init__(self):
        factors_path = Path(__file__).parent.parent / "data" / "calibration_factors.json"
        with open(factors_path) as f:
            self.factors = json.load(f)

    def build_calibration_context(self, config: ApplianceConfig) -> Dict[str, Any]:
        """
        Given an ApplianceConfig, return a dict of calibration factors
        and warnings relevant to this configuration.
        """
        context: Dict[str, Any] = {
            "warnings": [],
            "degradation_factors": {},
            "assumptions": []
        }

        self._apply_network_calibration(config, context)
        self._apply_cpu_calibration(config, context)
        self._apply_io_calibration(config, context)
        self._apply_veeam_calibration(config, context)
        self._apply_peak_hour_context(context)

        return context

    def _apply_network_calibration(self, config: ApplianceConfig, ctx: dict) -> None:
        net = config.network
        if net is None:
            ctx["assumptions"].append(
                "Network configuration not provided. Assuming ideal conditions: "
                "no packet loss, no jitter, dedicated storage network."
            )
            return

        if not net.dedicated_storage_network:
            ctx["warnings"].append(
                "Shared network (production + storage): expect 15-25% throughput "
                "reduction during peak hours due to bandwidth contention."
            )
            ctx["degradation_factors"]["shared_network"] = 0.80

        if not net.jumbo_frames_mtu9000:
            ctx["warnings"].append(
                "Jumbo frames not confirmed. Standard MTU (1500) increases CPU overhead "
                "for large sequential I/O and reduces NAS/iSCSI throughput by ~8-12%."
            )
            ctx["degradation_factors"]["no_jumbo_frames"] = 0.90

        if net.bonding_mode in ("none", None):
            ctx["assumptions"].append(
                "Single NIC active. No bonding/LACP. Throughput capped at single port speed. "
                "No network redundancy."
            )

    def _apply_cpu_calibration(self, config: ApplianceConfig, ctx: dict) -> None:
        compute = config.compute
        if compute is None:
            return

        if compute.cpu_reservation_pct and compute.cpu_reservation_pct > 20:
            ctx["warnings"].append(
                f"High CPU reservation ({compute.cpu_reservation_pct}%) for storage/backup services "
                f"leaves limited headroom for workloads under peak load."
            )

    def _apply_io_calibration(self, config: ApplianceConfig, ctx: dict) -> None:
        sc = config.storage_config
        if sc is None:
            return

        if sc.write_back_policy == "write_through":
            ctx["warnings"].append(
                "Write-through cache policy active. Write performance will be ~40% lower "
                "than write-back. Recommended: enable write-back with BBU/capacitor protection."
            )
            ctx["degradation_factors"]["write_through"] = 0.60

        if sc.raid_level and sc.raid_level.value in ("raid5", "raid6"):
            ctx["assumptions"].append(
                f"{sc.raid_level.value.upper()} write penalty applies: every write requires "
                f"additional parity read-modify-write cycles. Random write performance will be "
                f"significantly lower than sequential."
            )

    def _apply_veeam_calibration(self, config: ApplianceConfig, ctx: dict) -> None:
        veeam = config.veeam
        if veeam is None:
            return

        if veeam.concurrent_backup_jobs and veeam.concurrent_backup_jobs >= 2:
            n = veeam.concurrent_backup_jobs
            if n == 2:
                factor_key = "jobs_2"
            elif n == 3:
                factor_key = "jobs_3"
            elif n == 4:
                factor_key = "jobs_4"
            else:
                factor_key = "jobs_5_plus"

            factor = self.factors["veeam"]["concurrent_jobs_scaling"].get(factor_key, 0.55)
            ctx["degradation_factors"]["concurrent_jobs"] = factor
            ctx["warnings"].append(
                f"{n} concurrent backup jobs: per-job throughput "
                f"reduced to ~{int(factor * 100)}% of single-job throughput due to I/O contention."
            )

        if veeam.backup_encryption:
            ctx["degradation_factors"]["encryption_overhead"] = (
                1 - self.factors["veeam"]["encryption_overhead_pct"] / 100
            )
            ctx["warnings"].append(
                "Backup file encryption enabled: ~10% additional CPU overhead on backup proxy."
            )

    def _apply_peak_hour_context(self, ctx: dict) -> None:
        ctx["assumptions"].append(
            "Performance estimates represent average sustained throughput. "
            "Peak-hour tail latency (p99) will be 3-8x the average latency shown. "
            "Queue backpressure under peak load adds ~15ms additional latency."
        )
