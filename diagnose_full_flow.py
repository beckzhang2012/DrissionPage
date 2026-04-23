# -*- coding:utf-8 -*-
"""
Diagnostic script to test full Chromium initialization flow
"""
import sys
sys.path.insert(0, 'd:\\work\\solo-coder\\task\\20260422-drissionpage-3314-tab-lifecycle-race-fix\\repo\\DrissionPage')

print("=" * 60)
print("Full Chromium Initialization Flow Diagnostic")
print("=" * 60)

# Let's trace the exact flow
from DrissionPage import ChromiumOptions
from DrissionPage._base.chromium import handle_options, run_browser
from DrissionPage._functions.browser import connect_browser, test_connect

# Step 1: Create options exactly like the tests
print("\nStep 1: Create ChromiumOptions exactly like tests do")
co = ChromiumOptions(read_file=False)
co.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
co.set_argument('--headless=new')
co.set_argument('--disable-gpu')
co.set_argument('--no-sandbox')
co.set_argument('--disable-dev-shm-usage')
co.auto_port()

print(f"  address: '{co.address}'")
print(f"  auto_port: {co.is_auto_port}")
print(f"  ws_address: '{co.ws_address}'")
print(f"  browser_path: '{co.browser_path}'")

# Step 2: Call handle_options
print("\nStep 2: Call handle_options")
opt = handle_options(co)
print(f"  After handle_options:")
print(f"    address: '{opt.address}'")
print(f"    auto_port: {opt.is_auto_port}")
print(f"    ws_address: '{opt.ws_address}'")
print(f"    user_data_path: '{opt.user_data_path}'")

# Step 3: Check if browser is already running on that port
print("\nStep 3: Check if port is already in use")
ip, port = opt.address.split(':')
print(f"  IP: {ip}, Port: {port}")

from DrissionPage._functions.tools import port_is_using
port_in_use = port_is_using(ip, port)
print(f"  Port is in use: {port_in_use}")

if port_in_use:
    can_connect = test_connect(ip, port)
    print(f"  Can connect to existing browser: {can_connect}")

# Step 4: Try to run browser
print("\nStep 4: Call run_browser")
try:
    is_headless, browser_id, is_exists, ws_only = run_browser(opt)
    print(f"  run_browser result:")
    print(f"    is_headless: {is_headless}")
    print(f"    browser_id: {browser_id}")
    print(f"    is_exists: {is_exists}")
    print(f"    ws_only: {ws_only}")
    
    # Now check what _ws_address would be
    if opt.ws_address:
        ws_address = opt.ws_address
    else:
        ws_address = f'ws://{opt.address}/devtools/browser/{browser_id}'
    print(f"    Calculated _ws_address: {ws_address}")
    
    # Step 5: Try to create BrowserDriver
    print("\nStep 5: Try to create BrowserDriver")
    from DrissionPage._base.driver import BrowserDriver
    
    try:
        driver = BrowserDriver(browser_id, ws_address, None)
        print(f"    BrowserDriver created successfully!")
        print(f"    is_running: {driver.is_running}")
        
        # Stop it
        driver.stop()
        print(f"    BrowserDriver stopped")
        
        # Step 6: Now try to create a full Chromium instance
        print("\nStep 6: Try to create full Chromium instance")
        from DrissionPage import Chromium
        
        # Create fresh options
        co2 = ChromiumOptions(read_file=False)
        co2.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
        co2.set_argument('--headless=new')
        co2.set_argument('--disable-gpu')
        co2.set_argument('--no-sandbox')
        co2.set_argument('--disable-dev-shm-usage')
        co2.auto_port()
        
        browser = Chromium(co2)
        print(f"    Chromium created successfully!")
        print(f"    browser.id: {browser.id}")
        print(f"    browser.address: {browser.address}")
        print(f"    browser._ws_address: {browser._ws_address}")
        
        # Get a tab
        tab = browser.latest_tab
        print(f"    tab.tab_id: {tab.tab_id}")
        
        # Try to navigate
        tab.get('https://httpbin.org/get')
        print(f"    Navigation completed, title: {tab.title}")
        
        # Test listener
        tab.listen.start('https://httpbin.org')
        print(f"    Listener started, listening: {tab.listen.listening}")
        
        tab.get('https://httpbin.org/headers')
        
        try:
            packet = tab.listen.wait(timeout=5)
            if packet:
                print(f"    Received packet: tab_id={packet.tab_id}, url={packet.url}")
            else:
                print(f"    No packet received")
        except Exception as e:
            print(f"    Wait error: {e}")
        
        tab.listen.stop()
        browser.quit()
        print(f"    Browser quit successfully!")
        
    except Exception as e:
        print(f"    BrowserDriver creation failed: {e}")
        import traceback
        traceback.print_exc()
        
except Exception as e:
    print(f"  run_browser failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Diagnostic Complete")
print("=" * 60)
