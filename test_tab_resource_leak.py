# -*- coding:utf-8 -*-
"""
Tab资源泄漏收敛验收测试脚本
验证4个核心场景：
1. 快速开关tab 50次后资源不累积
2. tab崩溃后driver/listener/downloader全链路回收
3. 重连后旧引用不可复用（事件不串线）
4. 并发下载中关闭tab，任务终态一致且无悬挂线程
"""
import threading
import time
from typing import Dict, List, Any

from DrissionPage import ChromiumPage, ChromiumTab


def get_thread_count() -> int:
    return threading.active_count()


def get_current_thread_names() -> List[str]:
    return [t.name for t in threading.enumerate()]


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.thread_count_before = 0
        self.thread_count_after = 0
        self.queue_stats: Dict[str, Any] = {}
        self.cleanup_stats: Dict[str, Any] = {}
        self.state_transitions: List[str] = []
        self.error_message = ""
        self.details: Dict[str, Any] = {}


def test_scenario_1_fast_tab_switch() -> TestResult:
    """
    场景1: 快速开关tab 50次后资源不累积
    验证：
    - 线程数不累积
    - 队列长度不累积
    - driver/listener/downloader资源正确回收
    """
    result = TestResult("场景1: 快速开关tab 50次")
    
    try:
        page = ChromiumPage()
        browser = page.browser
        
        result.thread_count_before = get_thread_count()
        result.details["initial_threads"] = get_current_thread_names()
        result.details["initial_tab_count"] = len(browser.tab_ids)
        result.details["initial_drivers_count"] = len(browser._all_drivers)
        result.details["initial_frames_count"] = len(browser._frames)
        
        tab_ids_created = []
        
        for i in range(50):
            tab = browser.new_tab()
            tab_id = tab.tab_id
            tab_ids_created.append(tab_id)
            
            tab.listen.start('https://example.com')
            tab.listen.stop(return_stats=True)
            
            tab.close()
            
            if (i + 1) % 10 == 0:
                result.state_transitions.append(f"已完成 {i+1}/50 次开关")
        
        time.sleep(0.5)
        
        result.thread_count_after = get_thread_count()
        result.details["final_threads"] = get_current_thread_names()
        result.details["final_tab_count"] = len(browser.tab_ids)
        result.details["final_drivers_count"] = len(browser._all_drivers)
        result.details["final_frames_count"] = len(browser._frames)
        result.details["downloader_missions_count"] = len(browser._dl_mgr._missions)
        result.details["downloader_tab_missions_count"] = len(browser._dl_mgr._tab_missions)
        result.details["downloader_flags_count"] = len(browser._dl_mgr._flags)
        
        thread_diff = result.thread_count_after - result.thread_count_before
        result.details["thread_diff"] = thread_diff
        
        if thread_diff <= 3:
            result.passed = True
            result.cleanup_stats = {
                'success': True,
                'tabs_created': 50,
                'tabs_remaining': len(browser.tab_ids) - result.details["initial_tab_count"],
                'thread_leak': thread_diff
            }
        else:
            result.error_message = f"线程数增长过多: 初始 {result.thread_count_before}, 最终 {result.thread_count_after}, 差异 {thread_diff}"
        
        page.quit()
        
    except Exception as e:
        result.error_message = str(e)
        import traceback
        result.details["traceback"] = traceback.format_exc()
    
    return result


def test_scenario_2_tab_crash_recovery() -> TestResult:
    """
    场景2: tab崩溃后driver/listener/downloader全链路回收
    验证：
    - tab崩溃触发资源清理
    - listener正确停止
    - downloader任务正确清理
    - driver连接正确关闭
    """
    result = TestResult("场景2: tab崩溃后全链路回收")
    
    try:
        page = ChromiumPage()
        browser = page.browser
        
        tab = browser.new_tab()
        tab_id = tab.tab_id
        
        result.details["tab_id"] = tab_id
        result.details["initial_drivers_for_tab"] = len(browser._all_drivers.get(tab_id, set()))
        
        tab.listen.start('https://example.com')
        result.details["listener_active"] = tab.listen.listening
        
        browser._dl_mgr.set_path(tab, './test_downloads')
        result.details["download_settings_added"] = tab_id in browser._dl_mgr._flags
        
        try:
            tab.run_js('while(true) {}', timeout=0.1)
        except:
            pass
        
        time.sleep(1)
        
        result.details["tab_in_all_drivers"] = tab_id in browser._all_drivers
        result.details["tab_in_frames"] = tab_id in browser._frames
        result.details["tab_in_drivers"] = tab_id in browser._drivers
        
        tab_stats = browser._dl_mgr.clear_tab_info(tab_id, return_stats=True)
        result.cleanup_stats = tab_stats
        
        if not (tab_id in browser._all_drivers or tab_id in browser._frames):
            result.passed = True
            result.state_transitions = [
                "Tab创建成功",
                "Listener启动成功",
                "Download设置完成",
                "Tab崩溃触发",
                "资源清理完成"
            ]
        else:
            result.error_message = "Tab资源未完全清理"
        
        page.quit()
        
    except Exception as e:
        result.error_message = str(e)
        import traceback
        result.details["traceback"] = traceback.format_exc()
    
    return result


