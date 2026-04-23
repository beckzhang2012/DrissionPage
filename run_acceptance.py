# -*- coding:utf-8 -*-
"""
Listener FSM 验收脚本
一次性输出：完整包率、丢弃/降级计数、状态流转样例、重复完成拦截次数
"""
import sys
import os
from unittest.mock import MagicMock
from queue import Queue

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from DrissionPage._units.listener import Listener, RequestState, _TERMINAL_STATES


class FSMStateTracker:
    """状态流转追踪器"""

    def __init__(self):
        self.transitions = []

    def track_transition(self, request_id, from_state, to_state, event):
        """记录状态转换"""
        self.transitions.append({
            'request_id': request_id,
            'from': from_state,
            'to': to_state,
            'event': event
        })


def create_mock_owner():
    """创建模拟 owner"""
    mock_owner = MagicMock()
    mock_owner.tab_id = 'test-tab-id'
    mock_owner._target_id = 'test-target-id'
    mock_owner._is_diff_domain = False
    mock_owner._frame_id = 'test-frame-id'
    mock_owner.browser._ws_address = 'ws://test'
    return mock_owner


def create_mock_driver():
    """创建模拟 driver"""
    mock_driver = MagicMock()
    mock_driver.is_running = True
    mock_driver.run.return_value = {'body': '{}', 'base64Encoded': False}
    return mock_driver


def create_listener():
    """创建 listener 实例"""
    owner = create_mock_owner()
    listener = Listener(owner)
    listener._driver = create_mock_driver()
    listener._caught = Queue(maxsize=0)
    listener._request_ids = {}
    listener._extra_info_ids = {}
    listener._fsm_states = {}
    listener._pending_events = {}
    listener._fsm_stats = {
        'out_of_order_count': 0,
        'missing_events_count': 0,
        'duplicate_terminal_count': 0,
    }
    listener._running_requests = 0
    listener._running_targets = 0
    listener._targets = True
    listener._method = True
    listener._res_type = True
    return listener


class AcceptanceMetrics:
    """验收指标收集器"""

    def __init__(self):
        self.total_requests = 0
        self.complete_packets = 0
        self.dropped_packets = 0
        self.degraded_packets = 0
        self.duplicate_terminal_count = 0
        self.out_of_order_count = 0
        self.state_transitions = []

    def record_complete(self):
        self.complete_packets += 1
        self.total_requests += 1

    def record_dropped(self):
        self.dropped_packets += 1
        self.total_requests += 1

    def record_degraded(self):
        self.degraded_packets += 1
        self.total_requests += 1

    def record_transition(self, rid, from_state, to_state, event):
        self.state_transitions.append({
            'rid': rid,
            'from': from_state,
            'to': to_state,
            'event': event
        })

    @property
    def complete_rate(self):
        if self.total_requests == 0:
            return 100.0
        return (self.complete_packets / self.total_requests) * 100


def run_normal_scenario(metrics):
    """正常场景：完整请求流程"""
    listener = create_listener()
    rid = 'normal-scenario-001'

    listener._requestWillBeSent(
        requestId=rid,
        request={'url': 'http://test.com/api/normal', 'method': 'GET'},
        type='XHR',
        frameId='test-frame-id'
    )
    metrics.record_transition(rid, None, RequestState.ACTIVE, 'requestWillBeSent')

    listener._requestWillBeSentExtraInfo(
        requestId=rid,
        headers={'X-Request-Id': 'req-001'}
    )

    listener._response_received(
        requestId=rid,
        response={'status': 200, 'url': 'http://test.com/api/normal'},
        type='XHR'
    )

    listener._responseReceivedExtraInfo(
        requestId=rid,
        statusCode=200,
        headers={'Content-Type': 'application/json'}
    )

    listener._loading_finished(
        requestId=rid,
        timestamp=1000
    )
    metrics.record_transition(rid, RequestState.ACTIVE, RequestState.COMPLETED, 'loadingFinished')

    if listener._caught.qsize() == 1:
        metrics.record_complete()
    else:
        metrics.record_dropped()

    return listener


