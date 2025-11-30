import datetime
from typing import Dict, Any, Optional

class Task:
    """任务对象"""
    
    def __init__(self, task_id: int, name: str, script_path: str, 
                 script_params: Dict[str, Any] = None, description: str = None, 
                 cron_expression: str = None, enabled: bool = True, 
                 max_retry: int = 3, retry_interval: int = 60, 
                 timeout: int = 3600, created_at: datetime.datetime = None, 
                 updated_at: datetime.datetime = None):
        """
        初始化任务对象
        :param task_id: 任务ID
        :param name: 任务名称
        :param script_path: 脚本路径
        :param script_params: 脚本参数
        :param description: 任务描述
        :param cron_expression: cron表达式
        :param enabled: 是否启用
        :param max_retry: 最大重试次数
        :param retry_interval: 重试间隔（秒）
        :param timeout: 任务超时时间（秒）
        :param created_at: 创建时间
        :param updated_at: 更新时间
        """
        self.id = task_id
        self.name = name
        self.script_path = script_path
        self.script_params = script_params or {}
        self.description = description or ''
        self.cron_expression = cron_expression
        self.enabled = enabled
        self.max_retry = max_retry
        self.retry_interval = retry_interval
        self.timeout = timeout
        self.created_at = created_at or datetime.datetime.now()
        self.updated_at = updated_at or datetime.datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'script_path': self.script_path,
            'script_params': self.script_params,
            'description': self.description,
            'cron_expression': self.cron_expression,
            'enabled': self.enabled,
            'max_retry': self.max_retry,
            'retry_interval': self.retry_interval,
            'timeout': self.timeout,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Task':
        """从字典创建任务对象"""
        return cls(
            task_id=data['id'],
            name=data['name'],
            script_path=data['script_path'],
            script_params=data.get('script_params', {}),
            description=data.get('description', ''),
            cron_expression=data.get('cron_expression'),
            enabled=data.get('enabled', True),
            max_retry=data.get('max_retry', 3),
            retry_interval=data.get('retry_interval', 60),
            timeout=data.get('timeout', 3600),
            created_at=datetime.datetime.strptime(data['created_at'], '%Y-%m-%d %H:%M:%S') if data.get('created_at') else None,
            updated_at=datetime.datetime.strptime(data['updated_at'], '%Y-%m-%d %H:%M:%S') if data.get('updated_at') else None
        )
    
    def __repr__(self) -> str:
        return f'<Task {self.id} {self.name}>'


class TaskExecution:
    """任务执行记录"""
    
    STATUS_WAITING = 'waiting'  # 等待中
    STATUS_RUNNING = 'running'  # 执行中
    STATUS_COMPLETED = 'completed'  # 已完成
    STATUS_FAILED = 'failed'  # 失败
    STATUS_CANCELED = 'canceled'  # 已取消
    
    def __init__(self, execution_id: int, task_id: int, task_name: str, 
                 status: str = STATUS_WAITING, start_time: datetime.datetime = None, 
                 end_time: datetime.datetime = None, duration: float = None, 
                 result: Dict[str, Any] = None, error_message: str = None, 
                 log_file_path: str = None, retry_count: int = 0, 
                 created_at: datetime.datetime = None):
        """
        初始化任务执行记录
        :param execution_id: 执行ID
        :param task_id: 任务ID
        :param task_name: 任务名称
        :param status: 执行状态
        :param start_time: 开始时间
        :param end_time: 结束时间
        :param duration: 执行时长（秒）
        :param result: 执行结果
        :param error_message: 错误信息
        :param log_file_path: 日志文件路径
        :param retry_count: 重试次数
        :param created_at: 创建时间
        """
        self.id = execution_id
        self.task_id = task_id
        self.task_name = task_name
        self.status = status
        self.start_time = start_time
        self.end_time = end_time
        self.duration = duration
        self.result = result or {}
        self.error_message = error_message
        self.log_file_path = log_file_path
        self.retry_count = retry_count
        self.created_at = created_at or datetime.datetime.now()
    
    def start(self):
        """开始执行"""
        self.status = self.STATUS_RUNNING
        self.start_time = datetime.datetime.now()
    
    def complete(self, result: Dict[str, Any] = None):
        """执行完成"""
        self.status = self.STATUS_COMPLETED
        self.end_time = datetime.datetime.now()
        self.duration = (self.end_time - self.start_time).total_seconds() if self.start_time else None
        self.result = result or {}
    
    def fail(self, error_message: str):
        """执行失败"""
        self.status = self.STATUS_FAILED
        self.end_time = datetime.datetime.now()
        self.duration = (self.end_time - self.start_time).total_seconds() if self.start_time else None
        self.error_message = error_message
    
    def cancel(self):
        """取消执行"""
        self.status = self.STATUS_CANCELED
        self.end_time = datetime.datetime.now()
        self.duration = (self.end_time - self.start_time).total_seconds() if self.start_time else None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'task_id': self.task_id,
            'task_name': self.task_name,
            'status': self.status,
            'start_time': self.start_time.strftime('%Y-%m-%d %H:%M:%S') if self.start_time else None,
            'end_time': self.end_time.strftime('%Y-%m-%d %H:%M:%S') if self.end_time else None,
            'duration': self.duration,
            'result': self.result,
            'error_message': self.error_message,
            'log_file_path': self.log_file_path,
            'retry_count': self.retry_count,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskExecution':
        """从字典创建任务执行记录"""
        return cls(
            execution_id=data['id'],
            task_id=data['task_id'],
            task_name=data['task_name'],
            status=data.get('status', cls.STATUS_WAITING),
            start_time=datetime.datetime.strptime(data['start_time'], '%Y-%m-%d %H:%M:%S') if data.get('start_time') else None,
            end_time=datetime.datetime.strptime(data['end_time'], '%Y-%m-%d %H:%M:%S') if data.get('end_time') else None,
            duration=data.get('duration'),
            result=data.get('result', {}),
            error_message=data.get('error_message'),
            log_file_path=data.get('log_file_path'),
            retry_count=data.get('retry_count', 0),
            created_at=datetime.datetime.strptime(data['created_at'], '%Y-%m-%d %H:%M:%S') if data.get('created_at') else None
        )
    
    def __repr__(self) -> str:
        return f'<TaskExecution {self.id} Task {self.task_id} {self.status}>'