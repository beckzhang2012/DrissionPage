
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
