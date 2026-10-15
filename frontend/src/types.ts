export type OperationId = "segment_person" | "replace_background";

export interface Capability {
  id: OperationId;
  status: "ready" | "unavailable" | "planned";
}

export interface Prediction {
  id: string;
  created_at: string;
  operation: OperationId;
  original_filename: string;
  source_width: number;
  source_height: number;
  foreground_fraction: number;
  model_version: string;
  original_url: string;
  mask_url: string;
  overlay_url: string;
  cutout_url: string | null;
}
export interface Account { email: string; credits: number }
export interface Composition { id: string; background_url: string; cutout_url: string; credits: number }
