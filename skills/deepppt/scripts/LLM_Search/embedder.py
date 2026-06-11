#!/usr/bin/env python3
"""
LLM_Search 嵌入模型封装
========================
双引擎驱动：ONNX Runtime（主，轻量） / sentence-transformers（备，通用）

特性：
  - 主引擎：本地 ONNX 模型 (bge-small-zh-v1.5, 512d)
    · 仅需 onnxruntime + tokenizers，无需 PyTorch
    · 模型已预下载到 model/ 目录
  - 备选引擎：sentence-transformers（网络下载模型）
  - 自动选择最优可用引擎
  - 批量编码，支持均值池化（BERT 模型标准用法）

用法：
  embedder = Embedder()
  vectors = embedder.encode(["文本1", "文本2", ...])
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional, Union

import numpy as np

from .config import (
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_DIM,
    BATCH_SIZE,
    get_model_path,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# ONNX 嵌入引擎（主引擎，推荐）
# ═══════════════════════════════════════════════════════


class ONNXEmbedEngine:
    """基于 ONNX Runtime 的嵌入引擎。

    使用本地 ONNX 模型进行文本向量化，无需 PyTorch。
    模型位于 model/ 目录，首次使用时已验证存在。

    Attributes:
        model_path: ONNX 模型文件路径
        dimension: 输出向量维度（bge-small-zh-v1.5 = 512）
    """

    def __init__(self, model_dir: Path, device: str = "cpu"):
        self.model_dir = Path(model_dir)
        self.device = device

        # 查找 ONNX 模型文件
        onnx_file = self._find_onnx_model()
        if onnx_file is None:
            raise FileNotFoundError(
                f"在 {model_dir} 中未找到 ONNX 模型文件"
            )

        self.model_path = onnx_file
        self._session = None
        self._tokenizer = None
        self._dimension = None

    def _find_onnx_model(self) -> Optional[Path]:
        """递归查找 ONNX 模型文件"""
        for f in self.model_dir.rglob("*.onnx"):
            if "optimized" in f.name or "model" in f.name.lower():
                return f
        # 任意 onnx 文件
        onnx_files = list(self.model_dir.rglob("*.onnx"))
        return onnx_files[0] if onnx_files else None

    @property
    def session(self):
        if self._session is None:
            import onnxruntime as ort

            # 选择执行提供器
            providers = ["CPUExecutionProvider"]
            if ort.get_device() == "GPU":
                try:
                    providers.insert(0, "CUDAExecutionProvider")
                except Exception:
                    pass

            logger.info(f"加载 ONNX 模型: {self.model_path}")
            self._session = ort.InferenceSession(
                str(self.model_path),
                providers=providers,
            )
            logger.info(f"ONNX 模型就绪，提供器: {self._session.get_providers()}")
        return self._session

    @property
    def tokenizer(self):
        if self._tokenizer is None:
            from tokenizers import Tokenizer

            # 查找 tokenizer.json
            tokenizer_files = list(self.model_dir.rglob("tokenizer.json"))
            if tokenizer_files:
                tok_path = tokenizer_files[0]
                logger.info(f"加载分词器: {tok_path}")
                self._tokenizer = Tokenizer.from_file(str(tok_path))
            else:
                raise FileNotFoundError(
                    f"在 {self.model_dir} 中未找到 tokenizer.json"
                )
        return self._tokenizer

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            # 从 ONNX 模型输出推导
            for output in self.session.get_outputs():
                if output.shape and len(output.shape) == 2:
                    self._dimension = output.shape[1]
                    break
            if self._dimension is None:
                self._dimension = 512  # bge-small 默认
        return self._dimension

    def encode(
        self,
        texts: List[str],
        show_progress: bool = True,
        normalize: bool = True,
    ) -> np.ndarray:
        """将文本列表编码为向量矩阵。

        BGE 模型使用 [CLS] token 的输出作为句子向量，
        然后进行 L2 归一化。
        """
        if not texts:
            raise ValueError("texts 不能为空")

        MAX_SEQ_LEN = 512  # BGE 模型的最大序列长度
        all_embeddings = []
        total = len(texts)

        for i in range(0, total, BATCH_SIZE):
            batch_texts = texts[i : i + BATCH_SIZE]
            if show_progress and total > BATCH_SIZE:
                logger.info(f"编码: {min(i + BATCH_SIZE, total)}/{total}")

            # Tokenize（启用截断）
            encoded = self.tokenizer.encode_batch(batch_texts)
            # 截断到 MAX_SEQ_LEN（包含特殊 token）
            max_len = min(max(len(e.ids) for e in encoded), MAX_SEQ_LEN)

            # Padding + attention mask
            input_ids = np.zeros((len(encoded), max_len), dtype=np.int64)
            attention_mask = np.zeros((len(encoded), max_len), dtype=np.int64)
            token_type_ids = np.zeros((len(encoded), max_len), dtype=np.int64)

            for j, e in enumerate(encoded):
                seq_len = min(len(e.ids), MAX_SEQ_LEN)
                input_ids[j, :seq_len] = e.ids[:seq_len]
                attention_mask[j, :seq_len] = 1

            # ONNX 推理
            outputs = self.session.run(
                None,
                {
                    "input_ids": input_ids,
                    "attention_mask": attention_mask,
                    "token_type_ids": token_type_ids,
                },
            )

            # outputs[0] = last_hidden_state: (batch, seq_len, hidden)
            # outputs[1] = pooler_output: (batch, hidden) — BERT 的 [CLS] 池化
            if len(outputs) > 1:
                # 使用 pooler_output（如果存在）
                embeddings = outputs[1]
            else:
                # 手动 [CLS] token 池化
                embeddings = outputs[0][:, 0, :]

            embeddings = np.asarray(embeddings, dtype=np.float32)

            if normalize:
                # L2 归一化
                norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
                norms = np.maximum(norms, 1e-12)
                embeddings = embeddings / norms

            all_embeddings.append(embeddings)

        return np.vstack(all_embeddings)

    def encode_single(self, text: str, normalize: bool = True) -> np.ndarray:
        return self.encode([text], show_progress=False, normalize=normalize)[0]


# ═══════════════════════════════════════════════════════
# Sentence-Transformers 引擎（备选）
# ═══════════════════════════════════════════════════════


class STEmbedEngine:
    """sentence-transformers 嵌入引擎（备选方案）。

    当 ONNX 模型不可用时使用，需下载 PyTorch 模型。
    """

    def __init__(self, model_name: str, device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info(f"加载 ST 模型: {self.model_name}")
            self._model = SentenceTransformer(self.model_name, device=self.device)
            logger.info(
                f"ST 模型就绪 (dim={self._model.get_sentence_embedding_dimension()})"
            )
        return self._model

    @property
    def dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()

    def encode(
        self,
        texts: List[str],
        show_progress: bool = True,
        normalize: bool = True,
    ) -> np.ndarray:
        return np.asarray(
            self.model.encode(
                texts,
                batch_size=BATCH_SIZE,
                show_progress_bar=show_progress,
                normalize_embeddings=normalize,
                convert_to_numpy=True,
            ),
            dtype=np.float32,
        )

    def encode_single(self, text: str, normalize: bool = True) -> np.ndarray:
        return self.encode([text], show_progress=False, normalize=normalize)[0]


# ═══════════════════════════════════════════════════════
# 统一嵌入器
# ═══════════════════════════════════════════════════════


class Embedder:
    """文本嵌入统一封装器。

    自动选择最佳可用引擎：
    1. ONNX Runtime + 本地模型（推荐，启动最快）
    2. sentence-transformers + HuggingFace 模型（备选）

    Usage:
        embedder = Embedder()                     # 自动选择
        embedder = Embedder(backend="onnx")       # 指定 ONNX
        embedder = Embedder(backend="st")         # 指定 ST
        vec = embedder.encode_single("金融架构")
        vecs = embedder.encode(["文本1", "文本2"])
    """

    def __init__(
        self,
        model_name_or_path: Optional[str] = None,
        backend: str = "auto",
        device: str = "cpu",
    ):
        """
        Args:
            model_name_or_path: 模型路径或名称
                - None: 自动选择本地 ONNX 模型或默认 ST 模型
                - Path: 本地模型目录
                - str: HuggingFace 模型名
            backend: "auto" | "onnx" | "st"
            device: "cpu" | "cuda"
        """
        self._backend = backend
        self._device = device
        self._engine = None
        self._engine_type = None

        # 确定模型路径
        if model_name_or_path:
            self._model_path = Path(model_name_or_path)
        else:
            self._model_path = get_model_path()

        self._init_engine()

    def _init_engine(self):
        """初始化最佳可用引擎"""
        errors = []

        # 1. 尝试 ONNX
        if self._backend in ("auto", "onnx"):
            onnx_dir = self._model_path
            if onnx_dir.exists():
                try:
                    self._engine = ONNXEmbedEngine(onnx_dir, self._device)
                    self._engine_type = "onnx"
                    logger.info(
                        f"Embedder 初始化: ONNX ({self.dimension}d) "
                        f"model={self._engine.model_path.name}"
                    )
                    return
                except ImportError as e:
                    errors.append(f"ONNX: {e}")
                except Exception as e:
                    errors.append(f"ONNX: {e}")
            else:
                errors.append(f"ONNX: 模型目录不存在 {onnx_dir}")

        # 2. 尝试 sentence-transformers
        if self._backend in ("auto", "st"):
            try:
                model_name = (
                    str(self._model_path)
                    if self._backend == "st"
                    else DEFAULT_MODEL_NAME
                )
                self._engine = STEmbedEngine(model_name, self._device)
                self._engine_type = "st"
                logger.info(
                    f"Embedder 初始化: Sentence-Transformers ({self.dimension}d)"
                )
                return
            except ImportError as e:
                errors.append(f"ST: {e}")
            except Exception as e:
                errors.append(f"ST: {e}")

        raise RuntimeError(
            f"无法初始化任何嵌入引擎。请安装依赖:\n"
            f"  pip install onnxruntime tokenizers     # 轻量方案\n"
            f"  pip install sentence-transformers      # 完整方案\n"
            f"错误: {'; '.join(errors)}"
        )

    @property
    def dimension(self) -> int:
        return self._engine.dimension

    @property
    def engine_type(self) -> str:
        return self._engine_type

    def encode(
        self,
        texts: List[str],
        show_progress: bool = True,
        normalize: bool = True,
    ) -> np.ndarray:
        return self._engine.encode(texts, show_progress, normalize)

    def encode_single(self, text: str, normalize: bool = True) -> np.ndarray:
        return self._engine.encode_single(text, normalize)

    @staticmethod
    def _preprocess(text: str, max_length: int = 512) -> str:
        if not text:
            return ""
        text = " ".join(text.split())
        if len(text) > max_length:
            text = text[:max_length]
        return text

    def __repr__(self):
        return f"Embedder(engine={self.engine_type}, dim={self.dimension})"
