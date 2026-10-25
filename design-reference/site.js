import * as THREE from '/assets/three.module.js';

const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const sections = [
 {id:'discover',label:'Discover',eyebrow:'YOUR CONTENT. REFORGED.',title:'One video.\nEndless potential.',body:'Your next great clip is already in there. Give your long-form stories a whole new life.',tags:['YOUR FOOTAGE','YOUR VOICE','YOUR NEXT CHAPTER'],scroll:1.5,linger:.15,asset:'shell',cta:{primary:{label:'Find your next clip ↗',href:'/app/'},secondary:{label:'Take a look inside',href:'#product'}}},
 {id:'moments',label:'Find the moment',eyebrow:'01 / FIND THE SPARK',title:'Get to the\ngood part.',body:'A meaningful moment. A different perspective. Shape the part that deserves a second look.',tags:['PRECISE TIMING','FOCUSED STORIES'],scroll:1.3,linger:.25,asset:'mechanism'},
 {id:'formats',label:'Make it yours',eyebrow:'02 / MADE FOR EVERY FEED',title:'Every format.\nEvery possibility.',body:'Give one story a fresh frame. Compose a clip for wherever your audience finds you.',tags:['VERTICAL','SQUARE','LANDSCAPE'],scroll:1.3,linger:.2,asset:'circuit'},
 {id:'voice',label:'Find your voice',eyebrow:'03 / KEEP WHAT MAKES IT YOU',title:'Your voice.\nFront and centre.',body:'Add your words, find your style, and let the story speak in a way only you can.',tags:['EDITABLE CAPTIONS','YOUR OWN STYLE'],scroll:1.3,linger:.3,asset:'core'},
 {id:'share',label:'Share the story',eyebrow:'04 / READY FOR WHAT’S NEXT',title:'A little moment.\nA bigger story.',body:'From one recording to your next great clip. Take the story somewhere new.',tags:[],scroll:1.5,linger:.25,asset:'reveal',cta:{primary:{label:'Open your workspace ↗',href:'/app/'},secondary:{label:'Explore the product',href:'#product'}}}
].map(s=>({...s,still:`/assets/${s.asset}-poster.webp`,clip:`/assets/vid/${s.asset}.mp4`,accent:'#4e744c'}));
const world=document.querySelector('#world');
const player=window.mountScrollWorld(world,{nav:false,atmosphere:true,hint:'Scroll to discover',crossfade:.2,sections,connectors:[]});
window.forgeWorld=player;
const firstTitle=world.querySelector('.sw-copy__title');
if(firstTitle){const h1=document.createElement('h1');h1.className=firstTitle.className;h1.innerHTML='One video.<br><em>Endless potential.</em>';firstTitle.replaceWith(h1);}
const titles=world.querySelectorAll('.sw-copy__title');
titles.forEach((title,index)=>{if(index>0){const lines=sections[index].title.split('\n');title.innerHTML=`${lines[0]}<br><em>${lines[1]}</em>`;}});
// Keep the supplied engine's blob loading, seek coalescing and mobile priming;
// composite its video frames through Three.js for the original rendering brief.
let renderer,threeScene,camera,canvas,lastSignature='',lastWidth=0,lastHeight=0,active=true;
const layers=new Map();
try{
 canvas=document.createElement('canvas');canvas.className='three-world';canvas.setAttribute('aria-hidden','true');world.append(canvas);
 renderer=new THREE.WebGLRenderer({canvas,alpha:true,antialias:false,powerPreference:'low-power'});
 renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.setClearColor(0x000000,0);
 threeScene=new THREE.Scene();camera=new THREE.OrthographicCamera(-1,1,1,-1,.1,10);camera.position.z=2;
 const loader=new THREE.TextureLoader();
 player.getState().segments.forEach((segment,index)=>{
  const texture=loader.load(segment.img.src,()=>{lastSignature='';});texture.colorSpace=THREE.NoColorSpace;texture.minFilter=THREE.LinearFilter;
  const material=new THREE.ShaderMaterial({uniforms:{map:{value:texture},opacity:{value:1}},transparent:true,depthWrite:false,vertexShader:'varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}',fragmentShader:'uniform sampler2D map;uniform float opacity;varying vec2 vUv;void main(){vec3 c=texture2D(map,vUv).rgb;float light=min(c.r,min(c.g,c.b));float a=1.0-smoothstep(0.79,0.89,light);float edge=min(min(vUv.x,1.0-vUv.x),min(vUv.y,1.0-vUv.y));gl_FragColor=vec4(c,a*smoothstep(0.0,0.025,edge)*opacity);}'});
  const mesh=new THREE.Mesh(new THREE.PlaneGeometry(1,1),material);mesh.renderOrder=index;threeScene.add(mesh);
  layers.set(segment,{mesh,poster:texture,videoTexture:null});
 });
 canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();world.classList.remove('three-ready');renderer=null;canvas.remove();});
}catch{renderer=null;if(canvas)canvas.remove();}

