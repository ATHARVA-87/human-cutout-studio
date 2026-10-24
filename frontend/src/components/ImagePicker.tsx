import { type DragEvent, useEffect, useState } from "react";

const ALLOWED_TYPES = ["image/jpeg", "image/png"];
const MAX_BYTES = 10 * 1024 * 1024; // must match SEGMENTATION_MAX_UPLOAD_BYTES on the server

interface ImagePickerProps {
  label: string;
  file?: File;
  onPick: (file: File) => void;
  onError: (message: string) => void;
}

/** Click, keyboard or drag-and-drop a JPG/PNG under 10 MB. The server checks again; this gives fast feedback. */
export function ImagePicker({ label, file, onPick, onError }: ImagePickerProps) {
  const [dragging, setDragging] = useState(false);
  const [preview, setPreview] = useState<string>();

  // Show a small preview of the chosen photo; free the temporary URL when it changes.
  useEffect(() => {
    if (!file) return setPreview(undefined);
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const accept = (chosen?: File) => {
    if (!chosen) return;
    if (!ALLOWED_TYPES.includes(chosen.type)) return onError("That file isn't a JPG or PNG. Choose a JPG or PNG photo.");
    if (chosen.size > MAX_BYTES) return onError("That photo is over 10 MB. Choose a smaller one or resize it first.");
    onPick(chosen);
  };

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragging(false);
    accept(event.dataTransfer.files[0]);
  };

  return (
    <label
      className={dragging ? "dropzone dragging" : "dropzone"}
      onDragOver={(event) => {
        event.preventDefault(); // allow dropping
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      {preview ? <img className="dropzone-preview" src={preview} alt="" /> : <span className="dropzone-preview" aria-hidden="true">+</span>}
      <span>
        <strong>{file ? file.name : label}</strong>
        <span>{file ? "Click to choose a different photo" : "Click or drop a JPG or PNG up to 10 MB"}</span>
      </span>
      <input
        className="visually-hidden"
        type="file"
        accept={ALLOWED_TYPES.join(",")}
        onChange={(event) => {
          accept(event.target.files?.[0]);
          event.target.value = ""; // allow choosing the same file again
        }}
      />
    </label>
  );
}
