"""Presentation-first offline HTML UI for Mars Analog Engine V2.0.4.

No tile service, external JS, fabricated terrain or unverified analog scores.
All display strings derived from external files are inserted with textContent.
"""
from __future__ import annotations

import json


def render_dashboard(summary: dict) -> str:
    payload = (json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
               .replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
               .replace('\u2028','\\u2028').replace('\u2029','\\u2029'))
    css = r"""
:root{color-scheme:light;--navy:#0a2430;--blue:#0d606c;--jade:#148e83;--text:#172e39;--muted:#5e717a;--bg:#f2f6f6;--white:#fff;--line:#dbe5e6;--gold:#a66b26}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.53 'Segoe UI',Inter,Arial,sans-serif}
button,input{font:inherit}button{cursor:pointer}button:focus-visible,a:focus-visible,input:focus-visible{outline:3px solid #61c8c0;outline-offset:2px}
.header{background:radial-gradient(circle at 85% 10%,#256e74 0,#153944 37%,#0b2430 75%);color:#fff;padding:32px max(22px,calc((100vw - 1260px)/2)) 64px;position:relative;overflow:hidden}
.header:after{content:'';position:absolute;right:-110px;top:-150px;width:550px;height:550px;border:1px solid #ffffff20;border-radius:50%;pointer-events:none;box-shadow:0 0 0 80px #ffffff05,0 0 0 160px #ffffff05}
.header .inner{position:relative;z-index:1}.eyebrow{font-size:11px;letter-spacing:.18em;font-weight:800;color:#9be1d5;text-transform:uppercase}.header h1{margin:13px 0 10px;font-weight:760;letter-spacing:-.055em;line-height:1.06;font-size:clamp(29px,3.8vw,52px);max-width:900px}.header p{color:#d7e9eb;font-size:15px;max-width:790px;margin:0}.tagline{margin-top:19px;display:flex;gap:9px;flex-wrap:wrap}.tagline span{background:#d8faf01a;color:#d4f5f2;border:1px solid #a8eee049;border-radius:24px;padding:6px 12px;font-size:12px}
.page{max-width:1308px;margin:auto;padding:0 24px 28px}.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:-36px;position:relative;z-index:2}
.kpi{background:#fff;border:1px solid #e1e8e9;border-radius:14px;box-shadow:0 6px 18px #0b28341a;padding:16px 18px}.kpi strong{display:block;font-size:27px;letter-spacing:-.05em;line-height:1.2;color:#0d5b65}.kpi span{font-size:12px;color:var(--muted)}
.nav{display:flex;gap:7px;flex-wrap:wrap;margin:25px 0 15px}.nav button{background:#fff;border:1px solid #d4e2e4;color:#244d58;border-radius:22px;padding:9px 15px;font-weight:700;font-size:13px}.nav button[aria-selected=true]{background:#116a75;border-color:#116a75;color:#fff}
.view[hidden]{display:none!important}.panel{background:#fff;border:1px solid var(--line);border-radius:15px;padding:21px;margin-bottom:15px;box-shadow:0 2px 14px #0c293808}.section-head{display:flex;justify-content:space-between;gap:14px;align-items:center;margin-bottom:12px}.section-head h2,.panel h2{font-size:22px;line-height:1.22;letter-spacing:-.025em;margin:0}.panel h3{margin:0 0 8px;font-size:17px}.panel p{margin:6px 0 12px}.muted{color:var(--muted)}.small{font-size:12px;color:var(--muted)}.kicker{font-size:10px;letter-spacing:.13em;color:#2b7781;font-weight:800;text-transform:uppercase}.chip{display:inline-flex;align-items:center;gap:5px;border-radius:20px;background:#e9f5f3;color:#187565;font-size:11px;font-weight:700;padding:4px 9px}.chip.amber{background:#fff1dd;color:#995d21}.chip.blue{background:#eaf3f9;color:#246c8b}.lead{font-size:15px;color:#405964;max-width:950px}
.callout{padding:15px 18px;background:linear-gradient(100deg,#f0faf7,#f5fbfc);border:1px solid #d8eee9;border-radius:13px;margin-bottom:16px}.callout b{color:#0d636b}
.explore{display:grid;grid-template-columns:322px minmax(0,1fr);gap:15px;align-items:start}.side{padding:0;overflow:hidden}.side-top{padding:17px 17px 11px;border-bottom:1px solid var(--line)}.side-top h3{font-size:18px;margin:0 0 3px}.side-top input{width:100%;border:1px solid #cadbdf;border-radius:10px;padding:10px 12px;background:#fff;color:#24404b;margin-top:12px}.filterline{display:flex;gap:5px;margin-top:10px;flex-wrap:wrap}.filterline button{background:#f1f7f8;border:1px solid #dbe7e8;color:#4d666f;border-radius:16px;padding:5px 10px;font-size:11px}.filterline button[aria-pressed=true]{background:#116d76;color:#fff;border-color:#116d76}
.list{max-height:635px;overflow-y:auto;padding:9px}.candidate-option{width:100%;background:#fff;border:1px solid transparent;border-radius:10px;text-align:left;padding:10px 11px;display:grid;grid-template-columns:1fr auto;gap:3px 10px;margin:2px 0;color:var(--text)}.candidate-option:hover{background:#f1f8f7}.candidate-option[aria-current=true]{background:#eaf7f4;border-color:#90d8cd;box-shadow:inset 3px 0 #168a80}.candidate-option b{font-weight:740;font-size:13px}.candidate-option .coordinates{grid-column:1/3;color:#6e848a;font-size:11px}.rank{background:#e8f3f3;color:#176a71;border-radius:10px;padding:3px 7px;font-weight:800;font-size:12px;line-height:1.35;white-space:nowrap}.priority-tag{font-size:10px;color:#077965;font-weight:700;grid-column:1/3}
.details-top{display:flex;align-items:flex-start;justify-content:space-between;gap:13px;flex-wrap:wrap}.details-title{font-size:23px;letter-spacing:-.035em;font-weight:800;line-height:1.2;margin:4px 0}.label-id{font-family:Consolas,monospace;font-size:12px;color:#61838b}.detail-metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:15px 0}.detail-metric{border-radius:10px;padding:12px 14px;background:#f3f8f8}.detail-metric strong{display:block;font-size:22px;line-height:1.18;letter-spacing:-.035em;color:#0e6970}.detail-metric span{font-size:11px;color:#5b767e}
.map-tabs{display:flex;flex-wrap:wrap;gap:7px;margin:14px 0 10px}.map-tabs button{border:1px solid #d5e5e4;border-radius:9px;background:#f4f9f9;padding:8px 12px;color:#385d65;font-weight:700;font-size:12px}.map-tabs button[aria-selected=true]{background:#105c68;color:#fff;border-color:#105c68}
.map-head{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;padding:6px 0}.map-head strong{font-size:14px}.map-controls{display:flex;align-items:center;gap:5px;flex-wrap:wrap}.map-controls button{background:#fff;border:1px solid #d2e2e2;border-radius:8px;padding:5px 10px;color:#27606a;font-weight:700}.map-controls button[aria-pressed=true]{background:#e3f3f0;border-color:#8fc9c1}
.map-box{position:relative;border-radius:13px;background:#deeaec;overflow:hidden;border:1px solid #c6dadd}.map-box canvas{display:block;width:100%;height:410px;cursor:crosshair;touch-action:none}.map-missing{height:300px;display:flex;align-items:center;justify-content:center;padding:25px;color:#4c6d75;text-align:center;background:repeating-linear-gradient(45deg,#e9f3f5,#e9f3f5 9px,#e3eef0 9px,#e3eef0 18px)}.map-missing[hidden]{display:none}.map-overlay{position:absolute;left:12px;top:12px;background:#122d37c9;color:white;padding:7px 10px;font-size:11px;border-radius:8px;pointer-events:none}.map-zoom{position:absolute;right:12px;top:12px;background:#122d37b8;color:#fff;border-radius:8px;padding:5px 8px;font-size:11px;pointer-events:none}.map-popup{position:absolute;left:12px;bottom:12px;background:#102c38ec;color:#fff;border-radius:8px;padding:8px 11px;font:12px/1.45 Consolas,monospace;white-space:pre-line;pointer-events:none;max-width:75%}.map-popup[hidden]{display:none}
.legend{display:flex;gap:10px;align-items:center;margin-top:10px}.legend-bar{height:10px;flex:1;max-width:270px;border-radius:8px;background:linear-gradient(90deg,#254e60,#337d78,#86a87f,#c2c18e,#d2a56d,#96754d,#f1e7d3)}.legend span{font-size:11px;color:#647880}.source-note{font-size:11px;color:#657a82;margin-top:7px;max-width:870px}.site-notes{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:12px}.site-note{padding:11px 13px;border:1px solid #dce8e8;background:#f7fbfb;border-radius:10px;text-align:left;color:var(--text)}button.site-note:hover{border-color:#82c5be;background:#edf8f5}button.site-note{cursor:pointer}.site-note strong{display:block;font-size:13px}.site-note span{font-size:11px;color:#5f777e}
.map-bottom{margin-top:12px;display:flex;gap:12px;flex-wrap:wrap;align-items:center}.map-bottom a{color:#086c7b;font-size:12px;text-decoration:none;font-weight:700}.map-bottom a:hover{text-decoration:underline}.evidence{margin-top:13px;border-top:1px solid #e6eff0;padding-top:13px}.evidence h3{font-size:14px}.evidence .line{margin:5px 0;color:#4c656e;font-size:12px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:14px}.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.tile{background:#f3f8f9;border:1px solid #dde9ea;border-radius:13px;padding:15px}.tile h3{margin:0 0 6px}.tile .value{font-size:24px;font-weight:800;letter-spacing:-.04em;color:#0c6573}.rankline{display:grid;grid-template-columns:145px 1fr 48px;align-items:center;gap:10px;margin:9px 0;font-size:12px}.barbg{height:10px;border-radius:8px;background:#e7eeee;overflow:hidden}.barfill{height:100%;border-radius:8px;background:linear-gradient(90deg,#0b7787,#68b9a5)}
.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;min-width:630px}th,td{padding:11px 12px;border-bottom:1px solid #e7eff0;font-size:12px;text-align:left}th{text-transform:uppercase;letter-spacing:.08em;font-size:10px;color:#627984;background:#f4f9f9}tbody tr:hover{background:#f6faf9}.table-button{border:0;background:none;color:#087182;font-weight:700;padding:0;text-decoration:underline;text-decoration-color:#a2d4cf}
.footer{border-top:1px solid #d9e5e6;padding:22px 0 10px;margin-top:24px;color:#58727c;font-size:11px}.sourcehash{font:11px Consolas,monospace;word-break:break-all;color:#5c7580}.profile-card{border:1px solid #dae8e9;background:#f9fcfc;border-radius:12px;padding:15px;display:flex;flex-direction:column;gap:6px}.profile-card strong{font-size:16px}.profile-card span{font-size:12px;color:#56737e}.profile-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:11px}.warnnote{border-left:3px solid #bd8d53;background:#fff9ee;padding:11px 14px;border-radius:0 10px 10px 0;color:#74562d}.source-panel{background:#f8fbfb;padding:12px;border:1px solid #e0e9eb;border-radius:9px;margin:6px 0}

/* V2.0.2: Mars MOLA atlas and geographic research cards. */
.research-panels{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin:15px 0}
.research-panel{background:#f5faf9;border:1px solid #dbe9e9;border-radius:11px;padding:12px;min-height:103px}
.research-panel strong{display:block;font-size:11px;letter-spacing:.04em;text-transform:uppercase;color:#1a7880;margin-bottom:6px}
.research-panel p{margin:0!important;font-size:12px;line-height:1.5;color:#39555f}
.mars-explore{display:grid;grid-template-columns:330px minmax(0,1fr);gap:16px;align-items:start}
.mars-list{display:flex;flex-direction:column;gap:7px}
.mars-choice{border:1px solid #d4e6e5;border-radius:11px;padding:11px 13px;background:#f8fbfb;text-align:left;color:#244a56}
.mars-choice strong{display:block;font-size:13px}
.mars-choice span{display:block;color:#66818a;font-size:11px}
.mars-choice[aria-current=true]{background:#e8f6f3;border-color:#7fcec0;box-shadow:inset 3px 0 #148e83}
.mars-map-wrap{border:1px solid #d2e5e4;overflow:hidden;border-radius:12px;background:#d8e4e4;position:relative;margin:10px 0}
.mars-map-wrap canvas{display:block;width:100%;height:375px;cursor:crosshair;image-rendering:auto}
.mars-map-overlay{background:#112f3de3;color:#fff;font-size:11px;padding:7px 10px;border-radius:8px;position:absolute;top:12px;left:12px;pointer-events:none}
.mars-map-tip{background:#112f3de3;color:#fff;font:12px Consolas,monospace;white-space:pre-line;padding:8px 10px;border-radius:8px;position:absolute;bottom:12px;left:12px;pointer-events:none}
.mars-map-tip[hidden]{display:none}.mars-map-missing[hidden]{display:none}
.mars-map-missing{height:375px;display:flex;align-items:center;justify-content:center;padding:20px;text-align:center;color:#567;}
.mars-evidence{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0}
.mars-evidence div{border-radius:9px;background:#eff7f7;padding:10px}
.mars-evidence strong{display:block;font-size:18px;color:#116875}
.mars-evidence span{font-size:11px;color:#57747d}
@media(max-width:960px){.mars-explore{grid-template-columns:1fr}.mars-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:730px){.research-panels{grid-template-columns:1fr}.mars-list{grid-template-columns:1fr}.mars-map-wrap canvas{height:310px}}

@media(max-width:1000px){.explore{grid-template-columns:280px 1fr}.profile-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:730px){.header{padding:24px 17px 66px}.page{padding:0 12px 22px}.kpis{grid-template-columns:repeat(2,1fr)}.kpi{padding:12px}.explore{grid-template-columns:1fr}.list{max-height:270px}.detail-metrics,.tiles{grid-template-columns:repeat(2,1fr)}.profile-grid,.cols{grid-template-columns:1fr}.map-box canvas{height:320px}.panel{padding:15px}.site-notes{grid-template-columns:1fr}.header h1{font-size:30px}}
@media print{.header{padding:18px 25px;background:#143c48!important;color:white!important}.nav,.side,.map-controls,.filterline{display:none!important}.explore,.cols{display:block}.panel{break-inside:avoid;box-shadow:none}.view[hidden]{display:none!important}.view:not(#view-candidates){display:none!important}.page{padding:4px}.map-box canvas{height:310px}}
"""
    css += r"""
.world-map-wrap{border:1px solid #cadde0;border-radius:14px;overflow:hidden;position:relative;background:#dcecf1;margin:12px 0 8px}
.world-map-wrap canvas{width:100%;height:auto;aspect-ratio:1000/500;display:block;cursor:crosshair;touch-action:manipulation}
.world-hint{position:absolute;top:12px;left:12px;background:#12313bcc;color:#fff;border-radius:8px;font-size:11px;padding:7px 10px;pointer-events:none}
.world-tip{position:absolute;right:12px;bottom:12px;background:#12313bf0;color:white;white-space:pre-line;border-radius:9px;padding:9px 12px;font-size:12px;max-width:60%;pointer-events:none}
.world-tip[hidden]{display:none}
.world-stats{display:flex;gap:9px;flex-wrap:wrap;margin:10px 0}.world-stats span{padding:5px 10px;background:#eaf5f3;color:#205863;border-radius:20px;font-size:12px}
.moon-layout{display:grid;grid-template-columns:220px 1fr;gap:16px}
.moon-list{display:flex;flex-direction:column;gap:7px}.moon-choice{border:1px solid #d6e5e8;background:#f8fbfb;border-radius:10px;color:#315d67;padding:11px 12px;text-align:left}
.moon-choice strong{display:block}.moon-choice span{display:block;font-size:11px;color:#6b8187}.moon-choice[aria-current=true]{background:#dff2f0;border-color:#5dbbb3}
.moon-map-wrap{position:relative;border-radius:12px;background:#e0eaeb;overflow:hidden;border:1px solid #ccdcdf;margin-top:12px}
.moon-map-wrap canvas{width:100%;height:410px;display:block;cursor:crosshair}.moon-map-missing{padding:50px 25px;min-height:250px;display:flex;align-items:center;justify-content:center;text-align:center;color:#5e7580}
.moon-map-missing[hidden]{display:none}.moon-map-tip{position:absolute;bottom:12px;left:12px;background:#112f3de9;color:#fff;padding:7px 10px;white-space:pre-line;border-radius:8px;font-size:12px;pointer-events:none}.moon-map-tip[hidden]{display:none}
.audit-layout{display:grid;grid-template-columns:300px 1fr;gap:15px}.audit-list{max-height:650px;overflow:auto;display:flex;flex-direction:column;gap:6px}
.audit-choice{background:#f6fafa;border:1px solid #dce7e8;border-radius:9px;padding:9px 12px;text-align:left;color:#29525d}.audit-choice[aria-current=true]{background:#e4f4f1;border-color:#81cbbf}
.audit-choice span{display:block;font-size:11px;color:#70858b}.audit-detail{border:1px solid #dce8e9;border-radius:12px;padding:20px;background:#fcfefe}.audit-detail ul{padding-left:20px}.audit-detail li{margin:9px 0;line-height:1.55}.audit-badges{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 16px}

/* V2.0.5 fullscreen-style continuous world explorer */
.world-panel{padding:22px}.world-tools{display:flex;align-items:end;gap:10px;flex-wrap:wrap;padding:6px 0 10px}
.world-picker{flex:1;min-width:230px}.world-picker label{font-weight:700;font-size:12px;color:#3b6470;display:block;margin-bottom:4px}
.world-picker select{width:100%;background:#f8fcfb;border:1px solid #b8d5d9;border-radius:9px;padding:10px;font-size:13px;color:#214b55}
.world-action,.world-zoom-controls button{border:1px solid #a4c9ca;border-radius:9px;background:#116c76;color:white;padding:10px 13px;font-weight:700;font-size:12px;cursor:pointer}
.world-action.secondary{background:#f5fbfa;color:#1a6873}.world-action:hover{filter:brightness(.93)}.world-zoom-controls{display:flex;gap:5px;align-items:center}
.world-zoom-controls button{background:#f0f8f8;color:#245f69}.world-zoom-controls button:nth-child(-n+2){font-size:18px;padding:4px 12px}
.world-level{font:700 13px Consolas,monospace;color:#285c68;min-width:34px;text-align:right}
.world-layers{display:flex;flex-wrap:wrap;gap:10px 20px;margin:6px 0 12px;color:#355e69;font-size:12px}
.world-layers label{display:flex;align-items:center;gap:5px;cursor:pointer}.world-layers input{accent-color:#147f85}
.world-map-wrap{border:1px solid #a3bfc4;background:#194059;border-radius:12px;overflow:hidden;position:relative;min-height:340px;margin:8px 0 0}
.world-map-wrap canvas{display:block;width:100%;height:auto;aspect-ratio:16/9;min-height:340px;cursor:grab;touch-action:none}
.world-hint{position:absolute;top:11px;left:11px;max-width:75%;padding:8px 10px;background:#142f3ad9;color:white;font-size:11px;border-radius:8px;pointer-events:none}
.world-tip{position:absolute;bottom:12px;left:12px;background:#132d39e8;color:#fff;white-space:pre-line;font:12px/1.45 Consolas,monospace;padding:9px 12px;border-radius:8px;pointer-events:none}
.world-tip[hidden]{display:none}.world-depth-indicator{position:absolute;right:12px;bottom:12px;background:#132d39be;color:#fff;font-size:11px;padding:7px 9px;border-radius:7px;pointer-events:none}
.world-map-foot{display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap;background:#eaf4f5;border-radius:0 0 9px 9px;padding:9px 12px;font-size:11px;color:#355f6a}
.world-active{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap;align-items:center;background:#f3f9f8;border:1px solid #d9e8e7;border-radius:11px;margin:13px 0;padding:14px 16px}
.world-active h3{margin:3px 0}.world-active p{margin:2px 0}.world-active-actions{display:flex;flex-wrap:wrap;gap:8px}
.world-legend{display:flex;gap:10px 18px;flex-wrap:wrap;font-size:12px;color:#516f78;margin-bottom:12px}.world-legend span{display:flex;align-items:center;gap:6px}.world-legend b{display:inline-block;width:12px;height:12px;border-radius:50%;border:1px solid white;box-shadow:0 0 0 1px #aac6cb}
@media(max-width:700px){.world-panel{padding:12px}.world-hint{font-size:10px}.world-picker{min-width:100%}.world-map-wrap canvas{min-height:275px}.world-active-actions{width:100%}}
@media(max-width:780px){.moon-layout,.audit-layout{grid-template-columns:1fr}.moon-list{display:grid;grid-template-columns:repeat(2,1fr)}.world-map-wrap canvas{min-height:280px}.moon-map-wrap canvas{height:310px}}
"""
    js = r"""
'use strict';
const DATA=JSON.parse(document.getElementById('dataset').textContent);
const el=id=>document.getElementById(id);const all=s=>document.querySelectorAll(s);
const fmt=n=>n===null||n===undefined?'—':String(n);
const number=(n,d=1)=>n===null||n===undefined?'—':Number(n).toLocaleString('es-ES',{maximumFractionDigits:d});
const rank=n=>n===null||n===undefined?'—':'#'+n;
const coord=(lat,lon,d=3)=>`${Math.abs(lat).toFixed(d)}° ${lat<0?'S':'N'} · ${Math.abs(lon).toFixed(d)}° ${lon<0?'O':'E'}`;
const make=(tag,txt,cls)=>{const x=document.createElement(tag);if(txt!==undefined)x.textContent=String(txt);if(cls)x.className=cls;return x};
const add=(node,tag,text,cls)=>{const x=make(tag,text,cls);node.appendChild(x);return x};
const place=(id,txt)=>{el(id).textContent=String(txt??'—')};
const atlas=DATA.topographic_atlas;
place('climate-coverage',`Clima NASA POWER: ${DATA.climate_v203.complete} completos, ${DATA.climate_v203.partial} parciales y ${DATA.climate_v203.missing} pendientes entre ${atlas.entries.length} candidatos.`);
const byId=new Map(atlas.entries.map(x=>[x.id,x]));
place('kpi-profiles',DATA.profiles.length);place('kpi-anchor',atlas.entries.length);place('kpi-pairs',DATA.correspondence_pairs);place('kpi-priority',DATA.candidates.length);
const labels=Object.fromEntries(atlas.entries.map(e=>[e.id,e.label]));
let current='r026_c146',mapId='r026_c146',filter='all';
let showContours=true,showMask=true,showFootprint=false;
const scaleKeys=['15km_17x17','30km_9x9','40km_7x7'];
// Navigation: no external JS or network needed.
all('.nav button').forEach(b=>b.addEventListener('click',()=>{
  all('.nav button').forEach(x=>x.setAttribute('aria-selected',x===b?'true':'false'));
  all('.view').forEach(x=>x.hidden=x.id!=='view-'+b.dataset.view);
  if(b.dataset.view==='candidates')requestAnimationFrame(drawTopo);
}));
function openCandidate(id,section=true){
  const record=byId.get(id);if(!record)return;
  current=id;mapId=id;candidateFocus();
  if(section){const b=document.querySelector('.nav button[data-view="candidates"]');b.click()}
  


renderCandidateList();showDetail();
  if(section||window.innerWidth<735)el('details-top').scrollIntoView({behavior:'smooth',block:'start'});
}
function renderCandidateList(){
  const term=el('search-candidates').value.trim().toLowerCase();
  const list=el('candidate-list');list.replaceChildren();
  const entries=atlas.entries.filter(x=>
    (filter==='all'||(filter==='top10'&&x.topographic_rank<=10)||(filter==='volcanic'&&x.volcanic_points>0))&&
    (x.label.toLowerCase().includes(term)||x.id.toLowerCase().includes(term)||coord(x.center_lat,x.center_lon).toLowerCase().includes(term)));
  for(const c of entries){
    const b=make('button',undefined,'candidate-option');b.type='button';b.setAttribute('aria-current',c.id===current?'true':'false');
    add(b,'b',c.label);add(b,'span',rank(c.topographic_rank),'rank');
    add(b,'span',`${c.id} · ${coord(c.center_lat,c.center_lon,0)}`,'coordinates');
    if(c.volcanic_points>0)add(b,'span',`${c.volcanic_points} observaciones volcánicas GLiM`,'priority-tag');
    b.addEventListener('click',()=>openCandidate(c.id,false));list.appendChild(b);
  }
  if(!entries.length)add(list,'div','No hay candidatos para ese filtro.','small');
  place('candidate-count',entries.length+' regiones');
}
el('search-candidates').addEventListener('input',renderCandidateList);
all('.filterline button').forEach(b=>b.addEventListener('click',()=>{filter=b.dataset.filter;all('.filterline button').forEach(x=>x.setAttribute('aria-pressed',x===b?'true':'false'));renderCandidateList()}));
function mapTab(label,id){const b=make('button',label);b.setAttribute('aria-selected',mapId===id?'true':'false');b.addEventListener('click',()=>{mapId=id;candidateFocus();showDetail()});return b}
function showDetail(){
 const c=byId.get(current);if(!c)return;
 place('selected-name',c.label);place('selected-code',c.id);place('selected-coords',coord(c.center_lat,c.center_lon));
 place('selected-rank',rank(c.topographic_rank));const nGlM=Object.values(c.lithology_counts).reduce((a,b)=>a+Number(b),0);place('selected-volcanic',nGlM?c.volcanic_points+'/'+nGlM:'Sin datos');
 place('selected-scale',c.scale_ranks?scaleKeys.map(k=>rank(c.scale_ranks[k])).join(' / '):'Sin auditoría individual');
 place('selected-kind',!nGlM?'Observaciones GLiM no disponibles':c.volcanic_points?'Señal volcánica cartográfica':'Otras litologías en el muestreo GLiM');
 const box=el('rock-types');box.replaceChildren();
 for(const[k,v]of Object.entries(c.lithology_counts))add(box,'div',`${k}: ${v} de 9 puntos`,'line');
 if(!Object.keys(c.lithology_counts).length)add(box,'div','No hay datos GLiM.','line');
 place('selected-explainer',c.id==='r026_c146'
   ?'Argentina fue sexta de 2.617 regiones para Elysium. Sus puestos bajo las tres escalas fueron 2, 6 y 16; cuenta además con dos sectores volcánicos estudiados con NASADEM.'
   :c.volcanic_points?`Ubicación: ${c.country}. Puesto ${c.topographic_rank} para Elysium. El muestreo GLiM contiene ${c.volcanic_points} observaciones volcánicas o piroclásticas entre nueve puntos.`
   :`Ubicación: ${c.country}. Puesto ${c.topographic_rank} según relieve. El muestreo GLiM documentó otros materiales; no demuestra ausencia total de vulcanismo.`);
 const m0=atlas.maps[current],earthLand=c.climate_earth_context;
 place('earth-terrain-summary',c.relief_context_m===null?'No se dispone del mosaico topográfico regional en esta instalación.':`En el mapa regional ETOPO, la elevación va de ${number(m0.elevation_min_m,0)} a ${number(m0.elevation_max_m,0)} m; diferencia P98–P02: ${number(c.relief_context_m,0)} m. Es relieve de contexto, no de los nueve puntos GLiM.`);
 const sorted=Object.entries(c.lithology_counts).sort((a,b)=>Number(b[1])-Number(a[1]));
 place('earth-geology-summary',sorted.length?`Predomina en las observaciones GLiM la categoría «${sorted[0][0]}» (${sorted[0][1]} de 9). ${c.volcanic_points?`Se registraron ${c.volcanic_points} puntos de clases volcánicas o piroclásticas.`:'No se registraron clases volcánicas en los puntos seleccionados.'}`:'Sin muestreo GLiM disponible.');
 place('earth-climate-summary',earthLand?`NASA POWER (centro de celda): temperatura media ${number(earthLand.air_temp_mean_c,1)} °C; precipitación anual ${number(earthLand.precip_annual_mean_mm,0)} mm; humedad relativa ${number(earthLand.relative_humidity_mean_pct,0)} %; amplitud térmica estacional ${number(earthLand.seasonal_air_temp_range_c,1)} °C. ${earthLand.climate_descriptor||''}. ${earthLand.source_detail||''}. Contexto terrestre puntual, no del planeta Marte.`:'NASA POWER: datos no disponibles para este centro; el lanzador puede intentar descargarlos. Nunca se estiman a partir del país.');
 const tabs=el('map-tabs');tabs.replaceChildren();tabs.appendChild(mapTab('Relieve regional · ETOPO',current));
 if(current==='r026_c146')for(const s of atlas.local_sites)tabs.appendChild(mapTab(s.id.endsWith('p04')?'p04 · NASADEM':'p08 · NASADEM',s.id));
 const active=atlas.maps[mapId];
 el('mask-toggle').disabled=!(active&&active.volcanic_mask);
 el('mask-toggle').setAttribute('aria-pressed',showMask?'true':'false');
 place('map-source-label',active?.source==='NASADEM_HGT.001'?'Visor continuo · detalle NASADEM': 'Visor continuo · ETOPO mundial');
 place('map-citation',(active?.caption||active?.reason||'Mapa no disponible')+' El mapa principal se puede explorar sin bordes; la resolución cambia con el zoom.');
 place('map-level',active?.status==='available'?`${number(active.elevation_min_m,0)} a ${number(active.elevation_max_m,0)} m`:'Sin elevación');
 let site=atlas.local_sites.find(s=>s.id===mapId);
 el('site-comparison').hidden=current!=='r026_c146';
 el('site-active-details').hidden=!site;
 if(site){place('site-active-title',site.label);place('site-active-coord',coord(site.lat,site.lon,5));place('site-active-metrics',`Recorte GLiM: ${number(site.metrics.glim_clip_km2)} km² · Pendiente mediana: ${number(site.metrics.slope_median_deg,3)}° · Rugosidad mediana: ${number(site.metrics.roughness_median_m,3)} m`)}
 const loc=site?{lat:site.lat,lon:site.lon}:{lat:c.center_lat,lon:c.center_lon};
 el('osm-link').href=`https://www.openstreetmap.org/?mlat=${loc.lat}&mlon=${loc.lon}#map=10/${loc.lat}/${loc.lon}`;
 drawTopo();
}
// Topographic Canvas: real elevations from ETOPO or NASADEM, never decorative fake terrain.
const canvas=el('topo-canvas');const cx=canvas.getContext('2d');
const colors=[[37,78,96],[47,121,117],[121,160,123],[188,188,138],[206,158,102],[139,102,76],[237,228,205]];
function colorRamp(t){t=Math.max(0,Math.min(.99999,t));let f=t*(colors.length-1),i=Math.floor(f),u=f-i;return colors[i].map((x,k)=>Math.round(x*(1-u)+colors[i+1][k]*u))}
const cachedRaster=new Map();
function raster(m,id){if(cachedRaster.has(id))return cachedRaster.get(id);
 const z=m.elevation,H=z.length,W=z[0].length;
 const tmp=document.createElement('canvas');tmp.width=W;tmp.height=H;const c=tmp.getContext('2d');const image=c.createImageData(W,H);
 const den=Math.max(1,m.elevation_p98_m-m.elevation_p02_m);
 for(let y=0;y<H;y++)for(let x=0;x<W;x++){
  const v=z[H-1-y][x],idx=4*(y*W+x);
  if(v===null){image.data[idx]=37;image.data[idx+1]=77;image.data[idx+2]=105;image.data[idx+3]=255;continue;}
  const t=(v-m.elevation_p02_m)/den;
  const [r,g,b]=colorRamp(t);let shade=1;
  if(x>0&&x<W-1&&y>0&&y<H-1){
    const neighbor=(dy,dx)=>z[H-1-y+dy][x+dx];
    const a=neighbor(0,1),b0=neighbor(0,-1),d=neighbor(1,0),e=neighbor(-1,0);
    if(a!==null&&b0!==null&&d!==null&&e!==null){
      const dx=(a-b0)/den,dy=(d-e)/den;
      shade=Math.max(.68,Math.min(1.24,1+(dx-dy)*.82));
    }
  }
  image.data[idx]=Math.min(255,r*shade);image.data[idx+1]=Math.min(255,g*shade);image.data[idx+2]=Math.min(255,b*shade);image.data[idx+3]=255;
 }
 c.putImageData(image,0,0);cachedRaster.set(id,tmp);return tmp;
}
// Shared geographic projection helpers for the independent Mars/Lunar atlases.
function topox(lon,b,W){return (lon-b[0])/(b[2]-b[0])*W}
function topoy(lat,b,H){return (b[3]-lat)/(b[3]-b[1])*H}
// V2.0.6 — georeferenced, continuous candidate explorer with zoom-adaptive LOD.
// Base relief is the verified full-world ETOPO image; NASADEM is only overlaid
// at its real coordinates when the user zooms into the two available sectors.
const candidateSource=DATA.continuous_terrain_v205||{status:'unavailable'};
const candidateCamera={lon:-67,lat:-37,z:30,drag:null};
let candidateTexture=null,candidatePyramid=[],candidateCodes=null;
let candidateDecodedWidth=0,candidateDecodedHeight=0,candidateDrawPending=false;
const candidateSiteCache=new Map();
const candidateNormLon=v=>((v+180)%360+360)%360-180;
function candidateDimensions(){return {w:canvas.width,h:canvas.height,wmap:canvas.width*candidateCamera.z,hmap:canvas.width*candidateCamera.z/2}}
function candidateClamp(){
 candidateCamera.lon=candidateNormLon(candidateCamera.lon);
 const {h,hmap}=candidateDimensions();
 const maxLat=Math.max(0,90-90*h/hmap);
 candidateCamera.lat=Math.max(-maxLat,Math.min(maxLat,candidateCamera.lat));
}
function candidateXY(lon,lat){const b=candidateDimensions();return [b.w/2+candidateNormLon(lon-candidateCamera.lon)/360*b.wmap,b.h/2-(lat-candidateCamera.lat)/180*b.hmap]}
function candidateLL(x,y){const b=candidateDimensions();return {lon:candidateNormLon(candidateCamera.lon+(x-b.w/2)/b.wmap*360),lat:Math.max(-90,Math.min(90,candidateCamera.lat-(y-b.h/2)/b.hmap*180))}}
function candidateFocus(){
 const site=atlas.local_sites.find(s=>s.id===mapId),c=byId.get(current);
 if(!c)return;
 candidateCamera.lon=site?site.lon:c.center_lon;
 candidateCamera.lat=site?site.lat:c.center_lat;
 // Candidate regional view ~12 km-equivalent degrees wide; NASADEM site view subdegree.
 candidateCamera.z=site?520:30;
 candidateClamp();
}
function candidateSample(lon,lat){
 if(!candidateCodes)return null;
 const west=candidateSource.raster_lon_west_edge_deg??-180;
 const north=candidateSource.raster_lat_north_edge_deg??90;
 let x=Math.floor((((lon-west)%360+360)%360)/360*candidateDecodedWidth);
 let y=Math.floor((north-lat)/180*candidateDecodedHeight);
 if(y<0||y>=candidateDecodedHeight)return null;
 x=Math.max(0,Math.min(candidateDecodedWidth-1,x));
 const n=candidateCodes[y*candidateDecodedWidth+x];return n===65535?null:n-32768;
}
function candidateSiteSample(lon,lat){
 if(candidateCamera.z<85)return null;
 for(const s of atlas.local_sites){
  const m=atlas.maps[s.id];if(m?.status!=='available')continue;
  const [w,so,e,n]=m.bounds;
  if(lon<w||lon>e||lat<so||lat>n)continue;
  const x=Math.max(0,Math.min(m.shape[1]-1,Math.round((lon-w)/(e-w)*(m.shape[1]-1))));
  const y=Math.max(0,Math.min(m.shape[0]-1,Math.round((lat-so)/(n-so)*(m.shape[0]-1))));
  const value=m.elevation[y][x];
  if(value!==null)return {value,source:'NASADEM',mask:m.volcanic_mask?.[y]?.[x]??null};
 }
 return null;
}
// A mipmap is a genuine lower-resolution resampling of the *same* ETOPO source;
// it lowers render cost while zooming out, without claiming any new terrain detail.
function candidateCreatePyramid(img){
 const levels=[img];let previous=img;
 for(let i=0;i<6&&Math.max(previous.width,previous.height)>64;i++){
  const w=Math.max(1,Math.ceil(previous.width/2)),h=Math.max(1,Math.ceil(previous.height/2));
  const tmp=document.createElement('canvas');tmp.width=w;tmp.height=h;
  const context=tmp.getContext('2d');context.imageSmoothingEnabled=true;
  context.imageSmoothingQuality='high';context.drawImage(previous,0,0,w,h);
  levels.push(tmp);previous=tmp;
 }
 return levels;
}
function candidateSelectLevel(){
 if(!candidatePyramid.length)return {image:null,level:-1};
 const full=candidatePyramid[0];
 const pxPerSource=canvas.width*candidateCamera.z/full.width;
 const idx=Math.max(0,Math.min(candidatePyramid.length-1,Math.floor(Math.log2(1/Math.max(pxPerSource,.00001)))));
 return {image:candidatePyramid[idx],level:idx};
}
function candidateDrawGlobal(){
 const b=candidateDimensions();cx.fillStyle='#194159';cx.fillRect(0,0,b.w,b.h);
 const {image,level}=candidateSelectLevel();
 if(!image)return level;
 const west=candidateSource.raster_lon_west_edge_deg??-180;
 const north=candidateSource.raster_lat_north_edge_deg??90;
 const left=b.w/2+(west-candidateCamera.lon)/360*b.wmap;
 const top=b.h/2-(north-candidateCamera.lat)/180*b.hmap;
 // Clip source and destination to the visible viewport. Never ask Canvas to
 // resize a 2160x1080 world image to hundreds of thousands of screen pixels.
 const start=Math.floor(-left/b.wmap)-1,end=Math.ceil((b.w-left)/b.wmap)+1;
 cx.imageSmoothingEnabled=(level>0 || canvas.width*candidateCamera.z/image.width<8);
 for(let k=start;k<=end;k++){
  const x=left+k*b.wmap,y=top;
  const dx=Math.max(0,x),dy=Math.max(0,y);
  const right=Math.min(b.w,x+b.wmap),bottom=Math.min(b.h,y+b.hmap);
  if(dx>=right||dy>=bottom)continue;
  const sx=Math.max(0,(dx-x)/b.wmap*image.width),sy=Math.max(0,(dy-y)/b.hmap*image.height);
  const sw=Math.min(image.width-sx,(right-dx)/b.wmap*image.width);
  const sh=Math.min(image.height-sy,(bottom-dy)/b.hmap*image.height);
  if(sw>0&&sh>0)cx.drawImage(image,sx,sy,sw,sh,dx,dy,right-dx,bottom-dy);
 }
 return level;
}
function candidateSiteRaster(m,id,masked){
 const key=id+(masked?'_mask':'_clean');if(candidateSiteCache.has(key))return candidateSiteCache.get(key);
 const base=raster(m,id),t=document.createElement('canvas');t.width=base.width;t.height=base.height;
 const ct=t.getContext('2d',{willReadFrequently:true});ct.drawImage(base,0,0);
 const im=ct.getImageData(0,0,t.width,t.height);
 for(let y=0;y<t.height;y++)for(let x=0;x<t.width;x++){
  const p=4*(y*t.width+x),edge=Math.min(x,y,t.width-1-x,t.height-1-y);
  // Feather the DEM patch to remove the hard rectangular seam against ETOPO.
  const tFade=Math.max(0,Math.min(1,edge/Math.max(2,Math.min(t.width,t.height)*.24)));
  const alpha=tFade*tFade*(3-2*tFade);
  im.data[p+3]=Math.round(255*alpha);
  if(masked&&m.volcanic_mask?.[t.height-1-y]?.[x]===0){
   im.data[p]=Math.round(im.data[p]*.48);
   im.data[p+1]=Math.round(im.data[p+1]*.53);
   im.data[p+2]=Math.round(im.data[p+2]*.58);
  }
 }
 ct.putImageData(im,0,0);candidateSiteCache.set(key,t);return t;
}
function candidateDrawLocal(){
 if(candidateCamera.z<85)return;
 const W=canvas.width,H=canvas.height;
 for(const site of atlas.local_sites){
  const m=atlas.maps[site.id];if(m?.status!=='available')continue;
  const tl=candidateXY(m.bounds[0],m.bounds[3]),br=candidateXY(m.bounds[2],m.bounds[1]);
  const width=br[0]-tl[0],height=br[1]-tl[1];
  if(width<2||height<2||br[0]<0||tl[0]>W||br[1]<0||tl[1]>H)continue;
  cx.imageSmoothingEnabled=true;cx.drawImage(candidateSiteRaster(m,site.id,showMask),tl[0],tl[1],width,height);
  if(width>80){cx.font='700 12px Segoe UI';cx.fillStyle='#fff';cx.strokeStyle='#102935';cx.lineWidth=3;
   const text=site.id.slice(-3).toUpperCase()+' · NASADEM';cx.strokeText(text,tl[0]+7,tl[1]+17);cx.fillText(text,tl[0]+7,tl[1]+17)}
 }
}
function candidateDrawFootprint(){
 const c=byId.get(current),site=atlas.local_sites.find(s=>s.id===mapId);if(!c)return;
 const bounds=site?atlas.maps[mapId]?.bounds:c.cell_bounds;
 if(showFootprint&&bounds){const [w,s,e,n]=bounds,tl=candidateXY(w,n),br=candidateXY(e,s);
  if(br[0]>=tl[0]){cx.strokeStyle='#fff8e2';cx.lineWidth=1.6;cx.setLineDash([6,5]);
   cx.strokeRect(tl[0],tl[1],br[0]-tl[0],br[1]-tl[1]);cx.setLineDash([])}}
 const lat=site?site.lat:c.center_lat,lon=site?site.lon:c.center_lon;
 const [x,y]=candidateXY(lon,lat);if(x<0||x>canvas.width||y<0||y>canvas.height)return;
 cx.beginPath();cx.arc(x,y,6,0,2*Math.PI);cx.fillStyle='#ef6942';cx.fill();cx.lineWidth=2.4;cx.strokeStyle='#fff';cx.stroke();
 cx.font='700 12px Segoe UI';cx.fillStyle='#fff';cx.lineWidth=3.4;cx.strokeStyle='#1c343e';
 const label=site?site.id.slice(-3).toUpperCase():c.id;
 cx.strokeText(label,x+11,y-11);cx.fillText(label,x+11,y-11);
}
function candidateLocalContours(){
 if(!showContours||candidateCamera.z<=300)return;
 for(const site of atlas.local_sites){
  const m=atlas.maps[site.id];if(m?.status!=='available')continue;
  const tl=candidateXY(m.bounds[0],m.bounds[3]),br=candidateXY(m.bounds[2],m.bounds[1]);
  const width=br[0]-tl[0],height=br[1]-tl[1];
  if(br[0]<0||tl[0]>canvas.width||br[1]<0||tl[1]>canvas.height||width<12)continue;
  const nY=m.shape[0],nX=m.shape[1],step=Math.max(1,Math.ceil(Math.max(nY,nX)/75));
  const levels=[10,20,25,50,100,200,500,1000].find(v=>(m.elevation_p98_m-m.elevation_p02_m)/v<=8)||1000;
  cx.save();cx.strokeStyle='#f7f7e2ab';cx.lineWidth=.8;
  for(let level=Math.ceil(m.elevation_p02_m/levels)*levels,count=0;
      level<m.elevation_p98_m&&count<9;level+=levels,count++){
   cx.beginPath();
   for(let y=0;y<nY-1;y+=step)for(let x=0;x<nX-1;x+=step){
    const stepX=Math.min(step,nX-1-x),stepY=Math.min(step,nY-1-y);
    const v=[m.elevation[nY-1-y][x],m.elevation[nY-1-y][x+stepX],
             m.elevation[nY-1-y-stepY][x+stepX],m.elevation[nY-1-y-stepY][x]];
    if(v.some(q=>q===null))continue;
    const xy=[[0,0],[1,0],[1,1],[0,1]];let hits=[];
    for(let edge=0;edge<4;edge++){
     const q=(edge+1)%4;
     if((v[edge]<level)!==(v[q]<level)&&v[edge]!==v[q]){
      const fraction=(level-v[edge])/(v[q]-v[edge]);
      const fx=xy[edge][0]+(xy[q][0]-xy[edge][0])*fraction;
      const fy=xy[edge][1]+(xy[q][1]-xy[edge][1])*fraction;
      hits.push([tl[0]+(x+fx*stepX)/(nX-1)*width,
                 tl[1]+(y+fy*stepY)/(nY-1)*height]);
     }
    }
    for(let j=0;j+1<hits.length;j+=2){cx.moveTo(...hits[j]);cx.lineTo(...hits[j+1])}
   }cx.stroke();
  }cx.restore();
 }
}
function candidateContours(){
 if(!showContours||!candidateCodes||candidateCamera.z<5)return;
 if(candidateCamera.z>300){candidateLocalContours();return;}
 // Dynamic marching-squares on a bounded, viewport-sized elevation sample.
 // Resolution is limited to <=120 x 65; calculations never scale with zoom.
 const W=canvas.width,H=canvas.height,cell=Math.max(10,Math.ceil(W/115));
 const nx=Math.ceil(W/cell)+1,ny=Math.ceil(H/cell)+1;
 const zz=new Array(nx*ny);let low=Infinity,high=-Infinity;
 for(let y=0;y<ny;y++)for(let x=0;x<nx;x++){
  const ll=candidateLL(Math.min(W,x*cell),Math.min(H,y*cell));
  const v=candidateSample(ll.lon,ll.lat);zz[y*nx+x]=v;
  if(v!==null){low=Math.min(low,v);high=Math.max(high,v)}
 }
 if(!(high>low+50))return;
 const interval=[50,100,200,500,1000,2000,5000,10000].find(x=>(high-low)/x<=9)||10000;
 cx.save();cx.strokeStyle='#fff9ddad';cx.lineWidth=.75;
 const edgePairs=[[0,1],[1,2],[2,3],[3,0]],unit=[[0,0],[1,0],[1,1],[0,1]];
 let count=0;
 for(let level=Math.ceil(low/interval)*interval;level<high&&count<10;level+=interval,count++){
  cx.beginPath();
  for(let y=0;y<ny-1;y++)for(let x=0;x<nx-1;x++){
   const vals=[zz[y*nx+x],zz[y*nx+x+1],zz[(y+1)*nx+x+1],zz[(y+1)*nx+x]];
   if(vals.some(v=>v===null))continue;
   let ints=[];
   for(const [a,b] of edgePairs){if((vals[a]<level)!==(vals[b]<level)&&vals[a]!==vals[b]){
    const t=(level-vals[a])/(vals[b]-vals[a]);
    ints.push([Math.min(W,(x+unit[a][0]+(unit[b][0]-unit[a][0])*t)*cell),
               Math.min(H,(y+unit[a][1]+(unit[b][1]-unit[a][1])*t)*cell)])
   }}
   for(let j=0;j+1<ints.length;j+=2){cx.moveTo(...ints[j]);cx.lineTo(...ints[j+1])}
  }
  cx.stroke();
 }
 cx.restore();
}
function candidateDrawLegacy(){
 // Explicit, bounded fallback only if the historical whole-world ETOPO is missing.
 const active=atlas.maps[mapId];if(active?.status!=='available')return;
 cx.imageSmoothingEnabled=active.source==='NASADEM_HGT.001';
 cx.drawImage(raster(active,mapId),0,0,canvas.width,canvas.height);
}
function drawTopo(){
 const active=atlas.maps[mapId],miss=el('map-missing'),overlay=el('map-overlay');
 const box=canvas.getBoundingClientRect();if(box.width<10)return;
 const ratio=Math.min(window.devicePixelRatio||1,2),w=Math.round(box.width*ratio),h=Math.round(box.height*ratio);
 if(w!==canvas.width||h!==canvas.height){canvas.width=w;canvas.height=h}
 canvas.hidden=false;miss.hidden=true;overlay.hidden=false;
 candidateClamp();cx.setTransform(1,0,0,1,0,0);cx.clearRect(0,0,canvas.width,canvas.height);
 const lod=candidateDrawGlobal();
 if(!candidateTexture){
  if(candidateSource.status==='available'){
   cx.fillStyle='#e7f1f2';cx.font='13px Segoe UI';cx.fillText('Cargando relieve mundial ETOPO…',16,canvas.height/2);
  }else candidateDrawLegacy();
 }
 if(candidateTexture){candidateDrawLocal();candidateContours();candidateDrawFootprint()}
 const degWidth=360/candidateCamera.z;
 const kmWidth=degWidth*111.195*Math.max(.15,Math.cos(candidateCamera.lat*Math.PI/180));
 const resolution=(candidateTexture&&candidateCamera.z>110)?'ETOPO · resolución nativa limitada':'ETOPO · relieve mundial continuo';
 place('map-overlay',`${resolution}${candidateCamera.z>=85?' · NASADEM donde existe':''}`);
 place('map-zoom',`${number(kmWidth,0)} km de anchura aprox. · LOD ${lod>=0?lod:'—'}`);
 if(candidateCodes){let lo=Infinity,hi=-Infinity;
  for(let y=0;y<14;y++)for(let x=0;x<25;x++){
   const ll=candidateLL(x/(24)*canvas.width,y/(13)*canvas.height),site=candidateSiteSample(ll.lon,ll.lat);
   const v=site?.value??candidateSample(ll.lon,ll.lat);
   if(v!==null){lo=Math.min(lo,v);hi=Math.max(hi,v)}
  }
  place('map-level',hi>=lo?`Relieve visible aprox.: ${number(lo,0)} a ${number(hi,0)} m`:'Sin elevaciones terrestres en esta vista');
 }
}
function candidateQueueDraw(){if(candidateDrawPending)return;candidateDrawPending=true;
 requestAnimationFrame(()=>{candidateDrawPending=false;if(!el('view-candidates').hidden)drawTopo()})}
function canvasPoint(e){const r=canvas.getBoundingClientRect();return [(e.clientX-r.left)*canvas.width/r.width,(e.clientY-r.top)*canvas.height/r.height]}
function candidateZoom(factor,pt){
 const p=pt||[canvas.width/2,canvas.height/2],before=candidateLL(...p);
 candidateCamera.z=Math.max(1,Math.min(2400,candidateCamera.z*factor));
 const after=candidateLL(...p);
 candidateCamera.lon=candidateNormLon(candidateCamera.lon+before.lon-after.lon);
 candidateCamera.lat+=before.lat-after.lat;candidateClamp();candidateQueueDraw();
}
canvas.addEventListener('pointerdown',e=>{
 if(e.button!==0)return;candidateCamera.drag={pointerId:e.pointerId,pt:canvasPoint(e),lon:candidateCamera.lon,lat:candidateCamera.lat};
 canvas.setPointerCapture(e.pointerId);canvas.style.cursor='grabbing';
});
canvas.addEventListener('pointermove',e=>{
 const p=canvasPoint(e),dr=candidateCamera.drag;
 if(dr&&dr.pointerId===e.pointerId){
  const b=candidateDimensions(),dx=p[0]-dr.pt[0],dy=p[1]-dr.pt[1];
  candidateCamera.lon=candidateNormLon(dr.lon-dx/b.wmap*360);
  candidateCamera.lat=dr.lat+dy/b.hmap*180;candidateClamp();candidateQueueDraw();
 }
 const ll=candidateLL(...p),site=candidateSiteSample(ll.lon,ll.lat),v=site?.value??candidateSample(ll.lon,ll.lat);
 const tip=el('map-popup');tip.textContent=`${coord(ll.lat,ll.lon,3)}\n${site?'NASADEM':'ETOPO'}: ${v===null?'sin cota terrestre':number(v,0)+' m'}${site?.mask!==null&&site?.mask!==undefined?'\nGLiM (recorte): '+(site.mask?'volcánico':'otras litologías'):''}`;
 tip.hidden=false;
});
function candidateRelease(e){if(candidateCamera.drag&&candidateCamera.drag.pointerId===e.pointerId)candidateCamera.drag=null;
 if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);canvas.style.cursor='grab'}
canvas.addEventListener('pointerup',candidateRelease);
canvas.addEventListener('pointercancel',candidateRelease);
canvas.addEventListener('pointerleave',()=>{if(!candidateCamera.drag)el('map-popup').hidden=true});
canvas.addEventListener('wheel',e=>{e.preventDefault();candidateZoom(e.deltaY<0?1.25:1/1.25,canvasPoint(e))},{passive:false});
canvas.addEventListener('dblclick',e=>{e.preventDefault();candidateZoom(1.8,canvasPoint(e))});
function changeZoom(f){candidateZoom(f)}
el('zoom-in').addEventListener('click',()=>changeZoom(1.45));
el('zoom-out').addEventListener('click',()=>changeZoom(1/1.45));
el('zoom-reset').addEventListener('click',()=>{candidateFocus();drawTopo()});
el('contours-toggle').addEventListener('click',()=>{showContours=!showContours;el('contours-toggle').setAttribute('aria-pressed',showContours?'true':'false');drawTopo()});
el('footprint-toggle').addEventListener('click',()=>{showFootprint=!showFootprint;el('footprint-toggle').setAttribute('aria-pressed',showFootprint?'true':'false');drawTopo()});
el('mask-toggle').addEventListener('click',()=>{showMask=!showMask;el('mask-toggle').setAttribute('aria-pressed',showMask?'true':'false');drawTopo()});
all('[data-site-map]').forEach(b=>b.addEventListener('click',()=>{mapId=b.dataset.siteMap;candidateFocus();showDetail()}));
window.addEventListener('resize',()=>{if(!el('view-candidates').hidden)candidateQueueDraw()});
// Decode once: the array supports instant elevation sampling and contour lines.
if(candidateSource.status==='available'){
 const img=new Image();img.onload=()=>{candidateTexture=img;candidatePyramid=candidateCreatePyramid(img);candidateQueueDraw()};
 img.onerror=()=>{place('map-citation','No se pudo leer la textura ETOPO; comproba el archivo global.');candidateQueueDraw()};
 img.src=candidateSource.texture_data_uri;
 const enc=new Image();enc.onload=()=>{
  const tmp=document.createElement('canvas');tmp.width=enc.width;tmp.height=enc.height;
  const tc=tmp.getContext('2d',{willReadFrequently:true});tc.drawImage(enc,0,0);
  const bytes=tc.getImageData(0,0,enc.width,enc.height).data;
  candidateDecodedWidth=enc.width;candidateDecodedHeight=enc.height;
  candidateCodes=new Uint16Array(enc.width*enc.height);
  for(let i=0;i<candidateCodes.length;i++)candidateCodes[i]=bytes[i*4]*256+bytes[i*4+1];
  candidateQueueDraw();
 };enc.src=candidateSource.height_data_uri;
}

// Quantitative comparisons and all 25 rows remain accessible, including their coordinates.
const comparison=el('comparison-rows');
for(const c of DATA.candidates){const row=byId.get(c.id),tr=make('tr');
 let b=make('button',row?.label||c.id,'table-button');b.addEventListener('click',()=>openCandidate(c.id));let td=make('td');td.appendChild(b);tr.appendChild(td);
 [rank(c.rank),rank(c.scale_ranks['15km_17x17']),rank(c.scale_ranks['30km_9x9']),rank(c.scale_ranks['40km_7x7']),`${c.volcanic_samples}/${c.glim_samples}`].forEach(x=>add(tr,'td',x));comparison.appendChild(tr)}
for(const c of DATA.candidates){const d=make('div',undefined,'tile');add(d,'h3',labels[c.id]||c.id);add(d,'div',rank(c.rank),'value');add(d,'p',`Puesto 30 km · ${coord(byId.get(c.id).center_lat,byId.get(c.id).center_lon,0)}`,'small');for(const [key,label] of [['15km_17x17','15 km'],['30km_9x9','30 km'],['40km_7x7','40 km']]){const line=make('div',undefined,'rankline');add(line,'span',label);const bg=make('div',undefined,'barbg'),fill=make('div',undefined,'barfill');fill.style.width=Math.max(2,100*(51-Math.min(c.scale_ranks[key],50))/50)+'%';bg.appendChild(fill);line.appendChild(bg);add(line,'b',rank(c.scale_ranks[key]));d.appendChild(line)}let b=make('button','Ver mapa topográfico','table-button');b.addEventListener('click',()=>openCandidate(c.id));d.appendChild(b);el('comparison-cards').appendChild(d)}

const completeTable=el('comparison-all25-rows');
if(completeTable){
 const coverage=DATA.full_sensitivity_v204?.coverage||0;
 place('comparison-all25-caption',coverage===atlas.entries.length
   ?`${coverage} auditorías completas: 3 métodos de distancia, 3 escalas topográficas, 60 perturbaciones de pesos y muestras GLiM.`
   :'Auditoría ampliada pendiente; ejecutá EJECUTAR_V2.ps1 para completar las 25 regiones.');
 for(const r of [...atlas.entries].sort((a,b)=>(a.topographic_rank??99999)-(b.topographic_rank??99999))){
  const tr=make('tr'),td=make('td');const btn=make('button',r.label,'table-button');
  btn.addEventListener('click',()=>{document.querySelector('.nav button[data-view="audits"]').click();openAudit(r.id)});
  td.appendChild(btn);tr.appendChild(td);
  [rank(r.topographic_rank), ...(r.scale_ranks?scaleKeys.map(k=>rank(r.scale_ranks[k])):['—','—','—']),
   r.method_ranks?rank(r.method_ranks.robust_log_l2):'—',
   r.method_ranks?rank(r.method_ranks.empirical_percentile_l1):'—',
   r.weight_top25_of_60!==undefined?r.weight_top25_of_60+'/60':'—'].forEach(x=>add(tr,'td',x));
  completeTable.appendChild(tr);
 }
}
for(const r of DATA.benchmark_cases){const tr=make('tr');[r.site_name,r.mars_profile||'Referencia de proceso',rank(r.topographic_rank),r.evaluation_status].forEach(x=>add(tr,'td',x));el('benchmark-rows').appendChild(tr)}
place('benchmark-result',`${DATA.benchmark_summary.direct_sites_missing_from_ranked_population} de ${DATA.benchmark_summary.direct_target_process_analogues} referencias directas quedaron fuera de la población clasificada. Por ello la prueba externa no produce una tasa de acierto.`);
for(const [k,v] of Object.entries(DATA.input_hashes)){const d=make('div',undefined,'source-panel');add(d,'b',k);add(d,'div',v,'sourcehash');el('sources-list').appendChild(d)}
for(const [k,v] of Object.entries(atlas.sources)){const d=make('div',undefined,'source-panel');add(d,'b','Atlas: '+k);add(d,'div',`${v.path} · ${v.sha256}`,'sourcehash');el('sources-list').appendChild(d)}
for(const lim of DATA.limitations)add(el('limitations-list'),'li',lim);
for(const file of (DATA.climate_v203.source_files||[])){
 const d=make('div',undefined,'source-panel');add(d,'b','Clima / NASA POWER');add(d,'div',`${file.file} · ${file.sha256}`,'sourcehash');el('sources-list').appendChild(d);
}
const lunarSource=DATA.lunar_atlas.source;
const lsrc=make('div',undefined,'source-panel');add(lsrc,'b','Luna / NASA LRO LOLA LDEM_4');
add(lsrc,'div',`${lunarSource.url} · ${lunarSource.sha256||'fuente pendiente'}`,'sourcehash');el('sources-list').appendChild(lsrc);
const ne=make('div',undefined,'source-panel');add(ne,'b','Mapamundi / Natural Earth 1:110m');add(ne,'div',DATA.world_land.source,'small');el('sources-list').appendChild(ne);
// V2.0.2: six real Mars MOLA maps; NO terrestrial OpenStreetMap links here.
const marsAtlas=DATA.mars_topographic_atlas;
const marsById=new Map(DATA.profiles.map(p=>[p.id,p]));
const martianUnitDescriptions={
 AHtu:'Transición indiferenciada amazónica-hespérica',lAv:'Unidad volcánica amazónica tardía',
 lHt:'Unidad de transición hespérica tardía',AHi:'Unidad de impacto amazónica-hespérica',
 HNt:'Unidad de transición hespérica-noáquica',Htu:'Transición hespérica indiferenciada',
 Ave:'Edificio volcánico amazónico',HNhu:'Tierras altas hespéricas-noáquicas indiferenciadas',
 eHv:'Unidad volcánica del Hespérico temprano',mNh:'Tierras altas del Noáquico medio',
 mNhm:'Macizos del Noáquico medio'};
const marsCoordinate=(lat,lon)=>`${Math.abs(lat).toFixed(2)}° ${lat<0?'S':'N'} · ${(((lon%360)+360)%360).toFixed(2)}° E (Marte)`;
let marsSelected='elysium_planitia',marsZoom=1;
const marsCanvas=el('mars-topo-canvas'),mctx=marsCanvas.getContext('2d');
function renderMarsList(){const list=el('mars-profile-list');list.replaceChildren();for(const p of DATA.profiles){
 let d=marsAtlas.profiles[p.id],b=make('button',undefined,'mars-choice');b.type='button';b.setAttribute('aria-current',p.id===marsSelected?'true':'false');
 add(b,'strong',p.name);add(b,'span',marsCoordinate(d.center_lat,d.center_lon_east));
 b.addEventListener('click',()=>openMarsProfile(p.id));list.appendChild(b);
}}
function openMarsProfile(id){if(!marsById.has(id))return; marsSelected=id;marsZoom=1;renderMarsList();
 const p=marsById.get(id),d=marsAtlas.profiles[id],m=marsAtlas.maps[id],f=d.features||{};
 place('mars-selected-name',p.name);place('mars-selected-coordinates',marsCoordinate(d.center_lat,d.center_lon_east));
 place('mars-elevation',m?.status==='available'?`${number(m.elevation_min_m,0)} a ${number(m.elevation_max_m,0)} m`:'Sin MOLA');
 place('mars-slope',f.slope_median_deg!==undefined?`${number(f.slope_median_deg,3)}°`:'—');
 place('mars-relief',f.relief_p90_p10_m!==undefined?`${number(f.relief_p90_p10_m,0)} m`:'—');
 const units=Object.entries(p.units).sort((a,b)=>b[1]-a[1]);
 place('mars-research-summary',`En nueve puntos de la cartografía geológica SIM 3292, las unidades registradas fueron: ${units.map(([code,n])=>`${code} (${n}; ${martianUnitDescriptions[code]||'unidad descrita en USGS'})`).join('; ')}. ${d.scope_note}`);
 place('mars-map-caption',m?.caption||m?.reason||'MOLA no encontrado.');
 place('mars-additional-metrics',f.slope_p90_deg!==undefined?`Pendiente P90: ${number(f.slope_p90_deg,3)}° · Rugosidad mediana: ${number(f.roughness_std3_median_m,0)} m · Rugosidad P90: ${number(f.roughness_std3_p90_m,0)} m`:'Métricas adicionales: requiere el perfil MOLA V1.2 guardado.');
 el('mars-map-legend').textContent=m?.status==='available'?`${number(m.elevation_min_m,0)} a ${number(m.elevation_max_m,0)} m · altitud MOLA`:'Sin datos';
 requestAnimationFrame(drawMarsTopo);
}
function drawMarsTopo(){const m=marsAtlas.maps[marsSelected];const miss=el('mars-map-missing'),wrap=el('mars-topo-canvas');
 if(!m||m.status!=='available'){wrap.hidden=true;miss.hidden=false;miss.textContent='No hay mapa MOLA para este perfil: '+(m?.reason||'datos ausentes');return}
 wrap.hidden=false;miss.hidden=true;const rect=wrap.getBoundingClientRect();if(rect.width<10)return;
 const pr=Math.min(2,window.devicePixelRatio||1),w=Math.round(rect.width*pr),h=Math.round(rect.height*pr);
 if(w!==wrap.width||h!==wrap.height){wrap.width=w;wrap.height=h}
 mctx.clearRect(0,0,w,h);mctx.save();mctx.translate(w/2,h/2);mctx.scale(marsZoom,marsZoom);mctx.translate(-w/2,-h/2);
 mctx.imageSmoothingEnabled=false;mctx.drawImage(raster(m,'mars_'+marsSelected),0,0,w,h);
 // Context square ~640 km. The inner outline corresponds to the 240km analysis window.
 const d=marsAtlas.profiles[marsSelected],b=m.bounds,R=3396,
 half=(120/R)*(180/Math.PI),halfLon=half/Math.max(.15,Math.cos(d.center_lat*Math.PI/180));
 const gx=lon=>topox(lon,b,w),gy=lat=>topoy(lat,b,h);
 mctx.lineWidth=2/marsZoom;mctx.strokeStyle='rgba(255,255,255,.96)';mctx.setLineDash([7/marsZoom,4/marsZoom]);
 mctx.strokeRect(gx(d.center_lon_east-halfLon),gy(d.center_lat+half),gx(d.center_lon_east+halfLon)-gx(d.center_lon_east-halfLon),gy(d.center_lat-half)-gy(d.center_lat+half));mctx.setLineDash([]);
 const x=gx(d.center_lon_east),y=gy(d.center_lat);mctx.beginPath();mctx.arc(x,y,6/marsZoom,0,Math.PI*2);mctx.fillStyle='#ff734d';mctx.fill();mctx.strokeStyle='white';mctx.stroke();mctx.restore();
 place('mars-map-overlay',`MOLA · ${number(marsZoom,1)}× · recuadro punteado: análisis de 240 km`);
}
marsCanvas.addEventListener('wheel',e=>{if(!marsAtlas.maps[marsSelected]||marsAtlas.maps[marsSelected].status!=='available')return;e.preventDefault();marsZoom=Math.max(1,Math.min(7,marsZoom*(e.deltaY<0?1.2:1/1.2)));drawMarsTopo()},{passive:false});
el('mars-reset').addEventListener('click',()=>{marsZoom=1;drawMarsTopo()});
marsCanvas.addEventListener('pointermove',e=>{const m=marsAtlas.maps[marsSelected];if(!m||m.status!=='available')return;
 const rc=marsCanvas.getBoundingClientRect(),px=(e.clientX-rc.left)*marsCanvas.width/rc.width,py=(e.clientY-rc.top)*marsCanvas.height/rc.height,
 wx=(px-marsCanvas.width/2)/marsZoom+marsCanvas.width/2,wy=(py-marsCanvas.height/2)/marsZoom+marsCanvas.height/2;
 const col=Math.floor(wx/marsCanvas.width*m.shape[1]),row=Math.floor(wy/marsCanvas.height*m.shape[0]);
 const tip=el('mars-tip');if(col<0||col>=m.shape[1]||row<0||row>=m.shape[0]){tip.hidden=true;return}
 const val=m.elevation[m.shape[0]-1-row][col],lat=m.bounds[3]-(wy/marsCanvas.height)*(m.bounds[3]-m.bounds[1]),lon=m.bounds[0]+(wx/marsCanvas.width)*(m.bounds[2]-m.bounds[0]);
 tip.textContent=`${marsCoordinate(lat,Number(lon.toFixed(2)))}\nElevación MOLA: ${val===null?'sin datos':number(val,0)+' m'}`;tip.hidden=false;
});
marsCanvas.addEventListener('pointerleave',()=>{el('mars-tip').hidden=true});
window.addEventListener('resize',()=>{if(!el('view-mars').hidden)drawMarsTopo()});
const prevMarsNav=document.querySelector('.nav button[data-view="mars"]');prevMarsNav.addEventListener('click',()=>requestAnimationFrame(drawMarsTopo));
renderMarsList();openMarsProfile(marsSelected);
for(const [k,v] of Object.entries(marsAtlas.sources)){const d=make('div',undefined,'source-panel');add(d,'b','Marte / MOLA: '+k);add(d,'div',`${v.path} · ${v.sha256}`,'sourcehash');el('sources-list').appendChild(d)}

renderCandidateList();showDetail();

// V2.0.4 — independent lunar educational atlas, offline after official LOLA download.
const moonAtlas=DATA.lunar_atlas;
let moonSelected=moonAtlas.regions[0].id,moonZoom=1;
const moonCanvas=el('moon-canvas'),moonCtx=moonCanvas.getContext('2d');
const lunarCoordinate=(lat,lon)=>`${Math.abs(lat).toFixed(2)}° ${lat<0?'S':'N'} · ${(((lon%360)+360)%360).toFixed(2)}° E (Luna)`;
function renderMoonChoices(){const list=el('moon-list');list.replaceChildren();for(const r of moonAtlas.regions){
 const b=make('button',undefined,'moon-choice');b.setAttribute('aria-current',r.id===moonSelected?'true':'false');
 add(b,'strong',r.name);add(b,'span',lunarCoordinate(r.lat,r.lon_east));b.addEventListener('click',()=>openMoon(r.id));list.appendChild(b);
}}
function openMoon(id){const r=moonAtlas.regions.find(x=>x.id===id);if(!r)return;moonSelected=id;moonZoom=1;renderMoonChoices();
 place('moon-title',r.name);place('moon-coordinates',lunarCoordinate(r.lat,r.lon_east));place('moon-process',r.process);
 const m=moonAtlas.maps[id];place('moon-data-caption',m?.caption||m?.reason||'Falta fuente LOLA LDEM_4');
 place('moon-height-range',m?.status==='available'?`Elevaciones en el mapa: ${number(m.elevation_min_m,0)} a ${number(m.elevation_max_m,0)} m sobre la esfera lunar de 1737,4 km.`:'Altimetría lunar no cargada todavía');
 requestAnimationFrame(drawMoon);
}
function drawMoon(){const m=moonAtlas.maps[moonSelected],miss=el('moon-missing');
 if(!m||m.status!=='available'){moonCanvas.hidden=true;miss.hidden=false;miss.textContent='No hay topografía lunar: '+(m?.reason||'descargá NASA LOLA LDEM_4.IMG');return;}
 moonCanvas.hidden=false;miss.hidden=true;const box=moonCanvas.getBoundingClientRect();if(box.width<10)return;
 const dpr=Math.min(2,window.devicePixelRatio||1),w=Math.round(box.width*dpr),h=Math.round(box.height*dpr);
 if(moonCanvas.width!==w||moonCanvas.height!==h){moonCanvas.width=w;moonCanvas.height=h}
 moonCtx.setTransform(1,0,0,1,0,0);moonCtx.clearRect(0,0,w,h);moonCtx.save();moonCtx.translate(w/2,h/2);moonCtx.scale(moonZoom,moonZoom);moonCtx.translate(-w/2,-h/2);
 moonCtx.drawImage(raster(m,'lunar_'+moonSelected),0,0,w,h);
 const r=moonAtlas.regions.find(x=>x.id===moonSelected),b=m.bounds;
 const x=topox(r.lon_east,b,w),y=topoy(r.lat,b,h);
 moonCtx.beginPath();moonCtx.arc(x,y,7/moonZoom,0,Math.PI*2);moonCtx.fillStyle='#e76d4f';moonCtx.fill();moonCtx.lineWidth=2/moonZoom;moonCtx.strokeStyle='#fff';moonCtx.stroke();moonCtx.restore();
}
moonCanvas.addEventListener('wheel',e=>{e.preventDefault();moonZoom=Math.max(1,Math.min(8,moonZoom*(e.deltaY<0?1.2:1/1.2)));drawMoon()},{passive:false});
el('moon-reset').addEventListener('click',()=>{moonZoom=1;drawMoon()});
moonCanvas.addEventListener('pointermove',e=>{const m=moonAtlas.maps[moonSelected];if(!m||m.status!=='available')return;
 const b=moonCanvas.getBoundingClientRect(),px=(e.clientX-b.left)*moonCanvas.width/b.width,py=(e.clientY-b.top)*moonCanvas.height/b.height;
 const x=(px-moonCanvas.width/2)/moonZoom+moonCanvas.width/2,y=(py-moonCanvas.height/2)/moonZoom+moonCanvas.height/2;
 const col=Math.floor(x/moonCanvas.width*m.shape[1]),row=Math.floor(y/moonCanvas.height*m.shape[0]),tip=el('moon-tip');
 if(col<0||row<0||col>=m.shape[1]||row>=m.shape[0]){tip.hidden=true;return}
 const elev=m.elevation[m.shape[0]-1-row][col],lat=m.bounds[3]-(y/moonCanvas.height)*(m.bounds[3]-m.bounds[1]),lon=m.bounds[0]+x/moonCanvas.width*(m.bounds[2]-m.bounds[0]);
 tip.textContent=`${lunarCoordinate(lat,lon)}\nAltitud LOLA: ${elev===null?'sin datos':number(elev,0)+' m'}`;tip.hidden=false;
});moonCanvas.addEventListener('pointerleave',()=>{el('moon-tip').hidden=true});
document.querySelector('.nav button[data-view="moon"]').addEventListener('click',()=>requestAnimationFrame(drawMoon));
window.addEventListener('resize',()=>{if(!el('view-moon').hidden)drawMoon()});openMoon(moonSelected);
// V2.0.5 — one continuous, pannable, zoomable global ETOPO canvas.
// The 240 km screening footprint is an optional overlay, never a map boundary.
const worldCanvas=el('world-canvas'), worldCtx=worldCanvas.getContext('2d');
const worldData=DATA.continuous_terrain_v205||{status:'unavailable'};
const worldState={lon:0,lat:0,z:1,active:'r026_c146',showWindow:true,showCells:false,showLocal:true,drag:null};
let worldMarkers=[],worldTexture=null,worldHeights=null,worldHeightCtx=null,worldDown=null;
const normalizedLon=x=>((x+180)%360+360)%360-180;
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const worldW=()=>worldCanvas.width*worldState.z;
const worldH=()=>worldW()/2;
function worldBounds(){return {w:worldCanvas.width,h:worldCanvas.height,wmap:worldW(),hmap:worldH()}}
function worldClamp(){const {h,hmap}=worldBounds();worldState.lat=clamp(worldState.lat,-Math.max(0,90-90*h/hmap),Math.max(0,90-90*h/hmap));worldState.lon=normalizedLon(worldState.lon)}
function worldXY(lon,lat){const b=worldBounds();const dx=normalizedLon(lon-worldState.lon);return [b.w/2+dx/360*b.wmap,b.h/2-(lat-worldState.lat)/180*b.hmap]}
function worldLL(px,py){const b=worldBounds();return {lon:normalizedLon(worldState.lon+(px-b.w/2)/b.wmap*360),lat:clamp(worldState.lat-(py-b.h/2)/b.hmap*180,-90,90)}}
function canvasEventXY(e){const r=worldCanvas.getBoundingClientRect();return [(e.clientX-r.left)*worldCanvas.width/r.width,(e.clientY-r.top)*worldCanvas.height/r.height]}
function resizeWorld(){const r=worldCanvas.getBoundingClientRect();if(r.width<10)return false;
 const ratio=Math.min(2,window.devicePixelRatio||1),w=Math.round(r.width*ratio),h=Math.round(r.height*ratio);
 if(worldCanvas.width!==w||worldCanvas.height!==h){worldCanvas.width=w;worldCanvas.height=h;worldClamp()};return true}
function sampleWorld(lon,lat){if(!worldHeightCtx||!worldHeights)return null;
 const west=worldData.raster_lon_west_edge_deg??-180,north=worldData.raster_lat_north_edge_deg??90;
 const unitX=((lon-west)%360+360)%360;const x=clamp(Math.floor(unitX/360*worldHeights.width),0,worldHeights.width-1);
 const y=Math.floor((north-lat)/180*worldHeights.height);if(y<0||y>=worldHeights.height)return null;
 const v=worldHeightCtx.getImageData(x,y,1,1).data,n=v[0]*256+v[1];return n===65535?null:n-32768}
function drawWorldCoastline(){worldCtx.fillStyle='#e5e7d6';worldCtx.strokeStyle='#a2a995';worldCtx.lineWidth=Math.min(1.5,window.devicePixelRatio||1);
 // Fallback is explicitly non-topographic; never manufacture relief when ETOPO is absent.
 for(const ring of DATA.world_land.rings){const segments=[];let segment=[],last=null;
  for(const [lon,lat] of ring){const p=worldXY(lon,lat);
   if(last&&Math.abs(p[0]-last[0])>worldW()/2){if(segment.length>=3)segments.push(segment);segment=[]}
   segment.push(p);last=p
  }if(segment.length>=3)segments.push(segment);
  for(const seg of segments){worldCtx.beginPath();seg.forEach((p,i)=>i?worldCtx.lineTo(...p):worldCtx.moveTo(...p));worldCtx.closePath();worldCtx.fill();worldCtx.stroke()}
 }}
function drawWorldTerrain(){const b=worldBounds();worldCtx.fillStyle='#1b415a';worldCtx.fillRect(0,0,b.w,b.h);
 if(worldTexture){const west=worldData.raster_lon_west_edge_deg??-180,north=worldData.raster_lat_north_edge_deg??90;
 const left=b.w/2-(worldState.lon-west)/360*b.wmap,top=b.h/2-(north-worldState.lat)/180*b.hmap;
   const first=Math.floor(-left/b.wmap)-1,last=Math.ceil((b.w-left)/b.wmap)+1;
   worldCtx.imageSmoothingEnabled=worldState.z<=16;
   for(let k=first;k<=last;k++)worldCtx.drawImage(worldTexture,left+k*b.wmap,top,b.wmap,b.hmap);
 }else{drawWorldCoastline(); if(worldData.status!=='available'){
    worldCtx.fillStyle='#f1f5ef';worldCtx.fillRect(10,b.h-42,Math.min(b.w-20,580),30);
    worldCtx.fillStyle='#4d6970';worldCtx.font='12px Segoe UI';worldCtx.fillText('Sin ETOPO: contornos cartográficos, no topografía',22,b.h-23);
 }}
}
function drawWorldGrid(){if(!el('world-grid-check').checked)return;
 const z=worldState.z,step=z>30?2:z>8?10:30,b=worldBounds();worldCtx.save();worldCtx.strokeStyle='#ffffff60';worldCtx.lineWidth=1;
 for(let lat=-90+step;lat<90;lat+=step){const p=worldXY(worldState.lon,lat);if(p[1]<0||p[1]>b.h)continue;worldCtx.beginPath();worldCtx.moveTo(0,p[1]);worldCtx.lineTo(b.w,p[1]);worldCtx.stroke()}
 for(let lon=-180;lon<180;lon+=step){const p=worldXY(lon,worldState.lat);if(p[0]<0||p[0]>b.w)continue;worldCtx.beginPath();worldCtx.moveTo(p[0],0);worldCtx.lineTo(p[0],b.h);worldCtx.stroke()}worldCtx.restore()}
function drawWorldFootprints(){const b=worldBounds();worldCtx.save();
 if(worldState.showCells){worldCtx.lineWidth=1.4;worldCtx.strokeStyle='#faf4dc9c';worldCtx.setLineDash([5,4]);
  for(const c of atlas.entries){const tl=worldXY(c.center_lon-1,c.center_lat+1),br=worldXY(c.center_lon+1,c.center_lat-1);
   if(br[0]<tl[0]||br[0]<0||tl[0]>b.w)continue;worldCtx.strokeRect(tl[0],tl[1],br[0]-tl[0],br[1]-tl[1]);}
  worldCtx.setLineDash([])}
 if(worldState.showWindow){const c=byId.get(worldState.active);if(c){const halfLat=120/111.195,halfLon=halfLat/Math.max(.10,Math.cos(c.center_lat*Math.PI/180));
  const tl=worldXY(c.center_lon-halfLon,c.center_lat+halfLat),br=worldXY(c.center_lon+halfLon,c.center_lat-halfLat);
  if(br[0]>=tl[0]){worldCtx.strokeStyle='#ffe6a9';worldCtx.lineWidth=2.4;worldCtx.setLineDash([10,6]);
  worldCtx.strokeRect(tl[0],tl[1],br[0]-tl[0],br[1]-tl[1]);worldCtx.setLineDash([])}}}
 worldCtx.restore()}
function drawWorldLocal(){if(!worldState.showLocal||worldState.z<17)return;
 const b=worldBounds();const dpr=Math.min(2,window.devicePixelRatio||1);
 for(const site of atlas.local_sites){const m=atlas.maps[site.id];if(m?.status!=='available')continue;
  const tl=worldXY(m.bounds[0],m.bounds[3]),br=worldXY(m.bounds[2],m.bounds[1]);
  if(br[0]<tl[0]||br[0]<0||tl[0]>b.w||br[1]<0||tl[1]>b.h||br[0]-tl[0]<8)continue;
  worldCtx.save();worldCtx.imageSmoothingEnabled=true;
  worldCtx.drawImage(raster(m,site.id),tl[0],tl[1],br[0]-tl[0],br[1]-tl[1]);
  worldCtx.strokeStyle='#ffe8a7';worldCtx.lineWidth=2*dpr;worldCtx.strokeRect(tl[0],tl[1],br[0]-tl[0],br[1]-tl[1]);
  worldCtx.fillStyle='#112d39e8';worldCtx.fillRect(tl[0],tl[1]-21,123,20);
  worldCtx.fillStyle='#fff';worldCtx.font=`${11*dpr}px Segoe UI`;worldCtx.fillText(`${site.id.slice(-3).toUpperCase()} · NASADEM`,tl[0]+3,tl[1]-6);
  worldCtx.restore();}
}
function drawWorldMarkers(){worldMarkers=[];const b=worldBounds(),dpr=Math.min(2,window.devicePixelRatio||1);
 for(const c of atlas.entries){const [x,y]=worldXY(c.center_lon,c.center_lat);
  if(x< -25||x>b.w+25||y< -25||y>b.h+25)continue;
  const selected=c.id===worldState.active,r=(selected?8.5:c.is_priority?7:c.volcanic_points?6:5)*dpr;
  worldMarkers.push({x,y,r,id:c.id,c});worldCtx.beginPath();worldCtx.arc(x,y,r,0,Math.PI*2);
  worldCtx.fillStyle=selected?'#f7d17b':c.is_priority?'#13a99d':c.volcanic_points?'#dba04a':'#388daf';worldCtx.fill();
  worldCtx.lineWidth=selected?3*dpr:1.7*dpr;worldCtx.strokeStyle=selected?'#203c4e':'#fff';worldCtx.stroke();
  if(selected||(worldState.z>3.5&&c.is_priority)){worldCtx.font=`700 ${11*dpr}px Segoe UI`;
    worldCtx.lineWidth=3.5*dpr;worldCtx.strokeStyle='#142c36';worldCtx.fillStyle='#fff';const txt=c.label.split(' — ')[0];
    worldCtx.strokeText(txt,x+r+5,y-r);worldCtx.fillText(txt,x+r+5,y-r)}
 }
}
function drawWorld(){if(!resizeWorld())return;worldClamp();const b=worldBounds();worldCtx.clearRect(0,0,b.w,b.h);
 drawWorldTerrain();drawWorldGrid();drawWorldLocal();drawWorldFootprints();drawWorldMarkers();
 place('world-zoom',worldState.z.toFixed(worldState.z<10?1:0)+'×');
 place('world-view-area',`${number(360/worldState.z,1)}° de longitud visibles aprox. · centro ${coord(worldState.lat,worldState.lon,2)}`);
}
function nearestWorldMarker(e){const [x,y]=canvasEventXY(e);let best=null,dist=Infinity;
 for(const m of worldMarkers){const d=Math.hypot(m.x-x,m.y-y);if(d<dist){dist=d;best=m}}
 return dist<Math.max(13,Math.min(2,window.devicePixelRatio||1)*13)?best:null}
function worldSetCandidate(id,focus=true){const c=byId.get(id);if(!c)return;worldState.active=id;el('world-select').value=id;
 place('world-active-name',c.label);place('world-active-coords',`${coord(c.center_lat,c.center_lon,2)} · ${c.id} · Elysium #${c.topographic_rank}`);
 if(focus){worldState.lon=c.center_lon;worldState.lat=c.center_lat;worldState.z=12;worldClamp();}
 drawWorld();}
function worldChangeZoom(factor,pivot){const b=worldBounds(),[px,py]=pivot||[b.w/2,b.h/2],before=worldLL(px,py);
 worldState.z=clamp(worldState.z*factor,1,160);
 const after=worldLL(px,py);
 worldState.lon=normalizedLon(worldState.lon+before.lon-after.lon);worldState.lat+=before.lat-after.lat;
 worldClamp();drawWorld()}
const selectWorld=el('world-select');for(const c of atlas.entries){const o=make('option',`${c.label} · #${c.topographic_rank}`);o.value=c.id;selectWorld.appendChild(o)}
selectWorld.addEventListener('change',()=>worldSetCandidate(selectWorld.value,true));
el('world-focus').addEventListener('click',()=>worldSetCandidate(worldState.active,true));
el('world-reset').addEventListener('click',()=>{worldState.lon=0;worldState.lat=0;worldState.z=1;drawWorld()});
el('world-plus').addEventListener('click',()=>worldChangeZoom(1.6));
el('world-minus').addEventListener('click',()=>worldChangeZoom(1/1.6));
el('world-window-check').addEventListener('change',e=>{worldState.showWindow=e.target.checked;drawWorld()});
el('world-cell-check').addEventListener('change',e=>{worldState.showCells=e.target.checked;drawWorld()});
el('world-local-check').addEventListener('change',e=>{worldState.showLocal=e.target.checked;drawWorld()});
el('world-grid-check').addEventListener('change',drawWorld);
el('world-open-detail').addEventListener('click',()=>openCandidate(worldState.active,true));
el('world-open-audit').addEventListener('click',()=>{document.querySelector('.nav button[data-view="audits"]').click();openAudit(worldState.active)});
const globeFromDetail=el('explore-global-candidate');if(globeFromDetail)globeFromDetail.addEventListener('click',()=>{
 document.querySelector('.nav button[data-view="world"]').click();worldSetCandidate(current,true)});
let worldPointer=null,worldMoved=false;
worldCanvas.addEventListener('pointerdown',e=>{if(e.button!==0)return;const [x,y]=canvasEventXY(e);
 worldPointer={id:e.pointerId,x,y,lon:worldState.lon,lat:worldState.lat};worldMoved=false;
 worldCanvas.setPointerCapture(e.pointerId)});
worldCanvas.addEventListener('pointermove',e=>{
 const xy=canvasEventXY(e),hit=nearestWorldMarker(e),ll=worldLL(...xy),value=sampleWorld(ll.lon,ll.lat);
 const tip=el('world-tip');tip.hidden=false;
 tip.textContent=hit?`${hit.c.label}\n${coord(hit.c.center_lat,hit.c.center_lon,1)} · Elysium #${hit.c.topographic_rank}\nClic: centrar candidato`:
  `${coord(ll.lat,ll.lon,3)}\nETOPO: ${value===null?'sin altura terrestre':number(value,0)+' m'}${worldState.z>18?'\nResolución mundial limitada; no hay detalle adicional.':''}`;
 worldCanvas.style.cursor=worldPointer?'grabbing':hit?'pointer':'grab';
 if(worldPointer&&e.pointerId===worldPointer.id){const dx=xy[0]-worldPointer.x,dy=xy[1]-worldPointer.y;
  if(Math.hypot(dx,dy)>3)worldMoved=true;
  worldState.lon=normalizedLon(worldPointer.lon-dx/worldW()*360);
  worldState.lat=worldPointer.lat+dy/worldH()*180;worldClamp();drawWorld()}
});
worldCanvas.addEventListener('pointerup',e=>{if(!worldPointer||e.pointerId!==worldPointer.id)return;
 const moved=worldMoved;worldPointer=null;if(worldCanvas.hasPointerCapture(e.pointerId))worldCanvas.releasePointerCapture(e.pointerId);
 if(!moved){const m=nearestWorldMarker(e);if(m)worldSetCandidate(m.id,true)}});
worldCanvas.addEventListener('pointercancel',()=>worldPointer=null);
worldCanvas.addEventListener('pointerleave',()=>{if(!worldPointer)el('world-tip').hidden=true});
worldCanvas.addEventListener('wheel',e=>{e.preventDefault();worldChangeZoom(e.deltaY<0?1.33:1/1.33,canvasEventXY(e))},{passive:false});
worldCanvas.addEventListener('dblclick',e=>{e.preventDefault();worldChangeZoom(2,canvasEventXY(e))});
worldCanvas.addEventListener('keydown',e=>{if(['+','=','-','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();
 if(['+','='].includes(e.key))worldChangeZoom(1.4);else if(e.key==='-')worldChangeZoom(1/1.4);
 else{worldState.lon=normalizedLon(worldState.lon+(e.key==='ArrowRight'?1:e.key==='ArrowLeft'?-1:0)*35/worldState.z);
 worldState.lat+=(e.key==='ArrowUp'?1:e.key==='ArrowDown'?-1:0)*20/worldState.z;worldClamp();drawWorld()}}});
let terrainFailed=false;
if(worldData.status==='available'){
 const img=new Image();img.onload=()=>{worldTexture=img;drawWorld()};img.onerror=()=>{terrainFailed=true;el('world-source').textContent='Error cargando textura ETOPO';drawWorld()};img.src=worldData.texture_data_uri;
 const encoded=new Image();encoded.onload=()=>{worldHeights=encoded;let sample=document.createElement('canvas');sample.width=encoded.width;sample.height=encoded.height;
 worldHeightCtx=sample.getContext('2d',{willReadFrequently:true});worldHeightCtx.drawImage(encoded,0,0)};encoded.src=worldData.height_data_uri;
 place('world-source',`NOAA ETOPO · ${number(worldData.nominal_resolution_arcmin,1)}′ de arco · ${(worldData.grid_shape||[]).join(' × ')} celdas · sin Internet`);
}else place('world-source','No se encontró la grilla ETOPO histórica; solo se muestran costas y marcadores');
place('world-active-name',byId.get(worldState.active).label);
worldSetCandidate(worldState.active,false);
document.querySelector('.nav button[data-view="world"]').addEventListener('click',()=>requestAnimationFrame(drawWorld));
window.addEventListener('resize',()=>{if(!el('view-world').hidden)requestAnimationFrame(drawWorld)});
// V2.0.4 — all 25 factual audits with a distinct evidence-availability record.
const audits=DATA.candidate_audits;let auditSelected=audits[0]?.id;
function openAudit(id){const a=audits.find(x=>x.id===id);if(!a)return;auditSelected=id;renderAudits();
 place('audit-name',a.label);place('audit-coordinates',`${a.id} · ${coord(a.center_lat,a.center_lon,1)}`);
 const badges=el('audit-badges');badges.replaceChildren();
 for(const txt of [`Puesto ${rank(a.topographic_rank_elysium)}`,`${a.volcanic_observed_points}/${a.sampled_glim_points} GLiM volcánicos`,
  `Clima: ${a.climate_status==='complete'?'completo':a.climate_status==='partial'?'parcial':'pendiente'}`,
  `Multiescala: ${a.individual_multiscale_tested?'evaluada':'pendiente'}`,
  `Top25/pesos: ${a.weight_top25_of_60===null||a.weight_top25_of_60===undefined?'pendiente':a.weight_top25_of_60+'/60'}`])add(badges,'span',txt,'chip');
 const ul=el('audit-findings');ul.replaceChildren();for(const f of a.findings)add(ul,'li',f);
 const tbody=el('audit-profile-rows');tbody.replaceChildren();for(const r of a.six_mars_profiles){const tr=make('tr');
 add(tr,'td',r.profile);add(tr,'td',rank(r.rank));add(tr,'td',r.triage||'Sin diagnóstico');tbody.appendChild(tr)}
 el('audit-open-map').onclick=()=>openCandidate(a.id,true);
}
function renderAudits(){const div=el('audit-list');div.replaceChildren();for(const a of audits){const b=make('button',undefined,'audit-choice');
 b.setAttribute('aria-current',a.id===auditSelected?'true':'false');add(b,'strong',a.label);add(b,'span',`${a.id} · ${rank(a.topographic_rank_elysium)} · clima ${a.climate_status}`);
 b.addEventListener('click',()=>openAudit(a.id));div.appendChild(b);
}}
if(audits.length)openAudit(auditSelected);

"""
    markup = r"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Mars Analog Engine V2.0.6 · Explorador topográfico mundial</title><style>"""+css+r"""</style></head><body>
<header class="header"><div class="inner"><div class="eyebrow">Mars Analog Discovery Engine · V2.0.6 / Topografía adaptativa</div>
<h1>De Marte a la Tierra.<br>Candidatos concretos, datos visibles.</h1>
<p>Exploramos 6 paisajes marcianos y comparamos el relieve terrestre, la cartografía geológica y la robustez de los resultados. Seleccioná una región para examinar su ubicación y su topografía real.</p>
<div class="tagline"><span>Datos NASA / NOAA / USGS</span><span>Mapas topográficos sin Internet</span><span>Resultados reproducibles</span></div></div></header>
<main class="page"><div class="kpis"><div class="kpi"><strong id="kpi-profiles">6</strong><span>Perfiles de Marte</span></div><div class="kpi"><strong id="kpi-anchor">25</strong><span>Regiones terrestres con GLiM</span></div><div class="kpi"><strong id="kpi-pairs">150</strong><span>Comparaciones Tierra–Marte</span></div><div class="kpi"><strong id="kpi-priority">3</strong><span>Candidatos volcánicos destacados para Elysium</span></div></div>
<nav class="nav" aria-label="Secciones"><button data-view="candidates" aria-selected="true">Explorar candidatos</button><button data-view="comparison" aria-selected="false">Comparación y resultados</button><button data-view="mars" aria-selected="false">Regiones de Marte</button><button data-view="world" aria-selected="false">Mapa mundial</button><button data-view="audits" aria-selected="false">Auditorías individuales</button><button data-view="moon" aria-selected="false">Regiones de la Luna</button><button data-view="reference" aria-selected="false">Fuentes y metodología</button></nav>
<section class="view" id="view-candidates"><div class="callout"><span class="kicker">Resultado principal</span><p><b>Argentina destaca para Elysium Planitia:</b> puesto 6 en el ranking base, posiciones 2 / 6 / 16 al cambiar la escala, y observaciones de rocas volcánicas básicas. Dos sectores locales, <b>p04 y p08</b>, cuentan además con análisis NASADEM.</p></div>
<p class="small" id="climate-coverage"></p><div class="explore"><aside class="panel side"><div class="side-top"><h3>Regiones candidatas · país y coordenadas</h3><p class="small">Elegí cualquiera para abrir su ficha y mapa.</p><input type="search" id="search-candidates" placeholder="Buscar país, coordenadas o código" aria-label="Buscar candidatos"><div class="filterline"><button data-filter="all" aria-pressed="true">Todos</button><button data-filter="top10" aria-pressed="false">Top 10</button><button data-filter="volcanic" aria-pressed="false">Señal volcánica</button></div><p class="small" id="candidate-count"></p></div><div class="list" id="candidate-list"></div></aside>
<div class="panel" id="details-top"><div class="details-top"><div><div class="kicker">Ficha interactiva de terreno</div><h2 class="details-title" id="selected-name">Argentina</h2><div class="label-id" id="selected-code"></div><p class="muted" id="selected-coords"></p></div><span class="chip">Mapa topográfico</span></div>
<div class="detail-metrics"><div class="detail-metric"><strong id="selected-rank">#6</strong><span>Puesto para Elysium</span></div><div class="detail-metric"><strong id="selected-volcanic">2/9</strong><span>Observaciones volcánicas GLiM</span></div><div class="detail-metric"><strong id="selected-scale">2 / 6 / 16</strong><span>Puestos a 15 / 30 / 40 km</span></div></div>
<p class="lead" id="selected-explainer"></p>
<div class="research-panels"><div class="research-panel"><strong>Relieve observado</strong><p id="earth-terrain-summary"></p></div><div class="research-panel"><strong>Geología observada</strong><p id="earth-geology-summary"></p></div><div class="research-panel"><strong>Contexto climático</strong><p id="earth-climate-summary"></p></div></div>
<div id="map-tabs" class="map-tabs" role="group" aria-label="Elegir mapa topográfico"></div>
<div class="map-head"><strong id="map-source-label">Topografía ETOPO</strong><div class="map-controls"><button id="contours-toggle" aria-pressed="true" title="Mostrar u ocultar curvas de nivel">Curvas de nivel</button><button id="footprint-toggle" aria-pressed="false" title="Mostrar u ocultar la celda de investigación (no es el límite del mapa)">Celda de estudio</button><button id="mask-toggle" aria-pressed="true" title="Mostrar máscara volcánica GLiM">GLiM</button><button id="zoom-out" title="Alejar">−</button><button id="zoom-in" title="Acercar">+</button><button id="zoom-reset" title="Reiniciar mapa">Restablecer</button></div></div>
<div class="map-box"><canvas id="topo-canvas" role="img" aria-label="Visor topográfico terrestre sin bordes: ETOPO mundial, zoom multinivel, NASADEM local y elevación al señalar"></canvas><div class="map-missing" id="map-missing" hidden></div><div class="map-overlay" id="map-overlay"></div><div class="map-zoom" id="map-zoom">1.0×</div><div class="map-popup" id="map-popup" hidden></div></div>
<div class="legend"><span id="map-level"></span><div class="legend-bar" aria-label="Gradiente de elevación relativa"></div><span>Elevación</span></div><p class="source-note" id="map-citation"></p><div class="map-bottom"><span class="small">Exploración libre: arrastrá para recorrer regiones vecinas · rueda para acercar o alejar · LOD variable con el zoom · NASADEM se integra donde hay datos.</span><a id="osm-link" href="https://www.openstreetmap.org" target="_blank" rel="noopener noreferrer">Abrir ubicación en OpenStreetMap ↗</a><button id="explore-global-candidate" class="world-action">Explorar en mapa continuo ↗</button></div>
<div class="site-notes" id="site-comparison"><button type="button" class="site-note" data-site-map="r026_c146_p04"><strong>Argentina · p04 · Ver mapa topográfico ↗</strong><span>GLiM: 1.675,65 km² en el recorte; pendiente mediana 1,858°. Abrir NASADEM p04.</span></button><button type="button" class="site-note" data-site-map="r026_c146_p08"><strong>Argentina · p08 · Ver mapa topográfico ↗</strong><span>GLiM: 798,53 km² en el recorte; pendiente mediana 1,491°. Abrir NASADEM p08.</span></button></div><div id="site-active-details" class="site-note" hidden><strong id="site-active-title"></strong><span id="site-active-coord"></span><p id="site-active-metrics"></p></div>
<div class="evidence"><h3 id="selected-kind"></h3><div id="rock-types"></div><p class="small">Las coordenadas regionales representan <b>el centro de una celda de 2°</b>, no un afloramiento exacto. Los puntos volcánicos son observaciones cartográficas, no porcentajes de área.</p></div></div></div></section>
<section class="view" id="view-comparison" hidden><div class="panel"><div class="kicker">Hallazgos del experimento Elysium</div><h2>Tres candidatos, mismas pruebas</h2><p class="lead">Argentina es el candidato más consistente del grupo bajo el protocolo actual. El sector piroclástico alcanza el primer puesto a 40 km; el orden de preferencia depende de la escala.</p><div class="tiles" id="comparison-cards"></div></div><div class="panel"><h3>Resultados comparativos</h3><div class="scroll"><table><thead><tr><th>Candidato</th><th>Base</th><th>15 km</th><th>30 km</th><th>40 km</th><th>Señal volcánica GLiM</th></tr></thead><tbody id="comparison-rows"></tbody></table></div><p class="small">Las posiciones reflejan el modelo topográfico; no representan una probabilidad de similitud geológica.</p></div>
<div class="panel" id="all25-panel"><h3>Pruebas de sensibilidad para las 25 regiones</h3><p class="lead" id="comparison-all25-caption">Resultados completos por región, con las mismas funciones, escalas y perturbaciones.</p><div class="scroll"><table><thead><tr><th>Región / país</th><th>Original</th><th>15 km</th><th>30 km</th><th>40 km</th><th>Log-L2</th><th>Percentil L1</th><th>Top 25 / 60 pesos</th></tr></thead><tbody id="comparison-all25-rows"></tbody></table></div><p class="small">Puestos menores indican mejor coincidencia topográfica dentro de cada población evaluada. La permanencia ante cambios de peso no es una probabilidad de analogía.</p></div></section>
<section class="view" id="view-mars" hidden><div class="panel"><div class="kicker">Atlas de Marte · altimetría orbital MOLA / NASA</div><h2>Topografía de seis regiones marcianas</h2><p class="lead">Seleccioná un perfil para mostrar su mapa de elevación real, posición planetocéntrica, métricas del relieve y unidades geológicas USGS. Los mapas están alejados para mostrar ~1600 km de contexto y el recuadro punteado indica la ventana analizada de 240 km.</p>
<div class="mars-explore"><div class="mars-list" id="mars-profile-list"></div><div><div class="section-head"><div><h2 id="mars-selected-name">Elysium Planitia</h2><div class="small" id="mars-selected-coordinates"></div></div><button id="mars-reset" class="table-button">Restablecer zoom</button></div>
<div class="mars-evidence"><div><strong id="mars-elevation">—</strong><span>Intervalo del mapa MOLA</span></div><div><strong id="mars-slope">—</strong><span>Pendiente mediana (240 km)</span></div><div><strong id="mars-relief">—</strong><span>Relieve P90–P10 (240 km)</span></div></div>
<div class="mars-map-wrap"><canvas id="mars-topo-canvas" role="img" aria-label="Altimetría real MOLA de Marte, selección interactiva de seis regiones"></canvas><div class="mars-map-missing" id="mars-map-missing" hidden></div><div class="mars-map-overlay" id="mars-map-overlay">Topografía MOLA</div><div class="mars-map-tip" id="mars-tip" hidden></div></div>
<div class="legend"><span id="mars-map-legend"></span><div class="legend-bar"></div><span>Altitud</span></div><p class="small" id="mars-map-caption"></p><p class="small" id="mars-additional-metrics"></p><div class="research-panel" style="margin-top:12px"><strong>Lectura geológica y área de estudio</strong><p id="mars-research-summary"></p></div>
</div></div></div></section>
<section class="view" id="view-world" hidden><div class="panel world-panel"><div class="kicker">Explorador topográfico continuo · NOAA ETOPO</div><h2>Un mundo, 25 candidatos: navegá sin límites de recorte</h2>
<p class="lead">Arrastrá para explorar montañas y regiones vecinas; usá la rueda o los controles para acercarte. Los puntos indican las 25 celdas GLiM estudiadas. El recuadro de 240 km es una <b>capa opcional</b>, no el límite del mapa. Relieve real de NOAA ETOPO, sin conexión a Internet.</p>
<div class="world-tools"><div class="world-picker"><label for="world-select">Viajar a un candidato</label><select id="world-select" aria-label="Seleccionar candidato en el mapa mundial"></select></div><button id="world-focus" class="world-action">Centrar candidato</button><div class="world-zoom-controls"><button id="world-minus" title="Alejar" aria-label="Alejar">−</button><button id="world-plus" title="Acercar" aria-label="Acercar">+</button><button id="world-reset">Vista mundial</button><span id="world-zoom" class="world-level">1×</span></div></div>
<div class="world-layers"><label><input type="checkbox" id="world-window-check" checked> Ventana de análisis de 240 km</label><label><input type="checkbox" id="world-cell-check"> Celdas GLiM de 2°</label><label><input type="checkbox" id="world-local-check" checked> NASADEM p04/p08 al acercar</label><label><input type="checkbox" id="world-grid-check"> Coordenadas</label></div>
<div class="world-map-wrap" id="continuous-world-wrap"><canvas id="world-canvas" tabindex="0" role="img" aria-label="Explorador topográfico mundial continuo con elevaciones ETOPO, desplazamiento y zoom, y 25 candidatos interactivos"></canvas><div class="world-hint">Arrastrá para mover · rueda para zoom · clic en un marcador para centrar</div><div class="world-tip" id="world-tip" hidden></div><div class="world-depth-indicator">ETOPO global · tierra y relieve</div></div>
<div class="world-map-foot"><span id="world-source">Preparando topografía mundial…</span><span id="world-view-area"></span></div>
<div class="world-active"><div><span class="kicker">Candidato seleccionado</span><h3 id="world-active-name">Argentina</h3><p id="world-active-coords" class="small"></p></div><div class="world-active-actions"><button id="world-open-detail" class="world-action">Ver ficha y mapas locales</button><button id="world-open-audit" class="world-action secondary">Abrir auditoría</button></div></div>
<div class="world-legend"><span><b style="background:#f7d17b"></b> Seleccionado</span><span><b style="background:#13a99d"></b> Volcánicos prioritarios</span><span><b style="background:#dba04a"></b> Otras señales volcánicas</span><span><b style="background:#388daf"></b> Otros candidatos</span></div>
<p class="small">Resolución real mundial: <b>10 minutos de arco (~18 km en latitud)</b> con los datos históricos. Zoom libre no aumenta resolución; los sectores p04 y p08 muestran NASADEM, solo en sus superficies disponibles. No existe cartografía continua NASADEM para el resto del planeta en este paquete. Las celdas de 2° no representan la superficie exacta de cada afloramiento.</p></div></section>
<section class="view" id="view-audits" hidden><div class="panel"><div class="kicker">Investigación documentada · 25 casos</div><h2>Auditorías individuales de las regiones candidatas</h2><p class="lead">Cada ficha reúne el puesto topográfico, litologías GLiM, mapa regional, contexto NASA POWER disponible y relación con seis perfiles de Marte. Las 25 regiones cuentan con las mismas pruebas de sensibilidad de escalas, métodos, pesos y observaciones GLiM cuando se proporciona el reporte V2.0.4.</p>
<div class="audit-layout"><div class="audit-list" id="audit-list"></div><div class="audit-detail"><div class="kicker">Informe individual</div><h2 id="audit-name">Candidato</h2><p class="small" id="audit-coordinates"></p><div class="audit-badges" id="audit-badges"></div><ul id="audit-findings"></ul><h3>Comparación con perfiles marcianos</h3><div class="scroll"><table><thead><tr><th>Perfil</th><th>Puesto</th><th>Diagnóstico</th></tr></thead><tbody id="audit-profile-rows"></tbody></table></div><p class="small">La auditoría resume evidencia previamente obtenida y disponibilidad. No reemplaza un análisis geológico in situ.</p><button class="table-button" id="audit-open-map">Abrir ficha y mapa topográfico</button></div></div></div></section>
<section class="view" id="view-moon" hidden><div class="panel"><div class="kicker">Atlas de la Luna · NASA LRO / LOLA</div><h2>Seis regiones lunares con topografía orbital</h2><p class="lead">Atlas independiente para comparar visualmente cuencas, mares volcánicos y cráteres de impacto. Elevaciones LOLA LDEM_4, 4 píxeles por grado (~7,6 km por píxel cerca del ecuador); se indica claramente cuando la fuente aún debe descargarse.</p>
<div class="moon-layout"><div class="moon-list" id="moon-list"></div><div><div class="section-head"><div><h2 id="moon-title">Mare Imbrium</h2><p class="small" id="moon-coordinates"></p></div><button class="table-button" id="moon-reset">Restablecer zoom</button></div><p id="moon-process"></p><div class="moon-map-wrap"><canvas id="moon-canvas" role="img" aria-label="Topografía real de regiones lunares a partir de NASA LOLA"></canvas><div class="moon-map-missing" id="moon-missing" hidden></div><div class="moon-map-tip" id="moon-tip" hidden></div></div><p class="small" id="moon-data-caption"></p><p class="small" id="moon-height-range"></p></div></div></div></section>
<section class="view" id="view-reference" hidden><div class="panel"><h2>Fuentes y alcance de la investigación</h2><p class="lead">Este panel prioriza resultados reproducibles. Los límites científicos se explican aquí para no confundir una selección sólida con una equivalencia planetaria demostrada.</p><div class="cols"><div><h3>Fuentes científicas</h3><p>Topografía marciana MOLA; topografía terrestre NOAA ETOPO; sectores argentinos NASADEM; litología GLiM y cartografía marciana USGS SIM 3292; ambiente terrestre NASA POWER.</p></div><div><h3>Qué podemos afirmar</h3><p>Con los datos disponibles, Argentina conserva un puesto topográfico favorable y una señal volcánica general para Elysium. La mineralogía, formación y utilidad operativa de esos materiales requieren validación independiente.</p></div></div></div><div class="panel"><h3>Referencias externas</h3><p class="lead" id="benchmark-result"></p><div class="scroll"><table><thead><tr><th>Sitio</th><th>Región marciana</th><th>Puesto</th><th>Resultado del protocolo</th></tr></thead><tbody id="benchmark-rows"></tbody></table></div></div><div class="panel"><h3>Limitaciones técnicas y científicas</h3><ul id="limitations-list"></ul></div><div class="panel"><h3>Procedencia verificada (SHA-256)</h3><p class="small">Los informes históricos se comprueban antes de construir el panel. ETOPO y NASADEM también se identifican con hashes cuando están disponibles.</p><div id="sources-list"></div></div></section>
<footer class="footer">Mars Analog Discovery Engine V2.0.6 · Explorador topográfico mundial local · Topografía terrestre ETOPO/NASADEM y marciana MOLA procedente de tus archivos · Sin dependencia de Internet para visualizar las elevaciones.</footer></main><script type="application/json" id="dataset">"""+payload+r"""</script><script>"""+js+r"""</script></body></html>"""
    return markup
