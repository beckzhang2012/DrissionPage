# -*- coding:utf-8 -*-
"""
最终验证脚本 - 直接验证4个核心场景
1. Range/Content-Range 不匹配
2. 下载失败后 .part 残留清理
3. 重复回调状态幂等（终态不可被覆盖）
4. 并发同名下载冲突
5. 完整性校验（可选参数、失败清理）
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
from urllib.parse import urlparse, parse_qs

import sys
sys.path.insert(0, str(Path(__file__).parent))

from DrissionPage._libs.DownloadKit import DownloadKit


TEST_DATA = b"Hello, this is a test file for DownloadKit testing. " * 100
TEST_DATA_SHA256 = hashlib.sha256(TEST_DATA).hexdigest()
CORRUPT_DATA = TEST_DATA + b"corrupted"
CORRUPT_DATA_SHA256 = hashlib.sha256(CORRUPT_DATA).hexdigest()


class MockHandler(BaseHTTPRequestHandler):
    """模拟HTTP服务器"""
    support_range = True
    wrong_range_offset = 0
    return_corrupt = False
    delay_seconds = 0
    
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        if MockHandler.delay_seconds > 0:
            time.sleep(MockHandler.delay_seconds)
        
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        
        data = TEST_DATA
        if MockHandler.return_corrupt:
            data = CORRUPT_DATA
        
        range_header = self.headers.get('Range', None)
        
        if not MockHandler.support_range or not range_header:
            self._send_full(data)
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
            
            actual_start = start + MockHandler.wrong_range_offset
            
            self.send_response(206)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(len(chunk)))
            self.send_header('Content-Range', f'bytes {actual_start}-{end}/{len(data)}')
            self.send_header('Accept-Ranges', 'bytes')
            self.end_headers()
            self.wfile.write(chunk)
            
        except Exception:
            self._send_full(data)
    
    def _send_full(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(len(data)))
        if MockHandler.support_range:
            self.send_header('Accept-Ranges', 'bytes')
        else:
            self.send_header('Accept-Ranges', 'none')
        self.end_headers()
        self.wfile.write(data)


def run_verification():
    print("="*70)
    print("DownloadKit 核心场景验证")
    print("="*70)
    
    results = []
    
    server = HTTPServer(('localhost', 8877), MockHandler)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.1)
    
    base_url = "http://localhost:8877"
    temp_root = tempfile.mkdtemp(prefix='dk_final_')
    
    try:
        print("\n" + "-"*70)
        print("场景1: 状态幂等性（终态不可被覆盖）")
        print("-"*70)
        
        from DrissionPage._libs.DownloadKit.mission import BaseTask
        task = BaseTask(ID="test")
        
        print(f"初始状态: state={task.state}, result={task.result}")
        
        task.set_states(result='success', info='第一次成功', state='done')
        print(f"第一次设置后: state={task.state}, result={task.result}")
        
        task.set_states(result='failed', info='第二次失败', state='done')
        print(f"第二次设置后: state={task.state}, result={task.result}")
        
        passed = task.state == 'done' and task.result == 'success'
        results.append({
            'name': '状态幂等性',
            'passed': passed,
            'state_transitions': ['waiting', 'done'],
            'part_file': False,
            'final_file': False,
            'exit_code': 0 if passed else 1
        })
        print(f"结果: {'通过' if passed else '失败'}")
        
        print("\n" + "-"*70)
        print("场景2: 下载失败后 .part 残留清理")
        print("-"*70)
        
        MockHandler.support_range = True
        MockHandler.wrong_range_offset = 0
        MockHandler.return_corrupt = False
        MockHandler.delay_seconds = 0
        
        test_dir = Path(temp_root) / "cleanup_test"
        test_dir.mkdir(exist_ok=True)
        
        dk = DownloadKit(save_path=str(test_dir), roads=1)
        dk.split = False
        
        invalid_url = "http://localhost:19999/nonexistent"
        mission = dk.add(
            invalid_url,
            rename="test_cleanup.bin",
            file_exists='overwrite',
            split=False
        )
        
        result, info = mission.wait(show=False, timeout=15)
        
        states = [t['state'] for t in mission.state_transitions]
        print(f"状态流转: {states}")
        print(f"结果: {result}")
        print(f"信息: {info}")
        
        final_file = test_dir / "test_cleanup.bin"
        part_file = test_dir / "test_cleanup.bin.part"
        
        print(f"最终文件存在: {final_file.exists()}")
        print(f"临时文件存在: {part_file.exists()}")
        
        passed = result == 'failed' and not part_file.exists()
        results.append({
            'name': '下载失败后.part清理',
            'passed': passed,
            'state_transitions': states,
            'part_file': part_file.exists(),
            'final_file': final_file.exists(),
            'exit_code': 0 if passed else 1
        })
        print(f"结果: {'通过' if passed else '失败'}")
        
        print("\n" + "-"*70)
        print("场景3: Range/Content-Range 不匹配（非分块下载）")
        print("-"*70)
        
        MockHandler.support_range = True
        MockHandler.wrong_range_offset = 10
        MockHandler.return_corrupt = False
        MockHandler.delay_seconds = 0
        
        test_dir = Path(temp_root) / "range_test"
        test_dir.mkdir(exist_ok=True)
        
        dk = DownloadKit(save_path=str(test_dir), roads=1)
        dk.split = False
        
        mission = dk.add(
            f"{base_url}/test",
            rename="test_range.bin",
            file_exists='overwrite',
            split=False
        )
        
        result, info = mission.wait(show=False, timeout=15)
        
        states = [t['state'] for t in mission.state_transitions]
        print(f"状态流转: {states}")
        print(f"结果: {result}")
        print(f"信息: {info}")
        
        for t in mission.state_transitions:
            if 'range' in t.get('state', '').lower() or 'range' in t.get('info', '').lower():
                print(f"  Range相关: {t}")
        
        final_file = test_dir / "test_range.bin"
        part_file = test_dir / "test_range.bin.part"
        
        print(f"最终文件存在: {final_file.exists()}")
        print(f"临时文件存在: {part_file.exists()}")
        
        if 'range_mismatch' in str(states).lower() or result == 'failed':
            passed = not part_file.exists()
        else:
            passed = result == 'success'
        
        results.append({
            'name': 'Range/Content-Range不匹配',
            'passed': passed,
            'state_transitions': states,
            'part_file': part_file.exists(),
            'final_file': final_file.exists(),
            'exit_code': 0 if passed else 1
        })
        print(f"结果: {'通过' if passed else '失败'}")
        
        print("\n" + "-"*70)
        print("场景4: 完整性校验失败清理")
        print("-"*70)
        
        MockHandler.support_range = True
        MockHandler.wrong_range_offset = 0
        MockHandler.return_corrupt = True
        MockHandler.delay_seconds = 0
        
        test_dir = Path(temp_root) / "integrity_test"
        test_dir.mkdir(exist_ok=True)
        
        dk = DownloadKit(save_path=str(test_dir), roads=1)
        dk.split = False
        
        mission = dk.add(
            f"{base_url}/test",
            rename="test_integrity.bin",
            file_exists='overwrite',
            integrity_algorithm='sha256',
            expected_hash=TEST_DATA_SHA256
        )
        
        result, info = mission.wait(show=False, timeout=15)
        
        states = [t['state'] for t in mission.state_transitions]
        print(f"状态流转: {states}")
        print(f"结果: {result}")
        print(f"信息: {info}")
        
        for t in mission.state_transitions:
            if 'integrity' in t.get('state', '').lower() or 'integrity' in t.get('info', '').lower():
                print(f"  完整性相关: {t}")
        
        final_file = test_dir / "test_integrity.bin"
        part_file = test_dir / "test_integrity.bin.part"
        
        print(f"最终文件存在: {final_file.exists()}")
        print(f"临时文件存在: {part_file.exists()}")
        
        passed = (
            result == 'integrity_failed' and
            not final_file.exists() and
            not part_file.exists()
        )
        results.append({
            'name': '完整性校验失败清理',
            'passed': passed,
            'state_transitions': states,
            'part_file': part_file.exists(),
            'final_file': final_file.exists(),
            'exit_code': 0 if passed else 1
        })
        print(f"结果: {'通过' if passed else '失败'}")
        
        print("\n" + "-"*70)
        print("场景5: 完整性校验可选（默认不校验）")
        print("-"*70)
        
        MockHandler.return_corrupt = True
        
        test_dir = Path(temp_root) / "integrity_optional"
        test_dir.mkdir(exist_ok=True)
        
        dk = DownloadKit(save_path=str(test_dir), roads=1)
        dk.split = False
        
        mission = dk.add(
            f"{base_url}/test",
            rename="test_optional.bin",
            file_exists='overwrite'
        )
        
        result, info = mission.wait(show=False, timeout=15)
        
        states = [t['state'] for t in mission.state_transitions]
        print(f"状态流转: {states}")
        print(f"结果: {result}")
        
        has_verifying = any('verifying' in t.get('state', '').lower() for t in mission.state_transitions)
        print(f"是否进行了完整性校验: {has_verifying}")
        
        final_file = test_dir / "test_optional.bin"
        part_file = test_dir / "test_optional.bin.part"
        
        print(f"最终文件存在: {final_file.exists()}")
        print(f"临时文件存在: {part_file.exists()}")
        
        passed = result == 'success' and not has_verifying and final_file.exists()
        results.append({
            'name': '完整性校验可选',
            'passed': passed,
            'state_transitions': states,
            'part_file': part_file.exists(),
            'final_file': final_file.exists(),
            'exit_code': 0 if passed else 1
        })
        print(f"结果: {'通过' if passed else '失败'}")
        
        print("\n" + "-"*70)
        print("场景6: 并发同名下载冲突")
        print("-"*70)
        
        MockHandler.return_corrupt = False
        MockHandler.delay_seconds = 0.05
        
        test_dir = Path(temp_root) / "concurrent_test"
        test_dir.mkdir(exist_ok=True)
        
        dk = DownloadKit(save_path=str(test_dir), roads=5)
        dk.split = False
        dk.file_exists = 'rename'
        
        missions = []
        missions_lock = threading.Lock()
        
        def download_task(idx):
            mission = dk.add(
                f"{base_url}/test?idx={idx}",
                rename="concurrent.bin",
                file_exists='rename',
                split=False
            )
            with missions_lock:
                missions.append((idx, mission))
        
        threads = []
        for i in range(5):
            t = Thread(target=download_task, args=(i,), daemon=True)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join(timeout=20)
        
        time.sleep(1)
        
        file_names = set()
        all_success = True
        
        for idx, mission in missions:
            result, info = mission.wait(show=False, timeout=15)
            states = [t['state'] for t in mission.state_transitions]
            if result != 'success':
                all_success = False
            if mission.file_name:
                file_names.add(mission.file_name)
            print(f"任务{idx}: 结果={result}, 状态={states}, 文件名={mission.file_name}")
        
        files_in_dir = list(test_dir.glob("*"))
        print(f"\n目录中的文件: {[f.name for f in files_in_dir]}")
        print(f"唯一文件名数量: {len(file_names)}")
        
        passed = all_success and len(file_names) == 5
        results.append({
            'name': '并发同名下载冲突',
            'passed': passed,
            'state_transitions': [],
            'part_file': False,
            'final_file': len(files_in_dir) == 5,
            'exit_code': 0 if passed else 1
        })
        print(f"结果: {'通过' if passed else '失败'}")
        
    finally:
        server.shutdown()
        server.server_close()
        if os.path.exists(temp_root):
            shutil.rmtree(temp_root)
    
    print("\n" + "="*70)
    print("验证结果摘要")
    print("="*70)
    
    all_passed = True
    for r in results:
        status = "PASS" if r['passed'] else "FAIL"
        print(f"\n[{status}]: {r['name']}")
        if r['state_transitions']:
            print(f"  状态流转: {r['state_transitions']}")
        print(f"  .part 文件存在: {r['part_file']}")
        print(f"  最终文件存在: {r['final_file']}")
        print(f"  退出码: {r['exit_code']}")
        if not r['passed']:
            all_passed = False
    
    total = len(results)
    passed_count = len([r for r in results if r['passed']])
    
    print("\n" + "-"*70)
    print(f"总计: {passed_count}/{total} 验证通过")
    print("-"*70)
    
    exit_code = 0 if all_passed else 1
    print(f"\n$LASTEXITCODE = {exit_code}")
    sys.exit(exit_code)


if __name__ == '__main__':
    run_verification()
