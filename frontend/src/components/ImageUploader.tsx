import { type ChangeEvent, type DragEvent, useRef, useState } from "react";

interface ImageUploaderProps {
  disabled: boolean;
  onSelect: (file: File) => void;
}

const validTypes = new Set(["image/jpeg", "image/png", "image/webp"]);

export function ImageUploader({ disabled, onSelect }: ImageUploaderProps) {
  const input = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<string>();

  const accept = (file?: File) => {
    if (!file) return;
    if (!validTypes.has(file.type)) {
      setMessage("Use a JPG, PNG, or WebP image.");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setMessage("Choose an image below 10 MB.");
      return;
    }
    setMessage(undefined);
    onSelect(file);
  };

  const drop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    accept(event.dataTransfer.files[0]);
  };

  return (
    <section className="upload-card">
      <p className="eyebrow">Input image</p>
      <h2>Cut out a person</h2>
      <p className="muted">Upload a photo and the model returns a binary mask and a clean preview overlay.</p>
      <button className="dropzone" type="button" disabled={disabled} onDrop={drop} onDragOver={(event) => event.preventDefault()} onClick={() => input.current?.click()}>
        <span className="upload-icon">↑</span>
        <strong>Drop an image here</strong>
        <span>or choose a file · JPG, PNG, WebP · up to 10 MB</span>
      </button>
      <input ref={input} hidden type="file" accept="image/jpeg,image/png,image/webp" onChange={(event: ChangeEvent<HTMLInputElement>) => accept(event.target.files?.[0])} />
      {message && <p className="input-error">{message}</p>}
    </section>
  );
}
