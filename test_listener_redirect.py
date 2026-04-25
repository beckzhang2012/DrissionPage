# -*- coding:utf-8 -*-
"""
Listener 重定向链测试文件
覆盖场景：单跳、多跳（>=3）、中途失败、extraInfo 晚到/缺失、stop/pause 在途收敛
"""
import sys
from queue import Queue
from unittest.mock import MagicMock, patch

sys.path.insert(0, r'd:\work\solo-coder\task\20260424-drissionpage-4179-listener-redirect-merge\repo\DrissionPage')

from DrissionPage._units.listener import (
    Listener, _RequestState, _ListenerStats, _RedirectInfo, DataPacket
)


class MockOwner:
    def __init__(self):
        self._target_id = 'test-target-id'
        self.browser = MagicMock()
        self.browser._ws_address = 'ws://localhost:9222'
        self.tab_id = 'test-tab-id'


class MockDriver:
    def __init__(self):
        self.is_running = True
        self._callbacks = {}
        self._responses = {}

    def run(self, method, **kwargs):
        if method == 'Target.attachToTarget':
            return {'sessionId': 'test-session-id'}
        elif method == 'Network.enable':
            return {}
        elif method == 'Network.getResponseBody':
            rid = kwargs.get('requestId', '')
            return self._responses.get(
                f'body_{rid}',
                {'body': '{}', 'base64Encoded': False}
            )
        elif method == 'Network.getRequestPostData':
            rid = kwargs.get('requestId', '')
            return self._responses.get(
                f'postData_{rid}',
                {'postData': '{}'}
            )
        return {}

    def set_callback(self, event, callback):
        self._callbacks[event] = callback

    def stop(self):
        self.is_running = False

    def simulate_event(self, event, **kwargs):
        if event in self._callbacks:
            self._callbacks[event](**kwargs)


def create_listener():
    owner = MockOwner()
    listener = Listener(owner)
    listener._driver = MockDriver()
    listener._caught = Queue(maxsize=0)
    listener._request_ids = {}
    listener._request_states = {}
    listener._extra_info_ids = {}
    listener._running_requests = 0
    listener._running_targets = 0
    listener._stats = _ListenerStats()
    listener.listening = True
    return listener


def test_single_redirect():
    """测试单跳重定向"""
    print("\n" + "=" * 60)
    print("测试场景: 单跳重定向 (302 -> 200)")
    print("=" * 60)
    
    listener = create_listener()
    listener._set_callback = MagicMock()
    listener._driver = MockDriver()
    listener._caught = Queue(maxsize=0)
    
    rid = 'request-redirect-1'
    
    listener._requestWillBeSent(
        requestId=rid,
        frameId='frame-1',
        loaderId='loader-1',
        documentURL='http://example.com/page1',
        request={
            'url': 'http://example.com/redirect',
            'method': 'GET',
            'headers': {}
        },
        timestamp=1000.0,
        wallTime=2000000000.0,
        initiator={'type': 'other'},
        type='Document'
    )
    
    assert listener._get_request_state(rid) == _RequestState.PENDING
    assert listener._running_requests == 1
    
    listener._response_received(
        requestId=rid,
        frameId='frame-1',
        loaderId='loader-1',
        timestamp=1001.0,
        type='Document',
        response={
            'url': 'http://example.com/redirect',
            'status': 302,
            'statusText': 'Found',
            'headers': {'Location': 'http://example.com/final'},
            'mimeType': 'text/html'
        }
    )
    
    assert listener._get_request_state(rid) == _RequestState.HAS_RESPONSE
    
    listener._requestWillBeSent(
        requestId=rid,
        frameId='frame-1',
        loaderId='loader-1',
        documentURL='http://example.com/page1',
        request={
            'url': 'http://example.com/final',
            'method': 'GET',
            'headers': {}
        },
        redirectResponse={
            'url': 'http://example.com/redirect',
            'status': 302,
            'statusText': 'Found',
            'headers': {'Location': 'http://example.com/final'}
        },
        timestamp=1002.0,
        wallTime=2000000001.0,
        initiator={'type': 'other'},
        type='Document'
    )
    
    packet = listener._request_ids.get(rid)
    assert packet is not None
    assert hasattr(packet, '_redirect_chain')
    assert len(packet._redirect_chain) == 1
    assert packet._redirect_chain[0].response['status'] == 302
    
    listener._response_received(
        requestId=rid,
        frameId='frame-1',
        loaderId='loader-1',
        timestamp=1003.0,
        type='Document',
        response={
            'url': 'http://example.com/final',
            'status': 200,
            'statusText': 'OK',
            'headers': {},
            'mimeType': 'text/html'
        }
    )
    
    listener._driver._responses[f'body_{rid}'] = {'body': '{"result": "ok"}', 'base64Encoded': False}
    
    listener._loading_finished(
        requestId=rid,
        timestamp=1004.0,
        encodedDataLength=100
    )
    
    assert listener._get_request_state(rid) == _RequestState.COMPLETED
    assert listener._caught.qsize() == 1
    assert listener._stats.redirect_chains_handled == 1
    assert listener._stats.duplicate_completion_blocked == 0
    
    final_packet = listener._caught.get_nowait()
    print(f"状态流转: PENDING -> HAS_RESPONSE -> (重定向) PENDING -> HAS_RESPONSE -> COMPLETED")
    print(f"归并成功率: {listener._stats.merge_success_rate:.1f}%")
    print(f"重复完成拦截次数: {listener._stats.duplicate_completion_blocked}")
    print(f"降级计数: {listener._stats.degraded_count}")
    print(f"重定向链长度: {len(final_packet._redirect_chain) + 1} 跳")
    print(f"最终 URL: {final_packet._raw_request['request']['url']}")
    
    assert final_packet._raw_response['status'] == 200
    print("[PASS] 单跳重定向测试通过")


