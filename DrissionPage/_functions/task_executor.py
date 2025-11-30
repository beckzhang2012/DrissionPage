import threading
import time
import uuid
from typing import Callable, Optional, List, Dict, Any
from croniter import croniter
from datetime import datetime
import json
import os

class TaskExecutor:
    """任务执行器，支持立即执行和定时执行(cron表达式)"""
    
    def __init__(self, log_dir: str = "task_logs"):
        """初始化任务执行器
        :param log_dir: 日志目录，用于保存执行记录和详细日志
        """
        self.tasks: Dict[str, Task] = {}  # 任务字典，key为任务ID
        self.execution_records: List[Dict[str, Any]] = []  # 执行记录列表
        self.log_dir = log_dir
        self._stop_event = threading.Event()
        
        # 创建日志目录
        os.makedirs(log_dir, exist_ok=True)
        
        # 加载历史执行记录
        self._load_execution_records()
    
    def add_task(self, func: Callable, args: tuple = (), kwargs: dict = None,
                 task_name: str = None, cron_expr: str = None,
                 retry_times: int = 0, retry_interval: int = 1) -> str:
        """添加任务
        :param func: 任务函数
        :param args: 任务函数位置参数
        :param kwargs: 任务函数关键字参数
        :param task_name: 任务名称
        :param cron_expr: cron表达式，用于定时执行
        :param retry_times: 失败重试次数
        :param retry_interval: 重试间隔(秒)
        :return: 任务ID
        """
        if kwargs is None:
            kwargs = {}
        
        task_id = str(uuid.uuid4())
        task = Task(
            task_id=task_id,
            func=func,
            args=args,
            kwargs=kwargs,
            task_name=task_name or f"Task_{task_id[:8]}",
            cron_expr=cron_expr,
            retry_times=retry_times,
            retry_interval=retry_interval,
            log_dir=self.log_dir
        )
        
        self.tasks[task_id] = task
        return task_id
    
    def remove_task(self, task_id: str) -> bool:
        """移除任务
        :param task_id: 任务ID
        :return: 移除成功返回True，否则返回False
        """
        if task_id in self.tasks:
            del self.tasks[task_id]
            return True
        return False
    
    def start(self):
        """启动任务执行器"""
        self._stop_event.clear()
        # 启动定时任务检查线程
        threading.Thread(target=self._cron_check_thread, daemon=True).start()
    
    def stop(self):
        """停止任务执行器"""
        self._stop_event.set()
        # 停止所有任务
        for task in self.tasks.values():
            task.stop()
    
    def execute_task(self, task_id: str) -> Optional[Any]:
        """立即执行任务
        :param task_id: 任务ID
        :return: 任务执行结果，如果任务不存在返回None
        """
        if task_id not in self.tasks:
            return None
        
        task = self.tasks[task_id]
        result = task.execute()
        
        # 保存执行记录
        self._save_execution_record(task)
        
        return result
    
    def get_task_status(self, task_id: str) -> Optional[str]:
        """获取任务状态
        :param task_id: 任务ID
        :return: 任务状态，如果任务不存在返回None
        """
        if task_id not in self.tasks:
            return None
        return self.tasks[task_id].status
    
    def get_task_result(self, task_id: str) -> Optional[Any]:
        """获取任务执行结果
        :param task_id: 任务ID
        :return: 任务执行结果，如果任务不存在返回None
        """
        if task_id not in self.tasks:
            return None
        return self.tasks[task_id].result
    
    def get_task_log(self, task_id: str) -> Optional[str]:
        """获取任务执行日志
        :param task_id: 任务ID
        :return: 任务执行日志，如果任务不存在返回None
        """
        if task_id not in self.tasks:
            return None
        return self.tasks[task_id].log
    
    def get_execution_records(self, task_name: str = None, 
                               start_time: datetime = None, 
                               end_time: datetime = None, 
                               status: str = None) -> List[Dict[str, Any]]:
        """获取执行记录
        :param task_name: 任务名称筛选
        :param start_time: 开始时间筛选
        :param end_time: 结束时间筛选
        :param status: 执行状态筛选
        :return: 筛选后的执行记录列表
        """
        filtered = self.execution_records.copy()
        
        if task_name:
            filtered = [r for r in filtered if r['task_name'] == task_name]
        
        if start_time:
            filtered = [r for r in filtered if r['execution_time'] >= start_time]
        
        if end_time:
            filtered = [r for r in filtered if r['execution_time'] <= end_time]
        
        if status:
            filtered = [r for r in filtered if r['status'] == status]
        
        # 按执行时间倒序排列
        filtered.sort(key=lambda x: x['execution_time'], reverse=True)
        
        return filtered
    
    def get_execution_log(self, record_id: str) -> Optional[str]:
        """获取执行记录的详细日志
        :param record_id: 执行记录ID
        :return: 详细日志内容，如果记录不存在返回None
        """
        log_file = os.path.join(self.log_dir, f"{record_id}.log")
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                return f.read()
        return None
    
    def _cron_check_thread(self):
        """定时任务检查线程"""
        while not self._stop_event.is_set():
            current_time = datetime.now()
            
            for task in self.tasks.values():
                if task.cron_expr and task.status != "running":
                    if croniter(task.cron_expr, current_time).get_next(datetime) <= current_time:
                        # 启动任务线程
                        threading.Thread(target=self._execute_cron_task, args=(task,), daemon=True).start()
            
            time.sleep(1)  # 每秒检查一次
    
    def _execute_cron_task(self, task: 'Task'):
        """执行定时任务"""
        task.execute()
        self._save_execution_record(task)
    
    def _save_execution_record(self, task: 'Task'):
        """保存执行记录"""
        record = {
            'record_id': str(uuid.uuid4()),
            'task_id': task.task_id,
            'task_name': task.task_name,
            'execution_time': task.execution_time,
            'status': task.status,
            'execution_duration': task.execution_duration,
            'error_message': task.error_message,
            'retry_count': task.retry_count
        }
        
        self.execution_records.append(record)
        
        # 保存到文件
        self._save_records_to_file()
        
        # 保存详细日志到文件
        log_file = os.path.join(self.log_dir, f"{record['record_id']}.log")
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(task.log)
    
    def _load_execution_records(self):
        """加载历史执行记录"""
        records_file = os.path.join(self.log_dir, "execution_records.json")
        if os.path.exists(records_file):
            with open(records_file, 'r', encoding='utf-8') as f:
                try:
                    records = json.load(f)
                    # 转换字符串时间为datetime对象
                    for record in records:
                        record['execution_time'] = datetime.fromisoformat(record['execution_time'])
                    self.execution_records = records
                except (json.JSONDecodeError, KeyError):
                    self.execution_records = []
    
    def _save_records_to_file(self):
        """保存执行记录到文件"""
        records_file = os.path.join(self.log_dir, "execution_records.json")
        # 转换datetime对象为字符串
        records_to_save = []
        for record in self.execution_records:
            record_copy = record.copy()
            record_copy['execution_time'] = record_copy['execution_time'].isoformat()
            records_to_save.append(record_copy)
        
        with open(records_file, 'w', encoding='utf-8') as f:
            json.dump(records_to_save, f, ensure_ascii=False, indent=2)


