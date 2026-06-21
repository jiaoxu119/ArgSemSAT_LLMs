from config import Config
import time
import os
import json
import ray
import random

# 添加全局变量存储程序开始执行时间
EXECUTION_START_TIME = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

# 导入自定义模块
from file_utils import read_file, copy_code_folders, create_results_directories, save_solution_results
from solution_utils import parse_solutions, extract_code_from_response, apply_code_to_template, build_solution_json
from execution_utils import wait_for_completion, calculate_total_execution_time, execute_code_variant
from api_utils import init_api_clients
from parallel_cpp_runner import ExecutionWorker

# 全局大脑文件路径
GLOBAL_BRAIN_FILE = "prompt/global_brain.txt"
HISTORY_FILE = "prompt/history.txt"  # 历史记录文件路径
gpt_api, claude_api, deepseek_api = init_api_clients()

# 修改获取执行计数函数，改为返回程序开始时间
def get_execution_count():
    global EXECUTION_START_TIME
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines:
                    if line.startswith("执行时间:"):
                        try:
                            # 如果历史文件中有执行时间记录，则返回当前程序开始时间
                            return EXECUTION_START_TIME
                        except:
                            return EXECUTION_START_TIME
        return EXECUTION_START_TIME
    except Exception as e:
        print(f"获取执行时间时出错: {str(e)}")
        return EXECUTION_START_TIME

# 修改递增函数，直接返回程序开始时间而不是递增计数
def increment_execution_count():
    global EXECUTION_START_TIME
    return EXECUTION_START_TIME

