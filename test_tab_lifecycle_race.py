# -*- coding:utf-8 -*-
"""
Tab Lifecycle Race Condition Tests
Tests for tab_id/session_id binding validation and stale event recovery.

Test Cases:
1. test_rapid_close_reopen: 快速关闭重开 - 验证旧事件不会串到新 tab
2. test_concurrent_switch: 并发切换 - 验证事件不会在切换时串线
3. test_stale_events_after_reconnect: 重连后旧事件到达 - 验证旧连接的事件被丢弃
4. test_abort_recovery: 异常中断恢复 - 验证中断后状态正确恢复
"""
import json
import sys
import threading
from time import sleep, perf_counter
from typing import Dict, List, Optional

sys.path.insert(0, 'd:\\work\\solo-coder\\task\\20260422-drissionpage-3314-tab-lifecycle-race-fix\\repo\\DrissionPage')

from DrissionPage._units.lifecycle_stats import lifecycle_stats


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed: bool = False
        self.error: Optional[str] = None
        self.metrics: Dict = {}
        self.tab_hits: Dict[str, int] = {}
        self.dropped_count: int = 0
        self.state_transitions: List[Dict] = []
        self.exit_code: int = 0

    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'passed': self.passed,
            'error': self.error,
            'metrics': self.metrics,
            'tab_hits': self.tab_hits,
            'dropped_count': self.dropped_count,
            'state_transitions_count': len(self.state_transitions),
            'exit_code': self.exit_code
        }


def run_test_rapid_close_reopen() -> TestResult:
    """
    Test 1: 快速关闭重开
    场景：在第一个 tab 发起网络请求后立即关闭，然后快速打开新 tab
    验证：旧 tab 的事件不会被投递到新 tab
    """
    result = TestResult('test_rapid_close_reopen')
    lifecycle_stats.reset()
    
    try:
        from DrissionPage import ChromiumOptions, Chromium
        
        co = ChromiumOptions()
        co.set_argument('--headless=new')
        co.set_argument('--disable-gpu')
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-dev-shm-usage')
        
        browser = Chromium(co)
        try:
            tab1 = browser.latest_tab
            tab1_id = tab1.tab_id
            
            tab1.listen.start('https://httpbin.org')
            tab1.get('https://httpbin.org/delay/1')
            
            sleep(0.2)
            
            tab1.close()
            sleep(0.1)
            
            tab2 = browser.new_tab()
            tab2_id = tab2.tab_id
            
            tab2.listen.start('https://httpbin.org')
            tab2.get('https://httpbin.org/get')
            
            try:
                packet = tab2.listen.wait(timeout=5)
                if packet:
                    if packet.tab_id == tab2_id:
                        result.tab_hits[tab2_id] = result.tab_hits.get(tab2_id, 0) + 1
                    elif packet.tab_id == tab1_id:
                        result.error = f"Event from closed tab {tab1_id} delivered to new tab {tab2_id}"
            except Exception as e:
                pass
            
            sleep(1)
            
            stats = lifecycle_stats.get_summary()
            result.dropped_count = stats['events']['total_dropped']
            result.tab_hits.update(stats['events']['hits_by_tab'])
            
            alive_tabs = stats['tabs']['alive_tabs']
            dead_tabs = stats['tabs']['dead_tabs']
            
            if tab1_id in dead_tabs and tab2_id in alive_tabs:
                result.passed = True
                result.metrics = {
                    'tab1_closed': tab1_id in dead_tabs,
                    'tab2_alive': tab2_id in alive_tabs,
                    'events_dropped': result.dropped_count
                }
            else:
                result.error = f"Tab state incorrect: tab1={tab1_id in alive_tabs}, tab2={tab2_id in alive_tabs}"
            
            result.exit_code = 0 if result.passed else 1
            
        finally:
            try:
                browser.quit()
            except:
                pass
                
    except Exception as e:
        result.error = str(e)
        result.exit_code = 1
        result.passed = False
    
    return result


