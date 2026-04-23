# -*- coding:utf-8 -*-
"""
Diagnostic script to trace handle_options execution
"""
import sys
sys.path.insert(0, 'd:\\work\\solo-coder\\task\\20260422-drissionpage-3314-tab-lifecycle-race-fix\\repo\\DrissionPage')

print("=" * 60)
print("Diagnose handle_options flow")
print("=" * 60)

# Test: Manually trace what happens
from DrissionPage import ChromiumOptions
from DrissionPage._functions.tools import PortFinder

print("\nStep 1: Create ChromiumOptions with read_file=False")
co = ChromiumOptions(read_file=False)
print(f"  address: '{co.address}'")
print(f"  auto_port: {co.is_auto_port}")
print(f"  browser_path: '{co.browser_path}'")
print(f"  tmp_path: '{co.tmp_path}'")

print("\nStep 2: Set browser path manually (like test does)")
co.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
print(f"  browser_path: '{co.browser_path}'")

print("\nStep 3: Set headless mode")
co.set_argument('--headless=new')
co.set_argument('--disable-gpu')
co.set_argument('--no-sandbox')
co.set_argument('--disable-dev-shm-usage')
print(f"  arguments: {co.arguments}")

print("\nStep 4: Call auto_port()")
print(f"  Before - address: '{co.address}', auto_port: {co.is_auto_port}")
co.auto_port()
print(f"  After - address: '{co.address}', auto_port: {co.is_auto_port}")

print("\nStep 5: Manually simulate what handle_options does")
if co.is_auto_port:
    print(f"  is_auto_port is truthy: {bool(co.is_auto_port)}")
    print(f"  auto_port value: {co.is_auto_port}")
    print(f"  tmp_path: '{co.tmp_path}'")
    
    # Simulate PortFinder
    pf = PortFinder(co.tmp_path)
    print(f"  PortFinder tmp_dir: {pf.tmp_dir}")
    
    port, path = pf.get_port(co.is_auto_port)
    print(f"  Allocated port: {port}")
    print(f"  Data path: {path}")
    
    # Simulate setting address
    co._address = f'127.0.0.1:{port}'
    co.set_user_data_path(path)
    print(f"  After manual handle_options:")
    print(f"    address: '{co.address}'")
    print(f"    user_data_path: '{co.user_data_path}'")
else:
    print("  is_auto_port is falsy, skipping port allocation")

print("\nStep 6: Check if we can create Chromium with these options")
print(f"  Final options:")
print(f"    address: '{co.address}'")
print(f"    auto_port: {co.is_auto_port}")
print(f"    browser_path: '{co.browser_path}'")
print(f"    user_data_path: '{co.user_data_path}'")

# Now let's compare with what test_tab_lifecycle_race.py does
print("\n" + "=" * 60)
print("Comparing with create_test_options() flow")
print("=" * 60)

# Replicate create_test_options exactly
def create_test_options_diagnose():
    from DrissionPage import ChromiumOptions
    
    co = ChromiumOptions(read_file=False)
    print(f"  After ChromiumOptions(read_file=False):")
    print(f"    address: '{co.address}'")
    print(f"    auto_port: {co.is_auto_port}")
    print(f"    browser_path: '{co.browser_path}'")
    
    co.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    print(f"\n  After set_browser_path:")
    print(f"    browser_path: '{co.browser_path}'")
    
    co.set_argument('--headless=new')
    co.set_argument('--disable-gpu')
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')
    
    co.auto_port()
    print(f"\n  After auto_port():")
    print(f"    address: '{co.address}'")
    print(f"    auto_port: {co.is_auto_port}")
    
    return co

co2 = create_test_options_diagnose()

print("\n" + "=" * 60)
print("The issue:")
print("=" * 60)
print("""
Problem analysis:
1. auto_port() sets _address to '' and _auto_port to (9600, 59600)
2. handle_options() in chromium.py should check is_auto_port and allocate a port
3. But at the time Chromium(co) is created, co.address is already ''
4. The question is: does handle_options() get called and does it set _address?

Let me check the actual Chromium.__new__ flow by looking at the code:
- Chromium.__new__ calls handle_options(addr_or_opts) FIRST
- Then calls run_browser(opt)

So handle_options should be modifying the ChromiumOptions object.
""")

# Let's actually check what handle_options does
print("\nStep 7: Directly inspect handle_options behavior")
from DrissionPage._base.chromium import handle_options

print(f"\n  Before handle_options:")
print(f"    co2.address: '{co2.address}'")
print(f"    co2.is_auto_port: {co2.is_auto_port}")

# Call handle_options directly
result = handle_options(co2)

print(f"\n  After handle_options:")
print(f"    co2.address: '{co2.address}'")
print(f"    co2.is_auto_port: {co2.is_auto_port}")
print(f"    result.address: '{result.address}'")
print(f"    result.is_auto_port: {result.is_auto_port}")
print(f"    result.user_data_path: '{result.user_data_path}'")

print("\n" + "=" * 60)
print("Diagnostic Complete")
print("=" * 60)
