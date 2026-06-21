from config import Config
from file_utils import read_file
import os 
import re

def parse_solutions(response):
    """解析LLM返回的解决方案"""
    solutions = []
    
    try:
        # 使用行分割来处理响应
        lines = response.strip().split('\n')
        
        # 定义正则表达式模式
        core_pattern = re.compile(r'^(\d+)([^\.\d].*)')   # 匹配数字开头、后面不是点号的行
        variant_pattern = re.compile(r'^(\d+\.\d+)(.*)') # 匹配数字.数字开头的行
        
        current_core = None
        current_variants = []
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            
            if not line:
                continue
            
            # 检查是否是核心方案（以数字开头，后面没有点号）
            core_match = core_pattern.match(line)
            if core_match:
                # 如果有上一个核心方案，先保存它
                if current_core is not None and current_variants:
                    solutions.append({
                        "core": current_core,
                        "variants": current_variants
                    })
                
                # 提取数字前缀和剩余内容
                core_id = core_match.group(1)
                core_content = core_match.group(2).strip()
                current_core = core_id + core_content
                
                # 收集核心方案的后续描述行（直到遇到变种方案或下一个核心方案）
                while i < len(lines):
                    next_line = lines[i].strip()
                    if not next_line:
                        i += 1
                        continue
                    
                    # 如果遇到新的核心方案或变种方案，停止收集
                    if core_pattern.match(next_line) or variant_pattern.match(next_line):
                        break
                    
                    current_core += " " + next_line
                    i += 1
                
                current_variants = []
                continue
            
            # 检查是否是变种方案（以数字.数字格式开头）
            variant_match = variant_pattern.match(line)
            if variant_match:
                # 提取变种ID和内容
                variant_id = variant_match.group(1)
                variant_content = variant_match.group(2).strip()
                current_variant = variant_id + variant_content
                
                # 收集变种方案的后续描述行（直到遇到新的变种或核心方案）
                while i < len(lines):
                    next_line = lines[i].strip()
                    if not next_line:
                        i += 1
                        continue
                    
                    # 如果遇到新的核心方案或变种方案，停止收集
                    if core_pattern.match(next_line) or variant_pattern.match(next_line):
                        break
                    
                    current_variant += " " + next_line
                    i += 1
                
                # 添加变种方案
                if current_variant.strip():
                    current_variants.append(current_variant)
        
        # 添加最后一个核心方案
        if current_core is not None and current_variants:
            solutions.append({
                "core": current_core,
                "variants": current_variants
            })
    
    except Exception as e:
        print(f"解析解决方案时出错: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return solutions

def extract_code_from_response(response):
    """解析Claude API返回的代码内容"""
    try:
        # 查找@@@之间的代码块
        start_marker = "@@@"
        end_marker = "@@@"
        
        start_index = response.find(start_marker)
        if start_index == -1:
            print("未找到代码开始标记")
            return None
            
        start_index += len(start_marker)
        end_index = response.find(end_marker, start_index)
        
        if end_index == -1:
            print("未找到代码结束标记")
            return None
            
        code_content = response[start_index:end_index].strip()
        return code_content
    except Exception as e:
        print(f"解析代码内容时出错: {str(e)}")
        return None

def apply_code_to_template(code_result, variant_id):
    """将代码应用到模板中"""
    try:
        # 读取替换模板文件
        replace_template = read_file("replace/Solver.cc")
        if replace_template:
            # 替换模板中的占位符
            new_code = replace_template.replace("{{ replace_code }}", code_result)
            
            # 替换目标工作目录中的文件
            target_file = os.path.join("work", f"ArgSemSAT_{variant_id}", "src", "minisat", "core", "Solver.cc")
            with open(target_file, 'w', encoding='utf-8') as f:
                f.write(new_code)
            print(f"已成功更新文件: {target_file}")
            return True
        else:
            print("无法读取替换模板文件")
            return False
    except Exception as e:
        print(f"替换文件时出错: {str(e)}")
        return False

def build_solution_json(solution_id, solution_core, solution_results,iteration):
    """构建解决方案JSON结果"""
    return {
        "solution_id": solution_id,
        "solution_core": solution_core,
        "variants_results": solution_results,
        "iteration": iteration
    }

