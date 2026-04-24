# -*- coding:utf-8 -*-
"""
调试场景3: 重连后旧引用不可复用
"""
import threading
import time

from DrissionPage import ChromiumPage


def get_thread_count():
    return threading.active_count()


def test_reconnect_debug():
    """调试重连场景"""
    print("=" * 70)
    print("调试: 重连后旧引用不可复用")
    print("=" * 70)
    
    page = ChromiumPage()
    browser = page.browser
    
    print(f"\n=== 阶段1: 初始状态 ===")
    print(f"  page.tab_id: {page.tab_id}")
    print(f"  page.driver: {page.driver}")
    print(f"  page.driver.is_running: {page.driver.is_running}")
    print(f"  browser._all_drivers: {list(browser._all_drivers.keys())}")
    
    old_tab_id = page.tab_id
    old_driver = page.driver
    old_listener = page.listen
    
    print(f"\n=== 阶段2: 保存旧引用 ===")
    print(f"  old_tab_id: {old_tab_id}")
    print(f"  old_driver: {old_driver}")
    print(f"  old_driver.is_running: {old_driver.is_running}")
    
    old_listener.start('test')
    print(f"  old_listener.listening: {old_listener.listening}")
    
    print(f"\n=== 阶段3: 执行重连 ===")
    page.reconnect(wait=0.5)
    
    print(f"\n=== 阶段4: 重连后状态 ===")
    print(f"  page.tab_id: {page.tab_id}")
    print(f"  page.driver: {page.driver}")
    print(f"  page.driver.is_running: {page.driver.is_running}")
    print(f"  browser._all_drivers: {list(browser._all_drivers.keys())}")
    
    print(f"\n=== 阶段5: 检查旧引用 ===")
    print(f"  old_driver.is_running: {old_driver.is_running}")
    print(f"  old_listener.listening: {old_listener.listening}")
    print(f"  old_tab_id == page.tab_id: {old_tab_id == page.tab_id}")
    
    print(f"\n  尝试调用 old_driver.run('Page.getTitle'):")
    try:
        result = old_driver.run('Page.getTitle')
        print(f"    结果: {result}")
        print(f"    结果类型: {type(result)}")
        if isinstance(result, dict) and 'error' in result:
            print(f"    包含错误: {result['error']}")
            print(f"    => 旧引用实际上不可用（返回错误）")
        else:
            print(f"    => 旧引用仍然可用")
    except Exception as e:
        print(f"    抛出异常: {e}")
        print(f"    => 旧引用不可用")
    
    print(f"\n=== 阶段6: 浏览器 _all_drivers 详情 ===")
    for tid, drivers in browser._all_drivers.items():
        print(f"  tab_id: {tid}")
        for d in drivers:
            print(f"    - Driver: {id(d)}, is_running: {d.is_running}")
            if d is old_driver:
                print(f"      => 这是 old_driver")
            if d is page.driver:
                print(f"      => 这是新的 page.driver")
    
    page.quit()
    time.sleep(0.5)
    
    print(f"\n=== 阶段7: 退出后 ===")
    print(f"  old_driver.is_running: {old_driver.is_running}")
    print(f"  线程数: {get_thread_count()}")
    
    print("\n" + "=" * 70)
    print("调试完成")
    print("=" * 70)


if __name__ == '__main__':
    test_reconnect_debug()
