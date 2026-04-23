# -*- coding:utf-8 -*-
"""
Detailed diagnostic for Chromium initialization
"""
import sys
sys.path.insert(0, 'd:\\work\\solo-coder\\task\\20260422-drissionpage-3314-tab-lifecycle-race-fix\\repo\\DrissionPage')

print("=" * 70)
print("Detailed Chromium Initialization Diagnostic")
print("=" * 70)

# First, let's check what the default configuration gives us
print("\n[1] Checking ChromiumOptions default behavior")
print("-" * 70)

from DrissionPage import ChromiumOptions

# Test 1: read_file=True (default)
print("\n--- Test 1a: ChromiumOptions(read_file=True) ---")
co1 = ChromiumOptions(read_file=True)
print(f"  address: '{co1.address}'")
print(f"  auto_port: {co1.is_auto_port}")
print(f"  browser_path: '{co1.browser_path}'")
print(f"  ws_address: '{co1.ws_address}'")
print(f"  arguments: {co1.arguments[:3]}...")

# Test 2: read_file=False
print("\n--- Test 1b: ChromiumOptions(read_file=False) ---")
co2 = ChromiumOptions(read_file=False)
print(f"  address: '{co2.address}'")
print(f"  auto_port: {co2.is_auto_port}")
print(f"  browser_path: '{co2.browser_path}'")
print(f"  ws_address: '{co2.ws_address}'")

# Test 3: read_file=False + set_browser_path + set_local_port
print("\n--- Test 1c: ChromiumOptions(read_file=False) with manual config ---")
co3 = ChromiumOptions(read_file=False)
co3.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
co3.set_argument('--headless=new')
co3.set_argument('--disable-gpu')
co3.set_argument('--no-sandbox')

# Find a port
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
co3.set_local_port(test_port)

print(f"  After set_local_port({test_port}):")
print(f"    address: '{co3.address}'")
print(f"    auto_port: {co3.is_auto_port}")
print(f"    browser_path: '{co3.browser_path}'")
print(f"    ws_address: '{co3.ws_address}'")

# Now let's trace handle_options
print("\n[2] Tracing handle_options")
print("-" * 70)

from DrissionPage._base.chromium import handle_options

print("\n--- Calling handle_options(co3) ---")
opt = handle_options(co3)
print(f"  After handle_options:")
print(f"    address: '{opt.address}'")
print(f"    auto_port: {opt.is_auto_port}")
print(f"    browser_path: '{opt.browser_path}'")
print(f"    user_data_path: '{opt.user_data_path}'")

# Now let's trace run_browser
print("\n[3] Tracing run_browser")
print("-" * 70)

from DrissionPage._base.chromium import run_browser
from DrissionPage._functions.browser import connect_browser, test_connect

print("\n--- Checking port status before run_browser ---")
ip, port = opt.address.split(':')
print(f"  IP: {ip}, Port: {port}")

from DrissionPage._functions.tools import port_is_using
in_use = port_is_using(ip, port)
print(f"  Port is in use: {in_use}")

if in_use:
    can_connect = test_connect(ip, port)
    print(f"  Can connect to existing browser: {can_connect}")
else:
    print(f"  Port is free, will start new browser")

print("\n--- Calling connect_browser(opt) ---")
try:
    # connect_browser returns True if using existing browser, False if started new one
    is_existing = connect_browser(opt)
    print(f"  connect_browser returned: is_existing={is_existing}")
except Exception as e:
    print(f"  connect_browser failed: {e}")
    import traceback
    traceback.print_exc()

# Check if browser is now running
print("\n--- Checking if browser is now running ---")
in_use_after = port_is_using(ip, port)
print(f"  Port is in use: {in_use_after}")

