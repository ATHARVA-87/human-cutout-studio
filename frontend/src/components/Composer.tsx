import { type KeyboardEvent, type PointerEvent, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Composition, SavedPlacement } from "../types";

/** Where the person is, in BACKGROUND-IMAGE pixels: bottom-centre point (their feet) and height. */
interface Placement {
  x: number;
  bottom: number;
  height: number;
}

interface LoadedImages {
  background: HTMLImageElement;
  cutout: HTMLImageElement;
}

const MIN_HEIGHT = 0.05; // fraction of the background height
const MAX_HEIGHT = 2;
const SAVE_DELAY_MS = 500; // autosave this long after the last change

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`Could not load ${url}`));
    image.src = url;
  });
}

/** Start at a believable size: about 70% of the scene height, never wider than 90% of it. */
function initialPlacement({ background, cutout }: LoadedImages, anchorBottom: boolean): Placement {
  const aspect = cutout.naturalWidth / cutout.naturalHeight;
  const height = Math.min(background.naturalHeight * (anchorBottom ? 0.6 : 0.7), (background.naturalWidth * 0.9) / aspect);
  const bottom = anchorBottom ? background.naturalHeight : background.naturalHeight * 0.92;
  return { x: background.naturalWidth / 2, bottom, height };
}

/** Saved fractions (0-1 of the background) -> pixels of this background image, and back. */
function fromSaved(saved: SavedPlacement, background: HTMLImageElement): Placement {
  return { x: saved.x * background.naturalWidth, bottom: saved.bottom * background.naturalHeight, height: saved.height * background.naturalHeight };
}
function toSaved(place: Placement, mirrored: boolean, background: HTMLImageElement): SavedPlacement {
  return { x: place.x / background.naturalWidth, bottom: place.bottom / background.naturalHeight, height: place.height / background.naturalHeight, mirrored };
}

type SaveState = "idle" | "saving" | "saved" | "error";

interface ComposerProps {
  item: Composition;
  onSaved?: (placement: SavedPlacement) => void; // lets the parent keep its copy of the composition up to date
}