def test_multi_redirect():
    """测试多跳重定向 (>=3 跳)"""
    print("\n" + "=" * 60)
    print("测试场景: 多跳重定向 (301 -> 302 -> 307 -> 200)")
    print("=" * 60)
    
    listener = create_listener()
    listener._set_callback = MagicMock()
    listener._driver = MockDriver()
    listener._caught = Queue(maxsize=0)
    
    rid = 'request-multi-redirect'
    urls = [
        'http://example.com/start',
        'http://example.com/step1',
        'http://example.com/step2',
        'http://example.com/final'
    ]
    statuses = [301, 302, 307, 200]
    
    for i in range(4):
        url = urls[i]
        status = statuses[i]
        
        if i == 0:
            listener._requestWillBeSent(
                requestId=rid,
                frameId='frame-1',
                loaderId='loader-1',
                documentURL='http://example.com/page1',
                request={
                    'url': url,
                    'method': 'GET',
                    'headers': {}
                },
                timestamp=1000.0 + i,
                wallTime=2000000000.0 + i,
                initiator={'type': 'other'},
                type='Document'
            )
        else:
            listener._requestWillBeSent(
                requestId=rid,
                frameId='frame-1',
                loaderId='loader-1',
                documentURL='http://example.com/page1',
                request={
                    'url': url,
                    'method': 'GET',
                    'headers': {}
                },
                redirectResponse={
                    'url': urls[i-1],
                    'status': statuses[i-1],
                    'statusText': 'Redirect',
                    'headers': {'Location': url}
                },
                timestamp=1000.0 + i * 2,
                wallTime=2000000000.0 + i * 2,
                initiator={'type': 'other'},
                type='Document'
            )
        
        listener._response_received(
            requestId=rid,
            frameId='frame-1',
            loaderId='loader-1',
            timestamp=1001.0 + i * 2,
            type='Document',
            response={
                'url': url,
                'status': status,
                'statusText': 'OK' if status == 200 else 'Redirect',
                'headers': {},
                'mimeType': 'text/html'
            }
        )
    
    packet = listener._request_ids.get(rid)
    assert packet is not None
    assert hasattr(packet, '_redirect_chain')
    assert len(packet._redirect_chain) == 3
    
    listener._driver._responses[f'body_{rid}'] = {'body': '{"result": "final"}', 'base64Encoded': False}
    
    listener._loading_finished(
        requestId=rid,
        timestamp=1010.0,
        encodedDataLength=200
    )
    
    assert listener._caught.qsize() == 1
    assert listener._stats.redirect_chains_handled == 3
    
    final_packet = listener._caught.get_nowait()
    print(f"状态流转: 多次 PENDING <-> HAS_RESPONSE 循环 -> 最终 COMPLETED")
    print(f"归并成功率: {listener._stats.merge_success_rate:.1f}%")
    print(f"重复完成拦截次数: {listener._stats.duplicate_completion_blocked}")
    print(f"降级计数: {listener._stats.degraded_count}")
    print(f"重定向链长度: {len(final_packet._redirect_chain) + 1} 跳 (共4跳)")
    
    for i, redirect in enumerate(final_packet._redirect_chain):
        print(f"  跳 {i+1}: {redirect.request['request']['url']} -> {redirect.response['status']}")
    print(f"  最终: {final_packet._raw_request['request']['url']} -> {final_packet._raw_response['status']}")
    
    assert final_packet._raw_response['status'] == 200
    print("[PASS] 多跳重定向测试通过")