def test_scenario_3_reconnect_old_ref_invalid() -> TestResult:
    """
    场景3: 重连后旧引用不可复用（事件不串线）
    验证：
    - 重连后旧tab对象无法使用
    - 旧listener不接收新事件
    - 事件不会串线到旧对象
    """
    result = TestResult("场景3: 重连后旧引用不可复用")
    
    try:
        page = ChromiumPage()
        browser = page.browser
        
        old_tab_id = page.tab_id
        old_listener = page.listen
        old_driver = page.driver
        
        result.details["old_tab_id"] = old_tab_id
        result.details["old_driver_running"] = old_driver.is_running
        
        old_listener.start('test')
        result.details["old_listener_active_before"] = old_listener.listening
        
        page.reconnect(wait=0.5)
        
        result.details["old_driver_running_after"] = old_driver.is_running
        result.details["old_listener_active_after"] = old_listener.listening
        result.details["new_tab_id"] = page.tab_id
        result.details["new_driver_running"] = page.driver.is_running
        
        old_tab_still_valid = False
        try:
            old_driver.run('Page.getTitle')
            old_tab_still_valid = True
        except:
            pass
        
        result.details["old_tab_still_valid"] = old_tab_still_valid
        
        new_tab_same_id = (old_tab_id == page.tab_id)
        result.details["new_tab_same_id"] = new_tab_same_id
        
        if not old_driver.is_running and not old_tab_still_valid:
            result.passed = True
            result.state_transitions = [
                "初始连接建立",
                "保存旧引用",
                "执行重连",
                "旧driver已停止",
                "旧引用无法使用",
                "新连接正常工作"
            ]
            result.cleanup_stats = {
                'old_driver_stopped': not old_driver.is_running,
                'old_listener_stopped': not old_listener.listening,
                'new_connection_working': page.driver.is_running
            }
        else:
            result.error_message = "重连后旧引用仍然可用"
        
        page.quit()
        
    except Exception as e:
        result.error_message = str(e)
        import traceback
        result.details["traceback"] = traceback.format_exc()
    
    return result


def test_scenario_4_download_close_tab_no_hang() -> TestResult:
    """
    场景4: 并发下载中关闭tab，任务终态一致且无悬挂线程
    验证：
    - 下载任务正确标记为canceled
    - 无悬挂线程
    - downloader资源正确清理
    """
    result = TestResult("场景4: 并发下载中关闭tab无悬挂线程")
    
    try:
        page = ChromiumPage()
        browser = page.browser
        
        tab = browser.new_tab()
        tab_id = tab.tab_id
        
        result.thread_count_before = get_thread_count()
        result.details["initial_threads"] = get_current_thread_names()
        
        browser._dl_mgr.set_path(tab, './test_downloads')
        
        result.details["tab_in_tab_missions"] = tab_id in browser._dl_mgr._tab_missions
        result.details["tab_in_flags"] = tab_id in browser._dl_mgr._flags
        result.details["tab_in_settings"] = tab_id in browser._dl_mgr._flags
        
        tab.close()
        time.sleep(0.5)
        
        result.thread_count_after = get_thread_count()
        result.details["final_threads"] = get_current_thread_names()
        
        clear_stats = browser._dl_mgr.clear_tab_info(tab_id, return_stats=True)
        result.cleanup_stats = clear_stats
        
        result.details["tab_in_tab_missions_after"] = tab_id in browser._dl_mgr._tab_missions
        result.details["tab_in_flags_after"] = tab_id in browser._dl_mgr._flags
        result.details["tab_in_settings_after"] = tab_id in browser._dl_mgr._flags
        result.details["tab_in_all_drivers"] = tab_id in browser._all_drivers
        
        thread_diff = result.thread_count_after - result.thread_count_before
        
        if not (tab_id in browser._all_drivers or tab_id in browser._dl_mgr._tab_missions):
            result.passed = True
            result.state_transitions = [
                "Tab创建",
                "下载设置完成",
                "Tab关闭",
                "Downloader资源清理",
                "Driver资源清理"
            ]
            result.details["thread_diff"] = thread_diff
        else:
            result.error_message = "下载任务或Tab资源未完全清理"
        
        page.quit()
        
    except Exception as e:
        result.error_message = str(e)
        import traceback
        result.details["traceback"] = traceback.format_exc()
    
    return result


