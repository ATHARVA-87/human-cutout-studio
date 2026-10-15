# Application architecture

## Current request flow

```text
React client → FastAPI route → rate-limit policy → segmentation service
                                      ↓                    ↓
                                PostgreSQL usage       trained checkpoint
                                      ↓                    ↓
                              prediction metadata ← local artifact storage
```

The API records the original image, binary mask, overlay, source dimensions, model version, and foreground percentage. Raw media is held under `uploads/` and model weights under `backend/weights/`; both stay out of Git.

## Extending image operations

The public response has an `operation` field and `/api/capabilities` advertises enabled operations. `segment_person` is the first operation. A future `replace_background` operation should:

1. Reuse `SegmentationService` to obtain the foreground mask.
2. Validate a second user-provided background image.
3. Composite foreground and background in a dedicated image-editing service.
4. Store the background and resulting composite as additional artifacts.
5. Persist the same operation, model version, and artifact metadata.

This keeps model inference, compositing, persistence, and HTTP validation independently testable.

## Checkpoint contract

`model.pth` is the versioned boundary between training and inference. The current API supports metadata format v1 for the trained 256×256 checkpoint and emits format v2 on later training runs. Format v2 records an architecture ID, model configuration, input size, normalization, resize strategy (`stretch` or `letterbox`), and output threshold. The application obtains these values from the checkpoint at startup; it does not hard-code `256` or ImageNet normalization in the HTTP layer.

Replacing a compatible trained checkpoint therefore requires a verifier run and API restart, not a frontend redeploy. A different architecture must be registered in the model factory, which prevents accidental loading of an unknown or incompatible checkpoint.

## Rate limiting

`UsageEvent` records a salted SHA-256 hash of the client address and time. The default policy permits five prediction operations in the trailing hour. In a multi-instance deployment, PostgreSQL is shared by every API container, unlike in-memory rate limiting. Replace the client identifier with authenticated user IDs when accounts are introduced; configure `SEGMENTATION_RATE_LIMIT_SALT` outside source control.
