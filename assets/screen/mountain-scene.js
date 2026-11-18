import {sites} from './farm-landscape.js';

const clamp = (v,min,max) => Math.max(min, Math.min(max,v));
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const panorama=document.getElementById('panorama');
const findings = new Map(sites.map(site => [site.id, new Map()]));
const names={blade:'叶片',hub:'轮毂',nacelle:'机舱',tower:'塔筒',foundation:'基础',unknown:'待定位'};
const stations=document.getElementById('stations');
const template=document.getElementById('turbine');
const photoAspect = 1672 / 941;
let selected='',view='overview';
let gpu=null,gpuActive=false,angle=.12,visible=true,frameDirty=true,lastTick=0;

function notify(type, data={}) {
  if (parent!==window) parent.postMessage({type,...data},location.origin);
}
const stationsById=new Map();
for (const site of sites) {
  const station=template.content.firstElementChild.cloneNode(true);
  station.dataset.unit=site.id;
  const button=station.querySelector('button');
  button.textContent=site.id;
  button.addEventListener('click',()=>choose(site.id));
  stations.append(station);
  stationsById.set(site.id,{station,button,caption:station.querySelector('.part-caption'),
    svg:station.querySelector('svg'),rotor:station.querySelector('[data-part=blade]')});
}

function mark() {
  for (const [id,{station,button,caption,svg}] of stationsById) {
    const parts = findings.get(id);
    const damaged = [], clear = [];
    for (const [part, status] of parts) {
      (status === 'damaged' ? damaged : clear).push(names[part]);
    }
    station.toggleAttribute('data-alert', damaged.length > 0);
    station.toggleAttribute('data-clear', !damaged.length && clear.length > 0);
    button.setAttribute('aria-pressed',String(id===selected));
    const damageLabel = damaged.length ? '检出病害 · ' + damaged.join('、') : '';
    const clearLabel = clear.length ? '未见病害 · ' + clear.join('、') : '';
    caption.textContent = damaged.length ? damaged.join('、') : clearLabel;
    button.title = [id, damageLabel, clearLabel].filter(Boolean).join(' · ');
    button.setAttribute('aria-label','选择 '+button.title);
    for (const item of svg.querySelectorAll('[data-part]')) {
      const status = parts.get(item.dataset.part);
      item.classList.toggle('fault', status === 'damaged');
      item.classList.toggle('clear', status === 'clear');
    }
  }
  gpu?.mark(findings);
  frameDirty=true;
}

function layout() {
  const width = innerWidth;
  const height = innerHeight;
  if (!width || !height) return;
  const focused = view === 'turbine' && Boolean(selected);
  document.body.dataset.view = view;
  const site = sites.find(item => item.id === selected);
  // A centred 1.12× cover crop is the original mountain overview framing.
  const coverWidth = Math.max(width, height * photoAspect);
  const targetScreenY = height * (focused ? .78 : .5);
  // Keep the selected site centred even at the limits of the panorama crop.
  const photoWidth = focused ? Math.max(coverWidth * 1.36,
    width / (2 * Math.min(site.x, 1 - site.x)),
    photoAspect * targetScreenY / site.y,
    photoAspect * (height - targetScreenY) / (1 - site.y)) : coverWidth * 1.12;
  const photoHeight = photoWidth / photoAspect;
  const targetX = focused ? site.x : .5;
  const targetY = focused ? site.y : .5;
  const originX = width / 2 - targetX * photoWidth;
  const originY = targetScreenY - targetY * photoHeight;
  const left = clamp(originX, width - photoWidth, 0);
  const top = clamp(originY, height - photoHeight, 0);
  panorama.style.backgroundSize = photoWidth + 'px ' + photoHeight + 'px';
  panorama.style.backgroundPosition = left + 'px ' + top + 'px';

  const placements = sites.map(turbine => {
    const x = left + turbine.x * photoWidth;
    const y = top + turbine.y * photoHeight;
    let towerHeight = turbine.height * photoHeight;
    if (focused && turbine.id === selected) {
      // Use a consistent inspection scale for near and distant turbines.
      towerHeight = Math.min(height * .68, width * .90);
    }
    const visible = (!focused || turbine.id === selected) &&
      x > -towerHeight / 2 && x < width + towerHeight / 2 && y > 0 && y - towerHeight < height;
    const {station, svg} = stationsById.get(turbine.id);
    station.hidden = !visible;
    station.style.transform = 'translate(' + x + 'px,' + y + 'px)';
    station.style.setProperty('--foot-x', x + 'px');
    // On wide, shallow screens the tower can extend below the photo crop or behind the view switch.
    const tagTop = Math.min(y + 3, height - 60);
    station.style.setProperty('--tag-offset', (tagTop - y) + 'px');
    station.style.zIndex = String(Math.round(turbine.y * 100));
    station.style.setProperty('--model-height', towerHeight + 'px');
    svg.style.width = svg.style.height = towerHeight + 'px';
    return {id: turbine.id, x, y, height: towerHeight, visible};
  });

  if (gpuActive) gpu.frame({width, height, placements: placements.sort((a, b) => a.y - b.y)});
  frameDirty = true;
}
function choose(id) {
  if (!findings.has(id)) return;
  selected=id;mark();layout();
  notify('wd:select',{id});
}

