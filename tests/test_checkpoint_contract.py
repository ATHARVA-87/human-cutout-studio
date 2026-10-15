from segmentation.checkpoints import ARCHITECTURE_UNET_V1, parse_checkpoint


def test_v1_checkpoint_metadata_remains_compatible() -> None:
    spec = parse_checkpoint({
        "format_version": 1,
        "model_config": {"in_channels": 3, "out_channels": 1, "base_channels": 32, "dropout": 0.2},
        "state_dict": {},
        "preprocessing": {"image_size": 256, "mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]},
        "epoch": 38,
        "best_validation_dice": 0.9229,
    })
    assert spec.architecture == ARCHITECTURE_UNET_V1
    assert (spec.preprocessing.input_height, spec.preprocessing.input_width) == (256, 256)
    assert spec.preprocessing.resize_strategy == "stretch"


def test_v2_checkpoint_can_declare_a_new_input_size_and_strategy() -> None:
    spec = parse_checkpoint({
        "format_version": 2,
        "architecture": ARCHITECTURE_UNET_V1,
        "model_config": {"in_channels": 3, "out_channels": 1, "base_channels": 32, "dropout": 0.2},
        "state_dict": {},
        "preprocessing": {"input_size": [512, 384], "mean": [0.4, 0.5, 0.6], "std": [0.2, 0.3, 0.4], "resize_strategy": "letterbox", "output_threshold": 0.6},
        "epoch": 1,
        "best_validation_dice": 0.5,
    })
    assert (spec.preprocessing.input_height, spec.preprocessing.input_width) == (512, 384)
    assert spec.preprocessing.output_threshold == 0.6
