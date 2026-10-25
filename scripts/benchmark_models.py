#!/usr/bin/env python3
"""Compare our from-scratch U-Net with stronger alternatives on the untouched 268-image test split.

Models (all see the same 256x256 test images and are scored against the same masks):
  ours           U-Net trained from scratch: the deployed model.onnx, run with ONNX Runtime
  resnet34_unet  U-Net with an ImageNet-pretrained ResNet-34 encoder, fine-tuned on the same data
                 (scripts/train_pretrained_baseline.py)
  deeplabv3      DeepLabV3-MobileNetV3 pretrained on COCO, its built-in "person" class, no training
  sam_detector   Faster R-CNN finds people, Segment Anything (SAM ViT-B) cuts them out: no training
  sam_oracle     SAM given the TRUE person boxes: an upper bound, not a real pipeline

Quality: Dice, IoU and boundary F1 (outline accuracy within 2 px) per image, plus global Dice.
Cost: each model runs in a fresh process on the CPU with 1 thread (like the free server):
median milliseconds per image, and the RAM that loading and running the model adds to the process.
Both U-Nets run in ONNX Runtime (the baseline is exported to ONNX first), so their speed is
compared on the same runtime. DeepLab and SAM run in PyTorch; the RAM of importing PyTorch itself
is NOT counted for them, which is generous to them.
"Fits the free server": the deployed server peaked at 378 MiB with our model (measured in the
production container). Server without the model = 378 - our model's RAM; a model fits if that plus
its own RAM stays within 512 MB.

    pip install -e '.[benchmark]'
    python scripts/benchmark_models.py            # writes frontend/src/data/benchmark.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

DATA_ROOT = PROJECT_ROOT / "data" / "processed"
OUTPUT = PROJECT_ROOT / "frontend" / "src" / "data" / "benchmark.json"
MEAN, STD = np.array([0.485, 0.456, 0.406], np.float32), np.array([0.229, 0.224, 0.225], np.float32)
COCO_PERSON, VOC_PERSON = 1, 15
SERVER_LIMIT_MB = 512  # Render free plan
SERVER_PEAK_WITH_OURS_MB = 378  # measured peak of the deployed server (production container, docs: WALKTHROUGH section 11)
ONNX_MODELS = {"ours": "model.onnx", "resnet34_unet": "baseline_resnet34_unet.onnx"}  # served with ONNX Runtime

MODELS = {
    "ours": "Our U-Net, trained from scratch",
    "resnet34_unet": "U-Net + pretrained ResNet-34, fine-tuned",
    "deeplabv3": "DeepLabV3-MobileNetV3 (COCO), off the shelf",
    "sam_detector": "Person detector + SAM ViT-B",
    "sam_oracle": "SAM ViT-B with the true box (upper bound)",
}


# ---------------------------------------------------------------- data


def load_test_split(limit: int | None = None) -> tuple[list[str], list[np.ndarray], list[np.ndarray]]:
    names = json.loads((DATA_ROOT / "splits.json").read_text())["splits"]["test"][:limit]
    images = [np.asarray(Image.open(DATA_ROOT / "images" / n).convert("RGB")) for n in names]
    masks = [np.asarray(Image.open(DATA_ROOT / "masks" / n).convert("L")) > 127 for n in names]
    return names, images, masks


def normalised(image: np.ndarray) -> np.ndarray:
    """uint8 HxWx3 -> float32 1x3xHxW with ImageNet mean/std (the normalisation all these models expect)."""
    return ((image.astype(np.float32) / 255.0 - MEAN) / STD).transpose(2, 0, 1)[np.newaxis]


def true_boxes(mask: np.ndarray) -> list[list[float]]:
    """One box per person-sized blob of the ground-truth mask (for the SAM upper bound)."""
    labels, count = ndimage.label(mask)
    boxes = []
    for index, region in enumerate(ndimage.find_objects(labels), start=1):
        if region is not None and (labels[region] == index).sum() >= 0.005 * mask.size:
            ys, xs = region
            boxes.append([xs.start, ys.start, xs.stop, ys.stop])
    return boxes


# ---------------------------------------------------------------- predictors (image -> boolean mask)


def make_predictor(name: str, device: str):
    """Build one model and return predict(image, gt_mask) -> bool mask, plus its parameter count."""
    if name == "ours" or (name in ONNX_MODELS and device == "cpu"):
        import onnxruntime

        path = PROJECT_ROOT / "backend" / "weights" / ONNX_MODELS[name]
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 1 if device == "cpu" else 0
        session = onnxruntime.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
        input_name = session.get_inputs()[0].name

        def predict(image, _mask):
            logits = session.run(None, {input_name: normalised(image)})[0][0, 0]
            return logits > 0  # sigmoid(x) >= 0.5  <=>  x >= 0

        return predict, 0  # parameters are counted in the main process

    import torch

    torch.set_grad_enabled(False)
    dev = torch.device(device)

    def count(*models) -> int:
        return sum(p.numel() for m in models for p in m.parameters())

    if name == "resnet34_unet":
        model = load_resnet34_unet().to(dev)

        def predict(image, _mask):
            return (model(torch.from_numpy(normalised(image)).to(dev))[0, 0] > 0).cpu().numpy()

        return predict, count(model)

    if name == "deeplabv3":
        from torch.nn import functional as F
        from torchvision.models.segmentation import DeepLabV3_MobileNet_V3_Large_Weights, deeplabv3_mobilenet_v3_large

        model = deeplabv3_mobilenet_v3_large(weights=DeepLabV3_MobileNet_V3_Large_Weights.COCO_WITH_VOC_LABELS_V1).eval().to(dev)

        def predict(image, _mask):
            x = torch.from_numpy(normalised(image)).to(dev)
            x = F.interpolate(x, size=(520, 520), mode="bilinear", align_corners=False)  # its training resolution
            out = model(x)["out"]
            out = F.interpolate(out, size=image.shape[:2], mode="bilinear", align_corners=False)
            return (out.argmax(1)[0] == VOC_PERSON).cpu().numpy()

        return predict, count(model)

    # SAM-based pipelines
    from transformers import SamModel, SamProcessor

    sam = SamModel.from_pretrained("facebook/sam-vit-base").eval().to(dev)
    processor = SamProcessor.from_pretrained("facebook/sam-vit-base")

    def sam_masks(image: np.ndarray, boxes: list[list[float]]) -> np.ndarray:
        if not boxes:
            return np.zeros(image.shape[:2], bool)
        inputs = processor(Image.fromarray(image), input_boxes=[boxes], return_tensors="pt").to(dev)
        outputs = sam(**inputs, multimask_output=False)
        masks = processor.image_processor.post_process_masks(
            outputs.pred_masks.cpu(), inputs["original_sizes"].cpu(), inputs["reshaped_input_sizes"].cpu()
        )
        return masks[0][:, 0].numpy().any(axis=0)  # union of the people

    if name == "sam_oracle":
        return (lambda image, mask: sam_masks(image, true_boxes(mask))), count(sam)

    from torchvision.models.detection import FasterRCNN_MobileNet_V3_Large_FPN_Weights, fasterrcnn_mobilenet_v3_large_fpn

    detector = fasterrcnn_mobilenet_v3_large_fpn(weights=FasterRCNN_MobileNet_V3_Large_FPN_Weights.COCO_V1).eval().to(dev)

    def detect_then_segment(image, _mask):
        x = torch.from_numpy(image.astype(np.float32) / 255.0).permute(2, 0, 1).to(dev)
        found = detector([x])[0]
        keep = (found["labels"] == COCO_PERSON) & (found["scores"] >= 0.5)
        return sam_masks(image, found["boxes"][keep].cpu().tolist())

    return detect_then_segment, count(sam, detector)


def load_resnet34_unet():
    import segmentation_models_pytorch as smp
    import torch

    model = smp.Unet(encoder_name="resnet34", encoder_weights=None, in_channels=3, classes=1)
    model.load_state_dict(torch.load(PROJECT_ROOT / "backend/weights/baseline_resnet34_unet.pth", map_location="cpu")["state_dict"])
    return model.eval()


def export_resnet34_unet_onnx() -> None:
    """Export the fine-tuned baseline to ONNX (like our model), and check it matches PyTorch."""
    import onnxruntime
    import torch

    path = PROJECT_ROOT / "backend" / "weights" / ONNX_MODELS["resnet34_unet"]
    model = load_resnet34_unet()
    dummy = torch.randn(1, 3, 256, 256)
    torch.onnx.export(model, (dummy,), str(path), input_names=["image"], output_names=["logits"], opset_version=17, dynamo=False)
    session = onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    with torch.no_grad():
        difference = np.abs(session.run(None, {"image": dummy.numpy()})[0] - model(dummy).numpy()).max()
    assert difference < 1e-3, f"ONNX export differs from PyTorch by {difference}"
    print(f"  exported {path.name} (max difference from PyTorch {difference:.1e})", flush=True)


def onnx_parameter_count(name: str) -> int:
    import onnx

    graph = onnx.load(str(PROJECT_ROOT / "backend" / "weights" / ONNX_MODELS[name])).graph
    return sum(int(np.prod(t.dims)) for t in graph.initializer)


# ---------------------------------------------------------------- metrics


def boundary(mask: np.ndarray) -> np.ndarray:
    return mask & ~ndimage.binary_erosion(mask, structure=np.ones((3, 3)))


def scores(pred: np.ndarray, truth: np.ndarray) -> tuple[float, float, float, int, int]:
    """Dice, IoU, boundary F1 (2 px tolerance), and the intersection/total counts for global Dice."""
    inter, total = int((pred & truth).sum()), int(pred.sum() + truth.sum())
    union = int((pred | truth).sum())
    dice = 1.0 if total == 0 else 2 * inter / total
    iou = 1.0 if union == 0 else inter / union
    bp, bt = boundary(pred), boundary(truth)
    if bp.sum() == 0 and bt.sum() == 0:
        bf1 = 1.0
    elif bp.sum() == 0 or bt.sum() == 0:
        bf1 = 0.0
    else:
        precision = (bp & ndimage.binary_dilation(bt, iterations=2)).sum() / bp.sum()
        recall = (bt & ndimage.binary_dilation(bp, iterations=2)).sum() / bt.sum()
        bf1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return dice, iou, float(bf1), inter, total


# ---------------------------------------------------------------- cost (runs in its own process)


def proc_status_mb(field: str) -> float:
    """VmRSS = memory in use now, VmHWM = peak. Both belong to this process only. (getrusage's
    ru_maxrss is NOT usable here: Linux carries it over from the parent process into the child.)"""
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(field + ":"):
            return int(line.split()[1]) / 1024
    raise RuntimeError(f"{field} not found")


def measure_cpu(name: str, samples: int) -> dict:
    """Fresh process, CPU only, 1 thread: median ms per image, and the RAM the model adds (peak minus before loading it)."""
    _, images, masks = load_test_split(limit=samples + 2)
    before = proc_status_mb("VmRSS")
    predict, _ = make_predictor(name, "cpu")
    for i in range(2):  # warm-up
        predict(images[i], masks[i])
    times = []
    for i in range(samples):
        start = time.perf_counter()
        predict(images[i], masks[i])
        times.append((time.perf_counter() - start) * 1000)
    return {"cpu_ms": round(statistics.median(times), 1), "model_ram_mb": round(proc_status_mb("VmHWM") - before)}


def cpu_cost_in_subprocess(name: str, samples: int) -> dict:
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": "", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
    result = subprocess.run(
        [sys.executable, __file__, "--measure-cpu", name, "--samples", str(samples)], env=env, capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


# ---------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--measure-cpu", help=argparse.SUPPRESS)  # internal: child-process mode
    parser.add_argument("--samples", type=int, default=20, help="images timed per model on the CPU")
    parser.add_argument("--models", default=",".join(MODELS))
    args = parser.parse_args()

    if args.measure_cpu:
        if args.measure_cpu not in ONNX_MODELS:  # ONNX models never import PyTorch (like our server)
            import torch

            torch.set_num_threads(1)
        print(json.dumps(measure_cpu(args.measure_cpu, args.samples)))
        return

    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    _, images, masks = load_test_split()
    results, per_image = [], {}
    for name in args.models.split(","):
        print(f"[{name}] quality on {len(images)} test images ({device}) ...", flush=True)
        predict, params = make_predictor(name, device)
        if name in ONNX_MODELS:
            if name != "ours":
                export_resnet34_unet_onnx()
            params = onnx_parameter_count(name)
        rows = [scores(predict(image, mask), mask) for image, mask in zip(images, masks, strict=True)]
        dice = np.array([r[0] for r in rows])
        del predict
        if device == "cuda":
            torch.cuda.empty_cache()
        print(f"[{name}] CPU cost ...", flush=True)
        cost = cpu_cost_in_subprocess(name, args.samples)
        results.append(
            {
                "id": name,
                "name": MODELS[name],
                "params_m": round(params / 1e6, 2),
                "size_mb": round(params * 4 / 1e6, 1),  # float32 weights
                "dice_global": round(2 * sum(r[3] for r in rows) / sum(r[4] for r in rows), 4),
                "dice_mean": round(float(dice.mean()), 4),
                "iou_mean": round(float(np.mean([r[1] for r in rows])), 4),
                "boundary_f1": round(float(np.mean([r[2] for r in rows])), 4),
                "failure_rate": round(float((dice < 0.8).mean()), 4),  # share of images with Dice below 0.8
                **cost,
                "needs_true_box": name == "sam_oracle",
            }
        )
        per_image[name] = [round(float(d), 3) for d in dice]
        print(json.dumps(results[-1]), flush=True)

    # Estimated server peak with each model = the server without a model + that model's RAM.
    ours = next((r for r in results if r["id"] == "ours"), None)
    server_without_model = SERVER_PEAK_WITH_OURS_MB - (ours["model_ram_mb"] if ours else 0)
    for r in results:
        r["peak_mb"] = server_without_model + r["model_ram_mb"]
        r["fits_free_tier"] = r["peak_mb"] <= SERVER_LIMIT_MB

    gpu = torch.cuda.get_device_name(0) if device == "cuda" else None
    report = {
        "meta": {
            "date": date.today().isoformat(),
            "test_images": len(images),
            "resolution": "256 x 256",
            "cpu_threads": 1,
            "gpu_for_quality": gpu,
            "server_limit_mb": SERVER_LIMIT_MB,
            "server_without_model_mb": server_without_model,
        },
        "models": results,
        "per_image_dice": per_image,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=1) + "\n")
    print(f"\nwrote {OUTPUT}\n")
    print("| Model | Dice | IoU | Boundary F1 | CPU ms/image | Model RAM | Server peak (est.) | Weights | Fits 512 MB |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in results:
        print(
            f"| {r['name']} | {r['dice_mean']:.3f} | {r['iou_mean']:.3f} | {r['boundary_f1']:.3f} | {r['cpu_ms']:.0f} | "
            f"{r['model_ram_mb']} MB | {r['peak_mb']} MB | {r['size_mb']} MB | {'yes' if r['fits_free_tier'] else 'no'} |"
        )


if __name__ == "__main__":
    main()
