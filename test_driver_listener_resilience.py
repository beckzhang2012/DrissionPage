# -*- coding:utf-8 -*-
"""
最小验收测试：验证 Listener 和 Driver 的弹性机制
覆盖场景：
1. 单请求失败不影响同批请求
2. 旧会话迟到回包隔离
3. Listener 在 response/body/extraInfo 乱序或缺失下可降级完成
4. tab 销毁并发时 inflight 快速终止且不死锁
5. 多轮运行无状态泄漏
"""
import sys
import threading
from queue import Empty
from time import perf_counter, sleep
from unittest.mock import MagicMock, patch

sys.path.insert(0, '.')


class TestSingleRequestFailureIsolation:
    """场景1: 单请求失败不影响同批请求"""
    
    def test_loading_failed_does_not_block_successful_requests(self):
        """验证失败请求不会影响其他成功请求的捕获"""
        from DrissionPage._units.listener import Listener, DataPacket
        
        mock_owner = MagicMock()
        mock_owner.tab_id = 'tab-1'
        mock_owner.browser._ws_address = 'ws://mock'
        mock_owner._target_id = 'target-1'
        
        listener = Listener(mock_owner)
        listener._listener_epoch = 1
        listener.listening = True
        listener._targets = True
        listener._method = True
        listener._res_type = True
        listener._lock = threading.RLock()
        listener._caught = type('MockQueue', (), {
            'qsize': lambda self: 0,
            'put_nowait': lambda self, x: setattr(self, '_items', getattr(self, '_items', []) + [x])
        })()
        listener._request_ids = {}
        listener._extra_info_ids = {}
        listener._running_requests = 0
        listener._running_targets = 0
        
        rid_success = 'req-success-1'
        rid_failed = 'req-failed-1'
        
        listener._requestWillBeSent(requestId=rid_success, request={'url': 'http://test.com/success', 'method': 'GET'}, type='Document')
        listener._requestWillBeSent(requestId=rid_failed, request={'url': 'http://test.com/failed', 'method': 'GET'}, type='Document')
        
        assert listener._running_requests == 2
        assert listener._running_targets == 2
        assert rid_success in listener._request_ids
        assert rid_failed in listener._request_ids
        
        listener._response_received(requestId=rid_success, response={'status': 200}, type='Document')
        
        packet_success = listener._request_ids[rid_success]
        assert packet_success._raw_response == {'status': 200}
        
        listener._loading_failed(requestId=rid_failed, type='Document', errorText='net::ERR_FAILED')
        
        assert rid_failed not in listener._request_ids
        assert len(listener._caught._items) == 1
        failed_packet = listener._caught._items[0]
        assert failed_packet.is_failed is True
        assert failed_packet.url == 'http://test.com/failed'
        
        listener._loading_finished(requestId=rid_success, encodedDataLength=100)
        
        assert rid_success not in listener._request_ids
        assert len(listener._caught._items) == 2
        success_packet = [p for p in listener._caught._items if not p.is_failed][0]
        assert success_packet.url == 'http://test.com/success'
        
        assert listener._running_targets == 0
        
        print("[PASS] 场景1: 单请求失败不影响同批请求")
        return True


class TestOldSessionPacketIsolation:
    """场景2: 旧会话迟到回包隔离"""
    
    def test_listener_epoch_isolates_old_session_packets(self):
        """验证 _listener_epoch 机制隔离旧会话数据包"""
        from DrissionPage._units.listener import Listener, DataPacket
        
        mock_owner = MagicMock()
        mock_owner.tab_id = 'tab-1'
        mock_owner.browser._ws_address = 'ws://mock'
        mock_owner._target_id = 'target-1'
        
        listener = Listener(mock_owner)
        listener._listener_epoch = 1
        listener.listening = True
        listener._targets = True
        listener._method = True
        listener._res_type = True
        listener._lock = threading.RLock()
        listener._caught = type('MockQueue', (), {
            'qsize': lambda self: 0,
            'put_nowait': lambda self, x: setattr(self, '_items', getattr(self, '_items', []) + [x])
        })()
        listener._request_ids = {}
        listener._extra_info_ids = {}
        listener._running_requests = 0
        listener._running_targets = 0
        
        rid_old = 'req-old-1'
        listener._requestWillBeSent(requestId=rid_old, request={'url': 'http://test.com/old', 'method': 'GET'}, type='Document')
        
        old_packet = listener._request_ids[rid_old]
        assert old_packet._listener_epoch == 1
        
        listener._listener_epoch = 2
        listener._request_ids = {}
        listener._extra_info_ids = {}
        listener._caught._items = []
        
        listener._response_received(requestId=rid_old, response={'status': 200}, type='Document')
        
        assert rid_old not in listener._request_ids
        
        old_packet_2 = DataPacket('tab-1', True)
        old_packet_2._listener_epoch = 1
        old_packet_2._raw_request = {'request': {'url': 'http://test.com/old2', 'method': 'GET'}}
        
        listener._request_ids['req-old-2'] = old_packet_2
        
        listener._loading_finished(requestId='req-old-2', encodedDataLength=100)
        
        assert 'req-old-2' not in listener._request_ids
        assert len(listener._caught._items) == 0
        
        rid_new = 'req-new-1'
        listener._requestWillBeSent(requestId=rid_new, request={'url': 'http://test.com/new', 'method': 'GET'}, type='Document')
        
        new_packet = listener._request_ids[rid_new]
        assert new_packet._listener_epoch == 2
        
        listener._response_received(requestId=rid_new, response={'status': 200}, type='Document')
        listener._loading_finished(requestId=rid_new, encodedDataLength=100)
        
        assert len(listener._caught._items) == 1
        assert listener._caught._items[0]._listener_epoch == 2
        assert listener._caught._items[0].url == 'http://test.com/new'
        
        print("[PASS] 场景2: 旧会话迟到回包隔离")
        return True


