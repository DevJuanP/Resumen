"""Genera un visor HTML autocontenido: video de la clase + apuntes sincronizados.

El HTML no incluye el video: apunta a las URLs firmadas de Class, que caducan a
las 12 horas. Regenerar el visor es instantáneo y no vuelve a llamar al modelo.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from .fetch import Clase, urls_de_video
from .summarize import _seg, mmss

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,300..700;1,6..72,300..500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root{
  --paper:#f3f4f1; --panel:#eaede7; --ink:#131815; --ink-soft:#39443d;
  --muted:#68766d; --rule:#d7ddd5; --pass:#1e7a4e; --fail:#b03a2c;
  --mark:#e4e9df;
  --serif:'Newsreader',Georgia,'Times New Roman',serif;
  --sans:'IBM Plex Sans',system-ui,-apple-system,Segoe UI,sans-serif;
  --mono:'IBM Plex Mono',ui-monospace,Consolas,monospace;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  background:var(--paper); color:var(--ink);
  font-family:var(--sans); font-size:15px; line-height:1.55;
  -webkit-font-smoothing:antialiased;
}
a{color:inherit}
::selection{background:var(--mark)}

/* ---------- cabecera ---------- */
.top{
  position:sticky; top:0; z-index:40; background:color-mix(in srgb,var(--paper) 88%,transparent);
  backdrop-filter:blur(12px); border-bottom:1px solid var(--rule);
}
.top-in{
  max-width:1560px; margin:0 auto; padding:14px 28px;
  display:flex; align-items:baseline; gap:18px; flex-wrap:wrap;
}
.top h1{
  font-family:var(--serif); font-size:26px; font-weight:500; letter-spacing:-.01em;
  margin:0; line-height:1.1;
}
.top .meta{color:var(--muted); font-size:13px; display:flex; gap:14px; flex-wrap:wrap}
.top .grow{flex:1}
.ctrl{display:flex; gap:8px; align-items:center}
.search{
  border:1px solid var(--rule); background:#fff; border-radius:999px;
  padding:7px 14px; font:inherit; font-size:13px; width:210px; color:var(--ink);
}
.search:focus{outline:2px solid var(--pass); outline-offset:1px}
.btn{
  border:1px solid var(--rule); background:#fff; color:var(--ink); border-radius:999px;
  padding:7px 15px; font:inherit; font-size:13px; font-weight:500; cursor:pointer;
}
.btn:hover{background:var(--panel)}
.btn:focus-visible{outline:2px solid var(--pass); outline-offset:2px}

/* ---------- estructura ---------- */
.wrap{
  max-width:1560px; margin:0 auto; padding:22px 28px 120px;
  display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.02fr); gap:44px;
  align-items:start;
}
@media (max-width:1120px){
  .wrap{grid-template-columns:1fr; gap:26px; padding:16px 18px 100px}
  .top-in{padding:12px 18px}
  .top h1{font-size:21px}
}
.pane-time{position:sticky; top:78px}
@media (max-width:1120px){ .pane-time{position:static} }

/* ---------- reproductor ---------- */
.player{
  background:#0c110e; border-radius:10px; overflow:hidden; position:relative;
  box-shadow:0 18px 40px -28px rgba(19,24,21,.55);
}
.player video{width:100%; display:block; aspect-ratio:16/9; background:#0c110e}
.no-video{
  aspect-ratio:16/9; display:grid; place-content:center; gap:10px; text-align:center;
  color:#c9d3cb; font-size:13px; padding:24px;
}
.no-video code{font-family:var(--mono); font-size:12px; background:#1b241e; padding:6px 10px; border-radius:6px; color:#e7ede8; word-break:break-all}
.seg{position:absolute; right:10px; top:10px; display:flex; gap:4px; z-index:3}
.seg button{
  font:inherit; font-size:11px; letter-spacing:.03em; padding:5px 10px; border-radius:6px;
  border:1px solid rgba(255,255,255,.22); background:rgba(12,17,14,.62); color:#dce4dd; cursor:pointer;
}
.seg button[aria-pressed="true"]{background:#eef2ec; color:#131815; border-color:#eef2ec}

/* ---------- línea de tiempo ---------- */
.timeline{margin-top:16px}
.tl-head{display:flex; justify-content:space-between; align-items:baseline; margin-bottom:7px}
.tl-head span{font-size:12px; color:var(--muted)}
.rail{
  position:relative; display:flex; height:52px; border-radius:6px; overflow:hidden;
  background:var(--panel); cursor:pointer;
}
.chap{
  position:relative; border:0; padding:0; margin:0; cursor:pointer;
  background:transparent; border-right:1px solid var(--paper);
  display:flex; align-items:flex-end; overflow:hidden;
}
.chap:last-child{border-right:0}
.chap i{
  position:absolute; inset:0; display:block;
  background:color-mix(in srgb,var(--pass) calc(9% + var(--d) * 26%),var(--panel));
  transition:background .18s ease;
}
.chap.on i{background:var(--ink)}
.chap:hover i{background:color-mix(in srgb,var(--ink) 60%,var(--pass))}
.chap b{
  position:relative; z-index:1; font-weight:500; font-size:10px; color:var(--ink-soft);
  padding:4px 5px; font-family:var(--mono); letter-spacing:-.02em; white-space:nowrap;
}
.chap.on b{color:#e9efe9}
/* En pantallas estrechas el mapa se lee por el capítulo de abajo, no por la etiqueta. */
@media (max-width:640px){ .chap b{display:none} }
.line{
  position:absolute; top:0; bottom:0; width:2px; background:var(--fail); z-index:4;
  left:0; pointer-events:none; transform:translateX(-1px);
}
.chaps{list-style:none; margin:12px 0 0; padding:0; display:grid; gap:1px}
.chaps li button{
  width:100%; text-align:left; background:none; border:0; border-bottom:1px solid var(--rule);
  padding:8px 2px; cursor:pointer; font:inherit; color:var(--ink);
  display:grid; grid-template-columns:52px 1fr; gap:10px; align-items:baseline;
}
.chaps li button:hover{background:var(--panel)}
.chaps li button:focus-visible{outline:2px solid var(--pass); outline-offset:-2px}
.chaps time{font-family:var(--mono); font-size:11.5px; color:var(--muted)}
.chaps b{font-weight:500; font-size:13.5px; display:block}
.chaps small{color:var(--muted); font-size:12px; display:block; margin-top:2px; line-height:1.4}
.chaps li.on button{background:var(--mark)}

/* ---------- notas ---------- */
.notes{min-width:0}
.lede{
  font-family:var(--serif); font-size:19px; line-height:1.5; color:var(--ink-soft);
  margin:0 0 30px; max-width:60ch; padding-bottom:22px; border-bottom:1px solid var(--rule);
}
h2{
  font-size:12px; letter-spacing:.09em; text-transform:uppercase; color:var(--muted);
  font-weight:600; margin:38px 0 14px; display:flex; align-items:center; gap:10px;
}
h2::after{content:''; flex:1; height:1px; background:var(--rule)}
h2:first-of-type{margin-top:0}

.item{
  display:grid; grid-template-columns:34px 1fr; gap:14px;
  padding:16px 0; border-bottom:1px solid var(--rule);
}
.item .num{
  font-family:var(--serif); font-size:19px; line-height:1; color:var(--muted);
  padding-top:2px; font-variant-numeric:tabular-nums;
}
.item.alto .num{color:var(--fail); font-weight:600}
.item.medio .num{color:var(--ink-soft)}
.item h3{
  font-family:var(--serif); font-size:20px; line-height:1.25; font-weight:500;
  margin:0 0 6px; letter-spacing:-.01em;
}
.item p{margin:0; color:var(--ink-soft); font-size:14.5px; line-height:1.62}
.tag{
  display:inline-block; font-family:var(--mono); font-size:11px; color:var(--muted);
  text-decoration:none; border-bottom:1px dashed var(--rule); margin-left:8px;
  vertical-align:2px; letter-spacing:-.02em;
}
.tag:hover{color:var(--pass); border-bottom-color:var(--pass)}
.peso{
  font-size:11px; letter-spacing:.04em; text-transform:uppercase; font-weight:600;
  margin-left:10px; vertical-align:2px; color:var(--muted);
}
.item.alto .peso{color:var(--fail)}

.ideas{list-style:none; padding:0; margin:0; columns:2; column-gap:34px}
@media (max-width:760px){ .ideas{columns:1} }
.ideas li{
  break-inside:avoid; padding:9px 0; border-bottom:1px solid var(--rule);
  font-size:13.5px; line-height:1.55; color:var(--ink-soft);
}
.ideas b{color:var(--ink); font-weight:600}
.ideas .t{font-family:var(--mono); font-size:11px; color:var(--muted); margin-right:6px}

table{width:100%; border-collapse:collapse; font-size:13.5px; table-layout:fixed}
th{
  text-align:left; font-weight:600; font-size:11px; letter-spacing:.07em; text-transform:uppercase;
  color:var(--muted); border-bottom:1px solid var(--ink); padding:0 10px 7px 0;
}
td{padding:9px 10px 9px 0; border-bottom:1px solid var(--rule); vertical-align:top; color:var(--ink-soft); overflow-wrap:anywhere}
td:first-child{font-weight:500; color:var(--ink)}
td .t{font-family:var(--mono); font-size:11px; color:var(--muted)}
/* Reparte el ancho: primera columna corta, última (minuto) estrecha. */
td:last-child, th:last-child{width:64px; padding-right:0}
td:first-child, th:first-child{width:27%}

.check{list-style:none; padding:0; margin:0}
.check li{display:grid; grid-template-columns:20px 1fr; gap:11px; padding:11px 0; border-bottom:1px solid var(--rule)}
.check input{appearance:none; width:16px; height:16px; margin:3px 0 0; border:1.5px solid var(--muted); border-radius:3px; cursor:pointer}
.check input:checked{background:var(--pass); border-color:var(--pass)}
.check input:checked::after{content:''; display:block; width:4px; height:8px; border:solid #fff; border-width:0 1.5px 1.5px 0; transform:translate(4.5px,1.5px) rotate(45deg)}
.check input:focus-visible{outline:2px solid var(--pass); outline-offset:2px}
.check label{font-size:14px; cursor:pointer}
.check label b{font-weight:600}
.check .why{display:block; color:var(--muted); font-size:12.5px; margin-top:2px; line-height:1.45}
.check .buscar{
  display:inline-block; margin-top:5px; font-family:var(--mono); font-size:11.5px;
  background:var(--panel); padding:3px 8px; border-radius:4px; color:var(--ink-soft);
  cursor:pointer; border:0;
}
.check .buscar:hover{background:var(--ink); color:var(--paper)}
.check li.done label b{text-decoration:line-through; color:var(--muted)}

details{border-bottom:1px solid var(--rule); padding:12px 0}
summary{cursor:pointer; font-size:14px; font-weight:500}
summary:focus-visible{outline:2px solid var(--pass); outline-offset:2px}
details p, details li{font-size:13.5px; color:var(--ink-soft)}
.dots{columns:2; column-gap:32px; margin:10px 0 0; padding-left:18px}
@media (max-width:760px){ .dots{columns:1} }

.empty-hint{
  font-size:13px; color:var(--muted); background:var(--panel); padding:14px 16px;
  border-left:2px solid var(--rule); border-radius:0 6px 6px 0;
}
.hide{display:none !important}

.transc{max-height:440px; overflow:auto; margin-top:10px}
.transc ul{list-style:none; padding:0; margin:0; font-size:13px}
.transc li{padding:5px 0; border-bottom:1px solid var(--rule); display:grid; grid-template-columns:48px 1fr; gap:10px}
.transc .who{color:var(--ink); font-weight:600}
.transc .t{font-family:var(--mono); font-size:11px; color:var(--muted); cursor:pointer}
.transc .t:hover{color:var(--pass)}
mark{background:var(--mark); color:var(--ink)}

.foot{margin-top:44px; padding-top:18px; border-top:1px solid var(--rule); color:var(--muted); font-size:12px; line-height:1.6}
.mini{
  display:none; position:fixed; left:0; right:0; bottom:0; z-index:50;
  background:#0c110e; padding:8px 14px; align-items:center; gap:12px;
}
@media (max-width:1120px){ .mini{display:flex} }
.mini button{
  font:inherit; font-size:12px; background:#eef2ec; color:#131815; border:0; border-radius:5px;
  padding:7px 12px; cursor:pointer; font-weight:500;
}
.mini span{color:#c9d3cb; font-size:12px; font-family:var(--mono)}
.mini .bar{flex:1; height:3px; background:#2a352d; border-radius:2px; overflow:hidden}
.mini .bar i{display:block; height:100%; background:#eef2ec; width:0}
@media (prefers-reduced-motion:reduce){ *{transition:none !important} }
"""

