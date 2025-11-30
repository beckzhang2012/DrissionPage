import threading
import time
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from .task import Task, TaskExecution, ExecutionHistory
from .cron_parser import CronParser
from .executor import TaskExecutor


class TaskScheduler:
    """任务调度器"""
    def __init__(self, tasks_file: str = 'tasks.json', log_dir: str = 'logs', history_dir: str = 'executions'):
        self.tasks_file = tasks_file
        self.tasks: Dict[str, Task] = {}  # task_id -> Task
        self.executor = TaskExecutor(log_dir=log_dir)
        self.history = ExecutionHistory(history_dir=history_dir)
        self.is_running = False
        self.scheduler_thread: Optional[threading.Thread] = None

        # 加载任务
        self.load_tasks()

    def load_tasks(self):
        """从文件加载任务"""
        if os.path.exists(self.tasks_file):
            try:
                with open(self.tasks_file, 'r', encoding='utf-8') as f:
                    tasks_data = json.load(f)
                for task_data in tasks_data:
                    task = Task.from_dict(task_data)
                    self.tasks[task.task_id] = task
                print(f"Loaded {len(self.tasks)} tasks from {self.tasks_file}")
            except Exception as e:
                print(f"Failed to load tasks from {self.tasks_file}: {e}")
        else:
            print(f"Tasks file {self.tasks_file} not found. No tasks loaded.")

    def save_tasks(self):
        """保存任务到文件"""
        tasks_data = [task.to_dict() for task in self.tasks.values()]
        with open(self.tasks_file, 'w', encoding='utf-8') as f:
            json.dump(tasks_data, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(self.tasks)} tasks to {self.tasks_file}")

    def add_task(self, task: Task):
        """添加任务"""
        self.tasks[task.task_id] = task
        self.save_tasks()
        print(f"Added task: {task.name} (ID: {task.task_id})")

    def remove_task(self, task_id: str):
        """移除任务"""
        if task_id in self.tasks:
            task_name = self.tasks[task_id].name
            del self.tasks[task_id]
            self.save_tasks()
            print(f"Removed task: {task_name} (ID: {task_id})")
        else:
            print(f"Task not found: {task_id}")

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[Task]:
        """获取所有任务"""
        return list(self.tasks.values())

    def execute_task_immediately(self, task_id: str) -> Optional[TaskExecution]:
        """立即执行任务"""
        task = self.get_task(task_id)
        if task:
            execution = self.executor.execute_immediately(task)
            # 保存执行记录
            self.history.save_execution(execution)
            return execution
        else:
            print(f"Task not found: {task_id}")
            return None

    def _scheduler_loop(self):
        """调度器循环"""
        print("Scheduler started")
        while self.is_running:
            current_time = datetime.now()
            
            # 检查所有定时任务
            for task in self.tasks.values():
                if task.cron_expr:
                    try:
                        parser = CronParser(task.cron_expr)
                        if parser.is_due(current_time):
                            # 检查是否已经执行过
                            # 这里可以添加逻辑避免重复执行
                            print(f"Task is due: {task.name} (ID: {task.task_id})")
                            execution = self.executor.execute_immediately(task)
                            self.history.save_execution(execution)
                    except Exception as e:
                        print(f"Error processing task {task.name}: {e}")
            
            # 等待1分钟
            time.sleep(60)
        print("Scheduler stopped")

    def start(self):
        """启动调度器"""
        if not self.is_running:
            self.is_running = True
            self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self.scheduler_thread.start()
            print("Scheduler started")
        else:
            print("Scheduler is already running")

    def stop(self):
        """停止调度器"""
        if self.is_running:
            self.is_running = False
            if self.scheduler_thread:
                self.scheduler_thread.join()
            print("Scheduler stopped")
        else:
            print("Scheduler is not running")

    def get_execution_history(self, task_name: str = None, status: str = None,
                             start_time_from: datetime = None, start_time_to: datetime = None) -> List[TaskExecution]:
        """获取执行历史记录"""
        return self.history.filter_executions(task_name, status, start_time_from, start_time_to)

    def get_execution_detail(self, execution_id: str) -> Optional[TaskExecution]:
        """获取执行记录详情"""
        return self.history.get_execution(execution_id)

    def get_execution_log(self, execution_id: str) -> Optional[str]:
        """获取执行日志"""
        return self.history.get_execution_log(execution_id)


# 测试代码
if __name__ == "__main__":
    # 创建调度器
    scheduler = TaskScheduler()

    # 创建测试任务1：立即执行
    task1 = Task(
        task_id="task_1",
        name="Test Task 1",
        script_path="test_script.py",
        params={"arg1": "value1", "arg2": "value2"},
        max_retries=2,
        retry_interval=10
    )

    # 创建测试任务2：定时执行（每分钟）
    task2 = Task(
        task_id="task_2",
        name="Test Task 2",
        script_path="test_script.py",
        params={"arg1": "value3", "arg2": "value4"},
        cron_expr="* * * * *",
        max_retries=1,
        retry_interval=5
    )

    # 添加任务
    scheduler.add_task(task1)
    scheduler.add_task(task2)

    # 立即执行任务1
    print("Executing task 1 immediately...")
    execution1 = scheduler.execute_task_immediately("task_1")
    print(f"Task 1 execution status: {execution1.status}")

    # 启动调度器
    print("Starting scheduler...")
    scheduler.start()

    # 运行5分钟
    print("Running for 5 minutes...")
    time.sleep(300)

    # 停止调度器
    print("Stopping scheduler...")
    scheduler.stop()

    # 打印执行历史
    print("\nExecution history:")
    history = scheduler.get_execution_history()
    for execution in history:
        print(f"- {execution.task_name} ({execution.status}) at {execution.start_time}")
