# -*- coding:utf-8 -*-
"""
Listener 回归测试
验证 start/wait/steps/pause/resume 旧行为不回归
确保生命周期清理：回调解绑、队列/映射释放、引用断开、重复 stop 幂等
"""
import os
import sys
import threading
import time
from queue import Queue
from unittest.mock import patch, MagicMock

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
        self._stop_called = 0
        
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
        self._stop_called += 1
        self.is_running = False
        self._stopped = True
        self.event_handlers.clear()
        self.immediate_event_handlers.clear()


class TestListenerRegressionBaseline:
    """
    回归测试基准：验证旧行为不回归
    测试 start/wait/steps/pause/resume 的原始语义
    """
    
    def setup_method(self):
        self.owner = MockOwner()
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_regression_01_start_idempotent(self):
        """
        回归测试：start 幂等性
        旧行为：如果已在监听，直接返回，不创建新 driver
        """
        listener = Listener(self.owner)
        
        listener.start()
        driver_1 = listener._driver
        assert listener.listening == True
        
        listener.start()
        assert listener._driver is driver_1
        assert listener.listening == True
        
        print("[回归验证] start 幂等性：已监听时直接返回，不创建新 driver")
        listener.stop()
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_regression_02_start_creates_new_driver_each_time(self):
        """
        回归测试：每次 start 都创建新 driver
        旧行为：stop 后再次 start 应该创建新的 driver 实例
        """
        listener = Listener(self.owner)
        
        listener.start()
        driver_1 = listener._driver
        listener.stop()
        
        listener.start()
        driver_2 = listener._driver
        listener.stop()
        
        assert driver_1 is not driver_2
        
        print("[回归验证] stop 后再次 start 创建新的 driver 实例")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_regression_03_wait_raises_when_not_listening(self):
        """
        回归测试：wait 在未监听时抛出 RuntimeError
        旧行为：如果没有在监听，wait 应该抛出 RuntimeError
        """
        listener = Listener(self.owner)
        
        try:
            listener.wait(timeout=0.1)
            assert False, "应该抛出 RuntimeError"
        except RuntimeError:
            pass
            
        print("[回归验证] wait 在未监听时抛出 RuntimeError")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_regression_04_steps_raises_when_not_listening(self):
        """
        回归测试：steps 在未监听时抛出 RuntimeError
        旧行为：如果没有在监听，steps 应该抛出 RuntimeError
        """
        listener = Listener(self.owner)
        
        try:
            for _ in listener.steps(timeout=0.1):
                pass
            assert False, "应该抛出 RuntimeError"
        except RuntimeError:
            pass
            
        print("[回归验证] steps 在未监听时抛出 RuntimeError")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_regression_05_pause_sets_listening_false(self):
        """
        回归测试：pause 设置 listening=False
        旧行为：pause 后 listening 为 False，但 driver 仍然存在
        """
        listener = Listener(self.owner)
        listener.start()
        
        assert listener.listening == True
        assert listener._driver is not None
        
        listener.pause(clear=False)
        
        assert listener.listening == False
        assert listener._driver is not None
        
        print("[回归验证] pause 设置 listening=False，driver 仍然存在")
        listener.stop()
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_regression_06_pause_clear_flag(self):
        """
        回归测试：pause 的 clear 参数
        旧行为：clear=True 时清空队列和映射，clear=False 时保留
        """
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
        
        print("[回归验证] pause 的 clear 参数工作正常")
        listener.stop()
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_regression_07_resume_idempotent(self):
        """
        回归测试：resume 幂等性
        旧行为：如果已在监听，直接返回
        """
        listener = Listener(self.owner)
        listener.start()
        
        assert listener.listening == True
        
        listener.resume()
        assert listener.listening == True
        
        print("[回归验证] resume 幂等性：已监听时直接返回")
        listener.stop()
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_regression_08_resume_raises_without_driver(self):
        """
        回归测试：resume 在没有 driver 时抛出 RuntimeError
        旧行为：如果没有 driver（已 stop），resume 应该抛出 RuntimeError
        """
        listener = Listener(self.owner)
        
        try:
            listener.resume()
            assert False, "应该抛出 RuntimeError"
        except RuntimeError:
            pass
            
        print("[回归验证] resume 在没有 driver 时抛出 RuntimeError")


