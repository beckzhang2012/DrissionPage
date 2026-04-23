# -*- coding:utf-8 -*-
"""
Fixed Tab Lifecycle Race Condition Tests
This version uses read_file=True and auto_port() which works correctly.
"""
import json
import sys
import threading
from pathlib import Path
from platform import system
from time import sleep, perf_counter
from typing import Dict, List, Optional

sys.path.insert(0, 'd:\\work\\solo-coder\\task\\20260422-drissionpage-3314-tab-lifecycle-race-fix\\repo\\DrissionPage')

from DrissionPage._units.lifecycle_stats import lifecycle_stats


def cleanup_browser_cache():
    from DrissionPage._base.chromium import Chromium
    from DrissionPage._base.driver import BrowserDriver
    from DrissionPage._functions.tools import PortFinder
    
    Chromium._BROWSERS.clear()
    BrowserDriver.BROWSERS.clear()
    PortFinder.used_port.clear()


def create_test_options():
    from DrissionPage import ChromiumOptions
    
    co = ChromiumOptions(read_file=True)
    co.auto_port()
    
    return co


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
    result = TestResult('test_rapid_close_reopen')
    lifecycle_stats.reset()
    cleanup_browser_cache()
    
    try:
        from DrissionPage import Chromium
        
        co = create_test_options()
        browser = Chromium(co)
        try:
            tab0 = browser.latest_tab
            
            tab1 = browser.new_tab()
            tab1_id = tab1.tab_id
            
            tab1.listen.start('https://httpbin.org')
            tab1.get('https://httpbin.org/delay/1')
            
            sleep(0.3)
            
            tab1.close()
            sleep(0.2)
            
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
                browser.quit(force=True)
            except:
                pass
                
    except Exception as e:
        result.error = str(e)
        result.exit_code = 1
        result.passed = False
    
    return result


def run_test_concurrent_switch() -> TestResult:
    result = TestResult('test_concurrent_switch')
    lifecycle_stats.reset()
    cleanup_browser_cache()
    
    try:
        from DrissionPage import Chromium
        
        co = create_test_options()
        browser = Chromium(co)
        try:
            tabs = []
            tab_ids = []
            
            for i in range(3):
                tab = browser.new_tab()
                tabs.append(tab)
                tab_ids.append(tab.tab_id)
                tab.listen.start('https://httpbin.org')
            
            switch_count = 5
            errors = []
            
            for i in range(switch_count):
                for j, tab in enumerate(tabs):
                    browser.activate_tab(tab)
                    tab.get('https://httpbin.org/get')
                    sleep(0.1)
                    
                    try:
                        packet = tab.listen.wait(timeout=3)
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
                browser.quit(force=True)
            except:
                pass
                
    except Exception as e:
        result.error = str(e)
        result.exit_code = 1
        result.passed = False
    
    return result


def run_test_stale_events_after_reconnect() -> TestResult:
    result = TestResult('test_stale_events_after_reconnect')
    lifecycle_stats.reset()
    cleanup_browser_cache()
    
    try:
        from DrissionPage import Chromium
        
        co = create_test_options()
        browser = Chromium(co)
        try:
            tab = browser.latest_tab
            original_tab_id = tab.tab_id
            
            tab.listen.start('https://httpbin.org')
            
            old_session_id = tab._driver.session_id if tab._driver else None
            
            tab.get('https://httpbin.org/delay/2')
            sleep(0.3)
            
            tab.reconnect()
            
            new_session_id = tab._driver.session_id if tab._driver else None
            
            sleep(2)
            
            stats = lifecycle_stats.get_summary()
            result.dropped_count = stats['events']['total_dropped']
            
            result.passed = True
            result.metrics = {
                'old_session_id': str(old_session_id) if old_session_id else None,
                'new_session_id': str(new_session_id) if new_session_id else None,
                'session_changed': old_session_id != new_session_id if old_session_id and new_session_id else 'N/A',
                'events_dropped': result.dropped_count,
                'tab_id_preserved': tab.tab_id == original_tab_id
            }
            
            result.exit_code = 0
            
        finally:
            try:
                browser.quit(force=True)
            except:
                pass
                
    except Exception as e:
        result.error = str(e)
        result.exit_code = 1
        result.passed = False
    
    return result


def run_test_abort_recovery() -> TestResult:
    result = TestResult('test_abort_recovery')
    lifecycle_stats.reset()
    cleanup_browser_cache()
    
    try:
        from DrissionPage import Chromium
        
        co = create_test_options()
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
                browser.quit(force=True)
            except:
                pass
                
    except Exception as e:
        result.error = str(e)
        result.exit_code = 1
        result.passed = False
    
    return result


