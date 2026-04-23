# -*- coding:utf-8 -*-
"""
Diagnostic to trace full Chromium initialization
"""
import sys
sys.path.insert(0, 'd:\\work\\solo-coder\\task\\20260422-drissionpage-3314-tab-lifecycle-race-fix\\repo\\DrissionPage')

print("=" * 70)
print("Tracing Full Chromium Initialization")
print("=" * 70)

# First, let's test with set_local_port (which worked in diagnostic)
print("\n[1] Test with set_local_port()")
print("-" * 70)

from DrissionPage import ChromiumOptions
from DrissionPage._base.chromium import Chromium

# Clean up any cached state
Chromium._BROWSERS.clear()
from DrissionPage._base.driver import BrowserDriver
BrowserDriver.BROWSERS.clear()
from DrissionPage._functions.tools import PortFinder
PortFinder.used_port.clear()

# Create options like the diagnostic did
co = ChromiumOptions(read_file=False)
co.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
co.set_argument('--headless=new')
co.set_argument('--disable-gpu')
co.set_argument('--no-sandbox')

# Find and set a port manually
from socket import socket, AF_INET, SOCK_STREAM
from random import randint

def find_port():
    for _ in range(100):
        port = randint(9600, 59600)
        s = socket(AF_INET, SOCK_STREAM)
        s.settimeout(0.1)
        try:
            result = s.connect_ex(('127.0.0.1', port))
            s.close()
            if result != 0:
                return port
        except:
            s.close()
    return 9600

test_port = find_port()
print(f"  Selected port: {test_port}")
co.set_local_port(test_port)

print(f"\n  Options before Chromium():")
print(f"    address: '{co.address}'")
print(f"    auto_port: {co.is_auto_port}")
print(f"    browser_path: '{co.browser_path}'")

# Now create Chromium instance
print(f"\n  Creating Chromium(co)...")
try:
    browser = Chromium(co)
    print(f"  Chromium created successfully!")
    print(f"    browser.id: {browser.id}")
    print(f"    browser.address: {browser.address}")
    print(f"    browser._ws_address: {browser._ws_address}")
    
    # Try to get a tab
    tab = browser.latest_tab
    print(f"\n  Tab created: tab_id={tab.tab_id}")
    
    # Try navigation
    tab.get('https://httpbin.org/get')
    print(f"  Navigation completed: title={tab.title}")
    
    # Cleanup
    browser.quit(force=True)
    print(f"\n  Browser quit successfully")
    
except Exception as e:
    print(f"  Chromium creation failed: {e}")
    import traceback
    traceback.print_exc()

# Now test with auto_port()
print("\n" + "=" * 70)
print("[2] Test with auto_port()")
print("=" * 70)

# Clean up again
Chromium._BROWSERS.clear()
BrowserDriver.BROWSERS.clear()
PortFinder.used_port.clear()

# Create options with auto_port
co2 = ChromiumOptions(read_file=False)
co2.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
co2.set_argument('--headless=new')
co2.set_argument('--disable-gpu')
co2.set_argument('--no-sandbox')

print(f"\n  Before auto_port():")
print(f"    address: '{co2.address}'")
print(f"    auto_port: {co2.is_auto_port}")

co2.auto_port()

print(f"\n  After auto_port():")
print(f"    address: '{co2.address}'")
print(f"    auto_port: {co2.is_auto_port}")
print(f"    ws_address: '{co2.ws_address}'")

# Now create Chromium instance
print(f"\n  Creating Chromium(co2)...")
try:
    browser2 = Chromium(co2)
    print(f"  Chromium created successfully!")
    print(f"    browser.id: {browser2.id}")
    print(f"    browser.address: {browser2.address}")
    print(f"    browser._ws_address: {browser2._ws_address}")
    
    # Try to get a tab
    tab2 = browser2.latest_tab
    print(f"\n  Tab created: tab_id={tab2.tab_id}")
    
    # Cleanup
    browser2.quit(force=True)
    print(f"\n  Browser quit successfully")
    
except Exception as e:
    print(f"  Chromium creation failed: {e}")
    import traceback
    traceback.print_exc()

# Let's also test using default config (read_file=True)
print("\n" + "=" * 70)
print("[3] Test with default config (read_file=True)")
print("=" * 70)

# Clean up
Chromium._BROWSERS.clear()
BrowserDriver.BROWSERS.clear()
PortFinder.used_port.clear()

# Check what default config gives us
co3 = ChromiumOptions(read_file=True)
print(f"\n  Default options:")
print(f"    address: '{co3.address}'")
print(f"    auto_port: {co3.is_auto_port}")
print(f"    browser_path: '{co3.browser_path}'")

# Check if port is in use
from DrissionPage._functions.tools import port_is_using
ip3, port3 = co3.address.split(':')
in_use3 = port_is_using(ip3, int(port3))
print(f"\n  Port {port3} is in use: {in_use3}")

# If port is not in use, we can't test (browser not running)
# Let's modify to use auto_port instead
if not in_use3:
    print(f"\n  Port {port3} not in use, switching to auto_port mode...")
    co3.auto_port()
    print(f"  After auto_port(): address='{co3.address}', auto_port={co3.is_auto_port}")

print(f"\n  Creating Chromium(co3)...")
try:
    browser3 = Chromium(co3)
    print(f"  Chromium created successfully!")
    print(f"    browser.id: {browser3.id}")
    print(f"    browser.address: {browser3.address}")
    
    # Cleanup
    browser3.quit(force=True)
    print(f"\n  Browser quit successfully")
    
except Exception as e:
    print(f"  Chromium creation failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("Diagnostic Complete")
print("=" * 70)
