# U-Net model

The model in [unet.py](./unet.py) follows the legacy U-Net baseline without copying its project structure:

```text
RGB image (3 × 256 × 256)
  → DoubleConv(32)
  → Down(64) → Down(128) → Down(256) → Down(512)
  → Up(256)  → Up(128)   → Up(64)     → Up(32)
  → 1-channel logits (1 × 256 × 256)
```

Every `Up` stage concatenates the matching encoder feature map before its `DoubleConv`, preserving standard U-Net skip connections. The output is a logit, not an already-thresholded mask; training uses `BCEWithLogitsLoss` plus soft Dice loss, and inference applies `sigmoid` followed by a threshold of `0.5`.

## Dropout

`dropout` is configured in [train.json](../../../configs/train.json). A value of `0.2` applies `Dropout2d(0.1)` after the `Down(256)` block, `Dropout2d(0.2)` after the deepest `Down(512)` block, and `Dropout2d(0.1)` after the first decoder block. Shallow feature maps do not receive dropout so edge detail is retained.

## Hyperparameters

Training controls live in JSON, rather than YAML, to keep installation beginner-friendly: Python can read JSON with its standard library, whereas YAML adds a parser dependency. Update `base_channels`, `dropout`, batch size, optimizer settings, or epochs in [train.json](../../../configs/train.json); the training script records these settings in every best checkpoint.

## Train

After installing the dependencies and preparing data, run from the repository root:

```bash
python scripts/train.py \
  --config configs/train.json \
  --data-root data/processed \
  --checkpoint backend/weights/model.pth
```

The trainer writes `backend/weights/model.pth` only when validation Dice improves. Verify its model configuration, learned state dictionary, and a 256×256 inference pass with:

```bash
python scripts/verify_checkpoint.py --checkpoint backend/weights/model.pth
```

## Initial trained checkpoint

Training completed for 40 epochs. The selected checkpoint is from epoch 38, where validation Dice reached `0.9229` and validation loss was `0.2336`. The epoch-40 weights were not saved as the best model because their validation Dice (`0.9171`) was lower. A fresh-process reload and inference check passed with output shape `(1, 1, 256, 256)`.