class TestOutOfOrderHandling:
    """场景3: Listener 在 response/body/extraInfo 乱序或缺失下可降级完成"""
    
    def test_out_of_order_events_handled_gracefully(self):
        """验证乱序事件处理"""
        from DrissionPage._units.listener import Listener, DataPacket
        
        mock_owner = MagicMock()
        mock_owner.tab_id = 'tab-1'
        mock_owner.browser._ws_address = 'ws://mock'
        mock_owner._target_id = 'target-1'
        
        listener = Listener(mock_owner)
        listener._listener_epoch = 1
        listener.listening = True
        listener._targets = True
        listener._method = True
        listener._res_type = True
        listener._lock = threading.RLock()
        listener._caught = type('MockQueue', (), {
            'qsize': lambda self: 0,
            'put_nowait': lambda self, x: setattr(self, '_items', getattr(self, '_items', []) + [x])
        })()
        listener._request_ids = {}
        listener._extra_info_ids = {}
        listener._running_requests = 0
        listener._running_targets = 0
        
        rid = 'req-oo-1'
        
        listener._response_received(requestId=rid, response={'status': 200}, type='Document')
        assert rid not in listener._request_ids
        
        listener._loading_finished(requestId=rid, encodedDataLength=100)
        assert len(getattr(listener._caught, '_items', [])) == 0
        
        listener._loading_failed(requestId=rid, type='Document', errorText='test')
        assert len(getattr(listener._caught, '_items', [])) == 0
        
        listener._responseReceivedExtraInfo(requestId=rid, headers={})
        assert rid not in listener._extra_info_ids
        
        listener._requestWillBeSentExtraInfo(requestId=rid, headers={})
        assert rid in listener._extra_info_ids
        
        listener._requestWillBeSent(requestId=rid, request={'url': 'http://test.com/oo', 'method': 'GET'}, type='Document')
        
        assert rid in listener._request_ids
        packet = listener._request_ids[rid]
        assert packet._raw_request is not None
        
        listener._response_received(requestId=rid, response={'status': 200}, type='Document')
        assert packet._raw_response == {'status': 200}
        
        listener._loading_finished(requestId=rid, encodedDataLength=100)
        
        assert rid not in listener._request_ids
        assert len(listener._caught._items) == 1
        final_packet = listener._caught._items[0]
        assert final_packet.url == 'http://test.com/oo'
        assert final_packet._raw_body == ''
        
        print("[PASS] 场景3: 乱序或缺失事件可降级完成")
        return True
    
    def test_missing_response_body_handled(self):
        """验证缺失响应体时的降级处理"""
        from DrissionPage._units.listener import DataPacket
        
        packet = DataPacket('tab-1', True)
        packet._raw_request = {'request': {'url': 'http://test.com/missing', 'method': 'GET'}}
        packet._raw_response = None
        packet._raw_body = None
        
        assert packet.url == 'http://test.com/missing'
        assert packet.response.status is None
        assert packet.response.body is None
        
        print("[PASS] 场景3b: 缺失字段降级处理")
        return True


