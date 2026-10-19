const ALLOWED_TYPES = ["image/jpeg", "image/png"];
const MAX_BYTES = 10 * 1024 * 1024; // must match SEGMENTATION_MAX_UPLOAD_BYTES on the server

interface ImagePickerProps {
  label: string;
  file?: File;
  onPick: (file: File) => void;
  onError: (message: string) => void;
}

/** A file chooser that accepts only JPG/PNG under 10 MB. The server checks again; this is for fast feedback. */
export function ImagePicker({ label, file, onPick, onError }: ImagePickerProps) {
  const accept = (chosen?: File) => {
    if (!chosen) return;
    if (!ALLOWED_TYPES.includes(chosen.type)) return onError("Only JPG and PNG images are supported.");
    if (chosen.size > MAX_BYTES) return onError("Choose an image smaller than 10 MB.");
    onPick(chosen);
  };

  return (
    <label className="dropzone">
      <strong>{file ? file.name : label}</strong>
      <span>JPG or PNG · up to 10 MB</span>
      <input
        hidden
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