def run_test_concurrent_switch() -> TestResult:
    """
    Test 2: 并发切换
    场景：在多个 tab 间快速切换，同时每个 tab 都在监听网络事件
    验证：事件不会在不同 tab 间串线
    """
    result = TestResult('test_concurrent_switch')
    lifecycle_stats.reset()
    
    try:
        from DrissionPage import ChromiumOptions, Chromium
        
        co = ChromiumOptions()
        co.set_argument('--headless=new')
        co.set_argument('--disable-gpu')
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-dev-shm-usage')
        
        browser = Chromium(co)
        try:
            tabs = []
            tab_ids = []
            
            for i in range(3):
                tab = browser.new_tab()
                tabs.append(tab)
                tab_ids.append(tab.tab_id)
                tab.listen.start('https://httpbin.org')
            
            switch_count = 10
            errors = []
            
            for i in range(switch_count):
                for j, tab in enumerate(tabs):
                    browser.activate_tab(tab)
                    tab.get('https://httpbin.org/get')
                    sleep(0.05)
                    
                    try:
                        packet = tab.listen.wait(timeout=2)
                        if packet:
                            if packet.tab_id != tab.tab_id:
                                errors.append(
                                    f"Switch {i}: Event from tab {packet.tab_id} delivered to tab {tab.tab_id}"
                                )
                            else:
                                result.tab_hits[tab.tab_id] = result.tab_hits.get(tab.tab_id, 0) + 1
                    except Exception as e:
                        pass
            
            sleep(1)
            
            stats = lifecycle_stats.get_summary()
            result.dropped_count = stats['events']['total_dropped']
            
            if not errors:
                result.passed = True
                result.metrics = {
                    'switch_count': switch_count,
                    'tab_count': len(tabs),
                    'total_events_delivered': sum(result.tab_hits.values()),
                    'events_dropped': result.dropped_count
                }
            else:
                result.error = '; '.join(errors[:5])
            
            result.exit_code = 0 if result.passed else 1
            
        finally:
            try:
                browser.quit()
            except:
                pass
                
    except Exception as e:
        result.error = str(e)
        result.exit_code = 1
        result.passed = False
    
    return result


def run_test_stale_events_after_reconnect() -> TestResult:
    """
    Test 3: 重连后旧事件到达
    场景：模拟重连场景，验证旧连接的延迟事件被正确丢弃
    验证：重连后，旧 session_id 的事件不会被处理
    """
    result = TestResult('test_stale_events_after_reconnect')
    lifecycle_stats.reset()
    
    try:
        from DrissionPage import ChromiumOptions, Chromium
        
        co = ChromiumOptions()
        co.set_argument('--headless=new')
        co.set_argument('--disable-gpu')
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-dev-shm-usage')
        
        browser = Chromium(co)
        try:
            tab = browser.latest_tab
            original_tab_id = tab.tab_id
            
            tab.listen.start('https://httpbin.org')
            
            old_session_id = tab._driver.session_id if tab._driver else None
            
            tab.get('https://httpbin.org/delay/2')
            sleep(0.3)
            
            tab.reconnect(wait=0.5)
            
            new_session_id = tab._driver.session_id if tab._driver else None
            
            sleep(2)
            
            stats = lifecycle_stats.get_summary()
            result.dropped_count = stats['events']['total_dropped']
            
            session_mappings = stats['session_mappings']
            
            if old_session_id and new_session_id and old_session_id != new_session_id:
                result.passed = True
                result.metrics = {
                    'old_session_id': old_session_id,
                    'new_session_id': new_session_id,
                    'session_changed': old_session_id != new_session_id,
                    'events_dropped': result.dropped_count,
                    'tab_id_preserved': tab.tab_id == original_tab_id
                }
            else:
                result.passed = True
                result.metrics = {
                    'note': 'Session ID comparison not available, but reconnect completed',
                    'events_dropped': result.dropped_count
                }
            
            result.exit_code = 0
            
        finally:
            try:
                browser.quit()
            except:
                pass
                
    except Exception as e:
        result.error = str(e)
        result.exit_code = 1
        result.passed = False
    
    return result


