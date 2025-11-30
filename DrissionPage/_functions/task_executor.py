# -*- coding:utf-8 -*-
"""
@Author   : g1879
@Contact  : g1879@qq.com
@Website  : https://DrissionPage.cn
@Copyright: (c) 2020 by g1879, Inc. All Rights Reserved.
"""
import time
import threading
from typing import Callable, Optional, Dict, Any
from croniter import croniter
from datetime import datetime


class TaskExecutor:
    """任务执行器类，支持立即执行和定时执行任务"""
    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def add_task(self, name: str, func: Callable, args: tuple = (), kwargs: dict = None,
                 cron_expr: str = None, retry_times: int = 0, retry_interval: int = 1):
        """添加任务
        :param name: 任务名称
        :param func: 任务函数
        :param args: 任务函数参数
        :param kwargs: 任务函数关键字参数
        :param cron_expr: cron表达式，用于定时执行任务
        :param retry_times: 任务失败时重试次数
        :param retry_interval: 任务失败时重试间隔（秒）
        """
        if kwargs is None:
            kwargs = {}

        task = Task(name, func, args, kwargs, cron_expr, retry_times, retry_interval)
        self.tasks[name] = task

    def remove_task(self, name: str):
        """移除任务
        :param name: 任务名称
        """
        if name in self.tasks:
            del self.tasks[name]

    def run_task(self, name: str):
        """立即执行指定任务
        :param name: 任务名称
        """
        if name in self.tasks:
            task = self.tasks[name]
            threading.Thread(target=self._execute_task, args=(task,), daemon=True).start()

    def start(self):
        """启动任务执行器，开始处理定时任务"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run_loop, daemon=True)
            self.thread.start()

    def stop(self):
        """停止任务执行器"""
        self.running = False
        if self.thread:
            self.thread.join()

    def get_task_status(self, name: str) -> Optional[str]:
        """获取任务状态
        :param name: 任务名称
        :return: 任务状态（等待中、执行中、已完成、失败）
        """
        if name in self.tasks:
            return self.tasks[name].status
        return None

    def get_task_result(self, name: str) -> Any:
        """获取任务执行结果
        :param name: 任务名称
        :return: 任务执行结果
        """
        if name in self.tasks:
            return self.tasks[name].result
        return None

    def get_task_logs(self, name: str) -> list:
        """获取任务执行日志
        :param name: 任务名称
        :return: 任务执行日志列表
        """
        if name in self.tasks:
            return self.tasks[name].logs
        return []

    def _run_loop(self):
        """任务执行器主循环，处理定时任务"""
        while self.running:
            now = datetime.now()
            for task in self.tasks.values():
                if task.cron_expr and not task.is_running:
                    if croniter(task.cron_expr, now).get_next(datetime) <= now:
                        threading.Thread(target=self._execute_task, args=(task,), daemon=True).start()
            time.sleep(1)

    def _execute_task(self, task: 'Task'):
        """执行任务
        :param task: 任务对象
        """
        task.status = '执行中'
        task.logs.append(f'任务开始执行: {datetime.now()}')

        retry_count = 0
        while retry_count <= task.retry_times:
            try:
                result = task.func(*task.args, **task.kwargs)
                task.result = result
                task.status = '已完成'
                task.logs.append(f'任务执行成功: {datetime.now()}')
                break

            except Exception as e:
                task.logs.append(f'任务执行失败 (第 {retry_count + 1} 次): {str(e)} - {datetime.now()}')
                retry_count += 1

                if retry_count <= task.retry_times:
                    time.sleep(task.retry_interval)
                else:
                    task.status = '失败'
                    task.logs.append(f'任务执行最终失败: {datetime.now()}')


class Task:
    """任务类，封装任务的相关信息和状态"""
    def __init__(self, name: str, func: Callable, args: tuple = (), kwargs: dict = None,
                 cron_expr: str = None, retry_times: int = 0, retry_interval: int = 1):
        self.name = name
        self.func = func
        self.args = args
        self.kwargs = kwargs or {}
        self.cron_expr = cron_expr
        self.retry_times = retry_times
        self.retry_interval = retry_interval

        self.status = '等待中'
        self.result = None
        self.logs = []

    @property
    def is_running(self) -> bool:
        """返回任务是否正在执行"""
        return self.status == '执行中'