function renderWorld(){
 requestAnimationFrame(renderWorld);
 if(!renderer||!active||document.hidden||world.classList.contains('world-paused'))return;
 const rect=canvas.getBoundingClientRect(),width=Math.round(rect.width),height=Math.round(rect.height);if(!width||!height)return;
 const resized=width!==lastWidth||height!==lastHeight;
 if(resized){lastWidth=width;lastHeight=height;renderer.setSize(width,height,false);const a=width/height;camera.left=-a;camera.right=a;camera.updateProjectionMatrix();}
 let signature='',ready=false;
 for(const [segment,layer] of layers){
  const opacity=Number(segment.el.style.opacity)||0;
  const videoReady=segment.video?.readyState>=2 && segment.el.classList.contains('has-clip');
  if(videoReady&&!layer.videoTexture){layer.videoTexture=new THREE.VideoTexture(segment.video);layer.videoTexture.colorSpace=THREE.NoColorSpace;layer.videoTexture.minFilter=THREE.LinearFilter;layer.videoTexture.generateMipmaps=false;}
  const texture=videoReady?layer.videoTexture:layer.poster;
  layer.mesh.material.uniforms.map.value=texture;layer.mesh.material.uniforms.opacity.value=opacity;layer.mesh.visible=opacity>.001;
  layer.mesh.renderOrder=Number(segment.el.style.zIndex)||0;
  const aspect=videoReady?segment.video.videoWidth/segment.video.videoHeight:16/9;
  const fitHeight=Math.min(2,(width/height)*2/aspect);layer.mesh.scale.set(fitHeight*aspect,fitHeight,1);
  signature+=`${opacity.toFixed(3)}:${videoReady?segment.video.currentTime.toFixed(3):'p'};`;
  if(opacity>.5&&texture?.image?.width>0)ready=true;
 }
 if(signature!==lastSignature||resized){renderer.render(threeScene,camera);lastSignature=signature;if(ready)world.classList.add('three-ready');}
}
requestAnimationFrame(renderWorld);

const header=document.querySelector('.site-header'),ui=document.querySelector('.world-ui');
const chapterButtons=[...document.querySelectorAll('[data-scene]')];
const labels=['01 / THE POSSIBILITY','02 / THE MOMENT','03 / THE FORMAT','04 / THE VOICE','05 / THE NEXT CHAPTER'];
let ticking=false;
function updatePage(){
 const state=player.getState(),y=Math.max(0,scrollY-world.offsetTop),progress=Math.min(1,y/(state.totalW*state.vh));
 const bottom=world.getBoundingClientRect().bottom;active=bottom>0;
 world.classList.toggle('world-hidden',!active);document.body.classList.toggle('past-world',!active);
 const opacity=Math.max(0,Math.min(1,bottom/state.vh));
 world.querySelectorAll('.sw-sky,.sw-stage,.sw-copylayer,.three-world').forEach(el=>el.style.opacity=opacity);
 ui.style.opacity=opacity;ui.style.visibility=active?'visible':'hidden';
 header.classList.toggle('scrolled',scrollY>70);
 document.querySelector('.world-progress>span').style.transform=`scaleX(${progress})`;
 let index=0;state.sections.forEach((s,i)=>{if(y>=s._seg.start)index=i;});
 chapterButtons.forEach((button,i)=>{button.classList.toggle('active',i===index);button.setAttribute('aria-current',i===index?'step':'false');});
 document.querySelector('#world-counter').innerHTML=`${String(index+1).padStart(2,'0')} <span>/ 05</span>`;
 document.querySelector('#world-scene-label').textContent=labels[index];
 const hint=document.querySelector('.world-scroll');hint.style.opacity=Math.max(0,1-progress*8);
 ticking=false;
}
addEventListener('scroll',()=>{if(!ticking){ticking=true;requestAnimationFrame(updatePage);}},{passive:true});addEventListener('resize',updatePage,{passive:true});
chapterButtons.forEach(button=>button.addEventListener('click',()=>player.jumpTo(Number(button.dataset.scene))));
const motionButton=document.querySelector('.motion-toggle');
motionButton.addEventListener('click',()=>{const paused=!world.classList.contains('world-paused');world.classList.toggle('world-paused',paused);player.setPaused(paused);motionButton.textContent=paused?'Resume motion':'Pause motion';motionButton.setAttribute('aria-pressed',String(paused));});
if(reduceMotion){motionButton.textContent='Reduced motion';motionButton.disabled=true;}
updatePage();

