# -*- coding:utf-8 -*-
"""
测试 Downloader 同目录同名文件并发下载场景
覆盖：并发同名成功、部分失败、取消重试、重复回调去重、多轮一致性
"""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from shutil import rmtree
from threading import Barrier, Lock
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from DrissionPage._units.downloader import DownloadManager, DownloadMission, TabDownloadSettings


class MockBrowser:
    def __init__(self, download_path):
        self._download_path = download_path
        self.download_path = download_path
        self._frames = {}
        self._relation = {}
        self._driver = MagicMock()
        self._driver.set_callback = MagicMock()

    def _run_cdp(self, *args, **kwargs):
        return {}


def create_temp_file(file_path, content=b'test content'):
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'wb') as f:
        f.write(content)


def count_temp_files(tmp_path):
    if not Path(tmp_path).exists():
        return 0
    return len(list(Path(tmp_path).glob('*')))


class TestDownloaderConcurrency:
    
    def __init__(self):
        self.test_dir = tempfile.mkdtemp(prefix='dp_test_')
        self.download_path = os.path.join(self.test_dir, 'downloads')
        self.tmp_path = os.path.join(self.test_dir, 'tmp')
        os.makedirs(self.download_path, exist_ok=True)
        os.makedirs(self.tmp_path, exist_ok=True)
        
        TabDownloadSettings.TABS.clear()
    
    def cleanup(self):
        try:
            rmtree(self.test_dir)
        except:
            pass
    
    def simulate_download_begin(self, mgr, tab_id, guid, name, suggested_filename=None, frame_id='frame1'):
        if suggested_filename is None:
            suggested_filename = name
        
        mgr._browser._frames[frame_id] = tab_id
        
        kwargs = {
            'guid': guid,
            'frameId': frame_id,
            'suggestedFilename': suggested_filename,
            'url': f'http://test.com/{name}'
        }
        mgr._onDownloadWillBegin(**kwargs)
    
    def simulate_download_progress(self, mgr, guid, state, received_bytes=100, total_bytes=100):
        kwargs = {
            'guid': guid,
            'state': state,
            'receivedBytes': received_bytes,
            'totalBytes': total_bytes
        }
        mgr._onDownloadProgress(**kwargs)
    
    def test_concurrent_same_name_success(self):
        """
        测试：并发同名成功下载
        预期：只有一个文件使用原始名称，其他重命名；无覆盖；无残留临时文件
        """
        print("\n" + "="*60)
        print("Test 1: Concurrent same name download success")
        print("="*60)
        
        browser = MockBrowser(self.download_path)
        mgr = DownloadManager(browser)
        mgr._tmp_path = self.tmp_path
        
        TabDownloadSettings('browser').path = self.download_path
        TabDownloadSettings('browser').when_file_exists = 'rename'
        
        concurrent_count = 5
        filename = 'test.txt'
        
        for i in range(concurrent_count):
            guid = f'guid_{i}'
            create_temp_file(os.path.join(self.tmp_path, guid), f'content_{i}'.encode())
        
        barrier = Barrier(concurrent_count)
        errors = []
        results_lock = Lock()
        results = []
        
        def download_task(task_id):
            try:
                guid = f'guid_{task_id}'
                barrier.wait(timeout=5)
                
                self.simulate_download_begin(mgr, 'browser', guid, filename)
                
                barrier.wait(timeout=5)
                
                self.simulate_download_progress(mgr, guid, 'completed')
                
                with results_lock:
                    results.append({
                        'task_id': task_id,
                    })
            except Exception as e:
                errors.append(str(e))
                import traceback
                traceback.print_exc()
        
        threads = []
        for i in range(concurrent_count):
            t = threading.Thread(target=download_task, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join(timeout=10)
        
        download_files = list(Path(self.download_path).glob('test*.txt'))
        temp_files = count_temp_files(self.tmp_path)
        
        print(f"Concurrent tasks: {concurrent_count}")
        print(f"Downloaded files count: {len(download_files)}")
        print(f"Downloaded files: {[f.name for f in download_files]}")
        print(f"Remaining temp files: {temp_files}")
        
        assert len(download_files) == concurrent_count, f"Expected {concurrent_count} files, got {len(download_files)}"
        assert temp_files == 0, f"Remaining {temp_files} temp files"
        
        names = set()
        for f in download_files:
            assert f.name not in names, f"Duplicate filename: {f.name}"
            names.add(f.name)
        
        assert 'test.txt' in names, "Expected original filename 'test.txt' to exist"
        
        print("PASS: Test 1")
        return True
    
    def test_duplicate_final_state(self):
        """
        测试：重复回调去重
        预期：同一任务多次触发completed/canceled只计一次；状态不被覆盖
        """
        print("\n" + "="*60)
        print("Test 2: Duplicate final state blocking")
        print("="*60)
        
        browser = MockBrowser(self.download_path)
        mgr = DownloadManager(browser)
        mgr._tmp_path = self.tmp_path
        
        TabDownloadSettings('browser').path = self.download_path
        TabDownloadSettings('browser').when_file_exists = 'rename'
        
        guid = 'test_duplicate'
        create_temp_file(os.path.join(self.tmp_path, guid), b'content')
        
        self.simulate_download_begin(mgr, 'browser', guid, 'dup_test.txt')
        
        mission = None
        for mid, m in list(mgr._missions.items()):
            if m.id == guid:
                mission = m
                break
        
        assert mission is not None, "Mission should exist"
        assert mission._is_done is False, "Mission should not be done yet"
        
        self.simulate_download_progress(mgr, guid, 'completed')
        
        assert mission._is_done is True, "Mission should be done after first completed"
        assert mission.state == 'completed', "Mission state should be 'completed'"
        
        first_final_path = mission.final_path
        assert first_final_path is not None, "Final path should be set"
        
        self.simulate_download_progress(mgr, guid, 'completed')
        self.simulate_download_progress(mgr, guid, 'canceled')
        
        assert mission.state == 'completed', "Mission state should still be 'completed' after duplicate callbacks"
        assert mission.final_path == first_final_path, "Final path should not change"
        
        temp_files = count_temp_files(self.tmp_path)
        
        download_files = list(Path(self.download_path).glob('dup_test*.txt'))
        print(f"Downloaded files count: {len(download_files)}")
        print(f"Mission state: {mission.state}")
        print(f"Mission is_done: {mission._is_done}")
        print(f"Remaining temp files: {temp_files}")
        
        assert len(download_files) == 1, "Should have exactly 1 downloaded file"
        assert temp_files == 0, f"Remaining {temp_files} temp files"
        
        print("PASS: Test 2")
        return True
    
    def test_cancel_cleanup(self):
        """
        测试：取消后临时文件清理
        预期：cancel/skipped 后临时文件被清理
        """
        print("\n" + "="*60)
        print("Test 3: Cancel/Skip temp file cleanup")
        print("="*60)
        
        browser = MockBrowser(self.download_path)
        mgr = DownloadManager(browser)
        mgr._tmp_path = self.tmp_path
        
        TabDownloadSettings('browser').path = self.download_path
        TabDownloadSettings('browser').when_file_exists = 'rename'
        
        guid1 = 'cancel_test'
        guid2 = 'cancel_via_progress'
        
        create_temp_file(os.path.join(self.tmp_path, guid1), b'content1')
        create_temp_file(os.path.join(self.tmp_path, guid2), b'content2')
        
        self.simulate_download_begin(mgr, 'browser', guid1, 'cancel_file.txt')
        
        mission1 = None
        for mid, m in list(mgr._missions.items()):
            if m.id == guid1:
                mission1 = m
                break
        
        assert mission1 is not None, "Mission 1 should exist"
        mgr.cancel(mission1)
        
        assert mission1.state == 'canceled', "Mission 1 state should be 'canceled'"
        assert mission1._is_done is True, "Mission 1 should be done"
        
        self.simulate_download_begin(mgr, 'browser', guid2, 'cancel_file2.txt')
        
        mission2 = None
        for mid, m in list(mgr._missions.items()):
            if m.id == guid2:
                mission2 = m
                break
        
        assert mission2 is not None, "Mission 2 should exist"
        
        self.simulate_download_progress(mgr, guid2, 'canceled')
        
        assert mission2.state == 'canceled', "Mission 2 state should be 'canceled'"
        assert mission2._is_done is True, "Mission 2 should be done"
        
        temp_files = count_temp_files(self.tmp_path)
        
        download_files = list(Path(self.download_path).glob('cancel_file*.txt'))
        print(f"Downloaded files count: {len(download_files)}")
        print(f"Mission 1 state: {mission1.state}")
        print(f"Mission 2 state: {mission2.state}")
        print(f"Remaining temp files: {temp_files}")
        
        assert len(download_files) == 0, "Should have no downloaded files after cancel"
        assert temp_files == 0, f"Remaining {temp_files} temp files"
        
        print("PASS: Test 3")
        return True
    
    def test_skip_mode(self):
        """
        测试：skip 模式
        预期：文件已存在时跳过；并发时正确处理
        """
        print("\n" + "="*60)
        print("Test 4: Skip mode")
        print("="*60)
        
        browser = MockBrowser(self.download_path)
        mgr = DownloadManager(browser)
        mgr._tmp_path = self.tmp_path
        
        TabDownloadSettings('browser').path = self.download_path
        TabDownloadSettings('browser').when_file_exists = 'skip'
        
        existing_file = os.path.join(self.download_path, 'skip_test.txt')
        create_temp_file(existing_file, b'existing')
        
        guid1 = 'skip_guid1'
        guid2 = 'skip_guid2'
        create_temp_file(os.path.join(self.tmp_path, guid1), b'content1')
        create_temp_file(os.path.join(self.tmp_path, guid2), b'content2')
        
        self.simulate_download_begin(mgr, 'browser', guid1, 'skip_test.txt')
        self.simulate_download_begin(mgr, 'browser', guid2, 'skip_test.txt')
        
        mission1 = None
        mission2 = None
        for mid, m in list(mgr._all_missions.items()):
            if m.id == guid1:
                mission1 = m
            if m.id == guid2:
                mission2 = m
        
        assert mission1 is not None, "Mission 1 should exist in all_missions"
        assert mission2 is not None, "Mission 2 should exist in all_missions"
        
        assert mission1.state == 'skipped', f"Mission 1 state should be 'skipped', got {mission1.state}"
        assert mission2.state == 'skipped', f"Mission 2 state should be 'skipped', got {mission2.state}"
        assert mission1._is_done is True, "Mission 1 should be done"
        assert mission2._is_done is True, "Mission 2 should be done"
        
        temp_files = count_temp_files(self.tmp_path)
        
        download_files = list(Path(self.download_path).glob('skip_test*.txt'))
        print(f"Downloaded files count: {len(download_files)}")
        print(f"Downloaded files: {[f.name for f in download_files]}")
        print(f"Mission 1 state: {mission1.state}")
        print(f"Mission 2 state: {mission2.state}")
        print(f"Remaining temp files: {temp_files}")
        
        assert len(download_files) == 1, "Should have only 1 file (original)"
        assert download_files[0].name == 'skip_test.txt', "Should be original filename"
        assert temp_files == 0, f"Remaining {temp_files} temp files"
        
        print("PASS: Test 4")
        return True
    
    def test_overwrite_mode(self):
        """
        测试：overwrite 模式
        预期：覆盖模式下并发时最后一个完成的覆盖；但状态一致
        """
        print("\n" + "="*60)
        print("Test 5: Overwrite mode")
        print("="*60)
        
        browser = MockBrowser(self.download_path)
        mgr = DownloadManager(browser)
        mgr._tmp_path = self.tmp_path
        
        TabDownloadSettings('browser').path = self.download_path
        TabDownloadSettings('browser').when_file_exists = 'overwrite'
        
        concurrent_count = 3
        filename = 'overwrite_test.txt'
        
        for i in range(concurrent_count):
            guid = f'guid_{i}'
            create_temp_file(os.path.join(self.tmp_path, guid), f'content_{i}'.encode())
        
        missions = []
        for i in range(concurrent_count):
            guid = f'guid_{i}'
            self.simulate_download_begin(mgr, 'browser', guid, filename)
            
            mission = None
            for mid, m in list(mgr._missions.items()):
                if m.id == guid:
                    mission = m
                    break
            if mission:
                missions.append(mission)
            
            self.simulate_download_progress(mgr, guid, 'completed')
        
        download_files = list(Path(self.download_path).glob('overwrite_test*.txt'))
        temp_files = count_temp_files(self.tmp_path)
        
        print(f"Concurrent tasks: {concurrent_count}")
        print(f"Downloaded files count: {len(download_files)}")
        print(f"Remaining temp files: {temp_files}")
        
        for i, mission in enumerate(missions):
            print(f"Mission {i} state: {mission.state}, is_done: {mission._is_done}")
            assert mission.state == 'completed', f"Mission {i} state should be 'completed'"
            assert mission._is_done is True, f"Mission {i} should be done"
        
        assert temp_files == 0, f"Remaining {temp_files} temp files"
        
        print("PASS: Test 5")
        return True
    
    def test_multiple_rounds_consistency(self):
        """
        测试：多轮一致性
        预期：多轮下载后状态一致；无残留
        """
        print("\n" + "="*60)
        print("Test 6: Multiple rounds consistency")
        print("="*60)
        
        browser = MockBrowser(self.download_path)
        mgr = DownloadManager(browser)
        mgr._tmp_path = self.tmp_path
        
        TabDownloadSettings('browser').path = self.download_path
        TabDownloadSettings('browser').when_file_exists = 'rename'
        
        rounds = 3
        files_per_round = 2
        
        for round_num in range(rounds):
            print(f"\n--- Round {round_num + 1} ---")
            
            round_missions = []
            for i in range(files_per_round):
                guid = f'round{round_num}_file{i}'
                create_temp_file(os.path.join(self.tmp_path, guid), f'round{round_num}_content{i}'.encode())
                
                self.simulate_download_begin(mgr, 'browser', guid, f'multi_test.txt')
                
                mission = None
                for mid, m in list(mgr._missions.items()):
                    if m.id == guid:
                        mission = m
                        break
                if mission:
                    round_missions.append(mission)
                
                self.simulate_download_progress(mgr, guid, 'completed')
            
            temp_files = count_temp_files(self.tmp_path)
            
            download_files = list(Path(self.download_path).glob('multi_test*.txt'))
            print(f"Downloaded files count (so far): {len(download_files)}")
            print(f"Remaining temp files: {temp_files}")
            
            for i, mission in enumerate(round_missions):
                assert mission.state == 'completed', f"Round {round_num + 1} Mission {i} state should be 'completed'"
                assert mission._is_done is True, f"Round {round_num + 1} Mission {i} should be done"
            
            assert temp_files == 0, f"Round {round_num + 1}: Remaining {temp_files} temp files"
        
        download_files = list(Path(self.download_path).glob('multi_test*.txt'))
        
        expected_files = rounds * files_per_round
        print(f"\nFinal result:")
        print(f"Downloaded files count: {len(download_files)}")
        print(f"Downloaded files: {[f.name for f in download_files]}")
        
        assert len(download_files) == expected_files, f"Expected {expected_files} files, got {len(download_files)}"
        
        names = set()
        for f in download_files:
            assert f.name not in names, f"Duplicate filename: {f.name}"
            names.add(f.name)
        
        print("PASS: Test 6")
        return True
    
    def run_all_tests(self):
        """Run all tests"""
        results = []
        
        try:
            results.append(('Concurrent same name', self.test_concurrent_same_name_success()))
        except Exception as e:
            print(f"FAIL Test 1: {e}")
            import traceback
            traceback.print_exc()
            results.append(('Concurrent same name', False))
        
        try:
            results.append(('Duplicate final state', self.test_duplicate_final_state()))
        except Exception as e:
            print(f"FAIL Test 2: {e}")
            import traceback
            traceback.print_exc()
            results.append(('Duplicate final state', False))
        
        try:
            results.append(('Cancel cleanup', self.test_cancel_cleanup()))
        except Exception as e:
            print(f"FAIL Test 3: {e}")
            import traceback
            traceback.print_exc()
            results.append(('Cancel cleanup', False))
        
        try:
            results.append(('Skip mode', self.test_skip_mode()))
        except Exception as e:
            print(f"FAIL Test 4: {e}")
            import traceback
            traceback.print_exc()
            results.append(('Skip mode', False))
        
        try:
            results.append(('Overwrite mode', self.test_overwrite_mode()))
        except Exception as e:
            print(f"FAIL Test 5: {e}")
            import traceback
            traceback.print_exc()
            results.append(('Overwrite mode', False))
        
        try:
            results.append(('Multiple rounds', self.test_multiple_rounds_consistency()))
        except Exception as e:
            print(f"FAIL Test 6: {e}")
            import traceback
            traceback.print_exc()
            results.append(('Multiple rounds', False))
        
        print("\n" + "="*60)
        print("Test Summary")
        print("="*60)
        
        all_passed = True
        for name, passed in results:
            status = "PASS" if passed else "FAIL"
            print(f"{name}: {status}")
            if not passed:
                all_passed = False
        
        return all_passed


def main():
    print("="*60)
    print("Downloader Same Name Concurrent Download Test")
    print("="*60)
    
    test = TestDownloaderConcurrency()
    try:
        all_passed = test.run_all_tests()
        
        temp_files_remaining = count_temp_files(test.tmp_path)
        
        print("\n" + "="*60)
        print("Final Statistics")
        print("="*60)
        print(f"Remaining temp files: {temp_files_remaining}")
        
        if all_passed and temp_files_remaining == 0:
            print("All tests passed, no remaining temp files")
            return 0
        else:
            print("Some tests failed or temp files remain")
            return 1
    finally:
        test.cleanup()


if __name__ == '__main__':
    exit_code = main()
    print(f"\nLASTEXITCODE = {exit_code}")
    sys.exit(exit_code)
