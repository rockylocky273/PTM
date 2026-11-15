// Mars Analog Discovery Engine V2.2 · self-contained offline WebGL2 terrain viewer.
// One physical DEM + one A* route: the 3D viewport NEVER recalculates the route,
// re-normalizes elevations, adds invented obstacles, or claims rover safety.
(()=>{'use strict';
const $=id=>document.getElementById(id);
const stage=$('rover-3d-stage'),canvas=$('rover-canvas-3d'),info=$('rover-3d-info');
if(!canvas||!window.MarsRoverBridgeV22)return;
const bridge=window.MarsRoverBridgeV22;
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const valid=x=>typeof x==='number'&&Number.isFinite(x);
const norm=v=>{let d=Math.hypot(...v)||1;return v.map(x=>x/d)};
const dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
function perspective(fov,aspect,near,far){const f=1/Math.tan(fov/2),d=1/(near-far);return new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)*d,-1,0,0,2*far*near*d,0])}
function lookAt(eye,target){const z=norm(eye.map((v,i)=>v-target[i])),x=norm(cross([0,1,0],z)),y=cross(z,x);return new Float32Array([x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1])}
function mul(a,b){const o=new Float32Array(16);for(let c=0;c<4;c++)for(let r=0;r<4;r++){let v=0;for(let k=0;k<4;k++)v+=a[k*4+r]*b[c*4+k];o[c*4+r]=v}return o}
const colors={sand:[.81,.64,.39],teal:[.18,.59,.63],ridge:[.83,.79,.70],route:[1,.80,.25],body:[1,.54,.19],wheel:[.12,.18,.23],mast:[.88,.91,.86],A:[.08,.91,.69],B:[1,.29,.24]};
let terrain=null,route=[],hazards=null,slopes=null,start=null,goal=null,progress=0;
let gl=null,soft=null,program=null,flatProgram=null,mesh=null,routeMesh=null,roverMesh=null,marks=null;
let mode='orbit',surfaceLayer='elevation',vertical=2,quality='auto';
let yaw=-.75,pitch=.66,radius=1,target=[0,0,0],extent=1,base=0,heightRange=1;
let running=false,playRAF=0,lastTick=0,speed=1,scheduled=false,contextLost=false;
let pointer=null,sceneTag='',meshStride=0;
const status=t=>{info.textContent=t};
function shader(type,src){const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s}
function programMake(vs,fs){const p=gl.createProgram();gl.attachShader(p,shader(gl.VERTEX_SHADER,vs));gl.attachShader(p,shader(gl.FRAGMENT_SHADER,fs));gl.linkProgram(p);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(p));return p}
const VERT=`#version 300 es
layout(location=0) in vec3 aPosition;
layout(location=1) in vec3 aNormal;
layout(location=2) in vec3 aColor;
uniform mat4 uMVP;
out vec3 vColor;
void main(){
 gl_Position=uMVP*vec4(aPosition,1.0);
 float light=0.48+0.52*max(dot(normalize(aNormal),normalize(vec3(-0.42,0.85,0.35))),0.0);
 vColor=aColor*light;
}`;
const FRAG=`#version 300 es
precision mediump float;
in vec3 vColor;out vec4 outColor;
void main(){outColor=vec4(vColor,1.0);}`;
function initGL(){
 if(gl||soft)return true;if(contextLost)return false;
 try{
  gl=canvas.getContext('webgl2',{antialias:true,alpha:false,preserveDrawingBuffer:false,powerPreference:'low-power'});
  if(!gl)throw Error('WebGL2 no está disponible en este navegador.');
  program=programMake(VERT,FRAG);
  gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.clearColor(.065,.135,.185,1);
  canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();contextLost=true;gl=null;stop();status('Se perdió el contexto WebGL. Volvé a Vista 2D o recargá el panel.');});
  canvas.addEventListener('webglcontextrestored',()=>{contextLost=false;gl=null;mesh=null;routeMesh=null;roverMesh=null;marks=null;initGL();rebuildAll();});
  return true;
 }catch(e){
  // When WebGL2 is blocked, render a genuine perspective projection of the
  // physical terrain using a bounded CPU triangle mesh rather than an empty tab.
  if(!gl)soft=canvas.getContext('2d');
  if(soft){status('Render 3D compatible por Canvas · detalle reducido (sin WebGL2).');return true}
  status('3D no disponible: '+e.message+' · Podés continuar usando el mapa 2D.');return false
 }
}
function destroy(obj){if(obj&&gl){gl.deleteBuffer(obj.vbo);gl.deleteBuffer(obj.ibo)}}
function makeMesh(vertices,indices,mode=gl.TRIANGLES,dynamic=false){
 const vbo=gl.createBuffer(),ibo=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,vbo);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(vertices),dynamic?gl.DYNAMIC_DRAW:gl.STATIC_DRAW);
 gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ibo);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(indices),gl.STATIC_DRAW);
 return {vbo,ibo,count:indices.length,mode};
}
function drawMesh(obj,mvp){if(!obj||!obj.count)return;gl.useProgram(program);gl.uniformMatrix4fv(gl.getUniformLocation(program,'uMVP'),false,mvp);
 gl.bindBuffer(gl.ARRAY_BUFFER,obj.vbo);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,obj.ibo);
 for(let k=0;k<3;k++){gl.enableVertexAttribArray(k);gl.vertexAttribPointer(k,3,gl.FLOAT,false,36,k*12)}
 gl.drawElements(obj.mode,obj.count,gl.UNSIGNED_INT,0);
}
function geo(x,y){if(!terrain)return [0,0,0];return [(x-(terrain.width-1)/2)*terrain.cell_size_x_m,0,(y-(terrain.height-1)/2)*terrain.cell_size_y_m]}
function point(x,y,extra=0){const p=geo(x,y),ix=clamp(Math.round(x),0,terrain.width-1),iy=clamp(Math.round(y),0,terrain.height-1);
 const z=terrain.elevation_m[iy]?.[ix];p[1]=valid(z)?(z-base)*vertical+extra:extra;return p}