JS = r"""
const D = window.__CLASE__;
const $$ = (s, r=document) => r.querySelector(s);
const $$all = (s, r=document) => [...r.querySelectorAll(s)];

const vids = D.videos || {};
let video = $$('#v');
let current = vids.active_speaker ? 'active_speaker' : (Object.keys(vids)[0] || null);

function fmt(s){
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s/3600), m = Math.floor(s%3600/60), x = s%60;
  return h ? `${h}:${String(m).padStart(2,'0')}:${String(x).padStart(2,'0')}`
           : `${String(m).padStart(2,'0')}:${String(x).padStart(2,'0')}`;
}
function seek(sec){
  if(!video || !video.src) return;
  const m = /^(\d+):(\d{1,2})(?::(\d{1,2}))?$/.exec(String(sec).trim());
  let s = 0;
  if(m){ s = m[3] ? (+m[1])*3600 + (+m[2])*60 + (+m[3]) : (+m[1])*60 + (+m[2]); }
  else s = +sec || 0;
  video.currentTime = s;
  video.play().catch(()=>{});
  video.scrollIntoView({block:'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto':'smooth'});
}
window.__seek = seek;

document.addEventListener('click', (e)=>{
  const t = e.target.closest('[data-t]');
  if(t){ e.preventDefault(); seek(t.dataset.t); }
});

// ---- reproductor: cambio de pista ----
if(video && current){
  video.src = vids[current];
}
$$all('.seg button').forEach(b=>{
  b.addEventListener('click', ()=>{
    const k = b.dataset.track;
    if(!vids[k] || !video) return;
    const at = video.currentTime, playing = !video.paused;
    video.src = vids[k];
    video.currentTime = at;
    if(playing) video.play().catch(()=>{});
    $$all('.seg button').forEach(x=>x.setAttribute('aria-pressed', String(x===b)));
  });
});

// ---- línea de tiempo ----
const rail = $$('#rail');
const line = $$('.line');
const chaps = $$all('.chap');
const list = $$all('#chaps li');

function pct(){ return video && video.duration ? video.currentTime/video.duration : 0; }

function paint(){
  if(!rail) return;
  const p = pct();
  if(line) line.style.left = (p*100)+'%';
  const bar = $$('#minibar');
  if(bar) bar.style.width = (p*100)+'%';
  const lab = $$('#minitime');
  if(lab && video) lab.textContent = fmt(video.currentTime) + ' / ' + fmt(video.duration||D.duration);

  let idx = -1;
  chaps.forEach((c,i)=>{ if(+c.dataset.start <= (video?video.currentTime:0)) idx = i; });
  chaps.forEach((c,i)=> c.classList.toggle('on', i===idx));
  list.forEach((c,i)=> c.classList.toggle('on', i===idx));
}
if(video){
  video.addEventListener('timeupdate', paint);
  video.addEventListener('loadedmetadata', paint);
}
if(rail){
  rail.addEventListener('click', (e)=>{
    const r = rail.getBoundingClientRect();
    const p = clamp((e.clientX - r.left) / r.width, 0, 1);
    seek(Math.round(p * (video && video.duration ? video.duration : D.duration)));
  });
}
function clamp(v,a,b){ return Math.min(b, Math.max(a,v)); }

// ---- mini reproductor (móvil) ----
const mini = $$('#mini');
if(mini && video){
  $$('#miniplay').addEventListener('click', ()=>{
    if(video.paused) video.play().catch(()=>{}); else video.pause();
    $$('#miniplay').textContent = video.paused ? 'Reproducir' : 'Pausa';
  });
  $$('#minijump').addEventListener('click', ()=> video.scrollIntoView({block:'center'}));
}

// ---- teclado ----
document.addEventListener('keydown', (e)=>{
  if(/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
  if(!video || !video.src) return;
  if(e.code === 'Space'){ e.preventDefault(); video.paused ? video.play().catch(()=>{}) : video.pause(); }
  else if(e.key === 'ArrowRight'){ e.preventDefault(); seek(video.currentTime + 10); }
  else if(e.key === 'ArrowLeft'){ e.preventDefault(); seek(video.currentTime - 10); }
});

// ---- búsqueda ----
const search = $$('#q');
if(search){
  search.addEventListener('input', ()=>{
    const q = search.value.trim().toLowerCase();
    $$all('[data-buscable]').forEach(el=>{
      const hit = !q || el.textContent.toLowerCase().includes(q);
      el.classList.toggle('hide', !hit);
    });
    $$all('.notes h2').forEach(h=>{
      const block = h.nextElementSibling;
      if(!block) return;
      const visible = [...block.querySelectorAll('[data-buscable]')].some(e=>!e.classList.contains('hide'));
      h.classList.toggle('hide', !!q && !visible && !block.querySelector('[data-buscable]'));
    });
  });
}

// ---- checklist persistente ----
const KEY = 'resumen:' + D.id;
let hechas = {};
try{ hechas = JSON.parse(localStorage.getItem(KEY) || '{}'); }catch(_){ hechas = {}; }
$$all('.check input').forEach(c=>{
  if(hechas[c.dataset.k]){ c.checked = true; c.closest('li').classList.add('done'); }
  c.addEventListener('change', ()=>{
    hechas[c.dataset.k] = c.checked;
    c.closest('li').classList.toggle('done', c.checked);
    localStorage.setItem(KEY, JSON.stringify(hechas));
    const p = $$('#progreso');
    if(p){
      const total = $$all('.check input').length;
      const ok = $$all('.check input:checked').length;
      p.textContent = ok + '/' + total;
    }
  });
});
const prog = $$('#progreso');
if(prog){
  const total = $$all('.check input').length;
  prog.textContent = $$all('.check input:checked').length + '/' + total;
}

// ---- copiar consulta de búsqueda ----
document.addEventListener('click', async (e)=>{
  const b = e.target.closest('.buscar');
  if(!b) return;
  try{ await navigator.clipboard.writeText(b.dataset.q); b.textContent = 'Copiado'; setTimeout(()=> b.textContent = b.dataset.q, 1200); }
  catch(_){}
});

paint();
"""


