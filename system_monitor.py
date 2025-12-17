#!/usr/bin/python3
# -*- coding: UTF-8 -*-
"""
System monitoring module for gathering device statistics.
Provides CPU, memory, storage, temperature, and network information.
"""

import os
import time
import logging
from pathlib import Path

class SystemMonitor:
    """Gathers system statistics for display on the LCD."""
    
    def __init__(self):
        self.last_cpu_times = None
        self.last_net_stats = None
        self.last_update = 0
        
    def get_cpu_usage(self):
        """Get CPU usage percentage. Returns dict with overall and per-core stats."""
        try:
            with open('/proc/stat', 'r') as f:
                lines = f.readlines()
            
            cpu_info = {}
            for line in lines:
                if line.startswith('cpu'):
                    parts = line.split()
                    cpu_name = parts[0]
                    # user, nice, system, idle, iowait, irq, softirq, steal
                    times = [int(x) for x in parts[1:8] if x.isdigit()]
                    if len(times) >= 4:
                        total = sum(times)
                        idle = times[3]
                        cpu_info[cpu_name] = {'total': total, 'idle': idle}
            
            # Calculate usage if we have previous data
            if self.last_cpu_times:
                result = {}
                for cpu_name, times in cpu_info.items():
                    if cpu_name in self.last_cpu_times:
                        prev = self.last_cpu_times[cpu_name]
                        total_delta = times['total'] - prev['total']
                        idle_delta = times['idle'] - prev['idle']
                        if total_delta > 0:
                            usage = 100.0 * (1.0 - idle_delta / total_delta)
                            result[cpu_name] = max(0.0, min(100.0, usage))
                        else:
                            result[cpu_name] = 0.0
                self.last_cpu_times = cpu_info
                return result
            else:
                self.last_cpu_times = cpu_info
                return {k: 0.0 for k in cpu_info.keys()}
                
        except Exception as e:
            logging.debug(f"get_cpu_usage failed: {e}")
            return {'cpu': 0.0}
    
    def get_cpu_temperature(self):
        """Get CPU temperature in Celsius."""
        temp_paths = [
            '/sys/class/thermal/thermal_zone0/temp',
            '/sys/class/hwmon/hwmon0/temp1_input',
        ]
        
        for path in temp_paths:
            try:
                with open(path, 'r') as f:
                    temp = int(f.read().strip())
                    # Temperature is usually in millidegrees
                    if temp > 1000:
                        temp = temp / 1000.0
                    return temp
            except Exception:
                continue
        
        return None
    
    def get_memory_info(self):
        """Get memory usage information."""
        try:
            with open('/proc/meminfo', 'r') as f:
                lines = f.readlines()
            
            mem_info = {}
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    # Extract numeric value (in kB)
                    value_parts = value.strip().split()
                    if value_parts:
                        try:
                            mem_info[key.strip()] = int(value_parts[0])
                        except ValueError:
                            pass
            
            total = mem_info.get('MemTotal', 0)
            available = mem_info.get('MemAvailable', mem_info.get('MemFree', 0))
            buffers = mem_info.get('Buffers', 0)
            cached = mem_info.get('Cached', 0)
            
            used = total - available
            
            return {
                'total': total * 1024,  # Convert to bytes
                'used': used * 1024,
                'available': available * 1024,
                'percent': (used / total * 100.0) if total > 0 else 0.0,
                'buffers': buffers * 1024,
                'cached': cached * 1024,
            }
        except Exception as e:
            logging.debug(f"get_memory_info failed: {e}")
            return {'total': 0, 'used': 0, 'available': 0, 'percent': 0.0}
    
    def get_swap_info(self):
        """Get swap usage information."""
        try:
            with open('/proc/meminfo', 'r') as f:
                lines = f.readlines()
            
            swap_total = 0
            swap_free = 0
            
            for line in lines:
                if line.startswith('SwapTotal:'):
                    swap_total = int(line.split()[1])
                elif line.startswith('SwapFree:'):
                    swap_free = int(line.split()[1])
            
            swap_used = swap_total - swap_free
            
            return {
                'total': swap_total * 1024,  # Convert to bytes
                'used': swap_used * 1024,
                'free': swap_free * 1024,
                'percent': (swap_used / swap_total * 100.0) if swap_total > 0 else 0.0,
            }
        except Exception as e:
            logging.debug(f"get_swap_info failed: {e}")
            return {'total': 0, 'used': 0, 'free': 0, 'percent': 0.0}
    
    def get_storage_info(self):
        """Get storage information for all mounted filesystems."""
        try:
            import shutil
            
            # Get list of mount points
            mounts = []
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        device = parts[0]
                        mountpoint = parts[1]
                        fstype = parts[2] if len(parts) > 2 else ''
                        
                        # Filter to relevant filesystems
                        if fstype in ['ext4', 'ext3', 'ext2', 'xfs', 'btrfs', 'vfat', 'ntfs', 'tmpfs']:
                            # Skip some system mounts
                            if mountpoint.startswith('/sys') or mountpoint.startswith('/proc'):
                                continue
                            if mountpoint.startswith('/dev') and mountpoint != '/dev':
                                continue
                            if mountpoint.startswith('/run') and mountpoint != '/run':
                                continue
                            
                            try:
                                usage = shutil.disk_usage(mountpoint)
                                mounts.append({
                                    'device': device,
                                    'mountpoint': mountpoint,
                                    'fstype': fstype,
                                    'total': usage.total,
                                    'used': usage.used,
                                    'free': usage.free,
                                    'percent': (usage.used / usage.total * 100.0) if usage.total > 0 else 0.0,
                                })
                            except Exception:
                                pass
            
            return mounts
        except Exception as e:
            logging.debug(f"get_storage_info failed: {e}")
            return []
    
    def get_network_stats(self):
        """Get network statistics for all interfaces."""
        try:
            net_stats = {}
            
            with open('/proc/net/dev', 'r') as f:
                lines = f.readlines()[2:]  # Skip header lines
            
            for line in lines:
                if ':' in line:
                    iface, data = line.split(':', 1)
                    iface = iface.strip()
                    parts = data.split()
                    
                    if len(parts) >= 16:
                        rx_bytes = int(parts[0])
                        rx_packets = int(parts[1])
                        tx_bytes = int(parts[8])
                        tx_packets = int(parts[9])
                        
                        net_stats[iface] = {
                            'rx_bytes': rx_bytes,
                            'rx_packets': rx_packets,
                            'tx_bytes': tx_bytes,
                            'tx_packets': tx_packets,
                        }
            
            # Calculate rates if we have previous data
            if self.last_net_stats:
                current_time = time.time()
                time_delta = current_time - self.last_update
                
                if time_delta > 0:
                    for iface, stats in net_stats.items():
                        if iface in self.last_net_stats:
                            prev = self.last_net_stats[iface]
                            stats['rx_rate'] = (stats['rx_bytes'] - prev['rx_bytes']) / time_delta
                            stats['tx_rate'] = (stats['tx_bytes'] - prev['tx_bytes']) / time_delta
                        else:
                            stats['rx_rate'] = 0.0
                            stats['tx_rate'] = 0.0
            else:
                for stats in net_stats.values():
                    stats['rx_rate'] = 0.0
                    stats['tx_rate'] = 0.0
            
            self.last_net_stats = net_stats
            self.last_update = time.time()
            
            return net_stats
        except Exception as e:
            logging.debug(f"get_network_stats failed: {e}")
            return {}
    
    def get_uptime(self):
        """Get system uptime in seconds."""
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.read().split()[0])
            return uptime_seconds
        except Exception as e:
            logging.debug(f"get_uptime failed: {e}")
            return 0.0
    
    def get_load_average(self):
        """Get system load average (1, 5, 15 minutes)."""
        try:
            with open('/proc/loadavg', 'r') as f:
                parts = f.read().split()
            return {
                '1min': float(parts[0]),
                '5min': float(parts[1]),
                '15min': float(parts[2]),
            }
        except Exception as e:
            logging.debug(f"get_load_average failed: {e}")
            return {'1min': 0.0, '5min': 0.0, '15min': 0.0}
    
    def format_bytes(self, bytes_value):
        """Format bytes to human-readable string."""
        value = float(bytes_value)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if value < 1024.0:
                return f"{value:.1f}{unit}"
            value /= 1024.0
        return f"{value:.1f}PB"
    
    def format_uptime(self, seconds):
        """Format uptime seconds to human-readable string."""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
