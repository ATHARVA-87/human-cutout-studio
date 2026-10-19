"""Training -> serving contract: a PyTorch U-Net exported to ONNX must load and run in the web server's service."""

from pathlib import Path

from PIL import Image

from backend.app.services.inference import SegmentationService
from segmentation.checkpoints import checkpoint_payload, parse_checkpoint
from segmentation.export import export_to_onnx
from segmentation.models import UNet, UNetConfig


def test_exported_model_runs_in_the_server_service(tmp_path: Path) -> None:
    model = UNet(UNetConfig(base_channels=4, dropout=0.0))  # tiny random network: fast, no real weights needed
    spec = parse_checkpoint(checkpoint_payload(model, {"image_size": 64}, epoch=1, best_validation_dice=0.5))
    onnx_path = tmp_path / "model.onnx"
    export_to_onnx(model, spec, onnx_path)

    service = SegmentationService(onnx_path)
    service.load()
    assert service.preprocessing.input_height == 64
    assert service.model_version == "unet.v1-epoch-1-dice-0.5000"

    result = service.predict(Image.new("RGB", (120, 90), (100, 150, 100)))
    assert result.mask.size == (120, 90)  # back at the original size
    assert result.cutout.mode == "RGBA"
    assert 0.0 <= result.foreground_fraction <= 1.0
