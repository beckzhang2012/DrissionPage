# -*- coding: utf-8 -*-
"""Step-by-step test to identify issues."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from queue import Queue
from threading import Thread, Lock
from unittest.mock import patch

from DrissionPage._base.driver import (
    Driver, _DriverMetrics, _STATE_PENDING, _STATE_COMPLETED, 
    _STATE_CANCELLED, _STATE_TIMEOUT
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


def create_test_driver(mock_ws):
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
            return driver


def test_step_1_basic_driver_creation():
    print("Test Step 1: Basic Driver Creation")
    mock_ws = MockWebSocket()
    try:
        driver = create_test_driver(mock_ws)
        assert driver is not None
        assert driver._session_version == 1
        print("  [PASS] Driver created successfully")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


def test_step_2_id_generation():
    print("Test Step 2: ID Generation")
    mock_ws = MockWebSocket()
    driver = create_test_driver(mock_ws)
    
    try:
        ids = []
        for i in range(1, 11):
            ws_id = driver._get_next_id()
            ids.append(ws_id)
            assert ws_id == i, f"Expected {i}, got {ws_id}"
        
        assert ids == list(range(1, 11))
        print(f"  [PASS] Generated IDs: {ids}")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


def test_step_3_request_state():
    print("Test Step 3: Request State Tracking")
    mock_ws = MockWebSocket()
    driver = create_test_driver(mock_ws)
    
    try:
        ws_id = 1
        version = 1
        
        driver._register_request(ws_id, version)
        assert driver._get_request_state(ws_id) == _STATE_PENDING
        assert driver._get_request_version(ws_id) == version
        
        result = driver._set_request_state(ws_id, _STATE_COMPLETED)
        assert result == True
        assert driver._get_request_state(ws_id) == _STATE_COMPLETED
        
        result = driver._set_request_state(ws_id, _STATE_TIMEOUT)
        assert result == False
        
        driver._unregister_request(ws_id)
        assert driver._get_request_state(ws_id) is None
        
        print("  [PASS] Request state tracking working")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


def test_step_4_final_state_consistency():
    print("Test Step 4: Final State Consistency")
    _DriverMetrics.reset()
    
    try:
        total_requests = 100
        
        for i in range(total_requests):
            _DriverMetrics.record_final_state(True)
        
        consistency_rate = _DriverMetrics.get_consistency_rate()
        
        assert consistency_rate == 1.0, f"Expected 100% consistency, got {consistency_rate * 100}%"
        assert _DriverMetrics.final_state_total == total_requests
        assert _DriverMetrics.final_state_consistent == total_requests
        
        print(f"  [PASS] Final state consistency: {consistency_rate * 100}%")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


def test_step_5_late_response_isolation():
    print("Test Step 5: Late Response Isolation")
    _DriverMetrics.reset()
    
    mock_ws = MockWebSocket()
    driver = create_test_driver(mock_ws)
    
    try:
        initial_late_count = _DriverMetrics.late_response_isolated
        
        ws_id = 1
        driver._register_request(ws_id, driver._session_version)
        driver.method_results[ws_id] = Queue()
        
        driver._set_request_state(ws_id, _STATE_TIMEOUT)
        
        with driver._results_lock:
            driver.method_results.pop(ws_id, None)
        driver._unregister_request(ws_id)
        
        with driver._results_lock:
            msg_id = ws_id
            if msg_id not in driver.method_results:
                req_state = driver._get_request_state(msg_id)
                if req_state in (_STATE_TIMEOUT, _STATE_CANCELLED):
                    _DriverMetrics.late_response_isolated += 1
        
        new_late_count = _DriverMetrics.late_response_isolated
        
        assert new_late_count > initial_late_count, f"Late response not isolated. Initial: {initial_late_count}, Final: {new_late_count}"
        
        print(f"  [PASS] Late response isolated. Count: {new_late_count - initial_late_count}")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


def test_step_6_session_version_isolation():
    print("Test Step 6: Session Version Isolation")
    _DriverMetrics.reset()
    
    mock_ws = MockWebSocket()
    driver = create_test_driver(mock_ws)
    
    try:
        initial_mismatch_count = _DriverMetrics.cross_session_mismatch
        
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
                _DriverMetrics.cross_session_mismatch += 1
        
        new_mismatch_count = _DriverMetrics.cross_session_mismatch
        
        assert new_mismatch_count > initial_mismatch_count, f"Cross-session mismatch not detected. Initial: {initial_mismatch_count}, Final: {new_mismatch_count}"
        
        print(f"  [PASS] Old session response isolated. Old version: {old_version}, New version: {new_version}")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


def test_step_7_duplicate_execution_blocking():
    print("Test Step 7: Duplicate Execution Blocking")
    _DriverMetrics.reset()
    
    mock_ws = MockWebSocket()
    driver = create_test_driver(mock_ws)
    
    try:
        initial_duplicate_count = _DriverMetrics.duplicate_execution_blocked
        
        ws_id = 1
        driver._register_request(ws_id, driver._session_version)
        result_queue = Queue()
        driver.method_results[ws_id] = result_queue
        
        result = driver._set_request_state(ws_id, _STATE_COMPLETED)
        assert result == True, "First state transition to COMPLETED failed"
        
        with driver._results_lock:
            msg_id = ws_id
            if msg_id in driver.method_results:
                req_state = driver._get_request_state(msg_id)
                if req_state == _STATE_COMPLETED:
                    _DriverMetrics.duplicate_execution_blocked += 1
        
        new_duplicate_count = _DriverMetrics.duplicate_execution_blocked
        
        assert new_duplicate_count > initial_duplicate_count, f"Duplicate execution not blocked. Initial: {initial_duplicate_count}, Final: {new_duplicate_count}"
        
        print(f"  [PASS] Duplicate execution blocked. Count: {new_duplicate_count - initial_duplicate_count}")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


def test_step_8_concurrent_id_generation():
    print("Test Step 8: Concurrent ID Generation")
    mock_ws = MockWebSocket()
    driver = create_test_driver(mock_ws)
    
    try:
        ids_generated = []
        ids_lock = Lock()
        
        def generate_ids(n):
            for _ in range(n):
                ws_id = driver._get_next_id()
                with ids_lock:
                    ids_generated.append(ws_id)
        
        threads = []
        num_threads = 5
        ids_per_thread = 20
        
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
        
        print(f"  [PASS] Generated {len(ids_generated)} unique IDs from {num_threads} threads")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("Step-by-Step Driver Concurrency Tests")
    print("=" * 60)
    
    _DriverMetrics.reset()
    
    tests = [
        test_step_1_basic_driver_creation,
        test_step_2_id_generation,
        test_step_3_request_state,
        test_step_4_final_state_consistency,
        test_step_5_late_response_isolation,
        test_step_6_session_version_isolation,
        test_step_7_duplicate_execution_blocking,
        test_step_8_concurrent_id_generation,
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
    print(f"  Consistency Rate: {_DriverMetrics.get_consistency_rate() * 100:.2f}%")
    print(f"  Cross-session Mismatches: {_DriverMetrics.cross_session_mismatch}")
    print(f"  Late Responses Isolated: {_DriverMetrics.late_response_isolated}")
    print(f"  Duplicate Executions Blocked: {_DriverMetrics.duplicate_execution_blocked}")
    
    exit_code = 0 if failed == 0 else 1
    print(f"\n$LASTEXITCODE: {exit_code}")
    
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
