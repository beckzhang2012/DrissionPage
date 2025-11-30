import json
import os
from datetime import datetime
from typing import Dict, Any, Optional


class Task:
    """任务类，定义任务的基本属性和方法"""
    def __init__(self, task_id: str, name: str, script_path: str, params: Dict[str, Any] = None,
                 cron_expr: str = None, max_retries: int = 0, retry_interval: int = 60):
        self.task_id = task_id
        self.name = name
        self.script_path = script_path
        self.params = params or {}
        self.cron_expr = cron_expr
        self.max_retries = max_retries
        self.retry_interval = retry_interval

    def to_dict(self) -> Dict[str, Any]:
        """将任务对象转换为字典"""
        return {
            'task_id': self.task_id,
            'name': self.name,
            'script_path': self.script_path,
            'params': self.params,
            'cron_expr': self.cron_expr,
            'max_retries': self.max_retries,
            'retry_interval': self.retry_interval
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Task':
        """从字典创建任务对象"""
        return cls(
            task_id=data['task_id'],
            name=data['name'],
            script_path=data['script_path'],
            params=data.get('params', {}),
            cron_expr=data.get('cron_expr'),
            max_retries=data.get('max_retries', 0),
            retry_interval=data.get('retry_interval', 60)
        )


class TaskExecution:
    """任务执行记录类，记录任务执行的详细信息"""
    STATUS_WAITING = 'waiting'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'

    def __init__(self, execution_id: str, task_id: str, task_name: str):
        self.execution_id = execution_id
        self.task_id = task_id
        self.task_name = task_name
        self.status = self.STATUS_WAITING
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.duration: Optional[int] = None  # 秒
        self.result: Any = None
        self.error_message: Optional[str] = None
        self.retry_count = 0
        self.log_path: Optional[str] = None

    def start(self):
        """标记任务开始执行"""
        self.status = self.STATUS_RUNNING
        self.start_time = datetime.now()

    def complete(self, result: Any = None):
        """标记任务执行完成"""
        self.status = self.STATUS_COMPLETED
        self.end_time = datetime.now()
        self.result = result
        if self.start_time:
            self.duration = int((self.end_time - self.start_time).total_seconds())

    def fail(self, error_message: str):
        """标记任务执行失败"""
        self.status = self.STATUS_FAILED
        self.end_time = datetime.now()
        self.error_message = error_message
        if self.start_time:
            self.duration = int((self.end_time - self.start_time).total_seconds())

    def cancel(self):
        """标记任务执行取消"""
        self.status = self.STATUS_CANCELLED
        self.end_time = datetime.now()
        if self.start_time:
            self.duration = int((self.end_time - self.start_time).total_seconds())

    def to_dict(self) -> Dict[str, Any]:
        """将执行记录转换为字典"""
        return {
            'execution_id': self.execution_id,
            'task_id': self.task_id,
            'task_name': self.task_name,
            'status': self.status,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration': self.duration,
            'result': self.result,
            'error_message': self.error_message,
            'retry_count': self.retry_count,
            'log_path': self.log_path
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskExecution':
        """从字典创建执行记录对象"""
        execution = cls(
            execution_id=data['execution_id'],
            task_id=data['task_id'],
            task_name=data['task_name']
        )
        execution.status = data['status']
        execution.start_time = datetime.fromisoformat(data['start_time']) if data['start_time'] else None
        execution.end_time = datetime.fromisoformat(data['end_time']) if data['end_time'] else None
        execution.duration = data['duration']
        execution.result = data['result']
        execution.error_message = data['error_message']
        execution.retry_count = data['retry_count']
        execution.log_path = data['log_path']
        return execution

    def save_to_file(self, directory: str):
        """将执行记录保存到文件"""
        if not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        file_path = os.path.join(directory, f"{self.execution_id}.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2, default=str)

    @classmethod
    def load_from_file(cls, file_path: str) -> 'TaskExecution':
        """从文件加载执行记录"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)


class ExecutionHistory:
    """执行历史记录管理类"""
    def __init__(self, history_dir: str = 'executions'):
        self.history_dir = history_dir
        if not os.path.exists(self.history_dir):
            os.makedirs(self.history_dir, exist_ok=True)

    def save_execution(self, execution: TaskExecution):
        """保存执行记录"""
        execution.save_to_file(self.history_dir)

    def get_execution(self, execution_id: str) -> Optional[TaskExecution]:
        """根据执行ID获取执行记录"""
        file_path = os.path.join(self.history_dir, f"{execution_id}.json")
        if os.path.exists(file_path):
            return TaskExecution.load_from_file(file_path)
        return None

    def get_all_executions(self) -> list[TaskExecution]:
        """获取所有执行记录"""
        executions = []
        if os.path.exists(self.history_dir):
            for filename in os.listdir(self.history_dir):
                if filename.endswith('.json'):
                    file_path = os.path.join(self.history_dir, filename)
                    try:
                        execution = TaskExecution.load_from_file(file_path)
                        executions.append(execution)
                    except Exception as e:
                        print(f"Failed to load execution from {file_path}: {e}")
        # 按开始时间排序
        executions.sort(key=lambda x: x.start_time or datetime.min, reverse=True)
        return executions

    def filter_executions(self, task_name: str = None, status: str = None,
                         start_time_from: datetime = None, start_time_to: datetime = None) -> list[TaskExecution]:
        """筛选执行记录"""
        all_executions = self.get_all_executions()
        filtered = all_executions

        if task_name:
            filtered = [e for e in filtered if e.task_name == task_name]

        if status:
            filtered = [e for e in filtered if e.status == status]

        if start_time_from:
            filtered = [e for e in filtered if e.start_time and e.start_time >= start_time_from]

        if start_time_to:
            filtered = [e for e in filtered if e.start_time and e.start_time <= start_time_to]

        return filtered

    def get_execution_log(self, execution_id: str) -> Optional[str]:
        """获取执行记录的日志内容"""
        execution = self.get_execution(execution_id)
        if execution and execution.log_path and os.path.exists(execution.log_path):
            try:
                with open(execution.log_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                print(f"Failed to read log file {execution.log_path}: {e}")
        return None

    def delete_execution(self, execution_id: str) -> bool:
        """删除执行记录"""
        file_path = os.path.join(self.history_dir, f"{execution_id}.json")
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                return True
            except Exception as e:
                print(f"Failed to delete execution {execution_id}: {e}")
        return False

    def delete_old_executions(self, days: int = 30):
        """删除指定天数前的执行记录"""
        cutoff_time = datetime.now() - timedelta(days=days)
        for execution in self.get_all_executions():
            if execution.start_time and execution.start_time < cutoff_time:
                self.delete_execution(execution.execution_id)
