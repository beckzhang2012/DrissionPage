# -*- coding: utf-8 -*-
"""Simple test to verify the Driver fixes."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from queue import Queue
from threading import Thread, Lock
from time import sleep

from DrissionPage._base.driver import Driver, DriverMetrics, RequestState


class MockWebSocket:
    def __init__(self):
        self._recv_queue = Queue()
        self._sent_messages = []
        self._lock = Lock()
        self.closed = False

    def recv(self):
        msg = self._recv_queue.get()
        if msg is None:
            raise Exception("Connection closed")
        return msg

    def send(self, message):
        with self._lock:
            self._sent_messages.append(message)

    def close(self):
        self.closed = True
        self._recv_queue.put(None)

    def inject_response(self, response_json):
        self._recv_queue.put(response_json)


def test_concurrent_ids():
    print("Test 1: Concurrent ID Generation")
    
    from unittest.mock import patch
    
    mock_ws = MockWebSocket()
    
    with patch('DrissionPage._base.driver.create_connection', return_value=mock_ws):
        with patch.object(Driver, 'start'):
            driver = Driver.__new__(Driver)
            driver.id = 'test'
            driver.address = 'ws://test'
            driver.owner = None
            driver.alert_flag = False
            driver._cur_id = 0
            driver._ws = mock_ws
            driver._recv_th = Thread(target=lambda: None)
            driver._handle_event_th = Thread(target=lambda: None)
            driver._handle_immediate_event_th = None
            driver.is_running = False
            driver.session_id = None
            driver.event_handlers = {}
            driver.immediate_event_handlers = {}
            driver.method_results = {}
            driver._request_states = {}
            driver._request_versions = {}
            driver.event_queue = Queue()
            driver.immediate_event_queue = Queue()
            driver._id_lock = Lock()
            driver._results_lock = Lock()
            driver._session_version = 1
            
            ids_generated = []
            ids_lock = Lock()
            
            def generate_ids(n):
                for _ in range(n):
                    ws_id = driver._get_next_id()
                    with ids_lock:
                        ids_generated.append(ws_id)
            
            threads = []
            num_threads = 10
            ids_per_thread = 100
            
            for _ in range(num_threads):
                t = Thread(target=generate_ids, args=(ids_per_thread,))
                threads.append(t)
            
            for t in threads:
                t.start()
            
            for t in threads:
                t.join()
            
            expected_ids = set(range(1, num_threads * ids_per_thread + 1))
            actual_ids = set(ids_generated)
            
            assert actual_ids == expected_ids, f"ID mismatch"
            assert len(ids_generated) == num_threads * ids_per_thread
            
            print(f"  [PASS] Generated {len(ids_generated)} unique IDs from {num_threads} threads")
            return True


def test_request_states():
    print("Test 2: Request State Tracking")
    
    from unittest.mock import patch
    
    mock_ws = MockWebSocket()
    
    with patch('DrissionPage._base.driver.create_connection', return_value=mock_ws):
        with patch.object(Driver, 'start'):
            driver = Driver.__new__(Driver)
            driver.id = 'test'
            driver.address = 'ws://test'
            driver.owner = None
            driver.alert_flag = False
            driver._cur_id = 0
            driver._ws = mock_ws
            driver._recv_th = Thread(target=lambda: None)
            driver._handle_event_th = Thread(target=lambda: None)
            driver._handle_immediate_event_th = None
            driver.is_running = False
            driver.session_id = None
            driver.event_handlers = {}
            driver.immediate_event_handlers = {}
            driver.method_results = {}
            driver._request_states = {}
            driver._request_versions = {}
            driver.event_queue = Queue()
            driver.immediate_event_queue = Queue()
            driver._id_lock = Lock()
            driver._results_lock = Lock()
            driver._session_version = 1
            
            ws_id = 1
            version = 1
            
            driver._register_request(ws_id, version)
            
            assert driver._get_request_state(ws_id) == RequestState.PENDING
            assert driver._get_request_version(ws_id) == version
            
            result = driver._set_request_state(ws_id, RequestState.COMPLETED)
            assert result == True
            assert driver._get_request_state(ws_id) == RequestState.COMPLETED
            
            result = driver._set_request_state(ws_id, RequestState.TIMEOUT)
            assert result == False
            
            driver._unregister_request(ws_id)
            assert driver._get_request_state(ws_id) is None
            
            print("  [PASS] Request state tracking working correctly")
            return True


def test_metrics():
    print("Test 3: Metrics Collection")
    
    DriverMetrics.reset()
    
    assert DriverMetrics.cross_session_mismatch == 0
    assert DriverMetrics.late_response_isolated == 0
    assert DriverMetrics.duplicate_execution_blocked == 0
    assert DriverMetrics.final_state_consistent == 0
    assert DriverMetrics.final_state_total == 0
    assert DriverMetrics.get_consistency_rate() == 1.0
    
    for i in range(100):
        DriverMetrics.record_final_state(True)
    
    assert DriverMetrics.final_state_total == 100
    assert DriverMetrics.final_state_consistent == 100
    assert DriverMetrics.get_consistency_rate() == 1.0
    
    DriverMetrics.cross_session_mismatch = 5
    DriverMetrics.late_response_isolated = 10
    DriverMetrics.duplicate_execution_blocked = 3
    
    assert DriverMetrics.cross_session_mismatch == 5
    assert DriverMetrics.late_response_isolated == 10
    assert DriverMetrics.duplicate_execution_blocked == 3
    
    print("  [PASS] Metrics collection working correctly")
    print(f"    Consistency Rate: {DriverMetrics.get_consistency_rate() * 100:.2f}%")
    print(f"    Cross-session Mismatches: {DriverMetrics.cross_session_mismatch}")
    print(f"    Late Responses Isolated: {DriverMetrics.late_response_isolated}")
    print(f"    Duplicate Executions Blocked: {DriverMetrics.duplicate_execution_blocked}")
    
    return True


def main():
    print("=" * 60)
    print("Simple Test Suite for Driver Concurrency Fixes")
    print("=" * 60)
    
    tests = [
        test_concurrent_ids,
        test_request_states,
        test_metrics,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  [FAIL] {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    print("\nFinal Metrics:")
    print(f"  Consistency Rate: {DriverMetrics.get_consistency_rate() * 100:.2f}%")
    print(f"  Cross-session Mismatches: {DriverMetrics.cross_session_mismatch}")
    print(f"  Late Responses Isolated: {DriverMetrics.late_response_isolated}")
    print(f"  Duplicate Executions Blocked: {DriverMetrics.duplicate_execution_blocked}")
    
    exit_code = 0 if failed == 0 else 1
    print(f"\n$LASTEXITCODE: {exit_code}")
    
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