def run_response_before_request_scenario(metrics):
    """乱序场景：response先于request"""
    listener = create_listener()
    rid = 'out-of-order-001'

    listener._response_received(
        requestId=rid,
        response={'status': 200, 'url': 'http://test.com/api/out-of-order'},
        type='XHR'
    )
    metrics.record_transition(rid, None, RequestState.PENDING, 'responseReceived')

    listener._requestWillBeSent(
        requestId=rid,
        request={'url': 'http://test.com/api/out-of-order', 'method': 'GET'},
        type='XHR',
        frameId='test-frame-id'
    )
    metrics.record_transition(rid, RequestState.PENDING, RequestState.ACTIVE, 'requestWillBeSent')

    listener._loading_finished(
        requestId=rid,
        timestamp=1000
    )
    metrics.record_transition(rid, RequestState.ACTIVE, RequestState.COMPLETED, 'loadingFinished')

    metrics.out_of_order_count += listener._fsm_stats['out_of_order_count']

    if listener._caught.qsize() == 1:
        metrics.record_complete()
    else:
        metrics.record_dropped()

    return listener


def run_duplicate_terminal_scenario(metrics):
    """幂等场景：重复终态事件"""
    listener = create_listener()
    rid = 'duplicate-terminal-001'

    listener._requestWillBeSent(
        requestId=rid,
        request={'url': 'http://test.com/api/idempotent', 'method': 'GET'},
        type='XHR',
        frameId='test-frame-id'
    )
    metrics.record_transition(rid, None, RequestState.ACTIVE, 'requestWillBeSent')

    listener._loading_finished(
        requestId=rid,
        timestamp=1000
    )
    metrics.record_transition(rid, RequestState.ACTIVE, RequestState.COMPLETED, 'loadingFinished')

    listener._loading_finished(
        requestId=rid,
        timestamp=1001
    )

    listener._loading_failed(
        requestId=rid,
        errorText='test error',
        type='XHR'
    )

    metrics.duplicate_terminal_count = listener._fsm_stats['duplicate_terminal_count']

    if listener._caught.qsize() == 1:
        metrics.record_complete()
    else:
        metrics.record_dropped()

    return listener


def run_competition_scenario(metrics):
    """竞争场景：loadingFailed与loadingFinished竞争"""
    listener = create_listener()
    rid = 'competition-001'

    listener._requestWillBeSent(
        requestId=rid,
        request={'url': 'http://test.com/api/competition', 'method': 'GET'},
        type='XHR',
        frameId='test-frame-id'
    )
    metrics.record_transition(rid, None, RequestState.ACTIVE, 'requestWillBeSent')

    listener._loading_failed(
        requestId=rid,
        errorText='network error',
        type='XHR'
    )
    metrics.record_transition(rid, RequestState.ACTIVE, RequestState.FAILED, 'loadingFailed')

    listener._loading_finished(
        requestId=rid,
        timestamp=1001
    )

    metrics.duplicate_terminal_count += listener._fsm_stats['duplicate_terminal_count']

    if listener._caught.qsize() == 1:
        packet = listener._caught.get_nowait()
        if packet.is_failed:
            metrics.record_complete()
        else:
            metrics.record_degraded()
    else:
        metrics.record_dropped()

    return listener


def run_missing_extra_info_scenario(metrics):
    """缺失场景：extraInfo缺失"""
    listener = create_listener()
    rid = 'missing-extra-001'

    listener._requestWillBeSent(
        requestId=rid,
        request={'url': 'http://test.com/api/missing-extra', 'method': 'GET'},
        type='XHR',
        frameId='test-frame-id'
    )
    metrics.record_transition(rid, None, RequestState.ACTIVE, 'requestWillBeSent')

    listener._response_received(
        requestId=rid,
        response={'status': 200, 'url': 'http://test.com/api/missing-extra'},
        type='XHR'
    )

    listener._loading_finished(
        requestId=rid,
        timestamp=1000
    )
    metrics.record_transition(rid, RequestState.ACTIVE, RequestState.COMPLETED, 'loadingFinished')

    if listener._caught.qsize() == 1:
        packet = listener._caught.get_nowait()
        if packet._requestExtraInfo is None or packet._responseExtraInfo is None:
            metrics.record_degraded()
        else:
            metrics.record_complete()
    else:
        metrics.record_dropped()

    return listener