# 更新全局大脑的函数
def update_global_brain(solution_desc, execution_time, base_time, solution_id=None, solution_code=None, initial_code=None):
    # 计算相对于基准的优劣程度（百分比）
    improvement = (base_time - execution_time) / base_time * 100
    status = "提升" if improvement > 0 else "下降"
    abs_improvement = abs(improvement)
    
    # 获取解决方案性能原因分析
    reason = ""
    if solution_code and initial_code and deepseek_api:
        try:
            summary_template = read_file("prompt/summary.txt")
            if summary_template:
                prompt = summary_template.format(
                    origincode=initial_code,
                    advise=solution_desc,
                    code=solution_code,
                    property=f"{status} {abs_improvement:.2f}%"
                )
                response = deepseek_api.generate(prompt)
                reason = f"原因分析: {response.strip()}"
        except Exception as e:
            print(f"获取解决方案原因分析时出错: {str(e)}")
    
    # 使用传入的solution_id或生成新的索引
    record_id = solution_id if solution_id is not None else None
    
    # 如果没有传入solution_id，则读取全局大脑文件以确定当前索引
    if record_id is None:
        print("正在读取全局大脑文件以确定索引...(大模型返回可能异常)")
        current_index = 0
        try:
            if os.path.exists(GLOBAL_BRAIN_FILE):
                with open(GLOBAL_BRAIN_FILE, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for line in lines:
                        if line.strip() and line.strip()[0].isdigit():
                            # 尝试提取索引编号
                            parts = line.split(":")
                            if len(parts) > 0 and parts[0].strip().isdigit():
                                index = int(parts[0].strip())
                                current_index = max(current_index, index + 1)
        except Exception as e:
            print(f"读取全局大脑文件以确定索引时出错: {str(e)}")
        record_id = str(current_index)
    
    # 更新全局大脑文件
    with open(GLOBAL_BRAIN_FILE, "a", encoding="utf-8") as f:
        f.write(f"{record_id}: {solution_desc} | 相对基准: {status} {abs_improvement:.2f}%{reason}\n")
    
    # 更新历史记录文件，同时添加执行时间
    try:
        execution_time_str = get_execution_count()
        history_content = f"执行时间: {execution_time_str} | {record_id}: {solution_desc} | 相对基准: {status} {abs_improvement:.2f}%{reason}\n"
        
        # 如果文件不存在，先创建并写入执行时间标题行
        if not os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                f.write(f"执行时间: {execution_time_str}\n")
        
        # 追加新内容
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(history_content)
            
        print(f"已更新历史记录 [执行时间: {execution_time_str}, 记录ID: {record_id}]: {solution_desc}, 相对基准: {status} {abs_improvement:.2f}%{' 并添加原因分析' if reason else ''}")
    except Exception as e:
        print(f"更新历史记录文件时出错: {str(e)}")
    
    print(f"已更新全局大脑记录 [{record_id}]: {solution_desc}, 相对基准: {status} {abs_improvement:.2f}%{' 并添加原因分析' if reason else ''}")

def main():
    # 初始化Ray
    ray.init()
    
    # 获取本次执行的时间（只在程序开始时获取一次）
    current_execution_time = increment_execution_count()
    print(f"当前实验执行时间: {current_execution_time}")
    
    # 创建结果目录
    results_dir, results_json_dir = create_results_directories()
    
    # 创建以执行时间命名的子目录
    time_based_dir = os.path.join(results_json_dir, current_execution_time.replace(":", "-").replace(" ", "_"))
    if not os.path.exists(time_based_dir):
        os.makedirs(time_based_dir)
        print(f"创建时间子目录: {time_based_dir}")
    
    # 初始化 best_solutions 列表
    best_solutions = []
    
    # 首先复制代码文件夹
    if not copy_code_folders():
        print("复制代码文件夹失败，程序终止")
        return
        
    # 利用历史数据更新提示词，加入外部小组
    try:
        unique_execution_times = set()
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("执行时间:"):
                        exec_time = line.split("|")[0].strip()
                        unique_execution_times.add(exec_time)
        
        # 如果不重复执行时间的数量能被5整除，则调用enlightenment.py中的函数
        if len(unique_execution_times) > 0 and len(unique_execution_times) % 5 == 0:
            print(f"检测到不重复执行时间数量 {len(unique_execution_times)} 能被5整除，调用enlightenment.py中的函数")
            
            # 导入enlightenment模块
            from enlightenment import fix_advise, fix_code, experience_to_code
            
            # 依次调用三个函数
            fix_advise()
            fix_code()
            experience_to_code()
        # else:
        #     print(f"已实验轮次 {len(unique_execution_times)} 低于5轮，不进行自优化")
        #     return 0
    except Exception as e:
        print(f"检查history文件或调用enlightenment函数时出错: {str(e)}")
        # 错误不影响主流程继续执行
    
    # 调用execute_original
    worker = ExecutionWorker()
    
    # 使用自增ID和配置的data_parallel_size
    id = 0
    success = worker.execute_original(id=id, data_parallel_size=Config.DATA_PARALLEL_SIZE)
    if success:
        print(f"成功执行ID为{id}的任务，data_parallel_size为{Config.DATA_PARALLEL_SIZE}")
    else:
        print(f"执行ID为{id}的任务失败")
    if wait_for_completion(id, Config.DATA_PARALLEL_SIZE):
        print("所有子进程执行完成，开始后续处理")
    
    # 计算总执行时间
    Base_times = calculate_total_execution_time(id, Config.DATA_PARALLEL_SIZE)
    base_total_time = sum(Base_times)
    print(f"初始代码总执行时间: {base_total_time} 秒")
    
    # 在历史记录文件中记录初始代码执行时间
    try:
        execution_time_str = get_execution_count()
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(f"执行时间: {execution_time_str} | 初始代码总执行时间: {base_total_time} 秒\n")
        print(f"已在历史记录中记录初始代码总执行时间: {base_total_time} 秒")
    except Exception as e:
        print(f"记录初始代码执行时间到历史文件时出错: {str(e)}")
    
    
    advise_prompt_template = read_file("prompt/advise.txt")
    if not advise_prompt_template:
        print("无法读取advise文件")
        return
    
    code_content = read_file(Config.CODE_SOURCE_PATH)
    if not code_content:
        print(f"无法读取代码源文件: {Config.CODE_SOURCE_PATH}")
        return
    
    prompt = advise_prompt_template.format(
        code=code_content,
        num=Config.SOLUTION_COUNT,
        nums=Config.VARIANT_COUNT
    )
    
    print("正在生成解决方案...")
    
    # 添加重试逻辑
    retry_count = 0
    solutions = None
    while retry_count < Config.MAX_RETRY_COUNT:
        try:
            response = deepseek_api.generate(prompt)
            solutions = parse_solutions(response)
            if solutions and len(solutions) > 0:
                break
            print(f"解析解决方案结果为空，重试 ({retry_count+1}/{Config.MAX_RETRY_COUNT})")
        except Exception as e:
            print(f"解析解决方案时出错: {str(e)}，重试 ({retry_count+1}/{Config.MAX_RETRY_COUNT})")
        retry_count += 1
        if retry_count >= Config.MAX_RETRY_COUNT:
            print(f"重试次数已达到上限 {Config.MAX_RETRY_COUNT}，无法解析解决方案")
            return
    
    print(f"共生成 {len(solutions)} 种解决方案:")
    for i, solution in enumerate(solutions):
        print(f"解决方案 {i+1}: {solution['core']}")
        for j, variant in enumerate(solution['variants']):
            print(f" 变种 {j+1}: {variant}")
    
    # 读取code.txt模板
    code_prompt_template = read_file("prompt/code.txt")
    if not code_prompt_template:
        print("无法读取code.txt模板")
        return
    
    # 读取newadvise.txt模板
    newadvise_prompt_template = read_file("prompt/newadvise.txt")
    if not newadvise_prompt_template:
        print("无法读取newadvise.txt模板")
        return
    
    # 读取newcode.txt模板
    newcode_prompt_template = read_file("prompt/newcode.txt")
    if not newcode_prompt_template:
        print("无法读取newcode.txt模板")
        return
    
    # 对每个解决方案及其变种调用Claude API
    for i, solution in enumerate(solutions):
        print(f"\n处理解决方案 {i+1}: {solution['core']}")
        
        # 当前解决方案的最佳策略
        current_best_strategy = solution['core']
        
        # 记录当前解决方案的最佳执行时间
        solution_best_time = float('inf')
        
        # 初始化当前最佳代码（第一轮迭代时为None）
        current_best_code = None
        
        # 迭代指定轮数
        for iteration in range(Config.MAX_ITERATIONS):
            id += Config.VARIANT_COUNT
            print(f"\n==== 解决方案 {i+1} 的迭代 {iteration+1}/{Config.MAX_ITERATIONS} ====")
            print(f"当前最佳策略: {current_best_strategy}")
            
            # 使用newadvise生成变种
            if iteration > 0:  # 第一轮使用原始变种，后续轮次生成新变种
                # 计算当前最佳策略相对于基准的性能变化
                improvement = (base_total_time - solution_best_time) / base_total_time * 100
                status = "提升" if improvement > 0 else "下降"
                abs_improvement = abs(improvement)
                performance_grade = f"{status} {abs_improvement:.2f}%"
                
                new_prompt = newadvise_prompt_template.format(
                    code=code_content,
                    advise=current_best_strategy,
                    nums=Config.VARIANT_COUNT,
                    grade=performance_grade
                )
                print("基于最佳策略生成新的变种...")
                new_response = deepseek_api.generate(new_prompt)
                new_solutions = parse_solutions(new_response)
                
                if new_solutions and len(new_solutions) > 0:
                    # 只使用第一个解决方案的变种，因为我们只传入了一个最佳策略
                    current_variants = new_solutions[0]['variants']
                    print(f"生成了 {len(current_variants)} 个新变种")
                    if len(current_variants) > Config.VARIANT_COUNT:
                        print("变种数量超过配置数量，删除多余变种")
                        del current_variants[Config.VARIANT_COUNT:]
                    for j, variant in enumerate(current_variants):
                        print(f" 变种 {j+1}: {variant}")
                else:
                    print("无法生成新变种，使用原始变种继续")
                    current_variants = solution['variants']
            else:
                current_variants = solution['variants']
            
            # 创建存储当前迭代所有变体结果的列表
            solution_results = []
            # 创建存储代码结果的字典
            variant_code_results = {}
            
            # 对每个变种进行处理
            for j, variant in enumerate(current_variants):
                print(f"处理变种 {j+1}: {variant}")
                
                # 构建提示
                if iteration == 0 or current_best_code is None:
                    # 第一轮迭代或者没有最佳代码时，使用原始提示模板
                    code_prompt = code_prompt_template.format(
                        code=code_content,
                        advise=variant,
                        rule=Config.CODE_RULE
                    )
                else:
                    # 非第一轮迭代且有最佳代码时，使用新的提示模板
                    # 计算当前最佳策略相对于基准的性能变化
                    improvement = (base_total_time - solution_best_time) / base_total_time * 100
                    status = "提升" if improvement > 0 else "下降"
                    abs_improvement = abs(improvement)
                    performance_grade = f"{status} {abs_improvement:.2f}%"
                    
                    code_prompt = newcode_prompt_template.format(
                        code=code_content,
                        old_advise=current_best_strategy,
                        old_code=current_best_code,
                        advise=variant,
                        grade=performance_grade,  # 添加grade参数
                        rule=Config.CODE_RULE
                    )
                
                # 调用Claude API
                print("正在调用Claude API...")
                
                # 添加重试逻辑
                retry_count = 0
                code_result = None
                while retry_count < Config.MAX_RETRY_COUNT:
                    try:
                        claude_response = claude_api.generate(code_prompt)
                        code_result = extract_code_from_response(claude_response)
                        if code_result:
                            break
                        print(f"无法从Claude API响应中提取代码，重试 ({retry_count+1}/{Config.MAX_RETRY_COUNT})")
                    except Exception as e:
                        print(f"解析Claude API响应时出错: {str(e)}，重试 ({retry_count+1}/{Config.MAX_RETRY_COUNT})")
                    retry_count += 1
                    if retry_count >= Config.MAX_RETRY_COUNT:
                        print(f"重试次数已达到上限 {Config.MAX_RETRY_COUNT}，无法解析Claude API响应")
                
                if code_result:
                    # 应用代码到模板
                    apply_code_to_template(code_result, j)
                else:
                    print("无法从Claude API响应中提取代码")

                # 存储code_result用于后续使用
                variant_code_results[j] = code_result

            #多线程开始
            # 使用Ray并行执行替换后的代码
            print(f"\n开始使用Ray并行执行替换后的代码")
            # 并行提交所有变体执行任务
            print(f"并行启动 {len(current_variants)} 个优化变体执行")
            ray_tasks = []
            for variant_id in range(len(current_variants)):
                # 为每个变种分配一个唯一的ID
                variant_task_id = id + 1 + variant_id  # 自增ID，每个变种一个唯一ID
                print(f"变种 {variant_id} 分配任务ID: {variant_task_id}")
                ray_task = execute_code_variant.remote(variant_id, variant_task_id)
                ray_tasks.append((variant_task_id, ray_task))
            
            # 等待所有Ray任务完成
            successful_variants = []
            for variant_task_id, ray_task in ray_tasks:
                try:
                    # 获取Ray任务的执行结果
                    success, variant_id = ray.get(ray_task)
                    
                    # 只有当执行成功且wait_for_completion返回True时，才认为变体执行成功
                    if success and wait_for_completion(variant_task_id, Config.DATA_PARALLEL_SIZE):
                        successful_variants.append(variant_task_id)
                    else:
                        print(f"变体 {variant_id} (任务ID: {variant_task_id}) 执行失败或超时")
                except Exception as e:
                    print(f"处理任务ID {variant_task_id} 时发生错误: {str(e)}")
            
            print(f"Ray并行执行完成，成功执行的变体数量: {len(successful_variants)}/{len(current_variants)}")
            
            # 收集成功变体的执行时间和其他信息
            best_variant = None
            best_execution_time = float('inf')
            
            for variant_task_id in successful_variants:
                # 计算变体ID (从0开始)
                variant_id = variant_task_id - (id + 1)
                
                if variant_id < len(current_variants):
                    # 获取变体的执行时间
                    execution_times = calculate_total_execution_time(variant_task_id, Config.DATA_PARALLEL_SIZE)
                    total_execution_time = sum(execution_times) if execution_times else 0
                    
                    # 获取变体方案和代码
                    variant_text = current_variants[variant_id]
                    
                    # 构建变体结果数据
                    variant_result = {
                        "variant_id": variant_id,
                        "variant_task_id": variant_task_id,
                        "variant_text": variant_text,
                        "execution_time": total_execution_time,
                        "code_result": variant_code_results[variant_id]  # 使用之前存储的code_result
                    }
                    
                    # 添加到解决方案结果列表
                    solution_results.append(variant_result)
                    
                    # 检查是否是最佳变体
                    if total_execution_time < best_execution_time:
                        best_execution_time = total_execution_time
                        best_variant = variant_result
            
            # 保存当前迭代的所有变体结果到JSON文件
            iteration_json = build_solution_json(
                solution_id=i, 
                solution_core=current_best_strategy, 
                solution_results=solution_results,
                iteration=iteration
            )
            
            # 保存到JSON文件
            save_solution_results(iteration_json, f"{i}_iteration_{iteration}", time_based_dir)
            
            # 如果找到最佳变体，更新策略用于下一轮迭代
            if best_variant:
                print(f"\n本轮迭代找到最佳变体: {best_variant['variant_text']}")
                print(f"最佳变体执行时间: {best_variant['execution_time']} 秒")
                current_best_strategy = best_variant['variant_text']
                # 保存当前最佳代码，用于下一轮迭代
                current_best_code = best_variant['code_result']
                
                # 更新当前解决方案的最佳执行时间
                if best_variant['execution_time'] < solution_best_time:
                    solution_best_time = best_variant['execution_time']
            else:
                print("\n本轮迭代未找到有效变体，继续使用当前策略")
            
            # 打印迭代进度
            print(f"完成迭代 {iteration+1}/{Config.MAX_ITERATIONS} 的处理")
        
        # 当前解决方案的所有迭代完成后，将最佳结果记录到全局大脑
        if solution_best_time != float('inf'):
            # 记录最佳策略到数组中
            best_solutions.append({
                'solution_id': i,
                'strategy': current_best_strategy,
                'code': current_best_code,
                'execution_time': solution_best_time
            })
            
            update_global_brain(
                f"解决方案 {i}: {solution['core']}", 
                solution_best_time, 
                base_total_time,
                str(i),  # 传递solution_id作为记录ID
                current_best_code,
                code_content
            )
    # 开始交互解决方案，进行进化
    print("\n==== 开始交互解决方案进化阶段 ====")
    
    # 加载extendGroup.txt数据
    try:
        extend_group_content = read_file("prompt/extendGroup.txt")
        if extend_group_content:
            print("正在加载extendGroup.txt数据...")
            # import json
            extend_group_data = json.loads(extend_group_content)
            extend_solutions = extend_group_data.get("best_solutions", [])
            
            if extend_solutions:
                print(f"从extendGroup.txt中加载了 {len(extend_solutions)} 个额外解决方案")
                
                # 继承最后一个解决方案的索引，用于混合策略的命名
                next_solution_id = len(best_solutions)
                
                # 调整extendGroup中的solution_id，避免与现有solution_id冲突
                for extend_solution in extend_solutions:
                    original_id = extend_solution['solution_id']
                    # 使用递增的ID
                    extend_solution['solution_id'] = str(next_solution_id)
                    next_solution_id += 1
                    
                    print(f"添加外部解决方案: 原ID {original_id} -> 新ID {extend_solution['solution_id']}, 执行时间: {extend_solution['execution_time']} 秒")
                    
                    # 更新全局大脑
                    update_global_brain(
                        f"外部解决方案 {extend_solution['solution_id']}: {extend_solution['strategy']}", 
                        extend_solution['execution_time'], 
                        base_total_time,
                        extend_solution['solution_id'],  # 传递调整后的solution_id
                        extend_solution['code'],
                        code_content
                    )
                
                # 将外部解决方案添加到best_solutions列表
                best_solutions.extend(extend_solutions)
                print(f"添加外部解决方案后，共有 {len(best_solutions)} 个可用于进化的解决方案")
    except Exception as e:
        print(f"加载extendGroup.txt数据时出错: {str(e)}")
    
    # 继承最后一个解决方案的索引，用于混合策略的命名
    next_solution_id = len(best_solutions)
    
    # 读取evolve.txt模板
    evolve_prompt_template = read_file("prompt/evolve.txt")
    if not evolve_prompt_template:
        print("无法读取evolve.txt模板")
        return
    
    print(f"收集到 {len(best_solutions)} 个可用于进化的解决方案")
    
    # 进化循环，直到只剩一个策略
    iteration = 0
    id += Config.VARIANT_COUNT
    
    # 添加一个标志，用于在只剩两个策略时控制最后一次迭代
    final_iteration_done = False
    
    while len(best_solutions) > 1:
        print(f"\n==== 进化迭代 {iteration+1} ====")
        print(f"当前剩余 {len(best_solutions)} 个策略")
        
        # 检查是否只剩两个策略且已执行最后一次迭代
        if len(best_solutions) == 2 and final_iteration_done:
            print("只剩下最后两个策略，完成最终迭代，结束进化过程")
            break
            
        # 如果只剩两个策略，标记这是最后一次迭代
        if len(best_solutions) == 2:
            final_iteration_done = True
            
        # 创建新的进化结果列表
        evolved_solutions = []
        
        # 为每对策略生成一个杂交策略
        # 首先从global_brain文件读取内容
        global_brain_content = read_file(GLOBAL_BRAIN_FILE)
        if not global_brain_content:
            print("无法读取全局大脑文件")
            return     
        # 读取evolveSelect.txt模板
        evolve_select_template = read_file("prompt/evolveSelect.txt")
        if not evolve_select_template:
            print("无法读取evolveSelect.txt模板")
            return
        
        # 构建evolveSelect提示
        evolve_select_prompt = evolve_select_template.format(
            origincode=code_content,
            globalbrain=global_brain_content             
        )
        
        # 调用deepseek API获取策略组合
        print("正在生成策略组合方案...")
        select_response = deepseek_api.generate(evolve_select_prompt)
        
        # 解析响应中的策略组合
        pairs = []
        if "@@" in select_response:
            # 提取@@之间的内容
            match_content = select_response.split("@@")[1].strip()
            # 按行分割获取每个组合
            for line in match_content.strip().split("\n"):
                if line.strip():
                    # 每行应该是两个用逗号分隔的数字，表示要配对的策略索引
                    pairs.append(line.strip())
            
            print(f"获取到 {len(pairs)} 对策略组合")
        else:
            print("无法从响应中解析策略组合")
            # 如果无法获取组合，则使用默认配对方式（按顺序两两配对）
            for i in range(0, len(best_solutions), 2):
                if i + 1 < len(best_solutions):
                    pairs.append(f"{i},{i+1}")
        
        # 根据解析出的策略组合进行杂交
        for pair in pairs:
            # 使用逗号分隔索引
            idx_parts = pair.split(",")
            if len(idx_parts) < 2:
                print(f"无效的策略组合: {pair}")
                continue
            
            try:
                # 解析策略ID
                id1 = idx_parts[0].strip()
                id2 = idx_parts[1].strip()
                
                # 在best_solutions中查找匹配的solution_id
                parent1 = None
                parent2 = None
                
                for solution in best_solutions:
                    if str(solution['solution_id']) == id1:
                        parent1 = solution
                    elif str(solution['solution_id']) == id2:
                        parent2 = solution
                
                # 检查是否找到了两个父策略
                if not parent1 or not parent2:
                    print(f"无法找到策略ID {id1} 或 {id2}，跳过此组合")
                    continue
                      
                print(f"杂交策略: {parent1['solution_id']} 和 {parent2['solution_id']}")
                
                # 构建evolve提示
                evolve_prompt = evolve_prompt_template.format(
                    origincode=code_content,
                    advise=parent1['strategy'],
                    code=parent1['code'],
                    newadvise=parent2['strategy'],
                    newcode=parent2['code'],
                    rule=Config.CODE_RULE
                )
                
                # 调用deepseek API生成杂交策略
                print("正在生成杂交策略...")
                
                # 添加重试逻辑
                retry_count = 0
                evolved_code = None
                while retry_count < Config.MAX_RETRY_COUNT:
                    try:
                        deepseek_response = deepseek_api.generate(evolve_prompt)
                        evolved_code = extract_code_from_response(deepseek_response)
                        if evolved_code:
                            break
                        print(f"无法从响应中提取杂交代码，重试 ({retry_count+1}/{Config.MAX_RETRY_COUNT})")
                    except Exception as e:
                        print(f"解析杂交代码时出错: {str(e)}，重试 ({retry_count+1}/{Config.MAX_RETRY_COUNT})")
                    retry_count += 1
                    if retry_count >= Config.MAX_RETRY_COUNT:
                        print(f"重试次数已达到上限 {Config.MAX_RETRY_COUNT}，无法解析杂交代码")
                
                if not evolved_code:
                    print("无法从响应中提取杂交代码，保留性能更好的父策略")
                    # 保留性能更好的父策略
                    better_parent = parent1 if parent1['execution_time'] < parent2['execution_time'] else parent2
                    evolved_solutions.append(better_parent)
                    continue
                
                # 应用代码到模板
                apply_code_to_template(evolved_code, 0)
                
                # 为杂交策略分配新ID
                id += 1
                evolved_task_id = id
                
                # 执行杂交策略
                print(f"准备执行杂交策略 (任务ID: {evolved_task_id})...")
                
                # 使用ray远程调用执行
                ray_task = execute_code_variant.remote(0, evolved_task_id)
                success, variant_id = ray.get(ray_task)
                
                if success and wait_for_completion(evolved_task_id, Config.DATA_PARALLEL_SIZE):
                    print(f"杂交策略 (任务ID: {evolved_task_id}) 执行成功")
                    
                    # 计算执行时间
                    exec_times = calculate_total_execution_time(evolved_task_id, Config.DATA_PARALLEL_SIZE)
                    if exec_times:
                        total_execution_time = sum(exec_times)
                        
                        # 构建进化结果
                        evolved_strategy = f"混合策略{parent1['solution_id']}+{parent2['solution_id']}"
                        # 使用递增的solution_id
                        hybrid_solution_id = str(next_solution_id)
                        next_solution_id += 1  # 递增solution_id
                        
                        evolved_solution = {
                            'solution_id': hybrid_solution_id,  # 使用数字ID而非E{iteration}_{len(evolved_solutions)}
                            'strategy': evolved_strategy,
                            'code': evolved_code,
                            'execution_time': total_execution_time,
                            'parents': [parent1['solution_id'], parent2['solution_id']]
                        }
                        
                        evolved_solutions.append(evolved_solution)
                        print(f"杂交策略执行时间: {total_execution_time} 秒")
                        
                        # 更新全局大脑时传递solution_id
                        update_global_brain(
                            f"杂交策略 {evolved_solution['solution_id']}: {evolved_strategy}", 
                            total_execution_time, 
                            base_total_time,
                            hybrid_solution_id,  # 传递数字ID
                            evolved_code,
                            code_content
                        )
                    else:
                        print("无法获取杂交策略的执行时间，保留性能更好的父策略")
                        better_parent = parent1 if parent1['execution_time'] < parent2['execution_time'] else parent2
                        evolved_solutions.append(better_parent)
                else:
                    print(f"杂交策略 (任务ID: {evolved_task_id}) 执行失败或超时")
            except Exception as e:
                print(f"处理策略组合 {pair} 时发生错误: {str(e)}")
        
        # 合并原始个体和杂交策略
        combined_solutions = best_solutions + evolved_solutions

        # 使用字典去重，确保solution_id唯一性
        unique_solutions = {}
        for solution in combined_solutions:
            solution_id = str(solution['solution_id'])
            # 如果已存在相同ID的策略，保留执行时间更短的那个
            if solution_id in unique_solutions:
                print("出现重复id，检查错误")
                if solution['execution_time'] < unique_solutions[solution_id]['execution_time']:
                    unique_solutions[solution_id] = solution
            else:
                unique_solutions[solution_id] = solution

        # 将去重后的策略转换回列表
        combined_solutions = list(unique_solutions.values())
        
        # 读取score.txt作为提示模板
        score_prompt_template = read_file("prompt/score.txt")
        if not score_prompt_template:
            print("无法读取score.txt模板")
            return
            
        # 读取全局大脑文件内容
        global_brain_content = read_file(GLOBAL_BRAIN_FILE)
        if not global_brain_content:
            print("无法读取全局大脑文件内容")
            return
            
        # 构建score提示
        score_prompt = score_prompt_template.format(
            tactics=global_brain_content
        )
        
        # 调用deepseek API获取评分
        print("正在获取策略评分...")
        score_response = deepseek_api.generate(score_prompt)
        
        # 解析响应，获取每个策略的评分
        strategy_scores = {}
        if "@@" in score_response:
            # 提取@@之间的内容
            score_content = score_response.split("@@")[1].strip() if len(score_response.split("@@")) > 1 else ""
            # 按行分割获取每个评分
            for line in score_content.strip().split("\n"):
                if line.strip() and "," in line:
                    try:
                        # 每行应该是"编号,分数"格式
                        strategy_id, score = line.strip().split(",")
                        strategy_scores[strategy_id.strip()] = float(score.strip())
                    except Exception as e:
                        print(f"解析评分行 '{line}' 时出错: {str(e)}")
        
        print(f"获取到 {len(strategy_scores)} 个策略的评分")
        
        # 计算每个策略的最终得分
        for solution in combined_solutions:
            solution_id = str(solution['solution_id'])
            # 获取创新性+复杂度得分，如果没有则默认为10分（满分20分的一半）
            innovation_complexity_score = strategy_scores.get(solution_id, 10.0)
            # 计算时间性能得分
            if solution['execution_time']!=0:
               time_score = base_total_time / solution['execution_time']
            else:
               time_score = 1 
            # 生成随机分数
            random_score = random.random()
            # 计算最终得分
            final_score = (time_score * 0.4) + (innovation_complexity_score / 20 * 0.4) + (random_score * 0.2)
            # 将得分添加到solution中
            solution['final_score'] = final_score
            solution['innovation_complexity_score'] = innovation_complexity_score
            solution['random_score'] = random_score
            
            print(f"策略 {solution_id} 最终得分: {final_score:.4f} (时间性能: {time_score:.4f}, 创新复杂度: {innovation_complexity_score}, 随机: {random_score:.4f})")
        
        # 首先找出时间性能最好的策略
        best_time_solution = min(combined_solutions, key=lambda x: x['execution_time'])
        print(f"时间性能最佳的策略: {best_time_solution['solution_id']} ({best_time_solution['execution_time']} 秒)")
        
        # 从combined_solutions中移除best_time_solution
        remaining_solutions = [s for s in combined_solutions if s['solution_id'] != best_time_solution['solution_id']]
        
        # 按最终得分排序其余策略
        remaining_solutions.sort(key=lambda x: x['final_score'], reverse=True)
        
        # 确定要保留的策略数量 - 保留前50%的策略
        keep_count = max(0, len(remaining_solutions) // 2)
        
        # 提取保留的策略
        kept_solutions = remaining_solutions[:keep_count]
        removed_solutions = remaining_solutions[keep_count:]
        
        # 将时间性能最佳的策略添加回保留列表
        kept_solutions.insert(0, best_time_solution)
        
        print(f"保留了总共 {len(kept_solutions)} 个策略（包含时间最优策略和 {keep_count} 个最高分策略）")
        for k in kept_solutions:
            print(f"  + 保留策略 {k['solution_id']}: 最终得分 {k.get('final_score', '时间最优'):.4f}, 执行时间 {k['execution_time']} 秒")
        
        print(f"淘汰了 {len(removed_solutions)} 个表现最差的策略")
        for r in removed_solutions:
            print(f"  - 淘汰策略 {r['solution_id']}: 最终得分 {r['final_score']:.4f}, 执行时间 {r['execution_time']} 秒")
            
        # 更新最佳策略列表
        best_solutions = kept_solutions
        
        # 将进化后的策略保存到文件
        evolved_json = {
            'iteration': iteration,
            'evolved_solutions': evolved_solutions
        }
        
        with open(os.path.join(time_based_dir, f"evolution_iteration_{iteration}.json"), 'w', encoding='utf-8') as f:
            json.dump(evolved_json, f, ensure_ascii=False, indent=2)
        
        # 更新全局记忆，删除不在best_solutions中的记录
        try:
            if os.path.exists(GLOBAL_BRAIN_FILE):
                # 读取全局大脑内容
                with open(GLOBAL_BRAIN_FILE, "r", encoding="utf-8") as f:
                    brain_lines = f.readlines()
                
                # 提取当前best_solutions中的solution_id列表
                current_solution_ids = [str(sol['solution_id']) for sol in best_solutions]
                
                # 过滤全局大脑中的记录，只保留当前存在的solution_id对应的记录
                filtered_brain_lines = []
                for line in brain_lines:
                    line_stripped = line.strip()
                    # 如果行不是以数字开头，表示不是解决方案记录行，应该保留
                    if not (line_stripped and line_stripped[0].isdigit()):
                        filtered_brain_lines.append(line)
                        continue
                        
                    # 如果是解决方案记录行，检查ID是否在当前保留的solution_ids中
                    solution_id_match = line_stripped.split(':')[0].strip()
                    if solution_id_match in current_solution_ids:
                        filtered_brain_lines.append(line)
                
                # 重写全局大脑文件
                with open(GLOBAL_BRAIN_FILE, "w", encoding="utf-8") as f:
                    f.writelines(filtered_brain_lines)
                
                print(f"已更新全局大脑记录，已删除不再使用的策略")
        except Exception as e:
            print(f"更新全局大脑记录时出错: {str(e)}")
            
        iteration += 1
    
    # 最终结果
    if best_solutions:
        final_best = best_solutions[0]
        print("\n==== 进化完成 ====")
        print(f"最终最佳策略: {final_best['solution_id']}")
        print(f"执行时间: {final_best['execution_time']} 秒")
        print(f"相对基准的改进: {(base_total_time - final_best['execution_time']) / base_total_time * 100:.2f}%")
        
        # 将最终结果保存到专门的文件
        final_result = {
            'best_strategy_id': final_best['solution_id'],
            'strategy_description': final_best['strategy'],
            'code': final_best['code'],
            'execution_time': final_best['execution_time'],
            'base_time': base_total_time,
            'improvement_percentage': (base_total_time - final_best['execution_time']) / base_total_time * 100
        }
        
        with open(os.path.join(time_based_dir, "final_best_solution.json"), 'w', encoding='utf-8') as f:
            json.dump(final_result, f, ensure_ascii=False, indent=2)
    else:
        print("\n==== 进化失败 ====")
        print("无法产生有效的最终策略")

    # 关闭Ray
    ray.shutdown()
    
if __name__ == "__main__":
    main()
