# -*- coding:utf-8 -*-
"""
详细调试脚本
"""
import threading
import time

from DrissionPage import ChromiumPage


def get_thread_count():
    return threading.active_count()


def test_detailed_close():
    """详细测试 tab 关闭流程"""
    print("=" * 70)
    print("详细测试: tab 关闭流程")
    print("=" * 70)
    
    page = ChromiumPage()
    browser = page.browser
    
    print(f"\n=== 阶段1: 初始状态 ===")
    print(f"  browser._all_drivers: {list(browser._all_drivers.keys())}")
    print(f"  browser._drivers: {list(browser._drivers.keys())}")
    
    tab = browser.new_tab()
    tab_id = tab.tab_id
    
    print(f"\n=== 阶段2: 创建新 tab ===")
    print(f"  tab_id: {tab_id}")
    print(f"  browser._all_drivers: {list(browser._all_drivers.keys())}")
    print(f"  browser._drivers: {list(browser._drivers.keys())}")
    print(f"  tab.driver: {tab.driver}")
    print(f"  tab.driver.is_running: {tab.driver.is_running}")
    
    tab.listen.start('https://example.com')
    
    print(f"\n=== 阶段3: 启动 Listener ===")
    print(f"  tab.listen.listening: {tab.listen.listening}")
    print(f"  tab.listen._driver: {tab.listen._driver}")
    print(f"  tab.listen._driver.is_running: {tab.listen._driver.is_running}")
    print(f"  browser._all_drivers[{tab_id}]: {len(browser._all_drivers.get(tab_id, set()))} 个 Driver")
    
    print(f"\n=== 阶段4: 检查 _onTargetDestroyed 回调 ===")
    print(f"  browser._driver.event_handlers keys: {list(browser._driver.event_handlers.keys())}")
    
    print(f"\n=== 阶段5: 关闭 tab ===")
    print(f"  关闭前:")
    print(f"    tab.driver.is_running: {tab.driver.is_running}")
    print(f"    tab_id in browser._all_drivers: {tab_id in browser._all_drivers}")
    print(f"    tab.listen.listening: {tab.listen.listening}")
    
    tab.close()
    
    print(f"  关闭后立即:")
    print(f"    tab.driver.is_running: {tab.driver.is_running}")
    print(f"    tab_id in browser._all_drivers: {tab_id in browser._all_drivers}")
    try:
        print(f"    tab.listen.listening: {tab.listen.listening}")
    except Exception as e:
        print(f"    访问 tab.listen 出错: {e}")
    
    time.sleep(0.5)
    
    print(f"\n=== 阶段6: 关闭后 0.5 秒 ===")
    print(f"  browser._all_drivers: {list(browser._all_drivers.keys())}")
    print(f"  browser._drivers: {list(browser._drivers.keys())}")
    print(f"  browser._frames: {list(browser._frames.keys())}")
    print(f"  tab_id in browser._all_drivers: {tab_id in browser._all_drivers}")
    
    if tab_id in browser._all_drivers:
        print(f"\n  !!! 问题: tab_id 仍在 browser._all_drivers 中 !!!")
        drivers = browser._all_drivers.get(tab_id, set())
        print(f"    仍有 {len(drivers)} 个 Driver:")
        for d in drivers:
            print(f"      - {id(d)}, is_running: {d.is_running}")
    
    page.quit()
    time.sleep(0.5)
    
    print(f"\n=== 阶段7: 退出浏览器后 ===")
    print(f"  线程数: {get_thread_count()}")
    
    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)


if __name__ == '__main__':
    test_detailed_close()