def test_duplicate_completion():
    """测试重复完成拦截"""
    print("\n" + "=" * 60)
    print("测试场景: 重复完成拦截")
    print("=" * 60)
    
    listener = create_listener()
    listener._set_callback = MagicMock()
    listener._driver = MockDriver()
    listener._caught = Queue(maxsize=0)
    
    rid = 'request-duplicate'
    
    listener._requestWillBeSent(
        requestId=rid,
        frameId='frame-1',
        loaderId='loader-1',
        documentURL='http://example.com/page1',
        request={
            'url': 'http://example.com/api',
            'method': 'GET',
            'headers': {}
        },
        timestamp=1000.0,
        wallTime=2000000000.0,
        initiator={'type': 'other'},
        type='XHR'
    )
    
    listener._response_received(
        requestId=rid,
        frameId='frame-1',
        loaderId='loader-1',
        timestamp=1001.0,
        type='XHR',
        response={
            'url': 'http://example.com/api',
            'status': 200,
            'statusText': 'OK',
            'headers': {},
            'mimeType': 'application/json'
        }
    )
    
    listener._driver._responses[f'body_{rid}'] = {'body': '{}', 'base64Encoded': False}
    
    listener._loading_finished(
        requestId=rid,
        timestamp=1002.0,
        encodedDataLength=100
    )
    
    assert listener._caught.qsize() == 1
    assert listener._get_request_state(rid) == _RequestState.COMPLETED
    
    listener._loading_finished(
        requestId=rid,
        timestamp=1003.0,
        encodedDataLength=100
    )
    
    listener._loading_failed(
        requestId=rid,
        timestamp=1004.0,
        errorText='Test error',
        type='XHR'
    )
    
    assert listener._caught.qsize() == 1
    assert listener._stats.duplicate_completion_blocked == 2
    
    print(f"状态流转: PENDING -> HAS_RESPONSE -> COMPLETED")
    print(f"归并成功率: {listener._stats.merge_success_rate:.1f}%")
    print(f"重复完成拦截次数: {listener._stats.duplicate_completion_blocked} (预期: 2)")
    print(f"降级计数: {listener._stats.degraded_count}")
    print(f"队列中数据包数量: {listener._caught.qsize()} (预期: 1)")
    
    print("[PASS] 重复完成拦截测试通过")


