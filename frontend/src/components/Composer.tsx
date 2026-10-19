import { type PointerEvent, useEffect, useRef, useState } from "react";
import type { Composition } from "../types";

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

export function Composer({ item }: { item: Composition }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [images, setImages] = useState<LoadedImages>();
  const [place, setPlace] = useState<Placement>();
  const [mirrored, setMirrored] = useState(false);
  // While dragging: the distance between the pointer and the person's feet, so the person
  // does not jump to the cursor; it moves exactly as far as the mouse moves.
  const grab = useRef<{ dx: number; dy: number } | null>(null);

  // 1) Load both images once per composition.
  useEffect(() => {
    let cancelled = false;
    Promise.all([loadImage(item.background_url), loadImage(item.cutout_url)]).then(([background, cutout]) => {
      if (cancelled) return;
      setImages({ background, cutout });
      setPlace(initialPlacement({ background, cutout }, item.anchor_bottom));
      setMirrored(false);
    });
    return () => {
      cancelled = true;
    };
  }, [item]);

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

  /** Resize around the feet (bottom-centre), so the person stays standing in the same spot. */
  const resize = (factor: number) => {
    if (!images) return;
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
    setPlace({ ...place, x, bottom });
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

  const sizePercent = images && place ? Math.round((place.height / images.background.naturalHeight) * 100) : 0;

  return (
    <section className="result-card">
      <div className="result-heading">
        <div>
          <p className="eyebrow">Compose</p>
          <h2>Place your cutout</h2>
        </div>
        <button className="mirror" onClick={() => setMirrored((value) => !value)}>
          ↔ Mirror
        </button>
      </div>
      <div className="canvas-frame">
        <canvas
          ref={canvasRef}
          className="canvas"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={stopDragging}
          onPointerCancel={stopDragging}
        />
      </div>
      <label className="size-control">
        Size {sizePercent}%
        <input
          type="range"
          min={MIN_HEIGHT * 100}
          max={MAX_HEIGHT * 100}
          value={sizePercent}
          onChange={(event) => images && setPlace((current) => current && { ...current, height: (Number(event.target.value) / 100) * images.background.naturalHeight })}
        />
      </label>
      <p className="muted">
        Drag the person to move them. Scroll over the image or use the slider to resize.
        {item.anchor_bottom && " This photo cuts the person off at the bottom, so they stay on the bottom edge."}
      </p>
      <button className="primary" onClick={download} disabled={!images}>
        Download image
      </button>
    </section>
  );
}
