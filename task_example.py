from DrissionPage import TaskExecutor
from datetime import datetime, timedelta
import time

# 示例任务函数：正常执行的任务
def normal_task():
    print("正常任务开始执行...")
    time.sleep(2)  # 模拟任务执行耗时
    print("正常任务执行完成！")
    return "任务执行结果"

# 示例任务函数：执行失败的任务
def failed_task():
    print("失败任务开始执行...")
    time.sleep(1)  # 模拟任务执行耗时
    print("失败任务执行失败！")
    raise Exception("这是一个故意的错误")

# 示例任务函数：定时任务
def cron_task():
    print(f"定时任务执行，当前时间：{datetime.now()}")
    return f"定时任务执行结果：{datetime.now()}"

if __name__ == "__main__":
    # 创建任务执行器，指定日志目录
    executor = TaskExecutor(log_dir="task_logs")
    
    # 添加正常执行的任务
    normal_task_id = executor.add_task(
        func=normal_task,
        task_name="正常任务",
        retry_times=0
    )
    
    # 添加执行失败的任务
    failed_task_id = executor.add_task(
        func=failed_task,
        task_name="失败任务",
        retry_times=3,
        retry_interval=1
    )
    
    # 添加定时任务（每分钟执行一次）
    cron_task_id = executor.add_task(
        func=cron_task,
        task_name="定时任务",
        cron_expr="* * * * *",
        retry_times=1
    )
    
    # 启动任务执行器
    executor.start()
    
    # 立即执行正常任务
    print(f"\n立即执行正常任务（ID：{normal_task_id}）...")
    normal_result = executor.execute_task(normal_task_id)
    print(f"正常任务执行结果：{normal_result}")
    
    # 立即执行失败任务
    print(f"\n立即执行失败任务（ID：{failed_task_id}）...")
    failed_result = executor.execute_task(failed_task_id)
    print(f"失败任务执行结果：{failed_result}")
    
    # 等待3秒，让定时任务有机会执行
    print(f"\n等待3秒，让定时任务有机会执行...")
    time.sleep(3)
    
    # 停止任务执行器
    executor.stop()
    
    # 查询执行记录
    print(f"\n--- 查询所有执行记录 ---\n")
    all_records = executor.get_execution_records()
    for record in all_records:
        print(f"记录ID：{record['record_id']}")
        print(f"任务名称：{record['task_name']}")
        print(f"执行时间：{record['execution_time']}")
        print(f"执行状态：{record['status']}")
        print(f"执行耗时：{record['execution_duration']:.2f} 秒")
        print(f"错误信息：{record['error_message']}")
        print(f"重试次数：{record['retry_count']}")
        print()
    
    # 按任务名称筛选执行记录
    print(f"--- 按任务名称筛选：正常任务 ---\n")
    normal_records = executor.get_execution_records(task_name="正常任务")
    for record in normal_records:
        print(f"记录ID：{record['record_id']}")
        print(f"任务名称：{record['task_name']}")
        print(f"执行状态：{record['status']}")
        print()
    
    # 按执行状态筛选执行记录
    print(f"--- 按执行状态筛选：failed ---\n")
    failed_records = executor.get_execution_records(status="failed")
    for record in failed_records:
        print(f"记录ID：{record['record_id']}")
        print(f"任务名称：{record['task_name']}")
        print(f"执行状态：{record['status']}")
        print()
    
    # 查看执行记录的详细日志
    if all_records:
        first_record_id = all_records[0]['record_id']
        print(f"--- 查看记录ID {first_record_id} 的详细日志 ---\n")
        log_content = executor.get_execution_log(first_record_id)
        print(log_content)
    
    print("示例执行完成！")