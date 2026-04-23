# -*- coding:utf-8 -*-
"""
Diagnostic script to test basic Chromium functionality
"""
import sys
sys.path.insert(0, 'd:\\work\\solo-coder\\task\\20260422-drissionpage-3314-tab-lifecycle-race-fix\\repo\\DrissionPage')

print("=" * 60)
print("Diagnostic Test")
print("=" * 60)

# Test 1: Check ChromiumOptions with default settings
print("\nTest 1: ChromiumOptions with read_file=True (default)")
try:
    from DrissionPage import ChromiumOptions
    co = ChromiumOptions()
    print(f"  address: {co.address}")
    print(f"  auto_port: {co.is_auto_port}")
    print(f"  browser_path: {co.browser_path}")
    print(f"  arguments: {co.arguments}")
except Exception as e:
    print(f"  Error: {e}")

# Test 2: Check ChromiumOptions with read_file=False
print("\nTest 2: ChromiumOptions with read_file=False")
try:
    co2 = ChromiumOptions(read_file=False)
    print(f"  address: {co2.address}")
    print(f"  auto_port: {co2.is_auto_port}")
    print(f"  browser_path: {co2.browser_path}")
    print(f"  tmp_path: {co2.tmp_path}")
except Exception as e:
    print(f"  Error: {e}")

# Test 3: Check auto_port effect
print("\nTest 3: After calling auto_port()")
try:
    co3 = ChromiumOptions(read_file=False)
    print(f"  Before auto_port: address={co3.address}, auto_port={co3.is_auto_port}")
    co3.auto_port()
    print(f"  After auto_port: address={co3.address}, auto_port={co3.is_auto_port}")
except Exception as e:
    print(f"  Error: {e}")

# Test 4: Test PortFinder
print("\nTest 4: PortFinder")
try:
    from DrissionPage._functions.tools import PortFinder
    pf = PortFinder()
    print(f"  tmp_dir: {pf.tmp_dir}")
    port, path = pf.get_port((9600, 9700))
    print(f"  Allocated port: {port}")
    print(f"  Data path: {path}")
except Exception as e:
    print(f"  Error: {e}")
    import traceback
    traceback.print_exc()

# Test 5: Try to find Chrome path
print("\nTest 5: Finding Chrome path")
try:
    from platform import system
    from pathlib import Path
    
    sys_name = system().lower()
    print(f"  System: {sys_name}")
    
    if sys_name == 'windows':
        possible_paths = [
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
            str(Path.home() / r'AppData\Local\Google\Chrome\Application\chrome.exe'),
        ]
        
        for p in possible_paths:
            exists = Path(p).exists()
            print(f"  {p}: exists={exists}")
            
        # Try registry
        try:
            from winreg import OpenKey, EnumValue, CloseKey, HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE, KEY_READ
            for root in [HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE]:
                try:
                    key = OpenKey(root, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe', 
                                  reserved=0, access=KEY_READ)
                    k = EnumValue(key, 0)
                    CloseKey(key)
                    print(f"  Registry path: {k[1]}, exists={Path(k[1]).exists() if k[1] else False}")
                except Exception as e:
                    print(f"  Registry error ({root}): {e}")
        except Exception as e:
            print(f"  Registry access error: {e}")
except Exception as e:
    print(f"  Error: {e}")

print("\n" + "=" * 60)
print("Diagnostic Complete")
print("=" * 60)
