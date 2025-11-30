# -*- coding:utf-8 -*-
"""
任务执行器示例文件
"""
from DrissionPage import TaskExecutor
import time


# 示例任务函数
def example_task(name, sleep_time=1):
    """示例任务函数"""
    print(f'任务 {name} 开始执行')
    time.sleep(sleep_time)
    print(f'任务 {name} 执行完成')
    return f'任务 {name} 执行结果'


# 示例任务函数（会失败）
def failed_task(name):
    """示例失败任务函数"""
    print(f'任务 {name} 开始执行')
    time.sleep(1)
    raise Exception(f'任务 {name} 执行失败')


if __name__ == '__main__':
    # 创建任务执行器
    executor = TaskExecutor()

    # 添加立即执行任务
    executor.add_task(
        name='立即任务1',
        func=example_task,
        args=('立即任务1',),
        kwargs={'sleep_time': 2},
        retry_times=2,
        retry_interval=1
    )

    # 添加定时执行任务（每分钟执行一次）
    executor.add_task(
        name='定时任务1',
        func=example_task,
        args=('定时任务1',),
        kwargs={'sleep_time': 1},
        cron_expr='* * * * *',
        retry_times=1,
        retry_interval=1
    )

    # 添加失败任务（用于测试重试功能）
    executor.add_task(
        name='失败任务1',
        func=failed_task,
        args=('失败任务1',),
        retry_times=2,
        retry_interval=1
    )

    # 立即执行任务
    print('\n立即执行任务：')
    executor.run_task('立即任务1')
    executor.run_task('失败任务1')

    # 等待任务执行完成
    time.sleep(10)

    # 启动定时任务
    print('\n启动定时任务：')
    executor.start()

    # 打印任务状态和结果
    print('\n任务状态和结果：')
    for task_name in executor.tasks:
        status = executor.get_task_status(task_name)
        result = executor.get_task_result(task_name)
        logs = executor.get_task_logs(task_name)

        print(f'\n任务名称：{task_name}')
        print(f'任务状态：{status}')
        print(f'任务结果：{result}')
        print('任务日志：')
        for log in logs:
            print(f'  {log}')

    # 等待定时任务执行几次
    time.sleep(300)

    # 停止任务执行器
    executor.stop()
    print('\n任务执行器已停止')
