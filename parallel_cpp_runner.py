import os
import subprocess
import platform
import glob
from datetime import datetime  # 新增datetime导入

class ExecutionWorker():
    def __init__(self, compile_timeout=60, execution_timeout=1300):
        self.compile_timeout = compile_timeout
        self.execution_timeout = execution_timeout
        # 新增错误日志路径
        self.error_log_path = "./prompt/historyerror.txt"
        os.makedirs(os.path.dirname(self.error_log_path), exist_ok=True)  # 确保目录存在

    # 新增错误日志方法
    def _log_error(self, id, error_type, error_message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.error_log_path, "a", encoding="utf-8") as f:
            f.write(f"\n[{timestamp}] ID: {id} - {error_type}\n")
            f.write(f"详细信息:\n{error_message}\n")
            f.write("-" * 80 + "\n")

    def execute(self, id, batch_size, data_parallel_size):
        folder_index = batch_size
        print(f"执行ID: {id}, 使用文件夹索引: {folder_index}")

        compile_cmd = f"cd ./work/ArgSemSAT_{folder_index} && ./build"

        if platform.system() == 'Windows':
            error_msg = "Windows系统暂不支持ArgSemSAT执行!"
            self._log_error(id, "系统不兼容", error_msg)  # 新增错误记录
            raise ValueError(error_msg)
        elif platform.system() == 'Linux':
            exe_ext = ""
        else:
            error_msg = "不支持的操作系统类型!"
            self._log_error(id, "系统错误", error_msg)  # 新增错误记录
            raise ValueError(error_msg)

        try:
            result = subprocess.run(
                compile_cmd,
                shell=True,
                timeout=self.compile_timeout,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                # 新增编译错误记录
                error_msg = f"标准输出: {result.stdout}\n标准错误: {result.stderr}"
                print(f"编译错误 (ID: {id}):")
                print(error_msg)
                self._log_error(id, "编译错误", error_msg)
                return False

            processes = []
            af_files = sorted(glob.glob("./work/data/*.af"))

            for i in range(data_parallel_size):
                if i >= len(af_files):
                    # 新增警告记录（可选）
                    warn_msg = f"没有足够的af文件，跳过执行 {i}"
                    print(f"警告：{warn_msg}")
                    self._log_error(id, "资源不足", warn_msg)
                    continue

                af_file = af_files[i]
                abs_af_path = os.path.abspath(af_file)
                
                try:
                    exec_cmd = f"./ASSAT -f {abs_af_path} -p SE-PR {id}_{i}"
                    proc = subprocess.Popen(
                        exec_cmd,
                        shell=True,
                        cwd=f"./work/ArgSemSAT_{folder_index}"
                    )
                    processes.append(proc)
                except Exception as e:
                    # 新增子进程错误记录
                    error_msg = f"子进程启动失败: {str(e)}"
                    print(f"执行错误 (ID: {id}-{i}): {error_msg}")
                    self._log_error(id, "子进程错误", error_msg)

            return True

        except subprocess.TimeoutExpired:
            # 新增超时错误记录
            error_msg = "编译超时，可能是代码有严重错误导致编译器卡住"
            print(f"编译超时 (ID: {id}): {error_msg}")
            self._log_error(id, "编译超时", error_msg)
            os.system("pkill -9 make 2>/dev/null")
            return False
        except Exception as e:
            # 新增未知错误记录
            error_msg = f"未捕获的异常: {str(e)}"
            print(f"执行错误 (ID: {id}): {error_msg}")
            self._log_error(id, "系统异常", error_msg)
            return False

    def execute_original(self, id, data_parallel_size):
        return self.execute(id=id, batch_size=0, data_parallel_size=data_parallel_size)