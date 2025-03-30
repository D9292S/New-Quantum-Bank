#!/usr/bin/env python3
"""
Quantum Bank Bot Clustering System

This script runs multiple instances of the bot in separate processes,
each handling a subset of the total shards for better performance.
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from threading import Thread

import psutil

__version__ = "1.0.0"


class BotCluster:
    """Manages a cluster of bot processes for scalability"""

    def __init__(self, cluster_count: int, shard_count: int, launcher_path: str, restart_delay: int = 5):
        self.cluster_count = cluster_count
        self.shard_count = shard_count
        self.launcher_path = launcher_path
        self.restart_delay = restart_delay
        self.processes: dict[int, subprocess.Popen] = {}
        self.start_times: dict[int, float] = {}
        self.running = True

        # Register signal handlers
        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)

        # Calculate shards per cluster
        self.calculate_shard_distribution()

    def calculate_shard_distribution(self):
        """Calculate how many shards each cluster should handle"""
        self.shards_per_cluster = {}
        base_shards = self.shard_count // self.cluster_count
        remainder = self.shard_count % self.cluster_count

        for i in range(self.cluster_count):
            # Each cluster gets at least base_shards
            cluster_shards = base_shards
            # Distribute remainder among first 'remainder' clusters
            if i < remainder:
                cluster_shards += 1
            self.shards_per_cluster[i] = cluster_shards

        print(f"Shard distribution: {self.shards_per_cluster}")

        # Calculate actual shard IDs for each cluster
        self.shard_ids_per_cluster = {}
        current_shard = 0

        for cluster_id, shard_count in self.shards_per_cluster.items():
            self.shard_ids_per_cluster[cluster_id] = list(range(current_shard, current_shard + shard_count))
            current_shard += shard_count

    def start_cluster(self, cluster_id: int):
        """Start a bot cluster"""
        if cluster_id in self.processes and self.processes[cluster_id].poll() is None:
            print(f"Cluster {cluster_id} is already running")
            return

        # Get shard IDs for this cluster
        shard_ids = self.shard_ids_per_cluster.get(cluster_id, [])
        shard_ids_str = ",".join(map(str, shard_ids))

        # Construct command with proper arguments
        cmd = [
            sys.executable,
            self.launcher_path,
            "--cluster",
            str(cluster_id),
            "--clusters",
            str(self.cluster_count),
            "--shards",
            str(self.shard_count),
            "--shardids",
            shard_ids_str,
        ]

        # Start the process
        print(f"Starting cluster {cluster_id} with shards {shard_ids}...")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
        )

        self.processes[cluster_id] = process
        self.start_times[cluster_id] = time.time()
        print(f"Cluster {cluster_id} started with PID {process.pid}")

        # Start a separate thread to capture and log the cluster's output
        # This helps with debugging and monitoring
        Thread(target=self._log_output, args=(process, cluster_id), daemon=True).start()

    def _log_output(self, process, cluster_id):
        """Log output from a cluster process"""
        try:
            log_dir = "logs"
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)

            log_file = os.path.join(log_dir, f"cluster_{cluster_id}.log")

            with open(log_file, "a", encoding="utf-8") as f:
                timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")
                f.write(f"{timestamp}Cluster {cluster_id} started with PID {process.pid}\n")

                for line in iter(process.stdout.readline, ""):
                    stripped_line = line.strip()
                    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")
                    print(f"[Cluster {cluster_id}] {stripped_line}")
                    f.write(f"{timestamp}{stripped_line}\n")
                    f.flush()  # Ensure log is written immediately

        except Exception as e:
            print(f"Error reading output from cluster {cluster_id}: {e}")

    def start_all(self):
        """Start all clusters"""
        print(f"Starting {self.cluster_count} clusters with {self.shard_count} total shards")
        for i in range(self.cluster_count):
            self.start_cluster(i)
            # Wait briefly between starts to avoid resource contention
            time.sleep(1)

    def monitor_clusters(self):
        """Monitor and restart crashed clusters"""
        print("Monitoring cluster processes...")
        try:
            while self.running:
                for cluster_id, process in list(self.processes.items()):
                    # Check if process is still running
                    if process.poll() is not None:
                        exit_code = process.poll()
                        print(f"Cluster {cluster_id} exited with code {exit_code}, restarting...")
                        # Remove the crashed process
                        self.processes.pop(cluster_id)
                        # Wait before restarting
                        time.sleep(self.restart_delay)
                        # Restart the cluster
                        self.start_cluster(cluster_id)

                time.sleep(1)
        except KeyboardInterrupt:
            self.shutdown()

    def get_status(self):
        """Get detailed status of all clusters"""
        status = {
            "clusters": {},
            "total_shards": self.shard_count,
            "cluster_count": self.cluster_count,
            "system": self._get_system_stats(),
        }

        # Get status for each cluster
        for cluster_id in range(self.cluster_count):
            process = self.processes.get(cluster_id)
            shard_ids = self.shard_ids_per_cluster.get(cluster_id, [])

            if process and process.poll() is None:
                # Process is running
                pid = process.pid
                psutil_process = psutil.Process(pid)

                # Calculate uptime
                uptime = time.time() - self.start_times.get(cluster_id, time.time())
                uptime_str = str(timedelta(seconds=int(uptime)))

                # Get resource usage
                try:
                    memory_info = psutil_process.memory_info()
                    cpu_percent = psutil_process.cpu_percent(interval=0.1)

                    cluster_status = {
                        "status": "running",
                        "pid": pid,
                        "uptime": uptime_str,
                        "memory_mb": round(memory_info.rss / (1024 * 1024), 2),
                        "cpu_percent": round(cpu_percent, 1),
                        "shard_ids": shard_ids,
                        "shard_count": len(shard_ids),
                    }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    cluster_status = {
                        "status": "unknown",
                        "pid": pid,
                        "uptime": uptime_str,
                        "shard_ids": shard_ids,
                        "shard_count": len(shard_ids),
                    }
            else:
                # Process is not running
                cluster_status = {
                    "status": "stopped",
                    "shard_ids": shard_ids,
                    "shard_count": len(shard_ids),
                }

            status["clusters"][cluster_id] = cluster_status

        return status

    def _get_system_stats(self):
        """Get system resource stats"""
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.5),
            "memory_percent": psutil.virtual_memory().percent,
            "memory_available_mb": round(psutil.virtual_memory().available / (1024 * 1024), 2),
            "memory_total_mb": round(psutil.virtual_memory().total / (1024 * 1024), 2),
        }

    def show_status(self):
        """Print formatted status information to console"""
        status = self.get_status()

        print("\n=== Quantum Bank Bot Cluster Status ===")
        print(f"Total Clusters: {status['cluster_count']}")
        print(f"Total Shards: {status['total_shards']}")

        # Print system stats
        system = status["system"]
        print(f"\nSystem CPU: {system['cpu_percent']}%")
        print(
            f"System Memory: {system['memory_percent']}% used ({system['memory_available_mb']} MB free of {system['memory_total_mb']} MB)"
        )

        # Print cluster stats
        print("\nClusters:")
        print("-" * 80)
        print(
            f"{'ID':^4} | {'Status':^10} | {'PID':^8} | {'Uptime':^15} | {'Memory (MB)':^12} | {'CPU %':^7} | {'Shards':^20}"
        )
        print("-" * 80)

        for cluster_id, cluster in sorted(status["clusters"].items()):
            status_str = cluster["status"]
            pid = cluster.get("pid", "N/A")
            uptime = cluster.get("uptime", "N/A")
            memory = cluster.get("memory_mb", "N/A")
            cpu = cluster.get("cpu_percent", "N/A")
            shards = f"{cluster.get('shard_count', 0)} ({', '.join(map(str, cluster['shard_ids']))})"

            print(
                f"{cluster_id:^4} | {status_str:^10} | {pid:^8} | {uptime:^15} | {memory:^12} | {cpu:^7} | {shards:^20}"
            )

        print("-" * 80)

    def shutdown(self):
        """Gracefully shut down all clusters"""
        self.running = False
        print("Shutting down all clusters...")

        # Send termination signal to all processes
        for cluster_id, process in self.processes.items():
            if process.poll() is None:  # If still running
                print(f"Terminating cluster {cluster_id} (PID: {process.pid})")
                try:
                    process.terminate()
                except Exception as e:
                    print(f"Error terminating cluster {cluster_id}: {e}")

        # Wait for processes to terminate gracefully
        print("Waiting for clusters to terminate...")
        for i in range(10):  # Wait up to 10 seconds
            if all(process.poll() is not None for process in self.processes.values()):
                break
            time.sleep(1)

        # Force kill any remaining processes
        for cluster_id, process in self.processes.items():
            if process.poll() is None:  # If still running
                print(f"Force killing cluster {cluster_id} (PID: {process.pid})")
                try:
                    process.kill()
                except Exception as e:
                    print(f"Error killing cluster {cluster_id}: {e}")

    def handle_signal(self, sig, frame):
        """Handle termination signals"""
        print(f"Received signal {sig}, shutting down...")
        self.shutdown()
        sys.exit(0)


def parse_arguments():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(description="Quantum Bank Bot Cluster Manager")
    parser.add_argument(
        "--clusters",
        "-c",
        type=int,
        default=os.cpu_count() or 2,
        help="Number of clusters to run (default: CPU count)",
    )
    parser.add_argument("--shards", "-s", type=int, default=1, help="Total number of shards across all clusters")
    parser.add_argument("--launcher", "-l", type=str, default="launcher.py", help="Path to launcher script")
    parser.add_argument(
        "--restart-delay",
        "-r",
        type=int,
        default=5,
        help="Seconds to wait before restarting a crashed cluster",
    )
    parser.add_argument("--status", action="store_true", help="Show status of running clusters and exit")
    parser.add_argument("--status-interval", type=int, default=0, help="Show status every N seconds (0 = disabled)")
    parser.add_argument(
        "--run-cluster",
        type=int,
        default=None,
        help="Run a single cluster with the specified ID (for testing)",
    )

    return parser.parse_args()


def check_for_running_clusters():
    """Check if there are any bot clusters already running"""
    running_clusters = []

    # Look for our own process ID to exclude it
    self_pid = os.getpid()

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            # Skip if this is our current process
            if proc.info["pid"] == self_pid:
                continue

            cmdline = proc.info.get("cmdline", [])

            # Skip invalid processes
            if not cmdline or len(cmdline) < 2:
                continue

            # Check for various indicators this is our bot process
            is_python = any(py in cmdline[0].lower() for py in ["python", "python3", "pythonw"])
            is_launcher = any("launcher.py" in arg for arg in cmdline)

            if is_python and is_launcher:
                # Search for --cluster argument
                cluster_id = None
                for i, arg in enumerate(cmdline):
                    if arg == "--cluster" and i + 1 < len(cmdline):
                        try:
                            cluster_id = int(cmdline[i + 1])
                            break
                        except (ValueError, IndexError):
                            pass

                # If no specific cluster ID found, assume it's a single shard
                pid = proc.info["pid"]
                if cluster_id is not None:
                    running_clusters.append((cluster_id, pid))
                    print(f"Found cluster {cluster_id} running with PID {pid}")
                else:
                    print(f"Found launcher.py process running with PID {pid} (no cluster ID)")

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, Exception) as e:
            # More generic error handling
            print(f"Error checking process: {e}")
            continue

    return running_clusters


def main():
    """Main function to start the cluster manager"""
    print(f"Quantum Bank Bot Cluster Manager v{__version__}")

    args = parse_arguments()

    # Special case: Run a single cluster directly
    if args.run_cluster is not None:
        print(f"Running single cluster {args.run_cluster} directly")
        cluster_id = args.run_cluster

        # Get shard IDs for this cluster
        total_shards = args.shards
        total_clusters = args.clusters

        # Calculate shards for this cluster
        base_shards = total_shards // total_clusters
        remainder = total_shards % total_clusters

        # Calculate start shard for this cluster
        start_shard = cluster_id * base_shards
        if cluster_id < remainder:
            start_shard += cluster_id
        else:
            start_shard += remainder

        # Calculate end shard for this cluster
        end_shard = start_shard + base_shards - 1
        if cluster_id < remainder:
            end_shard += 1

        shard_ids = list(range(start_shard, end_shard + 1))
        shard_ids_str = ",".join(map(str, shard_ids))

        # Run launcher directly with proper arguments
        cmd = [
            sys.executable,
            args.launcher,
            "--cluster",
            str(cluster_id),
            "--clusters",
            str(total_clusters),
            "--shards",
            str(total_shards),
            "--shardids",
            shard_ids_str,
        ]

        print(f"Starting cluster with command: {' '.join(cmd)}")
        os.execv(sys.executable, cmd)
        return  # This point is never reached as execv replaces the process

    # Check for already running clusters
    running_clusters = check_for_running_clusters()
    if running_clusters:
        print(f"Found {len(running_clusters)} clusters already running:")
        for cluster_id, pid in running_clusters:
            print(f"  Cluster {cluster_id} (PID: {pid})")

        # If only status mode, show the status of these clusters
        if args.status:
            # Create a BotCluster object to show status
            cluster_manager = BotCluster(
                cluster_count=max(c[0] for c in running_clusters) + 1,
                shard_count=args.shards,
                launcher_path=args.launcher,
                restart_delay=args.restart_delay,
            )

            # Add existing processes to the manager
            for cluster_id, pid in running_clusters:
                try:
                    process = psutil.Process(pid)
                    cluster_manager.processes[cluster_id] = process
                    cluster_manager.start_times[cluster_id] = process.create_time()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    print(f"Warning: Could not access process {pid}")

            # Show status and exit
            cluster_manager.show_status()
            return

        print("Use --status to show more detailed status")

        if not args.status:
            response = input("Do you want to start additional clusters? [y/N] ")
            if response.lower() != "y":
                print("Exiting.")
                return

    # Status mode only - check running clusters and show their status
    if args.status:
        if not running_clusters:
            print("No clusters are currently running.")
            return

    # Validate arguments
    if args.clusters < 1:
        print("ERROR: Number of clusters must be at least 1")
        sys.exit(1)

    if args.shards < args.clusters:
        print(f"WARNING: Using {args.clusters} shards instead of {args.shards} to match cluster count")
        args.shards = args.clusters

    if not os.path.exists(args.launcher):
        print(f"ERROR: Launcher script '{args.launcher}' not found")
        sys.exit(1)

    # Start the cluster manager
    cluster_manager = BotCluster(
        cluster_count=args.clusters,
        shard_count=args.shards,
        launcher_path=args.launcher,
        restart_delay=args.restart_delay,
    )

    # Start all clusters
    cluster_manager.start_all()

    # Show status periodically if requested
    if args.status_interval > 0:

        def status_thread():
            while cluster_manager.running:
                try:
                    cluster_manager.show_status()
                    time.sleep(args.status_interval)
                except KeyboardInterrupt:
                    return
                except Exception as e:
                    print(f"Error in status thread: {e}")
                    time.sleep(args.status_interval)

        Thread(target=status_thread, daemon=True).start()

    # Monitor and restart crashed clusters
    cluster_manager.monitor_clusters()


if __name__ == "__main__":
    main()
