import time
import datetime
from DrissionPage import Task, TaskScheduler

# 创建测试任务
print("创建测试任务...")
task1 = Task(
    task_id=1,
    name="立即执行测试任务",
    script_path="simple_example.py",
    script_params={"url": "https://www.baidu.com"},
    max_retry=2,
    retry_interval=5
)

task2 = Task(
    task_id=2,
    name="定时执行测试任务",
    script_path="simple_example.py",
    script_params={"url": "https://www.google.com"},
    cron_expression="*/1 * * * *",  # 每分钟执行一次
    enabled=True
)

# 创建调度器
scheduler = TaskScheduler()

# 添加任务
scheduler.add_task(task1)
scheduler.add_task(task2)

# 立即执行任务1
print("\n立即执行任务1...")
execution1 = scheduler.execute_task_immediately(1)
print(f"任务1执行结果: {execution1.status}")
print(f"执行时长: {execution1.duration}秒")
print(f"重试次数: {execution1.retry_count}")
print(f"日志文件: {execution1.log_file_path}")

# 启动调度器
print("\n启动调度器...")
scheduler.start()

# 运行3分钟后停止
print("调度器将运行3分钟后停止...")
time.sleep(180)

# 停止调度器
print("\n停止调度器...")
scheduler.stop()

# 打印所有执行记录
print("\n所有执行记录:")
executions = scheduler.get_all_executions()
for execution in executions:
    print(f"  执行ID: {execution.id}, 任务ID: {execution.task_id}, 任务名称: {execution.task_name}, 状态: {execution.status}, 开始时间: {execution.start_time}, 结束时间: {execution.end_time}")

# 打印任务2的执行记录
print("\n任务2的执行记录:")
task2_executions = scheduler.get_executions_by_task(2)
for execution in task2_executions:
    print(f"  执行ID: {execution.id}, 状态: {execution.status}, 开始时间: {execution.start_time}, 结束时间: {execution.end_time}, 重试次数: {execution.retry_count}")

print("\n测试完成!")