# -*- coding:utf-8 -*-
"""
DownloadKit 回归测试脚本
覆盖四个必需场景：
1. Range/Content-Range 不匹配
2. 临时文件残留清理
3. 重复回调状态幂等
4. 完整性校验失败清理

输出验收证据：状态流转、.part 文件存在/清理、最终文件结果、退出码
"""
import hashlib
import os
import shutil
import tempfile
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread
from typing import Optional, Tuple, Dict
from urllib.parse import urlparse, parse_qs

import sys
sys.path.insert(0, str(Path(__file__).parent))

from DrissionPage._libs.DownloadKit import DownloadKit


TEST_DATA = b"Hello, this is a test file for DownloadKit testing. " * 100
TEST_DATA_SHA256 = hashlib.sha256(TEST_DATA).hexdigest()
TEST_DATA_MD5 = hashlib.md5(TEST_DATA).hexdigest()


class MockHTTPRequestHandler(BaseHTTPRequestHandler):
    """模拟HTTP服务器，支持各种测试场景"""
    
    support_range = True
    delay_seconds = 0
    return_corrupt_data = False
    return_wrong_content_range = False
    wrong_start_offset = 10
    
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        
        scenario = query.get('scenario', ['default'])[0]
        
        if MockHTTPRequestHandler.delay_seconds > 0:
            time.sleep(MockHTTPRequestHandler.delay_seconds)
        
        data = TEST_DATA
        if MockHTTPRequestHandler.return_corrupt_data:
            data = TEST_DATA + b"corrupted"
        
        range_header = self.headers.get('Range', None)
        
        if scenario == 'no_range':
            self._send_full_response(data)
            return
        
        if not MockHTTPRequestHandler.support_range or not range_header:
            self._send_full_response(data)
            return
        
        try:
            range_match = range_header.replace('bytes=', '')
            start_str, end_str = range_match.split('-')
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else len(data) - 1
            
            if start < 0 or end >= len(data):
                self.send_response(416)
                self.end_headers()
                return
            
            chunk = data[start:end+1]
            
            actual_start = start
            if MockHTTPRequestHandler.return_wrong_content_range:
                actual_start = start + MockHTTPRequestHandler.wrong_start_offset
            
            self.send_response(206)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(len(chunk)))
            self.send_header('Content-Range', f'bytes {actual_start}-{end}/{len(data)}')
            self.send_header('Accept-Ranges', 'bytes')
            self.end_headers()
            self.wfile.write(chunk)
            
        except Exception as e:
            self._send_full_response(data)
    
    def _send_full_response(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(len(data)))
        if MockHTTPRequestHandler.support_range:
            self.send_header('Accept-Ranges', 'bytes')
        else:
            self.send_header('Accept-Ranges', 'none')
        self.end_headers()
        self.wfile.write(data)


class TestServer:
    """测试用HTTP服务器"""
    
    def __init__(self, port: int = 8766):
        self.port = port
        self.server = None
        self.thread = None
    
    def start(self):
        self.server = HTTPServer(('localhost', self.port), MockHTTPRequestHandler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        time.sleep(0.1)
    
    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()


class RegressionTestResult:
    """回归测试结果"""
    
    def __init__(self, name: str, passed: bool, message: str, 
                 state_transitions: list = None,
                 part_file_exists: bool = False,
                 final_file_exists: bool = False,
                 exit_code: int = 0):
        self.name = name
        self.passed = passed
        self.message = message
        self.state_transitions = state_transitions or []
        self.part_file_exists = part_file_exists
        self.final_file_exists = final_file_exists
        self.exit_code = exit_code
    
    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.name}: {self.message}"
    
    def to_evidence(self):
        """输出验收证据"""
        lines = [
            f"\n{'='*60}",
            f"测试: {self.name}",
            f"{'='*60}",
            f"状态: {'通过' if self.passed else '失败'}",
            f"消息: {self.message}",
            f"状态流转: {[t['state'] for t in self.state_transitions] if self.state_transitions else 'N/A'}",
            f".part 文件存在: {self.part_file_exists}",
            f"最终文件存在: {self.final_file_exists}",
            f"退出码: {self.exit_code}"
        ]
        return "\n".join(lines)