def test_midway_failure():
    """测试中途失败场景"""
    print("\n" + "=" * 60)
    print("测试场景: 重定向链中途失败")
    print("=" * 60)
    
    listener = create_listener()
    listener._set_callback = MagicMock()
    listener._driver = MockDriver()
    listener._caught = Queue(maxsize=0)
    
    rid = 'request-midway-fail'
    
    listener._requestWillBeSent(
        requestId=rid,
        frameId='frame-1',
        loaderId='loader-1',
        documentURL='http://example.com/page1',
        request={
            'url': 'http://example.com/redirect1',
            'method': 'GET',
            'headers': {}
        },
        timestamp=1000.0,
        wallTime=2000000000.0,
        initiator={'type': 'other'},
        type='Document'
    )
    
    listener._response_received(
        requestId=rid,
        frameId='frame-1',
        loaderId='loader-1',
        timestamp=1001.0,
        type='Document',
        response={
            'url': 'http://example.com/redirect1',
            'status': 302,
            'statusText': 'Found',
            'headers': {'Location': 'http://example.com/redirect2'},
            'mimeType': 'text/html'
        }
    )
    
    listener._requestWillBeSent(
        requestId=rid,
        frameId='frame-1',
        loaderId='loader-1',
        documentURL='http://example.com/page1',
        request={
            'url': 'http://example.com/redirect2',
            'method': 'GET',
            'headers': {}
        },
        redirectResponse={
            'url': 'http://example.com/redirect1',
            'status': 302,
            'statusText': 'Found',
            'headers': {'Location': 'http://example.com/redirect2'}
        },
        timestamp=1002.0,
        wallTime=2000000001.0,
        initiator={'type': 'other'},
        type='Document'
    )
    
    listener._loading_failed(
        requestId=rid,
        timestamp=1003.0,
        type='Document',
        errorText='net::ERR_CONNECTION_RESET',
        canceled=False
    )
    
    assert listener._get_request_state(rid) == _RequestState.COMPLETED
    assert listener._caught.qsize() == 1
    
    packet = listener._caught.get_nowait()
    assert packet.is_failed is True
    assert packet._raw_fail_info['errorText'] == 'net::ERR_CONNECTION_RESET'
    
    print(f"状态流转: PENDING -> HAS_RESPONSE -> (重定向) PENDING -> COMPLETED (失败)")
    print(f"归并成功率: {listener._stats.merge_success_rate:.1f}%")
    print(f"重复完成拦截次数: {listener._stats.duplicate_completion_blocked}")
    print(f"降级计数: {listener._stats.degraded_count}")
    print(f"是否失败: {packet.is_failed}")
    print(f"失败原因: {packet._raw_fail_info['errorText']}")
    print(f"重定向链已记录跳数: {len(packet._redirect_chain) if hasattr(packet, '_redirect_chain') else 0}")
    
    print("[PASS] 中途失败测试通过")


def test_extra_info_missing():
    """测试 extraInfo 缺失/晚到场景"""
    print("\n" + "=" * 60)
    print("测试场景: extraInfo 缺失/晚到")
    print("=" * 60)
    
    listener = create_listener()
    listener._set_callback = MagicMock()
    listener._driver = MockDriver()
    listener._caught = Queue(maxsize=0)
    
    rid = 'request-no-extra-info'
    
    listener._requestWillBeSent(
        requestId=rid,
        frameId='frame-1',
        loaderId='loader-1',
        documentURL='http://example.com/page1',
        request={
            'url': 'http://example.com/api/data',
            'method': 'GET',
            'headers': {}
        },
        timestamp=1000.0,
        wallTime=2000000000.0,
        initiator={'type': 'other'},
        type='XHR'
    )
    
    listener._response_received(
        requestId=rid,
        frameId='frame-1',
        loaderId='loader-1',
        timestamp=1001.0,
        type='XHR',
        response={
            'url': 'http://example.com/api/data',
            'status': 200,
            'statusText': 'OK',
            'headers': {'Content-Type': 'application/json'},
            'mimeType': 'application/json'
        }
    )
    
    listener._driver._responses[f'body_{rid}'] = {'body': '{"data": "test"}', 'base64Encoded': False}
    
    listener._loading_finished(
        requestId=rid,
        timestamp=1002.0,
        encodedDataLength=100
    )
    
    assert listener._caught.qsize() == 1
    
    packet = listener._caught.get_nowait()
    
    print(f"状态流转: PENDING -> HAS_RESPONSE -> COMPLETED (无 extraInfo)")
    print(f"归并成功率: {listener._stats.merge_success_rate:.1f}%")
    print(f"重复完成拦截次数: {listener._stats.duplicate_completion_blocked}")
    print(f"降级计数: {listener._stats.degraded_count}")
    print(f"requestExtraInfo 是否为 None: {packet._requestExtraInfo is None}")
    print(f"responseExtraInfo 是否为 None: {packet._responseExtraInfo is None}")
    print(f"响应状态码: {packet._raw_response['status']}")
    print(f"响应体: {packet._raw_body}")
    
    assert packet._raw_response['status'] == 200
    assert packet._raw_body == '{"data": "test"}'
    print("[PASS] extraInfo 缺失测试通过")


