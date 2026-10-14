// Browser harness for overlay sync. Plays the HLS stream, draws replacements/blurs from the
// sidecar track on top, and measures how far the player clock is from the displayed frame.
// The Vega app reuses shared/sidecar and swaps these DOM elements for RN views.

import Hls from 'hls.js';
import { cssMatrix3d, filterObjects, objectsAt, parseSidecar, samplesVideoFrames, type Category, type Quad, type SidecarFile, type SidecarObject, type SidecarTrack } from '../shared/sidecar';

interface BrandEntry {
  name: string;
  category: string;
  file: string;
}

const params = new URLSearchParams(location.search);
const server = params.get('server') ?? 'http://localhost:8787';
const clip = params.get('clip') ?? 'synth';
const src = params.get('src') ?? `${server}/media/${clip}/hls/index.m3u8`;
const sidecarUrl = params.get('sidecar') ?? `${server}/media/${clip}/sidecar.json`;

const video = document.querySelector<HTMLVideoElement>('#video')!;
const stage = document.querySelector<HTMLDivElement>('#stage')!;
const overlay = document.querySelector<HTMLDivElement>('#overlay')!;
const outlines = document.querySelector<SVGSVGElement>('#outlines')!;
const stats = document.querySelector<HTMLDListElement>('#stats')!;
const offsetInput = document.querySelector<HTMLInputElement>('#offset')!;
const offsetValue = document.querySelector<HTMLOutputElement>('#offset-value')!;
const showOutlines = document.querySelector<HTMLInputElement>('#show-outlines')!;
document.querySelector('#source')!.textContent = `${src}  +  ${sidecarUrl}`;

let track: SidecarTrack | null = null;
let replacements: { name: string; url: string; w: number; h: number }[] = [];

// Latest presented frame, from requestVideoFrameCallback.
let presentedMediaTime = NaN;
const skewSamples: number[] = [];

function selected(name: string): string[] {
  return [...document.querySelectorAll<HTMLInputElement>(`input[name="${name}"]:checked`)].map((i) => i.value);
}

function contentRect(): { x: number; y: number; w: number; h: number } {
  // Where the video pixels actually land inside the element (object-fit: contain).
  const ew = video.clientWidth;
  const eh = video.clientHeight;
  const vw = video.videoWidth || 16;
  const vh = video.videoHeight || 9;
  const scale = Math.min(ew / vw, eh / vh);
  const w = vw * scale;
  const h = vh * scale;
  return { x: (ew - w) / 2, y: (eh - h) / 2, w, h };
}

function hashIndex(id: string, n: number): number {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) h = Math.imul(h ^ id.charCodeAt(i), 16777619);
  return Math.abs(h) % n;
}

const elements = new Map<string, HTMLElement>();

function elementFor(id: string, treatment: string): HTMLElement {
  const key = `${treatment}:${id}`;
  let el = elements.get(key);
  if (!el) {
    if (treatment === 'replace') {
      const r = replacements[hashIndex(id, replacements.length)];
      const img = new Image(r.w, r.h);
      img.src = r.url;
      img.alt = '';
      img.dataset.w = String(r.w);
      img.dataset.h = String(r.h);
      el = img;
    } else {
      el = document.createElement('div');
      el.className = 'blur';
    }
    elements.set(key, el);
    overlay.append(el);
  }
  return el;
}

function render(time: number): void {
  if (!track) return;
  const rect = contentRect();
  for (const layer of [overlay, outlines] as HTMLElement[] | SVGElement[]) {
    Object.assign(layer.style, { left: `${rect.x}px`, top: `${rect.y}px`, width: `${rect.w}px`, height: `${rect.h}px` });
  }

  const offset = Number(offsetInput.value) / 1000;
  const all = objectsAt(track, time, { offset, interpolate: !samplesVideoFrames(track) });
  const categories = new Set(selected('category') as Category[]);
  const hidden = filterObjects(all, { categories });
  const treatment = selected('treatment')[0];

  const live = new Set<HTMLElement>();
  if (treatment !== 'none') {
    for (const o of hidden) {
      const px = toPixels(o.quad, rect.w, rect.h);
      const el = elementFor(o.id, treatment);
      if (treatment === 'replace') {
        el.style.transform = cssMatrix3d(Number(el.dataset.w), Number(el.dataset.h), px);
      } else {
        el.style.clipPath = `polygon(${px.map(([x, y]) => `${x.toFixed(1)}px ${y.toFixed(1)}px`).join(',')})`;
      }
      el.style.display = '';
      live.add(el);
    }
  }
  for (const el of elements.values()) if (!live.has(el)) el.style.display = 'none';

  drawOutlines(showOutlines.checked ? all : [], rect);
  updateStats(time, all.length, hidden.length);
}