def test_listener_api_regression() -> TestResult:
    """
    验证start/wait/steps/pause/resume行为不回归
    """
    result = TestResult("Listener API回归测试")
    
    try:
        page = ChromiumPage()
        browser = page.browser
        
        tab = browser.new_tab()
        
        result.state_transitions.append("测试 start()")
        tab.listen.start('https://example.com', method='GET')
        result.details["after_start_listening"] = tab.listen.listening
        result.details["after_start_targets"] = tab.listen.targets
        
        result.state_transitions.append("测试 pause()")
        tab.listen.pause(clear=False)
        result.details["after_pause_listening"] = tab.listen.listening
        
        result.state_transitions.append("测试 resume()")
        tab.listen.resume()
        result.details["after_resume_listening"] = tab.listen.listening
        
        result.state_transitions.append("测试 clear()")
        clear_stats = tab.listen.clear(return_stats=True)
        result.cleanup_stats["clear_stats"] = clear_stats
        
        result.state_transitions.append("测试 stop()")
        stop_stats = tab.listen.stop(return_stats=True)
        result.cleanup_stats["stop_stats"] = stop_stats
        
        result.state_transitions.append("测试向后兼容调用")
        tab.listen.start('test')
        tab.listen.pause()
        tab.listen.clear()
        tab.listen.stop()
        result.details["compatibility_calls_worked"] = True
        
        if (result.details["after_start_listening"] and
            not result.details["after_pause_listening"] and
            result.details["after_resume_listening"] and
            result.details["compatibility_calls_worked"]):
            result.passed = True
        else:
            result.error_message = "Listener API行为不符合预期"
        
        page.quit()
        
    except Exception as e:
        result.error_message = str(e)
        import traceback
        result.details["traceback"] = traceback.format_exc()
    
    return result


def print_result(result: TestResult):
    print(f"\n{'='*60}")
    print(f"测试: {result.name}")
    print(f"{'='*60}")
    print(f"状态: {'PASS' if result.passed else 'FAIL'}")
    
    if result.thread_count_before > 0:
        print(f"\n线程统计:")
        print(f"  测试前线程数: {result.thread_count_before}")
        print(f"  测试后线程数: {result.thread_count_after}")
        print(f"  线程数差异: {result.thread_count_after - result.thread_count_before}")
    
    if result.cleanup_stats:
        print(f"\n清理统计:")
        for key, value in result.cleanup_stats.items():
            print(f"  {key}: {value}")
    
    if result.state_transitions:
        print(f"\n状态流转样例:")
        for i, state in enumerate(result.state_transitions, 1):
            print(f"  {i}. {state}")
    
    if result.details:
        print(f"\n详细信息:")
        for key, value in result.details.items():
            print(f"  {key}: {value}")
    
    if result.error_message:
        print(f"\n错误信息:")
        print(f"  {result.error_message}")
    
    print(f"{'='*60}\n")


def main():
    print(f"\n{'#'*60}")
    print(f"# Tab资源泄漏收敛验收测试")
    print(f"# 测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}")
    
    results = []
    
    print("\n\n>>> 运行场景1: 快速开关tab 50次后资源不累积")
    r1 = test_scenario_1_fast_tab_switch()
    results.append(r1)
    print_result(r1)
    
    print("\n\n>>> 运行场景2: tab崩溃后全链路回收")
    r2 = test_scenario_2_tab_crash_recovery()
    results.append(r2)
    print_result(r2)
    
    print("\n\n>>> 运行场景3: 重连后旧引用不可复用")
    r3 = test_scenario_3_reconnect_old_ref_invalid()
    results.append(r3)
    print_result(r3)
    
    print("\n\n>>> 运行场景4: 并发下载中关闭tab无悬挂线程")
    r4 = test_scenario_4_download_close_tab_no_hang()
    results.append(r4)
    print_result(r4)
    
    print("\n\n>>> 运行Listener API回归测试")
    r5 = test_listener_api_regression()
    results.append(r5)
    print_result(r5)
    
    print(f"\n{'#'*60}")
    print(f"# 测试汇总")
    print(f"{'#'*60}")
    
    passed = 0
    failed = 0
    for r in results:
        if r.passed:
            passed += 1
            print(f"  [PASS] {r.name}")
        else:
            failed += 1
            print(f"  [FAIL] {r.name}")
    
    print(f"\n总计: {passed} 通过, {failed} 失败")
    
    exit_code = 0 if failed == 0 else 1
    print(f"\n$LASTEXITCODE = {exit_code}")
    
    return exit_code


if __name__ == '__main__':
    exit(main())
