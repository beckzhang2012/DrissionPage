# -*- coding:utf-8 -*-
"""
HAR导出功能测试
测试场景：
1. 正常请求数据包
2. 失败请求数据包
3. 超大body截断
"""
import json
import tempfile
import os
from base64 import b64encode
from DrissionPage._units.listener import DataPacket


def create_normal_packet():
    """创建一个正常的数据包"""
    packet = DataPacket('tab-12345', 'test-api')
    packet._raw_request = {
        'requestId': '12345',
        'loaderId': 'loader-123',
        'documentURL': 'https://example.com/page',
        'frameId': 'frame-123',
        'request': {
            'url': 'https://api.example.com/data?key=value',
            'method': 'GET',
            'headers': {
                'Accept': 'application/json',
                'User-Agent': 'DrissionPage Test',
                'Referer': 'https://example.com/'
            }
        },
        'timestamp': 1234567890.123456,
        'wallTime': 1713600000.0,
        'initiator': {'type': 'script'},
        'type': 'XHR'
    }
    packet._raw_response = {
        'url': 'https://api.example.com/data?key=value',
        'status': 200,
        'statusText': 'OK',
        'headers': {
            'Content-Type': 'application/json',
            'Cache-Control': 'no-cache',
            'Server': 'nginx'
        },
        'headersText': 'HTTP/1.1 200 OK',
        'mimeType': 'application/json',
        'connectionReused': False,
        'connectionId': 123,
        'encodedDataLength': 150,
        'timing': {
            'requestTime': 1234567890.0,
            'proxyStart': -1,
            'proxyEnd': -1,
            'dnsStart': 0,
            'dnsEnd': 50,
            'connectStart': 50,
            'connectEnd': 100,
            'sslStart': -1,
            'sslEnd': -1,
            'sendStart': 100,
            'sendEnd': 105,
            'receiveHeadersEnd': 200,
        }
    }
    packet._raw_body = json.dumps({'status': 'ok', 'data': [1, 2, 3]})
    packet._base64_body = False
    packet._resource_type = 'XHR'
    packet.is_failed = False
    return packet