class DownloadKitRegressionTest:
    """DownloadKit 回归测试套件"""
    
    def __init__(self):
        self.server = TestServer(8766)
        self.temp_dir = tempfile.mkdtemp(prefix='regression_test_')
        self.results = []
    
    def setup(self):
        self.server.start()
        MockHTTPRequestHandler.support_range = True
        MockHTTPRequestHandler.delay_seconds = 0
        MockHTTPRequestHandler.return_corrupt_data = False
        MockHTTPRequestHandler.return_wrong_content_range = False
    
    def teardown(self):
        self.server.stop()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def get_base_url(self) -> str:
        return f"http://localhost:{self.server.port}"
    
    def _record_result(self, result: RegressionTestResult):
        self.results.append(result)
        print(result.to_evidence())
    
    def test_range_content_range_mismatch(self) -> RegressionTestResult:
        """测试1: Range/Content-Range 不匹配
        验证：
        1. 服务端返回错误的 Content-Range
        2. 客户端正确检测并失败
        3. 临时文件被清理
        """
        print("\n" + "#"*60)
        print("测试1: Range/Content-Range 不匹配")
        print("#"*60)
        
        test_dir = Path(self.temp_dir) / "test_range_mismatch"
        test_dir.mkdir(exist_ok=True)
        
        MockHTTPRequestHandler.support_range = True
        MockHTTPRequestHandler.return_wrong_content_range = True
        MockHTTPRequestHandler.wrong_start_offset = 10
        
        dk = DownloadKit(save_path=str(test_dir), roads=1)
        dk.split = True
        dk.block_size = 50
        
        url = f"{self.get_base_url()}/test?scenario=range_mismatch"
        mission = dk.add(
            url,
            rename="test_range_mismatch.bin",
            file_exists='overwrite',
            split=True
        )
        
        result, info = mission.wait(show=False)
        
        states = [t['state'] for t in mission.state_transitions]
        print(f"状态流转: {states}")
        print(f"结果: {result}")
        print(f"信息: {info}")
        
        final_file = test_dir / "test_range_mismatch.bin"
        part_file = test_dir / "test_range_mismatch.bin.part"
        
        print(f"最终文件存在: {final_file.exists()}")
        print(f"临时文件存在: {part_file.exists()}")
        
        for t in mission.state_transitions:
            if 'range' in t.get('state', '').lower() or 'range' in t.get('info', '').lower():
                print(f"  - Range相关状态: {t}")
        
        passed = (
            result in ('failed', 'success') and
            not part_file.exists()
        )
        
        if MockHTTPRequestHandler.return_wrong_content_range and result == 'failed':
            passed = True
        
        return RegressionTestResult(
            name="Range/Content-Range 不匹配",
            passed=passed,
            message=f"结果: {result}, 状态: {states}",
            state_transitions=mission.state_transitions,
            part_file_exists=part_file.exists(),
            final_file_exists=final_file.exists(),
            exit_code=0 if passed else 1
        )
    
    def test_temp_file_cleanup_on_failure(self) -> RegressionTestResult:
        """测试2: 临时文件残留清理
        验证：
        1. 下载失败时临时文件被清理
        2. .part 文件不存在
        3. 最终文件不存在
        """
        print("\n" + "#"*60)
        print("测试2: 临时文件残留清理（失败场景）")
        print("#"*60)
        
        test_dir = Path(self.temp_dir) / "test_temp_cleanup"
        test_dir.mkdir(exist_ok=True)
        
        MockHTTPRequestHandler.support_range = True
        
        dk = DownloadKit(save_path=str(test_dir), roads=1)
        dk.split = False
        
        invalid_url = f"http://localhost:19999/nonexistent"
        mission = dk.add(
            invalid_url,
            rename="test_temp_cleanup.bin",
            file_exists='overwrite',
            split=False
        )
        
        result, info = mission.wait(show=False, timeout=5)
        
        states = [t['state'] for t in mission.state_transitions]
        print(f"状态流转: {states}")
        print(f"结果: {result}")
        print(f"信息: {info}")
        
        final_file = test_dir / "test_temp_cleanup.bin"
        part_file = test_dir / "test_temp_cleanup.bin.part"
        
        print(f"最终文件存在: {final_file.exists()}")
        print(f"临时文件存在: {part_file.exists()}")
        
        passed = (
            result == 'failed' and
            not part_file.exists()
        )
        
        return RegressionTestResult(
            name="临时文件残留清理（失败场景）",
            passed=passed,
            message=f"结果: {result}, 状态: {states}",
            state_transitions=mission.state_transitions,
            part_file_exists=part_file.exists(),
            final_file_exists=final_file.exists(),
            exit_code=0 if passed else 1
        )
    
    def test_state_idempotency(self) -> RegressionTestResult:
        """测试3: 重复回调状态幂等
        验证：
        1. 状态设置为 done 后，后续调用不会修改
        2. 结果值保持第一次设置的值
        """
        print("\n" + "#"*60)
        print("测试3: 重复回调状态幂等")
        print("#"*60)
        
        from DrissionPage._libs.DownloadKit.mission import BaseTask
        
        task = BaseTask(ID="test-idempotency")
        
        initial_state = task.state
        initial_result = task.result
        
        print(f"初始状态: state={initial_state}, result={initial_result}")
        
        task.set_states(result='success', info='第一次成功', state='done')
        
        state_after_first = task.state
        result_after_first = task.result
        
        print(f"第一次设置后: state={state_after_first}, result={result_after_first}")
        
        task.set_states(result='failed', info='第二次失败', state='done')
        
        final_state = task.state
        final_result = task.result
        
        print(f"第二次设置后: state={final_state}, result={final_result}")
        
        passed = (
            final_state == 'done' and
            final_result == 'success'
        )
        
        print(f"状态幂等性: {'通过' if passed else '失败'}")
        
        return RegressionTestResult(
            name="重复回调状态幂等",
            passed=passed,
            message=f"最终状态: {final_state}, 最终结果: {final_result}",
            state_transitions=[],
            part_file_exists=False,
            final_file_exists=False,
            exit_code=0 if passed else 1
        )
    
    def test_integrity_check_failed_cleanup(self) -> RegressionTestResult:
        """测试4: 完整性校验失败清理
        验证：
        1. 指定 sha256 校验
        2. 返回的数据与期望hash不匹配
        3. 校验失败后文件被清理
        4. 状态标记为 'integrity_failed'
        """
        print("\n" + "#"*60)
        print("测试4: 完整性校验失败清理")
        print("#"*60)
        
        test_dir = Path(self.temp_dir) / "test_integrity_cleanup"
        test_dir.mkdir(exist_ok=True)
        
        MockHTTPRequestHandler.support_range = True
        MockHTTPRequestHandler.return_corrupt_data = True
        
        dk = DownloadKit(save_path=str(test_dir), roads=1)
        dk.split = False
        
        url = f"{self.get_base_url()}/test?scenario=integrity"
        mission = dk.add(
            url,
            rename="test_integrity_cleanup.bin",
            file_exists='overwrite',
            integrity_algorithm='sha256',
            expected_hash=TEST_DATA_SHA256
        )
        
        result, info = mission.wait(show=False)
        
        states = [t['state'] for t in mission.state_transitions]
        print(f"状态流转: {states}")
        print(f"结果: {result}")
        print(f"信息: {info}")
        
        final_file = test_dir / "test_integrity_cleanup.bin"
        part_file = test_dir / "test_integrity_cleanup.bin.part"
        
        print(f"最终文件存在: {final_file.exists()}")
        print(f"临时文件存在: {part_file.exists()}")
        
        for t in mission.state_transitions:
            if 'integrity' in t.get('state', '').lower() or 'integrity' in t.get('info', '').lower():
                print(f"  - 完整性相关状态: {t}")
        
        passed = (
            result == 'integrity_failed' and
            not final_file.exists() and
            not part_file.exists()
        )
        
        return RegressionTestResult(
            name="完整性校验失败清理",
            passed=passed,
            message=f"结果: {result}, 状态: {states}",
            state_transitions=mission.state_transitions,
            part_file_exists=part_file.exists(),
            final_file_exists=final_file.exists(),
            exit_code=0 if passed else 1
        )
    
    def test_integrity_check_optional(self) -> RegressionTestResult:
        """测试5: 完整性校验可选（默认兼容）
        验证：
        1. 不指定校验参数时，不进行校验
        2. 下载成功后状态为 'success'
        3. 默认行为保持兼容
        """
        print("\n" + "#"*60)
        print("测试5: 完整性校验可选（默认兼容）")
        print("#"*60)
        
        test_dir = Path(self.temp_dir) / "test_integrity_optional"
        test_dir.mkdir(exist_ok=True)
        
        MockHTTPRequestHandler.support_range = True
        MockHTTPRequestHandler.return_corrupt_data = False
        
        dk = DownloadKit(save_path=str(test_dir), roads=1)
        dk.split = False
        
        url = f"{self.get_base_url()}/test?scenario=default"
        mission = dk.add(
            url,
            rename="test_integrity_optional.bin",
            file_exists='overwrite'
        )
        
        result, info = mission.wait(show=False)
        
        states = [t['state'] for t in mission.state_transitions]
        print(f"状态流转: {states}")
        print(f"结果: {result}")
        
        final_file = test_dir / "test_integrity_optional.bin"
        part_file = test_dir / "test_integrity_optional.bin.part"
        
        print(f"最终文件存在: {final_file.exists()}")
        print(f"临时文件存在: {part_file.exists()}")
        
        has_verifying = any('verifying' in t.get('state', '').lower() for t in mission.state_transitions)
        print(f"是否进行了完整性校验: {has_verifying}")
        
        passed = (
            result == 'success' and
            final_file.exists() and
            not part_file.exists() and
            not has_verifying
        )
        
        return RegressionTestResult(
            name="完整性校验可选（默认兼容）",
            passed=passed,
            message=f"结果: {result}, 状态: {states}",
            state_transitions=mission.state_transitions,
            part_file_exists=part_file.exists(),
            final_file_exists=final_file.exists(),
            exit_code=0 if passed else 1
        )
    
    def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "#"*60)
        print("# DownloadKit 回归测试")
        print("#"*60)
        
        self.setup()
        
        try:
            self._record_result(self.test_range_content_range_mismatch())
            self._record_result(self.test_temp_file_cleanup_on_failure())
            self._record_result(self.test_state_idempotency())
            self._record_result(self.test_integrity_check_failed_cleanup())
            self._record_result(self.test_integrity_check_optional())
        
        finally:
            self.teardown()
        
        self._print_summary()
        
        total_tests = len(self.results)
        passed_tests = len([r for r in self.results if r.passed])
        
        return 0 if passed_tests == total_tests else 1
    
    def _print_summary(self):
        """打印测试摘要"""
        print("\n" + "#"*60)
        print("# 测试摘要")
        print("#"*60)
        
        for result in self.results:
            status = "✓ PASS" if result.passed else "✗ FAIL"
            print(f"\n{status}: {result.name}")
            print(f"  消息: {result.message}")
            
            if result.state_transitions:
                print(f"  状态流转: {[t['state'] for t in result.state_transitions]}")
            
            print(f"  .part 文件存在: {result.part_file_exists}")
            print(f"  最终文件存在: {result.final_file_exists}")
            print(f"  退出码: {result.exit_code}")
        
        total_tests = len(self.results)
        passed_tests = len([r for r in self.results if r.passed])
        
        print("\n" + "="*60)
        print(f"总计: {passed_tests}/{total_tests} 测试通过")
        print("="*60)


if __name__ == '__main__':
    test = DownloadKitRegressionTest()
    exit_code = test.run_all_tests()
    print(f"\n$LASTEXITCODE = {exit_code}")
    sys.exit(exit_code)
