#!/usr/bin/env python3
"""
One-time script to export CLIP ViT-B-32 text encoder to ONNX format.

Run locally with PyTorch installed:
    python export_clip_onnx.py

Produces:
    models/clip_text_encoder.onnx
    models/bpe_simple_vocab_16e6.txt.gz
"""

import shutil
from pathlib import Path

import numpy as np
import open_clip
import torch
import torch.nn as nn


class CLIPTextEncoder(nn.Module):
    """Wrapper that exposes encode_text as forward() for ONNX export."""

    def __init__(self, clip_model):
        super().__init__()
        self.model = clip_model

    def forward(self, text):
        return self.model.encode_text(text, normalize=True)


def main():
    output_path = Path("models/clip_text_encoder.onnx")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("Loading CLIP ViT-B-32...")
    model, _, _ = open_clip.create_model_and_transforms(
        "ViT-B-32", pretrained="laion2b_s34b_b79k"
    )
    model.eval()
    model = model.cpu()

    tokenizer = open_clip.get_tokenizer("ViT-B-32")

    text_encoder = CLIPTextEncoder(model)
    dummy_input = tokenizer(["a photo of a cat"])  # [1, 77]

    print(f"Exporting to {output_path}...")
    torch.onnx.export(
        text_encoder,
        dummy_input,
        str(output_path),
        export_params=True,
        opset_version=14,
        do_constant_folding=True,
        input_names=["input_ids"],
        output_names=["embedding"],
        dynamic_axes={
            "input_ids": {0: "batch_size"},
            "embedding": {0: "batch_size"},
        },
    )
    print(f"Exported ONNX model: {output_path} ({output_path.stat().st_size / 1e6:.1f} MB)")

    # Copy BPE vocab file for the standalone tokenizer
    bpe_src = Path(open_clip.__file__).parent / "bpe_simple_vocab_16e6.txt.gz"
    bpe_dst = output_path.parent / "bpe_simple_vocab_16e6.txt.gz"
    if bpe_src.exists() and not bpe_dst.exists():
        shutil.copy2(bpe_src, bpe_dst)
        print(f"Copied BPE vocab: {bpe_dst}")

    # Verify: compare PyTorch vs ONNX outputs
    print("Verifying ONNX output matches PyTorch...")
    import onnxruntime as ort

    session = ort.InferenceSession(str(output_path))

    test_queries = [
        "homer eating donuts",
        "bart writing on chalkboard",
        "marge angry",
    ]

    for query in test_queries:
        tokens = tokenizer([query])

        # PyTorch reference
        with torch.no_grad():
            pt_out = model.encode_text(tokens, normalize=True)
        pt_embedding = pt_out[0].numpy()

        # ONNX inference
        onnx_out = session.run(None, {"input_ids": tokens.numpy()})
        onnx_embedding = onnx_out[0][0]

        cosine_sim = np.dot(pt_embedding, onnx_embedding) / (
            np.linalg.norm(pt_embedding) * np.linalg.norm(onnx_embedding)
        )
        max_diff = np.max(np.abs(pt_embedding - onnx_embedding))
        print(f"  '{query}': cosine_sim={cosine_sim:.6f}, max_diff={max_diff:.6f}")

        assert cosine_sim > 0.999, f"Cosine similarity too low: {cosine_sim}"

    print("Verification passed.")


if __name__ == "__main__":
    main()