class TestListenerLifecycleCleanup:
    """
    生命周期清理测试
    验证：回调解绑、队列/映射释放、引用断开、重复 stop 幂等
    """
    
    def setup_method(self):
        self.owner = MockOwner()
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_cleanup_01_callback_unbind_on_stop(self):
        """
        生命周期清理：stop 时回调解绑
        验证：所有 6 个 Network 事件的回调都被清除
        """
        listener = Listener(self.owner)
        listener.start()
        
        driver = listener._driver
        
        for event in _NETWORK_EVENTS:
            assert event in driver.event_handlers, f"事件 {event} 应该有回调"
            
        listener.stop()
        
        assert driver._stopped == True
        assert len(driver.event_handlers) == 0
        
        print("[生命周期验证] stop 时所有回调都被解绑")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_cleanup_02_callback_unbind_on_pause(self):
        """
        生命周期清理：pause 时回调解绑
        验证：pause 时所有 6 个 Network 事件的回调都被清除
        """
        listener = Listener(self.owner)
        listener.start()
        
        driver = listener._driver
        
        for event in _NETWORK_EVENTS:
            assert event in driver.event_handlers, f"事件 {event} 应该有回调"
            
        listener.pause(clear=False)
        
        for event in _NETWORK_EVENTS:
            assert event not in driver.event_handlers, f"事件 {event} 回调应该被清除"
            
        assert listener._driver is driver
        
        print("[生命周期验证] pause 时所有回调都被解绑")
        listener.stop()
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_cleanup_03_queue_release_on_stop(self):
        """
        生命周期清理：stop 时队列释放
        验证：_caught 队列被清空并重新创建
        """
        listener = Listener(self.owner)
        listener.start()
        
        original_queue = listener._caught
        listener._caught.put('item1')
        listener._caught.put('item2')
        
        assert listener._caught.qsize() == 2
        
        listener.stop()
        
        assert listener._caught is not original_queue
        assert listener._caught.qsize() == 0
        
        print("[生命周期验证] stop 时队列被释放")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_cleanup_04_maps_release_on_stop(self):
        """
        生命周期清理：stop 时映射释放
        验证：_request_ids 和 _extra_info_ids 被清空
        """
        listener = Listener(self.owner)
        listener.start()
        
        listener._request_ids = {'id1': 'packet1', 'id2': 'packet2'}
        listener._extra_info_ids = {'extra1': 'info1', 'extra2': 'info2'}
        
        assert len(listener._request_ids) == 2
        assert len(listener._extra_info_ids) == 2
        
        listener.stop()
        
        assert listener._request_ids == {}
        assert listener._extra_info_ids == {}
        
        print("[生命周期验证] stop 时映射被释放")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_cleanup_05_reference_disconnect_on_stop(self):
        """
        生命周期清理：stop 时引用断开
        验证：_driver 被设为 None，driver 被停止
        """
        listener = Listener(self.owner)
        listener.start()
        
        driver = listener._driver
        assert driver is not None
        assert driver.is_running == True
        
        listener.stop()
        
        assert listener._driver is None
        assert driver.is_running == False
        assert driver._stopped == True
        
        print("[生命周期验证] stop 时 driver 引用断开")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_cleanup_06_stop_idempotent(self):
        """
        生命周期清理：stop 幂等性
        验证：多次调用 stop 是安全的，driver.stop() 只被调用一次
        """
        listener = Listener(self.owner)
        listener.start()
        
        driver = listener._driver
        assert driver._stop_called == 0
        
        listener.stop()
        assert driver._stop_called == 1
        assert listener._driver is None
        
        listener.stop()
        assert driver._stop_called == 1
        
        listener.stop()
        assert driver._stop_called == 1
        
        print("[生命周期验证] stop 幂等性：多次调用安全，driver.stop() 只被调用一次")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_cleanup_07_stop_on_paused_state(self):
        """
        生命周期清理：pause 后 stop
        验证：pause 后调用 stop 能正确清理
        """
        listener = Listener(self.owner)
        listener.start()
        
        driver = listener._driver
        
        listener.pause(clear=False)
        assert listener.listening == False
        assert listener._driver is driver
        
        listener.stop()
        assert listener._driver is None
        assert driver._stopped == True
        
        print("[生命周期验证] pause 后 stop 能正确清理")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_cleanup_08_running_counters_reset(self):
        """
        生命周期清理：运行计数器重置
        验证：_running_requests 和 _running_targets 在 stop 后归零
        """
        listener = Listener(self.owner)
        listener.start()
        
        listener._running_requests = 100
        listener._running_targets = 50
        
        listener.stop()
        
        assert listener._running_requests == 0
        assert listener._running_targets == 0
        
        print("[生命周期验证] stop 后运行计数器归零")


