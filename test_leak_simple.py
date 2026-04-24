# -*- coding:utf-8 -*-
"""
简化版资源泄漏验证脚本
快速验证核心问题
"""
import threading
import time

from DrissionPage import ChromiumPage


def get_thread_count():
    return threading.active_count()


def get_thread_names():
    return [t.name for t in threading.enumerate()]


def test_listener_driver_leak():
    """验证 Listener 的 driver 是否在 tab 关闭时被正确清理"""
    print("=" * 60)
    print("测试: Listener Driver 资源泄漏验证")
    print("=" * 60)
    
    page = ChromiumPage()
    browser = page.browser
    
    print(f"\n初始状态:")
    print(f"  线程数: {get_thread_count()}")
    print(f"  线程名: {get_thread_names()}")
    print(f"  browser._all_drivers: {list(browser._all_drivers.keys())}")
    
    initial_threads = get_thread_count()
    
    tab = browser.new_tab()
    tab_id = tab.tab_id
    
    print(f"\n创建新 tab 后:")
    print(f"  tab_id: {tab_id}")
    print(f"  线程数: {get_thread_count()}")
    print(f"  browser._all_drivers: {list(browser._all_drivers.keys())}")
    
    tab.listen.start('https://example.com')
    
    print(f"\n启动 Listener 后:")
    print(f"  listener.listening: {tab.listen.listening}")
    print(f"  listener._driver: {tab.listen._driver}")
    print(f"  listener._driver.is_running: {tab.listen._driver.is_running if tab.listen._driver else None}")
    print(f"  线程数: {get_thread_count()}")
    print(f"  browser._all_drivers: {list(browser._all_drivers.keys())}")
    
    if tab.listen._driver:
        listener_driver_id = id(tab.listen._driver)
        print(f"  Listener Driver ID: {listener_driver_id}")
        
        all_drivers_for_tab = browser._all_drivers.get(tab_id, set())
        print(f"  browser._all_drivers[{tab_id}] 中的 Driver:")
        for d in all_drivers_for_tab:
            print(f"    - {id(d)} (is_running: {d.is_running})")
        
        listener_in_all_drivers = any(id(d) == listener_driver_id for d in all_drivers_for_tab)
        print(f"  Listener Driver 是否在 browser._all_drivers 中: {listener_in_all_drivers}")
    
    tab.listen.stop()
    
    print(f"\n停止 Listener 后:")
    print(f"  listener.listening: {tab.listen.listening}")
    print(f"  listener._driver: {tab.listen._driver}")
    print(f"  线程数: {get_thread_count()}")
    
    tab.close()
    time.sleep(0.5)
    
    print(f"\n关闭 tab 后:")
    print(f"  线程数: {get_thread_count()}")
    print(f"  线程数增长: {get_thread_count() - initial_threads}")
    print(f"  browser._all_drivers: {list(browser._all_drivers.keys())}")
    
    page.quit()
    time.sleep(0.5)
    
    print(f"\n退出浏览器后:")
    print(f"  线程数: {get_thread_count()}")
    print(f"  线程名: {get_thread_names()}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == '__main__':
    test_listener_driver_leak()