export function Composer({ item, onSaved }: ComposerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [images, setImages] = useState<LoadedImages>();
  const [place, setPlace] = useState<Placement>();
  const [mirrored, setMirrored] = useState(false);
  const [loadError, setLoadError] = useState<string>();
  const [saveState, setSaveState] = useState<SaveState>("idle");
  // Autosave bookkeeping: `edited` is set only by the user's actions (so opening the editor never
  // overwrites a saved placement); `pending` holds a change that hasn't been sent yet.
  const edited = useRef(false);
  const pending = useRef<SavedPlacement | null>(null);
  // While dragging: the distance between the pointer and the person's feet, so the person
  // does not jump to the cursor; it moves exactly as far as the mouse moves.
  const grab = useRef<{ dx: number; dy: number } | null>(null);

  // 1) Load both images once per composition.
  useEffect(() => {
    let cancelled = false;
    setLoadError(undefined);
    Promise.all([loadImage(item.background_url), loadImage(item.cutout_url)])
      .then(([background, cutout]) => {
        if (cancelled) return;
        setImages({ background, cutout });
        // Continue where the user left off, if this composition was edited before.
        setPlace(item.placement ? fromSaved(item.placement, background) : initialPlacement({ background, cutout }, item.anchor_bottom));
        setMirrored(item.placement?.mirrored ?? false);
        edited.current = false;
      })
      .catch(() => !cancelled && setLoadError("The images could not be loaded (the free server may have restarted). Please create the composition again."));
    return () => {
      cancelled = true;
    };
  }, [item.id, item.background_url, item.cutout_url]); // not [item]: saving a placement updates the object, which must not reload

  // 2) Redraw whenever the placement changes.
  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context || !images || !place) return;
    const { background, cutout } = images;
    canvas.width = background.naturalWidth;
    canvas.height = background.naturalHeight;
    context.drawImage(background, 0, 0);

    const width = place.height * (cutout.naturalWidth / cutout.naturalHeight);
    if (!item.anchor_bottom) {
      // Soft contact shadow under the feet, so a full-body person looks like they stand on the ground.
      context.save();
      context.filter = `blur(${Math.max(2, width * 0.04)}px)`;
      context.fillStyle = "rgba(0, 0, 0, 0.35)";
      context.beginPath();
      context.ellipse(place.x, place.bottom - place.height * 0.01, width * 0.35, Math.max(3, place.height * 0.025), 0, 0, Math.PI * 2);
      context.fill();
      context.restore();
    }
    context.save();
    context.translate(place.x, 0);
    context.scale(mirrored ? -1 : 1, 1);
    context.drawImage(cutout, -width / 2, place.bottom - place.height, width, place.height);
    context.restore();
  }, [images, place, mirrored, item.anchor_bottom]);

  // Autosave: SAVE_DELAY_MS after the last change, send the placement to the server.
  const save = (placement: SavedPlacement) => {
    pending.current = null;
    setSaveState("saving");
    api
      .savePlacement(item.id, placement)
      .then(() => {
        setSaveState("saved");
        onSaved?.(placement);
      })
      .catch(() => setSaveState("error"));
  };
  useEffect(() => {
    if (!edited.current || !place || !images) return;
    pending.current = toSaved(place, mirrored, images.background);
    setSaveState("saving");
    const timer = window.setTimeout(() => pending.current && save(pending.current), SAVE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [place, mirrored]); // re-run (and restart the timer) only when the placement changes
  // If the editor closes before the timer fires, send the last change right away.
  useEffect(
    () => () => {
      if (pending.current) save(pending.current);
    },
    [], // empty list: the cleanup runs once, when the editor closes
  );

  /** Every user action goes through here, which marks the placement as edited (so it gets saved). */
  const edit = (next: Placement | ((current: Placement | undefined) => Placement | undefined)) => {
    edited.current = true;
    setPlace(next);
  };

  /** Resize around the feet (bottom-centre), so the person stays standing in the same spot. */
  const resize = (factor: number) => {
    if (!images) return;
    edited.current = true;
    const sceneHeight = images.background.naturalHeight;
    setPlace((current) =>
      current && { ...current, height: Math.min(sceneHeight * MAX_HEIGHT, Math.max(sceneHeight * MIN_HEIGHT, current.height * factor)) },
    );
  };

  // 3) Mouse wheel zooms the person. React registers wheel listeners as "passive", where
  // preventDefault() is ignored and the page scrolls too, so we attach a native listener instead.
  // Outside the canvas the wheel scrolls the page as usual.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      resize(event.deltaY < 0 ? 1.08 : 1 / 1.08);
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  });

  /** Screen (CSS) pixels -> background-image pixels. The canvas box has the image's exact aspect ratio. */
  const toImagePoint = (event: PointerEvent<HTMLCanvasElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const scale = event.currentTarget.width / box.width;
    return { x: (event.clientX - box.left) * scale, y: (event.clientY - box.top) * scale };
  };

  const onPointerDown = (event: PointerEvent<HTMLCanvasElement>) => {
    if (!images || !place) return;
    const point = toImagePoint(event);
    const width = place.height * (images.cutout.naturalWidth / images.cutout.naturalHeight);
    const onPerson =
      point.x >= place.x - width / 2 && point.x <= place.x + width / 2 && point.y >= place.bottom - place.height && point.y <= place.bottom;
    if (!onPerson) return;
    grab.current = { dx: point.x - place.x, dy: point.y - place.bottom };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: PointerEvent<HTMLCanvasElement>) => {
    if (!grab.current || !images || !place) return;
    const point = toImagePoint(event);
    const { naturalWidth: sceneWidth, naturalHeight: sceneHeight } = images.background;
    const x = Math.min(sceneWidth, Math.max(0, point.x - grab.current.dx));
    // A half-body person stays glued to the bottom edge: only horizontal movement.
    const bottom = item.anchor_bottom ? sceneHeight : Math.min(sceneHeight + place.height / 2, Math.max(place.height * 0.2, point.y - grab.current.dy));
    edit({ ...place, x, bottom });
  };

  const stopDragging = () => {
    grab.current = null;
  };

  const download = () => {
    const anchor = document.createElement("a");
    anchor.download = "composition.png";
    anchor.href = canvasRef.current?.toDataURL("image/png") ?? "";
    anchor.click();
  };

  /** Keyboard editing (accessibility): arrows move the person, + and - resize. Shift moves further. */
  const onKeyDown = (event: KeyboardEvent<HTMLCanvasElement>) => {
    if (!images || !place) return;
    const { naturalWidth: sceneWidth, naturalHeight: sceneHeight } = images.background;
    const step = (event.shiftKey ? 0.05 : 0.01) * sceneWidth;
    const moves: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (event.key in moves) {
      event.preventDefault();
      const [dx, dy] = moves[event.key];
      const x = Math.min(sceneWidth, Math.max(0, place.x + dx));
      const bottom = item.anchor_bottom ? sceneHeight : Math.min(sceneHeight + place.height / 2, Math.max(place.height * 0.2, place.bottom + dy));
      edit({ ...place, x, bottom });
    } else if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      resize(1.08);
    } else if (event.key === "-") {
      event.preventDefault();
      resize(1 / 1.08);
    }
  };

  const sizePercent = images && place ? Math.round((place.height / images.background.naturalHeight) * 100) : 0;

  return (
    <div className="result-card">
      <div className="mat-head">
        <h2>Place the person</h2>
        <p>{item.anchor_bottom ? "Their photo was cut off at the bottom, so they stay on the bottom edge." : "A soft shadow keeps their feet on the ground."}</p>
      </div>
      <div className="canvas-frame">
        <canvas
          ref={canvasRef}
          className="canvas"
          tabIndex={0}
          aria-label="Editor. Drag the person, or use the arrow keys to move and plus or minus to resize."
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={stopDragging}
          onPointerCancel={stopDragging}
          onKeyDown={onKeyDown}
        />
      </div>
      {loadError && (
        <p className="notice" role="alert">
          {loadError}
        </p>
      )}
      <div className="toolbar">
        <button
          className="button on-mat-outline"
          onClick={() => {
            edited.current = true;
            setMirrored((value) => !value);
          }}
          aria-pressed={mirrored}
        >
          Mirror
        </button>
        <label className="size-control">
          <span>Size {sizePercent}%</span>
          <input
            type="range"
            min={MIN_HEIGHT * 100}
            max={MAX_HEIGHT * 100}
            value={sizePercent}
            onChange={(event) =>
              images && edit((current) => current && { ...current, height: (Number(event.target.value) / 100) * images.background.naturalHeight })
            }
          />
        </label>
        <button className="button on-mat" onClick={download} disabled={!images}>
          Download image
        </button>
      </div>
      <p className="editor-hint">
        Drag the person to move them. Scroll over the photo or use the slider to resize. Arrow keys work too.{" "}
        <span role="status">
          {saveState === "saving" && "Saving…"}
          {saveState === "saved" && "Your changes are saved."}
          {saveState === "error" && "Couldn't save your changes. They'll be saved with your next change."}
          {saveState === "idle" && (item.placement ? "Continuing where you left off." : "Changes save automatically.")}
        </span>
      </p>
    </div>
  );
}
