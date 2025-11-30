# -*- coding:utf-8 -*-
"""
@Author   : g1879
@Contact  : g1879@qq.com
@Website  : https://DrissionPage.cn
@Copyright: (c) 2020 by g1879, Inc. All Rights Reserved.
"""
from click import command, option, argument, group

from .._functions.tools import configs_to_here as ch
from .._configs.chromium_options import ChromiumOptions
from .._pages.chromium_page import ChromiumPage
from .._functions.task_manager import TaskManager


@group()
def main():
    """DrissionPage 命令行工具"""
    pass


@main.command()
@option("-p", "--set-browser-path", help="设置浏览器路径")
@option("-u", "--set-user-path", help="设置用户数据路径")
@option("-c", "--configs-to-here", is_flag=True, help="复制默认配置文件到当前路径")
@option("-l", "--launch-browser", default=-1, help="启动浏览器，传入端口号，0表示用配置文件中的值")
def config(set_browser_path, set_user_path, configs_to_here, launch_browser):
    """配置和启动浏览器"""
    if set_browser_path:
        set_paths(browser_path=set_browser_path)

    if set_user_path:
        set_paths(user_data_path=set_user_path)

    if configs_to_here:
        ch()

    if launch_browser >= 0:
        port = f'127.0.0.1:{launch_browser}' if launch_browser else None
        ChromiumPage(port)


def set_paths(browser_path=None, user_data_path=None):
    """快捷的路径设置函数
    :param browser_path: 浏览器可执行文件路径
    :param user_data_path: 用户数据路径
    :return: None
    """
    co = ChromiumOptions()

    if browser_path is not None:
        co.set_browser_path(browser_path)

    if user_data_path is not None:
        co.set_user_data_path(user_data_path)

    co.save()


@main.group()
def task():
    """任务管理"""
    pass


@task.command()
@option("-n", "--name", required=True, help="任务名称")
@option("-s", "--script-path", required=True, help="脚本路径")
@option("-a", "--args", default="", help="执行参数")
@option("-d", "--description", default="", help="任务描述")
@option("-e", "--enabled", is_flag=True, help="启用任务")
def add(name, script_path, args, description, enabled):
    """添加新任务"""
    tm = TaskManager()
    task = tm.add_task(name, script_path, args, description, enabled)
    if task:
        print(f'任务已添加：{task.name} ({task.task_id})')


@task.command()
def list():
    """列出所有任务"""
    tm = TaskManager()
    tm.list_tasks()


@task.command()
@argument("task_id")
def run(task_id):
    """运行指定任务"""
    tm = TaskManager()
    tm.run_task(task_id)


@task.command()
def run_all():
    """运行所有已启用的任务"""
    tm = TaskManager()
    tm.run_all_enabled_tasks()


@task.command()
@argument("task_id")
@option("-n", "--name", help="任务名称")
@option("-s", "--script-path", help="脚本路径")
@option("-a", "--args", help="执行参数")
@option("-d", "--description", help="任务描述")
@option("-e", "--enabled", type=bool, help="启用任务")
def update(task_id, **kwargs):
    """更新任务信息"""
    tm = TaskManager()
    task = tm.update_task(task_id, **{k: v for k, v in kwargs.items() if v is not None})
    if task:
        print(f'任务已更新：{task.name} ({task.task_id})')


@task.command()
@argument("task_id")
def delete(task_id):
    """删除任务"""
    tm = TaskManager()
    if tm.delete_task(task_id):
        print(f'任务已删除：{task_id}')


@task.command()
@argument("task_id")
def toggle(task_id):
    """切换任务的启用/禁用状态"""
    tm = TaskManager()
    task = tm.toggle_task(task_id)
    if task:
        status = '启用' if task.enabled else '禁用'
        print(f'任务状态已更新：{task.name} ({task.task_id}) - {status}')


if __name__ == '__main__':
    main()
