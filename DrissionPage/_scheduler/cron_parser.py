import datetime
import re
from typing import List, Tuple, Optional

class CronParser:
    """cron表达式解析器"""
    
    def __init__(self, cron_expression: str):
        """
        初始化cron表达式解析器
        :param cron_expression: cron表达式，格式：分 时 日 月 周
        """
        self.cron_expression = cron_expression
        self.minute, self.hour, self.day, self.month, self.weekday = self._parse_expression()
    
    def _parse_expression(self) -> Tuple[List[int], List[int], List[int], List[int], List[int]]:
        """解析cron表达式"""
        parts = self.cron_expression.strip().split()
        if len(parts) != 5:
            raise ValueError(f"无效的cron表达式: {self.cron_expression}，必须包含5个字段")
        
        minute = self._parse_field(parts[0], 0, 59)
        hour = self._parse_field(parts[1], 0, 23)
        day = self._parse_field(parts[2], 1, 31)
        month = self._parse_field(parts[3], 1, 12)
        weekday = self._parse_field(parts[4], 0, 6)  # 0=周日, 1=周一, ..., 6=周六
        
        return minute, hour, day, month, weekday
    
    def _parse_field(self, field: str, min_val: int, max_val: int) -> List[int]:
        """解析单个cron字段"""
        if field == '*':
            return list(range(min_val, max_val + 1))
        
        # 处理范围表达式，如 1-5
        if '-' in field:
            start, end = field.split('-')
            try:
                start = int(start.strip())
                end = int(end.strip())
            except ValueError:
                raise ValueError(f"无效的范围表达式: {field}")
            
            if start < min_val or end > max_val or start > end:
                raise ValueError(f"范围表达式超出有效范围: {field}")
            
            return list(range(start, end + 1))
        
        # 处理列表表达式，如 1,3,5
        if ',' in field:
            items = field.split(',')
            result = []
            for item in items:
                try:
                    val = int(item.strip())
                except ValueError:
                    raise ValueError(f"无效的列表项: {item}")
                
                if val < min_val or val > max_val:
                    raise ValueError(f"列表项超出有效范围: {item}")
                
                result.append(val)
            
            return sorted(list(set(result)))
        
        # 处理步长表达式，如 */5
        if '*/' in field:
            step = int(field.split('*/')[1].strip())
            if step <= 0:
                raise ValueError(f"无效的步长值: {step}")
            
            return list(range(min_val, max_val + 1, step))
        
        # 处理单个值
        try:
            val = int(field.strip())
        except ValueError:
            raise ValueError(f"无效的字段值: {field}")
        
        if val < min_val or val > max_val:
            raise ValueError(f"字段值超出有效范围: {val}")
        
        return [val]
    
    def get_next_run_time(self, base_time: Optional[datetime.datetime] = None) -> datetime.datetime:
        """
        计算下一次执行时间
        :param base_time: 基准时间，默认为当前时间
        :return: 下一次执行时间
        """
        if base_time is None:
            base_time = datetime.datetime.now()
        
        # 从下一分钟开始计算
        next_time = base_time.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
        
        while True:
            # 检查月份
            if next_time.month not in self.month:
                # 跳到下一个月的第一天
                if next_time.month == 12:
                    next_time = next_time.replace(year=next_time.year + 1, month=1, day=1, hour=0, minute=0)
                else:
                    next_time = next_time.replace(month=next_time.month + 1, day=1, hour=0, minute=0)
                continue
            
            # 检查日期
            if next_time.day not in self.day:
                # 跳到下一天
                next_time = next_time + datetime.timedelta(days=1)
                next_time = next_time.replace(hour=0, minute=0)
                continue
            
            # 检查星期几
            if next_time.weekday() not in self.weekday:  # weekday()返回0-6，周一到周日
                # 跳到下一天
                next_time = next_time + datetime.timedelta(days=1)
                next_time = next_time.replace(hour=0, minute=0)
                continue
            
            # 检查小时
            if next_time.hour not in self.hour:
                # 跳到下一个小时
                next_time = next_time + datetime.timedelta(hours=1)
                next_time = next_time.replace(minute=0)
                continue
            
            # 检查分钟
            if next_time.minute not in self.minute:
                # 跳到下一个匹配的分钟
                valid_minutes = [m for m in self.minute if m > next_time.minute]
                if valid_minutes:
                    next_time = next_time.replace(minute=min(valid_minutes))
                else:
                    # 跳到下一个小时的第一个匹配分钟
                    next_time = next_time + datetime.timedelta(hours=1)
                    next_time = next_time.replace(minute=min(self.minute))
                continue
            
            # 所有条件都满足
            return next_time
    
    def __repr__(self) -> str:
        return f'<CronParser {self.cron_expression}>'


# 测试代码
if __name__ == '__main__':
    # 测试每天9点执行
    cron1 = CronParser('0 9 * * *')
    next1 = cron1.get_next_run_time()
    print(f"每天9点执行，下一次执行时间: {next1}")
    
    # 测试每周一到周五18点执行
    cron2 = CronParser('0 18 * * 1-5')
    next2 = cron2.get_next_run_time()
    print(f"每周一到周五18点执行，下一次执行时间: {next2}")
    
    # 测试每5分钟执行一次
    cron3 = CronParser('*/5 * * * *')
    next3 = cron3.get_next_run_time()
    print(f"每5分钟执行一次，下一次执行时间: {next3}")