function pushVertex(v,p,n,c){v.push(p[0],p[1],p[2],n[0],n[1],n[2],c[0],c[1],c[2])}
function landColor(z,s,blocked){
 if(surfaceLayer==='hazards')return blocked? [.91,.25,.19] : [.23,.65,.47];
 if(surfaceLayer==='slope'){const t=clamp(s/35,0,1);return [.20+.75*t,.77-.50*t,.42-.30*t]}
 const t=clamp((z-base)/Math.max(1,heightRange),0,1);
 return t<.5?colors.teal.map((c,i)=>c*(1-t*2)+colors.sand[i]*t*2):colors.sand.map((c,i)=>c*(2-2*t)+colors.ridge[i]*(t*2-1));
}
function nativeValidRect(x0,y0,x1,y1){for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++)if(!valid(terrain.elevation_m[y][x]))return false;return true}
function makeSurface(stride){
 const w=terrain.width,h=terrain.height,v=[],idx=[];
 const xs=[],ys=[];for(let x=0;x<w-1;x+=stride)xs.push(x);xs.push(w-1);for(let y=0;y<h-1;y+=stride)ys.push(y);ys.push(h-1);
 const nX=xs.length;
 for(let yi=0;yi<ys.length;yi++)for(let xi=0;xi<xs.length;xi++){
  const x=xs[xi],y=ys[yi],z=terrain.elevation_m[y][x],p=point(x,y);
  const l=terrain.elevation_m[y][Math.max(0,x-1)],r=terrain.elevation_m[y][Math.min(w-1,x+1)];
  const u=terrain.elevation_m[Math.max(0,y-1)][x],d=terrain.elevation_m[Math.min(h-1,y+1)][x];
  const dzdx=valid(l)&&valid(r)?(r-l)/(x===0||x===w-1?terrain.cell_size_x_m:2*terrain.cell_size_x_m):0;
  const dzdy=valid(u)&&valid(d)?(d-u)/(y===0||y===h-1?terrain.cell_size_y_m:2*terrain.cell_size_y_m):0;
  let n=norm([-dzdx*vertical,1,-dzdy*vertical]);
  const pidx=y*w+x;
  pushVertex(v,p,n,valid(z)?landColor(z,slopes?.[pidx]||0,hazards?.[pidx]||0):[.2,.24,.3]);
 }
 for(let yi=0;yi<ys.length-1;yi++)for(let xi=0;xi<xs.length-1;xi++){
  if(!nativeValidRect(xs[xi],ys[yi],xs[xi+1],ys[yi+1]))continue;
  const a=yi*nX+xi,b=a+1,c=a+nX,d=c+1;
  idx.push(a,c,b,b,c,d);
 }
 return makeMesh(v,idx);
}
// Road ribbon follows the exact cell-centre route computed by V2.1; no smoothing
// that could visually move the path into a blocked or unobserved cell.
function makeRoute(){if(!terrain||route.length<2)return null;
 const verts=[],inds=[],width=Math.max(.7,Math.min(terrain.cell_size_x_m,terrain.cell_size_y_m)*.13);
 const gap=Math.max(.35,heightRange*vertical*.015);
 for(let i=0;i<route.length-1;i++){
  const a=route[i],b=route[i+1],pa=point(a.x,a.y,gap),pb=point(b.x,b.y,gap),dv=norm([pb[0]-pa[0],0,pb[2]-pa[2]]);
  const side=[-dv[2]*width,0,dv[0]*width],k=verts.length/9;
  [pa.map((x,j)=>x+side[j]),pa.map((x,j)=>x-side[j]),pb.map((x,j)=>x+side[j]),pb.map((x,j)=>x-side[j])].forEach(p=>pushVertex(verts,p,[0,1,0],colors.route));
  inds.push(k,k+2,k+1,k+1,k+2,k+3);
 }
 return makeMesh(verts,inds);
}
function boxPart(v,ind,center,dim,color,basis){
 const [right,up,forward]=basis;
 const faceDefs=[[[0,1,2,3],up],[[4,5,6,7],up.map(x=>-x)],[[0,4,7,3],right.map(x=>-x)],[[1,5,6,2],right],[[0,1,5,4],forward.map(x=>-x)],[[3,2,6,7],forward]];
 const [a,b,c]=dim.map(d=>d/2);
 const coords=[[-a,b,-c],[a,b,-c],[a,b,c],[-a,b,c],[-a,-b,-c],[a,-b,-c],[a,-b,c],[-a,-b,c]];
 const world=coords.map(d=>center.map((n,i)=>n+right[i]*d[0]+up[i]*d[1]+forward[i]*d[2]));
 for(const [corners,n] of faceDefs){const k=v.length/9;corners.forEach(q=>pushVertex(v,world[q],n,color));ind.push(k,k+1,k+2,k,k+2,k+3)}
}
function buildVehicle(){if(!terrain)return null;
 const p=positionAt(progress);if(!p)return null;
 const unit=Math.min(terrain.cell_size_x_m,terrain.cell_size_y_m),s=Math.max(1,unit*.65);
 const grad=normalAt(p.x,p.y),forward0=[p.dir[0],0,p.dir[1]];
 const f=norm(forward0.map((v,i)=>v-grad[i]*dot(forward0,grad)));
 const right=norm(cross(grad,f)),basis=[right,grad,f];
 const ground=point(p.x,p.y),verts=[],idx=[];
 function centre(dx,dy,dz){return ground.map((n,i)=>n+right[i]*dx+grad[i]*dy+f[i]*dz)}
 boxPart(verts,idx,centre(0,.55*s,0),[1.1*s,.38*s,1.55*s],colors.body,basis);
 boxPart(verts,idx,centre(0,.91*s,-.05*s),[.78*s,.07*s,.72*s],[.13,.27,.36],basis);
 boxPart(verts,idx,centre(0,1.17*s,-.1*s),[.07*s,.54*s,.07*s],colors.mast,basis);
 boxPart(verts,idx,centre(0,1.42*s,-.1*s),[.29*s,.18*s,.32*s],[.85,.92,.92],basis);
 for(const side of [-1,1])for(const dz of [-.52,0,.52]){
  boxPart(verts,idx,centre(side*.66*s,.25*s,dz*s),[.33*s,.45*s,.37*s],colors.wheel,basis)
 }
 return makeMesh(verts,idx);
}
function normalAt(x,y){const ix=clamp(Math.round(x),0,terrain.width-1),iy=clamp(Math.round(y),0,terrain.height-1);
 const l=terrain.elevation_m[iy][clamp(ix-1,0,terrain.width-1)],r=terrain.elevation_m[iy][clamp(ix+1,0,terrain.width-1)];
 const u=terrain.elevation_m[clamp(iy-1,0,terrain.height-1)][ix],d=terrain.elevation_m[clamp(iy+1,0,terrain.height-1)][ix];
 if(![l,r,u,d].every(valid))return [0,1,0];
 return norm([-(r-l)*vertical/(2*terrain.cell_size_x_m),1,-(d-u)*vertical/(2*terrain.cell_size_y_m)]);
}
function positionAt(t){if(!route.length)return start?{x:start.x,y:start.y,dir:[0,1]}:null;
 const a=clamp(t,0,1)*(route.length-1),i=Math.min(route.length-2,Math.floor(a)),u=clamp(a-i,0,1);
 if(route.length===1)return {x:route[0].x,y:route[0].y,dir:[0,1]};
 const p=route[i],q=route[i+1];return {x:p.x+(q.x-p.x)*u,y:p.y+(q.y-p.y)*u,dir:norm([(q.x-p.x)*terrain.cell_size_x_m,(q.y-p.y)*terrain.cell_size_y_m])};
}
function makeMarkers(){if(!terrain)return null;const verts=[],inds=[],s=Math.min(terrain.cell_size_x_m,terrain.cell_size_y_m),basis=[[1,0,0],[0,1,0],[0,0,1]];
 for(const [pt,col] of [[start,colors.A],[goal,colors.B]])if(pt){let p=point(pt.x,pt.y);p[1]+=.65*s;boxPart(verts,inds,p,[.34*s,1.1*s,.34*s],col,basis)}
 return makeMesh(verts,inds);
}
function currentStride(){if(quality==='full')return 1;if(quality==='economy')return 4;
 return radius>extent*3.2?4:radius>extent*1.65?2:1;
}
function rebuildSurface(){if(!gl||!terrain)return;const stride=currentStride();if(mesh&&meshStride===stride)return;
 destroy(mesh);mesh=makeSurface(stride);meshStride=stride;
 $('rover-3d-lod').textContent=`LOD ×${stride} · ${Math.floor(mesh.count/3).toLocaleString('es-ES')} triángulos`;
}
function rebuildAll(){if(soft){redraw();return}if(!gl||!terrain)return;destroy(mesh);mesh=null;meshStride=0;
 destroy(routeMesh);routeMesh=makeRoute();destroy(marks);marks=makeMarkers();rebuildSurface();redraw()}
