import os
import shutil
from config import Config

def read_file(file_path):
    """读取文件内容"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        print(f"读取文件 {file_path} 时出错: {str(e)}")
        return None

def copy_code_folders():
    """复制代码文件夹"""
    variant_count = Config.VARIANT_COUNT
    origin_code_path = os.path.join("originCode", "ArgSemSAT")
    work_dir = "work"
    
    # 确保work目录存在
    if not os.path.exists(work_dir):
        os.makedirs(work_dir)
    
    # 检查源文件夹是否存在
    if not os.path.exists(origin_code_path):
        print(f"源代码文件夹不存在: {origin_code_path}")
        return False
    
    # 复制文件夹多份
    for i in range(variant_count):
        target_path = os.path.join(work_dir, f"ArgSemSAT_{i}")
        
        # 如果目标文件夹已存在，先删除
        if os.path.exists(target_path):
            shutil.rmtree(target_path)
        
        # 复制文件夹
        try:
            shutil.copytree(origin_code_path, target_path)
            print(f"已复制代码文件夹到: {target_path}")
        except Exception as e:
            print(f"复制文件夹时出错: {str(e)}")
            return False
    
    return True

def create_results_directories():
    """创建结果目录"""
    # 清理work/results目录
    results_dir = os.path.join("work", "results")
    if os.path.exists(results_dir):
        shutil.rmtree(results_dir)
    os.makedirs(results_dir, exist_ok=True)
    
    # 创建保存结果的目录
    results_json_dir = os.path.join("work", "json_results")
    os.makedirs(results_json_dir, exist_ok=True)
    
    # 清除global文件内容
    global_file = os.path.join("prompt", "global_brain.txt")
    if os.path.exists(global_file):
        with open(global_file, 'w', encoding='utf-8') as f:
            f.write('')
        print(f"已清除global文件内容: {global_file}")
    
    return results_dir, results_json_dir

def save_solution_results(solution_json, solution_id, results_json_dir):
    """保存解决方案结果到JSON文件"""
    json_file_path = os.path.join(results_json_dir, f"solution_{solution_id}_results.json")
    try:
        import json
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump(solution_json, json_file, ensure_ascii=False, indent=2)
        print(f"已将解决方案 {solution_id} 的结果保存到: {json_file_path}")
        return True
    except Exception as e:
        print(f"保存JSON文件时出错: {str(e)}")
        return False 