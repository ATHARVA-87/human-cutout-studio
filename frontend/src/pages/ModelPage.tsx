import { type ReactNode, useCallback, useRef, useState } from "react";
import benchmark from "../data/benchmark.json";

/** Results of scripts/benchmark_models.py (same 268 untouched test images for every model). */
interface ModelResult {
  id: string;
  name: string;
  params_m: number;
  size_mb: number;
  dice_global: number;
  dice_mean: number;
  iou_mean: number;
  boundary_f1: number;
  failure_rate: number;
  cpu_ms: number;
  model_ram_mb: number; // RAM that loading and running the model adds
  peak_mb: number; // estimated server peak: the server without a model + model_ram_mb
  fits_free_tier: boolean;
  needs_true_box: boolean;
}

const data = benchmark as unknown as {
  meta: { date: string; test_images: number; resolution: string; server_limit_mb: number; server_without_model_mb: number; gpu_for_quality: string | null };
  models: ModelResult[];
  per_image_dice: Record<string, number[]>;
};
const OURS = "ours";
const models = data.models;
const ours = models.find((m) => m.id === OURS)!;

const pct = (value: number) => `${(value * 100).toFixed(1)}`;
const ms = (value: number) => (value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${Math.round(value)} ms`);
const shortName: Record<string, string> = {
  ours: "Ours (from scratch)",
  resnet34_unet: "Pretrained ResNet-34 U-Net",
  deeplabv3: "DeepLabV3 (off the shelf)",
  sam_detector: "Detector + SAM",
  sam_oracle: "SAM + true box",
};

// ---------------------------------------------------------------- shared tooltip

interface Tip {
  x: number;
  y: number;
  title: string;
  lines: string[];
}

function useTooltip() {
  const [tip, setTip] = useState<Tip>();
  const show = (event: React.PointerEvent | React.FocusEvent, title: string, lines: string[]) => {
    const box = (event.currentTarget as Element).getBoundingClientRect();
    const frame = (event.currentTarget as Element).closest(".viz-card")!.getBoundingClientRect();
    setTip({ x: box.left - frame.left + box.width / 2, y: box.top - frame.top, title, lines });
  };
  const hide = () => setTip(undefined);
  const node = tip && (
    <div className="viz-tip" style={{ left: tip.x, top: tip.y }} role="status">
      {tip.lines.map((line, i) => (
        <strong key={line} className={i === 0 ? "viz-tip-value" : "viz-tip-extra"}>
          {line}
        </strong>
      ))}
      <span>{tip.title}</span>
    </div>
  );
  return { show, hide, node };
}

function Card({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <figure className="viz-card">
      <figcaption>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </figcaption>
      {children}
    </figure>
  );
}

// ---------------------------------------------------------------- responsive width
// Charts draw in real pixels at the width they get, so text stays 12px on a phone and on a wide screen.

function useWidth(initial = 560) {
  const [width, setWidth] = useState(initial);
  const observer = useRef<ResizeObserver | null>(null);
  const ref = useCallback((node: HTMLDivElement | null) => {
    observer.current?.disconnect();
    if (!node) return;
    setWidth(node.clientWidth || initial);
    observer.current = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    observer.current.observe(node);
  }, [initial]);
  return [ref, Math.max(280, width)] as const;
}

const NARROW = 460; // below this, row labels move above their bar or strip

// ---------------------------------------------------------------- horizontal bars (one series: ours highlighted)

interface BarRow {
  id: string;
  label: string;
  value: number;
  text: string;
  extra?: string;
}

function BarChart({ rows, max, refs = [], tipTitle }: { rows: BarRow[]; max: number; refs?: { value: number; label: string }[]; tipTitle: string }) {
  const { show, hide, node } = useTooltip();
  const [frame, width] = useWidth();
  const narrow = width < NARROW;
  const labelWidth = narrow ? 0 : 180;
  const plot = width - labelWidth - 64; // room for the value text after the bar
  const rowHeight = narrow ? 42 : 32;
  const barHeight = narrow ? 14 : 16;
  const top = refs.length ? 22 : 4;
  const height = top + rows.length * rowHeight + 4;
  const x = (value: number) => labelWidth + (Math.min(value, max) / max) * plot;
  return (
    <div className="viz-frame" ref={frame}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={tipTitle}>
        {refs.map((ref) => (
          <g key={ref.label}>
            <line className="viz-ref" x1={x(ref.value)} x2={x(ref.value)} y1={top - 6} y2={height - 2} />
            <text className="viz-ref-label" x={x(ref.value)} y={top - 10} textAnchor="middle">
              {ref.label}
            </text>
          </g>
        ))}
        {!narrow && <line className="viz-axis" x1={labelWidth} x2={labelWidth} y1={top - 2} y2={height - 2} />}
        {rows.map((row, i) => {
          const y = top + i * rowHeight;
          const barY = narrow ? y + rowHeight - barHeight - 6 : y + (rowHeight - barHeight) / 2;
          const barWidth = Math.max(2, x(row.value) - labelWidth);
          const lines = [row.text, ...(row.extra ? [row.extra] : [])];
          return (
            <g
              key={row.id}
              className={row.id === OURS ? "viz-mark ours" : "viz-mark"}
              tabIndex={0}
              onPointerEnter={(e) => show(e, row.label, lines)}
              onPointerLeave={hide}
              onFocus={(e) => show(e, row.label, lines)}
              onBlur={hide}
            >
              <rect className="viz-hit" x={0} y={y} width={width} height={rowHeight} />
              <text
                className="viz-label"
                x={narrow ? 0 : labelWidth - 10}
                y={narrow ? barY - 5 : barY + barHeight / 2 + 4}
                textAnchor={narrow ? "start" : "end"}
              >
                {row.label}
              </text>
              {/* 4px rounded data end, square at the baseline */}
              <path className="viz-bar" d={barPath(labelWidth, barY, barWidth, barHeight)} />
              <text className="viz-value" x={labelWidth + barWidth + 6} y={barY + barHeight / 2 + 4}>
                {row.text}
              </text>
            </g>
          );
        })}
      </svg>
      {node}
    </div>
  );
}

function barPath(x: number, y: number, width: number, height: number): string {
  const r = Math.min(4, width / 2, height / 2);
  return `M${x},${y} H${x + width - r} Q${x + width},${y} ${x + width},${y + r} V${y + height - r} Q${x + width},${y + height} ${x + width - r},${y + height} H${x} Z`;
}

// ---------------------------------------------------------------- quality vs speed (scatter, log x)

/** Where each dot's name goes, so neighbouring labels don't collide (ours and DeepLabV3 sit close together). */
const labelSide: Record<string, "right" | "left" | "above" | "below"> = {
  ours: "above",
  resnet34_unet: "right",
  deeplabv3: "below",
  sam_detector: "left",
  sam_oracle: "left",
};

function TradeOffChart() {
  const { show, hide, node } = useTooltip();
  const [frame, width] = useWidth(900);
  const narrow = width < NARROW;
  const height = narrow ? 300 : 340;
  const pad = { left: 60, right: 16, top: 16, bottom: 48 };
  const xs = models.map((m) => m.cpu_ms);
  const lo = Math.log10(Math.min(...xs) / 1.8);
  const hi = Math.log10(Math.max(...xs) * 1.4);
  const yMin = Math.floor(Math.min(...models.map((m) => m.dice_mean)) * 20) / 20 - 0.02;
  const yMax = 1;
  const px = (v: number) => pad.left + ((Math.log10(v) - lo) / (hi - lo)) * (width - pad.left - pad.right);
  const py = (v: number) => pad.top + ((yMax - v) / (yMax - yMin)) * (height - pad.top - pad.bottom);
  const xTicks = (narrow ? [100, 1000, 10000] : [30, 100, 300, 1000, 3000, 10000, 30000]).filter((t) => Math.log10(t) >= lo && Math.log10(t) <= hi);
  const yTicks: number[] = [];
  for (let t = Math.ceil(yMin * 20) / 20; t <= yMax + 1e-9; t += 0.05) yTicks.push(Number(t.toFixed(2)));
  const midY = pad.top + (height - pad.top - pad.bottom) / 2;
  return (
    <div className="viz-frame" ref={frame}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Dice score against CPU time per image">
        {yTicks.map((t) => (
          <g key={t}>
            <line className="viz-grid" x1={pad.left} x2={width - pad.right} y1={py(t)} y2={py(t)} />
            <text className="viz-tick" x={pad.left - 8} y={py(t) + 4} textAnchor="end">
              {t.toFixed(2)}
            </text>
          </g>
        ))}
        {xTicks.map((t) => (
          <text key={t} className="viz-tick" x={px(t)} y={height - pad.bottom + 18} textAnchor="middle">
            {ms(t)}
          </text>
        ))}
        <line className="viz-axis" x1={pad.left} x2={width - pad.right} y1={height - pad.bottom} y2={height - pad.bottom} />
        <text className="viz-axis-title" x={(pad.left + width - pad.right) / 2} y={height - 8} textAnchor="middle">
          {narrow ? "CPU time per image (log scale)" : "CPU time per image, 1 thread (log scale; further left is faster)"}
        </text>
        <text className="viz-axis-title" x={12} y={midY} textAnchor="middle" transform={`rotate(-90 12 ${midY})`}>
          Dice (higher is better)
        </text>
        {models.map((m) => {
          const cx = px(m.cpu_ms);
          const cy = py(m.dice_mean);
          const side = labelSide[m.id] ?? "right";
          const label = {
            right: { x: cx + 12, y: cy + 4, anchor: "start" },
            left: { x: cx - 12, y: cy + 4, anchor: "end" },
            above: { x: cx, y: cy - 13, anchor: "middle" },
            below: { x: cx, y: cy + 21, anchor: "middle" },
          }[side];
          const lines = [`Dice ${m.dice_mean.toFixed(3)}`, `${ms(m.cpu_ms)} per image · model RAM ${m.model_ram_mb} MB`];
          return (
            <g
              key={m.id}
              className={m.id === OURS ? "viz-mark ours" : "viz-mark"}
              tabIndex={0}
              onPointerEnter={(e) => show(e, m.name, lines)}
              onPointerLeave={hide}
              onFocus={(e) => show(e, m.name, lines)}
              onBlur={hide}
            >
              <circle className="viz-hit" cx={cx} cy={cy} r={14} />
              <circle className={m.needs_true_box ? "viz-dot hollow" : "viz-dot"} cx={cx} cy={cy} r={6} />
              <text className="viz-label" x={label.x} y={label.y} textAnchor={label.anchor as "start" | "end" | "middle"}>
                {shortName[m.id]}
              </text>
            </g>
          );
        })}
      </svg>
      {node}
    </div>
  );
}

// ---------------------------------------------------------------- per-image distribution (strip + median)

function ConsistencyChart() {
  const { show, hide, node } = useTooltip();
  const [frame, width] = useWidth();
  const narrow = width < NARROW;
  const labelWidth = narrow ? 0 : 180;
  const plot = width - labelWidth - 12;
  const rowHeight = narrow ? 52 : 38;
  const top = 6;
  const height = top + models.length * rowHeight + 26;
  const x = (v: number) => labelWidth + Math.max(0, v) * plot;
  return (
    <div className="viz-frame" ref={frame}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Dice score of every test image, per model">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line className="viz-grid" x1={x(t)} x2={x(t)} y1={top} y2={height - 24} />
            <text className="viz-tick" x={x(t)} y={height - 8} textAnchor={t === 0 && narrow ? "start" : t === 1 ? "end" : "middle"}>
              {t.toFixed(2)}
            </text>
          </g>
        ))}
        {models.map((m, row) => {
          const values = data.per_image_dice[m.id] ?? [];
          const sorted = [...values].sort((a, b) => a - b);
          const median = sorted[Math.floor(sorted.length / 2)] ?? 0;
          const p10 = sorted[Math.floor(sorted.length * 0.1)] ?? 0;
          const rowTop = top + row * rowHeight;
          const cy = narrow ? rowTop + rowHeight - 16 : rowTop + rowHeight / 2;
          const lines = [`median ${median.toFixed(3)}`, `worst 10%: below ${p10.toFixed(3)} · ${pct(m.failure_rate)}% under 0.80`];
          return (
            <g
              key={m.id}
              className={m.id === OURS ? "viz-mark ours" : "viz-mark"}
              tabIndex={0}
              onPointerEnter={(e) => show(e, m.name, lines)}
              onPointerLeave={hide}
              onFocus={(e) => show(e, m.name, lines)}
              onBlur={hide}
            >
              <rect className="viz-hit" x={0} y={rowTop} width={width} height={rowHeight} />
              <text className="viz-label" x={narrow ? 0 : labelWidth - 10} y={narrow ? rowTop + 14 : cy + 4} textAnchor={narrow ? "start" : "end"}>
                {shortName[m.id]}
              </text>
              {values.map((v, i) => (
                // deterministic jitter so the strip doesn't move between renders
                <circle key={i} className="viz-strip" cx={x(v)} cy={cy + (((i * 37) % 17) - 8) * 0.9} r={2} />
              ))}
              <line className="viz-median" x1={x(median)} x2={x(median)} y1={cy - 12} y2={cy + 12} />
            </g>
          );
        })}
      </svg>
      {node}
    </div>
  );
}

// ---------------------------------------------------------------- page

const times = (a: number, b: number) => `${(a / b).toFixed(a / b >= 10 ? 0 : 1)}×`;

function Takeaways() {
  const pretrained = models.find((m) => m.id === "resnet34_unet");
  const deeplab = models.find((m) => m.id === "deeplabv3");
  const sam = models.find((m) => m.id === "sam_detector");
  if (!pretrained || !deeplab || !sam) return null;
  const gap = (pretrained.dice_mean - ours.dice_mean) * 100;
  const pretrainedFaster = pretrained.cpu_ms < ours.cpu_ms;
  return (
    <section className="takeaways" aria-label="Key findings">
      <div>
        <strong>{gap > 0 ? `+${gap.toFixed(1)} Dice points` : `${gap.toFixed(1)} Dice points`}</strong>
        <span>
          {gap > 0 ? "for the pretrained encoder. " : "for the pretrained encoder: no gain. "}
          Fine-tuned on the same images, the ResNet-34 U-Net {gap > 0 ? "beats" : "matches"} my from-scratch model
          {pretrainedFaster
            ? ` and is ${times(ours.cpu_ms, pretrained.cpu_ms)} faster (${ms(pretrained.cpu_ms)} vs ${ms(ours.cpu_ms)}).`
            : `, while mine is ${times(pretrained.cpu_ms, ours.cpu_ms)} faster.`}
        </span>
      </div>
      <div>
        <strong>{times(sam.cpu_ms, ours.cpu_ms)} faster than SAM</strong>
        <span>
          {ours.dice_mean > sam.dice_mean ? "with higher Dice than Detector + SAM" : "Detector + SAM is more accurate, but it needs"} (
          {ours.dice_mean.toFixed(3)} vs {sam.dice_mean.toFixed(3)}) {ours.dice_mean > sam.dice_mean ? "and" : ""}{" "}
          {times(sam.model_ram_mb, ours.model_ram_mb)} {ours.dice_mean > sam.dice_mean ? "less memory" : "the memory"}. A general model loses to a small
          specialist on one narrow task.
        </span>
      </div>
      <div>
        <strong>Sharper edges</strong>
        <span>
          than DeepLabV3 off the shelf: {Math.abs(ours.dice_mean - deeplab.dice_mean) < 0.01 ? "similar" : "different"} Dice (
          {ours.dice_mean.toFixed(3)} vs {deeplab.dice_mean.toFixed(3)}), but boundary F1 {ours.boundary_f1.toFixed(3)} vs{" "}
          {deeplab.boundary_f1.toFixed(3)}. Training on this data teaches where a person's outline is.
        </span>
      </div>
    </section>
  );
}

export function ModelPage() {
  const byQuality = [...models].sort((a, b) => b.dice_mean - a.dice_mean);
  const pretrained = models.find((m) => m.id === "resnet34_unet");
  const sam = models.find((m) => m.id === "sam_detector");

  return (
    <article className="model-page">
      <section className="page-head">
        <h1 className="page-title">How the model compares</h1>
        <p>
          The cutouts on this site come from a small U-Net I trained from scratch. To see what that choice costs and buys, I ran it against a
          fine-tuned pretrained model, an off-the-shelf segmenter and Segment Anything (SAM) on the same {data.meta.test_images} test images
          that none of them trained on.
        </p>
      </section>

      <Takeaways />

      <div className="viz-grid-2">
        <Card title="Overlap with the true mask" subtitle="Mean Dice per image (1.0 = perfect)">
          <BarChart
            tipTitle="Mean Dice per model"
            max={1}
            rows={byQuality.map((m) => ({ id: m.id, label: shortName[m.id], value: m.dice_mean, text: m.dice_mean.toFixed(3), extra: `IoU ${m.iou_mean.toFixed(3)}` }))}
          />
        </Card>
        <Card title="Outline accuracy" subtitle="Boundary F1: edge pixels within 2 px of the true outline">
          <BarChart
            tipTitle="Boundary F1 per model"
            max={1}
            rows={byQuality.map((m) => ({ id: m.id, label: shortName[m.id], value: m.boundary_f1, text: m.boundary_f1.toFixed(3) }))}
          />
        </Card>
      </div>

      <Card title="Quality against speed" subtitle="Top-left is best. The hollow dot needs the true box, so it isn't a real option.">
        <TradeOffChart />
      </Card>

      <div className="viz-grid-2">
        <Card
          title="Memory against the free server"
          subtitle={`Estimated server peak: the web app without a model (${data.meta.server_without_model_mb} MB) plus the model's own RAM`}
        >
          <BarChart
            tipTitle="Estimated server peak memory per model"
            max={Math.max(...models.map((m) => m.peak_mb), data.meta.server_limit_mb) * 1.08}
            refs={[{ value: data.meta.server_limit_mb, label: `${data.meta.server_limit_mb} MB server` }]}
            rows={[...models]
              .sort((a, b) => a.peak_mb - b.peak_mb)
              .map((m) => ({ id: m.id, label: shortName[m.id], value: m.peak_mb, text: `${m.peak_mb} MB`, extra: `model adds ${m.model_ram_mb} MB · ${m.size_mb} MB of weights` }))}
          />
        </Card>
        <Card title="Consistency" subtitle="Dice of every test image; the tick is the median">
          <ConsistencyChart />
        </Card>
      </div>

      <section className="viz-table-wrap" aria-labelledby="results-table">
        <h2 id="results-table">All results</h2>
        <div className="table-scroll">
          <table className="viz-table">
            <thead>
              <tr>
                <th>Model</th>
                <th>Dice</th>
                <th>IoU</th>
                <th>Boundary F1</th>
                <th>Under 0.80</th>
                <th>CPU per image</th>
                <th>Model RAM</th>
                <th>Server peak (est.)</th>
                <th>Weights</th>
                <th>Fits 512 MB</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m) => (
                <tr key={m.id} className={m.id === OURS ? "ours" : undefined}>
                  <th scope="row" title={m.name}>
                    {shortName[m.id]}
                  </th>
                  <td>{m.dice_mean.toFixed(3)}</td>
                  <td>{m.iou_mean.toFixed(3)}</td>
                  <td>{m.boundary_f1.toFixed(3)}</td>
                  <td>{pct(m.failure_rate)}%</td>
                  <td>{ms(m.cpu_ms)}</td>
                  <td>{m.model_ram_mb} MB</td>
                  <td>{m.peak_mb} MB</td>
                  <td>{m.size_mb} MB</td>
                  <td>{m.needs_true_box ? "n/a" : m.fits_free_tier ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="method" aria-labelledby="verdict">
        <h2 id="verdict">What I conclude</h2>
        <ul>
          <li>
            Training from scratch was the right way to learn the whole pipeline, but transfer learning is the better production choice: the
            pretrained U-Net is more accurate on every metric and also faster on the CPU.
          </li>
          {pretrained && (
            <li>
              It still fits the free server (an estimated {pretrained.peak_mb} MB of {data.meta.server_limit_mb} MB), so swapping it in only needs
              the same ONNX export. The cost is a {times(pretrained.size_mb, ours.size_mb)} larger weights file and a thinner memory margin.
            </li>
          )}
          {sam && pretrained && (
            <li>
              Bigger is not automatically better: SAM is far more general, but for this one task it is{" "}
              {sam.dice_mean < Math.min(ours.dice_mean, pretrained.dice_mean) ? "less accurate than either U-Net" : "not clearly more accurate"},{" "}
              {times(sam.cpu_ms, ours.cpu_ms)} slower than mine, and too large for a small server.
            </li>
          )}
        </ul>
      </section>

      <section className="method" aria-labelledby="method">
        <h2 id="method">How this was measured</h2>
        <ul>
          <li>
            Every model sees the same {data.meta.test_images} test images at {data.meta.resolution} pixels, scored against the same hand-made
            masks. These images were never used for training or for choosing a model.
          </li>
          <li>
            The pretrained U-Net uses an ImageNet ResNet-34 encoder, fine-tuned on exactly the same training images, augmentation and loss as
            mine, so the pretrained encoder is the only difference.
          </li>
          <li>
            SAM needs a prompt. "Detector + SAM" gets person boxes from a Faster R-CNN detector, which is a real pipeline. "SAM + true box"
            gets the correct box from the answer key: it shows SAM's ceiling, not something you could run.
          </li>
          <li>
            Speed and memory: each model runs alone in a fresh process on the CPU with one thread, like the free server. Both U-Nets run
            on ONNX Runtime, as in production, so their speeds are directly comparable; DeepLabV3 and SAM run in PyTorch. "Model RAM" is
            what loading and running the model adds to the process (PyTorch's own import is not counted, which favours the PyTorch models).
            The server estimate starts from the live server's measured peak of 378 MB with my model.
          </li>
          <li>
            Limits: one training run per model, and 256-pixel inputs, which are smaller than what SAM and DeepLabV3 usually see. Measured on{" "}
            {data.meta.date}.
          </li>
        </ul>
      </section>
    </article>
  );
}
