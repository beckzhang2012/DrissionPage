# -*- coding:utf-8 -*-
"""
Test if --headless=new is causing the 404 error
"""
import sys
sys.path.insert(0, 'd:\\work\\solo-coder\\task\\20260422-drissionpage-3314-tab-lifecycle-race-fix\\repo\\DrissionPage')

print("=" * 70)
print("Testing --headless=new effect")
print("=" * 70)

# Clean up first
from DrissionPage._base.chromium import Chromium
from DrissionPage._base.driver import BrowserDriver
from DrissionPage._functions.tools import PortFinder

Chromium._BROWSERS.clear()
BrowserDriver.BROWSERS.clear()
PortFinder.used_port.clear()

# Test 1: read_file=True + auto_port + NO --headless=new
print("\n[Test 1] read_file=True + auto_port (no --headless)")
print("-" * 70)

from DrissionPage import ChromiumOptions

co1 = ChromiumOptions(read_file=True)
co1.auto_port()

print(f"  Options:")
print(f"    address: '{co1.address}'")
print(f"    auto_port: {co1.is_auto_port}")
print(f"    browser_path: '{co1.browser_path}'")
print(f"    arguments: {co1.arguments}")

try:
    browser1 = Chromium(co1)
    print(f"\n  Chromium created successfully!")
    print(f"    browser.id: {browser1.id}")
    print(f"    browser.address: {browser1.address}")
    
    # Try to get a tab
    tab1 = browser1.latest_tab
    print(f"  Tab created: tab_id={tab1.tab_id}")
    
    # Cleanup
    browser1.quit(force=True)
    print(f"  Browser quit successfully")
    
except Exception as e:
    print(f"\n  Chromium creation failed: {e}")
    import traceback
    traceback.print_exc()

# Clean up
Chromium._BROWSERS.clear()
BrowserDriver.BROWSERS.clear()
PortFinder.used_port.clear()

# Test 2: read_file=True + auto_port + --headless=new
print("\n" + "=" * 70)
print("[Test 2] read_file=True + auto_port + --headless=new")
print("=" * 70)

co2 = ChromiumOptions(read_file=True)
co2.auto_port()
co2.set_argument('--headless=new')
co2.set_argument('--disable-gpu')
co2.set_argument('--no-sandbox')

print(f"  Options:")
print(f"    address: '{co2.address}'")
print(f"    auto_port: {co2.is_auto_port}")
print(f"    browser_path: '{co2.browser_path}'")
print(f"    arguments: {co2.arguments}")

try:
    browser2 = Chromium(co2)
    print(f"\n  Chromium created successfully!")
    print(f"    browser.id: {browser2.id}")
    print(f"    browser.address: {browser2.address}")
    
    # Try to get a tab
    tab2 = browser2.latest_tab
    print(f"  Tab created: tab_id={tab2.tab_id}")
    
    # Cleanup
    browser2.quit(force=True)
    print(f"  Browser quit successfully")
    
except Exception as e:
    print(f"\n  Chromium creation failed: {e}")
    import traceback
    traceback.print_exc()

# Clean up
Chromium._BROWSERS.clear()
BrowserDriver.BROWSERS.clear()
PortFinder.used_port.clear()

# Test 3: read_file=False + auto_port + same as default configs
print("\n" + "=" * 70)
print("[Test 3] read_file=False + auto_port + default arguments (from configs)")
print("=" * 70)

co3 = ChromiumOptions(read_file=False)
co3.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
co3.auto_port()

# Add all default arguments from configs.ini
co3.set_argument('--no-default-browser-check')
co3.set_argument('--disable-suggestions-ui')
co3.set_argument('--no-first-run')
co3.set_argument('--disable-infobars')
co3.set_argument('--disable-popup-blocking')
co3.set_argument('--hide-crash-restore-bubble')
co3.set_argument('--disable-features=PrivacySandboxSettings4')

# Also set user-data-dir like configs does
co3.set_argument(r'--user-data-dir=D:\Chrome\User Data')

print(f"  Options:")
print(f"    address: '{co3.address}'")
print(f"    auto_port: {co3.is_auto_port}")
print(f"    browser_path: '{co3.browser_path}'")
print(f"    arguments: {co3.arguments}")

try:
    browser3 = Chromium(co3)
    print(f"\n  Chromium created successfully!")
    print(f"    browser.id: {browser3.id}")
    print(f"    browser.address: {browser3.address}")
    
    # Try to get a tab
    tab3 = browser3.latest_tab
    print(f"  Tab created: tab_id={tab3.tab_id}")
    
    # Cleanup
    browser3.quit(force=True)
    print(f"  Browser quit successfully")
    
except Exception as e:
    print(f"\n  Chromium creation failed: {e}")
    import traceback
    traceback.print_exc()

# Clean up
Chromium._BROWSERS.clear()
BrowserDriver.BROWSERS.clear()
PortFinder.used_port.clear()

# Test 4: read_file=False + auto_port + default arguments + --headless=new
print("\n" + "=" * 70)
print("[Test 4] read_file=False + auto_port + default arguments + --headless=new")
print("=" * 70)

co4 = ChromiumOptions(read_file=False)
co4.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
co4.auto_port()

# Add all default arguments from configs.ini
co4.set_argument('--no-default-browser-check')
co4.set_argument('--disable-suggestions-ui')
co4.set_argument('--no-first-run')
co4.set_argument('--disable-infobars')
co4.set_argument('--disable-popup-blocking')
co4.set_argument('--hide-crash-restore-bubble')
co4.set_argument('--disable-features=PrivacySandboxSettings4')

# Also set user-data-dir like configs does
co4.set_argument(r'--user-data-dir=D:\Chrome\User Data')

# Add headless
co4.set_argument('--headless=new')
co4.set_argument('--disable-gpu')
co4.set_argument('--no-sandbox')

print(f"  Options:")
print(f"    address: '{co4.address}'")
print(f"    auto_port: {co4.is_auto_port}")
print(f"    browser_path: '{co4.browser_path}'")
print(f"    arguments: {co4.arguments}")

try:
    browser4 = Chromium(co4)
    print(f"\n  Chromium created successfully!")
    print(f"    browser.id: {browser4.id}")
    print(f"    browser.address: {browser4.address}")
    
    # Try to get a tab
    tab4 = browser4.latest_tab
    print(f"  Tab created: tab_id={tab4.tab_id}")
    
    # Cleanup
    browser4.quit(force=True)
    print(f"  Browser quit successfully")
    
except Exception as e:
    print(f"\n  Chromium creation failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("Test Complete")
print("=" * 70)
