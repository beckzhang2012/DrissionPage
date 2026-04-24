# -*- coding:utf-8 -*-
"""
最简测试脚本：验证核心资源泄漏问题
"""
import threading
import time

from DrissionPage import ChromiumPage


def get_thread_count():
    return threading.active_count()


def test_listener_in_all_drivers():
    """验证 Listener 的 Driver 是否在 browser._all_drivers 中"""
    print("=" * 60)
    print("测试: Listener Driver 是否在 browser._all_drivers 中")
    print("=" * 60)
    
    page = ChromiumPage()
    browser = page.browser
    
    print(f"\n初始 _all_drivers: {list(browser._all_drivers.keys())}")
    
    tab = browser.new_tab()
    tab_id = tab.tab_id
    
    print(f"\n创建 tab 后:")
    print(f"  tab_id: {tab_id}")
    print(f"  _all_drivers: {list(browser._all_drivers.keys())}")
    print(f"  _all_drivers[{tab_id}]: {len(browser._all_drivers.get(tab_id, set()))} 个 Driver")
    
    tab.listen.start('https://example.com')
    
    print(f"\n启动 Listener 后:")
    print(f"  listener.listening: {tab.listen.listening}")
    print(f"  listener._driver: {tab.listen._driver}")
    if tab.listen._driver:
        listener_driver_id = id(tab.listen._driver)
        print(f"  listener._driver ID: {listener_driver_id}")
        print(f"  _all_drivers[{tab_id}]: {len(browser._all_drivers.get(tab_id, set()))} 个 Driver")
        
        all_drivers_for_tab = browser._all_drivers.get(tab_id, set())
        found = False
        for d in all_drivers_for_tab:
            print(f"    - Driver ID: {id(d)}, is_running: {d.is_running}")
            if id(d) == listener_driver_id:
                found = True
        print(f"  Listener Driver 在 _all_drivers 中: {found}")
    
    tab.close()
    time.sleep(0.5)
    
    print(f"\n关闭 tab 后:")
    print(f"  _all_drivers: {list(browser._all_drivers.keys())}")
    print(f"  tab_id in _all_drivers: {tab_id in browser._all_drivers}")
    
    page.quit()
    return True


if __name__ == '__main__':
    test_listener_in_all_drivers()