function toPixels(quad: Quad, w: number, h: number): Quad {
  return quad.map(([x, y]) => [x * w, y * h]) as Quad;
}

function drawOutlines(objects: SidecarObject[], rect: { w: number; h: number }): void {
  outlines.setAttribute('viewBox', `0 0 ${rect.w} ${rect.h}`);
  outlines.innerHTML = objects
    .map((o) => {
      const px = toPixels(o.quad, rect.w, rect.h);
      const pts = px.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
      return `<polygon points="${pts}"/><text x="${px[0][0] + 4}" y="${px[0][1] - 4}">${o.brand ?? o.id} · ${o.category}</text>`;
    })
    .join('');
}

function updateStats(time: number, total: number, hidden: number): void {
  const skew = skewSamples.length ? skewSamples.reduce((a, b) => a + b, 0) / skewSamples.length : NaN;
  const maxSkew = skewSamples.length ? Math.max(...skewSamples.map(Math.abs)) : NaN;
  const fps = track?.fps ?? 30;
  const rows: [string, string][] = [
    ['render time', `${time.toFixed(3)} s`],
    ['frame', `${Math.floor(time * fps + 1e-6)}`],
    ['objects / hidden', `${total} / ${hidden}`],
    ['clock skew avg', Number.isNaN(skew) ? 'n/a' : `${(skew * 1000).toFixed(1)} ms`],
    ['clock skew max', Number.isNaN(maxSkew) ? 'n/a' : `${(maxSkew * 1000).toFixed(1)} ms`],
    ['sidecar samples', `${track?.frames.length ?? 0} (${track?.source ?? '?'})`],
  ];
  stats.innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
}

// rAF loop: drives rendering in currentTime mode and records how far currentTime is from
// the frame actually on screen (the error the Vega app will live with).
function rafLoop(): void {
  if (!video.paused && !Number.isNaN(presentedMediaTime)) {
    skewSamples.push(video.currentTime - presentedMediaTime);
    if (skewSamples.length > 240) skewSamples.shift();
  }
  if (selected('clock')[0] === 'currentTime') render(video.currentTime);
  requestAnimationFrame(rafLoop);
}

function frameLoop(_now: number, meta: VideoFrameCallbackMetadata): void {
  presentedMediaTime = meta.mediaTime;
  if (selected('clock')[0] === 'rvfc') render(meta.mediaTime);
  video.requestVideoFrameCallback(frameLoop);
}

async function loadJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} fetching ${url}`);
  return res.json() as Promise<T>;
}

async function main(): Promise<void> {
  const [sidecar, brands] = await Promise.all([
    loadJson<SidecarFile>(sidecarUrl),
    loadJson<{ size: [number, number]; brands: BrandEntry[] }>(`${server}/assets/brands/brands.json`),
  ]);
  track = parseSidecar(sidecar);
  const [w, h] = brands.size;
  replacements = brands.brands
    .filter((b) => b.category === 'replacement')
    .map((b) => ({ name: b.name, url: `${server}/assets/brands/${b.file}`, w, h }));

  if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = src;
  } else if (Hls.isSupported()) {
    const hls = new Hls();
    hls.loadSource(src);
    hls.attachMedia(video);
  } else {
    throw new Error('HLS is not supported in this browser');
  }

  if ('requestVideoFrameCallback' in video) {
    video.requestVideoFrameCallback(frameLoop);
  } else {
    document.querySelector<HTMLInputElement>('input[name="clock"][value="rvfc"]')!.disabled = true;
  }
  requestAnimationFrame(rafLoop);
}

offsetInput.addEventListener('input', () => {
  offsetValue.textContent = `${offsetInput.value} ms`;
});
document.querySelectorAll('input[name="treatment"], input[name="clock"]').forEach((i) =>
  i.addEventListener('change', () => {
    skewSamples.length = 0;
  }),
);
document.addEventListener('keydown', (e) => {
  if (e.target instanceof HTMLInputElement && e.target.type === 'range') return;
  const step = 1 / (track?.fps ?? 30);
  if (e.key === 'o' || e.key === 'O') showOutlines.checked = !showOutlines.checked;
  else if (e.key === ' ') {
    e.preventDefault();
    if (video.paused) void video.play();
    else video.pause();
  } else if (e.key === ',') video.currentTime = Math.max(0, video.currentTime - step);
  else if (e.key === '.') video.currentTime = video.currentTime + step;
  else return;
  if (video.paused) render(video.currentTime);
});
new ResizeObserver(() => render(video.currentTime)).observe(stage);

main().catch((err: unknown) => {
  stats.innerHTML = `<dt>error</dt><dd>${String(err)}</dd>`;
  console.error(err);
});