function dims(){const w=(terrain.width-1)*terrain.cell_size_x_m,h=(terrain.height-1)*terrain.cell_size_y_m;return {w,h}}
function sync(kind){const state=bridge.snapshot();if(!state.terrain)return;
 const changed=state.terrain!==terrain;
 terrain=state.terrain;hazards=state.hazards;slopes=state.slopes;start=state.start;goal=state.goal;
 const changedRoute=state.route!==route;route=state.route||[];
 if(changed){const {w,h}=dims();extent=Math.max(w,h,100);const vals=terrain.elevation_m.flat().filter(valid);
  let low=Infinity,high=-Infinity;
  for(const v of vals){if(v<low)low=v;if(v>high)high=v}
  base=low;heightRange=Math.max(1,high-low);radius=extent*1.35;
  target=[0,heightRange*vertical*.15,0];yaw=-.8;pitch=.6;progress=0;stop();
 }
 if(changedRoute||kind==='constraints'||kind==='points'){progress=0;stop()}
 if(soft)redraw();
 if(gl){if(changed||kind==='constraints'||kind==='terrain')rebuildAll();else if(changedRoute||kind==='points'){destroy(routeMesh);routeMesh=makeRoute();destroy(marks);marks=makeMarkers();redraw()}}
 status(`${terrain.display_name} · ${terrain.width} × ${terrain.height} celdas · separación ${terrain.cell_size_x_m.toFixed(1)} × ${terrain.cell_size_y_m.toFixed(1)} m · altura original en metros · ${route.length?'ruta A* disponible':'calculá ruta A* en 2D'}`);
}
function resize(){if(!gl&&!soft)return false;const box=canvas.getBoundingClientRect();if(box.width<2||box.height<2)return false;
 const ratio=Math.min(window.devicePixelRatio||1,1.6),w=Math.min(1600,Math.round(box.width*ratio)),h=Math.min(1100,Math.round(box.height*ratio));
 if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h}if(gl)gl.viewport(0,0,w,h);return true;
}
function camera(){let eye,look;
 if(mode==='follow'&&route.length){const p=positionAt(progress),world=point(p.x,p.y);
  const fw=norm([p.dir[0],0,p.dir[1]]),d=Math.max(terrain.cell_size_x_m,terrain.cell_size_y_m);
  eye=[world[0]-fw[0]*d*10,world[1]+d*7,world[2]-fw[2]*d*10];
  look=[world[0]+fw[0]*d*2,world[1]+d*.8,world[2]+fw[2]*d*2];
 }else{
  const ang=mode==='aerial'?Math.max(pitch,1.30):pitch;
  look=target;eye=[target[0]+radius*Math.cos(ang)*Math.sin(yaw),target[1]+radius*Math.sin(ang),target[2]+radius*Math.cos(ang)*Math.cos(yaw)];
 }
 const near=Math.max(.04,extent*.00005),far=Math.max(extent*30,radius*15,heightRange*vertical*15);
 return mul(perspective(Math.PI/3,canvas.width/canvas.height,near,far),lookAt(eye,look));
}