def create_failed_packet():
    """创建一个失败的数据包"""
    packet = DataPacket('tab-12345', 'test-failed')
    packet._raw_request = {
        'requestId': '67890',
        'loaderId': 'loader-456',
        'documentURL': 'https://example.com/page',
        'frameId': 'frame-123',
        'request': {
            'url': 'https://api.example.com/broken-endpoint',
            'method': 'POST',
            'headers': {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
            'hasPostData': True,
            'postData': json.dumps({'param': 'value'})
        },
        'timestamp': 1234567891.0,
        'wallTime': 1713600001.0,
        'initiator': {'type': 'script'},
        'type': 'XHR'
    }
    packet._raw_response = {
        'url': 'https://api.example.com/broken-endpoint',
        'status': 500,
        'statusText': 'Internal Server Error',
        'headers': {
            'Content-Type': 'text/plain',
        },
        'mimeType': 'text/plain',
        'timing': None
    }
    packet._raw_body = 'Internal Server Error: Database connection failed'
    packet._base64_body = False
    packet._raw_fail_info = {
        'requestId': '67890',
        'timestamp': 1234567892.0,
        'type': 'XHR',
        'errorText': 'net::ERR_CONNECTION_RESET',
        'canceled': False,
        'blockedReason': None
    }
    packet._resource_type = 'XHR'
    packet.is_failed = True
    return packet


def create_large_body_packet():
    """创建一个带有超大body的数据包"""
    packet = DataPacket('tab-12345', 'test-large')
    packet._raw_request = {
        'requestId': 'large-001',
        'loaderId': 'loader-large',
        'documentURL': 'https://example.com/page',
        'frameId': 'frame-123',
        'request': {
            'url': 'https://api.example.com/large-data',
            'method': 'GET',
            'headers': {
                'Accept': 'text/plain',
            }
        },
        'timestamp': 1234567893.0,
        'wallTime': 1713600003.0,
        'initiator': {'type': 'other'},
        'type': 'Document'
    }
    packet._raw_response = {
        'url': 'https://api.example.com/large-data',
        'status': 200,
        'statusText': 'OK',
        'headers': {
            'Content-Type': 'text/plain',
            'Content-Length': '200000',
        },
        'mimeType': 'text/plain',
        'timing': {
            'requestTime': 1234567893.0,
            'dnsStart': 0,
            'dnsEnd': 10,
            'connectStart': 10,
            'connectEnd': 30,
            'sendStart': 30,
            'sendEnd': 31,
            'receiveHeadersEnd': 50,
        }
    }
    large_body = 'A' * 150000
    packet._raw_body = large_body
    packet._base64_body = False
    packet._resource_type = 'Document'
    packet.is_failed = False
    return packet


def create_binary_body_packet():
    """创建一个二进制body的数据包"""
    packet = DataPacket('tab-12345', 'test-binary')
    packet._raw_request = {
        'requestId': 'binary-001',
        'loaderId': 'loader-binary',
        'documentURL': 'https://example.com/page',
        'request': {
            'url': 'https://example.com/image.png',
            'method': 'GET',
            'headers': {
                'Accept': 'image/png,image/*',
            }
        },
        'timestamp': 1234567894.0,
        'wallTime': 1713600004.0,
        'type': 'Image'
    }
    packet._raw_response = {
        'url': 'https://example.com/image.png',
        'status': 200,
        'statusText': 'OK',
        'headers': {
            'Content-Type': 'image/png',
        },
        'mimeType': 'image/png',
        'timing': None
    }
    binary_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10\x08\x02\x00\x00\x00\x90\x91h6\x00\x00\x00\x04sBIT\x08\x08\x08\x08|\x88d\x88\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00\x0b\x13\x01\x00\x9a\x9c\x18\x00\x00\x00)IDATx\x9cc\xcb\xcf\x07\x00\x02\t\x01\x82h1\xcb\xc8\x8c\x00\x00\x18\xcd\x04?I\x8d\x0b\x00\x00\x00\x00IEND\xaeB`\x82'
    packet._raw_body = b64encode(binary_data).decode('ascii')
    packet._base64_body = True
    packet._resource_type = 'Image'
    packet.is_failed = False
    return packet


def test_normal_packet_to_har():
    """测试正常数据包转换为HAR entry"""
    print('=' * 60)
    print('测试1: 正常请求数据包')
    print('=' * 60)
    
    packet = create_normal_packet()
    entry = packet.to_har_entry(include_body=True)
    
    assert 'startedDateTime' in entry
    assert entry['request']['method'] == 'GET'
    assert entry['request']['url'] == 'https://api.example.com/data?key=value'
    assert len(entry['request']['headers']) == 3
    
    assert entry['response']['status'] == 200
    assert entry['response']['statusText'] == 'OK'
    assert entry['response']['content']['mimeType'] == 'application/json'
    assert 'text' in entry['response']['content']
    
    assert 'timings' in entry
    assert entry['timings']['dns'] >= 0
    assert entry['timings']['connect'] >= 0
    assert entry['timings']['send'] >= 0
    assert entry['timings']['wait'] >= 0
    
    assert not entry.get('_failed', False)
    
    print(f'请求URL: {entry["request"]["url"]}')
    print(f'请求方法: {entry["request"]["method"]}')
    print(f'响应状态: {entry["response"]["status"]} {entry["response"]["statusText"]}')
    print(f'响应类型: {entry["response"]["content"]["mimeType"]}')
    print(f'响应体大小: {entry["response"]["content"]["size"]} 字节')
    print(f'Timing: dns={entry["timings"]["dns"]}ms, connect={entry["timings"]["connect"]}ms, send={entry["timings"]["send"]}ms, wait={entry["timings"]["wait"]}ms')
    print(f'总耗时: {entry["time"]}ms')
    print('[PASS] 测试通过')
    return entry


def test_failed_packet_to_har():
    """测试失败数据包转换为HAR entry"""
    print('\n' + '=' * 60)
    print('测试2: 失败请求数据包')
    print('=' * 60)
    
    packet = create_failed_packet()
    entry = packet.to_har_entry(include_body=True)
    
    assert entry.get('_failed', True)
    assert entry['response']['status'] == 500 or entry['response']['status'] == 0
    assert entry['response']['statusText'] or entry.get('_errorType')
    
    print(f'请求URL: {entry["request"]["url"]}')
    print(f'请求方法: {entry["request"]["method"]}')
    print(f'响应状态: {entry["response"]["status"]} {entry["response"]["statusText"]}')
    print(f'请求失败标记: _failed={entry.get("_failed")}')
    print(f'错误类型: {entry.get("_errorType")}')
    print(f'错误文本: {entry["response"]["statusText"]}')
    
    if entry['request'].get('postData'):
        print(f'请求体大小: {entry["request"]["bodySize"]} 字节')
        print(f'请求体内容: {entry["request"]["postData"]["text"][:100]}...')
    
    print('[PASS] 测试通过')
    return entry


def test_large_body_truncation():
    """测试超大body截断"""
    print('\n' + '=' * 60)
    print('测试3: 超大body截断')
    print('=' * 60)
    
    packet = create_large_body_packet()
    max_body_kb = 1
    
    entry = packet.to_har_entry(include_body=True, max_body_kb=max_body_kb)
    
    max_bytes = max_body_kb * 1024
    body_text = entry['response']['content'].get('text', '')
    actual_size = len(body_text)
    
    print(f'原始body大小: {len(packet._raw_body)} 字节')
    print(f'限制大小: {max_bytes} 字节 (1KB)')
    print(f'实际保存大小: {actual_size} 字节')
    print(f'截断标记 _truncated: {entry["response"]["content"].get("_truncated")}')
    
    assert actual_size <= max_bytes + 20
    assert entry['response']['content'].get('_truncated') == True
    assert '[truncated]' in body_text
    
    print(f'截断标记内容: ... [truncated]')
    print('[PASS] 测试通过')
    return entry


def test_binary_body_encoding():
    """测试二进制body的base64编码"""
    print('\n' + '=' * 60)
    print('测试4: 二进制body的Base64编码')
    print('=' * 60)
    
    packet = create_binary_body_packet()
    entry = packet.to_har_entry(include_body=True)
    
    print(f'原始body是Base64: {packet._base64_body}')
    print(f'响应类型: {entry["response"]["content"]["mimeType"]}')
    print(f'编码方式: {entry["response"]["content"].get("encoding")}')
    print(f'响应体大小: {entry["response"]["content"]["size"]} 字节')
    
    assert entry['response']['content'].get('encoding') == 'base64'
    assert 'text' in entry['response']['content']
    
    body_text = entry['response']['content']['text']
    assert len(body_text) > 0
    
    print('[PASS] 测试通过')
    return entry


def test_export_har_function():
    """测试export_har功能（模拟）"""
    print('\n' + '=' * 60)
    print('测试5: HAR文件导出')
    print('=' * 60)
    
    packets = [
        create_normal_packet(),
        create_failed_packet(),
        create_large_body_packet(),
    ]
    
    entries = []
    for packet in packets:
        entry = packet.to_har_entry(include_body=True, max_body_kb=64)
        entries.append(entry)
    
    har = {
        'log': {
            'version': '1.2',
            'creator': {'name': 'DrissionPage', 'version': 'Test'},
            'browser': {'name': 'Chromium', 'version': 'unknown'},
            'pages': [],
            'entries': entries,
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.har', delete=False, encoding='utf-8') as f:
        json.dump(har, f, ensure_ascii=False, indent=2)
        temp_path = f.name
    
    print(f'临时HAR文件: {temp_path}')
    print(f'entries数量: {len(entries)}')
    
    with open(temp_path, 'r', encoding='utf-8') as f:
        loaded_har = json.load(f)
    
    assert loaded_har['log']['version'] == '1.2'
    assert len(loaded_har['log']['entries']) == 3
    
    print(f'文件验证: log.version={loaded_har["log"]["version"]}')
    print(f'entries数量验证: {len(loaded_har["log"]["entries"])}')
    
    for i, entry in enumerate(loaded_har['log']['entries']):
        print(f'  Entry {i+1}: {entry["request"]["method"]} {entry["request"]["url"][:60]}...')
    
    os.unlink(temp_path)
    print(f'临时文件已删除')
    print('[PASS] 测试通过')
    
    return har


def test_error_handling():
    """测试异常处理 - 单条异常不中断整体"""
    print('\n' + '=' * 60)
    print('测试6: 异常处理 - 单条异常不中断整体')
    print('=' * 60)
    
    normal_packet = create_normal_packet()
    bad_packet = DataPacket('tab-bad', 'bad-target')
    bad_packet._raw_request = None
    bad_packet._raw_response = None
    bad_packet._raw_body = None
    
    normal_entry = normal_packet.to_har_entry()
    bad_entry = bad_packet.to_har_entry()
    
    assert normal_entry['request']['method'] == 'GET'
    assert '_error' in bad_entry or bad_entry['request']['method']
    
    print(f'正常包转换: method={normal_entry["request"]["method"]}')
    print(f'异常包转换: _error={bad_entry.get("_error")}, _errorType={bad_entry.get("_errorType")}')
    print('[PASS] 测试通过 - 单条异常被捕获，不中断整体处理')
    
    return normal_entry, bad_entry


def main():
    """运行所有测试"""
    print('\n' + '#' * 60)
    print('# DrissionPage Listener HAR 导出功能测试')
    print('# ' + '=' * 58)
    print('# 测试场景:')
    print('#   1. 正常请求数据包')
    print('#   2. 失败请求数据包')
    print('#   3. 超大body截断')
    print('#   4. 二进制body的Base64编码')
    print('#   5. HAR文件导出')
    print('#   6. 异常处理')
    print('#' * 60 + '\n')
    
    results = {}
    
    try:
        results['test1_normal'] = test_normal_packet_to_har()
    except Exception as e:
        print(f'[FAIL] 测试1失败: {e}')
        results['test1_normal'] = None
    
    try:
        results['test2_failed'] = test_failed_packet_to_har()
    except Exception as e:
        print(f'[FAIL] 测试2失败: {e}')
        results['test2_failed'] = None
    
    try:
        results['test3_large_body'] = test_large_body_truncation()
    except Exception as e:
        print(f'[FAIL] 测试3失败: {e}')
        results['test3_large_body'] = None
    
    try:
        results['test4_binary'] = test_binary_body_encoding()
    except Exception as e:
        print(f'[FAIL] 测试4失败: {e}')
        results['test4_binary'] = None
    
    try:
        results['test5_export'] = test_export_har_function()
    except Exception as e:
        print(f'[FAIL] 测试5失败: {e}')
        results['test5_export'] = None
    
    try:
        results['test6_error'] = test_error_handling()
    except Exception as e:
        print(f'[FAIL] 测试6失败: {e}')
        results['test6_error'] = None
    
    print('\n' + '#' * 60)
    print('# 测试结果汇总')
    print('#' * 60)
    
    all_passed = all(v is not None for v in results.values())
    
    print(f'\n总测试数: 6')
    print(f'通过数: {sum(1 for v in results.values() if v is not None)}')
    print(f'失败数: {sum(1 for v in results.values() if v is None)}')
    
    if all_passed:
        print('\n[PASS] 所有测试通过!')
    else:
        print('\n[FAIL] 部分测试失败!')
    
    return results


if __name__ == '__main__':
    main()