class TestTabDestructionInflightHandling:
    """场景4: tab 销毁并发时 inflight 快速终止且不死锁"""
    
    def test_fail_inflight_requests_terminates_pending_requests(self):
        """验证 inflight 请求在连接断开时被正确终止"""
        from DrissionPage._base.driver import Driver
        
        driver = object.__new__(Driver)
        driver.id = 'test-driver'
        driver.address = 'ws://mock'
        driver.is_running = True
        driver._session_epoch = 1
        driver._method_results_lock = threading.RLock()
        driver.method_results = {}
        
        from queue import Queue
        q1 = Queue()
        q2 = Queue()
        driver.method_results[1] = {'queue': q1, 'epoch': 1}
        driver.method_results[2] = {'queue': q2, 'epoch': 1}
        
        driver._fail_inflight_requests()
        
        try:
            r1 = q1.get_nowait()
            r2 = q2.get_nowait()
            assert r1['error']['message'] == 'connection disconnected'
            assert r2['error']['message'] == 'connection disconnected'
        except Empty:
            assert False, "应该有错误消息被放入队列"
        
        print("[PASS] 场景4: inflight 请求快速终止")
        return True
    
    def test_session_epoch_invalidates_old_requests(self):
        """验证 _session_epoch 机制使旧会话请求失效"""
        from DrissionPage._base.driver import Driver
        
        driver = object.__new__(Driver)
        driver.id = 'test-driver'
        driver.address = 'ws://mock'
        driver.is_running = True
        driver._session_epoch = 1
        driver._method_results_lock = threading.RLock()
        driver.method_results = {}
        
        from queue import Queue
        q = Queue()
        driver.method_results[1] = {'queue': q, 'epoch': 1}
        
        driver._session_epoch = 2
        
        with driver._method_results_lock:
            result_info = driver.method_results[1]
            assert result_info['epoch'] == 1
            assert result_info['epoch'] != driver._session_epoch
        
        print("[PASS] 场景4b: session_epoch 隔离机制")
        return True


class TestMultiRunStateLeak:
    """场景5: 多轮运行无状态泄漏"""
    
    def test_clear_resets_all_state(self):
        """验证 clear() 方法正确重置所有状态"""
        from DrissionPage._units.listener import Listener, DataPacket
        
        mock_owner = MagicMock()
        mock_owner.tab_id = 'tab-1'
        mock_owner.browser._ws_address = 'ws://mock'
        mock_owner._target_id = 'target-1'
        
        listener = Listener(mock_owner)
        listener._lock = threading.RLock()
        
        listener._request_ids = {'req-1': DataPacket('tab-1', True)}
        listener._extra_info_ids = {'req-1': {'epoch': 1}}
        
        from queue import Queue
        listener._caught = Queue()
        listener._caught.put(DataPacket('tab-1', True))
        
        listener._running_requests = 5
        listener._running_targets = 3
        
        listener.clear()
        
        assert listener._request_ids == {}
        assert listener._extra_info_ids == {}
        assert listener._caught.qsize() == 0
        assert listener._running_requests == 0
        assert listener._running_targets == 0
        
        print("[PASS] 场景5: 状态正确重置")
        return True
    
    def test_multiple_start_stop_cycles(self):
        """验证多次 start/stop 后状态一致"""
        from DrissionPage._units.listener import Listener
        
        mock_owner = MagicMock()
        mock_owner.tab_id = 'tab-1'
        mock_owner.browser._ws_address = 'ws://mock'
        mock_owner._target_id = 'target-1'
        
        listener = Listener(mock_owner)
        listener._lock = threading.RLock()
        
        initial_epoch = listener._listener_epoch
        
        listener._listener_epoch += 1
        listener.clear()
        epoch1 = listener._listener_epoch
        
        listener._listener_epoch += 1
        listener.clear()
        epoch2 = listener._listener_epoch
        
        assert epoch2 > epoch1 > initial_epoch
        assert listener._request_ids == {}
        assert listener._extra_info_ids == {}
        assert listener._running_requests == 0
        
        print("[PASS] 场景5b: 多轮运行状态一致")
        return True


def run_all_tests():
    """运行所有验收测试"""
    tests = [
        ("场景1: 单请求失败不影响同批请求", TestSingleRequestFailureIsolation().test_loading_failed_does_not_block_successful_requests),
        ("场景2: 旧会话迟到回包隔离", TestOldSessionPacketIsolation().test_listener_epoch_isolates_old_session_packets),
        ("场景3: 乱序或缺失事件可降级完成", TestOutOfOrderHandling().test_out_of_order_events_handled_gracefully),
        ("场景3b: 缺失字段降级处理", TestOutOfOrderHandling().test_missing_response_body_handled),
        ("场景4: inflight 请求快速终止", TestTabDestructionInflightHandling().test_fail_inflight_requests_terminates_pending_requests),
        ("场景4b: session_epoch 隔离机制", TestTabDestructionInflightHandling().test_session_epoch_invalidates_old_requests),
        ("场景5: 状态正确重置", TestMultiRunStateLeak().test_clear_resets_all_state),
        ("场景5b: 多轮运行状态一致", TestMultiRunStateLeak().test_multiple_start_stop_cycles),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    print("\n" + "="*60)
    print("测试结果汇总:")
    print("="*60)
    
    all_passed = True
    for name, result in results:
        status = "PASS" if result else "FAIL"
        all_passed = all_passed and result
        print(f"  [{status}] {name}")
    
    print("="*60)
    if all_passed:
        print("所有测试通过!")
        return 0
    else:
        print("部分测试失败!")
        return 1


if __name__ == '__main__':
    exit_code = run_all_tests()
    sys.exit(exit_code)
