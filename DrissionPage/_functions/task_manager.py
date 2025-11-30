# -*- coding:utf-8 -*-
"""
@Author   : g1879
@Contact  : g1879@qq.com
@Website  : https://DrissionPage.cn
@Copyright: (c) 2020 by g1879, Inc. All Rights Reserved.
"""
import json
from pathlib import Path
from typing import List, Dict, Optional


class Task:
    """任务类，用于表示一个自动化任务"""
    def __init__(self, task_id: str, name: str, script_path: str, args: str = '', description: str = '', enabled: bool = True):
        self.task_id = task_id
        self.name = name
        self.script_path = script_path
        self.args = args
        self.description = description
        self.enabled = enabled

    def to_dict(self) -> Dict:
        """将任务转换为字典"""
        return {
            'task_id': self.task_id,
            'name': self.name,
            'script_path': self.script_path,
            'args': self.args,
            'description': self.description,
            'enabled': self.enabled
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Task':
        """从字典创建任务"""
        return cls(
            task_id=data.get('task_id', ''),
            name=data.get('name', ''),
            script_path=data.get('script_path', ''),
            args=data.get('args', ''),
            description=data.get('description', ''),
            enabled=data.get('enabled', True)
        )


class TaskManager:
    """任务管理器，用于管理自动化任务的配置和执行"""
    def __init__(self, config_path: str = 'tasks.json'):
        self.config_path = Path(config_path)
        self.tasks: Dict[str, Task] = {}
        self.load_tasks()

    def load_tasks(self) -> None:
        """从配置文件加载任务"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    tasks_data = json.load(f)
                    for task_data in tasks_data:
                        task = Task.from_dict(task_data)
                        self.tasks[task.task_id] = task
            except json.JSONDecodeError:
                print('任务配置文件格式错误，已忽略。')
            except Exception as e:
                print(f'加载任务配置失败：{e}')

    def save_tasks(self) -> None:
        """保存任务到配置文件"""
        try:
            tasks_data = [task.to_dict() for task in self.tasks.values()]
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(tasks_data, f, indent=2, ensure_ascii=False)
            print(f'任务配置已保存到：{self.config_path}')
        except Exception as e:
            print(f'保存任务配置失败：{e}')

    def add_task(self, name: str, script_path: str, args: str = '', description: str = '', enabled: bool = True) -> Optional[Task]:
        """添加新任务"""
        try:
            # 生成唯一的任务ID
            task_id = f'task_{len(self.tasks) + 1}'
            while task_id in self.tasks:
                task_id = f'task_{len(self.tasks) + 1}'

            # 检查脚本路径是否存在
            if not Path(script_path).exists():
                print(f'警告：脚本路径 {script_path} 不存在。')

            task = Task(task_id, name, script_path, args, description, enabled)
            self.tasks[task_id] = task
            self.save_tasks()
            return task
        except Exception as e:
            print(f'添加任务失败：{e}')
            return None

    def get_task(self, task_id: str) -> Optional[Task]:
        """根据任务ID获取任务"""
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[Task]:
        """获取所有任务"""
        return list(self.tasks.values())

    def update_task(self, task_id: str, **kwargs) -> Optional[Task]:
        """更新任务信息"""
        if task_id not in self.tasks:
            print(f'任务 {task_id} 不存在。')
            return None

        task = self.tasks[task_id]
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)

        self.save_tasks()
        return task

    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        if task_id not in self.tasks:
            print(f'任务 {task_id} 不存在。')
            return False

        del self.tasks[task_id]
        self.save_tasks()
        return True

    def toggle_task(self, task_id: str) -> Optional[Task]:
        """切换任务的启用/禁用状态"""
        if task_id not in self.tasks:
            print(f'任务 {task_id} 不存在。')
            return None

        task = self.tasks[task_id]
        task.enabled = not task.enabled
        self.save_tasks()
        return task

    def list_tasks(self) -> None:
        """列出所有任务"""
        if not self.tasks:
            print('没有任务。')
            return

        print('任务列表：')
        print(f'{"ID":<10} {"名称":<20} {"脚本路径":<30} {"状态":<8} {"描述"}')
        print('-' * 80)
        for task in self.tasks.values():
            status = '启用' if task.enabled else '禁用'
            print(f'{task.task_id:<10} {task.name:<20} {task.script_path:<30} {status:<8} {task.description}')

    def run_task(self, task_id: str) -> bool:
        """运行指定任务"""
        task = self.get_task(task_id)
        if not task:
            print(f'任务 {task_id} 不存在。')
            return False

        if not task.enabled:
            print(f'任务 {task_id} 已禁用。')
            return False

        try:
            import subprocess
            import sys

            # 构建命令行参数
            cmd = [sys.executable, task.script_path]
            if task.args:
                cmd.extend(task.args.split())

            print(f'正在运行任务：{task.name} ({task_id})')
            print(f'命令：{" ".join(cmd)}')

            # 执行任务
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f'任务执行成功：{task.name} ({task_id})')
            if result.stdout:
                print(f'输出：{result.stdout}')
            return True
        except subprocess.CalledProcessError as e:
            print(f'任务执行失败：{task.name} ({task_id})')
            print(f'错误代码：{e.returncode}')
            if e.stderr:
                print(f'错误信息：{e.stderr}')
            return False
        except Exception as e:
            print(f'任务执行出错：{task.name} ({task_id})')
            print(f'错误信息：{e}')
            return False

    def run_all_enabled_tasks(self) -> None:
        """运行所有已启用的任务"""
        enabled_tasks = [task for task in self.tasks.values() if task.enabled]
        if not enabled_tasks:
            print('没有已启用的任务。')
            return

        print(f'找到 {len(enabled_tasks)} 个已启用的任务，开始执行...')
        for task in enabled_tasks:
            print(f'\n正在运行任务：{task.name} ({task.task_id})')
            self.run_task(task.task_id)