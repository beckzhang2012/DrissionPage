import time
from datetime import datetime, timedelta
from DrissionPage import Task, TaskScheduler


# 创建测试脚本文件
test_script_content = '''
import argparse
import time
import random

parser = argparse.ArgumentParser(description='Test script for task scheduler')
parser.add_argument('--arg1', type=str, required=True, help='First argument')
parser.add_argument('--arg2', type=str, required=True, help='Second argument')
args = parser.parse_args()

print(f"Test script started with arg1={args.arg1}, arg2={args.arg2}")
print(f"Current time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

# 模拟一些工作
time.sleep(2)

# 随机失败或成功
if random.random() < 0.3:
    print("Script failed (simulated)")
    exit(1)
else:
    print("Script completed successfully")
    exit(0)
'''

with open('test_script.py', 'w', encoding='utf-8') as f:
    f.write(test_script_content)

print("Created test_script.py")

# 创建调度器
scheduler = TaskScheduler()

# 创建测试任务1：立即执行，允许重试
task1 = Task(
    task_id="task_1",
    name="立即执行任务",
    script_path="test_script.py",
    params={"arg1": "value1", "arg2": "value2"},
    max_retries=2,
    retry_interval=5
)

# 创建测试任务2：定时执行（每2分钟）
task2 = Task(
    task_id="task_2",
    name="定时执行任务",
    script_path="test_script.py",
    params={"arg1": "value3", "arg2": "value4"},
    cron_expr="*/2 * * * *",  # 每2分钟执行一次
    max_retries=1,
    retry_interval=3
)

# 添加任务到调度器
scheduler.add_task(task1)
scheduler.add_task(task2)

print("\n任务列表:")
for task in scheduler.get_all_tasks():
    print(f"- {task.name} (ID: {task.task_id})")
    if task.cron_expr:
        print(f"  定时表达式: {task.cron_expr}")

# 立即执行任务1
print("\n立即执行任务1...")
execution1 = scheduler.execute_task_immediately("task_1")
print(f"任务1执行状态: {execution1.status}")
print(f"开始时间: {execution1.start_time}")
print(f"结束时间: {execution1.end_time}")
print(f"执行耗时: {execution1.duration}秒")
print(f"重试次数: {execution1.retry_count}")
print(f"日志文件: {execution1.log_path}")

if execution1.status == execution1.STATUS_FAILED:
    print(f"错误信息: {execution1.error_message}")

# 启动调度器
print("\n启动调度器...")
scheduler.start()

# 运行10分钟
print("运行10分钟，等待定时任务执行...")
time.sleep(600)

# 停止调度器
print("\n停止调度器...")
scheduler.stop()

# 查看执行历史
print("\n执行历史记录:")
history = scheduler.get_execution_history()
for execution in history:
    print(f"- {execution.task_name} ({execution.status}) at {execution.start_time}")
    print(f"  执行耗时: {execution.duration}秒")
    print(f"  重试次数: {execution.retry_count}")

# 按任务名称筛选
print("\n按任务名称筛选（立即执行任务）:")
task1_history = scheduler.get_execution_history(task_name="立即执行任务")
for execution in task1_history:
    print(f"- {execution.task_name} ({execution.status}) at {execution.start_time}")

# 按状态筛选
print("\n按状态筛选（已完成）:")
completed_history = scheduler.get_execution_history(status="completed")
for execution in completed_history:
    print(f"- {execution.task_name} ({execution.status}) at {execution.start_time}")

# 按时间范围筛选
print("\n按时间范围筛选（最近5分钟）:")
start_time = datetime.now() - timedelta(minutes=5)
time_range_history = scheduler.get_execution_history(start_time_from=start_time)
for execution in time_range_history:
    print(f"- {execution.task_name} ({execution.status}) at {execution.start_time}")

# 查看执行日志
print("\n查看最近一次执行的日志:")
if history:
    latest_execution = history[0]
    log_content = scheduler.get_execution_log(latest_execution.execution_id)
    if log_content:
        print("日志内容:")
        print(log_content[:500] + "..." if len(log_content) > 500 else log_content)

print("\n测试完成!")
