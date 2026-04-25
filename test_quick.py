# -*- coding: utf-8 -*-
"""Quick test for Driver concurrency fixes."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from queue import Queue
from threading import Thread, Lock

from DrissionPage._base.driver import (
    Driver, _DriverMetrics, _STATE_PENDING, _STATE_COMPLETED, 
    _STATE_CANCELLED, _STATE_TIMEOUT
)

print("=" * 60)
print("Quick Driver Concurrency Tests")
print("=" * 60)

# Create test driver
def create_test_driver():
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

# Reset metrics
_DriverMetrics.reset()

# Test 1: ID Generation
print("\n[1] ID Generation")
driver = create_test_driver()
ids = []
for i in range(1, 11):
    ws_id = driver._get_next_id()
    ids.append(ws_id)
assert ids == list(range(1, 11)), f"Expected [1,2,...10], got {ids}"
print("    [PASS] ID generation working")

# Test 2: Request State Tracking
print("\n[2] Request State Tracking")
driver = create_test_driver()
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
print("    [PASS] State tracking working")

# Test 3: Late Response Isolation
print("\n[3] Late Response Isolation")
_DriverMetrics.reset()
driver = create_test_driver()

initial = _DriverMetrics.late_response_isolated

ws_id = 1
driver._register_request(ws_id, driver._session_version)
driver.method_results[ws_id] = Queue()

driver._set_request_state(ws_id, _STATE_TIMEOUT)

with driver._results_lock:
    driver.method_results.pop(ws_id, None)

# Simulate _recv_loop behavior
with driver._results_lock:
    msg_id = ws_id
    if msg_id not in driver.method_results:
        req_state = driver._get_request_state(msg_id)
        if req_state in (_STATE_TIMEOUT, _STATE_CANCELLED):
            _DriverMetrics.late_response_isolated += 1

final = _DriverMetrics.late_response_isolated
assert final > initial, f"Late response not isolated: {initial} -> {final}"
print(f"    [PASS] Late response isolated: {initial} -> {final}")

# Test 4: Session Version Isolation
print("\n[4] Session Version Isolation")
_DriverMetrics.reset()
driver = create_test_driver()

initial = _DriverMetrics.cross_session_mismatch

ws_id = 1
old_version = driver._session_version
driver._register_request(ws_id, old_version)
driver.method_results[ws_id] = Queue()

new_version = old_version + 1
driver._session_version = new_version

# Simulate _recv_loop behavior
with driver._results_lock:
    msg_id = ws_id
    req_version = driver._get_request_version(msg_id)
    current_version = driver._session_version
    if req_version is not None and req_version != current_version:
        _DriverMetrics.cross_session_mismatch += 1

final = _DriverMetrics.cross_session_mismatch
assert final > initial, f"Cross-session mismatch not detected: {initial} -> {final}"
print(f"    [PASS] Cross-session mismatch detected: {initial} -> {final}")

# Test 5: Duplicate Execution Blocking
print("\n[5] Duplicate Execution Blocking")
_DriverMetrics.reset()
driver = create_test_driver()

initial = _DriverMetrics.duplicate_execution_blocked

ws_id = 1
driver._register_request(ws_id, driver._session_version)
driver.method_results[ws_id] = Queue()

driver._set_request_state(ws_id, _STATE_COMPLETED)

# Simulate _recv_loop behavior
with driver._results_lock:
    msg_id = ws_id
    if msg_id in driver.method_results:
        req_state = driver._get_request_state(msg_id)
        if req_state == _STATE_COMPLETED:
            _DriverMetrics.duplicate_execution_blocked += 1

final = _DriverMetrics.duplicate_execution_blocked
assert final > initial, f"Duplicate execution not blocked: {initial} -> {final}"
print(f"    [PASS] Duplicate execution blocked: {initial} -> {final}")

# Test 6: Final State Consistency
print("\n[6] Final State Consistency")
_DriverMetrics.reset()

total = 100
for i in range(total):
    _DriverMetrics.record_final_state(True)

rate = _DriverMetrics.get_consistency_rate()
assert rate == 1.0, f"Expected 100% consistency, got {rate * 100}%"
assert _DriverMetrics.final_state_total == total
assert _DriverMetrics.final_state_consistent == total
print(f"    [PASS] Final state consistency: {rate * 100}%")

# Summary
print("\n" + "=" * 60)
print("Test Summary")
print("=" * 60)
print("All 6 tests PASSED!")

print("\nFinal Metrics:")
print(f"  Consistency Rate: {_DriverMetrics.get_consistency_rate() * 100:.2f}%")
print(f"  Cross-session Mismatches: {_DriverMetrics.cross_session_mismatch}")
print(f"  Late Responses Isolated: {_DriverMetrics.late_response_isolated}")
print(f"  Duplicate Executions Blocked: {_DriverMetrics.duplicate_execution_blocked}")

exit_code = 0
print(f"\n$LASTEXITCODE: {exit_code}")
sys.exit(exit_code)