def _esc(t: str) -> str:
    return html.escape(str(t or ""), quote=True)


def _vinculo(t: str) -> str:
    return f'<a class="tag" href="#" data-t="{_esc(t)}">{_esc(t)}</a>' if t else ""


def generar(clase: Clase, datos: dict, salida: Path, refrescar_video: bool = True) -> Path:
    """Escribe el visor HTML y devuelve la ruta."""
    fus, sin = datos["fusion"], datos["sintesis"]
    videos: dict[str, str] = {}
    if refrescar_video and clase.url:
        try:
            todos = urls_de_video(clase)
            videos = {k: v for k, v in todos.items() if k in ("active_speaker", "shared_screen")}
        except Exception:
            videos = {}

    duracion = clase.duracion_s or 1
    capítulos = sin.get("mapa") or []
    densidad = []
    for c in capítulos:
        a, b = _seg(str(c.get("desde", ""))), _seg(str(c.get("hasta", "")))
        n = sum(1 for i in fus["ideas"] if a <= _seg(str(i.get("t", ""))) < b)
        densidad.append(n / max(1, (b - a) / 60))

    L: list[str] = []
    L.append("<!doctype html><html lang=es><head><meta charset=utf-8>")
    L.append("<meta name=viewport content='width=device-width,initial-scale=1'>")
    L.append(f"<title>{_esc(clase.materia)} · apuntes</title>")
    L.append("<style>" + CSS + "</style></head><body>")

    # Cabecera
    fecha = clase.cuando.strftime("%d/%m/%Y")
    L.append("<div class=top><div class=top-in>")
    L.append(f"<h1>{_esc(clase.materia)}</h1>")
    L.append(f"<div class=meta><span>{fecha}</span><span>{round(duracion/60)} min</span>"
             f"<span>{len(clase.segmentos)} intervenciones</span>"
             f"{'<span>' + _esc(clase.docente) + '</span>' if clase.docente else ''}</div>")
    L.append("<div class=grow></div>")
    L.append("<div class=ctrl><input id=q class=search type=search placeholder='Buscar en los apuntes…' "
             "aria-label='Buscar en los apuntes'>")
    if sin.get("investigar"):
        L.append(f"<button class=btn id=progreso title='Temas investigados'>0/{len(sin['investigar'])}</button>")
    L.append("</div></div></div>")

    L.append("<div class=wrap>")

    # ---------------- columna de tiempo ----------------
    L.append("<div class=pane-time><div class=player id=playerbox>")
    if videos:
        L.append("<video id=v controls playsinline preload=metadata></video>")
        if len(videos) > 1:
            L.append("<div class=seg>")
            etiquetas = {"active_speaker": "Docente", "shared_screen": "Diapositivas"}
            for k in videos:
                activo = "true" if k == ("active_speaker" if "active_speaker" in videos else list(videos)[0]) else "false"
                L.append(f"<button data-track={k} aria-pressed={activo}>{etiquetas.get(k, k)}</button>")
            L.append("</div>")
    else:
        L.append("<div class=no-video><div>Los enlaces del video caducaron o no están disponibles.</div>"
                 "<div>Regenera el visor sin volver a resumir:</div>"
                 f"<code>python resumen.py \"{_esc(clase.url)}\" --solo-visor</code></div>")
    L.append("</div>")

    # Línea de tiempo proporcional
    L.append("<div class=timeline>")
    L.append(f"<div class=tl-head><span>Mapa de la clase</span><span>{round(duracion/60)} min</span></div>")
    L.append("<div class=rail id=rail role=slider tabindex=0 aria-label='Línea de tiempo de la clase'>")
    for c, d in zip(capítulos, densidad):
        a, b = _seg(str(c.get("desde", ""))), _seg(str(c.get("hasta", "")))
        ancho = max(2.5, 100 * (b - a) / duracion)
        nivel = min(1.0, d / 3.0)
        etiqueta = mmss(a)
        tema_txt = _esc(c.get("tema", ""))
        titulo = f"{tema_txt} ({mmss(a)}–{mmss(b)})"
        visible = ancho >= 6.0
        rotulo = f"<b>{etiqueta}</b>" if visible else ""
        L.append(f"<button class=chap data-start={a} style='flex:0 0 {ancho:.3f}%;--d:{nivel:.2f}' "
                 f"title='{titulo}' aria-label='{titulo}'>{rotulo}<i></i></button>")
    L.append("<div class=line></div></div>")
    L.append("</div>")

    # Capítulos
    L.append("<ol class=chaps id=chaps>")
    for c in capítulos:
        L.append(f"<li><button data-t='{_esc(c.get('desde',''))}'>"
                 f"<time>{_esc(c.get('desde',''))}</time><span><b>{_esc(c.get('tema',''))}</b>"
                 f"<small>{_esc(c.get('que_pasa',''))}</small></span></button></li>")
    L.append("</ol>")

    L.append("</div>")

    # ---------------- columna de notas ----------------
    L.append("<div class=notes>")
    L.append(f"<p class=lede data-buscable>{_esc(sin.get('resumen',''))}</p>")

    L.append("<h2>Lo que importa</h2><div>")
    for i, c in enumerate(sin.get("clave", []), 1):
        peso = (c.get("peso") or "medio").lower()
        etq = {"alto": "Alta prioridad", "medio": "Base", "bajo": "Contexto"}.get(peso, "Base")
        L.append(f"<div class='item {peso}' data-buscable><div class=num>{i:02d}</div><div>"
                 f"<h3>{_esc(c.get('punto',''))}{_vinculo(c.get('t',''))}</h3>"
                 f"<span class=peso>{etq}</span>"
                 f"<p>{_esc(c.get('desarrollo',''))}</p></div></div>")
    L.append("</div>")

    L.append("<h2>Investigá por tu cuenta</h2><div>")
    inv = sin.get("investigar") or []
    if inv:
        L.append("<ul class=check>")
        for i, x in enumerate(inv):
            clave = f"{i}-{x.get('tema','')[:40]}"
            boton = ""
            if x.get("buscar"):
                q = _esc(x["buscar"])
                boton = f'<button class=buscar data-q="{q}">{q}</button>'
            L.append(f"<li data-buscable><input type=checkbox id=ck{i} data-k='{_esc(clave)}'>"
                     f"<label for=ck{i}><b>{_esc(x.get('tema',''))}</b>"
                     f"<span class=why>{_esc(x.get('por_que',''))}</span>"
                     f"{boton}</label></li>")
        L.append("</ul>")
    else:
        L.append("<p class=empty-hint>La clase no dejó temas pendientes de ampliar.</p>")
    L.append("</div>")

    # Pendientes
    L.append("<h2>Pendientes y avisos</h2><div>")
    if fus["avisos"]:
        L.append("<table><thead><tr><th>Cuándo</th><th>Qué</th><th>Min</th></tr></thead><tbody>")
        for a in fus["avisos"]:
            L.append(f"<tr data-buscable><td>{_esc(a.get('cuando') or '—')}</td>"
                     f"<td>{_esc(a.get('que',''))}</td><td>{_vinculo(a.get('t',''))}</td></tr>")
        L.append("</tbody></table>")
    else:
        L.append("<p class=empty-hint>No se anunciaron fechas ni entregas en esta sesión.</p>")
    L.append("</div>")

    # Desarrollo completo
    if fus["ideas"]:
        L.append(f"<h2>Desarrollo completo<span style='text-transform:none;letter-spacing:0;font-weight:400'>"
                 f"&nbsp;{len(fus['ideas'])} ideas</span></h2>")
        L.append("<details><summary>Ver todas las ideas en orden de aparición</summary><div><ul class=ideas>")
        for idea in fus["ideas"]:
            L.append(f"<li data-buscable><span class=t>{_esc(idea.get('t',''))}</span>"
                     f"<b>{_esc(idea.get('titulo',''))}</b> — {_esc(idea.get('explicacion',''))}</li>")
        L.append("</ul></div></details>")

    # Glosario
    if fus["terminos"]:
        L.append(f"<h2>Glosario<span style='text-transform:none;letter-spacing:0;font-weight:400'>"
                 f"&nbsp;{len(fus['terminos'])} términos</span></h2>")
        L.append("<details><summary>Ver definiciones</summary><div><table><tbody>")
        for t in fus["terminos"]:
            L.append(f"<tr data-buscable><td>{_esc(t.get('termino',''))}</td>"
                     f"<td>{_esc(t.get('definicion',''))}</td><td>{_vinculo(t.get('t',''))}</td></tr>")
        L.append("</tbody></table></div></details>")

    # Ejemplos
    if fus["ejemplos"]:
        L.append("<h2>Ejemplos del docente</h2><div><ul class=ideas>")
        for e in fus["ejemplos"]:
            L.append(f"<li data-buscable><span class=t>{_esc(e.get('t',''))}</span>"
                     f"{_esc(e.get('ejemplo',''))} <em style='color:var(--muted)'>{_esc(e.get('ilustra',''))}</em></li>")
        L.append("</ul></div>")

    # Preguntas
    if fus["preguntas"]:
        L.append("<h2>Preguntas de tus compañeros</h2><div>")
        for p in fus["preguntas"]:
            L.append(f"<div class=item data-buscable><div class=num>?</div><div>"
                     f"<h3>{_esc(p.get('pregunta',''))}{_vinculo(p.get('t',''))}</h3>"
                     f"<p>{_esc(p.get('respuesta',''))}</p></div></div>")
        L.append("</div>")

    # Omitido
    omitido = sin.get("relleno") or fus["relleno"]
    if omitido:
        L.append(f"<h2>Lo que se omitió</h2><div><details><summary>"
                 f"{len(omitido)} fragmentos descartados sin contenido</summary><ul class=dots>")
        for r in omitido[:40]:
            L.append(f"<li>{_esc(r)}</li>")
        L.append("</ul></details></div>")

    # Transcripción
    L.append("<h2>Transcripción completa</h2><div><details><summary>"
             f"{len(clase.segmentos)} intervenciones con minuto exacto</summary><div class=transc><ul>")
    for s in clase.segmentos:
        quien = "Docente" if s.rol == "docente" else s.hablante
        L.append(f"<li><span class=t data-t='{mmss(s.segundos)}'>{mmss(s.segundos)}</span>"
                 f"<span data-buscable><span class=who>{_esc(quien)}:</span> {_esc(s.texto)}</span></li>")
    L.append("</ul></div></details></div>")

    L.append("<div class=foot>")
    L.append("Los enlaces del video caducan a las 12 horas. Si dejan de funcionar, "
             "regenera este visor con <code>--solo-visor</code>: no vuelve a resumir nada.")
    if clase.url:
        L.append(f"<br>Fuente: {_esc(clase.url)}")
    L.append("</div></div></div>")

    # Mini reproductor móvil
    L.append("<div class=mini id=mini><button id=miniplay>Reproducir</button>"
             "<div class=bar><i id=minibar></i></div>"
             "<span id=minitime></span><button id=minijump>Ir al video</button></div>")

    datos_video = {
        "id": re.sub(r"[^\w-]", "", f"{clase.materia}-{clase.cuando:%Y%m%d}")[:60],
        "duration": duracion,
        "videos": videos,
    }
    L.append("<script>window.__CLASE__=" + json.dumps(datos_video).replace("</", "<\\/") + ";</script>")
    L.append("<script>" + JS + "</script>")
    L.append("</body></html>")

    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text("".join(L), encoding="utf-8")
    return salida
