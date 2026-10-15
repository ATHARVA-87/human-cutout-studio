import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Composition } from "../types";

export function Composer({ item }: { item: Composition }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [scale, setScale] = useState(0.45);
  const [mirrored, setMirrored] = useState(false);
  const [point, setPoint] = useState({ x: 0.5, y: 0.5 });
  const dragging = useRef(false);

  useEffect(() => {
    const background = new Image();
    const cutout = new Image();
    background.src = api.assetUrl(item.background_url);
    cutout.src = api.assetUrl(item.cutout_url);
    const draw = () => {
      const element = canvas.current;
      if (!element || !background.complete || !cutout.complete) return;
      const context = element.getContext("2d");
      if (!context) return;
      element.width = background.naturalWidth;
      element.height = background.naturalHeight;
      context.drawImage(background, 0, 0);
      const width = cutout.naturalWidth * scale;
      const height = cutout.naturalHeight * scale;
      const x = element.width * point.x - width / 2;
      const y = element.height * point.y - height / 2;
      context.save();
      context.translate(x + width / 2, y + height / 2);
      context.scale(mirrored ? -1 : 1, 1);
      context.drawImage(cutout, -width / 2, -height / 2, width, height);
      context.restore();
    };
    background.onload = draw;
    cutout.onload = draw;
    draw();
  }, [item, scale, mirrored, point]);

  const move = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!dragging.current) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    setPoint({ x: (event.clientX - bounds.left) / bounds.width, y: (event.clientY - bounds.top) / bounds.height });
  };

  const download = () => {
    const anchor = document.createElement("a");
    anchor.download = "composition.png";
    anchor.href = canvas.current?.toDataURL("image/png") ?? "";
    anchor.click();
  };

  return <section className="result-card">
    <div className="result-heading"><div><p className="eyebrow">Compose</p><h2>Place your cutout</h2></div><button className="mirror" onClick={() => setMirrored(value => !value)}>↔ Mirror</button></div>
    <canvas ref={canvas} className="canvas" onPointerDown={event => { dragging.current = true; event.currentTarget.setPointerCapture(event.pointerId); }} onPointerUp={() => { dragging.current = false; }} onPointerMove={move} onWheel={event => { event.preventDefault(); setScale(value => Math.max(0.1, Math.min(1.5, value * (event.deltaY < 0 ? 1.1 : 0.9)))); }} />
    <p className="muted">Drag the person to move it. Scroll over the image to resize it.</p>
    <button className="download" onClick={download}>Download image</button>
  </section>;
}