const menuButton=document.querySelector('.menu-toggle');menuButton.addEventListener('click',()=>{const open=header.querySelector('nav').classList.toggle('is-open');menuButton.setAttribute('aria-expanded',String(open));menuButton.setAttribute('aria-label',open?'Close navigation':'Open navigation');});
header.querySelectorAll('nav a').forEach(a=>a.addEventListener('click',()=>{header.querySelector('nav').classList.remove('is-open');menuButton.setAttribute('aria-expanded','false');}));
const audiences={
 podcast:{tag:'LET THE CONVERSATION TRAVEL',title:'Your best conversations<br>deserve a second life.',body:'Turn a thoughtful exchange into a focused clip. Keep the context, refine the captions, and give new listeners a reason to tune in.',image:'circuit'},
 creator:{tag:'KEEP YOUR CREATIVE MOMENTUM',title:'One recording.<br>A fresh way to tell it.',body:'Give an idea another angle. Build a clip around your strongest moment, add your own treatment, and make it feel like you.',image:'shell'},
 team:{tag:'GIVE YOUR CONTENT A COMMON HOME',title:'A clearer workflow.<br>A stronger shared story.',body:'Bring your footage into one focused workspace. Connect your existing services and shape a repeatable approach to your next edit.',image:'mechanism'},
 educator:{tag:'MAKE THE TAKEAWAY STICK',title:'A smaller lesson.<br>A lasting impression.',body:'Find a useful explanation inside a longer recording. Frame it clearly, caption the key words, and share a focused takeaway.',image:'core'}
};
document.querySelectorAll('[data-audience]').forEach(button=>button.addEventListener('click',()=>{const data=audiences[button.dataset.audience];document.querySelectorAll('[data-audience]').forEach(b=>{b.setAttribute('aria-selected',String(b===button));b.tabIndex=b===button?0:-1;});document.querySelector('#audience-tag').textContent=data.tag;document.querySelector('#audience-title').innerHTML=data.title;document.querySelector('#audience-body').textContent=data.body;document.querySelector('#audience-image').src=`/assets/${data.image}.webp`;}));
document.querySelector('.audience-tabs').addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const tabs=[...event.currentTarget.querySelectorAll('button')];let i=tabs.indexOf(document.activeElement);i=event.key==='Home'?0:event.key==='End'?tabs.length-1:(i+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;tabs[i].click();tabs[i].focus();});

const mediaDialog=document.querySelector('#media-dialog');document.querySelector('[data-play-sample]').addEventListener('click',()=>{mediaDialog.showModal();const v=mediaDialog.querySelector('video');if(!v.getAttribute('src'))v.src=v.dataset.src;v.play().catch(()=>{});});mediaDialog.addEventListener('close',()=>mediaDialog.querySelector('video').pause());
document.querySelectorAll('.dialog-close').forEach(button=>button.addEventListener('click',()=>button.closest('dialog').close()));
document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}}));
const legal={privacy:`<h2>Privacy at ForgeClip</h2><p>Local editing uses files selected on your device. Your video is not sent to a server merely by opening it in the browser editor.</p><h3>Cloud actions</h3><p>When you choose to upload, transcribe or process a project with a connected backend, the selected files and project details are sent to that service. Its configured storage and processing providers handle those actions.</p><h3>Your device</h3><p>Project metadata, editing preferences and optional local video copies may be stored in this browser. You can delete local projects from the workspace. Browser data does not automatically sync across devices.</p><h3>Accounts and billing</h3><p>Authentication and payment details are handled by the connected backend and billing provider. Connection and service availability are displayed in the workspace.</p>`,terms:`<h2>Using ForgeClip</h2><p>Upload and edit footage you have permission to use. You retain responsibility for the content you create and share.</p><h3>Available services</h3><p>Browser editing is available without an AI-processing account. Automated transcription, highlights, cloud processing and subscriptions depend on the services connected to your workspace.</p><h3>Review your results</h3><p>Review captions, timing, framing and any AI suggestions before exporting or publishing. Results may require correction.</p><h3>Payments</h3><p>Available subscriptions, prices and payment terms are shown by the connected billing service before checkout.</p>`};
document.querySelectorAll('[data-legal]').forEach(button=>button.addEventListener('click',()=>{document.querySelector('#legal-content').innerHTML=legal[button.dataset.legal];document.querySelector('#legal-dialog').showModal();}));
// Use SVG arrows so directional controls render consistently across platforms.
document.querySelectorAll('.button>span,.text-link>span').forEach(span=>{if(['↗','→'].includes(span.textContent.trim()))span.innerHTML='<svg class="icon-arrow" viewBox="0 0 14 14" aria-hidden="true"><path d="M3 11 11 3M3 3h8v8"/></svg>';});
document.querySelector('#year').textContent=new Date().getFullYear();