// Low-cost perspective fallback, for browsers or devices that block WebGL2.
// The physical DEM is retained; only the number of drawn triangles is reduced.
function project3D(m,p){
 const x=p[0],y=p[1],z=p[2],v=[x,y,z,1],a=[0,0,0,0];
 for(let row=0;row<4;row++)for(let col=0;col<4;col++)a[row]+=m[col*4+row]*v[col];
 if(a[3]<=.001)return null;
 return {x:(a[0]/a[3]*.5+.5)*canvas.width,y:(.5-a[1]/a[3]*.5)*canvas.height,depth:a[2]/a[3]};
}
function colorCSS(col,light=1){return `rgb(${col.map(v=>Math.round(clamp(v*light,0,1)*255)).join(',')})`}
function paintCompatible3D(){
 const c=soft,w=canvas.width,h=canvas.height;
 c.clearRect(0,0,w,h);
 const grad=c.createLinearGradient(0,0,0,h);grad.addColorStop(0,'#102331');grad.addColorStop(1,'#21434b');c.fillStyle=grad;c.fillRect(0,0,w,h);
 const m=camera();
 const stride=quality==='full'?2:quality==='economy'?8:radius>extent*3?8:4;
 const xs=[],ys=[];for(let x=0;x<terrain.width-1;x+=stride)xs.push(x);xs.push(terrain.width-1);
 for(let y=0;y<terrain.height-1;y+=stride)ys.push(y);ys.push(terrain.height-1);
 const poly=[];
 for(let j=0;j<ys.length-1;j++)for(let i=0;i<xs.length-1;i++){
  const x0=xs[i],x1=xs[i+1],y0=ys[j],y1=ys[j+1];
  if(!nativeValidRect(x0,y0,x1,y1))continue;
  const a=project3D(m,point(x0,y0)),b=project3D(m,point(x1,y0)),d=project3D(m,point(x1,y1)),cc=project3D(m,point(x0,y1));
  if(!a||!b||!cc||!d)continue;
  const sl=slopes?.[Math.round((y0+y1)/2)*terrain.width+Math.round((x0+x1)/2)]||0;
  const blocked=hazards?.[Math.round((y0+y1)/2)*terrain.width+Math.round((x0+x1)/2)]||0;
  const elev=terrain.elevation_m[y0][x0];
  const col=landColor(elev,sl,blocked);
  const normal=normalAt((x0+x1)/2,(y0+y1)/2);
  const light=.54+.45*Math.max(0,dot(normal,norm([-.42,.85,.35])));
  poly.push({pts:[a,b,d,cc],depth:(a.depth+b.depth+d.depth+cc.depth)/4,color:colorCSS(col,light)});
 }
 poly.sort((a,b)=>b.depth-a.depth);
 for(const q of poly){c.fillStyle=q.color;c.beginPath();q.pts.forEach((p,i)=>i?c.lineTo(p.x,p.y):c.moveTo(p.x,p.y));c.closePath();c.fill()}
 if(route.length>1){c.strokeStyle='#ffcf4c';c.lineJoin='round';c.lineCap='round';c.lineWidth=Math.max(2,Math.min(6,w/230));c.beginPath();
  let count=0;for(const p of route){const q=project3D(m,point(p.x,p.y,Math.max(1,heightRange*.02)));
   if(q){count?c.lineTo(q.x,q.y):c.moveTo(q.x,q.y);count++}}
  c.stroke();
 }
 for(const [pt,name,col] of [[start,'A',colors.A],[goal,'B',colors.B]])if(pt){
  const p=project3D(m,point(pt.x,pt.y,Math.max(3,heightRange*.05)));if(!p)continue;
  c.fillStyle=colorCSS(col);c.beginPath();c.arc(p.x,p.y,Math.max(6,w/150),0,Math.PI*2);c.fill();
  c.fillStyle='#08232d';c.textAlign='center';c.font='bold 15px Arial';c.fillText(name,p.x,p.y+5)
 }
 const rover=positionAt(progress);
 if(rover){const p=project3D(m,point(rover.x,rover.y,Math.max(4,heightRange*.08)));
  const ahead=project3D(m,point(rover.x+rover.dir[0]*3,rover.y+rover.dir[1]*3,Math.max(4,heightRange*.08)));
  if(p){const sz=Math.max(9,Math.min(24,w/70));const a=ahead?Math.atan2(ahead.y-p.y,ahead.x-p.x):-.8;
   c.save();c.translate(p.x,p.y);c.rotate(a+Math.PI/2);
   c.fillStyle='#ffa83f';c.strokeStyle='#fff6c8';c.lineWidth=2;
   c.beginPath();c.moveTo(0,-sz*1.5);c.lineTo(-sz,sz*.7);c.lineTo(sz,sz*.7);c.closePath();c.fill();c.stroke();c.restore()}
 }
 $('rover-3d-lod').textContent=`LOD ×${stride} · modo 3D compatible (${poly.length} polígonos)`;
 $('rover-3d-progress').textContent=(progress*100).toFixed(0)+'%';
}
function paint(){scheduled=false;if(!terrain||(!gl&&!soft)||stage.hidden||document.getElementById('view-rover').hidden)return;
 if(!resize())return;
 if(soft){paintCompatible3D();return}
 rebuildSurface();gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
 const m=camera();drawMesh(mesh,m);drawMesh(routeMesh,m);drawMesh(marks,m);
 destroy(roverMesh);roverMesh=buildVehicle();drawMesh(roverMesh,m);
 $('rover-3d-progress').textContent=(progress*100).toFixed(0)+'%';
}
function redraw(){if(scheduled)return;scheduled=true;requestAnimationFrame(paint)}
function stop(){running=false;if(playRAF)cancelAnimationFrame(playRAF);playRAF=0;lastTick=0;$('rover-3d-play').textContent='▶ Reproducir'}
function play(){if(!route.length){status('Calculá una ruta A* en el mapa 2D antes de animar el rover.');return}
 if(running){stop();return}if(progress>=1)progress=0;
 running=true;lastTick=0;$('rover-3d-play').textContent='⏸ Pausar';
 const duration=Math.max(4500,Math.min(32000,route.length*115));
 const tick=t=>{if(!running)return;if(lastTick)progress=clamp(progress+(t-lastTick)*speed/duration,0,1);lastTick=t;redraw();
  if(progress>=1){stop();redraw()}else playRAF=requestAnimationFrame(tick)};
 playRAF=requestAnimationFrame(tick);
}
$('rover-view-2d').addEventListener('click',()=>{
 stop();stage.hidden=true;$('rover-map-two-d').hidden=false;
 $('rover-view-2d').setAttribute('aria-pressed','true');$('rover-view-3d').setAttribute('aria-pressed','false');
});
$('rover-view-3d').addEventListener('click',()=>{
 $('rover-map-two-d').hidden=true;stage.hidden=false;
 $('rover-view-2d').setAttribute('aria-pressed','false');$('rover-view-3d').setAttribute('aria-pressed','true');
 if(initGL())rebuildAll();
});
$('rover-3d-camera').addEventListener('change',e=>{mode=e.target.value;if(mode==='aerial')pitch=1.34;else if(mode==='orbit')pitch=.65;redraw()});
$('rover-3d-layer').addEventListener('change',e=>{surfaceLayer=e.target.value;meshStride=0;redraw()});
$('rover-3d-quality').addEventListener('change',e=>{quality=e.target.value;meshStride=0;redraw()});
$('rover-3d-vertical').addEventListener('input',e=>{vertical=Number(e.target.value);$('rover-3d-vertical-label').textContent=vertical+'×';
 target[1]=heightRange*vertical*.15;if(gl||soft)rebuildAll()});
