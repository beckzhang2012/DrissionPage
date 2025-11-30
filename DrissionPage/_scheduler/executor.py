import subprocess
import sys
import time
import datetime
import os
from typing import Dict, Any, Optional, Tuple
from .task import Task, TaskExecution

class TaskExecutor:
    """任务执行器"""
    
    def __init__(self, log_dir: str = 'logs'):
        """
        初始化任务执行器
        :param log_dir: 日志文件目录
        """
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
    
    def _get_log_file_path(self, execution_id: int) -> str:
        """获取日志文件路径"""
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        return os.path.join(self.log_dir, f'task_{execution_id}_{timestamp}.log')
    
    def _execute_script(self, script_path: str, script_params: Dict[str, Any], log_file_path: str) -> Tuple[bool, str, str]:
        """
        执行脚本
        :param script_path: 脚本路径
        :param script_params: 脚本参数
        :param log_file_path: 日志文件路径
        :return: (是否成功, 输出信息, 错误信息)
        """
        # 构建命令行参数
        cmd = [sys.executable, script_path]
        for key, value in script_params.items():
            cmd.append(f'--{key}={value}')
        
        # 执行脚本并捕获输出
        try:
            with open(log_file_path, 'w', encoding='utf-8') as log_file:
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=3600)
                # 写入日志
                log_file.write(f"命令: {' '.join(cmd)}\n")
                log_file.write(f"返回码: {result.returncode}\n")
                log_file.write(f"标准输出:\n{result.stdout}\n")
                log_file.write(f"标准错误:\n{result.stderr}\n")
            
            if result.returncode == 0:
                return True, result.stdout, result.stderr
            else:
                return False, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            error_msg = f"脚本执行超时"
            with open(log_file_path, 'w', encoding='utf-8') as log_file:
                log_file.write(f"命令: {' '.join(cmd)}\n")
                log_file.write(f"错误: {error_msg}\n")
            return False, '', error_msg
        except Exception as e:
            error_msg = f"脚本执行错误: {str(e)}"
            with open(log_file_path, 'w', encoding='utf-8') as log_file:
                log_file.write(f"命令: {' '.join(cmd)}\n")
                log_file.write(f"错误: {error_msg}\n")
            return False, '', error_msg
    
    def execute_task(self, task: Task, execution_id: int) -> TaskExecution:
        """
        执行任务
        :param task: 任务对象
        :param execution_id: 执行ID
        :return: 任务执行记录
        """
        # 创建任务执行记录
        execution = TaskExecution(
            execution_id=execution_id,
            task_id=task.id,
            task_name=task.name
        )
        
        # 获取日志文件路径
        log_file_path = self._get_log_file_path(execution_id)
        execution.log_file_path = log_file_path
        
        # 执行任务，支持重试
        for retry in range(task.max_retry + 1):
            execution.retry_count = retry
            execution.start()
            
            # 执行脚本
            success, stdout, stderr = self._execute_script(task.script_path, task.script_params, log_file_path)
            
            if success:
                # 执行成功
                execution.complete(result={
                    'success': True,
                    'stdout': stdout,
                    'stderr': stderr
                })
                break
            else:
                # 执行失败
                execution.fail(error_message=stderr)
                
                # 如果不是最后一次重试，等待重试间隔
                if retry < task.max_retry:
                    time.sleep(task.retry_interval)
        
        return execution
    
    def execute_task_immediately(self, task: Task) -> TaskExecution:
        """
        立即执行任务
        :param task: 任务对象
        :return: 任务执行记录
        """
        # 生成临时执行ID（使用时间戳）
        execution_id = int(datetime.datetime.now().timestamp() * 1000)
        return self.execute_task(task, execution_id)
    
    def __repr__(self) -> str:
        return f'<TaskExecutor log_dir={self.log_dir}>'


# 测试代码
if __name__ == '__main__':
    # 创建测试任务
    task = Task(
        task_id=1,
        name="测试任务",
        script_path="test_script.py",
        script_params={"param1": "value1", "param2": "value2"},
        max_retry=2,
        retry_interval=5
    )
    
    # 创建执行器
    executor = TaskExecutor()
    
    # 执行任务
    execution = executor.execute_task_immediately(task)
    print(f"任务执行结果: {execution.status}")
    print(f"执行时长: {execution.duration}秒")
    print(f"重试次数: {execution.retry_count}")
    print(f"日志文件: {execution.log_file_path}")
    
    if execution.status == TaskExecution.STATUS_FAILED:
        print(f"错误信息: {execution.error_message}")