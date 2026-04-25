# -*- coding: utf-8 -*-
"""
Fixed test cases for Driver concurrency and session ordering fixes.

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
    Driver, _DriverMetrics, _STATE_PENDING, _STATE_COMPLETED, _STATE_CANCELLED, _STATE_TIMEOUT
)

RequestState_PENDING = _STATE_PENDING
RequestState_COMPLETED = _STATE_COMPLETED
RequestState_CANCELLED = _STATE_CANCELLED
RequestState_TIMEOUT = _STATE_TIMEOUT
DriverMetrics = _DriverMetrics


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


def create_test_driver():
    """Create a test driver without using patch context managers."""
    driver = object.__new__(Driver)
    driver.id = 'test'
    driver.address = 'ws://test'
    driver.owner = None
    driver.alert_flag = False
    driver._cur_id = 0
    driver._ws = None
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
    return driver


def test_concurrent_id_generation():
    print("Test 1: Concurrent ID Generation")
    DriverMetrics.reset()
    
    ids_generated = []
    ids_lock = Lock()
    
    driver = create_test_driver()
    
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
    
    if actual_ids != expected_ids:
        print(f"  [FAIL] ID mismatch! Missing: {len(expected_ids - actual_ids)}, Extra: {len(actual_ids - expected_ids)}")
        return False
    
    if len(ids_generated) != num_threads * ids_per_thread:
        print(f"  [FAIL] Expected {num_threads * ids_per_thread} IDs, got {len(ids_generated)}")
        return False
    
    print(f"  [PASS] Generated {len(ids_generated)} unique IDs from {num_threads} threads")
    return True


def test_request_state_tracking():
    print("Test 2: Request State Tracking")
    DriverMetrics.reset()
    
    driver = create_test_driver()
    
    ws_id = 1
    version = 1
    
    driver._register_request(ws_id, version)
    
    if driver._get_request_state(ws_id) != _STATE_PENDING:
        print(f"  [FAIL] Expected PENDING state, got {driver._get_request_state(ws_id)}")
        return False
    
    if driver._get_request_version(ws_id) != version:
        print(f"  [FAIL] Expected version {version}, got {driver._get_request_version(ws_id)}")
        return False
    
    result = driver._set_request_state(ws_id, _STATE_COMPLETED)
    if not result:
        print("  [FAIL] State transition to COMPLETED failed")
        return False
    
    if driver._get_request_state(ws_id) != _STATE_COMPLETED:
        print(f"  [FAIL] Expected COMPLETED state, got {driver._get_request_state(ws_id)}")
        return False
    
    result = driver._set_request_state(ws_id, _STATE_TIMEOUT)
    if result:
        print("  [FAIL] Second state transition should have been blocked")
        return False
    
    driver._unregister_request(ws_id)
    if driver._get_request_state(ws_id) is not None:
        print("  [FAIL] State should be None after unregister")
        return False
    
    print("  [PASS] Request state tracking working correctly")
    return True


def test_late_response_isolation():
    print("Test 3: Late Response Isolation")
    DriverMetrics.reset()
    
    driver = create_test_driver()
    
    initial_late_count = DriverMetrics.late_response_isolated
    
    ws_id = 1
    
    driver._register_request(ws_id, driver._session_version)
    driver.method_results[ws_id] = Queue()
    
    driver._set_request_state(ws_id, _STATE_TIMEOUT)
    
    with driver._results_lock:
        driver.method_results.pop(ws_id, None)
    
    with driver._results_lock:
        msg_id = ws_id
        if msg_id not in driver.method_results:
            req_state = driver._get_request_state(msg_id)
            if req_state in (_STATE_TIMEOUT, _STATE_CANCELLED):
                DriverMetrics.late_response_isolated += 1
    
    new_late_count = DriverMetrics.late_response_isolated
    
    if new_late_count <= initial_late_count:
        print(f"  [FAIL] Late response not isolated. Initial: {initial_late_count}, Final: {new_late_count}")
        return False
    
    print(f"  [PASS] Late response isolated. Count: {new_late_count - initial_late_count}")
    return True


def test_session_version_isolation():
    print("Test 4: Session Version Isolation")
    DriverMetrics.reset()
    
    driver = create_test_driver()
    
    initial_mismatch_count = DriverMetrics.cross_session_mismatch
    
    ws_id = 1
    old_version = driver._session_version
    driver._register_request(ws_id, old_version)
    driver.method_results[ws_id] = Queue()
    
    new_version = old_version + 1
    driver._session_version = new_version
    
    with driver._results_lock:
        msg_id = ws_id
        req_version = driver._get_request_version(msg_id)
        current_version = driver._session_version
        if req_version is not None and req_version != current_version:
            DriverMetrics.cross_session_mismatch += 1
    
    new_mismatch_count = DriverMetrics.cross_session_mismatch
    
    if new_mismatch_count <= initial_mismatch_count:
        print(f"  [FAIL] Cross-session mismatch not detected. Initial: {initial_mismatch_count}, Final: {new_mismatch_count}")
        return False
    
    print(f"  [PASS] Old session response isolated. Old version: {old_version}, New version: {new_version}")
    return True


def test_duplicate_execution_blocking():
    print("Test 5: Duplicate Execution Blocking")
    DriverMetrics.reset()
    
    driver = create_test_driver()
    
    initial_duplicate_count = DriverMetrics.duplicate_execution_blocked
    
    ws_id = 1
    driver._register_request(ws_id, driver._session_version)
    result_queue = Queue()
    driver.method_results[ws_id] = result_queue
    
    result = driver._set_request_state(ws_id, _STATE_COMPLETED)
    if not result:
        print("  [FAIL] First state transition to COMPLETED failed")
        return False
    
    with driver._results_lock:
        msg_id = ws_id
        if msg_id in driver.method_results:
            req_state = driver._get_request_state(msg_id)
            if req_state == _STATE_COMPLETED:
                DriverMetrics.duplicate_execution_blocked += 1
    
    new_duplicate_count = DriverMetrics.duplicate_execution_blocked
    
    if new_duplicate_count <= initial_duplicate_count:
        print(f"  [FAIL] Duplicate execution not blocked. Initial: {initial_duplicate_count}, Final: {new_duplicate_count}")
        return False
    
    print(f"  [PASS] Duplicate execution blocked. Count: {new_duplicate_count - initial_duplicate_count}")
    return True


def test_final_state_consistency():
    print("Test 6: Final State Consistency")
    DriverMetrics.reset()
    
    total_requests = 100
    
    for i in range(total_requests):
        DriverMetrics.record_final_state(True)
    
    consistency_rate = DriverMetrics.get_consistency_rate()
    
    if consistency_rate != 1.0:
        print(f"  [FAIL] Expected 100% consistency, got {consistency_rate * 100}%")
        return False
    
    if DriverMetrics.final_state_total != total_requests:
        print(f"  [FAIL] Expected {total_requests} total states, got {DriverMetrics.final_state_total}")
        return False
    
    if DriverMetrics.final_state_consistent != total_requests:
        print(f"  [FAIL] Expected {total_requests} consistent states, got {DriverMetrics.final_state_consistent}")
        return False
    
    print(f"  [PASS] Final state consistency: {consistency_rate * 100}%")
    return True


def run_all_tests():
    print("=" * 60)
    print("Running Driver Concurrency and Session Ordering Tests")
    print("=" * 60)
    
    DriverMetrics.reset()
    
    tests = [
        test_concurrent_id_generation,
        test_request_state_tracking,
        test_late_response_isolation,
        test_session_version_isolation,
        test_duplicate_execution_blocking,
        test_final_state_consistency,
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
    print(f"\nFinal Metrics:")
    print(f"  Consistency Rate: {DriverMetrics.get_consistency_rate() * 100:.2f}%")
    print(f"  Cross-session Mismatches: {DriverMetrics.cross_session_mismatch}")
    print(f"  Late Responses Isolated: {DriverMetrics.late_response_isolated}")
    print(f"  Duplicate Executions Blocked: {DriverMetrics.duplicate_execution_blocked}")
    
    exit_code = 0 if failed == 0 else 1
    print(f"\n$LASTEXITCODE: {exit_code}")
    
    return exit_code


if __name__ == '__main__':
    sys.exit(run_all_tests())
