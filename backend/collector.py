"""
collector.py — System Metrics Collector
Gathers CPU, RAM, disk, network, process, and temperature data using psutil.
"""

import psutil
import platform
import socket
import time
from datetime import datetime
from typing import Any, Dict, List


class MetricsCollector:
    """
    Collects live system health metrics using psutil.
    All public methods return plain Python dicts for easy JSON serialisation.
    """

    def __init__(self):
        # Warm-up call so the first cpu_percent isn't 0.0
        psutil.cpu_percent(interval=None)
        self._boot_time = psutil.boot_time()

    # ── Public API ─────────────────────────────────────────────────────────
    def collect(self) -> Dict[str, Any]:
        """Return a full snapshot of all system metrics."""
        return {
            "cpu":      self._cpu(),
            "memory":   self._memory(),
            "disk":     self._disk(),
            "network":  self._network(),
            "processes": self._processes(),
            "system":   self._system_info(),
            "uptime_seconds": int(time.time() - self._boot_time),
        }

    # ── CPU ────────────────────────────────────────────────────────────────
    def _cpu(self) -> Dict[str, Any]:
        freq = psutil.cpu_freq()
        per_core = psutil.cpu_percent(interval=0.1, percpu=True)
        load = psutil.getloadavg() if hasattr(psutil, "getloadavg") else (0, 0, 0)
        temps = self._cpu_temps()
        return {
            "usage_percent":    psutil.cpu_percent(interval=None),
            "per_core_percent": per_core,
            "core_count":       psutil.cpu_count(logical=False) or 1,
            "logical_count":    psutil.cpu_count(logical=True),
            "freq_current_mhz": round(freq.current, 1) if freq else None,
            "freq_max_mhz":     round(freq.max, 1) if freq else None,
            "load_avg_1m":      round(load[0], 2),
            "load_avg_5m":      round(load[1], 2),
            "load_avg_15m":     round(load[2], 2),
            "temperature_c":    temps,
        }

    def _cpu_temps(self):
        try:
            sensors = psutil.sensors_temperatures()
            if not sensors:
                return None
            # Try common sensor names
            for key in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
                if key in sensors and sensors[key]:
                    return round(sensors[key][0].current, 1)
        except (AttributeError, NotImplementedError):
            pass
        return None

    # ── Memory ─────────────────────────────────────────────────────────────
    def _memory(self) -> Dict[str, Any]:
        vm  = psutil.virtual_memory()
        swp = psutil.swap_memory()
        return {
            "total_gb":         round(vm.total / (1024**3), 2),
            "used_gb":          round(vm.used  / (1024**3), 2),
            "available_gb":     round(vm.available / (1024**3), 2),
            "usage_percent":    vm.percent,
            "swap_total_gb":    round(swp.total / (1024**3), 2),
            "swap_used_gb":     round(swp.used  / (1024**3), 2),
            "swap_percent":     swp.percent,
        }

    # ── Disk ───────────────────────────────────────────────────────────────
    def _disk(self) -> Dict[str, Any]:
        partitions = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                partitions.append({
                    "device":        part.device,
                    "mountpoint":    part.mountpoint,
                    "fstype":        part.fstype,
                    "total_gb":      round(usage.total / (1024**3), 2),
                    "used_gb":       round(usage.used  / (1024**3), 2),
                    "free_gb":       round(usage.free  / (1024**3), 2),
                    "usage_percent": usage.percent,
                })
            except PermissionError:
                continue

        io = psutil.disk_io_counters()
        return {
            "partitions":     partitions,
            "read_mb":        round(io.read_bytes  / (1024**2), 2) if io else 0,
            "write_mb":       round(io.write_bytes / (1024**2), 2) if io else 0,
            "read_count":     io.read_count  if io else 0,
            "write_count":    io.write_count if io else 0,
        }

    # ── Network ────────────────────────────────────────────────────────────
    def _network(self) -> Dict[str, Any]:
        counters = psutil.net_io_counters()
        interfaces: List[Dict] = []
        for name, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    interfaces.append({"interface": name, "ip": addr.address})
                    break

        conns = psutil.net_connections(kind="inet")
        return {
            "bytes_sent_mb":    round(counters.bytes_sent / (1024**2), 2),
            "bytes_recv_mb":    round(counters.bytes_recv / (1024**2), 2),
            "packets_sent":     counters.packets_sent,
            "packets_recv":     counters.packets_recv,
            "errors_in":        counters.errin,
            "errors_out":       counters.errout,
            "connections_total": len(conns),
            "interfaces":       interfaces,
        }

    # ── Processes ──────────────────────────────────────────────────────────
    def _processes(self) -> Dict[str, Any]:
        procs = []
        attrs = ["pid", "name", "cpu_percent", "memory_percent", "status"]
        for p in psutil.process_iter(attrs=attrs):
            try:
                info = p.info
                if info["cpu_percent"] is not None:
                    procs.append({
                        "pid":    info["pid"],
                        "name":   info["name"],
                        "cpu":    round(info["cpu_percent"], 2),
                        "mem":    round(info["memory_percent"], 2),
                        "status": info["status"],
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Sort by CPU desc, take top 10
        top = sorted(procs, key=lambda x: x["cpu"], reverse=True)[:10]
        return {
            "total":   len(procs),
            "running": sum(1 for p in procs if p["status"] == "running"),
            "top_10":  top,
        }

    # ── System Info ────────────────────────────────────────────────────────
    def _system_info(self) -> Dict[str, Any]:
        uname = platform.uname()
        return {
            "hostname":  socket.gethostname(),
            "os":        uname.system,
            "os_release": uname.release,
            "architecture": uname.machine,
            "python_version": platform.python_version(),
        }
