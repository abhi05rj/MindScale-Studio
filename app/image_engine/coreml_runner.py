"""Minimal offline runner for precompiled Core ML Stable Diffusion resources.

This module runs in the isolated Core ML environment. Optional dependencies are
imported only during generation, so the MindScale application does not require
Core ML, Diffusers, or PyTorch merely to import its image provider contract.
"""

import argparse
from pathlib import Path


def generate_background(
    prompt: str,
    model_directory: Path,
    output_directory: Path,
    seed: int,
    inference_steps: int,
    compute_unit: str,
) -> Path:
    import numpy as np
    from diffusers import PNDMScheduler
    from transformers import CLIPTokenizer

    from python_coreml_stable_diffusion.coreml_model import CoreMLModel
    from python_coreml_stable_diffusion.pipeline import CoreMLStableDiffusionPipeline

    model_directory = Path(model_directory).resolve()
    output_directory = Path(output_directory).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)

    required_resources = {
        "TextEncoder.mlmodelc": model_directory / "TextEncoder.mlmodelc",
        "Unet.mlmodelc": model_directory / "Unet.mlmodelc",
        "VAEDecoder.mlmodelc": model_directory / "VAEDecoder.mlmodelc",
        "vocab.json": model_directory / "vocab.json",
        "merges.txt": model_directory / "merges.txt",
    }
    missing = [name for name, path in required_resources.items() if not path.exists()]
    if missing:
        raise RuntimeError(f"Missing Core ML resources: {', '.join(missing)}")

    tokenizer = CLIPTokenizer(
        vocab_file=str(required_resources["vocab.json"]),
        merges_file=str(required_resources["merges.txt"]),
        model_max_length=77,
    )
    scheduler = PNDMScheduler(
        beta_start=0.00085,
        beta_end=0.012,
        beta_schedule="scaled_linear",
        skip_prk_steps=True,
        set_alpha_to_one=False,
        steps_offset=1,
    )

    pipeline = CoreMLStableDiffusionPipeline(
        text_encoder=CoreMLModel(
            str(required_resources["TextEncoder.mlmodelc"]), compute_unit, sources="compiled"
        ),
        unet=CoreMLModel(
            str(required_resources["Unet.mlmodelc"]), compute_unit, sources="compiled"
        ),
        vae_decoder=CoreMLModel(
            str(required_resources["VAEDecoder.mlmodelc"]), compute_unit, sources="compiled"
        ),
        scheduler=scheduler,
        tokenizer=tokenizer,
        feature_extractor=None,
        safety_checker=None,
        controlnet=None,
    )

    np.random.seed(seed)
    result = pipeline(
        prompt=prompt,
        height=pipeline.height,
        width=pipeline.width,
        num_inference_steps=inference_steps,
        guidance_scale=7.5,
        negative_prompt="text, letters, words, watermark, logo, signature, blurry, low quality",
    )
    output_path = output_directory / "generated-background.png"
    result.images[0].save(output_path, format="PNG", optimize=True)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate one local Core ML background image.")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("-i", required=True, type=Path, dest="model_directory")
    parser.add_argument("-o", required=True, type=Path, dest="output_directory")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--num-inference-steps", type=int, default=20)
    parser.add_argument(
        "--compute-unit",
        choices=("ALL", "CPU_AND_GPU", "CPU_ONLY", "CPU_AND_NE"),
        default="CPU_AND_GPU",
    )
    args = parser.parse_args()

    output_path = generate_background(
        prompt=args.prompt,
        model_directory=args.model_directory,
        output_directory=args.output_directory,
        seed=args.seed,
        inference_steps=args.num_inference_steps,
        compute_unit=args.compute_unit,
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
