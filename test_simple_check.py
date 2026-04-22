# -*- coding:utf-8 -*-
"""
Simple test to verify basic functionality
"""
import sys
sys.path.insert(0, 'd:\\work\\solo-coder\\task\\20260422-drissionpage-3314-tab-lifecycle-race-fix\\repo\\DrissionPage')

from time import sleep

print("Starting simple test...")

try:
    from DrissionPage import ChromiumOptions, Chromium
    
    co = ChromiumOptions(read_file=False)
    co.set_argument('--headless=new')
    co.set_argument('--disable-gpu')
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')
    co.auto_port()
    
    print(f"ChromiumOptions created: address={co.address}, auto_port={co.is_auto_port}")
    
    browser = Chromium(co)
    print(f"Browser created: id={browser.id}")
    
    tab = browser.latest_tab
    print(f"Tab created: tab_id={tab.tab_id}")
    
    # Test basic navigation
    tab.get('https://httpbin.org/get')
    print(f"Navigation completed, title={tab.title}")
    
    # Test listener start
    tab.listen.start('https://httpbin.org')
    print(f"Listener started, listening={tab.listen.listening}")
    
    tab.get('https://httpbin.org/headers')
    print(f"Second navigation completed")
    
    try:
        packet = tab.listen.wait(timeout=5)
        if packet:
            print(f"Received packet: tab_id={packet.tab_id}, url={packet.url}")
        else:
            print("No packet received")
    except Exception as e:
        print(f"Wait error: {e}")
    
    tab.listen.stop()
    print(f"Listener stopped")
    
    browser.quit()
    print("Test passed!")
    
except Exception as e:
    print(f"Test failed: {e}")
    import traceback
    traceback.print_exc()