class Task:
    """任务类，封装任务的所有信息和执行逻辑"""
    
    def __init__(self, task_id: str, func: Callable, args: tuple, kwargs: dict,
                 task_name: str, cron_expr: str = None,
                 retry_times: int = 0, retry_interval: int = 1,
                 log_dir: str = "task_logs"):
        """初始化任务
        :param task_id: 任务ID
        :param func: 任务函数
        :param args: 任务函数位置参数
        :param kwargs: 任务函数关键字参数
        :param task_name: 任务名称
        :param cron_expr: cron表达式，用于定时执行
        :param retry_times: 失败重试次数
        :param retry_interval: 重试间隔(秒)
        :param log_dir: 日志目录
        """
        self.task_id = task_id
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.task_name = task_name
        self.cron_expr = cron_expr
        self.retry_times = retry_times
        self.retry_interval = retry_interval
        self.log_dir = log_dir
        
        # 任务状态
        self.status: str = "waiting"  # waiting, running, completed, failed
        self.result: Any = None
        self.error_message: str = ""
        self.execution_time: datetime = None
        self.execution_duration: float = 0.0
        self.retry_count: int = 0
        self.log: str = ""
        
        self._stop_event = threading.Event()
    
    def execute(self) -> Any:
        """执行任务"""
        self.status = "running"
        self.execution_time = datetime.now()
        start_time = time.time()
        self.log = f"任务开始执行: {self.execution_time}\n"
        
        retry_count = 0
        while retry_count <= self.retry_times:
            try:
                self.log += f"第 {retry_count + 1} 次执行...\n"
                self.result = self.func(*self.args, **self.kwargs)
                self.execution_duration = time.time() - start_time
                self.status = "completed"
                self.log += f"任务执行成功，耗时: {self.execution_duration:.2f} 秒\n"
                self.retry_count = retry_count
                break
            except Exception as e:
                self.error_message = str(e)
                self.log += f"任务执行失败: {e}\n"
                
                if retry_count < self.retry_times:
                    self.log += f"将在 {self.retry_interval} 秒后重试...\n"
                    time.sleep(self.retry_interval)
                    retry_count += 1
                else:
                    self.execution_duration = time.time() - start_time
                    self.status = "failed"
                    self.retry_count = retry_count
                    break
        
        return self.result
    
    def stop(self):
        """停止任务"""
        self._stop_event.set()
    
    def __str__(self):
        return f"Task(id={self.task_id}, name={self.task_name}, status={self.status})"
    
    def __repr__(self):
        return self.__str__()