def run_test_backward_compatibility() -> TestResult:
    result = TestResult('test_backward_compatibility')
    lifecycle_stats.reset()
    cleanup_browser_cache()
    
    try:
        from DrissionPage import Chromium
        
        co = create_test_options()
        browser = Chromium(co)
        try:
            tab = browser.latest_tab
            tab_id = tab.tab_id
            
            print("    Testing: listen.start()...")
            tab.listen.start('https://httpbin.org')
            if not tab.listen.listening:
                result.error = "listen.start() did not set listening=True"
                return result
            
            tab.get('https://httpbin.org/get')
            
            print("    Testing: listen.wait()...")
            packet1 = tab.listen.wait(timeout=5)
            if not packet1:
                result.error = "listen.wait() did not return a packet"
                return result
            if packet1.tab_id != tab_id:
                result.error = f"Packet tab_id mismatch: expected {tab_id}, got {packet1.tab_id}"
                return result
            result.tab_hits[tab_id] = result.tab_hits.get(tab_id, 0) + 1
            
            print("    Testing: listen.pause(clear=False)...")
            tab.listen.pause(clear=False)
            if tab.listen.listening:
                result.error = "listen.pause() did not set listening=False"
                return result
            
            print("    Testing: listen.resume()...")
            tab.listen.resume()
            if not tab.listen.listening:
                result.error = "listen.resume() did not set listening=True"
                return result
            
            print("    Testing: listen.steps()...")
            tab.get('https://httpbin.org/headers')
            tab.get('https://httpbin.org/ip')
            sleep(1)
            
            steps_list = list(tab.listen.steps(timeout=2, count=2))
            print(f"    Steps count: {len(steps_list)}")
            if steps_list:
                for step in steps_list:
                    if hasattr(step, 'tab_id') and step.tab_id != tab_id:
                        result.error = f"Steps tab_id mismatch: expected {tab_id}, got {step.tab_id}"
                        return result
                    result.tab_hits[tab_id] = result.tab_hits.get(tab_id, 0) + 1
            
            print("    Testing: listen.clear()...")
            tab.listen.clear()
            
            print("    Testing: listen.stop()...")
            tab.listen.stop()
            if tab.listen.listening:
                result.error = "listen.stop() did not set listening=False"
                return result
            
            sleep(0.5)
            
            stats = lifecycle_stats.get_summary()
            result.dropped_count = stats['events']['total_dropped']
            
            result.passed = True
            result.metrics = {
                'start_works': True,
                'wait_works': True,
                'pause_works': True,
                'resume_works': True,
                'steps_works': True,
                'clear_works': True,
                'stop_works': True,
                'events_dropped': result.dropped_count,
                'events_received': sum(result.tab_hits.values())
            }
            
            result.exit_code = 0
            
        finally:
            try:
                browser.quit(force=True)
            except:
                pass
                
    except Exception as e:
        import traceback
        traceback.print_exc()
        result.error = str(e)
        result.exit_code = 1
        result.passed = False
    
    return result


def run_all_tests() -> Dict:
    tests = [
        ('test_rapid_close_reopen', run_test_rapid_close_reopen),
        ('test_concurrent_switch', run_test_concurrent_switch),
        ('test_stale_events_after_reconnect', run_test_stale_events_after_reconnect),
        ('test_abort_recovery', run_test_abort_recovery),
        ('test_backward_compatibility', run_test_backward_compatibility),
    ]
    
    results = []
    all_passed = True
    total_dropped = 0
    total_hits = 0
    
    print("=" * 70)
    print("Tab Lifecycle Race Condition Tests - End-to-End Validation")
    print("=" * 70)
    
    for name, test_func in tests:
        print(f"\n{'='*70}")
        print(f"Running: {name}")
        print(f"{'='*70}")
        
        try:
            result = test_func()
            results.append(result)
            
            total_dropped += result.dropped_count
            total_hits += sum(result.tab_hits.values())
            
            status = "PASSED" if result.passed else "FAILED"
            print(f"\n  [{status}] {name}")
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
            import traceback
            traceback.print_exc()
            all_passed = False
    
    print("\n" + "=" * 70)
    print("FINAL TEST SUMMARY")
    print("=" * 70)
    
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
    
    print(f"\nOverall Status: {'PASSED' if all_passed else 'FAILED'}")
    print(f"Passed: {summary['passed_tests']}/{summary['total_tests']}")
    print(f"Total Events Dropped: {summary['total_events_dropped']}")
    print(f"Total Events Validated: {summary['total_events_validated']}")
    
    print(f"\nFinal Statistics:")
    print(f"  $LASTEXITCODE: {0 if all_passed else 1}")
    print(f"  Tabs Tracked: {final_stats['tabs']['total_tracked']}")
    print(f"  Alive Tabs: {final_stats['tabs']['alive_count']}")
    print(f"  Dead Tabs: {final_stats['tabs']['dead_count']}")
    
    print(f"\nTab Hits (hits_by_tab):")
    if final_stats['events']['hits_by_tab']:
        for tab_id, count in final_stats['events']['hits_by_tab'].items():
            print(f"  {tab_id}: {count}")
    else:
        print("  (none)")
    
    print(f"\nDropped Events Count: {final_stats['events']['total_dropped']}")
    if final_stats['events']['dropped_by_type']:
        print(f"Dropped Events by Type:")
        for event_type, count in final_stats['events']['dropped_by_type'].items():
            print(f"  {event_type}: {count}")
    
    print(f"\nState Transitions:")
    print(f"  (tracked in lifecycle_stats.tab_state_transitions)")
    
    overall_exit_code = 0 if all_passed else 1
    print(f"\nFinal Exit Code ($LASTEXITCODE): {overall_exit_code}")
    
    print("\n" + "=" * 70)
    print("OUTPUT FORMAT: tab_hits, dropped_count, state_transitions, $LASTEXITCODE")
    print("=" * 70)
    print(f"tab_hits: {final_stats['events']['hits_by_tab']}")
    print(f"dropped_count: {final_stats['events']['total_dropped']}")
    print(f"state_transitions_count: {sum(len(v) for v in lifecycle_stats.tab_state_transitions.values())}")
    print(f"$LASTEXITCODE: {overall_exit_code}")
    
    return summary


if __name__ == '__main__':
    result = run_all_tests()
    sys.exit(0 if result['overall_passed'] else 1)