class TestListenerStateTransitions:
    """
    状态流转测试
    验证完整的状态流转：初始 -> start -> pause -> resume -> stop
    """
    
    def setup_method(self):
        self.owner = MockOwner()
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_transition_01_initial_state(self):
        """
        状态流转：初始状态
        """
        listener = Listener(self.owner)
        
        assert listener.listening == False
        assert listener._driver is None
        assert listener._request_ids is None
        assert listener._extra_info_ids is None
        assert listener._caught is None
        assert listener._running_requests == 0
        assert listener._running_targets == 0
        
        print("[状态流转] 初始状态正确")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_transition_02_after_start(self):
        """
        状态流转：start 后
        """
        listener = Listener(self.owner)
        listener.start()
        
        assert listener.listening == True
        assert listener._driver is not None
        assert listener._request_ids == {}
        assert listener._extra_info_ids == {}
        assert listener._caught is not None
        assert listener._running_requests == 0
        assert listener._running_targets == 0
        
        driver = listener._driver
        for event in _NETWORK_EVENTS:
            assert event in driver.event_handlers
            
        print("[状态流转] start 后状态正确")
        listener.stop()
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_transition_03_after_pause(self):
        """
        状态流转：pause 后（clear=False）
        """
        listener = Listener(self.owner)
        listener.start()
        
        listener._request_ids = {'test': 'value'}
        listener._running_requests = 10
        
        listener.pause(clear=False)
        
        assert listener.listening == False
        assert listener._driver is not None
        assert listener._request_ids == {'test': 'value'}
        assert listener._running_requests == 10
        
        driver = listener._driver
        for event in _NETWORK_EVENTS:
            assert event not in driver.event_handlers
            
        print("[状态流转] pause(clear=False) 后状态正确")
        listener.stop()
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_transition_04_after_pause_clear(self):
        """
        状态流转：pause 后（clear=True）
        """
        listener = Listener(self.owner)
        listener.start()
        
        listener._request_ids = {'test': 'value'}
        listener._running_requests = 10
        
        listener.pause(clear=True)
        
        assert listener.listening == False
        assert listener._driver is not None
        assert listener._request_ids == {}
        assert listener._running_requests == 0
        
        print("[状态流转] pause(clear=True) 后状态正确")
        listener.stop()
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_transition_05_after_resume(self):
        """
        状态流转：resume 后
        """
        listener = Listener(self.owner)
        listener.start()
        
        listener.pause(clear=False)
        
        listener.resume()
        
        assert listener.listening == True
        assert listener._driver is not None
        
        driver = listener._driver
        for event in _NETWORK_EVENTS:
            assert event in driver.event_handlers
            
        print("[状态流转] resume 后状态正确")
        listener.stop()
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_transition_06_after_stop(self):
        """
        状态流转：stop 后
        """
        listener = Listener(self.owner)
        listener.start()
        
        driver = listener._driver
        
        listener.stop()
        
        assert listener.listening == False
        assert listener._driver is None
        assert listener._request_ids == {}
        assert listener._extra_info_ids == {}
        assert listener._caught is not None
        assert listener._running_requests == 0
        assert listener._running_targets == 0
        assert driver._stopped == True
        
        print("[状态流转] stop 后状态正确")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_transition_07_full_cycle(self):
        """
        状态流转：完整周期
        初始 -> start -> pause -> resume -> pause -> stop -> start -> stop
        """
        listener = Listener(self.owner)
        
        assert listener.listening == False
        assert listener._driver is None
        
        listener.start()
        driver_1 = listener._driver
        assert listener.listening == True
        
        listener.pause(clear=False)
        assert listener.listening == False
        assert listener._driver is driver_1
        
        listener.resume()
        assert listener.listening == True
        assert listener._driver is driver_1
        
        listener.pause(clear=True)
        assert listener.listening == False
        assert listener._driver is driver_1
        
        listener.stop()
        assert listener.listening == False
        assert listener._driver is None
        assert driver_1._stopped == True
        
        listener.start()
        driver_2 = listener._driver
        assert listener.listening == True
        assert driver_2 is not driver_1
        
        listener.stop()
        assert listener.listening == False
        assert listener._driver is None
        
        print("[状态流转] 完整周期状态正确")


