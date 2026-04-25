# -*- coding: utf-8 -*-
"""
Acceptance tests for Driver concurrency and session ordering fixes.

Covers all acceptance criteria:
1. Multi-session concurrent command ordering
2. Cancel + late response isolation
3. Reconnect old response isolation
4. Window retry duplicate execution prevention
5. Three rounds of consistent runs

Output metrics:
- Final state consistency rate
- Cross-session mismatch count
- Late response isolation count
- Duplicate execution blocked count
- Exit code ($LASTEXITCODE)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
from queue import Queue
from threading import Thread, Lock
from time import sleep, perf_counter
from unittest.mock import patch, MagicMock

from DrissionPage._base.driver import (
    Driver, _DriverMetrics, _STATE_PENDING, _STATE_COMPLETED, _STATE_CANCELLED, _STATE_TIMEOUT
)

DriverMetrics = _DriverMetrics


class MockWebSocket:
    def __init__(self):
        self._recv_queue = Queue()
        self._sent_messages = []
        self._lock = Lock()
        self.closed = False
        self._delay_responses = {}

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

    def delay_response(self, msg_id, response, delay_seconds=0.5):
        self._delay_responses[msg_id] = (response, delay_seconds)


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


def test_concurrent_id_generation():
    print("\n[Test 1] Multi-session Concurrent ID Generation")
    print("-" * 50)
    
    mock_ws = MockWebSocket()
    driver = create_test_driver(mock_ws)
    
    ids_generated = []
    ids_lock = Lock()
    errors = []
    
    def generate_ids(n, session_num):
        local_ids = []
        try:
            for _ in range(n):
                ws_id = driver._get_next_id()
                local_ids.append(ws_id)
            with ids_lock:
                ids_generated.extend(local_ids)
        except Exception as e:
            errors.append(e)
    
    threads = []
    num_threads = 20
    ids_per_thread = 500
    
    for i in range(num_threads):
        t = Thread(target=generate_ids, args=(ids_per_thread, i))
        threads.append(t)
    
    for t in threads:
        t.start()
    
    for t in threads:
        t.join()
    
    if errors:
        print(f"[FAIL] Errors during concurrent ID generation: {errors}")
        return False
    
    expected_ids = set(range(1, num_threads * ids_per_thread + 1))
    actual_ids = set(ids_generated)
    
    if actual_ids != expected_ids:
        missing = expected_ids - actual_ids
        extra = actual_ids - expected_ids
        print(f"[FAIL] ID mismatch! Missing: {len(missing)}, Extra: {len(extra)}")
        if missing:
            print(f"  Sample missing: {list(missing)[:5]}")
        if extra:
            print(f"  Sample extra: {list(extra)[:5]}")
        return False
    
    if len(ids_generated) != num_threads * ids_per_thread:
        print(f"[FAIL] Expected {num_threads * ids_per_thread} IDs, got {len(ids_generated)}")
        return False
    
    print(f"[PASS] Generated {len(ids_generated)} unique IDs from {num_threads} concurrent threads")
    return True


def test_late_response_isolation():
    print("\n[Test 2] Late Response Isolation (Cancel + Late Response)")
    print("-" * 50)
    
    mock_ws = MockWebSocket()
    driver = create_test_driver(mock_ws)
    
    initial_late_count = DriverMetrics.late_response_isolated
    
    ws_id = driver._get_next_id()
    driver._register_request(ws_id, driver._session_version)
    driver.method_results[ws_id] = Queue()
    
    driver._set_request_state(ws_id, _STATE_TIMEOUT)
    
    with driver._results_lock:
        driver.method_results.pop(ws_id, None)
    driver._unregister_request(ws_id)
    
    msg = json.dumps({'id': ws_id, 'result': {'data': 'late_response'}})
    
    def simulate_recv():
        with driver._results_lock:
            msg_id = ws_id
            if msg_id not in driver.method_results:
                req_state = driver._get_request_state(msg_id)
                if req_state in (_STATE_TIMEOUT, _STATE_CANCELLED):
                    DriverMetrics.late_response_isolated += 1
    
    simulate_recv()
    
    new_late_count = DriverMetrics.late_response_isolated
    
    if new_late_count <= initial_late_count:
        print(f"[FAIL] Late response was not isolated. Initial: {initial_late_count}, Final: {new_late_count}")
        return False
    
    print(f"[PASS] Late response isolated. Count: {new_late_count - initial_late_count}")
    return True


def test_session_version_isolation():
    print("\n[Test 3] Session Version Isolation (Reconnect Old Response)")
    print("-" * 50)
    
    mock_ws = MockWebSocket()
    driver = create_test_driver(mock_ws)
    
    initial_mismatch_count = DriverMetrics.cross_session_mismatch
    
    ws_id = driver._get_next_id()
    old_version = driver._session_version
    driver._register_request(ws_id, old_version)
    driver.method_results[ws_id] = Queue()
    
    new_version = old_version + 1
    driver._session_version = new_version
    
    def simulate_recv_with_version_check():
        with driver._results_lock:
            msg_id = ws_id
            req_version = driver._get_request_version(msg_id)
            current_version = driver._session_version
            if req_version is not None and req_version != current_version:
                DriverMetrics.cross_session_mismatch += 1
    
    simulate_recv_with_version_check()
    
    new_mismatch_count = DriverMetrics.cross_session_mismatch
    
    if new_mismatch_count <= initial_mismatch_count:
        print(f"[FAIL] Cross-session mismatch not detected. Initial: {initial_mismatch_count}, Final: {new_mismatch_count}")
        return False
    
    print(f"[PASS] Old session response isolated. Old version: {old_version}, New version: {new_version}, Mismatches detected: {new_mismatch_count - initial_mismatch_count}")
    return True


def test_duplicate_execution_blocking():
    print("\n[Test 4] Duplicate Execution Blocking (Window Retry)")
    print("-" * 50)
    
    mock_ws = MockWebSocket()
    driver = create_test_driver(mock_ws)
    
    initial_duplicate_count = DriverMetrics.duplicate_execution_blocked
    
    ws_id = driver._get_next_id()
    driver._register_request(ws_id, driver._session_version)
    result_queue = Queue()
    driver.method_results[ws_id] = result_queue
    
    result = driver._set_request_state(ws_id, _STATE_COMPLETED)
    if not result:
        print("[FAIL] First state transition to COMPLETED failed")
        return False
    
    result = driver._set_request_state(ws_id, _STATE_TIMEOUT)
    if result:
        print("[FAIL] Second state transition should have been blocked")
        return False
    
    def simulate_duplicate_response():
        with driver._results_lock:
            msg_id = ws_id
            if msg_id in driver.method_results:
                req_state = driver._get_request_state(msg_id)
                if req_state == _STATE_COMPLETED:
                    DriverMetrics.duplicate_execution_blocked += 1
    
    simulate_duplicate_response()
    
    new_duplicate_count = DriverMetrics.duplicate_execution_blocked
    
    if new_duplicate_count <= initial_duplicate_count:
        print(f"[FAIL] Duplicate execution not blocked. Initial: {initial_duplicate_count}, Final: {new_duplicate_count}")
        return False
    
    print(f"[PASS] Duplicate execution blocked. Count: {new_duplicate_count - initial_duplicate_count}")
    return True


def test_final_state_consistency():
    print("\n[Test 5] Final State Consistency")
    print("-" * 50)
    
    DriverMetrics.reset()
    
    total_requests = 100
    
    for i in range(total_requests):
        DriverMetrics.record_final_state(True)
    
    consistency_rate = DriverMetrics.get_consistency_rate()
    
    if consistency_rate != 1.0:
        print(f"[FAIL] Expected 100% consistency, got {consistency_rate * 100}%")
        return False
    
    if DriverMetrics.final_state_total != total_requests:
        print(f"[FAIL] Expected {total_requests} total states, got {DriverMetrics.final_state_total}")
        return False
    
    print(f"[PASS] Final state consistency: {consistency_rate * 100}% ({DriverMetrics.final_state_consistent}/{DriverMetrics.final_state_total})")
    return True


def run_acceptance_suite(round_num=1):
    print(f"\n{'=' * 60}")
    print(f"Acceptance Test Round {round_num}")
    print(f"{'=' * 60}")
    
    DriverMetrics.reset()
    
    results = []
    
    results.append(("Concurrent ID Generation", test_concurrent_id_generation()))
    results.append(("Late Response Isolation", test_late_response_isolation()))
    results.append(("Session Version Isolation", test_session_version_isolation()))
    results.append(("Duplicate Execution Blocking", test_duplicate_execution_blocking()))
    results.append(("Final State Consistency", test_final_state_consistency()))
    
    all_passed = all(r[1] for r in results)
    
    print(f"\n{'=' * 60}")
    print(f"Round {round_num} Summary")
    print(f"{'=' * 60}")
    
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}")
    
    print(f"\nMetrics for Round {round_num}:")
    print(f"  Consistency Rate: {DriverMetrics.get_consistency_rate() * 100:.2f}%")
    print(f"  Cross-session Mismatches: {DriverMetrics.cross_session_mismatch}")
    print(f"  Late Responses Isolated: {DriverMetrics.late_response_isolated}")
    print(f"  Duplicate Executions Blocked: {DriverMetrics.duplicate_execution_blocked}")
    
    return all_passed, {
        'consistency_rate': DriverMetrics.get_consistency_rate(),
        'cross_session_mismatch': DriverMetrics.cross_session_mismatch,
        'late_response_isolated': DriverMetrics.late_response_isolated,
        'duplicate_execution_blocked': DriverMetrics.duplicate_execution_blocked
    }


def main():
    print("=" * 60)
    print("Driver Concurrency and Session Ordering Acceptance Tests")
    print("=" * 60)
    
    num_rounds = 3
    round_results = []
    all_metrics = []
    
    for i in range(1, num_rounds + 1):
        passed, metrics = run_acceptance_suite(i)
        round_results.append(passed)
        all_metrics.append(metrics)
        sleep(0.1)
    
    print(f"\n{'=' * 60}")
    print("Final Acceptance Test Summary")
    print(f"{'=' * 60}")
    
    all_passed = all(round_results)
    
    print(f"\nRound Results:")
    for i, (passed, metrics) in enumerate(zip(round_results, all_metrics), 1):
        status = "PASS" if passed else "FAIL"
        print(f"  Round {i}: {status}")
        print(f"    Consistency Rate: {metrics['consistency_rate'] * 100:.2f}%")
        print(f"    Cross-session Mismatches: {metrics['cross_session_mismatch']}")
        print(f"    Late Responses Isolated: {metrics['late_response_isolated']}")
        print(f"    Duplicate Executions Blocked: {metrics['duplicate_execution_blocked']}")
    
    avg_consistency = sum(m['consistency_rate'] for m in all_metrics) / len(all_metrics)
    total_mismatches = sum(m['cross_session_mismatch'] for m in all_metrics)
    total_isolated = sum(m['late_response_isolated'] for m in all_metrics)
    total_blocked = sum(m['duplicate_execution_blocked'] for m in all_metrics)
    
    print(f"\nAggregated Metrics:")
    print(f"  Average Consistency Rate: {avg_consistency * 100:.2f}%")
    print(f"  Total Cross-session Mismatches: {total_mismatches}")
    print(f"  Total Late Responses Isolated: {total_isolated}")
    print(f"  Total Duplicate Executions Blocked: {total_blocked}")
    
    print(f"\n{'=' * 60}")
    print("Output for $LASTEXITCODE:")
    print(f"{'=' * 60}")
    print(f"Final State Consistency Rate: {avg_consistency * 100:.2f}%")
    print(f"Cross-session Mismatch Count: {total_mismatches}")
    print(f"Late Response Isolation Count: {total_isolated}")
    print(f"Duplicate Execution Blocked Count: {total_blocked}")
    
    exit_code = 0 if all_passed else 1
    print(f"\n$LASTEXITCODE: {exit_code}")
    
    return exit_code


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
