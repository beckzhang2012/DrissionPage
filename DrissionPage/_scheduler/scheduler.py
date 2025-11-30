import threading
import time
import datetime
import json
import os
from typing import Dict, List, Optional
from .task import Task, TaskExecution
from .cron_parser import CronParser
from .executor import TaskExecutor

class TaskScheduler:
    """任务调度器"""
    
    def __init__(self, tasks_file: str = 'tasks.json', executions_dir: str = 'executions', log_dir: str = 'logs'):
        """
        初始化任务调度器
        :param tasks_file: 任务配置文件路径
        :param executions_dir: 执行记录目录
        :param log_dir: 日志文件目录
        """
        self.tasks_file = tasks_file
        self.executions_dir = executions_dir
        self.log_dir = log_dir
        
        # 创建必要的目录
        os.makedirs(executions_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)
        
        # 任务列表
        self.tasks: Dict[int, Task] = {}
        # 执行记录
        self.executions: Dict[int, TaskExecution] = {}
        # 调度线程
        self.scheduler_thread: Optional[threading.Thread] = None
        # 停止标志
        self.stop_flag = threading.Event()
        # 任务执行器
        self.executor = TaskExecutor(log_dir)
        
        # 加载任务配置
        self._load_tasks()
        # 加载执行记录
        self._load_executions()
    
    def _load_tasks(self):
        """加载任务配置"""
        if os.path.exists(self.tasks_file):
            with open(self.tasks_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for task_data in data.get('tasks', []):
                    task = Task.from_dict(task_data)
                    self.tasks[task.id] = task
    
    def _save_tasks(self):
        """保存任务配置"""
        data = {
            'tasks': [task.to_dict() for task in self.tasks.values()],
            'next_id': max(self.tasks.keys()) + 1 if self.tasks else 1
        }
        with open(self.tasks_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _load_executions(self):
        """加载执行记录"""
        if os.path.exists(self.executions_dir):
            for filename in os.listdir(self.executions_dir):
                if filename.endswith('.json'):
                    file_path = os.path.join(self.executions_dir, filename)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        execution = TaskExecution.from_dict(data)
                        self.executions[execution.id] = execution
    
    def _save_execution(self, execution: TaskExecution):
        """保存执行记录"""
        filename = f'task_{execution.task_id}_exec_{execution.id}.json'
        file_path = os.path.join(self.executions_dir, filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(execution.to_dict(), f, ensure_ascii=False, indent=2)
    
    def add_task(self, task: Task):
        """添加任务"""
        self.tasks[task.id] = task
        self._save_tasks()
    
    def remove_task(self, task_id: int):
        """删除任务"""
        if task_id in self.tasks:
            del self.tasks[task_id]
            self._save_tasks()
    
    def update_task(self, task: Task):
        """更新任务"""
        if task.id in self.tasks:
            self.tasks[task.id] = task
            self._save_tasks()
    
    def get_task(self, task_id: int) -> Optional[Task]:
        """获取任务"""
        return self.tasks.get(task_id)
    
    def get_all_tasks(self) -> List[Task]:
        """获取所有任务"""
        return list(self.tasks.values())
    
    def get_execution(self, execution_id: int) -> Optional[TaskExecution]:
        """获取执行记录"""
        return self.executions.get(execution_id)
    
    def get_executions_by_task(self, task_id: int) -> List[TaskExecution]:
        """获取任务的所有执行记录"""
        return [execution for execution in self.executions.values() if execution.task_id == task_id]
    
    def get_all_executions(self) -> List[TaskExecution]:
        """获取所有执行记录"""
        return list(self.executions.values())
    
    def execute_task_immediately(self, task_id: int) -> TaskExecution:
        """立即执行任务"""
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        
        # 生成执行ID
        execution_id = max(self.executions.keys()) + 1 if self.executions else 1
        
        # 执行任务
        execution = self.executor.execute_task(task, execution_id)
        
        # 保存执行记录
        self.executions[execution.id] = execution
        self._save_execution(execution)
        
        return execution
    
    def _scheduler_loop(self):
        """调度器循环"""
        while not self.stop_flag.is_set():
            current_time = datetime.datetime.now()
            
            # 检查所有启用的定时任务
            for task in self.tasks.values():
                if task.enabled and task.cron_expression:
                    try:
                        # 解析cron表达式
                        cron_parser = CronParser(task.cron_expression)
                        # 计算下一次执行时间
                        next_run_time = cron_parser.get_next_run_time(current_time - datetime.timedelta(minutes=1))
                        
                        # 如果下一次执行时间在当前时间的1分钟内
                        if abs((next_run_time - current_time).total_seconds()) < 60:
                            # 执行任务
                            execution_id = max(self.executions.keys()) + 1 if self.executions else 1
                            execution = self.executor.execute_task(task, execution_id)
                            
                            # 保存执行记录
                            self.executions[execution.id] = execution
                            self._save_execution(execution)
                    except Exception as e:
                        print(f"调度任务 {task.id} 时出错: {str(e)}")
            
            # 等待1分钟后再次检查
            time.sleep(60)
    
    def start(self):
        """启动调度器"""
        if not self.scheduler_thread or not self.scheduler_thread.is_alive():
            self.stop_flag.clear()
            self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self.scheduler_thread.start()
    
    def stop(self):
        """停止调度器"""
        self.stop_flag.set()
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join()
    
    def __repr__(self) -> str:
        return f'<TaskScheduler tasks={len(self.tasks)} executions={len(self.executions)}>'


# 测试代码
if __name__ == '__main__':
    # 创建调度器
    scheduler = TaskScheduler()
    
    # 创建测试任务
    task1 = Task(
        task_id=1,
        name="每日数据采集",
        script_path="scripts/daily_collect.py",
        script_params={"param1": "value1", "param2": "value2"},
        cron_expression="0 9 * * *",
        enabled=True
    )
    
    task2 = Task(
        task_id=2,
        name="每小时清理缓存",
        script_path="scripts/clean_cache.py",
        script_params={"keep_days": 7},
        cron_expression="0 * * * *",
        enabled=True
    )
    
    # 添加任务
    scheduler.add_task(task1)
    scheduler.add_task(task2)
    
    # 立即执行任务1
    print("立即执行任务1...")
    execution1 = scheduler.execute_task_immediately(1)
    print(f"任务1执行结果: {execution1.status}")
    
    # 启动调度器
    print("启动调度器...")
    scheduler.start()
    
    # 运行一段时间后停止
    time.sleep(120)
    print("停止调度器...")
    scheduler.stop()
    
    # 打印所有执行记录
    print("所有执行记录:")
    for execution in scheduler.get_all_executions():
        print(f"  {execution}")