$('rover-3d-speed').addEventListener('change',e=>{speed=Number(e.target.value)});
$('rover-3d-play').addEventListener('click',play);
$('rover-3d-restart').addEventListener('click',()=>{stop();progress=0;redraw()});
$('rover-3d-reset').addEventListener('click',()=>{yaw=-.8;pitch=mode==='aerial'?1.34:.65;radius=extent*1.35;target=[0,heightRange*vertical*.15,0];redraw()});
$('rover-3d-fullscreen').addEventListener('click',()=>{if(document.fullscreenElement)document.exitFullscreen();else stage.requestFullscreen?.()});
canvas.addEventListener('pointerdown',e=>{if(e.button!==0)return;pointer={x:e.clientX,y:e.clientY,yaw,pitch,target:target.slice(),pan:e.shiftKey};canvas.setPointerCapture(e.pointerId)});
canvas.addEventListener('pointermove',e=>{if(!pointer||mode==='follow')return;
 const dx=e.clientX-pointer.x,dy=e.clientY-pointer.y;
 if(pointer.pan){const f=radius/Math.max(320,canvas.clientHeight),c=Math.cos(yaw),s=Math.sin(yaw);
  target=[pointer.target[0]+(-dx*c-dy*s)*f,pointer.target[1],pointer.target[2]+(dx*s-dy*c)*f];}
 else{yaw=pointer.yaw-dx*.007;pitch=clamp(pointer.pitch+dy*.007,.08,1.53)}redraw();
});
canvas.addEventListener('pointerup',()=>pointer=null);canvas.addEventListener('pointercancel',()=>pointer=null);
canvas.addEventListener('wheel',e=>{e.preventDefault();radius=clamp(radius*(e.deltaY>0?1.13:.885),Math.max(terrain?.cell_size_x_m||1,3),extent*12);redraw()},{passive:false});
canvas.addEventListener('dblclick',()=>{$('rover-3d-reset').click()});
window.addEventListener('mars-rover-bridge',e=>sync(e.detail.kind));
document.querySelector('.nav button[data-view="rover"]').addEventListener('click',()=>requestAnimationFrame(()=>{if(!stage.hidden)redraw()}));
new ResizeObserver(()=>{if(!stage.hidden)redraw()}).observe(canvas);
sync('init');
window.MarsRover3DV22={getState:()=>({terrain:terrain?.id||null,routeLength:route.length,mode,quality,vertical,progress,webglAvailable:!!gl,software3D:!!soft}),reset:()=>{$('rover-3d-reset').click()}};
})();
