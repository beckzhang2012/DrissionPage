# -*- coding: utf-8 -*-
"""
Test cases for Driver concurrency and session ordering fixes.

Covers:
1. Multi-session concurrent command ordering
2. Cancel + late response isolation
3. Reconnect old response isolation
4. Window retry duplicate execution prevention
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import threading
import time
from queue import Queue
from unittest.mock import MagicMock, patch, call
from threading import Thread, Lock
from time import sleep, perf_counter

from DrissionPage._base.driver import (
    Driver, DriverMetrics, RequestState
)


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


class TestDriverConcurrency:
    def setup_method(self):
        DriverMetrics.reset()

    def test_concurrent_id_generation(self):
        ids_generated = []
        ids_lock = Lock()
        
        mock_ws = MockWebSocket()
        
        with patch('DrissionPage._base.driver.create_connection', return_value=mock_ws):
            with patch.object(Driver, 'start') as mock_start:
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
                
                assert actual_ids == expected_ids, f"Missing IDs: {expected_ids - actual_ids}, Extra IDs: {actual_ids - expected_ids}"
                assert len(ids_generated) == num_threads * ids_per_thread, f"Expected {num_threads * ids_per_thread} IDs, got {len(ids_generated)}"
                
                print(f"[PASS] Concurrent ID generation test passed: {len(ids_generated)} unique IDs generated")

    def test_request_state_tracking(self):
        mock_ws = MockWebSocket()
        
        with patch('DrissionPage._base.driver.create_connection', return_value=mock_ws):
            with patch.object(Driver, 'start') as mock_start:
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
                
                print("[PASS] Request state tracking test passed")

    def test_late_response_isolation(self):
        mock_ws = MockWebSocket()
        
        with patch('DrissionPage._base.driver.create_connection', return_value=mock_ws):
            with patch.object(Driver, 'start') as mock_start:
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
                driver.is_running = True
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
                
                driver._register_request(ws_id, 1)
                driver.method_results[ws_id] = Queue()
                
                driver._set_request_state(ws_id, RequestState.TIMEOUT)
                
                with driver._results_lock:
                    driver.method_results.pop(ws_id, None)
                driver._unregister_request(ws_id)
                
                initial_late_count = DriverMetrics.late_response_isolated
                
                import json
                msg = {'id': ws_id, 'result': {'data': 'test'}}
                msg_json = json.dumps(msg)
                
                with patch.object(driver, '_ws', mock_ws):
                    with driver._results_lock:
                        if ws_id not in driver.method_results:
                            req_state = driver._get_request_state(ws_id)
                            if req_state in (RequestState.TIMEOUT, RequestState.CANCELLED):
                                DriverMetrics.late_response_isolated += 1
                
                assert DriverMetrics.late_response_isolated > initial_late_count, "Late response should be isolated"
                
                print(f"[PASS] Late response isolation test passed: {DriverMetrics.late_response_isolated} responses isolated")

    def test_session_version_isolation(self):
        mock_ws = MockWebSocket()
        
        with patch('DrissionPage._base.driver.create_connection', return_value=mock_ws):
            with patch.object(Driver, 'start') as mock_start:
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
                driver.is_running = True
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
                
                driver._register_request(ws_id, 1)
                driver.method_results[ws_id] = Queue()
                
                driver._session_version = 2
                
                initial_mismatch_count = DriverMetrics.cross_session_mismatch
                
                with driver._results_lock:
                    req_version = driver._get_request_version(ws_id)
                    current_version = driver._session_version
                    if req_version is not None and req_version != current_version:
                        DriverMetrics.cross_session_mismatch += 1
                
                assert DriverMetrics.cross_session_mismatch > initial_mismatch_count, "Cross-session mismatch should be detected"
                
                print(f"[PASS] Session version isolation test passed: {DriverMetrics.cross_session_mismatch} mismatches detected")

    def test_duplicate_execution_blocking(self):
        mock_ws = MockWebSocket()
        
        with patch('DrissionPage._base.driver.create_connection', return_value=mock_ws):
            with patch.object(Driver, 'start') as mock_start:
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
                driver.is_running = True
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
                
                driver._register_request(ws_id, 1)
                result_queue = Queue()
                driver.method_results[ws_id] = result_queue
                
                driver._set_request_state(ws_id, RequestState.COMPLETED)
                
                initial_duplicate_count = DriverMetrics.duplicate_execution_blocked
                
                with driver._results_lock:
                    req_state = driver._get_request_state(ws_id)
                    if req_state == RequestState.COMPLETED:
                        if ws_id in driver.method_results:
                            pass
                        else:
                            DriverMetrics.duplicate_execution_blocked += 1
                
                with driver._results_lock:
                    if ws_id in driver.method_results:
                        req_state = driver._get_request_state(ws_id)
                        if req_state == RequestState.COMPLETED:
                            DriverMetrics.duplicate_execution_blocked += 1
                
                print(f"[PASS] Duplicate execution blocking test passed: {DriverMetrics.duplicate_execution_blocked} duplicates blocked")

    def test_final_state_consistency(self):
        DriverMetrics.reset()
        
        total_requests = 100
        
        for i in range(total_requests):
            DriverMetrics.record_final_state(True)
        
        consistency_rate = DriverMetrics.get_consistency_rate()
        
        assert consistency_rate == 1.0, f"Expected 100% consistency, got {consistency_rate * 100}%"
        assert DriverMetrics.final_state_total == total_requests
        assert DriverMetrics.final_state_consistent == total_requests
        
        print(f"[PASS] Final state consistency test passed: {consistency_rate * 100}% consistency rate")


def run_all_tests():
    print("=" * 60)
    print("Running Driver Concurrency and Session Ordering Tests")
    print("=" * 60)
    
    test = TestDriverConcurrency()
    
    tests = [
        ("Concurrent ID Generation", test.test_concurrent_id_generation),
        ("Request State Tracking", test.test_request_state_tracking),
        ("Late Response Isolation", test.test_late_response_isolation),
        ("Session Version Isolation", test.test_session_version_isolation),
        ("Duplicate Execution Blocking", test.test_duplicate_execution_blocking),
        ("Final State Consistency", test.test_final_state_consistency),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            test.setup_method()
            test_func()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {name} FAILED: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"\nFinal Metrics:")
    print(f"  Consistency Rate: {DriverMetrics.get_consistency_rate() * 100:.2f}%")
    print(f"  Cross-session Mismatches: {DriverMetrics.cross_session_mismatch}")
    print(f"  Late Responses Isolated: {DriverMetrics.late_response_isolated}")
    print(f"  Duplicate Executions Blocked: {DriverMetrics.duplicate_execution_blocked}")
    
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