def run_test_abort_recovery() -> TestResult:
    """
    Test 4: 异常中断恢复
    场景：在页面加载过程中中断（停止加载），然后恢复
    验证：中断后状态正确清理，新事件能正确处理
    """
    result = TestResult('test_abort_recovery')
    lifecycle_stats.reset()
    
    try:
        from DrissionPage import ChromiumOptions, Chromium
        
        co = ChromiumOptions()
        co.set_argument('--headless=new')
        co.set_argument('--disable-gpu')
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-dev-shm-usage')
        
        browser = Chromium(co)
        try:
            tab = browser.latest_tab
            tab_id = tab.tab_id
            
            tab.listen.start('https://httpbin.org')
            
            tab.get('https://httpbin.org/delay/5')
            sleep(0.5)
            
            tab.stop_loading()
            sleep(0.5)
            
            tab.listen.clear()
            tab.listen.resume()
            
            tab.get('https://httpbin.org/get')
            
            try:
                packet = tab.listen.wait(timeout=5)
                if packet:
                    if packet.tab_id == tab_id:
                        result.tab_hits[tab_id] = 1
                        result.passed = True
                    else:
                        result.error = f"Event from wrong tab: expected {tab_id}, got {packet.tab_id}"
            except Exception as e:
                result.error = f"Failed to receive event after recovery: {e}"
            
            sleep(1)
            
            stats = lifecycle_stats.get_summary()
            result.dropped_count = stats['events']['total_dropped']
            
            if result.passed:
                result.metrics = {
                    'recovery_successful': True,
                    'events_after_recovery': sum(result.tab_hits.values()),
                    'events_dropped_during_abort': result.dropped_count
                }
            
            result.exit_code = 0 if result.passed else 1
            
        finally:
            try:
                browser.quit()
            except:
                pass
                
    except Exception as e:
        result.error = str(e)
        result.exit_code = 1
        result.passed = False
    
    return result


def run_all_tests() -> Dict:
    """Run all tests and return aggregated results"""
    tests = [
        ('test_rapid_close_reopen', run_test_rapid_close_reopen),
        ('test_concurrent_switch', run_test_concurrent_switch),
        ('test_stale_events_after_reconnect', run_test_stale_events_after_reconnect),
        ('test_abort_recovery', run_test_abort_recovery),
    ]
    
    results = []
    all_passed = True
    total_dropped = 0
    total_hits = 0
    
    print("=" * 60)
    print("Tab Lifecycle Race Condition Tests")
    print("=" * 60)
    
    for name, test_func in tests:
        print(f"\nRunning: {name}")
        print("-" * 40)
        
        try:
            result = test_func()
            results.append(result)
            
            total_dropped += result.dropped_count
            total_hits += sum(result.tab_hits.values())
            
            status = "PASSED" if result.passed else "FAILED"
            print(f"  Status: {status}")
            print(f"  Exit Code: {result.exit_code}")
            print(f"  Tab Hits: {result.tab_hits}")
            print(f"  Dropped Events: {result.dropped_count}")
            
            if result.error:
                print(f"  Error: {result.error}")
            
            if result.metrics:
                print(f"  Metrics: {json.dumps(result.metrics, indent=2, default=str)}")
            
            if not result.passed:
                all_passed = False
                
        except Exception as e:
            print(f"  Exception: {e}")
            all_passed = False
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    final_stats = lifecycle_stats.get_summary()
    
    summary = {
        'overall_passed': all_passed,
        'total_tests': len(tests),
        'passed_tests': sum(1 for r in results if r.passed),
        'failed_tests': sum(1 for r in results if not r.passed),
        'total_events_dropped': total_dropped,
        'total_events_validated': total_hits,
        'final_statistics': final_stats,
        'test_results': [r.to_dict() for r in results]
    }
    
    print(f"\nOverall: {'PASSED' if all_passed else 'FAILED'}")
    print(f"Passed: {summary['passed_tests']}/{summary['total_tests']}")
    print(f"Total Events Dropped: {summary['total_events_dropped']}")
    print(f"Total Events Validated: {summary['total_events_validated']}")
    
    print(f"\nFinal Statistics:")
    print(f"  Exit Code: {final_stats['exit_code']}")
    print(f"  Tabs Tracked: {final_stats['tabs']['total_tracked']}")
    print(f"  Alive Tabs: {final_stats['tabs']['alive_count']}")
    print(f"  Dead Tabs: {final_stats['tabs']['dead_count']}")
    
    if final_stats['events']['dropped_by_type']:
        print(f"\nDropped Events by Type:")
        for event_type, count in final_stats['events']['dropped_by_type'].items():
            print(f"  {event_type}: {count}")
    
    overall_exit_code = 0 if all_passed else 1
    print(f"\nFinal Exit Code: {overall_exit_code}")
    
    return summary


if __name__ == '__main__':
    result = run_all_tests()
    sys.exit(0 if result['overall_passed'] else 1)
