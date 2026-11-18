"""
风电结构损伤检测平台 — 配置文件
"""

import os
import sys

# Windows 控制台默认 GBK，强制 UTF-8 输出避免 emoji/中文打印崩溃
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ─── 路径配置 ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "qwen3.5-4b")
DATA_DIR = os.path.join(BASE_DIR, "data")
TEST_JSON = os.path.join(DATA_DIR, "dataset_test.json")
IMAGE_DIR = os.path.join(DATA_DIR, "images")

# ─── 推理配置 ─────────────────────────────────────────────
DEVICE = "cuda"         # Windows + NVIDIA GPU；CUDA 不可用时自动降级为 "cpu"
DTYPE = None            # None=自动选择 (bf16 on MPS, fp32 on CPU)；或指定 torch.bfloat16 / torch.float32
MAX_NEW_TOKENS = 2048   # JSON 输出约 250-500 token，留余量
TEMPERATURE = 0.0       # 确定性输出，保证可复现
TOP_P = 1.0

# ─── 提示词（与训练一致）──────────────────────────────────
SYSTEM_PROMPT = (
    "你是风电结构损伤检测领域的顶尖专家。请根据输入的巡检图像，对风电结构构件进行识别和损伤评估。"
    "输出必须为完整的JSON格式，每个描述字段不超过50字，是/否类问题只填是或否，置信度填高/中/低。"
)
USER_PROMPT = "请分析这张风电结构巡检图像，输出标准化的损伤评估JSON报告。"

# ─── 模型加载参数 ─────────────────────────────────────────
TRUST_REMOTE_CODE = True
LOW_CPU_MEM_USAGE = True

# ─── 关键字段定义（匹配数据集 Schema）─────────────────────
KEY_FIELDS = [
    ("图像Caption",                 "图像质量评价"),
    ("2. 损伤判定",                 "是否可判定"),
    ("2. 损伤判定",                 "是否存在损伤"),
    ("2. 损伤判定",                 "损伤类型"),
    ("2. 损伤判定",                 "损伤发展趋势"),
    ("3. 潜在风险影响分析",         "对结构安全性的影响程度"),
    ("3. 潜在风险影响分析",         "是否对机组运行可靠性影响"),
    ("3. 潜在风险影响分析",         "是否对长期服役寿命的影响"),
    ("4. 运维与处置建议",           "是否建议停机、限功率运行或重点监测"),
    ("5. 不确定性说明与调查建议",   "是否建议补充获取更高分辨率或多角度图像"),
    ("5. 不确定性说明与调查建议",   "是否建议结合现场巡检或历史运维数据进行综合判断"),
    ("5. 不确定性说明与调查建议",   "当前是否建议仅基于该图像做出维修或停机决策"),
    ("6. 结论建议",                 "巡检优先级"),
    ("6. 结论建议",                 "本次判断的置信度"),
]
