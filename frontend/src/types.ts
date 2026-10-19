// Shapes of the JSON the backend returns (see backend/app/schemas.py).

export interface Account {
  email: string;
  credits: number;
}

export interface Prediction {
  id: string;
  created_at: string;
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

export interface Composition {
  id: string;
  background_url: string;
  cutout_url: string;
  anchor_bottom: boolean; // person is cut off at the bottom of the photo -> keep them on the bottom edge
  credits: number;
}

// Must match backend/app/services/jobs.py
export const SEGMENT_COST = 1;
export const COMPOSE_COST = 2;
