import subprocess
import sys
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from .task import Task, TaskExecution


class TaskExecutor:
    """任务执行器"""
    def __init__(self, log_dir: str = 'logs'):
        self.log_dir = log_dir
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir, exist_ok=True)

        # 配置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(os.path.join(self.log_dir, 'scheduler.log')),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)

    def _create_log_file(self, execution_id: str) -> str:
        """创建日志文件"""
        log_file = os.path.join(self.log_dir, f"{execution_id}.log")
        return log_file

    def _execute_script(self, script_path: str, params: Dict[str, Any], log_file: str) -> Tuple[int, str, str]:
        """执行Python脚本"""
        # 构建命令
        cmd = [sys.executable, script_path]
        for key, value in params.items():
            cmd.append(f"--{key}={value}")

        self.logger.info(f"Executing script: {' '.join(cmd)}")

        # 执行脚本并捕获输出
        with open(log_file, 'w', encoding='utf-8') as f:
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    timeout=3600  # 默认超时1小时
                )
                # 将输出写入日志文件
                f.write(f"STDOUT:\n{result.stdout}\n")
                f.write(f"STDERR:\n{result.stderr}\n")
                f.write(f"Return code: {result.returncode}\n")
                return result.returncode, result.stdout, result.stderr
            except subprocess.TimeoutExpired:
                error_msg = f"Script execution timed out after 3600 seconds"
                f.write(f"ERROR: {error_msg}\n")
                return -1, "", error_msg
            except Exception as e:
                error_msg = f"Script execution failed: {str(e)}"
                f.write(f"ERROR: {error_msg}\n")
                return -1, "", error_msg

    def execute_task(self, task: Task, execution: TaskExecution) -> TaskExecution:
        """执行任务"""
        self.logger.info(f"Starting task: {task.name} (ID: {task.task_id})")
        execution.start()

        # 创建日志文件
        log_file = self._create_log_file(execution.execution_id)
        execution.log_path = log_file

        retry_count = 0
        while retry_count <= task.max_retries:
            try:
                self.logger.info(f"Executing task attempt {retry_count + 1}/{task.max_retries + 1}")
                
                # 执行脚本
                return_code, stdout, stderr = self._execute_script(task.script_path, task.params, log_file)
                
                if return_code == 0:
                    # 执行成功
                    self.logger.info(f"Task completed successfully: {task.name}")
                    execution.complete(result=f"Script executed successfully. Return code: {return_code}")
                    execution.retry_count = retry_count
                    break
                else:
                    # 执行失败
                    error_msg = f"Script execution failed with return code {return_code}. STDERR: {stderr}"
                    self.logger.error(error_msg)
                    if retry_count < task.max_retries:
                        self.logger.info(f"Retrying task in {task.retry_interval} seconds...")
                        retry_count += 1
                        # 这里可以添加等待逻辑
                    else:
                        # 达到最大重试次数
                        self.logger.error(f"Task failed after {task.max_retries + 1} attempts: {task.name}")
                        execution.fail(error_message=error_msg)
                        execution.retry_count = retry_count
                        break
            except Exception as e:
                error_msg = f"Task execution failed: {str(e)}"
                self.logger.error(error_msg)
                if retry_count < task.max_retries:
                    self.logger.info(f"Retrying task in {task.retry_interval} seconds...")
                    retry_count += 1
                    # 这里可以添加等待逻辑
                else:
                    self.logger.error(f"Task failed after {task.max_retries + 1} attempts: {task.name}")
                    execution.fail(error_message=error_msg)
                    execution.retry_count = retry_count
                    break

        return execution

    def execute_immediately(self, task: Task) -> TaskExecution:
        """立即执行任务"""
        # 创建执行记录
        execution_id = f"{task.task_id}_exec_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        execution = TaskExecution(execution_id, task.task_id, task.name)

        # 执行任务
        execution = self.execute_task(task, execution)

        return execution


# 测试代码
if __name__ == "__main__":
    # 创建测试任务
    task = Task(
        task_id="test_task_1",
        name="Test Task 1",
        script_path="test_script.py",
        params={"arg1": "value1", "arg2": "value2"},
        max_retries=2,
        retry_interval=10
    )

    # 创建执行器
    executor = TaskExecutor()

    # 立即执行任务
    execution = executor.execute_immediately(task)

    # 打印执行结果
    print(f"Task execution completed with status: {execution.status}")
    print(f"Start time: {execution.start_time}")
    print(f"End time: {execution.end_time}")
    print(f"Duration: {execution.duration} seconds")
    print(f"Retry count: {execution.retry_count}")
    print(f"Log file: {execution.log_path}")

    if execution.status == TaskExecution.STATUS_FAILED:
        print(f"Error message: {execution.error_message}")
