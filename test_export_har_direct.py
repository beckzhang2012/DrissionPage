# -*- coding:utf-8 -*-
"""
直接测试 Listener.export_har 方法
测试场景：
1. 正常包导出（有 log.entries）
2. 失败包导出（状态/错误字段正确）
3. 超限 body 截断（_truncated 生效）
4. clear_exported=True/False 行为正确
"""
import json
import tempfile
import os
from queue import Queue
from base64 import b64encode
from DrissionPage._units.listener import DataPacket, Listener
from DrissionPage.version import __version__ as DP_VERSION


class MockOwner:
    """模拟 Listener 需要的 owner 对象"""
    class MockBrowser:
        _ws_address = 'ws://localhost:9222'
    
    browser = MockBrowser()
    _target_id = 'target-123'
    tab_id = 'tab-123'


def create_mock_listener():
    """创建一个模拟的 Listener 实例"""
    owner = MockOwner()
    listener = Listener(owner)
    listener._caught = Queue()
    return listener


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
        },
        'mimeType': 'application/json',
        'timing': {
            'requestTime': 1234567890.0,
            'dnsStart': 0,
            'dnsEnd': 50,
            'connectStart': 50,
            'connectEnd': 100,
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


def create_failed_packet_with_response():
    """创建一个有响应状态码的失败数据包（如500错误）"""
    packet = DataPacket('tab-12345', 'test-failed-500')
    packet._raw_request = {
        'requestId': '67890',
        'loaderId': 'loader-456',
        'documentURL': 'https://example.com/page',
        'frameId': 'frame-123',
        'request': {
            'url': 'https://api.example.com/server-error',
            'method': 'POST',
            'headers': {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
        },
        'timestamp': 1234567891.0,
        'wallTime': 1713600001.0,
        'initiator': {'type': 'script'},
        'type': 'XHR'
    }
    packet._raw_response = {
        'url': 'https://api.example.com/server-error',
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
        'errorText': 'net::ERR_HTTP_RESPONSE_CODE_FAILURE',
        'canceled': False,
        'blockedReason': None
    }
    packet._resource_type = 'XHR'
    packet.is_failed = True
    return packet


def create_failed_packet_no_response():
    """创建一个完全没有响应的失败数据包（如网络错误）"""
    packet = DataPacket('tab-12345', 'test-failed-network')
    packet._raw_request = {
        'requestId': '99999',
        'loaderId': 'loader-999',
        'documentURL': 'https://example.com/page',
        'frameId': 'frame-123',
        'request': {
            'url': 'https://api.example.com/network-error',
            'method': 'GET',
            'headers': {
                'Accept': 'application/json',
            },
        },
        'timestamp': 1234567893.0,
        'wallTime': 1713600002.0,
        'initiator': {'type': 'script'},
        'type': 'XHR'
    }
    packet._raw_response = None
    packet._raw_body = None
    packet._base64_body = False
    packet._raw_fail_info = {
        'requestId': '99999',
        'timestamp': 1234567894.0,
        'type': 'XHR',
        'errorText': 'net::ERR_CONNECTION_REFUSED',
        'canceled': False,
        'blockedReason': 'connection_failed'
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


def test_normal_export():
    """测试1: 正常包导出（有 log.entries）"""
    print('=' * 60)
    print('测试1: 正常包导出')
    print('=' * 60)
    
    listener = create_mock_listener()
    packet = create_normal_packet()
    listener._caught.put(packet)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.har', delete=False, encoding='utf-8') as f:
        temp_path = f.name
    
    try:
        har = listener.export_har(temp_path, include_body=True)
        
        print(f'导出文件路径: {temp_path}')
        print(f'返回的 entries 数量: {len(har["log"]["entries"])}')
        
        with open(temp_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
            loaded_har = json.loads(file_content)
        
        print(f'文件中 entries 数量: {len(loaded_har["log"]["entries"])}')
        print(f'creator.name: {loaded_har["log"]["creator"]["name"]}')
        print(f'creator.version: {loaded_har["log"]["creator"]["version"]}')
        
        assert len(loaded_har['log']['entries']) == 1
        assert loaded_har['log']['creator']['name'] == 'DrissionPage'
        assert loaded_har['log']['creator']['version'] == DP_VERSION
        
        entry = loaded_har['log']['entries'][0]
        print(f'示例字段 - 请求方法: {entry["request"]["method"]}')
        print(f'示例字段 - 请求URL: {entry["request"]["url"]}')
        print(f'示例字段 - 响应状态: {entry["response"]["status"]}')
        print(f'示例字段 - 响应状态文本: {entry["response"]["statusText"]}')
        print(f'示例字段 - 响应类型: {entry["response"]["content"]["mimeType"]}')
        
        assert entry['request']['method'] == 'GET'
        assert entry['request']['url'] == 'https://api.example.com/data?key=value'
        assert entry['response']['status'] == 200
        assert entry['response']['statusText'] == 'OK'
        assert not entry.get('_failed', False)
        
        print('[PASS] 测试通过')
        return temp_path, loaded_har
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_failed_export():
    """测试2: 失败包导出（状态/错误字段正确）"""
    print('\n' + '=' * 60)
    print('测试2: 失败包导出')
    print('=' * 60)
    
    listener = create_mock_listener()
    packet_with_response = create_failed_packet_with_response()
    packet_no_response = create_failed_packet_no_response()
    listener._caught.put(packet_with_response)
    listener._caught.put(packet_no_response)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.har', delete=False, encoding='utf-8') as f:
        temp_path = f.name
    
    try:
        har = listener.export_har(temp_path, include_body=True)
        
        print(f'导出文件路径: {temp_path}')
        print(f'entries 数量: {len(har["log"]["entries"])}')
        
        with open(temp_path, 'r', encoding='utf-8') as f:
            loaded_har = json.loads(f.read())
        
        assert len(loaded_har['log']['entries']) == 2
        
        entry_with_response = loaded_har['log']['entries'][0]
        entry_no_response = loaded_har['log']['entries'][1]
        
        print('\n--- 有响应状态码的失败包（如500错误）---')
        print(f'URL: {entry_with_response["request"]["url"]}')
        print(f'_failed 标记: {entry_with_response.get("_failed")}')
        print(f'_errorType: {entry_with_response.get("_errorType")}')
        print(f'响应状态码: {entry_with_response["response"]["status"]}')
        print(f'响应状态文本: {entry_with_response["response"]["statusText"]}')
        
        assert entry_with_response.get('_failed') == True
        assert entry_with_response['response']['status'] == 500
        assert entry_with_response['response']['statusText'] == 'Internal Server Error'
        
        print('\n--- 完全没有响应的失败包（如网络错误）---')
        print(f'URL: {entry_no_response["request"]["url"]}')
        print(f'_failed 标记: {entry_no_response.get("_failed")}')
        print(f'_errorType: {entry_no_response.get("_errorType")}')
        print(f'响应状态码: {entry_no_response["response"]["status"]}')
        print(f'响应状态文本: {entry_no_response["response"]["statusText"]}')
        
        assert entry_no_response.get('_failed') == True
        assert entry_no_response['response']['status'] == 0
        assert 'ERR_CONNECTION_REFUSED' in entry_no_response['response']['statusText']
        
        print('\n[PASS] 测试通过')
        return temp_path, loaded_har
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_large_body_truncation():
    """测试3: 超限 body 截断（_truncated 生效）"""
    print('\n' + '=' * 60)
    print('测试3: 超限 body 截断')
    print('=' * 60)
    
    listener = create_mock_listener()
    packet = create_large_body_packet()
    listener._caught.put(packet)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.har', delete=False, encoding='utf-8') as f:
        temp_path = f.name
    
    try:
        max_body_kb = 1
        har = listener.export_har(temp_path, include_body=True, max_body_kb=max_body_kb)
        
        print(f'导出文件路径: {temp_path}')
        print(f'entries 数量: {len(har["log"]["entries"])}')
        
        with open(temp_path, 'r', encoding='utf-8') as f:
            loaded_har = json.loads(f.read())
        
        entry = loaded_har['log']['entries'][0]
        content = entry['response']['content']
        
        max_bytes = max_body_kb * 1024
        body_text = content.get('text', '')
        actual_size = len(body_text)
        
        print(f'原始body大小: {len(packet._raw_body)} 字节')
        print(f'限制大小: {max_bytes} 字节 (1KB)')
        print(f'实际保存大小: {actual_size} 字节')
        print(f'截断标记 _truncated: {content.get("_truncated")}')
        
        assert actual_size <= max_bytes + 20
        assert content.get('_truncated') == True
        assert '[truncated]' in body_text
        
        print('\n[PASS] 测试通过')
        return temp_path, loaded_har
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_clear_exported_behavior():
    """测试4: clear_exported=True/False 行为正确"""
    print('\n' + '=' * 60)
    print('测试4: clear_exported 行为')
    print('=' * 60)
    
    listener = create_mock_listener()
    packet1 = create_normal_packet()
    packet2 = create_large_body_packet()
    listener._caught.put(packet1)
    listener._caught.put(packet2)
    
    initial_size = listener._caught.qsize()
    print(f'初始队列大小: {initial_size}')
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.har', delete=False, encoding='utf-8') as f:
        temp_path1 = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.har', delete=False, encoding='utf-8') as f:
        temp_path2 = f.name
    
    try:
        print('\n--- 第一次导出 (clear_exported=False) ---')
        har1 = listener.export_har(temp_path1, include_body=False, clear_exported=False)
        size_after_first = listener._caught.qsize()
        print(f'entries 数量: {len(har1["log"]["entries"])}')
        print(f'导出后队列大小: {size_after_first}')
        
        assert len(har1['log']['entries']) == 2
        assert size_after_first == 2
        
        print('\n--- 第二次导出 (clear_exported=False) ---')
        har2 = listener.export_har(temp_path2, include_body=False, clear_exported=False)
        size_after_second = listener._caught.qsize()
        print(f'entries 数量: {len(har2["log"]["entries"])}')
        print(f'导出后队列大小: {size_after_second}')
        
        assert len(har2['log']['entries']) == 2
        assert size_after_second == 2
        
        print('\n--- 第三次导出 (clear_exported=True) ---')
        har3 = listener.export_har(temp_path1, include_body=False, clear_exported=True)
        size_after_third = listener._caught.qsize()
        print(f'entries 数量: {len(har3["log"]["entries"])}')
        print(f'导出后队列大小: {size_after_third}')
        
        assert len(har3['log']['entries']) == 2
        assert size_after_third == 0
        
        print('\n--- 第四次导出 (队列为空) ---')
        har4 = listener.export_har(temp_path2, include_body=False, clear_exported=False)
        size_after_fourth = listener._caught.qsize()
        print(f'entries 数量: {len(har4["log"]["entries"])}')
        print(f'导出后队列大小: {size_after_fourth}')
        
        assert len(har4['log']['entries']) == 0
        assert size_after_fourth == 0
        
        print('\n[PASS] 测试通过')
        return True
    finally:
        if os.path.exists(temp_path1):
            os.unlink(temp_path1)
        if os.path.exists(temp_path2):
            os.unlink(temp_path2)


def test_file_write_verification():
    """测试5: 验证 JSON 真正写入磁盘"""
    print('\n' + '=' * 60)
    print('测试5: JSON 文件写入验证')
    print('=' * 60)
    
    listener = create_mock_listener()
    packet = create_normal_packet()
    listener._caught.put(packet)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.har', delete=False, encoding='utf-8') as f:
        temp_path = f.name
    
    try:
        har = listener.export_har(temp_path, include_body=True)
        
        print(f'导出文件路径: {temp_path}')
        
        file_size = os.path.getsize(temp_path)
        print(f'文件大小: {file_size} 字节')
        
        with open(temp_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        print(f'文件内容预览 (前200字符):')
        print(file_content[:200])
        
        loaded_har = json.loads(file_content)
        
        assert 'log' in loaded_har
        assert 'entries' in loaded_har['log']
        assert len(loaded_har['log']['entries']) == 1
        
        assert loaded_har['log']['entries'][0]['request']['url'] == har['log']['entries'][0]['request']['url']
        
        assert file_size > 0
        
        print('\n[PASS] 测试通过')
        return temp_path, loaded_har
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def main():
    """运行所有测试"""
    print('\n' + '#' * 60)
    print('# 直接测试 Listener.export_har 方法')
    print('# ' + '=' * 58)
    print('# 测试场景:')
    print('#   1. 正常包导出（有 log.entries）')
    print('#   2. 失败包导出（状态/错误字段正确）')
    print('#   3. 超限 body 截断（_truncated 生效）')
    print('#   4. clear_exported=True/False 行为正确')
    print('#   5. JSON 文件写入验证')
    print('#' * 60 + '\n')
    
    results = {}
    
    try:
        results['test1_normal'] = test_normal_export()
    except Exception as e:
        print(f'[FAIL] 测试1失败: {e}')
        import traceback
        traceback.print_exc()
        results['test1_normal'] = None
    
    try:
        results['test2_failed'] = test_failed_export()
    except Exception as e:
        print(f'[FAIL] 测试2失败: {e}')
        import traceback
        traceback.print_exc()
        results['test2_failed'] = None
    
    try:
        results['test3_truncation'] = test_large_body_truncation()
    except Exception as e:
        print(f'[FAIL] 测试3失败: {e}')
        import traceback
        traceback.print_exc()
        results['test3_truncation'] = None
    
    try:
        results['test4_clear_exported'] = test_clear_exported_behavior()
    except Exception as e:
        print(f'[FAIL] 测试4失败: {e}')
        import traceback
        traceback.print_exc()
        results['test4_clear_exported'] = None
    
    try:
        results['test5_file_write'] = test_file_write_verification()
    except Exception as e:
        print(f'[FAIL] 测试5失败: {e}')
        import traceback
        traceback.print_exc()
        results['test5_file_write'] = None
    
    print('\n' + '#' * 60)
    print('# 测试结果汇总')
    print('#' * 60)
    
    all_passed = all(v is not None for v in results.values())
    
    print(f'\n总测试数: 5')
    print(f'通过数: {sum(1 for v in results.values() if v is not None)}')
    print(f'失败数: {sum(1 for v in results.values() if v is None)}')
    
    if all_passed:
        print('\n[PASS] 所有测试通过!')
    else:
        print('\n[FAIL] 部分测试失败!')
    
    return results


if __name__ == '__main__':
    main()
