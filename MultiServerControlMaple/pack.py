"""
pack.py — 将 MultiServerControlMaple 打包为 .mcdr 插件文件

用法:
    python pack.py

输出:
    MultiServerControlMaple-v{version}.mcdr

MCDR 打包插件结构 (.mcdr = zip):
    MultiServerControlMaple.mcdr
    ├── mcdreforged.plugin.json        # 插件元数据
    ├── requirements.txt               # Python 依赖
    └── multi_server_control_maple/    # 插件代码包
        ├── __init__.py
        ├── default_config.py
        ├── my_lib.py
        ├── utils.py
        └── commands/
            ├── __init__.py
            └── ...
"""
import json
import os
import zipfile

# 项目根目录 (pack.py 所在目录)
ROOT = os.path.dirname(os.path.abspath(__file__))

# 读取版本号
with open(os.path.join(ROOT, "mcdreforged.plugin.json"), "r", encoding="utf-8") as f:
    metadata = json.load(f)
version = metadata.get("version", "0.0.0")

OUTPUT_NAME = f"MultiServerControlMaple-v{version}.mcdr"
# 输出目录: 仓库根目录下的 output/
OUTPUT_DIR = os.path.abspath(os.path.join(ROOT, "..", "output"))
OUTPUT_PATH = os.path.join(OUTPUT_DIR, OUTPUT_NAME)

# 需要打包到 zip 根目录的文件
ROOT_FILES = [
    "mcdreforged.plugin.json",
    "requirements.txt",
]

# 需要打包的插件代码目录
PLUGIN_PACKAGE = "multi_server_control_maple"


def pack():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with zipfile.ZipFile(OUTPUT_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. 根目录文件
        for filename in ROOT_FILES:
            filepath = os.path.join(ROOT, filename)
            if os.path.exists(filepath):
                zf.write(filepath, filename)
                print(f"  + {filename}")

        # 2. 插件代码包 (递归添加 .py 文件)
        pkg_dir = os.path.join(ROOT, PLUGIN_PACKAGE)
        for dirpath, dirnames, filenames in os.walk(pkg_dir):
            # 跳过 __pycache__
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                filepath = os.path.join(dirpath, filename)
                # zip 内路径: multi_server_control_maple/xxx.py
                arcname = os.path.relpath(filepath, ROOT)
                zf.write(filepath, arcname)
                print(f"  + {arcname}")

    print(f"\n打包完成: {OUTPUT_NAME}")
    print(f"路径: {OUTPUT_PATH}")


if __name__ == "__main__":
    print(f"正在打包 MultiServerControlMaple v{version} ...\n")
    pack()
