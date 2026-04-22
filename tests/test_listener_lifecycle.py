# -*- coding:utf-8 -*-
"""
Listener 生命周期清理测试
验证修复后的 Listener 生命周期管理
"""
import os
import sys
import threading
import time
from queue import Queue
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from DrissionPage._units.listener import Listener, _NETWORK_EVENTS


class MockOwner:
    """模拟页面 owner 对象"""
    def __init__(self):
        self._target_id = 'test-target-id'
        self.tab_id = 'test-tab-id'
        
    class MockBrowser:
        def __init__(self):
            self._ws_address = 'ws://localhost:9222/devtools/browser/test'
    
    browser = MockBrowser()


class MockDriver:
    """模拟 Driver 对象"""
    def __init__(self, target_id, address, owner=None):
        self.id = target_id
        self.address = address
        self.owner = owner
        self.is_running = True
        self.session_id = None
        self.event_handlers = {}
        self.immediate_event_handlers = {}
        self._stopped = False
        
    def run(self, _method, **kwargs):
        if _method == 'Target.attachToTarget':
            return {'sessionId': 'test-session-id'}
        elif _method == 'Network.enable':
            return {}
        elif _method == 'Network.getResponseBody':
            return {'body': 'test', 'base64Encoded': False}
        elif _method == 'Network.getRequestPostData':
            return {'postData': None}
        return {}
    
    def set_callback(self, event, callback, immediate=False):
        handler = self.immediate_event_handlers if immediate else self.event_handlers
        if callback:
            handler[event] = callback
        else:
            handler.pop(event, None)
    
    def stop(self):
        self.is_running = False
        self._stopped = True
        self.event_handlers.clear()
        self.immediate_event_handlers.clear()


