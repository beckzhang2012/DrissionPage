# -*- coding:utf-8 -*-
"""
DownloadKit 断点续传与完整性校验修复测试
测试场景：
1. 正常续传测试
2. 服务端不支持Range测试
3. 校验失败测试
4. 并发同名下载冲突测试
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
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs

import sys
sys.path.insert(0, str(Path(__file__).parent))

from DrissionPage._libs.DownloadKit import DownloadKit


TEST_DATA = b"Hello, this is a test file for DownloadKit testing. " * 100
TEST_DATA_SHA256 = hashlib.sha256(TEST_DATA).hexdigest()
TEST_DATA_MD5 = hashlib.md5(TEST_DATA).hexdigest()
CORRUPT_DATA_SHA256 = hashlib.sha256(TEST_DATA + b"corrupted").hexdigest()


class MockHTTPRequestHandler(BaseHTTPRequestHandler):
    """模拟HTTP服务器，支持各种测试场景"""
    
    support_range = True
    delay_seconds = 0
    return_corrupt_data = False
    concurrent_access_count = {}
    concurrent_lock = threading.Lock()
    
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        
        scenario = query.get('scenario', ['default'])[0]
        
        if scenario == 'concurrent':
            with MockHTTPRequestHandler.concurrent_lock:
                MockHTTPRequestHandler.concurrent_access_count[scenario] = \
                    MockHTTPRequestHandler.concurrent_access_count.get(scenario, 0) + 1
            
            time.sleep(0.1)
            
            with MockHTTPRequestHandler.concurrent_lock:
                if MockHTTPRequestHandler.concurrent_access_count[scenario] > 1:
                    pass
        
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
            
            self.send_response(206)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(len(chunk)))
            self.send_header('Content-Range', f'bytes {start}-{end}/{len(data)}')
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
    
    def __init__(self, port: int = 8765):
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


class TestResult:
    """测试结果封装"""
    
    def __init__(self, name: str, passed: bool, message: str, 
                 state_transitions: list = None,
                 temp_files: list = None,
                 final_file: str = None,
                 exit_code: int = 0):
        self.name = name
        self.passed = passed
        self.message = message
        self.state_transitions = state_transitions or []
        self.temp_files = temp_files or []
        self.final_file = final_file
        self.exit_code = exit_code
    
    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.name}: {self.message}"


class DownloadKitPatchTest:
    """DownloadKit 修复测试套件"""
    
    def __init__(self):
        self.server = TestServer(8765)
        self.temp_dir = tempfile.mkdtemp(prefix='downloadkit_test_')
        self.results = []
    
    def setup(self):
        self.server.start()
        MockHTTPRequestHandler.support_range = True
        MockHTTPRequestHandler.delay_seconds = 0
        MockHTTPRequestHandler.return_corrupt_data = False
        MockHTTPRequestHandler.concurrent_access_count = {}
    
    def teardown(self):
        self.server.stop()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def get_base_url(self) -> str:
        return f"http://localhost:{self.server.port}"
    
    def _record_result(self, result: TestResult):
        self.results.append(result)
        print(result)
    
    def test_normal_resume(self) -> TestResult:
        """测试1: 正常断点续传
        验证：
        1. 使用 file_exists='add' 模式
        2. 部分下载后继续下载
        3. 状态流转正确
        4. 临时文件处理正确
        """
        print("\n" + "="*60)
        print("测试1: 正常断点续传")
        print("="*60)
        
        test_dir = Path(self.temp_dir) / "test_resume"
        test_dir.mkdir(exist_ok=True)
        
        dk = DownloadKit(save_path=str(test_dir), roads=1)
        dk.split = False
        dk.block_size = 1024
        
        part_size = len(TEST_DATA) // 2
        partial_data = TEST_DATA[:part_size]
        
        final_file = test_dir / "test_resume.bin"
        part_file = test_dir / "test_resume.bin.part"
        
        with open(part_file, 'wb') as f:
            f.write(partial_data)
        
        print(f"已创建部分文件: {part_file}, 大小: {len(partial_data)}")
        
        url = f"{self.get_base_url()}/test?scenario=default"
        mission = dk.add(
            url,
            rename="test_resume.bin",
            file_exists='add',
            split=False
        )
        
        result, info = mission.wait(show=False)
        
        states = [t['state'] for t in mission.state_transitions]
        print(f"状态流转: {states}")
        print(f"临时文件存在: {part_file.exists()}")
        print(f"最终文件存在: {final_file.exists()}")
        
        if final_file.exists():
            print(f"最终文件大小: {final_file.stat().st_size}")
            with open(final_file, 'rb') as f:
                content = f.read()
            print(f"内容校验: {'通过' if content == TEST_DATA else '失败'}")
        
        passed = (
            result == 'success' and
            final_file.exists() and
            not part_file.exists() and
            states[-1] == 'done'
        )
        
        if final_file.exists():
            with open(final_file, 'rb') as f:
                content = f.read()
            passed = passed and (content == TEST_DATA)
        
        return TestResult(
            name="正常断点续传",
            passed=passed,
            message=f"结果: {result}, 状态: {states}",
            state_transitions=mission.state_transitions,
            temp_files=[str(part_file)] if part_file.exists() else [],
            final_file=str(final_file) if final_file.exists() else None,
            exit_code=0 if passed else 1
        )
    
    def test_server_no_range(self) -> TestResult:
        """测试2: 服务端不支持Range
        验证：
        1. 服务端返回 Accept-Ranges: none
        2. 客户端正确处理，回退到完整下载
        3. 状态流转正确
        """
        print("\n" + "="*60)
        print("测试2: 服务端不支持Range")
        print("="*60)
        
        test_dir = Path(self.temp_dir) / "test_no_range"
        test_dir.mkdir(exist_ok=True)
        
        MockHTTPRequestHandler.support_range = False
        
        dk = DownloadKit(save_path=str(test_dir), roads=1)
        dk.split = True
        dk.block_size = 50
        
        url = f"{self.get_base_url()}/test?scenario=no_range"
        mission = dk.add(
            url,
            rename="test_no_range.bin",
            file_exists='overwrite',
            split=True
        )
        
        result, info = mission.wait(show=False)
        
        states = [t['state'] for t in mission.state_transitions]
        print(f"状态流转: {states}")
        print(f"结果: {result}")
        print(f"信息: {info}")
        
        for t in mission.state_transitions:
            if 'no_range' in t.get('info', '').lower() or 'range' in t.get('info', '').lower():
                print(f"  - 检测到Range相关状态: {t}")
        
        final_file = test_dir / "test_no_range.bin"
        
        passed = (
            result == 'success' and
            final_file.exists() and
            states[-1] == 'done'
        )
        
        if final_file.exists():
            with open(final_file, 'rb') as f:
                content = f.read()
            passed = passed and (content == TEST_DATA)
        
        return TestResult(
            name="服务端不支持Range",
            passed=passed,
            message=f"结果: {result}, 状态: {states}",
            state_transitions=mission.state_transitions,
            final_file=str(final_file) if final_file.exists() else None,
            exit_code=0 if passed else 1
        )
    
    def test_integrity_check_failed(self) -> TestResult:
        """测试3: 完整性校验失败
        验证：
        1. 指定 sha256 校验
        2. 返回的数据与期望hash不匹配
        3. 校验失败后文件被清理
        4. 状态标记为 'integrity_failed'
        """
        print("\n" + "="*60)
        print("测试3: 完整性校验失败")
        print("="*60)
        
        test_dir = Path(self.temp_dir) / "test_integrity"
        test_dir.mkdir(exist_ok=True)
        
        MockHTTPRequestHandler.return_corrupt_data = True
        MockHTTPRequestHandler.support_range = True
        
        dk = DownloadKit(save_path=str(test_dir), roads=1)
        dk.split = False
        
        url = f"{self.get_base_url()}/test?scenario=integrity"
        mission = dk.add(
            url,
            rename="test_integrity.bin",
            file_exists='overwrite',
            integrity_algorithm='sha256',
            expected_hash=TEST_DATA_SHA256
        )
        
        result, info = mission.wait(show=False)
        
        states = [t['state'] for t in mission.state_transitions]
        print(f"状态流转: {states}")
        print(f"结果: {result}")
        print(f"信息: {info}")
        
        final_file = test_dir / "test_integrity.bin"
        part_file = test_dir / "test_integrity.bin.part"
        
        print(f"最终文件存在: {final_file.exists()}")
        print(f"临时文件存在: {part_file.exists()}")
        
        passed = (
            result == 'integrity_failed' and
            not final_file.exists() and
            not part_file.exists()
        )
        
        if 'integrity_failed' in states:
            print("  - 检测到 integrity_failed 状态")
        
        return TestResult(
            name="完整性校验失败",
            passed=passed,
            message=f"结果: {result}, 状态: {states}",
            state_transitions=mission.state_transitions,
            temp_files=[str(part_file)] if part_file.exists() else [],
            final_file=str(final_file) if final_file.exists() else None,
            exit_code=0 if passed else 1
        )
    
    def test_integrity_check_success(self) -> TestResult:
        """测试3b: 完整性校验成功（补充测试）
        验证：
        1. 指定 sha256 校验
        2. 返回的数据与期望hash匹配
        3. 校验成功后状态为 'success'
        """
        print("\n" + "="*60)
        print("测试3b: 完整性校验成功")
        print("="*60)
        
        test_dir = Path(self.temp_dir) / "test_integrity_success"
        test_dir.mkdir(exist_ok=True)
        
        MockHTTPRequestHandler.return_corrupt_data = False
        MockHTTPRequestHandler.support_range = True
        
        dk = DownloadKit(save_path=str(test_dir), roads=1)
        dk.split = False
        
        url = f"{self.get_base_url()}/test?scenario=integrity_ok"
        mission = dk.add(
            url,
            rename="test_integrity_ok.bin",
            file_exists='overwrite',
            integrity_algorithm='sha256',
            expected_hash=TEST_DATA_SHA256
        )
        
        result, info = mission.wait(show=False)
        
        states = [t['state'] for t in mission.state_transitions]
        print(f"状态流转: {states}")
        print(f"结果: {result}")
        
        final_file = test_dir / "test_integrity_ok.bin"
        
        passed = (
            result == 'success' and
            final_file.exists()
        )
        
        return TestResult(
            name="完整性校验成功",
            passed=passed,
            message=f"结果: {result}, 状态: {states}",
            state_transitions=mission.state_transitions,
            final_file=str(final_file) if final_file.exists() else None,
            exit_code=0 if passed else 1
        )
    
    def test_concurrent_download_conflict(self) -> TestResult:
        """测试4: 并发同名下载冲突
        验证：
        1. 多个线程同时下载同名文件
        2. 使用 file_exists='rename' 模式
        3. 每个任务都获得唯一的文件名
        4. 没有状态错乱
        """
        print("\n" + "="*60)
        print("测试4: 并发同名下载冲突")
        print("="*60)
        
        test_dir = Path(self.temp_dir) / "test_concurrent"
        test_dir.mkdir(exist_ok=True)
        
        MockHTTPRequestHandler.support_range = True
        MockHTTPRequestHandler.delay_seconds = 0.01
        MockHTTPRequestHandler.concurrent_access_count = {}
        
        dk = DownloadKit(save_path=str(test_dir), roads=5)
        dk.split = False
        dk.file_exists = 'rename'
        
        missions = []
        threads = []
        
        def download_task(index):
            url = f"{self.get_base_url()}/test?scenario=concurrent&idx={index}"
            mission = dk.add(
                url,
                rename="concurrent_test.bin",
                file_exists='rename',
                split=False
            )
            missions.append((index, mission))
        
        for i in range(5):
            t = Thread(target=download_task, args=(i,), daemon=True)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join(timeout=10)
        
        time.sleep(0.5)
        
        results = []
        all_success = True
        file_names = set()
        
        for idx, mission in missions:
            result, info = mission.wait(show=False, timeout=10)
            states = [t['state'] for t in mission.state_transitions]
            results.append((idx, result, states))
            
            if result != 'success':
                all_success = False
            
            if mission.file_name:
                file_names.add(mission.file_name)
            
            print(f"任务 {idx}: 结果={result}, 状态={states}, 文件名={mission.file_name}")
        
        files_in_dir = list(test_dir.glob("*"))
        print(f"\n目录中的文件: {[f.name for f in files_in_dir]}")
        print(f"唯一文件名数量: {len(file_names)}")
        
        passed = (
            all_success and
            len(file_names) == 5
        )
        
        return TestResult(
            name="并发同名下载冲突",
            passed=passed,
            message=f"成功数: {len([r for r in results if r[1] == 'success'])}/5, 唯一文件数: {len(file_names)}",
            state_transitions=[r[2] for r in results],
            temp_files=[],
            final_file=str(test_dir),
            exit_code=0 if passed else 1
        )
    
    def test_md5_integrity(self) -> TestResult:
        """测试5: MD5完整性校验
        验证：
        1. MD5 校验功能正常
        """
        print("\n" + "="*60)
        print("测试5: MD5完整性校验")
        print("="*60)
        
        test_dir = Path(self.temp_dir) / "test_md5"
        test_dir.mkdir(exist_ok=True)
        
        MockHTTPRequestHandler.return_corrupt_data = False
        
        dk = DownloadKit(save_path=str(test_dir), roads=1)
        dk.split = False
        
        mission = dk.add(
            f"{self.get_base_url()}/test",
            rename="test_md5.bin",
            integrity_algorithm='md5',
            expected_hash=TEST_DATA_MD5
        )
        
        result, info = mission.wait(show=False)
        
        states = [t['state'] for t in mission.state_transitions]
        print(f"状态流转: {states}")
        print(f"结果: {result}")
        
        passed = result == 'success'
        
        return TestResult(
            name="MD5完整性校验",
            passed=passed,
            message=f"结果: {result}, 状态: {states}",
            state_transitions=mission.state_transitions,
            exit_code=0 if passed else 1
        )
    
    def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "#"*60)
        print("# DownloadKit 断点续传与完整性校验修复测试")
        print("#"*60)
        
        self.setup()
        
        try:
            self._record_result(self.test_normal_resume())
            self._record_result(self.test_server_no_range())
            self._record_result(self.test_integrity_check_success())
            self._record_result(self.test_integrity_check_failed())
            self._record_result(self.test_concurrent_download_conflict())
            self._record_result(self.test_md5_integrity())
        
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
                if isinstance(result.state_transitions[0], list):
                    for i, states in enumerate(result.state_transitions):
                        print(f"  任务{i}状态流转: {states}")
                else:
                    print(f"  状态流转: {[t['state'] for t in result.state_transitions]}")
            
            if result.temp_files:
                print(f"  残留临时文件: {result.temp_files}")
            
            if result.final_file:
                print(f"  最终文件: {result.final_file}")
            
            print(f"  退出码: {result.exit_code}")
        
        total_tests = len(self.results)
        passed_tests = len([r for r in self.results if r.passed])
        
        print("\n" + "="*60)
        print(f"总计: {passed_tests}/{total_tests} 测试通过")
        print("="*60)


if __name__ == '__main__':
    test = DownloadKitPatchTest()
    exit_code = test.run_all_tests()
    sys.exit(exit_code)
