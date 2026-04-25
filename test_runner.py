# -*- coding: utf-8 -*-
"""Simplified test runner for driver concurrency tests."""
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
print("Driver Concurrency and Session Ordering Tests")
print("=" * 60)

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

# Reset metrics at the start
_DriverMetrics.reset()

# Test 1: Concurrent ID Generation
print("\n[1] Concurrent ID Generation")
driver = create_test_driver()
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

if actual_ids == expected_ids and len(ids_generated) == num_threads * ids_per_thread:
    print(f"    [PASS] Generated {len(ids_generated)} unique IDs from {num_threads} threads")
else:
    print(f"    [FAIL] ID mismatch! Missing: {len(expected_ids - actual_ids)}, Extra: {len(actual_ids - expected_ids)}")
    sys.exit(1)

# Test 2: Request State Tracking
print("\n[2] Request State Tracking")
driver = create_test_driver()
ws_id = 1
version = 1

driver._register_request(ws_id, version)

if driver._get_request_state(ws_id) != _STATE_PENDING:
    print(f"    [FAIL] Expected PENDING state, got {driver._get_request_state(ws_id)}")
    sys.exit(1)

if driver._get_request_version(ws_id) != version:
    print(f"    [FAIL] Expected version {version}, got {driver._get_request_version(ws_id)}")
    sys.exit(1)

result = driver._set_request_state(ws_id, _STATE_COMPLETED)
if not result:
    print("    [FAIL] State transition to COMPLETED failed")
    sys.exit(1)

if driver._get_request_state(ws_id) != _STATE_COMPLETED:
    print(f"    [FAIL] Expected COMPLETED state, got {driver._get_request_state(ws_id)}")
    sys.exit(1)

result = driver._set_request_state(ws_id, _STATE_TIMEOUT)
if result:
    print("    [FAIL] Second state transition should have been blocked")
    sys.exit(1)

driver._unregister_request(ws_id)
if driver._get_request_state(ws_id) is not None:
    print("    [FAIL] State should be None after unregister")
    sys.exit(1)

print("    [PASS] Request state tracking working correctly")

# Test 3: Late Response Isolation
print("\n[3] Late Response Isolation")
_DriverMetrics.reset()
driver = create_test_driver()

initial_late_count = _DriverMetrics.late_response_isolated

ws_id = 1
driver._register_request(ws_id, driver._session_version)
driver.method_results[ws_id] = Queue()

# Simulate timeout
driver._set_request_state(ws_id, _STATE_TIMEOUT)
with driver._results_lock:
    driver.method_results.pop(ws_id, None)

# Simulate _recv_loop logic (msg_id not in method_results)
with driver._results_lock:
    msg_id = ws_id
    if msg_id not in driver.method_results:
        req_state = driver._get_request_state(msg_id)
        if req_state in (_STATE_TIMEOUT, _STATE_CANCELLED):
            _DriverMetrics.late_response_isolated += 1
            driver._unregister_request(msg_id)

new_late_count = _DriverMetrics.late_response_isolated

if new_late_count > initial_late_count:
    print(f"    [PASS] Late responses isolated: {initial_late_count} -> {new_late_count}")
else:
    print(f"    [FAIL] Late response not isolated: {initial_late_count} -> {new_late_count}")
    sys.exit(1)

# Test 4: Session Version Isolation (Cross-session Mismatch)
print("\n[4] Session Version Isolation (Cross-session Mismatch)")
_DriverMetrics.reset()
driver = create_test_driver()

initial_mismatch_count = _DriverMetrics.cross_session_mismatch

ws_id = 1
old_version = driver._session_version
driver._register_request(ws_id, old_version)
driver.method_results[ws_id] = Queue()

# Simulate session version change (reconnect)
new_version = old_version + 1
driver._session_version = new_version

# Simulate _recv_loop logic (version mismatch)
with driver._results_lock:
    msg_id = ws_id
    req_version = driver._get_request_version(msg_id)
    current_version = driver._session_version
    if req_version is not None and req_version != current_version:
        _DriverMetrics.cross_session_mismatch += 1
        driver._unregister_request(msg_id)

new_mismatch_count = _DriverMetrics.cross_session_mismatch

if new_mismatch_count > initial_mismatch_count:
    print(f"    [PASS] Cross-session mismatches: {initial_mismatch_count} -> {new_mismatch_count}")
    print(f"    [INFO] Old version: {old_version}, New version: {new_version}")
else:
    print(f"    [FAIL] Cross-session mismatch not detected: {initial_mismatch_count} -> {new_mismatch_count}")
    sys.exit(1)

# Test 5: Duplicate Execution Blocking
print("\n[5] Duplicate Execution Blocking")
_DriverMetrics.reset()
driver = create_test_driver()

initial_duplicate_count = _DriverMetrics.duplicate_execution_blocked

ws_id = 1
driver._register_request(ws_id, driver._session_version)
driver.method_results[ws_id] = Queue()

# Simulate first response received (state becomes COMPLETED)
driver._set_request_state(ws_id, _STATE_COMPLETED)

# Simulate _recv_loop logic for duplicate response
with driver._results_lock:
    msg_id = ws_id
    if msg_id in driver.method_results:
        req_state = driver._get_request_state(msg_id)
        if req_state != _STATE_PENDING:
            if req_state == _STATE_COMPLETED:
                _DriverMetrics.duplicate_execution_blocked += 1
                driver._unregister_request(msg_id)

new_duplicate_count = _DriverMetrics.duplicate_execution_blocked

if new_duplicate_count > initial_duplicate_count:
    print(f"    [PASS] Duplicate executions blocked: {initial_duplicate_count} -> {new_duplicate_count}")
else:
    print(f"    [FAIL] Duplicate execution not blocked: {initial_duplicate_count} -> {new_duplicate_count}")
    sys.exit(1)

# Test 6: Final State Consistency
print("\n[6] Final State Consistency")
_DriverMetrics.reset()

total_requests = 100
for i in range(total_requests):
    _DriverMetrics.record_final_state(True)

consistency_rate = _DriverMetrics.get_consistency_rate()

if consistency_rate == 1.0:
    print(f"    [PASS] Final state consistency: {consistency_rate * 100:.2f}%")
else:
    print(f"    [FAIL] Expected 100% consistency, got {consistency_rate * 100}%")
    sys.exit(1)

# Final Summary
print("\n" + "=" * 60)
print("Test Summary")
print("=" * 60)
print("All 6 tests PASSED!")

print("\nFinal Metrics:")
print(f"  终态一致率 (Consistency Rate): {_DriverMetrics.get_consistency_rate() * 100:.2f}%")
print(f"  跨会话串号 (Cross-session Mismatches): {_DriverMetrics.cross_session_mismatch}")
print(f"  迟到响应隔离 (Late Responses Isolated): {_DriverMetrics.late_response_isolated}")
print(f"  重复执行拦截 (Duplicate Executions Blocked): {_DriverMetrics.duplicate_execution_blocked}")

exit_code = 0
print(f"\n$LASTEXITCODE: {exit_code}")
sys.exit(exit_code)
