# -*- coding:utf-8 -*-
"""
关键场景验证脚本
验证: 当 Listener 仍在运行时关闭 tab，资源是否正确清理
"""
import threading
import time

from DrissionPage import ChromiumPage


def get_thread_count():
    return threading.active_count()


def get_thread_names():
    return [t.name for t in threading.enumerate()]


def test_listener_running_close_tab():
    """验证: 当 Listener 仍在运行时关闭 tab，资源是否正确清理"""
    print("=" * 60)
    print("测试: Listener 运行中关闭 tab 的资源清理验证")
    print("=" * 60)
    
    page = ChromiumPage()
    browser = page.browser
    
    print(f"\n=== 阶段1: 初始状态 ===")
    initial_threads = get_thread_count()
    print(f"  初始线程数: {initial_threads}")
    print(f"  线程名: {get_thread_names()}")
    print(f"  browser._all_drivers: {list(browser._all_drivers.keys())}")
    
    print(f"\n=== 阶段2: 创建新 tab ===")
    tab = browser.new_tab()
    tab_id = tab.tab_id
    print(f"  tab_id: {tab_id}")
    print(f"  线程数: {get_thread_count()} (增长: {get_thread_count() - initial_threads})")
    print(f"  browser._all_drivers: {list(browser._all_drivers.keys())}")
    
    print(f"\n=== 阶段3: 启动 Listener（不停止） ===")
    tab.listen.start('https://example.com')
    print(f"  listener.listening: {tab.listen.listening}")
    print(f"  listener._driver: {tab.listen._driver}")
    print(f"  listener._driver.is_running: {tab.listen._driver.is_running if tab.listen._driver else None}")
    print(f"  线程数: {get_thread_count()} (增长: {get_thread_count() - initial_threads})")
    print(f"  browser._all_drivers: {list(browser._all_drivers.keys())}")
    
    listener_driver_id = id(tab.listen._driver) if tab.listen._driver else None
    print(f"  Listener Driver ID: {listener_driver_id}")
    
    print(f"\n=== 阶段4: 关闭 tab（Listener 仍在运行！） ===")
    print(f"  关闭前: listener.listening = {tab.listen.listening}")
    print(f"  关闭前: listener._driver = {tab.listen._driver}")
    
    tab.close()
    time.sleep(0.5)
    
    print(f"  关闭后: 线程数: {get_thread_count()} (增长: {get_thread_count() - initial_threads})")
    print(f"  关闭后: browser._all_drivers: {list(browser._all_drivers.keys())}")
    
    try:
        print(f"  关闭后: tab.listen.listening = {tab.listen.listening}")
        print(f"  关闭后: tab.listen._driver = {tab.listen._driver}")
        if tab.listen._driver:
            print(f"  关闭后: tab.listen._driver.is_running = {tab.listen._driver.is_running}")
    except Exception as e:
        print(f"  访问 tab.listen 出错: {e}")
    
    print(f"\n=== 阶段5: 验证结果 ===")
    final_threads = get_thread_count()
    thread_growth = final_threads - initial_threads
    tab_in_all_drivers = tab_id in browser._all_drivers
    
    print(f"  最终线程数: {final_threads}")
    print(f"  线程数增长: {thread_growth}")
    print(f"  tab_id 是否仍在 browser._all_drivers 中: {tab_in_all_drivers}")
    
    passed = (thread_growth <= 1) and (not tab_in_all_drivers)
    
    print(f"\n  测试结果: {'PASS' if passed else 'FAIL'}")
    
    if passed:
        print(f"  ✓ 线程增长在可接受范围内")
        print(f"  ✓ Tab 资源已从 browser._all_drivers 中移除")
    else:
        if thread_growth > 1:
            print(f"  ✗ 线程增长过多: {thread_growth}")
        if tab_in_all_drivers:
            print(f"  ✗ Tab 资源仍在 browser._all_drivers 中")
    
    page.quit()
    time.sleep(0.5)
    
    print(f"\n=== 阶段6: 退出浏览器后 ===")
    print(f"  最终线程数: {get_thread_count()}")
    print(f"  线程名: {get_thread_names()}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    
    return passed


def test_fast_switch_10_times():
    """快速开关 tab 10 次，验证资源不累积"""
    print("\n" + "=" * 60)
    print("测试: 快速开关 tab 10 次（带 Listener）")
    print("=" * 60)
    
    page = ChromiumPage()
    browser = page.browser
    
    initial_threads = get_thread_count()
    print(f"\n初始线程数: {initial_threads}")
    
    for i in range(10):
        tab = browser.new_tab()
        tab.listen.start('https://example.com')
        # 注意：不调用 stop()，直接关闭 tab
        tab.close()
        time.sleep(0.1)
        if (i + 1) % 5 == 0:
            print(f"  已完成 {i+1}/10 次开关，当前线程数: {get_thread_count()}")
    
    time.sleep(0.5)
    
    final_threads = get_thread_count()
    thread_growth = final_threads - initial_threads
    
    print(f"\n最终线程数: {final_threads}")
    print(f"线程数增长: {thread_growth}")
    print(f"browser._all_drivers: {list(browser._all_drivers.keys())}")
    
    passed = thread_growth <= 2
    print(f"\n测试结果: {'PASS' if passed else 'FAIL'}")
    
    page.quit()
    time.sleep(0.5)
    
    print(f"\n退出浏览器后线程数: {get_thread_count()}")
    
    return passed


if __name__ == '__main__':
    print("\n" + "#" * 60)
    print("# 关键场景验证测试")
    print("#" * 60)
    
    results = []
    
    print("\n\n>>> 测试1: Listener 运行中关闭 tab")
    r1 = test_listener_running_close_tab()
    results.append(("Listener 运行中关闭 tab", r1))
    
    print("\n\n>>> 测试2: 快速开关 tab 10 次（带 Listener）")
    r2 = test_fast_switch_10_times()
    results.append(("快速开关 tab 10 次", r2))
    
    print("\n\n" + "#" * 60)
    print("# 测试汇总")
    print("#" * 60)
    
    passed = 0
    failed = 0
    for name, result in results:
        if result:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name}")
    
    print(f"\n总计: {passed} 通过, {failed} 失败")
    
    exit_code = 0 if failed == 0 else 1
    print(f"\n$LASTEXITCODE = {exit_code}")
    
    exit(exit_code)