if in_use_after:
    can_connect_after = test_connect(ip, port)
    print(f"  Can connect: {can_connect_after}")
    
    # Try to get /json/version
    if can_connect_after:
        print("\n--- Trying to get /json/version ---")
        from requests import Session
        try:
            s = Session()
            s.trust_env = False
            s.keep_alive = False
            r = s.get(f'http://{opt.address}/json/version', timeout=5, headers={'Connection': 'close'})
            print(f"  Status code: {r.status_code}")
            print(f"  Response: {r.text}")
            
            json_data = r.json()
            print(f"\n  Parsed JSON:")
            for k, v in json_data.items():
                print(f"    {k}: {v}")
            
            # Extract browser_id
            ws_url = json_data.get('webSocketDebuggerUrl', '')
            print(f"\n  webSocketDebuggerUrl: '{ws_url}'")
            if ws_url:
                browser_id = ws_url.split('/')[-1]
                print(f"  Extracted browser_id: '{browser_id}'")
                
                # Build _ws_address
                ws_address = f'ws://{opt.address}/devtools/browser/{browser_id}'
                print(f"  Calculated _ws_address: '{ws_address}'")
            
            r.close()
            s.close()
        except Exception as e:
            print(f"  Failed to get /json/version: {e}")
            import traceback
            traceback.print_exc()

# Now let's call run_browser properly
print("\n--- Calling run_browser(opt) ---")
try:
    is_headless, browser_id, is_exists, ws_only = run_browser(opt)
    print(f"  run_browser result:")
    print(f"    is_headless: {is_headless}")
    print(f"    browser_id: '{browser_id}'")
    print(f"    is_exists: {is_exists}")
    print(f"    ws_only: {ws_only}")
    
    # Calculate what _ws_address would be
    if opt.ws_address:
        final_ws_address = opt.ws_address
    else:
        final_ws_address = f'ws://{opt.address}/devtools/browser/{browser_id}'
    print(f"    Final _ws_address: '{final_ws_address}'")
    
    # Now try to create BrowserDriver
    print("\n[4] Testing BrowserDriver creation")
    print("-" * 70)
    
    from DrissionPage._base.driver import BrowserDriver
    
    print(f"\n--- Creating BrowserDriver('{browser_id}', '{final_ws_address}', None) ---")
    try:
        driver = BrowserDriver(browser_id, final_ws_address, None)
        print(f"  BrowserDriver created successfully!")
        print(f"  driver.is_running: {driver.is_running}")
        print(f"  driver.id: {driver.id}")
        print(f"  driver.address: {driver.address}")
        
        # Try a simple CDP command
        print("\n--- Trying simple CDP command ---")
        try:
            result = driver.run('Browser.getVersion')
            if 'error' not in result:
                print(f"  Browser.getVersion succeeded: {result.get('product', 'N/A')}")
            else:
                print(f"  Browser.getVersion failed: {result}")
        except Exception as e:
            print(f"  CDP command failed: {e}")
        
        # Stop the driver
        print("\n--- Stopping driver ---")
        driver.stop()
        print(f"  After stop: driver.is_running = {driver.is_running}")
        
    except Exception as e:
        print(f"  BrowserDriver creation failed: {e}")
        import traceback
        traceback.print_exc()
        
except Exception as e:
    print(f"  run_browser failed: {e}")
    import traceback
    traceback.print_exc()

# Cleanup
print("\n[5] Cleanup")
print("-" * 70)

# Try to close the browser gracefully
try:
    from requests import Session
    s = Session()
    s.trust_env = False
    s.keep_alive = False
    
    # First check if browser is still accessible
    r = s.get(f'http://{opt.address}/json/version', timeout=2, headers={'Connection': 'close'})
    if r.status_code == 200:
        print(f"  Browser still running at {opt.address}")
        
        # Try to close using CDP via WebSocket
        try:
            # Create a new driver to close the browser
            from DrissionPage._base.driver import Driver
            d = Driver(browser_id, final_ws_address, None)
            d.run('Browser.close')
            d.stop()
            print(f"  Browser closed via CDP")
        except Exception as e:
            print(f"  Failed to close browser via CDP: {e}")
    
    r.close()
    s.close()
except Exception as e:
    print(f"  Cleanup: {e}")

print("\n" + "=" * 70)
print("Diagnostic Complete")
print("=" * 70)
