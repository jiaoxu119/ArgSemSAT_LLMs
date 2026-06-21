import os
import time
import ray
from config import Config
from parallel_cpp_runner import ExecutionWorker

def wait_for_completion(task_id, parallel_size, results_dir="./work/results", timeout=1300, check_interval=5):
    """等待任务完成"""
    expected_files = {f'finished{task_id}_{i}.txt' for i in range(parallel_size)}
    print("开始执行")
    start_time = time.time()
    while True:
        existing_files = set(os.listdir(results_dir))
        missing_files = expected_files - existing_files
        
        # 成功条件：所有文件都存在
        if not missing_files:
            elapsed = time.time() - start_time
            return True
        
        # 超时条件
        elapsed = time.time() - start_time
        if elapsed > timeout:         
            return False       
        time.sleep(check_interval)

def calculate_total_execution_time(task_id, parallel_size, results_dir="./work/results"):
    """统计C++代码执行的总时间开销"""
    total_times = []
    
    for i in range(parallel_size):
        result_file = os.path.join(results_dir, f"{task_id}_{i}.txt")
        if not os.path.exists(result_file):
            print(f"结果文件不存在: {result_file}")
            continue
            
        try:
            with open(result_file, 'r', encoding='utf-8') as file:
                lines = file.readlines()
                
            # 跳过标题行
            if len(lines) > 1:
                process_total_time = 0
                for line in lines[1:]:  # 跳过标题行
                    parts = line.strip().split('\t')
                    if len(parts) >= 2:
                        try:
                            time_value = float(parts[1])
                            process_total_time += time_value
                        except ValueError:
                            continue
                
                total_times.append(process_total_time)
                print(f"进程 {i} 的总执行时间: {process_total_time} 秒")
        except Exception as e:
            print(f"读取或处理文件 {result_file} 时出错: {str(e)}")
    
    return total_times

@ray.remote
def execute_code_variant(variant_id, task_id):
    """Ray远程函数：执行代码变体"""
    worker = ExecutionWorker()
    # 使用execute函数执行特定变体
    success = worker.execute(
        id=task_id,  # 使用传入的task_id
        batch_size=variant_id,  # 设置batch_size为变体总数
        data_parallel_size=Config.DATA_PARALLEL_SIZE  # 每个变种执行DATA_PARALLEL_SIZE个进程
    )
    return success, variant_id 