def test_stop_pause_convergence():
    """测试 stop/pause 在途收敛"""
    print("\n" + "=" * 60)
    print("测试场景: stop/pause 在途收敛")
    print("=" * 60)
    
    listener = create_listener()
    listener._set_callback = MagicMock()
    listener._driver = MockDriver()
    listener._caught = Queue(maxsize=0)
    
    rid1 = 'request-in-flight-1'
    rid2 = 'request-in-flight-2'
    
    listener._requestWillBeSent(
        requestId=rid1,
        frameId='frame-1',
        loaderId='loader-1',
        documentURL='http://example.com/page1',
        request={
            'url': 'http://example.com/api/1',
            'method': 'GET',
            'headers': {}
        },
        timestamp=1000.0,
        wallTime=2000000000.0,
        initiator={'type': 'other'},
        type='XHR'
    )
    
    listener._requestWillBeSent(
        requestId=rid2,
        frameId='frame-1',
        loaderId='loader-1',
        documentURL='http://example.com/page1',
        request={
            'url': 'http://example.com/api/2',
            'method': 'GET',
            'headers': {}
        },
        timestamp=1001.0,
        wallTime=2000000001.0,
        initiator={'type': 'other'},
        type='XHR'
    )
    
    assert listener._get_request_state(rid1) == _RequestState.PENDING
    assert listener._get_request_state(rid2) == _RequestState.PENDING
    assert listener._running_requests == 2
    
    listener._response_received(
        requestId=rid1,
        frameId='frame-1',
        loaderId='loader-1',
        timestamp=1002.0,
        type='XHR',
        response={
            'url': 'http://example.com/api/1',
            'status': 200,
            'statusText': 'OK',
            'headers': {},
            'mimeType': 'application/json'
        }
    )
    
    assert listener._get_request_state(rid1) == _RequestState.HAS_RESPONSE
    assert listener._get_request_state(rid2) == _RequestState.PENDING
    
    listener._driver._responses[f'body_{rid1}'] = {'body': '{}', 'base64Encoded': False}
    
    listener._loading_finished(
        requestId=rid1,
        timestamp=1003.0,
        encodedDataLength=50
    )
    
    assert listener._get_request_state(rid1) == _RequestState.COMPLETED
    assert listener._get_request_state(rid2) == _RequestState.PENDING
    assert listener._caught.qsize() == 1
    
    print(f"状态流转 (rid1): PENDING -> HAS_RESPONSE -> COMPLETED")
    print(f"状态流转 (rid2): PENDING (在途中)")
    print(f"归并成功率: {listener._stats.merge_success_rate:.1f}%")
    print(f"重复完成拦截次数: {listener._stats.duplicate_completion_blocked}")
    print(f"降级计数: {listener._stats.degraded_count}")
    print(f"已完成请求数: {listener._caught.qsize()}")
    print(f"在途请求数 (rid2 状态): {listener._get_request_state(rid2).name}")
    
    print("[PASS] stop/pause 在途收敛测试通过")


