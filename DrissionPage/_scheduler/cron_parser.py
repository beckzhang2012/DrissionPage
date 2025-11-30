import re
from datetime import datetime, timedelta
from typing import List, Tuple, Optional


class CronParser:
    """Cron表达式解析器"""
    def __init__(self, cron_expr: str):
        self.cron_expr = cron_expr
        self.minute, self.hour, self.day, self.month, self.weekday = self._parse_cron(cron_expr)

    def _parse_cron(self, cron_expr: str) -> Tuple[List[int], List[int], List[int], List[int], List[int]]:
        """解析cron表达式"""
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError("Invalid cron expression: must have 5 fields")

        minute = self._parse_field(parts[0], 0, 59)
        hour = self._parse_field(parts[1], 0, 23)
        day = self._parse_field(parts[2], 1, 31)
        month = self._parse_field(parts[3], 1, 12)
        weekday = self._parse_field(parts[4], 0, 6)

        return minute, hour, day, month, weekday

    def _parse_field(self, field: str, min_val: int, max_val: int) -> List[int]:
        """解析单个cron字段"""
        if field == '*':
            return list(range(min_val, max_val + 1))

        values = []
        parts = field.split(',')
        for part in parts:
            if '-' in part:
                # 范围表达式
                start, end = part.split('-')
                start = int(start)
                end = int(end)
                if start < min_val or end > max_val or start > end:
                    raise ValueError(f"Invalid range in field: {field}")
                values.extend(range(start, end + 1))
            elif '/' in part:
                # 步长表达式
                if part.startswith('*/'):
                    step = int(part[2:])
                    values.extend(range(min_val, max_val + 1, step))
                else:
                    start, step = part.split('/')
                    start = int(start)
                    step = int(step)
                    if start < min_val or start > max_val:
                        raise ValueError(f"Invalid start value in field: {field}")
                    values.extend(range(start, max_val + 1, step))
            else:
                # 单个值
                val = int(part)
                if val < min_val or val > max_val:
                    raise ValueError(f"Invalid value in field: {field}")
                values.append(val)

        # 去重并排序
        return sorted(list(set(values)))

    def get_next_run_time(self, base_time: Optional[datetime] = None) -> datetime:
        """计算下一次执行时间"""
        if base_time is None:
            base_time = datetime.now()

        # 从下一分钟开始计算
        next_time = base_time.replace(second=0, microsecond=0) + timedelta(minutes=1)

        while True:
            # 检查月份
            if next_time.month not in self.month:
                # 跳到下个月1号
                if next_time.month == 12:
                    next_time = next_time.replace(year=next_time.year + 1, month=1, day=1, hour=0, minute=0)
                else:
                    next_time = next_time.replace(month=next_time.month + 1, day=1, hour=0, minute=0)
                continue

            # 检查日期
            if next_time.day not in self.day:
                # 跳到下一天
                next_time = next_time.replace(day=next_time.day + 1, hour=0, minute=0)
                continue

            # 检查星期几
            if next_time.weekday() not in self.weekday:
                # 跳到下一天
                next_time = next_time.replace(day=next_time.day + 1, hour=0, minute=0)
                continue

            # 检查小时
            if next_time.hour not in self.hour:
                # 跳到下一个小时
                next_time = next_time.replace(hour=next_time.hour + 1, minute=0)
                continue

            # 检查分钟
            if next_time.minute not in self.minute:
                # 跳到下一分钟
                next_time = next_time.replace(minute=next_time.minute + 1)
                continue

            # 所有条件都满足
            return next_time

    def is_due(self, current_time: Optional[datetime] = None) -> bool:
        """检查当前时间是否应该执行任务"""
        if current_time is None:
            current_time = datetime.now()

        return (
            current_time.minute in self.minute and
            current_time.hour in self.hour and
            current_time.day in self.day and
            current_time.month in self.month and
            current_time.weekday() in self.weekday
        )


# 测试代码
if __name__ == "__main__":
    # 测试每分钟执行
    parser1 = CronParser("* * * * *")
    next_run1 = parser1.get_next_run_time()
    print(f"每分钟执行: 下一次执行时间 {next_run1}")

    # 测试每小时第30分钟执行
    parser2 = CronParser("30 * * * *")
    next_run2 = parser2.get_next_run_time()
    print(f"每小时第30分钟执行: 下一次执行时间 {next_run2}")

    # 测试每天9点执行
    parser3 = CronParser("0 9 * * *")
    next_run3 = parser3.get_next_run_time()
    print(f"每天9点执行: 下一次执行时间 {next_run3}")

    # 测试每周一至周五9点执行
    parser4 = CronParser("0 9 * * 1-5")
    next_run4 = parser4.get_next_run_time()
    print(f"每周一至周五9点执行: 下一次执行时间 {next_run4}")
