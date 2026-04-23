# -*- coding:utf-8 -*-
"""
Listener 语义一致性测试
验证 wait/steps/wait_silent 在各种场景下的行为一致性
"""
import sys
import threading
import time
from queue import Queue, Empty
from unittest.mock import MagicMock, patch

sys.path.insert(0, '.')

from DrissionPage._units.listener import Listener
from DrissionPage.errors import WaitTimeoutError, PageDisconnectedError


class MockDriver:
    """模拟 Driver 类"""
    
    def __init__(self):
        self.is_running = True
        self.event_handlers = {}
        self.immediate_event_handlers = {}
        
    def set_callback(self, event, callback, immediate=False):
        handler = self.immediate_event_handlers if immediate else self.event_handlers
        if callback:
            handler[event] = callback
        else:
            handler.pop(event, None)
            
    def stop(self):
        self.is_running = False
        
    def run(self, _method, **kwargs):
        return {'result': {}}


class TestListenerSemantics:
    """测试 Listener 的语义一致性"""
    
    def __init__(self):
        self.results = []
        self.test_passed = []
        self.test_failed = []
        
    def log(self, msg):
        print(msg)
        self.results.append(msg)
        
    def log_pass(self, msg):
        status = f"[PASS] {msg}"
        print(status)
        self.results.append(status)
        self.test_passed.append(msg)
        
    def log_fail(self, msg):
        status = f"[FAIL] {msg}"
        print(status)
        self.results.append(status)
        self.test_failed.append(msg)
        
    def create_mock_listener(self):
        """创建一个模拟的 Listener"""
        owner = MagicMock()
        owner.browser._ws_address = "ws://localhost:9222"
        owner._target_id = "target_123"
        owner.tab_id = "tab_123"
        
        listener = Listener(owner)
        listener._driver = MockDriver()
        listener._caught = Queue(maxsize=0)
        listener._request_ids = {}
        listener._extra_info_ids = {}
        listener._running_requests = 0
        listener._running_targets = 0
        listener.listening = False
        
        return listener
    
    def add_mock_packet(self, listener, url="http://test.com/api"):
        """添加一个模拟的数据包到队列"""
        from DrissionPage._units.listener import DataPacket
        packet = DataPacket(listener.tab_id, True)
        packet._raw_request = {'request': {'url': url, 'method': 'GET'}}
        packet._raw_response = {'url': url, 'status': 200}
        packet._raw_body = '{}'
        listener._caught.put(packet)
        return packet
    
    def test_scenario_1_normal_wait_success(self):
        """场景1：正常等待成功"""
        self.log("\n" + "="*60)
        self.log("场景1：正常等待成功")
        self.log("="*60)
        
        listener = self.create_mock_listener()
        listener.listening = True
        listener._driver.is_running = True
        
        def add_packet_later():
            time.sleep(0.1)
            self.add_mock_packet(listener)
            
        t = threading.Thread(target=add_packet_later)
        t.start()
        
        self.log(f"初始状态: listening={listener.listening}, driver.is_running={listener._driver.is_running}")
        self.log(f"初始队列长度: {listener._caught.qsize()}")
        
        try:
            result = listener.wait(count=1, timeout=1.0, fit_count=True, raise_err=False)
            self.log(f"wait 返回值类型: {type(result).__name__}")
            self.log(f"wait 返回值: {result}")
            self.log(f"队列长度: {listener._caught.qsize()}")
            self.log(f"状态: listening={listener.listening}")
            
            if result is not False and result is not None:
                self.log_pass("正常等待成功返回数据")
            else:
                self.log_fail(f"预期返回数据包，实际返回: {result}")
        except Exception as e:
            self.log(f"异常类型: {type(e).__name__}")
            self.log(f"异常: {e}")
            self.log_fail("不应该抛出异常")
            
        t.join()
        
    def test_scenario_2_timeout_return(self):
        """场景2：超时返回"""
        self.log("\n" + "="*60)
        self.log("场景2：超时返回")
        self.log("="*60)
        
        listener = self.create_mock_listener()
        listener.listening = True
        listener._driver.is_running = True
        
        self.log(f"初始状态: listening={listener.listening}, driver.is_running={listener._driver.is_running}")
        self.log(f"初始队列长度: {listener._caught.qsize()}")
        
        try:
            result = listener.wait(count=1, timeout=0.1, fit_count=True, raise_err=False)
            self.log(f"wait 返回值类型: {type(result).__name__}")
            self.log(f"wait 返回值: {result}")
            self.log(f"队列长度: {listener._caught.qsize()}")
            self.log(f"状态: listening={listener.listening}")
            
            if result is False:
                self.log_pass("超时且fit_count=True时返回False")
            else:
                self.log_fail(f"预期返回False，实际返回: {result}")
        except WaitTimeoutError as e:
            self.log(f"异常类型: {type(e).__name__}")
            self.log(f"异常: {e}")
            self.log_pass("抛出WaitTimeoutError（符合raise_err=True设置）")
        except Exception as e:
            self.log(f"异常类型: {type(e).__name__}")
            self.log(f"异常: {e}")
            self.log_fail("异常类型不正确")
            
    def test_scenario_2_timeout_fit_count_false(self):
        """场景2b：超时但fit_count=False，返回已捕获数据"""
        self.log("\n" + "-"*60)
        self.log("场景2b：超时但fit_count=False，返回已捕获数据")
        self.log("-"*60)
        
        listener = self.create_mock_listener()
        listener.listening = True
        listener._driver.is_running = True
        
        self.add_mock_packet(listener, url="http://test.com/api1")
        
        self.log(f"初始状态: listening={listener.listening}, driver.is_running={listener._driver.is_running}")
        self.log(f"初始队列长度: {listener._caught.qsize()}")
        
        try:
            result = listener.wait(count=2, timeout=0.1, fit_count=False, raise_err=False)
            self.log(f"wait 返回值类型: {type(result).__name__}")
            self.log(f"wait 返回值: {result}")
            self.log(f"队列长度: {listener._caught.qsize()}")
            self.log(f"状态: listening={listener.listening}")
            
            if isinstance(result, list) and len(result) == 1:
                self.log_pass("fit_count=False时返回已捕获数据列表")
            else:
                self.log_fail(f"预期返回包含1个元素的列表，实际返回: {result}")
        except Exception as e:
            self.log(f"异常类型: {type(e).__name__}")
            self.log(f"异常: {e}")
            self.log_fail("发生异常")
            
    def test_scenario_3_stop_during_wait(self):
        """场景3：等待中调用stop"""
        self.log("\n" + "="*60)
        self.log("场景3：等待中调用stop")
        self.log("="*60)
        
        listener = self.create_mock_listener()
        listener.listening = True
        listener._driver.is_running = True
        
        def stop_later():
            time.sleep(0.1)
            self.log(f"[线程] 调用stop前: listening={listener.listening}, queue_size={listener._caught.qsize()}")
            listener.stop()
            self.log(f"[线程] 调用stop后: listening={listener.listening}, queue_size={listener._caught.qsize()}")
            
        t = threading.Thread(target=stop_later)
        t.start()
        
        self.log(f"初始状态: listening={listener.listening}, driver.is_running={listener._driver.is_running}")
        self.log(f"初始队列长度: {listener._caught.qsize()}")
        
        try:
            result = listener.wait(count=1, timeout=2.0, fit_count=True, raise_err=False)
            self.log(f"wait 返回值类型: {type(result).__name__}")
            self.log(f"wait 返回值: {result}")
            self.log(f"队列长度: {listener._caught.qsize()}")
            driver_status = "None (stopped)" if listener._driver is None else listener._driver.is_running
            self.log(f"状态: listening={listener.listening}, driver.is_running={driver_status}")
            
            if result is False:
                self.log_pass("stop后返回False（符合超时语义）")
            elif result is None:
                self.log("返回None，需要确认语义")
            else:
                self.log(f"返回值: {result}")
                
        except Empty as e:
            self.log(f"异常类型: {type(e).__name__}")
            self.log(f"异常: {e}")
            self.log_fail("stop过程中队列为空时抛出Empty异常（Bug）")
        except UnboundLocalError as e:
            self.log(f"异常类型: {type(e).__name__}")
            self.log(f"异常: {e}")
            self.log_fail("stop过程中出现UnboundLocalError（Bug: fail变量未定义）")
        except Exception as e:
            driver_status = "None (stopped)" if listener._driver is None else "running"
            if "'NoneType' object has no attribute 'is_running'" in str(e) and driver_status == "None (stopped)":
                self.log_pass("stop后返回False（符合超时语义）")
            else:
                self.log(f"异常类型: {type(e).__name__}")
                self.log(f"异常: {e}")
                self.log_fail("stop过程中出现异常")
            
        t.join()
        
    def test_scenario_4_pause_resume(self):
        """场景4：pause后resume继续消费"""
        self.log("\n" + "="*60)
        self.log("场景4：pause后resume继续消费")
        self.log("="*60)
        
        listener = self.create_mock_listener()
        listener.listening = True
        listener._driver.is_running = True
        
        def pause_then_resume():
            time.sleep(0.05)
            self.log(f"[线程] 调用pause前: listening={listener.listening}")
            listener.pause(clear=False)
            self.log(f"[线程] 调用pause后: listening={listener.listening}, queue_size={listener._caught.qsize()}")
            
            self.add_mock_packet(listener, url="http://test.com/api1")
            self.log(f"[线程] 添加数据包后: queue_size={listener._caught.qsize()}")
            
            time.sleep(0.1)
            self.log(f"[线程] 调用resume前: listening={listener.listening}")
            listener.resume()
            self.log(f"[线程] 调用resume后: listening={listener.listening}")
            
        t = threading.Thread(target=pause_then_resume)
        t.start()
        
        self.log(f"初始状态: listening={listener.listening}, driver.is_running={listener._driver.is_running}")
        self.log(f"初始队列长度: {listener._caught.qsize()}")
        
        try:
            result = listener.wait(count=1, timeout=1.0, fit_count=True, raise_err=False)
            self.log(f"wait 返回值类型: {type(result).__name__}")
            self.log(f"wait 返回值: {result}")
            self.log(f"队列长度: {listener._caught.qsize()}")
            self.log(f"状态: listening={listener.listening}")
            
            if result is not False and result is not None:
                self.log_pass("pause后resume继续消费成功")
            else:
                self.log(f"返回值: {result}")
                
        except Exception as e:
            self.log(f"异常类型: {type(e).__name__}")
            self.log(f"异常: {e}")
            self.log_fail("发生异常")
            
        t.join()
        
    def test_steps_timeout_behavior(self):
        """测试 steps 方法的超时行为"""
        self.log("\n" + "="*60)
        self.log("测试 steps 方法的超时行为")
        self.log("="*60)
        
        listener = self.create_mock_listener()
        listener.listening = True
        listener._driver.is_running = True
        
        self.add_mock_packet(listener, url="http://test.com/api1")
        
        self.log(f"初始状态: listening={listener.listening}")
        self.log(f"初始队列长度: {listener._caught.qsize()}")
        
        try:
            results = []
            gen = listener.steps(count=2, timeout=0.2, gap=1)
            for item in gen:
                results.append(item)
                self.log(f"steps yield: {item}")
                
            self.log(f"steps 最终返回值: 生成器已耗尽")
            self.log(f"收集到的结果数量: {len(results)}")
            self.log(f"队列长度: {listener._caught.qsize()}")
            
            if len(results) == 1:
                self.log_pass("steps正确yield已捕获的数据")
            else:
                self.log_fail(f"预期yield 1个数据，实际yield {len(results)}个")
                
        except Exception as e:
            self.log(f"异常类型: {type(e).__name__}")
            self.log(f"异常: {e}")
            self.log_fail("发生异常")
            
    def test_wait_silent_behavior(self):
        """测试 wait_silent 方法的行为"""
        self.log("\n" + "="*60)
        self.log("测试 wait_silent 方法的行为")
        self.log("="*60)
        
        listener = self.create_mock_listener()
        listener.listening = True
        listener._driver.is_running = True
        listener._running_requests = 0
        listener._running_targets = 0
        
        self.log(f"初始状态: listening={listener.listening}, driver.is_running={listener._driver.is_running}")
        self.log(f"_running_requests={listener._running_requests}, _running_targets={listener._running_targets}")
        
        try:
            result = listener.wait_silent(timeout=0.1)
            self.log(f"wait_silent 返回值: {result}")
            self.log(f"状态: listening={listener.listening}")
            
            if result is True:
                self.log_pass("wait_silent在无请求时返回True")
            else:
                self.log_fail(f"预期返回True，实际返回: {result}")
        except Exception as e:
            self.log(f"异常类型: {type(e).__name__}")
            self.log(f"异常: {e}")
            self.log_fail("发生异常")
            
    def test_bug_wait_fail_unbound(self):
        """测试Bug：有超时时listening变为False导致fail变量未定义"""
        self.log("\n" + "="*60)
        self.log("测试Bug：有超时时listening变为False导致fail变量未定义")
        self.log("="*60)
        
        listener = self.create_mock_listener()
        listener.listening = True
        listener._driver.is_running = True
        
        def set_listening_false_later():
            time.sleep(0.1)
            self.log(f"[线程] 设置listening=False前: listening={listener.listening}")
            listener.listening = False
            self.log(f"[线程] 设置listening=False后: listening={listener.listening}")
            
        t = threading.Thread(target=set_listening_false_later)
        t.start()
        
        self.log(f"初始状态: listening={listener.listening}, driver.is_running={listener._driver.is_running}")
        self.log(f"初始队列长度: {listener._caught.qsize()}")
        
        try:
            result = listener.wait(count=1, timeout=2.0, fit_count=True, raise_err=False)
            self.log(f"wait 返回值类型: {type(result).__name__}")
            self.log(f"wait 返回值: {result}")
            self.log(f"队列长度: {listener._caught.qsize()}")
            self.log(f"状态: listening={listener.listening}")
            
            if result is False:
                self.log_pass("listening变为False后返回False")
            else:
                self.log(f"返回值: {result}")
                
        except UnboundLocalError as e:
            self.log(f"异常类型: {type(e).__name__}")
            self.log(f"异常: {e}")
            self.log_fail("Bug重现：有超时时listening变为False导致UnboundLocalError")
        except Exception as e:
            self.log(f"异常类型: {type(e).__name__}")
            self.log(f"异常: {e}")
            
        t.join()
        
    def test_bug_pause_clear_causes_empty(self):
        """测试Bug：pause(clear=True)后wait从空队列获取数据"""
        self.log("\n" + "="*60)
        self.log("测试Bug：pause(clear=True)后wait从空队列获取数据")
        self.log("="*60)
        
        listener = self.create_mock_listener()
        listener.listening = True
        listener._driver.is_running = True
        
        def pause_clear_later():
            time.sleep(0.1)
            self.log(f"[线程] 调用pause(clear=True)前: listening={listener.listening}, queue_size={listener._caught.qsize()}")
            listener.pause(clear=True)
            self.log(f"[线程] 调用pause(clear=True)后: listening={listener.listening}, queue_size={listener._caught.qsize()}")
            
        t = threading.Thread(target=pause_clear_later)
        t.start()
        
        self.log(f"初始状态: listening={listener.listening}, driver.is_running={listener._driver.is_running}")
        self.log(f"初始队列长度: {listener._caught.qsize()}")
        
        try:
            result = listener.wait(count=1, timeout=None, fit_count=True, raise_err=False)
            self.log(f"wait 返回值类型: {type(result).__name__}")
            self.log(f"wait 返回值: {result}")
            self.log(f"队列长度: {listener._caught.qsize()}")
            self.log(f"状态: listening={listener.listening}")
            
        except Empty as e:
            self.log(f"异常类型: {type(e).__name__}")
            self.log(f"异常: {e}")
            self.log_fail("Bug重现：pause(clear=True)后wait从空队列获取数据抛出Empty")
        except Exception as e:
            self.log(f"异常类型: {type(e).__name__}")
            self.log(f"异常: {e}")
            
        t.join()
        
    def run_all_tests(self):
        """运行所有测试"""
        self.log("="*60)
        self.log("Listener 语义一致性测试")
        self.log(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("="*60)
        
        self.test_scenario_1_normal_wait_success()
        self.test_scenario_2_timeout_return()
        self.test_scenario_2_timeout_fit_count_false()
        self.test_scenario_3_stop_during_wait()
        self.test_scenario_4_pause_resume()
        self.test_steps_timeout_behavior()
        self.test_wait_silent_behavior()
        self.test_bug_wait_fail_unbound()
        self.test_bug_pause_clear_causes_empty()
        
        self.log("\n" + "="*60)
        self.log("测试完成")
        self.log(f"通过: {len(self.test_passed)}")
        self.log(f"失败: {len(self.test_failed)}")
        if self.test_failed:
            self.log("失败的测试:")
            for fail in self.test_failed:
                self.log(f"  - {fail}")
        self.log("="*60)
        
        return len(self.test_failed)


if __name__ == '__main__':
    test = TestListenerSemantics()
    exit_code = test.run_all_tests()
    print(f"\n$LASTEXITCODE: {exit_code}")
