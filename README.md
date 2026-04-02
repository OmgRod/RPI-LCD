# RPI-LCD System Monitor

A system monitoring display for Raspberry Pi with a 320x480 capacitive touchscreen LCD (Waveshare 2.5" ST7796).

## Features

This application displays real-time system information on a vertical LCD display with multiple tabbed views:

The screensaver tab now uses low-motion random squares with slow drift, darker colors, smooth transitions, capped frame pacing, and periodic reset pulses to reduce static panel stress during always-on use.
Tab switching is now restricted to the bottom navigation dots, with a brief stable press required so stray touches do not flip tabs.

### Tabs

1. **Overview** - System summary with CPU usage, temperature, memory, load average, and uptime
2. **CPU** - Detailed CPU usage with per-core statistics
3. **Memory** - RAM and swap usage with detailed breakdowns
4. **Storage** - Disk usage for all mounted filesystems
5. **Network** - Network interface statistics with RX/TX data
6. **Terminal** - Live shell tab with wrapped scrollback and monospace rendering

### Navigation

- **Tap the top portion** of the screen (top ~60 pixels) to switch to the previous tab
- **Tap and hold the bottom tab dots** to switch directly to a tab
- Touches outside the dots do not change tabs
- The terminal tab accepts keyboard input when the app is started from an interactive terminal or tmux session
- The current tab is indicated by the filled dot in the tab indicator at the bottom

## Hardware

- Raspberry Pi (any model with GPIO support)
- Waveshare 2.5" Capacitive Touch LCD (320x480, ST7796 driver, FT6336U touch controller)
- Display is designed to be used in **portrait orientation**

## Installation

1. Clone this repository
2. Install dependencies:

   ```bash
   pip3 install Pillow numpy spidev gpiozero RPi.GPIO smbus
   ```

3. Enable SPI and I2C interfaces:

   ```bash
   sudo raspi-config
   # Navigate to: Interface Options -> SPI -> Enable
   # Navigate to: Interface Options -> I2C -> Enable
   ```

4. Run the monitoring display:

   ```bash
   sudo python3 main.py
   ```

## Running as a Service

To run the monitoring display automatically on boot:

```bash
sudo ./install_service.sh
```

This will install and start a systemd service that runs the monitoring display.

## Testing

You can test the UI rendering without hardware:

```bash
python3 display_test.py
```

This will generate PNG images of all tabs for visual verification.

## Files

- `main.py` - Main application entry point
- `system_monitor.py` - System statistics gathering module
- `ui_tabs.py` - Tabbed UI system and tab implementations
- `screensaver_animation.py` - Low-motion screensaver animation engine
- `screensaver_tab.py` - Screensaver tab wrapper
- `display_driver.py` - ST7796 LCD driver
- `touch_controller.py` - FT6336U touch controller driver

## License

See repository license file.
