"""Configurable U-Net for one-class segmentation."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import torch
from torch import nn
from torch.nn import functional as F


@dataclass(frozen=True)
class UNetConfig:
    in_channels: int = 3
    out_channels: int = 1
    base_channels: int = 32
    dropout: float = 0.2

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


class DoubleConv(nn.Sequential):
    def __init__(self, in_channels: int, out_channels: int, dropout: float = 0.0) -> None:
        layers: list[nn.Module] = [
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        ]
        if dropout:
            layers.append(nn.Dropout2d(dropout))
        super().__init__(*layers)


class Down(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, dropout: float = 0.0) -> None:
        super().__init__()
        self.layers = nn.Sequential(nn.MaxPool2d(2), DoubleConv(in_channels, out_channels, dropout))

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.layers(value)


class Up(nn.Module):
    def __init__(self, in_channels: int, skip_channels: int, out_channels: int, dropout: float = 0.0) -> None:
        super().__init__()
        self.up = nn.ConvTranspose2d(in_channels, out_channels, kernel_size=2, stride=2)
        self.conv = DoubleConv(out_channels + skip_channels, out_channels, dropout)

    def forward(self, value: torch.Tensor, skip: torch.Tensor) -> torch.Tensor:
        value = self.up(value)
        if value.shape[-2:] != skip.shape[-2:]:
            value = F.interpolate(value, size=skip.shape[-2:], mode="bilinear", align_corners=False)
        return self.conv(torch.cat((skip, value), dim=1))


class UNet(nn.Module):
    """Four-level encoder-decoder U-Net with skip connections and deep dropout."""

    def __init__(self, config: UNetConfig = UNetConfig()) -> None:
        super().__init__()
        self.config = config
        c = config.base_channels
        self.stem = DoubleConv(config.in_channels, c)
        self.down1 = Down(c, c * 2)
        self.down2 = Down(c * 2, c * 4)
        self.down3 = Down(c * 4, c * 8, config.dropout / 2)
        self.down4 = Down(c * 8, c * 16, config.dropout)
        self.up1 = Up(c * 16, c * 8, c * 8, config.dropout / 2)
        self.up2 = Up(c * 8, c * 4, c * 4)
        self.up3 = Up(c * 4, c * 2, c * 2)
        self.up4 = Up(c * 2, c, c)
        self.head = nn.Conv2d(c, config.out_channels, kernel_size=1)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        x1 = self.stem(value)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)
        x5 = self.down4(x4)
        return self.head(self.up4(self.up3(self.up2(self.up1(x5, x4), x3), x2), x1))
