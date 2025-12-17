#!/usr/bin/env python3
"""
Test script to verify the system monitoring tabs work without hardware.
Creates test images for each tab to verify rendering logic.
"""

import sys
import logging
from PIL import Image
from system_monitor import SystemMonitor
from ui_tabs import TabManager

logging.basicConfig(level=logging.INFO)

def test_tabs():
    """Test rendering all tabs and save as images."""
    
    print("Testing tab rendering...")
    
    # Create tab manager
    width, height = 320, 480
    tab_manager = TabManager(width, height)
    
    # Render each tab
    for i in range(len(tab_manager.tabs)):
        tab_manager.current_tab = i
        tab_name = tab_manager.tabs[i].name
        
        print(f"Rendering tab {i+1}/{len(tab_manager.tabs)}: {tab_name}")
        
        try:
            img = tab_manager.render()
            filename = f"test_tab_{i}_{tab_name.lower().replace(' ', '_')}.png"
            img.save(filename)
            print(f"  Saved to {filename}")
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    print("\nTest complete!")
    
    # Test touch handling
    print("\nTesting touch handling...")
    print(f"Current tab: {tab_manager.tabs[tab_manager.current_tab].name}")
    
    # Test top touch (previous tab)
    if tab_manager.handle_touch(160, 30):
        print(f"Top touch -> Previous tab: {tab_manager.tabs[tab_manager.current_tab].name}")
    
    # Test bottom touch (next tab)
    if tab_manager.handle_touch(160, 450):
        print(f"Bottom touch -> Next tab: {tab_manager.tabs[tab_manager.current_tab].name}")
    
    # Test middle touch (no change)
    if not tab_manager.handle_touch(160, 240):
        print(f"Middle touch -> No change: {tab_manager.tabs[tab_manager.current_tab].name}")

if __name__ == "__main__":
    test_tabs()
