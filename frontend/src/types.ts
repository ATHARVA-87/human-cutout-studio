// Shapes of the JSON the backend returns (see backend/app/schemas.py).

export interface Account {
  email: string;
  credits: number;
  email_verified: boolean; // jobs are allowed only after the link in the verification email is opened
  retention_days: number; // uploads and results are deleted after this many days
}

export interface Prediction {
  id: string;
  created_at: string;
  expires_at: string;
  original_filename: string;
  source_width: number;
  source_height: number;
  foreground_fraction: number;
  model_version: string;
  original_url: string;
  mask_url: string;
  overlay_url: string;
  cutout_url: string;
  credits: number | null;
}

/** Where the person was left in the editor, as fractions of the background image (saved on the server). */
export interface SavedPlacement {
  x: number;
  bottom: number;
  height: number;
  mirrored: boolean;
}

export interface Composition {
  id: string;
  created_at: string;
  expires_at: string;
  background_url: string;
  cutout_url: string;
  anchor_bottom: boolean; // person is cut off at the bottom of the photo -> keep them on the bottom edge
  placement: SavedPlacement | null; // null until the user moves something in the editor
  credits: number | null;
}

export interface Page<T> {
  items: T[];
  total: number;
}

// Must match backend/app/services/jobs.py
export const SEGMENT_COST = 1;
export const COMPOSE_COST = 2;
// Must match SEGMENTATION_RETENTION_DAYS on the server (shown on the public Privacy page).
export const RETENTION_DAYS = 5;