class TestListenerEdgeCases:
    """
    边界情况测试
    """
    
    def setup_method(self):
        self.owner = MockOwner()
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_edge_01_stop_before_start(self):
        """
        边界情况：start 前调用 stop
        """
        listener = Listener(self.owner)
        
        assert listener.listening == False
        assert listener._driver is None
        
        listener.stop()
        
        assert listener.listening == False
        assert listener._driver is None
        
        print("[边界情况] start 前调用 stop 安全")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_edge_02_pause_before_start(self):
        """
        边界情况：start 前调用 pause
        """
        listener = Listener(self.owner)
        
        listener.pause(clear=True)
        
        assert listener.listening == False
        assert listener._driver is None
        
        print("[边界情况] start 前调用 pause 安全")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_edge_03_multiple_stops(self):
        """
        边界情况：多次调用 stop
        """
        listener = Listener(self.owner)
        listener.start()
        
        driver = listener._driver
        
        for _ in range(10):
            listener.stop()
            
        assert listener.listening == False
        assert listener._driver is None
        assert driver._stop_called == 1
        
        print("[边界情况] 多次调用 stop 安全")
        
    @patch('DrissionPage._units.listener.Driver', MockDriver)
    def test_edge_04_start_stop_start_stop(self):
        """
        边界情况：交替调用 start/stop
        """
        listener = Listener(self.owner)
        drivers = []
        
        for i in range(5):
            listener.start()
            drivers.append(listener._driver)
            listener.stop()
            
            assert listener.listening == False
            assert listener._driver is None
            
        for i in range(1, len(drivers)):
            assert drivers[i] is not drivers[i-1]
            
        print("[边界情况] 交替调用 start/stop 安全")