addEventListener('message',e=>{
  if (e.source!==parent||e.origin!==location.origin) return;
  const msg=e.data||{};
  if (msg.type==='wd:farm') {
    if (!Array.isArray(msg.units)) return;
    for (const parts of findings.values()) parts.clear();
    for (const unit of msg.units) {
      const parts = findings.get(unit?.id);
      if (!parts || !Array.isArray(unit.parts)) continue;
      if (Array.isArray(unit.clearParts)) {
        for (const part of unit.clearParts) {
          if (Object.hasOwn(names, part) && !parts.has(part)) parts.set(part, 'clear');
        }
      }
      for (const part of unit.parts) {
        if (Object.hasOwn(names, part)) parts.set(part, 'damaged');
      }
    }
    selected = findings.has(msg.selected) ? msg.selected : '';
    mark();
    layout();
  } else if (msg.type==='wd:view'&&['overview','turbine'].includes(msg.view)) {
    view=msg.view;layout();
  }
});

document.body.addEventListener('click',e=>{
  if(e.target.closest('button')) return;
  const hit=e.target.closest('.station')?.dataset.unit || (gpuActive&&gpu.pick(e.clientX,e.clientY));
  if (hit) choose(hit);
});
addEventListener('resize',layout);
function draw(t) {
  requestAnimationFrame(draw);
  if(document.hidden || !visible || t-lastTick<48 || (reducedMotion.matches&&!frameDirty)) return;
  if(!reducedMotion.matches) angle+=Math.min(.08,(t-lastTick)/1000)*.16;
  lastTick=t;
  if(gpuActive) gpu.draw(angle);
  else sites.forEach((site,i)=>stationsById.get(site.id).rotor.setAttribute('transform','rotate('+(-(angle+(i-2)*.78)*180/Math.PI)+')'));
  frameDirty=false;
}
new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;}).observe(document.body);
mark();layout();requestAnimationFrame(draw);
notify('wd:ready',{mode:'schematic'});

// The interactive projected site remains available throughout startup and after context loss.
async function enableWebGL() {
  const canvas=document.createElement('canvas');
  const gl=canvas.getContext('webgl2',{alpha:true,antialias:true,powerPreference:'low-power'});
  if (!gl) return;
  const [THREE, {buildFarmRenderer}]=await Promise.all([import('/wd-assets/vendor/three/three.module.js'),import('./mountain-renderer.js')]);
  gpu=buildFarmRenderer(THREE,canvas,gl);
  canvas.className='models';canvas.setAttribute('aria-hidden','true');
  canvas.addEventListener('webglcontextlost',e=>{
    e.preventDefault();gpuActive=false;canvas.hidden=true;
    document.body.classList.remove('gpu');layout();notify('wd:ready',{mode:'schematic'});
  });
  function activate() {
    gpuActive=true;gpu.mark(findings);layout();gpu.draw(angle);
    canvas.hidden=false;document.body.classList.add('gpu');notify('wd:ready',{mode:'3d'});
  }
  canvas.addEventListener('webglcontextrestored',activate);
  panorama.after(canvas);activate();
}
enableWebGL().catch(()=>{
  gpuActive=false;document.body.classList.remove('gpu');layout();
});
