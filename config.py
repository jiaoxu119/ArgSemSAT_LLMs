import os

# 混合专家模式
class Config:
    
    # ChatGPT配置
    OPENAI_API_KEY = "sk-xxxxxxxx"
    OPENAI_API_BASE = "https://api.deepseek.com"
    OPENAI_MODEL = "deepseek-chat"
    
    # Claude配置
    CLAUDE_API_KEY = "sk-cxxxxxxx"
    CLAUDE_API_BASE = "https://api.deepseek.com"
    CLAUDE_MODEL = "deepseek-chat"
    
    # DeepSeek 配置
    DEEPSEEK_API_KEY = "sk-cxxxxxxxx"
    DEEPSEEK_API_BASE = "https://api.deepseek.com"
    DEEPSEEK_MODEL = "deepseek-reasoner"
    
    # 代码规则配置
    # CODE_RULE = "Lit Solver::pickBranchLit() {// new code}"
    CODE_RULE = "Lit Solver::pickBranchLit() {// new code}"
    
    # 解决方案生成配置
    SOLUTION_COUNT = 5  # 生成的解决方案数量
    VARIANT_COUNT = 3   # 每个解决方案的变种数量
    CODE_SOURCE_PATH = "prompt/keycode.txt"  # 代码源文件路径
    DATA_PARALLEL_SIZE = 15  # 数据并行大小
    MAX_ITERATIONS = 3  # 每个解决方案的最大迭代轮次
    MAX_RETRY_COUNT = 5  # 解析响应失败时的最大重试次数

class LLMConfig:
    def __init__(self, api_base, api_key, model_name, stream=False):
        self.api_base = api_base
        self.api_key = api_key
        self.model_name = model_name
        self.stream = stream
