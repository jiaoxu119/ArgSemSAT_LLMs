import os
from typing import Optional, List, Dict, Any
import json
import time
import shutil
from api_utils import init_api_clients
import ray
import re
from execution_utils import wait_for_completion, calculate_total_execution_time
from parallel_cpp_runner import ExecutionWorker
from file_utils import read_file
from config import Config
from solution_utils import extract_code_from_response, apply_code_to_template

def read_file_content(file_path: str) -> Optional[str]:
    """读取文件内容"""
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        return None
    except Exception as e:
        print(f"读取文件 {file_path} 时出错: {str(e)}")
        return None

def append_to_file(file_path: str, content: str) -> bool:
    """追加内容到文件"""
    try:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write("\n" + content)
        return True
    except Exception as e:
        print(f"写入文件 {file_path} 时出错: {str(e)}")
        return False

def get_initial_execution_time() -> float:
    """从history.txt文件中获取初始代码执行时间"""
    try:
        history_content = read_file_content("prompt/history.txt")
        if not history_content:
            print("无法读取history.txt文件")
            return 0.0
            
        # 寻找包含"初始代码总执行时间"的行
        for line in history_content.split('\n'):
            if "初始代码总执行时间" in line:
                # 使用正则表达式提取数字
                match = re.search(r'初始代码总执行时间: (\d+\.?\d*) 秒', line)
                if match:
                    return float(match.group(1))
        
        print("在history.txt中未找到初始代码执行时间")
        return 0.0
    except Exception as e:
        print(f"获取初始执行时间时出错: {str(e)}")
        return 0.0

def fix_advise():
    """建议优化函数"""
    # 初始化API客户端
    _, _, deepseek_api = init_api_clients()
    
    # 读取相关文件
    history_content = read_file_content("prompt/history.txt")
    advise_content = read_file_content("prompt/advise.txt")
    fixadvise_template = read_file_content("prompt/fixadvise.txt")
    
    if not all([history_content, advise_content, fixadvise_template]):
        print("无法读取必要的文件")
        return False
    
    try:
        # 构建fixadvise提示
        fixadvise_prompt = fixadvise_template.format(
            history=history_content,
            advises=advise_content
        )
        
        # 调用deepseek API
        print("正在调用deepseek API进行建议优化分析...")
        response = deepseek_api.generate(fixadvise_prompt)
        
        if not response:
            print("未获得有效的建议优化响应")
            return False
            
        # 将响应添加到advise文件
        print("正在更新advise文件...")
        success = append_to_file("prompt/advise.txt", "\ntip:" + response)
        
        if success:
            print("建议优化完成，已更新advise文件")
            return True
        else:
            print("更新advise文件失败")
            return False
            
    except Exception as e:
        print(f"建议优化过程中出错: {str(e)}")
        return False

def fix_code():
    """代码优化函数"""
    # 初始化API客户端
    _, _, deepseek_api = init_api_clients()
    
    # 读取相关文件
    historyerror_content = read_file_content("prompt/historyerror.txt")
    code_content = read_file_content("prompt/code.txt")
    fixcode_template = read_file_content("prompt/fixcode.txt")
    
    if not all([historyerror_content, code_content, fixcode_template]):
        print("无法读取必要的文件")
        return False
    
    try:
        # 构建fixcode提示
        fixcode_prompt = fixcode_template.format(
            historyerror=historyerror_content,
            code=code_content
        )
        
        # 调用deepseek API
        print("正在调用deepseek API进行代码优化分析...")
        response = deepseek_api.generate(fixcode_prompt)
        
        if not response:
            print("未获得有效的代码优化响应")
            return False
            
        # 将响应添加到code文件
        print("正在更新code文件...")
        success = append_to_file("prompt/code.txt", response)
        
        if success:
            print("代码优化完成，已更新code文件")
            return True
        else:
            print("更新code文件失败")
            return False
            
    except Exception as e:
        print(f"代码优化过程中出错: {str(e)}")
        return False