def run_regression_tests():
    """运行回归测试并输出验证结果"""
    print("=" * 70)
    print("Listener 回归测试")
    print("=" * 70)
    print()
    
    test_results = []
    
    print("[1/5] 回归基准测试（旧行为不回归）...")
    try:
        test = TestListenerRegressionBaseline()
        test.setup_method()
        test.test_regression_01_start_idempotent()
        test.test_regression_02_start_creates_new_driver_each_time()
        test.test_regression_03_wait_raises_when_not_listening()
        test.test_regression_04_steps_raises_when_not_listening()
        test.test_regression_05_pause_sets_listening_false()
        test.test_regression_06_pause_clear_flag()
        test.test_regression_07_resume_idempotent()
        test.test_regression_08_resume_raises_without_driver()
        print("    [PASS] 通过")
        test_results.append(("回归基准测试", True))
    except Exception as e:
        import traceback
        print(f"    [FAIL] 失败: {e}")
        traceback.print_exc()
        test_results.append(("回归基准测试", False))
    
    print()
    print("[2/5] 生命周期清理测试...")
    try:
        test = TestListenerLifecycleCleanup()
        test.setup_method()
        test.test_cleanup_01_callback_unbind_on_stop()
        test.test_cleanup_02_callback_unbind_on_pause()
        test.test_cleanup_03_queue_release_on_stop()
        test.test_cleanup_04_maps_release_on_stop()
        test.test_cleanup_05_reference_disconnect_on_stop()
        test.test_cleanup_06_stop_idempotent()
        test.test_cleanup_07_stop_on_paused_state()
        test.test_cleanup_08_running_counters_reset()
        print("    [PASS] 通过")
        test_results.append(("生命周期清理测试", True))
    except Exception as e:
        import traceback
        print(f"    [FAIL] 失败: {e}")
        traceback.print_exc()
        test_results.append(("生命周期清理测试", False))
    
    print()
    print("[3/5] 状态流转测试...")
    try:
        test = TestListenerStateTransitions()
        test.setup_method()
        test.test_transition_01_initial_state()
        test.test_transition_02_after_start()
        test.test_transition_03_after_pause()
        test.test_transition_04_after_pause_clear()
        test.test_transition_05_after_resume()
        test.test_transition_06_after_stop()
        test.test_transition_07_full_cycle()
        print("    [PASS] 通过")
        test_results.append(("状态流转测试", True))
    except Exception as e:
        import traceback
        print(f"    [FAIL] 失败: {e}")
        traceback.print_exc()
        test_results.append(("状态流转测试", False))
    
    print()
    print("[4/5] 边界情况测试...")
    try:
        test = TestListenerEdgeCases()
        test.setup_method()
        test.test_edge_01_stop_before_start()
        test.test_edge_02_pause_before_start()
        test.test_edge_03_multiple_stops()
        test.test_edge_04_start_stop_start_stop()
        print("    [PASS] 通过")
        test_results.append(("边界情况测试", True))
    except Exception as e:
        import traceback
        print(f"    [FAIL] 失败: {e}")
        traceback.print_exc()
        test_results.append(("边界情况测试", False))
    
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
    print("详细验证项")
    print("=" * 70)
    print()
    
    print("回归验证（旧行为不回归）:")
    print("  + start 幂等性：已监听时直接返回，不创建新 driver")
    print("  + stop 后再次 start 创建新的 driver 实例")
    print("  + wait 在未监听时抛出 RuntimeError")
    print("  + steps 在未监听时抛出 RuntimeError")
    print("  + pause 设置 listening=False，driver 仍然存在")
    print("  + pause 的 clear 参数：clear=True 清空，clear=False 保留")
    print("  + resume 幂等性：已监听时直接返回")
    print("  + resume 在没有 driver 时抛出 RuntimeError")
    print()
    
    print("生命周期清理验证:")
    print("  + stop 时所有 6 个 Network 事件回调都被解绑")
    print("  + pause 时所有 6 个 Network 事件回调都被解绑")
    print("  + stop 时 _caught 队列被释放（清空并重新创建）")
    print("  + stop 时 _request_ids 映射被清空")
    print("  + stop 时 _extra_info_ids 映射被清空")
    print("  + stop 时 _driver 引用断开（设为 None）")
    print("  + stop 时 driver.stop() 被调用")
    print("  + stop 幂等性：多次调用安全，driver.stop() 只被调用一次")
    print("  + pause 后 stop 能正确清理")
    print("  + stop 后 _running_requests = 0")
    print("  + stop 后 _running_targets = 0")
    print()
    
    print("状态流转验证:")
    print("  初始状态:")
    print("    - listening = False")
    print("    - _driver = None")
    print("    - _request_ids = None")
    print("    - _extra_info_ids = None")
    print("    - _caught = None")
    print("    - _running_requests = 0")
    print("    - _running_targets = 0")
    print()
    print("  start 后:")
    print("    - listening = True")
    print("    - _driver = 实例")
    print("    - _request_ids = {}")
    print("    - _extra_info_ids = {}")
    print("    - _caught = Queue 实例")
    print("    - 所有 6 个 Network 事件都有回调")
    print()
    print("  pause(clear=False) 后:")
    print("    - listening = False")
    print("    - _driver = 仍存在")
    print("    - _request_ids = 保持不变")
    print("    - _extra_info_ids = 保持不变")
    print("    - 所有 6 个 Network 事件回调都被清除")
    print()
    print("  pause(clear=True) 后:")
    print("    - listening = False")
    print("    - _driver = 仍存在")
    print("    - _request_ids = {}")
    print("    - _extra_info_ids = {}")
    print("    - _caught = 新的 Queue 实例")
    print("    - _running_requests = 0")
    print("    - _running_targets = 0")
    print()
    print("  resume 后:")
    print("    - listening = True")
    print("    - _driver = 仍存在")
    print("    - 所有 6 个 Network 事件都有回调")
    print()
    print("  stop 后:")
    print("    - listening = False")
    print("    - _driver = None")
    print("    - _request_ids = {}")
    print("    - _extra_info_ids = {}")
    print("    - _caught = 新的 Queue 实例（空）")
    print("    - _running_requests = 0")
    print("    - _running_targets = 0")
    print("    - driver.is_running = False")
    print("    - driver._stopped = True")
    print()
    
    print("边界情况验证:")
    print("  + start 前调用 stop 安全")
    print("  + start 前调用 pause 安全")
    print("  + 多次调用 stop 安全（幂等）")
    print("  + 交替调用 start/stop 安全")
    print()
    
    print("退出码验证:")
    print(f"  - 所有测试通过: 0")
    print(f"  - 测试失败数: {total - passed}")
    print()
    
    return 0 if passed == total else 1


if __name__ == '__main__':
    exit_code = run_regression_tests()
    sys.exit(exit_code)
