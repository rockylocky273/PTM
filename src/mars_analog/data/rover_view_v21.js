// V2.1 rover planning viewer. All elevations in original metres, with explicit
// georeferenced sample spacing. Adapted from the user's 60x60 A* prototype,
// avoiding its arbitrary rescaling, 1m cell assumption and fictitious energy.
(()=>{'use strict';
const $=id=>document.getElementById(id);
const doc=DATA.rover_terrain_v21||{sites:[],available_sites:0};
const view=$('view-rover'),canvas=$('rover-canvas'),ctx=canvas.getContext('2d');
const select=$('rover-terrain-select');
let terrain=null,start=null,goal=null,route=[],metrics=null,mode=null;
let viewScale=1.0,panX=0,panY=0,isDragging=false,dragged=false,last=null;
let raster=null,frame=0,animRequest=null,animStart=0;
let hazards=null,slopes=null,drawPending=false;
const sourceSites=(doc.sites||[]).filter(s=>s.status==='available');
const unavailable=(doc.sites||[]).filter(s=>s.status!=='available');
function bridgePublish(kind){
 window.dispatchEvent(new CustomEvent('mars-rover-bridge',{detail:{kind}}));
}
window.MarsRoverBridgeV22={
 snapshot:()=>({terrain,start,goal,route,metrics,hazards,slopes,frame}),
 stop2D:()=>stopAnimation()
};
const status=t=>{$('rover-status').textContent=t};
const fmt=(n,d=1)=>Number(n).toLocaleString('es-ES',{maximumFractionDigits:d,minimumFractionDigits:0});
function addOption(value,text){const opt=document.createElement('option');opt.value=value;opt.textContent=text;select.appendChild(opt)}
sourceSites.forEach((s,i)=>addOption('site'+i,`${s.display_name} · NASADEM (${fmt(s.cell_size_x_m,0)} m/píxel)`));
unavailable.forEach(s=>addOption('missing:'+s.id,`${s.id.split('_').slice(-1)[0].toUpperCase()} · sin archivo NASADEM`));
addOption('demo','Terreno DEM de demostración · SINTÉTICO');
addOption('custom','DEM importado (JSON)');
const cell=(x,y)=>terrain.elevation_m[y]?.[x];
const inside=(x,y)=>x>=0&&y>=0&&x<terrain.width&&y<terrain.height;
const finite=v=>typeof v==='number'&&Number.isFinite(v);
const dxm=()=>terrain.cell_size_x_m,dym=()=>terrain.cell_size_y_m;
function clearMetrics(){['rover-distance','rover-ascent','rover-route-slope','rover-cost'].forEach(id=>$(id).textContent='—')}
function demoTerrain(){
 const width=110,height=110,grid=[];
 for(let y=0;y<height;y++){
  const row=[];for(let x=0;x<width;x++){
   const ridge=20*Math.exp(-((x-53)**2/110+(y-35)**2/210));
   const valley=12*Math.exp(-((x-20)**2/260+(y-72)**2/200));
   row.push(Math.round((2210+ridge-valley+1.1*Math.sin(x/8)*Math.cos(y/10))*100)/100);
  }grid.push(row);
 }
 return {id:'demo_synthetic',status:'available',display_name:'Terreno matemático sintético',source:'SIMULACIÓN MATEMÁTICA · NO ES UN DEM PLANETARIO',
  width,height,cell_size_x_m:5,cell_size_y_m:5,elevation_m:grid,planet:'Simulation',
  simulation_level:'synthetic_demonstration',valid_fraction:1};
}
function validateGrid(raw,source){
 if(!raw||!Array.isArray(raw.elevation_m))throw Error('El JSON debe contener un arreglo elevation_m de filas.');
 const arr=raw.elevation_m,h=arr.length,w=Array.isArray(arr[0])?arr[0].length:0;
 if(h<10||w<10||h>256||w>256||!arr.every(r=>Array.isArray(r)&&r.length===w))throw Error('La cuadrícula debe ser rectangular, de 10 a 256 muestras por eje.');
 const sx=Number(raw.cell_size_x_m),sy=Number(raw.cell_size_y_m);
 if(!Number.isFinite(sx)||!Number.isFinite(sy)||sx<.25||sy<.25||sx>2000||sy>2000)throw Error('Se necesitan cell_size_x_m y cell_size_y_m en metros, entre 0.25 y 2000.');
 const grid=[];let good=0;let low=Infinity,high=-Infinity;
 for(let y=0;y<h;y++){
  const row=[];for(let x=0;x<w;x++){
   const v=arr[y][x];if(v===null){row.push(null);continue}
   if(typeof v!=='number'||!Number.isFinite(v))throw Error('Valores de elevación inválidos; solo números en metros o null.');
   good++;low=Math.min(low,v);high=Math.max(high,v);row.push(v);
  }grid.push(row);
 }
 if(good<50||good/(h*w)<.5)throw Error('Insuficientes elevaciones válidas para generar una ruta.');
 return {id:String(raw.id||'imported_dem').slice(0,90),status:'available',planet:String(raw.planet||'Unspecified'),
  display_name:String(raw.display_name||raw.id||'DEM importado').slice(0,110),
  source:String(source||raw.source||'Archivo local aportado').slice(0,200),width:w,height:h,
  cell_size_x_m:sx,cell_size_y_m:sy,elevation_m:grid, min_elevation_m:low,max_elevation_m:high,
  lat_north_deg:finite(raw.lat_north_deg)?raw.lat_north_deg:null,
  lon_west_deg:finite(raw.lon_west_deg)?raw.lon_west_deg:null,simulation_level:'uploaded_dem_not_verified'};
}
function nearestClear(x,y){
 x=Math.min(terrain.width-1,Math.max(0,Math.round(x)));y=Math.min(terrain.height-1,Math.max(0,Math.round(y)));
 if(finite(cell(x,y))&&!hazards[y*terrain.width+x])return {x,y};
 for(let r=1;r<Math.max(terrain.width,terrain.height);r++){
  for(let yy=Math.max(0,y-r);yy<=Math.min(terrain.height-1,y+r);yy++)for(let xx=Math.max(0,x-r);xx<=Math.min(terrain.width-1,x+r);xx++){
   if(Math.max(Math.abs(xx-x),Math.abs(yy-y))===r&&finite(cell(xx,yy))&&!hazards[yy*terrain.width+xx])return {x:xx,y:yy};
  }
 }
 return null;
}
function measureSlope(x,y){
 const z=cell(x,y);if(!finite(z))return Infinity;
 let highest=0;
 for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){
  if(!dx&&!dy)continue;const nx=x+dx,ny=y+dy;
  if(!inside(nx,ny))continue;
  const v=cell(nx,ny);if(!finite(v))continue;
  const horizontal=Math.hypot(dx*dxm(),dy*dym());
  highest=Math.max(highest,Math.atan(Math.abs(v-z)/horizontal)*180/Math.PI);
 }
 return highest;
}
function recompute(){
 if(!terrain)return;
 const max=Number($('rover-max-slope').value);
 $('rover-slope-value').textContent=max+'°';
 $('rover-uphill-value').textContent=$('rover-uphill').value+'×';
 hazards=new Uint8Array(terrain.width*terrain.height);
 slopes=new Float32Array(hazards.length);
 for(let y=0;y<terrain.height;y++)for(let x=0;x<terrain.width;x++){
  const p=y*terrain.width+x,sl=measureSlope(x,y);
  slopes[p]=sl;hazards[p]=sl>max||!Number.isFinite(sl)?1:0;
 }
 // Explicitly invalidate previous plan when constraints change.
 route=[];metrics=null;stopAnimation();clearMetrics();queueDraw();bridgePublish('constraints');
}
function buildRaster(){
 const W=terrain.width,H=terrain.height;
 const off=document.createElement('canvas');off.width=W;off.height=H;
 const c=off.getContext('2d');const img=c.createImageData(W,H);
 const nums=terrain.elevation_m.flat().filter(finite).sort((a,b)=>a-b);
 const lo=nums[Math.floor(nums.length*.02)],hi=nums[Math.floor(nums.length*.98)];
 const span=Math.max(hi-lo,1);
 for(let y=0;y<H;y++)for(let x=0;x<W;x++){
  const z=cell(x,y),p=(y*W+x)*4;
  if(!finite(z)){img.data.set([23,39,51,255],p);continue}
  const t=Math.max(0,Math.min(1,(z-lo)/span));
  let r,g,b;
  if(t<.5){const f=t*2;r=41+115*f;g=101+66*f;b=126-28*f}
  else{const f=(t-.5)*2;r=156+74*f;g=167+50*f;b=98+87*f}
  const l=finite(cell(Math.max(0,x-1),y))?cell(Math.max(0,x-1),y):z;
  const rgt=finite(cell(Math.min(W-1,x+1),y))?cell(Math.min(W-1,x+1),y):z;
  const up=finite(cell(x,Math.max(0,y-1)))?cell(x,Math.max(0,y-1)):z;
  const down=finite(cell(x,Math.min(H-1,y+1)))?cell(x,Math.min(H-1,y+1)):z;
  const shade=Math.max(.65,Math.min(1.25,1+.8*((l-rgt)/Math.max(2,dxm())+(up-down)/Math.max(2,dym()))));
  img.data[p]=r*shade;img.data[p+1]=g*shade;img.data[p+2]=b*shade;img.data[p+3]=255;
 }
 c.putImageData(img,0,0);raster=off;
}
function setTerrain(t){
 stopAnimation();terrain=validateGrid(t,t.source);start=null;goal=null;route=[];metrics=null;
 viewScale=1;panX=0;panY=0;buildRaster();recompute();
 start=nearestClear(terrain.width*.15,terrain.height*.50);
 goal=nearestClear(terrain.width*.82,terrain.height*.52);
 $('rover-map-name').textContent=terrain.display_name;
 $('rover-source').textContent=`Fuente: ${terrain.source}. Rejilla ${terrain.width}×${terrain.height}; ${fmt(dxm(),1)}×${fmt(dym(),1)} metros por celda. Cobertura ~${fmt(terrain.width*dxm()/1000,2)} × ${fmt(terrain.height*dym()/1000,2)} km. ${terrain.id==='demo_synthetic'?'TODOS LOS DATOS SON ARTIFICIALES.':''}`;
 $('rover-map-scale').textContent=`${fmt(terrain.width*dxm()/1000,2)} km de ancho`;
 status('Terreno cargado. Elegí dos puntos o pulsa Calcular ruta A*.');queueDraw();bridgePublish('terrain');
}
class Heap{
 constructor(){this.a=[]}push(it){this.a.push(it);let i=this.a.length-1;while(i){let j=(i-1)>>1;if(this.a[j][0]<=it[0])break;this.a[i]=this.a[j];i=j}this.a[i]=it}
 pop(){const a=this.a;if(!a.length)return null;const top=a[0],last=a.pop();if(a.length){let i=0;while(true){let l=i*2+1,r=l+1,small=l;if(l>=a.length)break;if(r<a.length&&a[r][0]<a[l][0])small=r;if(last[0]<=a[small][0])break;a[i]=a[small];i=small}a[i]=last}return top}
 get length(){return this.a.length}
}
function routePlan(){
 if(!terrain)return status('Cargá primero una malla topográfica.');
 if(!start||!goal)return status('Elegí puntos de inicio y destino libres.');
 const W=terrain.width,H=terrain.height,N=W*H;
 const idx=pt=>pt.y*W+pt.x,si=idx(start),gi=idx(goal);
 if(hazards[si]||hazards[gi])return status('Inicio o destino bloqueado por el umbral de pendiente.');
 const g=new Float64Array(N).fill(Infinity),from=new Int32Array(N).fill(-1),closed=new Uint8Array(N),heap=new Heap();
 const minCost=1,uphill=Number($('rover-uphill').value);
 const h=(x,y)=>Math.hypot((x-goal.x)*dxm(),(y-goal.y)*dym())*minCost;
 g[si]=0;heap.push([h(start.x,start.y),si]);
 const neighbors=[[-1,0],[1,0],[0,-1],[0,1],[-1,-1],[-1,1],[1,-1],[1,1]];
 let expanded=0;const LIMIT=262144;
 while(heap.length&&expanded++<LIMIT){
  const item=heap.pop(),pos=item[1],x=pos%W,y=Math.floor(pos/W);
  if(closed[pos])continue;closed[pos]=1;
  if(pos===gi)break;
  for(const [dx,dy] of neighbors){
   const nx=x+dx,ny=y+dy;if(!inside(nx,ny))continue;
   const p=ny*W+nx;if(closed[p]||hazards[p])continue;
   // Diagonal corner-cutting is forbidden if either adjacent cardinal cell is blocked.
   if(dx&&dy&&(hazards[y*W+nx]||hazards[ny*W+x]))continue;
   const horiz=Math.hypot(dx*dxm(),dy*dym());
   const dz=cell(nx,ny)-cell(x,y),slope=Math.atan(Math.abs(dz)/horiz)*180/Math.PI;
   if(slope>Number($('rover-max-slope').value))continue;
   const weighted=horiz*(1+uphill*Math.max(0,dz)/horiz+1.4*Math.max(0,-dz)/horiz);
   const ng=g[pos]+weighted;
   if(ng+1e-9<g[p]){g[p]=ng;from[p]=pos;heap.push([ng+h(nx,ny),p])}
  }
 }
 if(!Number.isFinite(g[gi])){route=[];metrics=null;stopAnimation();clearMetrics();status('No existe una ruta conectada que cumpla el umbral de pendiente. Probá puntos cercanos o un límite diferente.');queueDraw();bridgePublish('route');return}
 let r=[],p=gi;while(p>=0){r.push({x:p%W,y:Math.floor(p/W)});if(p===si)break;p=from[p]}
 r.reverse();route=r;
 let length=0,ascent=0,descent=0,peak=0,slSum=0;
 for(let i=1;i<route.length;i++){
  const a=route[i-1],b=route[i],horizontal=Math.hypot((b.x-a.x)*dxm(),(b.y-a.y)*dym());
  const dz=cell(b.x,b.y)-cell(a.x,a.y),theta=Math.atan(Math.abs(dz)/horizontal)*180/Math.PI;
  length+=horizontal;ascent+=Math.max(0,dz);descent+=Math.max(0,-dz);peak=Math.max(peak,theta);slSum+=theta;
 }
 metrics={distance_m:+length.toFixed(2),ascent_m:+ascent.toFixed(2),descent_m:+descent.toFixed(2),
  max_transition_slope_deg:+peak.toFixed(2),mean_transition_slope_deg:+(slSum/Math.max(1,r.length-1)).toFixed(2),
  relative_route_cost:+g[gi].toFixed(2),total_steps:Math.max(0,r.length-1)};
 $('rover-distance').textContent=fmt(metrics.distance_m,1)+' m';
 $('rover-ascent').textContent=fmt(metrics.ascent_m,1)+' m';
 $('rover-route-slope').textContent=fmt(metrics.max_transition_slope_deg,1)+'°';
 $('rover-cost').textContent=fmt(metrics.relative_route_cost,1)+' u.r.';
 status(`Ruta encontrada: ${r.length} celdas · ${fmt(length,1)} m · ascenso ${fmt(ascent,1)} m · pendiente máxima de paso ${fmt(peak,1)}°. Resultados exploratorios, no seguridad física.`);
 queueDraw();bridgePublish('route');
}
function canvasFit(){const w=canvas.width,h=canvas.height;if(!terrain)return {x:0,y:0,w,h};
 const f=Math.min((w-30)/terrain.width,(h-30)/terrain.height)*viewScale;
 const rw=f*terrain.width,rh=f*terrain.height;
 return {x:(w-rw)/2+panX,y:(h-rh)/2+panY,w:rw,h:rh,px:f};
}
function clientPoint(e){const box=canvas.getBoundingClientRect();return {x:(e.clientX-box.left)/box.width*canvas.width,y:(e.clientY-box.top)/box.height*canvas.height}}
function canvasCell(p){if(!terrain)return null;const b=canvasFit();let x=Math.floor((p.x-b.x)/b.px),y=Math.floor((p.y-b.y)/b.px);
 return inside(x,y)?{x,y}:null;
}
function drawMarker(pt,name,color,b){if(!pt)return;const x=b.x+(pt.x+.5)*b.px,y=b.y+(pt.y+.5)*b.px;
 ctx.beginPath();ctx.arc(x,y,8,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();ctx.strokeStyle='white';ctx.lineWidth=2;ctx.stroke();
 ctx.fillStyle='white';ctx.font='bold 11px Arial';ctx.textAlign='center';ctx.fillText(name,x,y+4);
}
function draw(){
 const W=canvas.width,H=canvas.height;ctx.clearRect(0,0,W,H);ctx.fillStyle='#112e3c';ctx.fillRect(0,0,W,H);
 if(!terrain||!raster)return;
 const b=canvasFit();ctx.imageSmoothingEnabled=b.px<2;ctx.drawImage(raster,b.x,b.y,b.w,b.h);
 if($('rover-show-hazards').checked){
  ctx.fillStyle='rgba(198,55,45,.24)';
  for(let y=0;y<terrain.height;y++)for(let x=0;x<terrain.width;x++)if(hazards[y*terrain.width+x])ctx.fillRect(b.x+x*b.px,b.y+y*b.px,Math.max(1,b.px),Math.max(1,b.px));
 }
 if($('rover-show-grid').checked&&b.px>6){ctx.lineWidth=.6;ctx.strokeStyle='rgba(255,255,255,.19)';ctx.beginPath();
  for(let i=0;i<=terrain.width;i++){let xx=b.x+i*b.px;ctx.moveTo(xx,b.y);ctx.lineTo(xx,b.y+b.h)}
  for(let j=0;j<=terrain.height;j++){let yy=b.y+j*b.px;ctx.moveTo(b.x,yy);ctx.lineTo(b.x+b.w,yy)}ctx.stroke()}
 if(route.length){ctx.beginPath();ctx.lineWidth=Math.max(3,Math.min(6,b.px*.8));ctx.strokeStyle='#fff5c4';
  route.forEach((pt,i)=>{let x=b.x+(pt.x+.5)*b.px,y=b.y+(pt.y+.5)*b.px;i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();
  if(animRequest!==null){let idx=Math.min(route.length-1,Math.round(frame*(route.length-1))),p=route[idx];
   let xx=b.x+(p.x+.5)*b.px,yy=b.y+(p.y+.5)*b.px;ctx.fillStyle='#feaa38';ctx.beginPath();ctx.arc(xx,yy,Math.max(7,b.px*.65),0,Math.PI*2);ctx.fill();ctx.strokeStyle='white';ctx.stroke();}
 }
 drawMarker(start,'A','#168e87',b);drawMarker(goal,'B','#d96738',b);
}
function queueDraw(){if(drawPending)return;drawPending=true;requestAnimationFrame(()=>{drawPending=false;if(!view.hidden)draw()})}
function stopAnimation(){if(animRequest!==null)cancelAnimationFrame(animRequest);animRequest=null;frame=0}
function animate(){if(!route.length){routePlan();if(!route.length)return}
 stopAnimation();animStart=performance.now();const duration=Math.max(1600,Math.min(6500,route.length*30));
 function tick(t){frame=Math.min(1,(t-animStart)/duration);draw();if(frame<1){animRequest=requestAnimationFrame(tick)}else{animRequest=null;draw()}}
 animRequest=requestAnimationFrame(tick);
}
function setMode(m){mode=mode===m?null:m;for(const [name,id] of [['start','rover-pick-start'],['goal','rover-pick-goal']])$(id).setAttribute('aria-pressed',mode===name?'true':'false');
 $('rover-map-hint').textContent=mode?`Clic en el mapa para elegir ${mode==='start'?'INICIO A':'DESTINO B'}`:'Rueda: zoom · Arrastrar: mover · Botones: seleccionar A/B';}
function terrainChoice(){const v=select.value;if(v==='custom')return status('Seleccioná un archivo JSON con elevaciones originales en metros y tamaño de celda.');
 if(v==='demo')return setTerrain(demoTerrain());if(v.startsWith('missing:'))return status('No hay NASADEM local disponible para este sector. Conservá los datos históricos de V1.3.3.');
 const s=sourceSites[Number(v.slice(4))];if(s)setTerrain(s);
}
select.addEventListener('change',terrainChoice);
$('rover-upload').addEventListener('change',async e=>{const file=e.target.files?.[0];if(!file)return;
 try{if(file.size>6_000_000)throw Error('El archivo supera el límite de 6 MB.');
  const raw=JSON.parse(await file.text()),t=validateGrid(raw,`DEM importado: ${file.name}`);
  let opt=select.querySelector('option[value="custom"]');opt.textContent='DEM importado · '+t.display_name;select.value='custom';setTerrain(t);
 }catch(err){status('Archivo rechazado: '+err.message)}finally{e.target.value=''}
});
$('rover-pick-start').addEventListener('click',()=>setMode('start'));$('rover-pick-goal').addEventListener('click',()=>setMode('goal'));
$('rover-max-slope').addEventListener('input',()=>{recompute();status('Pendiente máxima modificada: volvé a calcular la ruta.');});
$('rover-uphill').addEventListener('input',()=>{recompute();status('Penalización de ascenso modificada: volvé a calcular la ruta.');});
$('rover-show-hazards').addEventListener('change',queueDraw);$('rover-show-grid').addEventListener('change',queueDraw);
$('rover-plan').addEventListener('click',routePlan);$('rover-animate').addEventListener('click',animate);
$('rover-reset-view').addEventListener('click',()=>{viewScale=1;panX=0;panY=0;queueDraw()});
$('rover-export').addEventListener('click',()=>{
 if(!terrain||!metrics||!route.length)return status('Primero calculá una ruta válida para exportarla.');
 const output={schema_version:'mars_rover_route_v2.1',source_id:terrain.id,source:terrain.source,
  source_sha256:terrain.source_sha256||null,planet:terrain.planet,physical_cell_size_m:[dxm(),dym()],
  rover_constraint:{max_slope_deg:Number($('rover-max-slope').value),uphill_penalty:Number($('rover-uphill').value)},
  route:Array.from(route),metrics,model:'heuristic_cost_not_joules',validated_for_real_rover:false};
 const blob=new Blob([JSON.stringify(output,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob);
 const a=document.createElement('a');a.href=url;a.download='mars_rover_route_v21_'+terrain.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);
});
let down=null;
canvas.addEventListener('pointerdown',e=>{if(e.button!==0)return;down={p:clientPoint(e),panX,panY};dragged=false;canvas.setPointerCapture(e.pointerId)});
canvas.addEventListener('pointermove',e=>{if(!terrain)return;const p=clientPoint(e);
 if(down){const dx=p.x-down.p.x,dy=p.y-down.p.y;if(Math.hypot(dx,dy)>4)dragged=true;
  if(dragged){panX=down.panX+dx;panY=down.panY+dy;queueDraw()}}
 const c=canvasCell(p);if(c){const z=cell(c.x,c.y);const s=slopes[c.y*terrain.width+c.x];
  let geo='';if(finite(terrain.lat_north_deg)&&finite(terrain.lon_west_deg)){
   const lat=terrain.lat_north_deg-c.y*dym()/111132;
   const lon=terrain.lon_west_deg+c.x*dxm()/(111320*Math.cos(lat*Math.PI/180));
   geo=` · ${fmt(lat,5)}°, ${fmt(lon,5)}°`;
  }
  $('rover-hover').textContent=`Celda (${c.x}, ${c.y}) · ${finite(z)?fmt(z,2)+' m':'sin datos'} · pendiente local ${finite(s)?fmt(s,1)+'°':'sin datos'}${geo}`;
 }});
canvas.addEventListener('pointerup',e=>{const p=clientPoint(e);if(down&&!dragged&&mode&&terrain){const c=canvasCell(p);
 if(c){if(hazards[c.y*terrain.width+c.x])status('Este punto supera la pendiente permitida o no tiene elevación; elegí otra celda.');
 else{if(mode==='start')start=c;else goal=c;route=[];metrics=null;stopAnimation();clearMetrics();status('Punto actualizado. Pulsá Calcular ruta A*.');setMode(null);queueDraw();bridgePublish('points')}}
 }down=null;});
canvas.addEventListener('pointercancel',()=>down=null);
canvas.addEventListener('wheel',e=>{e.preventDefault();if(!terrain)return;
 const p=clientPoint(e),prior=canvasFit(),px=(p.x-prior.x)/prior.px,py=(p.y-prior.y)/prior.px;
 viewScale=Math.max(.5,Math.min(24,viewScale*(e.deltaY<0?1.25:.8)));
 const after=canvasFit();panX+=(p.x-(after.x+px*after.px));panY+=(p.y-(after.y+py*after.px));queueDraw();
},{passive:false});
// Direct path from the existing Argentina NASADEM tabs to the rover tool.
const atlasLocalDetail=document.getElementById('site-active-details');
if(atlasLocalDetail){
 const go=document.createElement('button');go.type='button';go.className='table-button';
 go.textContent='Simular ruta sobre este sector';go.style.marginTop='9px';
 go.addEventListener('click',()=>{
  const which=(typeof mapId==='string'&&mapId.endsWith('p08'))?'r026_c146_p08':'r026_c146_p04';
  const i=sourceSites.findIndex(s=>s.id===which);
  document.querySelector('.nav button[data-view="rover"]').click();
  if(i>=0){select.value='site'+i;setTerrain(sourceSites[i])}
  else status('Faltan elevaciones NASADEM originales de '+which+'; se muestra el terreno de demostración por separado.');
 });atlasLocalDetail.appendChild(go);
}
// Only real DEM-based planning when a source is actually available. Synthetic demo is explicit.
if(sourceSites.length){select.value='site0';terrainChoice()}else{select.value='demo';terrainChoice();status('No se encontró NASADEM local. Se muestra un terreno SINTÉTICO DE DEMOSTRACIÓN; ejecutá con los datos históricos para obtener terreno real.');}
document.querySelector('.nav button[data-view="rover"]').addEventListener('click',()=>requestAnimationFrame(draw));
})();
