#!/usr/bin/python3
# -*- coding: UTF-8 -*-
"""
Tabbed UI system for system monitoring display.
Handles rendering multiple tabs and touch-based navigation.
"""

import logging
from PIL import Image, ImageDraw, ImageFont
from system_monitor import SystemMonitor

class Tab:
    """Base class for a tab in the UI."""
    
    def __init__(self, name, icon=None):
        self.name = name
        self.icon = icon
    
    def render(self, monitor: 'SystemMonitor', width: int, height: int) -> Image.Image:
        """Render this tab's content.
        
        Args:
            monitor: SystemMonitor instance to get system stats from
            width: Width of the display in pixels
            height: Height of the display in pixels
            
        Returns:
            PIL Image containing the rendered tab content
        """
        raise NotImplementedError()


class OverviewTab(Tab):
    """Overview tab showing CPU, memory, temperature summary."""
    
    def __init__(self):
        super().__init__("Overview", "📊")
    
    def render(self, monitor, width, height):
        img = Image.new('RGB', (width, height), (20, 20, 30))
        draw = ImageDraw.Draw(img)
        
        # Load fonts
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            label_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
            value_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        except Exception:
            title_font = ImageFont.load_default()
            label_font = ImageFont.load_default()
            value_font = ImageFont.load_default()
        
        y = 15
        
        # Title
        draw.text((width // 2, y), "System Overview", fill=(255, 255, 255), font=title_font, anchor="mt")
        y += 40
        
        # Get stats
        cpu_usage = monitor.get_cpu_usage()
        cpu_total = cpu_usage.get('cpu', 0.0)
        temp = monitor.get_cpu_temperature()
        mem_info = monitor.get_memory_info()
        load_avg = monitor.get_load_average()
        uptime = monitor.get_uptime()
        
        # CPU Usage
        draw.text((10, y), "CPU Usage:", fill=(180, 180, 200), font=label_font)
        self._draw_progress_bar(draw, 10, y + 25, width - 20, 20, cpu_total, (50, 150, 255))
        draw.text((width - 10, y + 25), f"{cpu_total:.1f}%", fill=(255, 255, 255), font=value_font, anchor="rm")
        y += 60
        
        # Temperature
        if temp is not None:
            draw.text((10, y), "Temperature:", fill=(180, 180, 200), font=label_font)
            temp_color = self._get_temp_color(temp)
            draw.text((width - 10, y), f"{temp:.1f}°C", fill=temp_color, font=value_font, anchor="rm")
            y += 35
        
        # Memory Usage
        draw.text((10, y), "Memory Usage:", fill=(180, 180, 200), font=label_font)
        mem_percent = mem_info['percent']
        self._draw_progress_bar(draw, 10, y + 25, width - 20, 20, mem_percent, (100, 200, 100))
        mem_text = f"{monitor.format_bytes(mem_info['used'])} / {monitor.format_bytes(mem_info['total'])}"
        draw.text((width - 10, y + 25), mem_text, fill=(255, 255, 255), font=label_font, anchor="rm")
        y += 60
        
        # Load Average
        draw.text((10, y), "Load Average:", fill=(180, 180, 200), font=label_font)
        load_text = f"{load_avg['1min']:.2f}, {load_avg['5min']:.2f}, {load_avg['15min']:.2f}"
        draw.text((width - 10, y), load_text, fill=(255, 255, 255), font=value_font, anchor="rm")
        y += 35
        
        # Uptime
        draw.text((10, y), "Uptime:", fill=(180, 180, 200), font=label_font)
        uptime_text = monitor.format_uptime(uptime)
        draw.text((width - 10, y), uptime_text, fill=(255, 255, 255), font=value_font, anchor="rm")
        
        return img
    
    def _draw_progress_bar(self, draw, x, y, width, height, percent, color):
        """Draw a progress bar."""
        # Background
        draw.rectangle([x, y, x + width, y + height], outline=(100, 100, 100), fill=(40, 40, 50))
        # Filled portion
        if percent > 0:
            filled_width = int(width * percent / 100.0)
            draw.rectangle([x, y, x + filled_width, y + height], fill=color)
    
    def _get_temp_color(self, temp):
        """Get color based on temperature."""
        if temp < 50:
            return (100, 255, 100)
        elif temp < 70:
            return (255, 255, 100)
        else:
            return (255, 100, 100)


class CPUTab(Tab):
    """CPU tab showing detailed CPU usage and per-core stats."""
    
    def __init__(self):
        super().__init__("CPU", "⚙️")
    
    def render(self, monitor, width, height):
        img = Image.new('RGB', (width, height), (20, 20, 30))
        draw = ImageDraw.Draw(img)
        
        # Load fonts
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            label_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
            value_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        except Exception:
            title_font = ImageFont.load_default()
            label_font = ImageFont.load_default()
            value_font = ImageFont.load_default()
        
        y = 15
        
        # Title
        draw.text((width // 2, y), "CPU Details", fill=(255, 255, 255), font=title_font, anchor="mt")
        y += 40
        
        # Get CPU stats
        cpu_usage = monitor.get_cpu_usage()
        load_avg = monitor.get_load_average()
        temp = monitor.get_cpu_temperature()
        
        # Overall CPU
        cpu_total = cpu_usage.get('cpu', 0.0)
        draw.text((10, y), f"Overall: {cpu_total:.1f}%", fill=(180, 180, 255), font=value_font)
        y += 30
        
        # Temperature
        if temp is not None:
            temp_color = (100, 255, 100) if temp < 70 else (255, 100, 100)
            draw.text((10, y), f"Temp: {temp:.1f}°C", fill=temp_color, font=value_font)
            y += 30
        
        # Load average
        draw.text((10, y), f"Load: {load_avg['1min']:.2f}", fill=(200, 200, 200), font=label_font)
        y += 30
        
        # Per-core usage
        draw.text((10, y), "Per-Core Usage:", fill=(180, 180, 200), font=label_font)
        y += 25
        
        # Filter to get only individual CPU cores (not the aggregate 'cpu' entry)
        # and sort them numerically by core number
        cores = [(k, v) for k, v in cpu_usage.items() if k.startswith('cpu') and k != 'cpu']
        cores.sort(key=lambda x: x[0])
        
        for core_name, usage in cores:
            if y > height - 40:
                break
            
            core_num = core_name[3:]  # Remove 'cpu' prefix
            draw.text((10, y), f"Core {core_num}:", fill=(150, 150, 170), font=label_font)
            
            # Draw mini progress bar
            bar_width = width - 100
            bar_height = 15
            bar_x = 80
            draw.rectangle([bar_x, y, bar_x + bar_width, y + bar_height], 
                          outline=(100, 100, 100), fill=(40, 40, 50))
            if usage > 0:
                filled = int(bar_width * usage / 100.0)
                color = self._get_cpu_color(usage)
                draw.rectangle([bar_x, y, bar_x + filled, y + bar_height], fill=color)
            
            draw.text((width - 10, y), f"{usage:.1f}%", fill=(255, 255, 255), font=label_font, anchor="rm")
            y += 22
        
        return img
    
    def _get_cpu_color(self, usage):
        """Get color based on CPU usage."""
        if usage < 50:
            return (50, 200, 50)
        elif usage < 80:
            return (255, 200, 50)
        else:
            return (255, 50, 50)


class MemoryTab(Tab):
    """Memory tab showing RAM and swap usage."""
    
    def __init__(self):
        super().__init__("Memory", "🧠")
    
    def render(self, monitor, width, height):
        img = Image.new('RGB', (width, height), (20, 20, 30))
        draw = ImageDraw.Draw(img)
        
        # Load fonts
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            label_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
            value_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        except Exception:
            title_font = ImageFont.load_default()
            label_font = ImageFont.load_default()
            value_font = ImageFont.load_default()
        
        y = 15
        
        # Title
        draw.text((width // 2, y), "Memory", fill=(255, 255, 255), font=title_font, anchor="mt")
        y += 40
        
        # Get memory stats
        mem_info = monitor.get_memory_info()
        swap_info = monitor.get_swap_info()
        
        # RAM section
        draw.text((10, y), "RAM Usage:", fill=(180, 180, 200), font=label_font)
        y += 30
        
        mem_percent = mem_info['percent']
        self._draw_large_progress_bar(draw, 10, y, width - 20, 30, mem_percent, (100, 200, 100))
        y += 40
        
        draw.text((10, y), f"Used: {monitor.format_bytes(mem_info['used'])}", 
                 fill=(200, 200, 200), font=label_font)
        y += 25
        draw.text((10, y), f"Available: {monitor.format_bytes(mem_info['available'])}", 
                 fill=(200, 200, 200), font=label_font)
        y += 25
        draw.text((10, y), f"Total: {monitor.format_bytes(mem_info['total'])}", 
                 fill=(200, 200, 200), font=label_font)
        y += 35
        
        # Buffers and cache
        draw.text((10, y), f"Buffers: {monitor.format_bytes(mem_info['buffers'])}", 
                 fill=(150, 150, 170), font=label_font)
        y += 25
        draw.text((10, y), f"Cached: {monitor.format_bytes(mem_info['cached'])}", 
                 fill=(150, 150, 170), font=label_font)
        y += 40
        
        # Swap section
        draw.text((10, y), "Swap Usage:", fill=(180, 180, 200), font=label_font)
        y += 30
        
        if swap_info['total'] > 0:
            swap_percent = swap_info['percent']
            self._draw_large_progress_bar(draw, 10, y, width - 20, 30, swap_percent, (200, 150, 100))
            y += 40
            
            draw.text((10, y), f"Used: {monitor.format_bytes(swap_info['used'])}", 
                     fill=(200, 200, 200), font=label_font)
            y += 25
            draw.text((10, y), f"Free: {monitor.format_bytes(swap_info['free'])}", 
                     fill=(200, 200, 200), font=label_font)
        else:
            draw.text((10, y), "No swap configured", fill=(150, 150, 150), font=label_font)
        
        return img
    
    def _draw_large_progress_bar(self, draw, x, y, width, height, percent, color):
        """Draw a large progress bar with percentage."""
        # Background
        draw.rectangle([x, y, x + width, y + height], outline=(100, 100, 100), fill=(40, 40, 50))
        # Filled portion
        if percent > 0:
            filled_width = int(width * percent / 100.0)
            draw.rectangle([x, y, x + filled_width, y + height], fill=color)
        # Percentage text
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        except Exception:
            font = ImageFont.load_default()
        draw.text((x + width // 2, y + height // 2), f"{percent:.1f}%", 
                 fill=(255, 255, 255), font=font, anchor="mm")


class StorageTab(Tab):
    """Storage tab showing disk usage for all mounted filesystems."""
    
    def __init__(self):
        super().__init__("Storage", "💾")
    
    def render(self, monitor, width, height):
        img = Image.new('RGB', (width, height), (20, 20, 30))
        draw = ImageDraw.Draw(img)
        
        # Load fonts
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            label_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
            value_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        except Exception:
            title_font = ImageFont.load_default()
            label_font = ImageFont.load_default()
            value_font = ImageFont.load_default()
        
        y = 15
        
        # Title
        draw.text((width // 2, y), "Storage", fill=(255, 255, 255), font=title_font, anchor="mt")
        y += 40
        
        # Get storage stats
        storage_info = monitor.get_storage_info()
        
        if not storage_info:
            draw.text((width // 2, height // 2), "No storage info available", 
                     fill=(150, 150, 150), font=label_font, anchor="mm")
            return img
        
        for mount in storage_info:
            if y > height - 60:
                break
            
            mountpoint = mount['mountpoint']
            # Truncate long mount points
            if len(mountpoint) > 20:
                mountpoint = mountpoint[:17] + "..."
            
            draw.text((10, y), mountpoint, fill=(180, 180, 255), font=label_font)
            y += 20
            
            # Usage bar
            percent = mount['percent']
            bar_width = width - 20
            bar_height = 20
            draw.rectangle([10, y, 10 + bar_width, y + bar_height], 
                          outline=(100, 100, 100), fill=(40, 40, 50))
            if percent > 0:
                filled = int(bar_width * percent / 100.0)
                color = self._get_storage_color(percent)
                draw.rectangle([10, y, 10 + filled, y + bar_height], fill=color)
            
            # Percentage text
            draw.text((width // 2, y + bar_height // 2), f"{percent:.1f}%", 
                     fill=(255, 255, 255), font=value_font, anchor="mm")
            y += 25
            
            # Size info
            used_text = f"{monitor.format_bytes(mount['used'])} / {monitor.format_bytes(mount['total'])}"
            draw.text((10, y), used_text, fill=(150, 150, 170), font=value_font)
            y += 25
        
        return img
    
    def _get_storage_color(self, percent):
        """Get color based on storage usage."""
        if percent < 70:
            return (100, 200, 255)
        elif percent < 90:
            return (255, 200, 50)
        else:
            return (255, 50, 50)


class NetworkTab(Tab):
    """Network tab showing network statistics."""
    
    def __init__(self):
        super().__init__("Network", "🌐")
    
    def render(self, monitor, width, height):
        img = Image.new('RGB', (width, height), (20, 20, 30))
        draw = ImageDraw.Draw(img)
        
        # Load fonts
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            label_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
            value_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        except Exception:
            title_font = ImageFont.load_default()
            label_font = ImageFont.load_default()
            value_font = ImageFont.load_default()
        
        y = 15
        
        # Title
        draw.text((width // 2, y), "Network", fill=(255, 255, 255), font=title_font, anchor="mt")
        y += 40
        
        # Get network stats
        net_stats = monitor.get_network_stats()
        
        if not net_stats:
            draw.text((width // 2, height // 2), "No network info available", 
                     fill=(150, 150, 150), font=label_font, anchor="mm")
            return img
        
        # Filter out loopback
        interfaces = [(k, v) for k, v in net_stats.items() if k != 'lo']
        
        for iface, stats in interfaces:
            if y > height - 80:
                break
            
            # Interface name
            draw.text((10, y), iface, fill=(180, 255, 180), font=label_font)
            y += 25
            
            # RX (download)
            rx_text = f"↓ {monitor.format_bytes(stats['rx_bytes'])}"
            draw.text((10, y), rx_text, fill=(100, 200, 255), font=value_font)
            if stats['rx_rate'] > 0:
                rate_text = f"({monitor.format_bytes(stats['rx_rate'])}/s)"
                draw.text((width - 10, y), rate_text, fill=(150, 150, 170), font=value_font, anchor="rm")
            y += 20
            
            # TX (upload)
            tx_text = f"↑ {monitor.format_bytes(stats['tx_bytes'])}"
            draw.text((10, y), tx_text, fill=(255, 200, 100), font=value_font)
            if stats['tx_rate'] > 0:
                rate_text = f"({monitor.format_bytes(stats['tx_rate'])}/s)"
                draw.text((width - 10, y), rate_text, fill=(150, 150, 170), font=value_font, anchor="rm")
            y += 30
        
        return img


class TabManager:
    """Manages multiple tabs and handles switching between them."""
    
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.monitor = SystemMonitor()
        
        # Create tabs
        self.tabs = [
            OverviewTab(),
            CPUTab(),
            MemoryTab(),
            StorageTab(),
            NetworkTab(),
        ]
        
        self.current_tab = 0
        self.tab_indicator_height = 30
        
    def get_current_tab(self):
        """Get the currently active tab."""
        return self.tabs[self.current_tab]
    
    def next_tab(self):
        """Switch to the next tab."""
        self.current_tab = (self.current_tab + 1) % len(self.tabs)
        logging.info(f"Switched to tab: {self.tabs[self.current_tab].name}")
    
    def previous_tab(self):
        """Switch to the previous tab."""
        self.current_tab = (self.current_tab - 1) % len(self.tabs)
        logging.info(f"Switched to tab: {self.tabs[self.current_tab].name}")
    
    def handle_touch(self, x, y):
        """Handle a touch event. Returns True if a tab switch occurred."""
        # Top portion switches to previous tab
        if y < 60:
            self.previous_tab()
            return True
        # Bottom portion switches to next tab
        elif y > self.height - 60:
            self.next_tab()
            return True
        return False
    
    def render(self):
        """Render the current tab with tab indicators."""
        # Get current tab content
        tab = self.tabs[self.current_tab]
        content_height = self.height - self.tab_indicator_height
        tab_img = tab.render(self.monitor, self.width, content_height)
        
        # Create final image with tab indicator
        img = Image.new('RGB', (self.width, self.height), (10, 10, 20))
        img.paste(tab_img, (0, 0))
        
        # Draw tab indicator at bottom
        self._draw_tab_indicator(img)
        
        return img
    
    def _draw_tab_indicator(self, img):
        """Draw tab indicator showing current tab and navigation hints."""
        draw = ImageDraw.Draw(img)
        
        y_start = self.height - self.tab_indicator_height
        
        # Background for indicator
        draw.rectangle([0, y_start, self.width, self.height], fill=(30, 30, 40))
        
        # Tab dots
        num_tabs = len(self.tabs)
        dot_spacing = min(40, self.width // (num_tabs + 1))
        start_x = (self.width - (num_tabs - 1) * dot_spacing) // 2
        
        for i in range(num_tabs):
            x = start_x + i * dot_spacing
            y = y_start + self.tab_indicator_height // 2
            
            if i == self.current_tab:
                # Current tab - larger filled circle
                draw.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(100, 150, 255))
            else:
                # Other tabs - smaller hollow circle
                draw.ellipse([x - 4, y - 4, x + 4, y + 4], outline=(100, 100, 120))
        
        # Tab name
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        except Exception:
            font = ImageFont.load_default()
        
        tab_name = self.tabs[self.current_tab].name
        draw.text((self.width // 2, y_start + 5), tab_name, 
                 fill=(180, 180, 200), font=font, anchor="mt")
