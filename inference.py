"""
风电结构损伤检测平台 — 模型加载与推理封装

支持 Apple Silicon (MPS) 和 CPU 回退。
复刻上游 vLLM 版的 prompt 构建和防护逻辑，适配 transformers 本地推理。
"""

import os
import re
import time
import torch
from pathlib import Path
from typing import Optional, Tuple
from transformers import AutoModelForImageTextToText, AutoProcessor

from config import (
    MODEL_PATH, DEVICE, DTYPE, MAX_NEW_TOKENS, TEMPERATURE, TOP_P,
    SYSTEM_PROMPT, USER_PROMPT, TRUST_REMOTE_CODE, LOW_CPU_MEM_USAGE
)
from parser import strip_thinking, parse_json_pred


class WindDamageModel:
    """风电损伤检测模型封装。"""

    def __init__(self, device: str = None, dtype: torch.dtype = None):
        self.device = device or DEVICE
        self.dtype = dtype
        self.model = None
        self.processor = None
        self._loaded = False

    def load(self) -> Tuple[float, str]:
        """加载模型与 processor，返回 (加载耗时, 状态信息)。"""
        t0 = time.time()

        # CUDA 不可用时降级 CPU
        if self.device == "cuda" and not torch.cuda.is_available():
            print("[Model] CUDA 不可用，自动降级到 CPU")
            self.device = "cpu"

        # 确定精度
        if self.dtype is None:
            if self.device in ("mps", "cuda"):
                self.dtype = torch.bfloat16
            else:
                self.dtype = torch.float32

        print(f"[Model] 加载模型: {MODEL_PATH}")
        print(f"[Model] device={self.device}, dtype={self.dtype}")

        self.processor = AutoProcessor.from_pretrained(
            MODEL_PATH, trust_remote_code=TRUST_REMOTE_CODE
        )

        # 覆盖 chat_template 为 nothink 版本
        # 原始模板在 enable_thinking=False 时注入 <think>\n\n</think>\n\n 前缀，
        # 但模型用 qwen3_5_nothink 训练（完全无 think 标记），此前缀导致模型走偏。
        # nothink 版本: 生成提示仅 <|im_start|>assistant\n，无任何 think 标记。
        template_path = os.path.join(MODEL_PATH, "chat_template.jinja")
        if os.path.exists(template_path):
            with open(template_path, "r", encoding="utf-8") as f:
                template_str = f.read()
            # 移除生成提示中的 think 标记（最后几行）
            # 原始: {{- '<|im_start|>assistant\n' }} + think 块
            # 替换为: {{- '<|im_start|>assistant\n' }} (无 think)
            template_str = re.sub(
                r"\{\%- if add_generation_prompt %\}.*?\{\%- endif %\}\s*$",
                '{%- if add_generation_prompt %}\n    {{- \'<|im_start|>assistant\\n\' }}\n{%- endif %}',
                template_str,
                flags=re.DOTALL
            )
            self.processor.chat_template = template_str
            print(f"[Model] chat_template 已覆盖为 nothink 版本")

        self.model = AutoModelForImageTextToText.from_pretrained(
            MODEL_PATH,
            torch_dtype=self.dtype,
            trust_remote_code=TRUST_REMOTE_CODE,
            low_cpu_mem_usage=LOW_CPU_MEM_USAGE,
        ).to(self.device)

        self.model.eval()

        # 记录内存占用
        if self.device == "mps":
            mem_gb = torch.mps.current_allocated_memory() / 1024**3
        elif self.device == "cuda":
            mem_gb = torch.cuda.memory_allocated() / 1024**3
        else:
            mem_gb = 0.0

        elapsed = time.time() - t0
        info = f"加载完成 ({elapsed:.1f}s, 内存 {mem_gb:.2f}GB, device={self.device})"
        print(f"[Model] {info}")
        self._loaded = True
        return elapsed, info

    def infer(self, image_path: str) -> Tuple[Optional[dict], str, float]:
        """对单张图片进行推理。

        Args:
            image_path: 图片文件路径

        Returns:
            (parsed_json, raw_output, elapsed_seconds)
        """
        if not self._loaded:
            raise RuntimeError("模型未加载，请先调用 load()")

        from qwen_vl_utils import process_vision_info

        # 构建消息（与训练一致）
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "image", "image": str(Path(image_path).resolve())},
                {"type": "text", "text": USER_PROMPT},
            ]},
        ]

        # 应用 chat_template，关闭 thinking
        text = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            chat_template_kwargs={"enable_thinking": False},
        )

        # 处理图像
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to(self.device)

        t0 = time.time()
        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                temperature=TEMPERATURE,
                top_p=TOP_P,
                do_sample=False,
            )
        elapsed = time.time() - t0

        # 提取生成的部分（去掉输入 token）
        generated = output_ids[:, inputs["input_ids"].shape[1]:]
        raw = self.processor.batch_decode(
            generated, skip_special_tokens=True
        )[0]

        # 解析 JSON
        parsed = parse_json_pred(raw)

        return parsed, raw, elapsed

    def chat_template_check(self) -> dict:
        """检查 chat_template 状态，确认 enable_thinking 关闭后输出格式。"""
        result = {
            "has_template": False,
            "is_thinking_template": False,
            "enable_thinking_false_works": False,
            "sample_prefix": "",
        }

        template = getattr(self.processor, "chat_template", None)
        if template:
            result["has_template"] = True
            result["is_thinking_template"] = "enable_thinking" in template
        else:
            # 尝试从 tokenizer 获取
            tok_template = getattr(self.processor.tokenizer, "chat_template", None)
            if tok_template:
                result["has_template"] = True
                result["is_thinking_template"] = "enable_thinking" in tok_template

        # 测试构建一条消息看前缀
        test_messages = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": [{"type": "text", "text": "test"}]},
        ]
        try:
            rendered = self.processor.apply_chat_template(
                test_messages,
                tokenize=False,
                add_generation_prompt=True,
                chat_template_kwargs={"enable_thinking": False},
            )
            result["enable_thinking_false_works"] = True
            result["sample_prefix"] = rendered[-80:] if len(rendered) > 80 else rendered
        except Exception as e:
            result["enable_thinking_false_works"] = False
            result["sample_prefix"] = f"ERROR: {e}"

        return result


def fallback_to_cpu(model: WindDamageModel) -> WindDamageModel:
    """MPS 失败时降级到 CPU 重新加载模型。"""
    print("[Fallback] 当前设备推理失败，降级到 CPU...")
    del model.model
    torch.mps.empty_cache() if hasattr(torch.mps, "empty_cache") else None

    new_model = WindDamageModel(device="cpu", dtype=torch.float32)
    new_model.load()
    return new_model
