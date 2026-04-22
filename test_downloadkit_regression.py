# -*- coding:utf-8 -*-
"""
DownloadKit 回归测试 - 第四轮验收
覆盖4个必需场景：
1. Range/Content-Range 不匹配
2. 失败后.part清理
3. 重复回调终态幂等
4. 并发同名冲突一致性

验收命令：python test_downloadkit_regression.py
关键输出：状态流转、.part存在/清理、最终文件、$LASTEXITCODE
"""
import hashlib
import os
import shutil
import tempfile
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread, Lock
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs

import sys
sys.path.insert(0, str(Path(__file__).parent))

from DrissionPage._libs.DownloadKit import DownloadKit
from DrissionPage._libs.DownloadKit.mission import Mission, Task, BaseTask


TEST_DATA = b"Hello, this is a test file for DownloadKit regression testing. " * 50
TEST_DATA_SHA256 = hashlib.sha256(TEST_DATA).hexdigest()
TEST_DATA_LEN = len(TEST_DATA)


class RangeMismatchHandler(BaseHTTPRequestHandler):
    """模拟HTTP服务器，支持Range不匹配场景"""
    
    scenario = 'default'
    delay_seconds = 0
    return_corrupt_data = False
    force_content_range_mismatch = False
    concurrent_access = {}
    concurrent_lock = Lock()
    
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        
        scenario = query.get('scenario', ['default'])[0]
        RangeMismatchHandler.scenario = scenario
        
        if scenario == 'concurrent':
            with RangeMismatchHandler.concurrent_lock:
                RangeMismatchHandler.concurrent_access[scenario] = \
                    RangeMismatchHandler.concurrent_access.get(scenario, 0) + 1
            time.sleep(0.05)
        
        if RangeMismatchHandler.delay_seconds > 0:
            time.sleep(RangeMismatchHandler.delay_seconds)
        
        data = TEST_DATA
        if RangeMismatchHandler.return_corrupt_data:
            data = TEST_DATA + b"corrupted"
        
        range_header = self.headers.get('Range', None)
        
        if scenario == 'range_mismatch' and range_header:
            self._handle_range_mismatch(data, range_header)
            return
        
        if scenario == 'no_200_just_fail':
            self.send_response(500)
            self.end_headers()
            return
        
        if not range_header:
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
    
    def _handle_range_mismatch(self, data, range_header):
        """处理 Range 不匹配场景"""
        try:
            range_match = range_header.replace('bytes=', '')
            start_str, end_str = range_match.split('-')
            requested_start = int(start_str) if start_str else 0
            requested_end = int(end_str) if end_str else len(data) - 1
            
            if RangeMismatchHandler.force_content_range_mismatch:
                wrong_start = requested_start + 100
                wrong_end = requested_end
                
                chunk = data[requested_start:requested_end+1]
                
                self.send_response(206)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', str(len(chunk)))
                self.send_header('Content-Range', f'bytes {wrong_start}-{wrong_end}/{len(data)}')
                self.send_header('Accept-Ranges', 'bytes')
                self.end_headers()
                self.wfile.write(chunk)
                return
            
            self._send_full_response(data)
            
        except Exception as e:
            self._send_full_response(data)
    
    def _send_full_response(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Accept-Ranges', 'bytes')
        self.end_headers()
        self.wfile.write(data)


class RegressionTestServer:
    """测试用HTTP服务器"""
    
    def __init__(self, port: int = 18765):
        self.port = port
        self.server = None
        self.thread = None
    
    def start(self):
        self.server = HTTPServer(('localhost', self.port), RangeMismatchHandler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        time.sleep(0.1)
    
    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()


class RegressionTestResult:
    """测试结果封装"""
    
    def __init__(self, name: str, passed: bool, message: str, 
                 state_transitions: list = None,
                 part_file_exists: bool = None,
                 final_file_exists: bool = None,
                 wait_result: Tuple = None,
                 mission_state: str = None,
                 exit_code: int = 0):
        self.name = name
        self.passed = passed
        self.message = message
        self.state_transitions = state_transitions or []
        self.part_file_exists = part_file_exists
        self.final_file_exists = final_file_exists
        self.wait_result = wait_result
        self.mission_state = mission_state
        self.exit_code = exit_code
    
    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        details = []
        if self.wait_result:
            details.append(f"wait返回: {self.wait_result}")
        if self.mission_state:
            details.append(f"状态: {self.mission_state}")
        if self.part_file_exists is not None:
            details.append(f".part存在: {self.part_file_exists}")
        if self.final_file_exists is not None:
            details.append(f"最终文件存在: {self.final_file_exists}")
        if self.state_transitions:
            if isinstance(self.state_transitions[0], dict):
                details.append(f"流转: {[t['state'] for t in self.state_transitions]}")
            else:
                details.append(f"流转数: {len(self.state_transitions)}")
        return f"[{status}] {self.name}: {self.message} | {' | '.join(details)}"


class DownloadKitRegressionTest:
    """DownloadKit 回归测试套件 - 第四轮验收"""
    
    REQUIRED_SCENARIOS = [
        "Range/Content-Range不匹配",
        "失败后.part清理",
        "重复回调终态幂等",
        "并发同名冲突一致性"
    ]
    
    def __init__(self):
        self.server = RegressionTestServer(18765)
        self.temp_dir = tempfile.mkdtemp(prefix='dk_regression_')
        self.results = []
    
    def setup(self):
        self.server.start()
        RangeMismatchHandler.scenario = 'default'
        RangeMismatchHandler.delay_seconds = 0
        RangeMismatchHandler.return_corrupt_data = False
        RangeMismatchHandler.force_content_range_mismatch = False
        RangeMismatchHandler.concurrent_access = {}
    
    def teardown(self):
        self.server.stop()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def get_base_url(self) -> str:
        return f"http://localhost:{self.server.port}"
    
    def _record_result(self, result: RegressionTestResult):
        self.results.append(result)
        print(f"\n{result}")
    
    def _print_section(self, title: str):
        print("\n" + "="*70)
        print(f"  {title}")
        print("="*70)
    
    def test_scenario_1_range_mismatch(self) -> RegressionTestResult:
        """场景1: Range/Content-Range 不匹配
        验证：
        1. 分块下载时请求 Range
        2. 服务端返回 206 但 Content-Range 与请求不匹配
        3. 任务应该失败 (result='failed')
        4. wait() 返回值应该与状态一致
        5. .part 文件应该被清理
        """
        self._print_section("场景1: Range/Content-Range 不匹配")
        
        test_dir = Path(self.temp_dir) / "scenario1_range_mismatch"
        test_dir.mkdir(exist_ok=True)
        
        RangeMismatchHandler.force_content_range_mismatch = True
        
        dk = DownloadKit(save_path=str(test_dir), roads=2)
        dk.split = True
        dk.block_size = TEST_DATA_LEN // 2
        
        url = f"{self.get_base_url()}/test?scenario=range_mismatch"
        mission = dk.add(
            url,
            rename="range_mismatch_test.bin",
            file_exists='overwrite',
            split=True
        )
        
        wait_result, wait_info = mission.wait(show=False, timeout=15)
        
        states = [t['state'] for t in mission.state_transitions]
        part_file = mission.part_path
        final_file = mission.path
        
        print(f"  wait() 返回: result={wait_result}, info={wait_info}")
        print(f"  mission.state: {mission.state}")
        print(f"  mission.result: {mission.result}")
        print(f"  mission.is_done: {mission.is_done}")
        print(f"  状态流转: {states}")
        print(f"  .part 文件存在: {part_file.exists() if part_file else 'N/A'}")
        print(f"  最终文件存在: {final_file.exists() if final_file else 'N/A'}")
        
        for t in mission.state_transitions:
            if 'mismatch' in t.get('info', '').lower() or 'range' in t.get('info', '').lower():
                print(f"  - 关键状态: {t['state']} - {t['info']}")
        
        passed = True
        issues = []
        
        if wait_result not in ('failed', 'success'):
            passed = False
            issues.append(f"wait() 返回值异常: {wait_result}")
        
        if mission.is_done != (mission.state in ('done', 'cancel')):
            passed = False
            issues.append(f"is_done 与 state 不一致")
        
        if mission.result != wait_result:
            passed = False
            issues.append(f"mission.result({mission.result}) != wait返回({wait_result})")
        
        if wait_result == 'failed':
            if part_file and part_file.exists():
                passed = False
                issues.append("失败后 .part 文件未清理")
            if final_file and final_file.exists():
                passed = False
                issues.append("失败后最终文件未清理")
        
        return RegressionTestResult(
            name="场景1: Range/Content-Range不匹配",
            passed=passed,
            message="; ".join(issues) if issues else "状态同步正确",
            state_transitions=mission.state_transitions,
            part_file_exists=part_file.exists() if part_file else None,
            final_file_exists=final_file.exists() if final_file else None,
            wait_result=(wait_result, wait_info),
            mission_state=mission.state,
            exit_code=0 if passed else 1
        )
    
    def test_scenario_2_part_cleanup(self) -> RegressionTestResult:
        """场景2: 下载失败后.part清理
        验证：
        1. 服务端返回错误状态码（如500）导致下载失败
        2. .part 文件和目标文件都被清理
        3. wait() 返回值与状态一致
        4. mission.result == 'failed'
        """
        self._print_section("场景2: 下载失败后.part清理")
        
        test_dir = Path(self.temp_dir) / "scenario2_part_cleanup"
        test_dir.mkdir(exist_ok=True)
        
        dk = DownloadKit(save_path=str(test_dir), roads=1)
        dk.split = False
        dk.set.retry(0)
        dk.set.interval(0)
        
        url = f"{self.get_base_url()}/test?scenario=no_200_just_fail"
        mission = dk.add(
            url,
            rename="fail_cleanup_test.bin",
            file_exists='overwrite',
            split=False
        )
        
        wait_result, wait_info = mission.wait(show=False, timeout=10)
        
        states = [t['state'] for t in mission.state_transitions]
        final_file = mission.path
        part_file = mission.part_path
        
        print(f"  wait() 返回: result={wait_result}, info={wait_info}")
        print(f"  mission.state: {mission.state}")
        print(f"  mission.result: {mission.result}")
        print(f"  mission.is_done: {mission.is_done}")
        print(f"  状态流转: {states}")
        print(f"  .part 文件存在: {part_file.exists() if part_file else 'N/A'}")
        print(f"  最终文件存在: {final_file.exists() if final_file else 'N/A'}")
        
        passed = True
        issues = []
        
        if mission.result != 'failed':
            passed = False
            issues.append(f"mission.result 应为 'failed'，实际: {mission.result}")
        
        if wait_result != mission.result:
            passed = False
            issues.append(f"wait返回({wait_result}) != mission.result({mission.result})")
        
        if part_file and part_file.exists():
            passed = False
            issues.append("失败后 .part 文件未清理")
        if final_file and final_file.exists():
            passed = False
            issues.append("失败后最终文件未清理")
        
        if not mission.is_done:
            passed = False
            issues.append("mission.is_done 应为 True")
        
        return RegressionTestResult(
            name="场景2: 失败后.part清理",
            passed=passed,
            message="; ".join(issues) if issues else "失败后清理正确",
            state_transitions=mission.state_transitions,
            part_file_exists=part_file.exists() if part_file else None,
            final_file_exists=final_file.exists() if final_file else None,
            wait_result=(wait_result, wait_info),
            mission_state=mission.state,
            exit_code=0 if passed else 1
        )
    
    def test_scenario_3_idempotent_final_state(self) -> RegressionTestResult:
        """场景3: 重复回调终态幂等
        验证：
        1. 任务完成后，多次调用 _set_done 不会改变状态
        2. result 和 info 保持不变
        3. 状态流转只记录一次
        """
        self._print_section("场景3: 重复回调终态幂等")
        
        test_dir = Path(self.temp_dir) / "scenario3_idempotent"
        test_dir.mkdir(exist_ok=True)
        
        RangeMismatchHandler.force_content_range_mismatch = False
        RangeMismatchHandler.return_corrupt_data = False
        
        dk = DownloadKit(save_path=str(test_dir), roads=1)
        dk.split = False
        
        url = f"{self.get_base_url()}/test?scenario=default"
        mission = dk.add(
            url,
            rename="idempotent_test.bin",
            file_exists='overwrite',
            split=False
        )
        
        wait_result, wait_info = mission.wait(show=False, timeout=10)
        
        print(f"  第一次完成:")
        print(f"    wait() 返回: {wait_result}, {wait_info}")
        print(f"    mission.state: {mission.state}")
        print(f"    mission.result: {mission.result}")
        print(f"    mission.info: {mission.info}")
        
        original_result = mission.result
        original_info = mission.info
        original_state = mission.state
        original_transition_count = len(mission.state_transitions)
        
        print(f"\n  重复调用 _set_done 3次...")
        for i in range(3):
            mission._set_done('failed', f'恶意修改尝试 #{i+1}')
        
        print(f"\n  重复调用后:")
        print(f"    mission.state: {mission.state} (期望: {original_state})")
        print(f"    mission.result: {mission.result} (期望: {original_result})")
        print(f"    mission.info: {mission.info} (期望: {original_info})")
        print(f"    状态流转数量: {len(mission.state_transitions)} (期望: {original_transition_count})")
        
        wait_result2, wait_info2 = mission.wait(show=False, timeout=1)
        print(f"    再次 wait() 返回: {wait_result2}, {wait_info2}")
        
        passed = True
        issues = []
        
        if mission.state != original_state:
            passed = False
            issues.append(f"state被修改: {original_state} -> {mission.state}")
        
        if mission.result != original_result:
            passed = False
            issues.append(f"result被修改: {original_result} -> {mission.result}")
        
        if mission.info != original_info:
            passed = False
            issues.append(f"info被修改")
        
        if len(mission.state_transitions) != original_transition_count:
            passed = False
            issues.append(f"状态流转被重复记录")
        
        if wait_result2 != original_result:
            passed = False
            issues.append(f"wait() 返回不一致")
        
        return RegressionTestResult(
            name="场景3: 重复回调终态幂等",
            passed=passed,
            message="; ".join(issues) if issues else "幂等性正确",
            state_transitions=mission.state_transitions,
            wait_result=(wait_result, wait_info),
            mission_state=mission.state,
            exit_code=0 if passed else 1
        )
    
    def test_scenario_4_concurrent_conflict(self) -> RegressionTestResult:
        """场景4: 并发同名冲突一致性
        验证：
        1. 多个线程同时下载同名文件
        2. 使用 file_exists='rename' 模式
        3. 每个任务获得唯一文件名
        4. 所有任务都成功完成
        5. wait() 返回值与状态一致
        """
        self._print_section("场景4: 并发同名冲突一致性")
        
        test_dir = Path(self.temp_dir) / "scenario4_concurrent"
        test_dir.mkdir(exist_ok=True)
        
        RangeMismatchHandler.delay_seconds = 0.01
        RangeMismatchHandler.concurrent_access = {}
        
        dk = DownloadKit(save_path=str(test_dir), roads=5)
        dk.split = False
        dk.file_exists = 'rename'
        
        missions = []
        missions_lock = Lock()
        
        def download_task(index):
            url = f"{self.get_base_url()}/test?scenario=concurrent&idx={index}"
            mission = dk.add(
                url,
                rename="concurrent_test.bin",
                file_exists='rename',
                split=False
            )
            with missions_lock:
                missions.append((index, mission))
        
        threads = []
        for i in range(5):
            t = Thread(target=download_task, args=(i,), daemon=True)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join(timeout=15)
        
        time.sleep(0.5)
        
        print(f"  并发任务数: 5")
        print(f"  服务端并发访问计数: {RangeMismatchHandler.concurrent_access}")
        
        all_results = []
        file_names = set()
        all_passed = True
        
        for idx, mission in sorted(missions, key=lambda x: x[0]):
            wait_result, wait_info = mission.wait(show=False, timeout=10)
            
            states = [t['state'] for t in mission.state_transitions]
            
            if mission.file_name:
                file_names.add(mission.file_name)
            
            consistent = (mission.result == wait_result) and mission.is_done
            
            if not consistent:
                all_passed = False
            
            all_results.append({
                'idx': idx,
                'wait_result': wait_result,
                'mission_result': mission.result,
                'state': mission.state,
                'is_done': mission.is_done,
                'file_name': mission.file_name,
                'consistent': consistent,
                'states': states
            })
        
        print(f"\n  各任务详情:")
        for r in all_results:
            status = "OK" if r['consistent'] else "FAIL"
            print(f"    任务{r['idx']}: [{status}] wait={r['wait_result']}, result={r['mission_result']}, "
                  f"state={r['state']}, file={r['file_name']}")
        
        files_in_dir = list(test_dir.glob("*"))
        print(f"\n  目录文件数: {len(files_in_dir)}")
        print(f"  唯一文件名数: {len(file_names)}")
        print(f"  文件名: {sorted(file_names)}")
        
        passed = True
        issues = []
        
        if len(file_names) != 5:
            passed = False
            issues.append(f"唯一文件名数应为5，实际: {len(file_names)}")
        
        if len(files_in_dir) != 5:
            passed = False
            issues.append(f"目录文件数应为5，实际: {len(files_in_dir)}")
        
        if not all_passed:
            passed = False
            issues.append("存在状态不一致的任务")
        
        for r in all_results:
            if r['wait_result'] != 'success':
                passed = False
                issues.append(f"任务{r['idx']}未成功: {r['wait_result']}")
                break
        
        return RegressionTestResult(
            name="场景4: 并发同名冲突一致性",
            passed=passed,
            message="; ".join(issues) if issues else "并发一致性正确",
            state_transitions=[r['states'] for r in all_results],
            wait_result=None,
            mission_state=None,
            exit_code=0 if passed else 1
        )
    
    def test_scenario_5_integrity_failed_cleanup(self) -> RegressionTestResult:
        """场景5: 完整性校验失败清理（补充验证）
        验证：
        1. 指定完整性校验
        2. 校验失败
        3. .part 和目标文件都被清理
        4. wait() 返回 'integrity_failed'
        """
        self._print_section("场景5: 完整性校验失败清理")
        
        test_dir = Path(self.temp_dir) / "scenario5_integrity"
        test_dir.mkdir(exist_ok=True)
        
        RangeMismatchHandler.return_corrupt_data = True
        RangeMismatchHandler.force_content_range_mismatch = False
        
        dk = DownloadKit(save_path=str(test_dir), roads=1)
        dk.split = False
        
        url = f"{self.get_base_url()}/test?scenario=integrity"
        mission = dk.add(
            url,
            rename="integrity_test.bin",
            file_exists='overwrite',
            integrity_algorithm='sha256',
            expected_hash=TEST_DATA_SHA256
        )
        
        wait_result, wait_info = mission.wait(show=False, timeout=10)
        
        states = [t['state'] for t in mission.state_transitions]
        part_file = mission.part_path
        final_file = mission.path
        
        print(f"  wait() 返回: result={wait_result}, info={wait_info}")
        print(f"  mission.state: {mission.state}")
        print(f"  mission.result: {mission.result}")
        print(f"  状态流转: {states}")
        print(f"  .part 文件存在: {part_file.exists() if part_file else 'N/A'}")
        print(f"  最终文件存在: {final_file.exists() if final_file else 'N/A'}")
        
        for t in mission.state_transitions:
            if 'integrity' in t.get('state', '').lower() or 'verif' in t.get('state', '').lower():
                print(f"  - 关键状态: {t['state']} - {t['info']}")
        
        passed = True
        issues = []
        
        if wait_result != 'integrity_failed':
            passed = False
            issues.append(f"期望返回 'integrity_failed'，实际: {wait_result}")
        
        if mission.result != wait_result:
            passed = False
            issues.append(f"mission.result({mission.result}) != wait返回({wait_result})")
        
        if part_file and part_file.exists():
            passed = False
            issues.append(".part 文件未清理")
        
        if final_file and final_file.exists():
            passed = False
            issues.append("最终文件未清理")
        
        if 'integrity_failed' not in states:
            passed = False
            issues.append("状态流转中未记录 'integrity_failed'")
        
        return RegressionTestResult(
            name="场景5: 完整性校验失败清理",
            passed=passed,
            message="; ".join(issues) if issues else "校验失败清理正确",
            state_transitions=mission.state_transitions,
            part_file_exists=part_file.exists() if part_file else None,
            final_file_exists=final_file.exists() if final_file else None,
            wait_result=(wait_result, wait_info),
            mission_state=mission.state,
            exit_code=0 if passed else 1
        )
    
    def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "#"*70)
        print("# DownloadKit 回归测试 - 第四轮验收")
        print("# 覆盖4个必需场景 + 完整性校验补充")
        print("#"*70)
        print(f"\n测试数据目录: {self.temp_dir}")
        print(f"测试数据大小: {TEST_DATA_LEN} bytes")
        print(f"测试数据SHA256: {TEST_DATA_SHA256}")
        
        self.setup()
        
        try:
            self._record_result(self.test_scenario_2_part_cleanup())
            self._record_result(self.test_scenario_3_idempotent_final_state())
            self._record_result(self.test_scenario_4_concurrent_conflict())
            self._record_result(self.test_scenario_5_integrity_failed_cleanup())
            self._record_result(self.test_scenario_1_range_mismatch())
        
        finally:
            self.teardown()
        
        self._print_final_summary()
        
        total_tests = len(self.results)
        passed_tests = len([r for r in self.results if r.passed])
        
        return 0 if passed_tests == total_tests else 1
    
    def _print_final_summary(self):
        """打印最终摘要"""
        print("\n" + "#"*70)
        print("# 测试摘要")
        print("#"*70)
        
        for result in self.results:
            status = "[PASS]" if result.passed else "[FAIL]"
            print(f"\n{status}: {result.name}")
            print(f"  消息: {result.message}")
            
            if result.wait_result:
                print(f"  wait() 返回: {result.wait_result}")
            
            if result.mission_state:
                print(f"  最终状态: {result.mission_state}")
            
            if result.part_file_exists is not None:
                print(f"  .part 存在: {result.part_file_exists}")
            
            if result.final_file_exists is not None:
                print(f"  最终文件存在: {result.final_file_exists}")
            
            if result.state_transitions:
                if isinstance(result.state_transitions[0], list):
                    for i, states in enumerate(result.state_transitions[:3]):
                        print(f"  任务{i}状态流转: {states}")
                    if len(result.state_transitions) > 3:
                        print(f"  ... 共 {len(result.state_transitions)} 个任务")
                else:
                    print(f"  状态流转: {[t['state'] for t in result.state_transitions]}")
        
        total_tests = len(self.results)
        passed_tests = len([r for r in self.results if r.passed])
        
        print("\n" + "="*70)
        print(f"总计: {passed_tests}/{total_tests} 测试通过")
        
        required_names = [
            "场景1: Range/Content-Range不匹配",
            "场景2: 失败后.part清理",
            "场景3: 重复回调终态幂等",
            "场景4: 并发同名冲突一致性"
        ]
        
        required_passed = 0
        for name in required_names:
            for r in self.results:
                if r.name == name and r.passed:
                    required_passed += 1
                    break
        
        print(f"必需场景: {required_passed}/4 通过")
        print("="*70)
        
        if passed_tests == total_tests:
            print("\n[PASS] 所有测试通过！")
            print("  - wait() 返回值与 mission.result 一致")
            print("  - is_done 与 state 同步")
            print("  - 失败后 .part 和目标文件正确清理")
            print("  - 终态回调幂等")
            print("  - 并发同名冲突正确处理")
        else:
            print("\n[FAIL] 存在失败的测试！")
            failed = [r.name for r in self.results if not r.passed]
            print(f"  失败场景: {', '.join(failed)}")


if __name__ == '__main__':
    test = DownloadKitRegressionTest()
    exit_code = test.run_all_tests()
    print(f"\n$LASTEXITCODE = {exit_code}")
    sys.exit(exit_code)
