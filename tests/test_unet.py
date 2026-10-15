import torch

from segmentation.models import UNet, UNetConfig


def test_unet_preserves_256_square_spatial_shape() -> None:
    model = UNet(UNetConfig(base_channels=8, dropout=0.1))
    assert model(torch.randn(2, 3, 256, 256)).shape == (2, 1, 256, 256)