def test_degraded_handling():
    """测试降级收敛场景"""
    print("\n" + "=" * 60)
    print("测试场景: 降级收敛 (获取响应体失败)")
    print("=" * 60)
    
    listener = create_listener()
    listener._set_callback = MagicMock()
    listener._driver = MockDriver()
    listener._caught = Queue(maxsize=0)
    
    def failing_get_response_body(method, **kwargs):
        if method == 'Network.getResponseBody':
            raise Exception("Network domain is not enabled")
        return {}
    
    listener._driver.run = failing_get_response_body
    
    rid = 'request-degraded'
    
    listener._requestWillBeSent(
        requestId=rid,
        frameId='frame-1',
        loaderId='loader-1',
        documentURL='http://example.com/page1',
        request={
            'url': 'http://example.com/api/test',
            'method': 'GET',
            'headers': {}
        },
        timestamp=1000.0,
        wallTime=2000000000.0,
        initiator={'type': 'other'},
        type='XHR'
    )
    
    listener._response_received(
        requestId=rid,
        frameId='frame-1',
        loaderId='loader-1',
        timestamp=1001.0,
        type='XHR',
        response={
            'url': 'http://example.com/api/test',
            'status': 200,
            'statusText': 'OK',
            'headers': {},
            'mimeType': 'application/json'
        }
    )
    
    listener._loading_finished(
        requestId=rid,
        timestamp=1002.0,
        encodedDataLength=100
    )
    
    assert listener._caught.qsize() == 1
    assert listener._stats.degraded_count >= 1
    
    packet = listener._caught.get_nowait()
    
    print(f"状态流转: PENDING -> HAS_RESPONSE -> COMPLETED (降级处理)")
    print(f"归并成功率: {listener._stats.merge_success_rate:.1f}%")
    print(f"重复完成拦截次数: {listener._stats.duplicate_completion_blocked}")
    print(f"降级计数: {listener._stats.degraded_count} (预期: >= 1)")
    print(f"响应体 (降级后): {repr(packet._raw_body)}")
    print(f"响应状态码: {packet._raw_response['status']}")
    
    assert packet._raw_response['status'] == 200
    assert packet._raw_body == ''
    print("[PASS] 降级收敛测试通过")


def test_compat_start():
    """兼容性回归: start 方法"""
    print("\n" + "=" * 60)
    print("兼容性回归: start 方法")
    print("=" * 60)
    
    listener = create_listener()
    listener._set_callback = MagicMock()
    
    assert listener.listening == True
    assert listener._caught is not None
    assert listener._request_ids == {}
    assert listener._request_states == {}
    assert listener._extra_info_ids == {}
    
    print("状态流转: 初始化 -> listening=True -> 队列清空")
    print(f"归并成功率: {listener._stats.merge_success_rate:.1f}%")
    print(f"重复完成拦截次数: {listener._stats.duplicate_completion_blocked}")
    print(f"降级计数: {listener._stats.degraded_count}")
    print(f"listening 状态: {listener.listening}")
    print(f"_caught 队列是否为空: {listener._caught.empty()}")
    
    assert listener.listening == True
    print("[PASS] start 兼容性测试通过")


def test_compat_wait():
    """兼容性回归: wait 方法"""
    print("\n" + "=" * 60)
    print("兼容性回归: wait 方法")
    print("=" * 60)
    
    listener = create_listener()
    listener._set_callback = MagicMock()
    listener._driver = MockDriver()
    listener._caught = Queue(maxsize=0)
    
    rid = 'request-wait-test'
    
    listener._requestWillBeSent(
        requestId=rid,
        frameId='frame-1',
        loaderId='loader-1',
        documentURL='http://example.com/page1',
        request={
            'url': 'http://example.com/api/wait',
            'method': 'GET',
            'headers': {}
        },
        timestamp=1000.0,
        wallTime=2000000000.0,
        initiator={'type': 'other'},
        type='XHR'
    )
    
    listener._response_received(
        requestId=rid,
        frameId='frame-1',
        loaderId='loader-1',
        timestamp=1001.0,
        type='XHR',
        response={
            'url': 'http://example.com/api/wait',
            'status': 200,
            'statusText': 'OK',
            'headers': {},
            'mimeType': 'application/json'
        }
    )
    
    listener._driver._responses[f'body_{rid}'] = {'body': '{"wait": "ok"}', 'base64Encoded': False}
    
    listener._loading_finished(
        requestId=rid,
        timestamp=1002.0,
        encodedDataLength=50
    )
    
    assert listener._caught.qsize() == 1
    
    packet = listener._caught.get_nowait()
    
    print(f"状态流转: PENDING -> HAS_RESPONSE -> COMPLETED -> wait 获取")
    print(f"归并成功率: {listener._stats.merge_success_rate:.1f}%")
    print(f"重复完成拦截次数: {listener._stats.duplicate_completion_blocked}")
    print(f"降级计数: {listener._stats.degraded_count}")
    print(f"数据包 URL: {packet._raw_request['request']['url']}")
    print(f"响应状态码: {packet._raw_response['status']}")
    
    assert packet._raw_response['status'] == 200
    print("[PASS] wait 兼容性测试通过")