def analyze_code_performance(initial_code: str, optimized_code: str, performance_improvement: float) -> str:
    """分析代码性能改进的原因"""
    _, _, deepseek_api = init_api_clients()
    
    try:
        # 读取summary模板
        summary_template = read_file("prompt/summary.txt")
        if not summary_template:
            print("无法读取summary.txt模板")
            return "无法获取性能分析"
            
        # 确定性能状态
        status = "提升" if performance_improvement > 0 else "下降"
        abs_improvement = abs(performance_improvement)
        
        # 构建summary提示
        summary_prompt = summary_template.format(
            origincode=initial_code,
            advise="代码优化",
            code=optimized_code,
            property=f"{status} {abs_improvement:.2f}%"
        )
        
        # 调用deepseek API
        print("正在分析代码性能...")
        response = deepseek_api.generate(summary_prompt)
        
        if response:
            return f"原因分析: {response.strip()}"
        else:
            return "无法获取性能分析"
    except Exception as e:
        print(f"分析代码性能时出错: {str(e)}")
        return "分析代码性能时出错"

def experience_to_code():
    """根据经验总结生成代码并评估性能"""
    # 初始化Ray
    if not ray.is_initialized():
        ray.init()
    results_dir = os.path.join("work", "results")
    if os.path.exists(results_dir):
        shutil.rmtree(results_dir)
    os.makedirs(results_dir, exist_ok=True)    
    # 初始化API客户端
    _, claude_api, deepseek_api = init_api_clients()
    
    # 读取相关文件
    history_content = read_file_content("prompt/history.txt")
    keycode_content = read_file_content("prompt/keycode.txt")
    experience_template = read_file_content("prompt/experience.txt")
    code_template = read_file_content("prompt/code.txt")
    
    if not all([history_content, keycode_content, experience_template, code_template]):
        print("无法读取必要的文件")
        return False
    
    # 获取初始代码执行时间作为基准
    base_execution_time = get_initial_execution_time()
    if base_execution_time <= 0:
        print("获取初始代码执行时间失败，将使用默认值 5000 秒")
        base_execution_time = 5000.0
    else:
        print(f"从历史记录中获取到初始代码执行时间: {base_execution_time} 秒")
    
    # 初始化best_solutions列表，用于保存结果
    best_solutions = []
    
    try:
        # 构建experience提示
        experience_prompt = experience_template.format(
            history=history_content,
            keycode=keycode_content
        )
        
        # 调用deepseek API获取改进idea
        print("正在调用deepseek API生成最佳改进idea...")
        idea_response = deepseek_api.generate(experience_prompt)
        
        if not idea_response:
            print("未获得有效的改进idea响应")
            return False
            
        print(f"生成的改进idea: {idea_response}")
        
        # 记录执行时间和是否满足要求
        attempt_count = 0
        max_attempts = 5  # 最多尝试5次
        execution_time = float('inf')
        best_code_result = None
        id = 999999 
        # 重复生成代码并评估，直到执行时间低于基准执行时间或达到最大尝试次数
        while execution_time >= base_execution_time and attempt_count < max_attempts:
            attempt_count += 1
            print(f"\n=== 尝试 {attempt_count}/{max_attempts} ===")
            
            # 构建code提示
            code_prompt = code_template.format(
                code=keycode_content,
                advise=idea_response,
                rule=Config.CODE_RULE
            )
            
            # 调用Deepseek API生成代码
            print("正在调用Deepseek API生成优化代码...")
            
            # 添加重试逻辑
            retry_count = 0
            code_result = None
            while retry_count < Config.MAX_RETRY_COUNT:
                try:
                    deepseek_response = deepseek_api.generate(code_prompt)
                    code_result = extract_code_from_response(deepseek_response)
                    if code_result:
                        break
                    print(f"无法从Deepseek API响应中提取代码，重试 ({retry_count+1}/{Config.MAX_RETRY_COUNT})")
                except Exception as e:
                    print(f"解析Deepseek API响应时出错: {str(e)}，重试 ({retry_count+1}/{Config.MAX_RETRY_COUNT})")
                retry_count += 1
                if retry_count >= Config.MAX_RETRY_COUNT:
                    print(f"重试次数已达到上限 {Config.MAX_RETRY_COUNT}，无法解析Deepseek API响应")
            
            if not code_result:
                print("无法从Deepseek API响应中提取代码")
                continue

            # 应用代码到模板
            print("正在应用生成的代码到求解器...")
            if not apply_code_to_template(code_result, 0):
                print("应用代码到模板失败")
                continue
                
            # 执行代码并评估性能
            print("正在执行代码并评估性能...")
            worker = ExecutionWorker()
            id+=1
            success = worker.execute_original(id=id, data_parallel_size=Config.DATA_PARALLEL_SIZE)
            if success:
                print(f"成功执行代码评估，等待完成...")
                if wait_for_completion(id, Config.DATA_PARALLEL_SIZE):
                    # 计算执行时间
                    execution_times = calculate_total_execution_time(id, Config.DATA_PARALLEL_SIZE)
                    current_execution_time = sum(execution_times) if execution_times else float('inf')
                    
                    print(f"代码执行完成，总执行时间: {current_execution_time} 秒")
                    
                    # 更新最佳执行时间和代码
                    if current_execution_time < execution_time:
                        execution_time = current_execution_time
                        best_code_result = code_result
                        
                    # 检查是否满足要求
                    if current_execution_time < base_execution_time:
                        print(f"执行时间 ({current_execution_time} 秒) 已低于基准时间 ({base_execution_time} 秒)，达到要求")
                        
                        # 分析代码性能改进原因
                        improvement_percentage = (base_execution_time - current_execution_time) / base_execution_time * 100
                        performance_analysis = analyze_code_performance(keycode_content, code_result, improvement_percentage)
                        
                        # 创建最佳解决方案结构
                        solution = {
                            'solution_id': 0,
                            'strategy': idea_response,
                            'code': code_result,
                            'execution_time': current_execution_time,
                            'base_time': base_execution_time,
                            'improvement_percentage': improvement_percentage,
                            'performance_analysis': performance_analysis
                        }
                        best_solutions.append(solution)
                        
                        # 提前结束循环，已找到符合要求的解决方案
                        break
                    else:
                        print(f"执行时间 ({current_execution_time} 秒) 高于基准时间 ({base_execution_time} 秒)，需要继续尝试")
                        
                else:
                    print("代码执行超时")
            else:
                print("代码执行失败")
        
        # 如果找到了符合要求的解决方案，将其保存到extendGroup.txt
        if best_solutions:
            best_solution = best_solutions[0]  # 获取第一个（也是唯一一个）符合要求的解决方案
            
            # 将best_solution结构保存到extendGroup.txt
            extendGroup_content = json.dumps({
                "best_solutions": best_solutions
            }, ensure_ascii=False, indent=2)
            
            with open("prompt/extendGroup.txt", "w", encoding="utf-8") as f:
                f.write(extendGroup_content)
            
            print("已将最佳解决方案保存到 prompt/extendGroup.txt")
            return True
        else:
            print(f"未找到执行时间低于基准时间 ({base_execution_time} 秒) 的解决方案")
            
            # 如果有最佳代码但未达到基准时间，不保存到extendGroup.txt
            if best_code_result and execution_time < float('inf'):
                print(f"最佳尝试执行时间: {execution_time} 秒，未达到基准要求，不保存结果")
            
            return False
            
    except Exception as e:
        print(f"experience_to_code 函数执行过程中出错: {str(e)}")
        return False

if __name__ == "__main__":
    fix_advise()
    fix_code()
    experience_to_code()