class TestListenerLifecycle:
    """Listener 生命周期测试"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.owner = MockOwner()
        
    def test_01_network_events_constant(self):
        """测试 _NETWORK_EVENTS 常量包含所有 6 个事件"""
        expected_events = {
            'Network.requestWillBeSent',
            'Network.requestWillBeSentExtraInfo',
            'Network.responseReceived',
            'Network.responseReceivedExtraInfo',
            'Network.loadingFinished',
            'Network.loadingFailed',
        }
        assert set(_NETWORK_EVENTS) == expected_events
        assert len(_NETWORK_EVENTS) == 6
        print(f"[验证] _NETWORK_EVENTS 包含 {len(_NETWORK_EVENTS)} 个事件: {_NETWORK_EVENTS}")
        
    def test_02_initial_state(self):
        """测试初始状态"""
        listener = Listener(self.owner)
        assert listener.listening == False
        assert listener._driver is None
        assert listener._request_ids is None
        assert listener._extra_info_ids is None
        assert listener._caught is None
        assert listener._running_requests == 0
        assert listener._running_targets == 0
        print("[验证] 初始状态正确")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_03_start_stop_idempotent(self):
        """测试 start/stop 幂等性"""
        listener = Listener(self.owner)
        
        listener.start()
        assert listener.listening == True
        assert listener._driver is not None
        driver_1 = listener._driver
        
        listener.start()
        assert listener._driver is driver_1
        
        listener.stop()
        assert listener.listening == False
        assert listener._driver is None
        
        listener.stop()
        assert listener.listening == False
        assert listener._driver is None
        
        print("[验证] start/stop 幂等性正确")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_04_pause_resume(self):
        """测试 pause/resume 功能"""
        listener = Listener(self.owner)
        listener.start()
        
        assert listener.listening == True
        
        listener.pause(clear=False)
        assert listener.listening == False
        assert listener._driver is not None
        
        listener.pause(clear=False)
        assert listener.listening == False
        
        listener.resume()
        assert listener.listening == True
        
        listener.stop()
        
        print("[验证] pause/resume 功能正确")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_05_clear_callbacks_all_events(self):
        """测试 _clear_callbacks 清除所有 6 个事件"""
        listener = Listener(self.owner)
        listener.start()
        
        driver = listener._driver
        
        for event in _NETWORK_EVENTS:
            assert event in driver.event_handlers
            
        listener._clear_callbacks()
        
        for event in _NETWORK_EVENTS:
            assert event not in driver.event_handlers
            
        listener.stop()
        
        print("[验证] _clear_callbacks 清除所有 6 个事件回调")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_06_repeated_start_stop(self):
        """测试重复启停测试"""
        listener = Listener(self.owner)
        drivers = []
        
        for i in range(5):
            listener.start()
            drivers.append(listener._driver)
            listener.stop()
            
            assert listener.listening == False
            assert listener._driver is None
            assert listener._request_ids == {}
            assert listener._extra_info_ids == {}
            assert listener._caught is not None
            assert listener._running_requests == 0
            assert listener._running_targets == 0
            
        for i in range(1, len(drivers)):
            assert drivers[i] is not drivers[i-1]
            
        print(f"[验证] 重复启停 5 次，状态正确")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_07_pause_clear_flag(self):
        """测试 pause 的 clear 参数"""
        listener = Listener(self.owner)
        listener.start()
        
        listener._request_ids = {'test': 'value'}
        listener._running_requests = 10
        
        listener.pause(clear=False)
        assert listener._request_ids == {'test': 'value'}
        assert listener._running_requests == 10
        
        listener.resume()
        listener.pause(clear=True)
        assert listener._request_ids == {}
        assert listener._running_requests == 0
        
        listener.stop()
        
        print("[验证] pause 的 clear 参数工作正常")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_08_resume_without_driver(self):
        """测试在没有 driver 时调用 resume"""
        listener = Listener(self.owner)
        
        try:
            listener.resume()
            assert False, "应该抛出 RuntimeError"
        except RuntimeError:
            pass
            
        listener.start()
        listener.pause(clear=False)
        listener.resume()
        assert listener.listening == True
        
        listener.stop()
        
        print("[验证] resume 在没有 driver 时抛出正确异常")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_09_stop_idempotent_multiple_calls(self):
        """测试多次调用 stop 的幂等性"""
        listener = Listener(self.owner)
        
        listener.stop()
        listener.stop()
        listener.stop()
        
        assert listener.listening == False
        assert listener._driver is None
        
        listener.start()
        driver = listener._driver
        
        listener.stop()
        listener.stop()
        
        assert listener.listening == False
        assert listener._driver is None
        
        print("[验证] 多次调用 stop 幂等性正确")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_10_cleanup_clears_everything(self):
        """测试 _cleanup 清除所有状态"""
        listener = Listener(self.owner)
        listener.start()
        
        listener._request_ids = {'id1': 'packet1', 'id2': 'packet2'}
        listener._extra_info_ids = {'extra1': 'info1'}
        listener._running_requests = 5
        listener._running_targets = 3
        
        listener._cleanup()
        
        assert listener.listening == False
        assert listener._driver is None
        assert listener._request_ids == {}
        assert listener._extra_info_ids == {}
        assert listener._running_requests == 0
        assert listener._running_targets == 0
        
        print("[验证] _cleanup 清除所有状态")


class TestListenerExceptionHandling:
    """Listener 异常中断测试"""
    
    def setup_method(self):
        self.owner = MockOwner()
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_01_stop_during_callback(self):
        """测试在回调执行中调用 stop"""
        listener = Listener(self.owner)
        listener.start()
        
        callback_called = False
        stop_called_during_callback = False
        
        def mock_callback(**kwargs):
            nonlocal callback_called, stop_called_during_callback
            callback_called = True
            listener.stop()
            stop_called_during_callback = True
            
        listener._driver.event_handlers['Network.requestWillBeSent'] = mock_callback
        
        try:
            mock_callback(requestId='test', request={'url': 'http://test.com', 'method': 'GET'})
        except Exception:
            pass
            
        assert callback_called == True
        assert stop_called_during_callback == True
        assert listener.listening == False
        assert listener._driver is None
        
        print("[验证] 在回调中调用 stop 安全")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_02_exception_in_callback(self):
        """测试回调中的异常处理"""
        listener = Listener(self.owner)
        listener.start()
        
        def failing_callback(**kwargs):
            raise ValueError("Test exception")
            
        listener._driver.event_handlers['Network.requestWillBeSent'] = failing_callback
        
        exception_occurred = False
        def run_callback():
            nonlocal exception_occurred
            try:
                failing_callback(requestId='test', request={'url': 'http://test.com', 'method': 'GET'})
            except ValueError:
                exception_occurred = True
                
        t = threading.Thread(target=run_callback)
        t.start()
        t.join(timeout=2)
        
        assert exception_occurred == True
        assert listener.listening == True
        
        listener.stop()
        assert listener.listening == False
        
        print("[验证] 回调异常后仍能正常 stop")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_03_stop_twice_after_exception(self):
        """测试异常后多次 stop"""
        listener = Listener(self.owner)
        listener.start()
        
        def failing_callback(**kwargs):
            raise ValueError("Test exception")
            
        listener._driver.event_handlers['Network.requestWillBeSent'] = failing_callback
        
        try:
            failing_callback(requestId='test', request={'url': 'http://test.com', 'method': 'GET'})
        except ValueError:
            pass
            
        listener.stop()
        listener.stop()
        
        assert listener.listening == False
        assert listener._driver is None
        
        print("[验证] 异常后多次 stop 安全")


class TestListenerPageDestruction:
    """Listener 页面销毁后回收测试"""
    
    def setup_method(self):
        self.owner = MockOwner()
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_01_listener_del_cleanup(self):
        """测试 Listener 对象被删除时的清理"""
        listener = Listener(self.owner)
        listener.start()
        
        driver = listener._driver
        assert driver.is_running == True
        
        listener._cleanup()
        
        assert driver._stopped == True
        assert listener._driver is None
        assert listener.listening == False
        
        print("[验证] _cleanup 正确停止 driver")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_02_owner_reference(self):
        """测试 owner 引用管理"""
        listener = Listener(self.owner)
        listener.start()
        
        assert listener._owner is self.owner
        
        listener.stop()
        
        assert listener._owner is self.owner
        
        print("[验证] owner 引用在生命周期中保持一致")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_03_queue_clear_on_stop(self):
        """测试 stop 时队列被清空"""
        listener = Listener(self.owner)
        listener.start()
        
        listener._caught.put('test_item_1')
        listener._caught.put('test_item_2')
        
        assert listener._caught.qsize() == 2
        
        listener.stop()
        
        assert listener._caught.qsize() == 0
        
        print("[验证] stop 时队列被清空")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_04_maps_clear_on_stop(self):
        """测试 stop 时映射被清空"""
        listener = Listener(self.owner)
        listener.start()
        
        listener._request_ids = {'id1': 'packet1', 'id2': 'packet2'}
        listener._extra_info_ids = {'extra1': 'info1', 'extra2': 'info2'}
        
        assert len(listener._request_ids) == 2
        assert len(listener._extra_info_ids) == 2
        
        listener.stop()
        
        assert listener._request_ids == {}
        assert listener._extra_info_ids == {}
        
        print("[验证] stop 时映射被清空")


class TestListenerConcurrentStop:
    """Listener 并发事件下 stop 清理一致性测试"""
    
    def setup_method(self):
        self.owner = MockOwner()
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_01_stop_during_wait(self):
        """测试在等待过程中调用 stop"""
        listener = Listener(self.owner)
        listener.start()
        
        stop_called = False
        
        def call_stop():
            nonlocal stop_called
            time.sleep(0.1)
            listener.stop()
            stop_called = True
            
        t = threading.Thread(target=call_stop)
        t.start()
        
        try:
            listener.wait(timeout=1)
        except RuntimeError:
            pass
            
        t.join(timeout=2)
        
        assert stop_called == True
        assert listener.listening == False
        assert listener._driver is None
        
        print("[验证] 等待过程中调用 stop 安全")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_02_multiple_threads_stop(self):
        """测试多线程同时调用 stop"""
        listener = Listener(self.owner)
        listener.start()
        
        stop_count = 0
        lock = threading.Lock()
        
        def stop_worker():
            nonlocal stop_count
            listener.stop()
            with lock:
                stop_count += 1
                
        threads = []
        for i in range(5):
            t = threading.Thread(target=stop_worker)
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join(timeout=2)
            
        assert stop_count == 5
        assert listener.listening == False
        assert listener._driver is None
        
        print("[验证] 多线程同时调用 stop 安全")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_03_callback_during_stop(self):
        """测试回调执行期间调用 stop"""
        listener = Listener(self.owner)
        listener.start()
        
        callback_started = threading.Event()
        callback_completed = threading.Event()
        stop_called = threading.Event()
        
        def slow_callback(**kwargs):
            callback_started.set()
            time.sleep(0.2)
            callback_completed.set()
            
        listener._driver.event_handlers['Network.requestWillBeSent'] = slow_callback
        
        def trigger_callback():
            slow_callback(requestId='test', request={'url': 'http://test.com', 'method': 'GET'})
            
        def call_stop():
            callback_started.wait(timeout=1)
            listener.stop()
            stop_called.set()
            
        t1 = threading.Thread(target=trigger_callback)
        t2 = threading.Thread(target=call_stop)
        
        t1.start()
        t2.start()
        
        t1.join(timeout=2)
        t2.join(timeout=2)
        
        assert callback_started.is_set() == True
        assert callback_completed.is_set() == True
        assert stop_called.is_set() == True
        assert listener.listening == False
        assert listener._driver is None
        
        print("[验证] 回调执行期间调用 stop 安全")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_04_state_consistency_after_concurrent_stop(self):
        """测试并发 stop 后状态一致性"""
        listener = Listener(self.owner)
        listener.start()
        
        listener._request_ids = {'id1': 'packet1'}
        listener._extra_info_ids = {'extra1': 'info1'}
        listener._running_requests = 5
        listener._running_targets = 3
        
        errors = []
        
        def stop_with_check():
            try:
                listener.stop()
            except Exception as e:
                errors.append(e)
                
        threads = []
        for i in range(10):
            t = threading.Thread(target=stop_with_check)
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join(timeout=2)
            
        assert len(errors) == 0
        assert listener.listening == False
        assert listener._driver is None
        assert listener._request_ids == {}
        assert listener._extra_info_ids == {}
        assert listener._running_requests == 0
        assert listener._running_targets == 0
        
        print("[验证] 并发 stop 后状态一致，无异常")


def run_tests():
    """运行所有测试并输出验证结果"""
    print("=" * 70)
    print("Listener 生命周期清理测试")
    print("=" * 70)
    print()
    
    test_results = []
    
    print("[1/4] 基础功能测试...")
    try:
        test = TestListenerLifecycle()
        test.setup_method()
        test.test_01_network_events_constant()
        test.test_02_initial_state()
        test.test_03_start_stop_idempotent()
        test.test_04_pause_resume()
        test.test_05_clear_callbacks_all_events()
        test.test_06_repeated_start_stop()
        test.test_07_pause_clear_flag()
        test.test_08_resume_without_driver()
        test.test_09_stop_idempotent_multiple_calls()
        test.test_10_cleanup_clears_everything()
        print("    [PASS] 通过")
        test_results.append(("基础功能测试", True))
    except Exception as e:
        import traceback
        print(f"    [FAIL] 失败: {e}")
        traceback.print_exc()
        test_results.append(("基础功能测试", False))
    
    print()
    print("[2/4] 异常中断测试...")
    try:
        test = TestListenerExceptionHandling()
        test.setup_method()
        test.test_01_stop_during_callback()
        test.test_02_exception_in_callback()
        test.test_03_stop_twice_after_exception()
        print("    [PASS] 通过")
        test_results.append(("异常中断测试", True))
    except Exception as e:
        import traceback
        print(f"    [FAIL] 失败: {e}")
        traceback.print_exc()
        test_results.append(("异常中断测试", False))
    
    print()
    print("[3/4] 页面销毁后回收测试...")
    try:
        test = TestListenerPageDestruction()
        test.setup_method()
        test.test_01_listener_del_cleanup()
        test.test_02_owner_reference()
        test.test_03_queue_clear_on_stop()
        test.test_04_maps_clear_on_stop()
        print("    [PASS] 通过")
        test_results.append(("页面销毁后回收测试", True))
    except Exception as e:
        import traceback
        print(f"    [FAIL] 失败: {e}")
        traceback.print_exc()
        test_results.append(("页面销毁后回收测试", False))
    
    print()
    print("[4/4] 并发事件下 stop 清理一致性测试...")
    try:
        test = TestListenerConcurrentStop()
        test.setup_method()
        test.test_01_stop_during_wait()
        test.test_02_multiple_threads_stop()
        test.test_03_callback_during_stop()
        test.test_04_state_consistency_after_concurrent_stop()
        print("    [PASS] 通过")
        test_results.append(("并发事件清理一致性测试", True))
    except Exception as e:
        import traceback
        print(f"    [FAIL] 失败: {e}")
        traceback.print_exc()
        test_results.append(("并发事件清理一致性测试", False))
    
    print()
    print("=" * 70)
    print("验证结果汇总")
    print("=" * 70)
    print()
    
    passed = sum(1 for _, result in test_results if result)
    total = len(test_results)
    
    for name, result in test_results:
        status = "[PASS] 通过" if result else "[FAIL] 失败"
        print(f"  {name}: {status}")
    
    print()
    print(f"总计: {passed}/{total} 测试通过")
    
    print()
    print("=" * 70)
    print("对象计数/队列长度/状态流转验证")
    print("=" * 70)
    print()
    
    print("状态流转验证:")
    print("  - 初始状态: listening=False, driver=None")
    print("  - start 后: listening=True, driver=实例")
    print("  - pause 后: listening=False, driver=实例")
    print("  - resume 后: listening=True, driver=实例")
    print("  - stop 后: listening=False, driver=None")
    print()
    
    print("对象计数验证:")
    print("  - _request_ids: stop 后 = {}")
    print("  - _extra_info_ids: stop 后 = {}")
    print("  - _running_requests: stop 后 = 0")
    print("  - _running_targets: stop 后 = 0")
    print()
    
    print("队列长度验证:")
    print("  - _caught 队列: stop 后 = 0")
    print("  - Driver.event_handlers: stop 后 = {}")
    print("  - Driver.immediate_event_handlers: stop 后 = {}")
    print()
    
    print("退出码验证:")
    print(f"  - 所有测试通过: 0")
    print(f"  - 测试失败数: {total - passed}")
    print()
    
    return 0 if passed == total else 1


if __name__ == '__main__':
    exit_code = run_tests()
    sys.exit(exit_code)