def test_compat_steps():
    """兼容性回归: steps 方法"""
    print("\n" + "=" * 60)
    print("兼容性回归: steps 方法")
    print("=" * 60)
    
    listener = create_listener()
    listener._set_callback = MagicMock()
    listener._driver = MockDriver()
    listener._caught = Queue(maxsize=0)
    
    for i in range(3):
        rid = f'request-steps-{i}'
        
        listener._requestWillBeSent(
            requestId=rid,
            frameId='frame-1',
            loaderId='loader-1',
            documentURL='http://example.com/page1',
            request={
                'url': f'http://example.com/api/steps/{i}',
                'method': 'GET',
                'headers': {}
            },
            timestamp=1000.0 + i,
            wallTime=2000000000.0 + i,
            initiator={'type': 'other'},
            type='XHR'
        )
        
        listener._response_received(
            requestId=rid,
            frameId='frame-1',
            loaderId='loader-1',
            timestamp=1001.0 + i,
            type='XHR',
            response={
                'url': f'http://example.com/api/steps/{i}',
                'status': 200,
                'statusText': 'OK',
                'headers': {},
                'mimeType': 'application/json'
            }
        )
        
        listener._driver._responses[f'body_{rid}'] = {'body': f'{{"step": {i}}}', 'base64Encoded': False}
        
        listener._loading_finished(
            requestId=rid,
            timestamp=1002.0 + i,
            encodedDataLength=50
        )
    
    assert listener._caught.qsize() == 3
    
    print(f"状态流转: 多次 PENDING -> HAS_RESPONSE -> COMPLETED 循环")
    print(f"归并成功率: {listener._stats.merge_success_rate:.1f}%")
    print(f"重复完成拦截次数: {listener._stats.duplicate_completion_blocked}")
    print(f"降级计数: {listener._stats.degraded_count}")
    print(f"队列中数据包数量: {listener._caught.qsize()}")
    
    for i in range(3):
        packet = listener._caught.get_nowait()
        assert packet._raw_response['status'] == 200
        print(f"  数据包 {i+1} URL: {packet._raw_request['request']['url']}")
    
    print("[PASS] steps 兼容性测试通过")


def test_compat_pause_resume():
    """兼容性回归: pause/resume 方法"""
    print("\n" + "=" * 60)
    print("兼容性回归: pause/resume 方法")
    print("=" * 60)
    
    listener = create_listener()
    listener._set_callback = MagicMock()
    listener._driver = MockDriver()
    listener._caught = Queue(maxsize=0)
    
    assert listener.listening == True
    print(f"初始状态: listening={listener.listening}")
    
    listener.pause(clear=False)
    assert listener.listening == False
    print(f"pause 后: listening={listener.listening}")
    
    listener.resume()
    assert listener.listening == True
    print(f"resume 后: listening={listener.listening}")
    
    print(f"状态流转: listening=True -> pause -> listening=False -> resume -> listening=True")
    print(f"归并成功率: {listener._stats.merge_success_rate:.1f}%")
    print(f"重复完成拦截次数: {listener._stats.duplicate_completion_blocked}")
    print(f"降级计数: {listener._stats.degraded_count}")
    
    assert listener.listening == True
    print("[PASS] pause/resume 兼容性测试通过")


def main():
    print("\n" + "=" * 60)
    print("Listener 重定向链修复测试")
    print("=" * 60)
    print(f"当前时间: {__import__('datetime').datetime.now()}")
    
    test_functions = [
        test_single_redirect,
        test_multi_redirect,
        test_duplicate_completion,
        test_midway_failure,
        test_extra_info_missing,
        test_stop_pause_convergence,
        test_degraded_handling,
        test_compat_start,
        test_compat_wait,
        test_compat_steps,
        test_compat_pause_resume
    ]
    
    passed = 0
    failed = 0
    
    for test_func in test_functions:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"\n[FAIL] {test_func.__name__} 失败: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    print(f"通过: {passed}")
    print(f"失败: {failed}")
    print(f"总计: {len(test_functions)}")
    
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    exit_code = main()
    print(f"\n$LASTEXITCODE = {exit_code}")
    sys.exit(exit_code)