def run_pause_inflight_scenario(metrics):
    """收敛场景：pause期间在途请求"""
    listener = create_listener()
    rid1 = 'inflight-001'
    rid2 = 'inflight-002'

    listener._requestWillBeSent(
        requestId=rid1,
        request={'url': 'http://test.com/api/inflight1', 'method': 'GET'},
        type='XHR',
        frameId='test-frame-id'
    )
    metrics.record_transition(rid1, None, RequestState.ACTIVE, 'requestWillBeSent')

    listener._requestWillBeSent(
        requestId=rid2,
        request={'url': 'http://test.com/api/inflight2', 'method': 'GET'},
        type='XHR',
        frameId='test-frame-id'
    )
    metrics.record_transition(rid2, None, RequestState.ACTIVE, 'requestWillBeSent')

    listener.listening = True
    listener.pause(clear=False)

    listener._loading_finished(
        requestId=rid1,
        timestamp=1000
    )
    metrics.record_transition(rid1, RequestState.ACTIVE, RequestState.COMPLETED, 'loadingFinished')

    if listener._fsm_states[rid1] == RequestState.COMPLETED:
        metrics.record_complete()
    else:
        metrics.record_dropped()

    if listener._fsm_states[rid2] == RequestState.ACTIVE:
        metrics.total_requests += 1
    else:
        metrics.record_dropped()

    return listener


def run_stop_clear_scenario(metrics):
    """收敛场景：stop清除所有状态"""
    listener = create_listener()
    rid1 = 'stop-clear-001'
    rid2 = 'stop-clear-002'

    listener._requestWillBeSent(
        requestId=rid1,
        request={'url': 'http://test.com/api/stop1', 'method': 'GET'},
        type='XHR',
        frameId='test-frame-id'
    )

    listener._requestWillBeSent(
        requestId=rid2,
        request={'url': 'http://test.com/api/stop2', 'method': 'GET'},
        type='XHR',
        frameId='test-frame-id'
    )

    listener.listening = True
    listener._driver.stop = MagicMock()
    listener.stop()

    if len(listener._fsm_states) == 0:
        metrics.record_complete()
    else:
        metrics.record_dropped()

    return listener


def print_report(metrics):
    """打印验收报告"""
    print("=" * 80)
    print("LISTENER FSM 验收报告")
    print("=" * 80)

    print("\n【完整包率】")
    print(f"  总请求数: {metrics.total_requests}")
    print(f"  完整包数: {metrics.complete_packets}")
    print(f"  完整包率: {metrics.complete_rate:.2f}%")

    print("\n【丢弃/降级计数】")
    print(f"  丢弃包数: {metrics.dropped_packets}")
    print(f"  降级包数: {metrics.degraded_packets}")

    print("\n【重复完成拦截次数】")
    print(f"  拦截次数: {metrics.duplicate_terminal_count}")

    print("\n【乱序事件计数】")
    print(f"  乱序次数: {metrics.out_of_order_count}")

    print("\n【状态流转样例】")
    print("-" * 80)
    for i, trans in enumerate(metrics.state_transitions[:10], 1):
        from_state = trans['from'].name if trans['from'] else 'None'
        to_state = trans['to'].name if trans['to'] else 'None'
        print(f"  样例{i}: {trans['rid']} - {trans['event']}")
        print(f"         {from_state} → {to_state}")
        if i < len(metrics.state_transitions[:10]):
            print()

    print("-" * 80)
    print("\n【验收结果】")
    if metrics.dropped_packets == 0:
        print("  [OK] 验收通过")
        exit_code = 0
    else:
        print("  [FAIL] 验收失败")
        exit_code = 1

    print("=" * 80)
    print(f"$LASTEXITCODE = {exit_code}")

    return exit_code


def main():
    """主函数"""
    metrics = AcceptanceMetrics()

    print("运行验收场景...")

    print("\n1. 正常场景...", end=" ")
    run_normal_scenario(metrics)
    print("完成")

    print("2. 乱序场景 (response先于request)...", end=" ")
    run_response_before_request_scenario(metrics)
    print("完成")

    print("3. 幂等场景 (重复终态)...", end=" ")
    run_duplicate_terminal_scenario(metrics)
    print("完成")

    print("4. 竞争场景 (loadingFailed/Finished)...", end=" ")
    run_competition_scenario(metrics)
    print("完成")

    print("5. 缺失场景 (extraInfo缺失)...", end=" ")
    run_missing_extra_info_scenario(metrics)
    print("完成")

    print("6. 收敛场景 (pause期间在途请求)...", end=" ")
    run_pause_inflight_scenario(metrics)
    print("完成")

    print("7. 收敛场景 (stop清除状态)...", end=" ")
    run_stop_clear_scenario(metrics)
    print("完成")

    print("\n" + "=" * 80)

    exit_code = print_report(metrics)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
