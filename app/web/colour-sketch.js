/* Lightweight, deliberately schematic models. No game assets or live hooks.
 * Three.js r147 and OrbitControls are the existing catalogue's MIT-licensed copies.
 * Material region placement/area is illustrative; this is not a shader port.
 */
(()=>{
 'use strict';
 const T=THREE,make=(tag,text='',cls='')=>{const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e;};
 const NEUTRAL='#788595';
 function role(name,weapon){
  if(/通用|基础属性|^基础$/.test(name))return 'common';
  if(/特效|火焰|燃烧|流光|星云|流沙|水纹|气流/.test(name))return 'effect';
  if(weapon){
   if(/刀柄|剑柄|扇柄|根系|树干|棍身|枪杆/.test(name))return 'handle';
   if(/剑鞘|刀鞘/.test(name))return 'sheath';
   if(/刀刃|剑刃|枪头|飞刀/.test(name))return 'edge';
   if(/磨损/.test(name))return 'wear';
   if(/弦|连线|龙筋/.test(name))return 'string';
   if(/羽毛|副翼|鸟翼/.test(name))return 'feather';
   if(/扇面/.test(name))return 'fan';
   if(/弓身|刀身|刀背|外壳|树枝|鱼飞船/.test(name))return 'body';
   return 'trim';
  }
  if(/翅膀|光翼/.test(name))return 'wings';
  if(/尾巴/.test(name))return 'tail';
  if(/丝袜|袜子/.test(name))return 'stockings';
  if(/裤子|底裤/.test(name))return 'trousers';
  if(/鞋/.test(name)&&!/领结/.test(name))return 'shoes';
  if(/袖/.test(name))return 'sleeves';
  if(/飘带|丝带/.test(name))return 'ribbons';
  if(/系带|腰带/.test(name))return 'belt';
  if(/外袍|上衣外|外壳/.test(name))return 'coat';
  if(/裙/.test(name))return 'skirt';
  if(/眼罩|头发|兽头|兽角/.test(name))return 'head';
  if(/抹胸|内衣|上衣|衣服|盔甲|铠甲|内构/.test(name))return 'top';
  if(/皮肤|纹身|兽身/.test(name))return 'skin';
  return 'trim';
 }
 function analyse(item,data,family){
  const weapon=item.c==='weapon';
  const parts=data.groups.map(group=>{
   const kind=role(group.name,weapon),base=group.colours.filter(c=>!c.hdr&&!/SSS|透光|自发光|常量/.test(c.name));
   const source=base.length?base:kind==='effect'?group.colours.filter(c=>!c.colour||c.colour.strength!==0):[];
   const entries=source.slice(0,4).map(c=>({hex:c.colour?.hex||NEUTRAL,uncertain:!c.colour,name:c.name}));
   return {name:group.name.replace(/变色|异变|材质/g,''),nativeName:group.name,role:kind,colours:entries,uncertain:entries.some(c=>c.uncertain)};
  }).filter(p=>p.role!=='common'&&p.colours.length);
  if(!parts.length)parts.push({name:'Appearance',nativeName:'Appearance',role:weapon?'body':'top',colours:[{hex:NEUTRAL,uncertain:true}],uncertain:true});
  return {weapon,family:family?.en||'',familyZh:family?.zh||'',parts};
 }
 class Sketch {
  constructor(host){
   this.host=host;this.model=null;this.key=null;this.meshCount=0;this.renderCount=0;
   this.wrap=make('div','','colour-sketch-layout');this.stage=make('div','','colour-sketch-stage');this.stage.setAttribute('aria-label','Approximate coloured model; drag to rotate');
   const tools=make('div','','colour-sketch-tools');this.caption=make('span','','tag');const reset=make('button','Reset view · 重置视角','quiet');reset.type='button';reset.onclick=()=>this.home();tools.append(this.caption,reset);
   this.legend=make('div','','colour-sketch-legend');this.wrap.append(this.stage,this.legend);host.append(tools,this.wrap);
   this.scene=new T.Scene();this.scene.background=new T.Color('#101a28');this.camera=new T.PerspectiveCamera(34,1,.01,100);
   try{this.renderer=new T.WebGLRenderer({antialias:true,alpha:false,preserveDrawingBuffer:true});this.renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.5));this.renderer.outputEncoding=T.sRGBEncoding;this.renderer.toneMapping=T.NoToneMapping;this.stage.append(this.renderer.domElement);}
   catch(error){this.renderer=null;this.stage.append(make('p','3D unavailable on this display. The colour placement diagram is shown instead.','hint'));this.fallback=make('canvas');this.fallback.width=650;this.fallback.height=580;this.stage.append(this.fallback);}
   this.scene.add(new T.HemisphereLight(0xffffff,0x60738c,1.15));const light=new T.DirectionalLight(0xffffff,.8);light.position.set(3,5,5);this.scene.add(light);const back=new T.DirectionalLight(0xbad4ff,.35);back.position.set(-3,2,-3);this.scene.add(back);
   if(this.renderer){this.controls=new T.OrbitControls(this.camera,this.renderer.domElement);this.controls.enablePan=false;this.controls.minDistance=2;this.controls.maxDistance=10;this.controls.addEventListener('change',()=>this.render());}
   this.observer=new ResizeObserver(()=>this.resize());this.observer.observe(this.stage);
  }
  material(part,plain=false){
   const colours=(part?.colours?.length?part.colours:[{hex:NEUTRAL}]).map(c=>c.hex),width=96,bytes=new Uint8Array(width*4);
   for(let x=0;x<width;x++){const pos=x/(width-1)*Math.max(0,colours.length-1),i=Math.floor(pos),f=pos-i,a=new T.Color(colours[i]),b=new T.Color(colours[Math.min(i+1,colours.length-1)]);a.lerp(b,f);bytes.set([Math.round(a.r*255),Math.round(a.g*255),Math.round(a.b*255),255],4*x);}
   const texture=new T.DataTexture(bytes,width,1,T.RGBAFormat);texture.encoding=T.sRGBEncoding;texture.minFilter=texture.magFilter=T.LinearFilter;texture.needsUpdate=true;
   const material=new T.MeshStandardMaterial({map:texture,color:0xffffff,roughness:plain ? .8 : .64,metalness:plain?0:.12,side:T.DoubleSide});
   material.userData.part=part?.name||'Neutral';return material;
  }
  solid(hex){return new T.MeshStandardMaterial({color:new T.Color(hex).convertSRGBToLinear(),roughness:.8,metalness:0});}
  mesh(geometry,material,x=0,y=0,z=0,rz=0){const uv=geometry.attributes.uv,pos=geometry.attributes.position;if(uv&&pos){geometry.computeBoundingBox();const lo=geometry.boundingBox.min.x,span=geometry.boundingBox.max.x-lo;if(span>1e-6){for(let i=0;i<uv.count;i++)uv.setX(i,(pos.getX(i)-lo)/span);uv.needsUpdate=true;}}const m=new T.Mesh(geometry,material);m.position.set(x,y,z);m.rotation.z=rz;this.model.add(m);this.meshCount++;return m;}
  box(w,h,d,mat,x=0,y=0,z=0,rz=0){return this.mesh(new T.BoxGeometry(w,h,d),mat,x,y,z,rz);}
  cylinder(top,bottom,h,mat,x=0,y=0,z=0,rz=0){return this.mesh(new T.CylinderGeometry(top,bottom,h,20,1),mat,x,y,z,rz);}
  ball(r,mat,x,y,z,sx=1,sy=1,sz=1){const m=this.mesh(new T.SphereGeometry(r,16,10),mat,x,y,z);m.scale.set(sx,sy,sz);return m;}
  line(points,radius,mat){const curve=new T.CatmullRomCurve3(points.map(v=>new T.Vector3(...v)));return this.mesh(new T.TubeGeometry(curve,32,radius,7,false),mat);}
  polygon(points,depth,mat,x=0,y=0,z=0,rz=0){const shape=new T.Shape();shape.moveTo(...points[0]);for(const pt of points.slice(1))shape.lineTo(...pt);shape.closePath();const mesh=this.mesh(new T.ExtrudeGeometry(shape,{depth,bevelEnabled:true,bevelThickness:.014,bevelSize:.015,bevelSegments:1}),mat,x,y,z-depth/2,rz);return mesh;}
  part(analysis,roles,fallback){return roles.map(r=>analysis.parts.find(p=>p.role===r)).find(Boolean)||fallback||analysis.parts.find(p=>p.role!=='effect')||analysis.parts[0];}
  outfit(a){
   const p=roles=>this.part(a,roles),mat=roles=>this.material(p(roles),true),has=role=>a.parts.some(p=>p.role===role),neutral=this.solid('#84929f');
   this.ball(.19,neutral,0,2.08,0,.85,1.15,.87);this.cylinder(.09,.1,.15,neutral,0,1.88); // neutral mannequin
   this.cylinder(.31,.22,.55,mat(['top','coat']),0,1.57,0);this.cylinder(.22,.29,.25,mat(['belt','top']),0,1.18,0);
   for(const sign of [-1,1]){
    this.cylinder(.105,.085,.51,has('sleeves')?mat(['sleeves']):neutral,sign*.40,1.48,0,sign*.26);this.cylinder(.073,.052,.43,neutral,sign*.49,1.04,0,sign*.10);this.ball(.065,neutral,sign*.51,.79,.01,.8,1.2,.8);
    const legs=has('trousers')?mat(['trousers']):has('stockings')?mat(['stockings']):neutral;this.cylinder(.116,.075,.72,legs,sign*.145,.56,0);this.box(.16,.12,.31,has('shoes')?mat(['shoes']):this.solid('#536273'),sign*.145,.11,.065);
   }
   if(has('skirt')){
    const skirts=a.parts.filter(p=>p.role==='skirt'),main=skirts.find(p=>!/[内|纱|摆]/.test(p.name))||skirts[0];this.cylinder(.26,.52,.73,this.material(main,true),0,.88);
    if(skirts.length>1)this.cylinder(.45,.54,.19,this.material(skirts[skirts.length-1],true),0,.58,.005);
   }
   if(has('coat')){const m=mat(['coat']);for(const sign of [-1,1])this.polygon([[0,.6],[sign*.27,.52],[sign*.39,-.46],[sign*.05,-.36]],.035,m,sign*.19,1.1,-.11);}
   if(has('belt')||has('trim'))this.cylinder(.238,.24,.075,mat(['belt','trim']),0,1.28,.005);
   if(has('ribbons')){const m=mat(['ribbons']);for(const sign of [-1,1])this.line([[sign*.31,1.65,-.06],[sign*.69,1.42,-.03],[sign*.74,.85,.04],[sign*.43,.37,.08]],.045,m);}
   if(has('wings')){const m=mat(['wings']);for(const sign of [-1,1])this.polygon([[0,0],[sign*.72,.53],[sign*.61,-.10],[sign*.31,-.31]],.025,m,sign*.19,1.58,-.18);}
   if(has('tail'))this.line([[0,1,-.15],[.45,.82,-.4],[.68,.4,-.22],[.48,.2,.13]],.10,mat(['tail']));
   const trim=a.parts.filter(p=>p.role==='trim');for(let i=0;i<Math.min(trim.length,5);i++){const angle=(i/(Math.max(1,trim.length-1))-.5)*1.8;this.ball(.055,this.material(trim[i]),Math.sin(angle)*.31,1.36+((i%2)*.27),.22);}
   if(has('head')){this.box(.29,.075,.12,mat(['head']),0,2.1,.16);}
  }
  blade(a,{wide=false,short=false,curved=false,dual=false}={}){
   const main=this.material(this.part(a,['body','edge'])),edge=this.material(this.part(a,['edge','body'])),handle=this.material(this.part(a,['handle'])),trim=this.material(this.part(a,['trim']));
   const sword=(x,angle)=>{const root=new T.Group(),old=this.model;old.add(root);this.model=root;const h=short?1.20:1.95,w=wide ? .30 : .14;
    this.polygon([[-w/2,0],[-w*.6,h*.75],[curved?w*.3:0,h],[w*.9,h*.72],[w/2,0]],.07,main,x,.02,0,angle);
    this.polygon([[0,0],[w*.55,0],[w*.92,h*.72],[curved?w*.3:0,h],[0,h*.72]],.075,edge,x,.02,.002,angle);
    this.box(wide ? .48 : .40,.08,.13,trim,x,-.02,.015,angle);this.cylinder(.055,.055,.43,handle,x,-.27,0,angle);this.ball(.067,trim,x,-.51,0);this.model=old;root.rotation.z=angle;root.position.x=x;};
   if(dual){sword(-.26,-.20);sword(.26,.20);}else sword(0,-.18);
   if(a.parts.some(p=>p.role==='sheath'))this.box(.18,1.55,.11,this.material(this.part(a,['sheath'])),.53,.55,-.14,-.18);
  }
  weapon(a){
   const en=a.family.toLowerCase(),zh=a.familyZh,main=this.material(this.part(a,['body','edge','fan'])),edge=this.material(this.part(a,['edge','body'])),handle=this.material(this.part(a,['handle'])),trim=this.material(this.part(a,['trim','feather']));
   if(/弓|bow/.test(zh+' '+en)){
    this.line([[.22,-1.02,0],[-.30,-.70,0],[-.52,0,0],[-.30,.70,0],[.22,1.02,0]],.085,main);this.line([[.22,-1.02,0],[.16,0,0],[.22,1.02,0]],.009,this.material(this.part(a,['string'])));this.cylinder(.10,.10,.30,handle,-.50,0);this.line([[-.7,0,0],[.65,0,0]],.016,trim);this.polygon([[.55,-.06],[.78,0],[.55,.06]],.03,edge);return;
   }
   if(/枪|spear/.test(zh+' '+en)&&!/铳|炮/.test(zh)){this.cylinder(.045,.045,2.1,handle,0,.1);this.polygon([[0,1.74],[-.18,1.13],[-.055,.88],[.055,.88],[.18,1.13]],.07,edge);this.cylinder(.09,.07,.18,trim,0,.93);return;}
   if(/^棍$|staff/.test(zh+' '+en)){this.cylinder(.052,.052,2.70,handle,0,.20);this.ball(.17,trim,0,1.63,0);this.line([[0,1.25,0],[-.34,1.40,0],[-.45,1.70,0]],.045,main);this.line([[0,1.10,0],[.31,1.35,0],[.47,1.57,0]],.042,main);return;}
   if(/扇|fan/.test(zh+' '+en)){for(let i=0;i<11;i++){const angle=-1.18+i*.236;this.polygon([[0,0],[Math.sin(angle)*1.12,Math.cos(angle)*1.12],[Math.sin(angle+.236)*1.12,Math.cos(angle+.236)*1.12]],.03,main,0,-.5);this.line([[0,-.5,.03],[Math.sin(angle)*1.13,Math.cos(angle)*1.13-.5,.03]],.012,handle);}this.ball(.10,trim,0,-.49,.025);return;}
   if(/炮|cannon/.test(zh+' '+en)){const m=this.cylinder(.20,.28,1.65,main,0,.2);m.rotation.z=-.45;this.cylinder(.24,.24,.16,trim,.37,.94);this.box(.50,.22,.40,handle,-.20,-.62);return;}
   if(/双节|nunchuck/.test(zh+' '+en)){for(const sign of [-1,1])this.cylinder(.08,.08,1.04,handle,sign*.37,.1,0,sign*.16);this.line([[-.45,.62,0],[0,.83,0],[.45,.62,0]],.021,trim);return;}
   if(/飞刀|throwing/.test(zh+' '+en)){for(const x of [-.52,0,.52]){this.polygon([[-.09,0],[0,1.05],[.12,.12],[.07,-.17],[-.07,-.17]],.06,edge,x,0,0,x*.45);this.box(.10,.30,.09,handle,x,-.31);}return;}
   this.blade(a,{wide:/阔刀|greatsword|斩马|polesword/.test(zh+' '+en),short:/匕首|dagger|双刀|dual/.test(zh+' '+en),curved:/太刀|katana|横刀|heng/.test(zh+' '+en),dual:/双刀|dual/.test(zh+' '+en)});
  }
  set(item,data,family){
   const a=analyse(item,data,family);this.analysis=a;this.host.dataset.target=item.key;this.host.dataset.partCount=a.parts.length;
   if(this.model){this.scene.remove(this.model);const mats=new Set(),geos=new Set();this.model.traverse(o=>{if(o.geometry)geos.add(o.geometry);if(o.material)mats.add(o.material);});for(const g of geos)g.dispose();for(const m of mats){m.map?.dispose();m.dispose();}}
   this.model=new T.Group();this.meshCount=0;this.scene.add(this.model);if(a.weapon)this.weapon(a);else this.outfit(a);
   // Normalize every family to the same view and preserve the orbit on colour edits.
   this.model.updateMatrixWorld(true);const box=new T.Box3().setFromObject(this.model),size=box.getSize(new T.Vector3()),centre=box.getCenter(new T.Vector3());this.model.position.sub(centre);const scale=2.6/Math.max(size.x,size.y,size.z,.01);this.model.scale.setScalar(scale);this.model.position.multiplyScalar(scale);
   this.caption.textContent=item.zh+' · Abstract shape · 形色示意';this.legend.replaceChildren(make('h4','Colours by part · 部位配色'));
   const order=['top','body','edge','skirt','trousers','coat','stockings','sleeves','wings','handle','sheath','ribbons','belt','trim','shoes','skin','head','tail','fan','feather','string','wear','effect'];
   const sorted=[...a.parts].sort((x,y)=>order.indexOf(x.role)-order.indexOf(y.role));
   for(const part of sorted){const row=make('div','','sketch-part'),colours=make('div','','sketch-part-colours');row.append(make('span',part.name));for(const c of part.colours){const dot=make('i');dot.style.backgroundColor=c.hex;dot.title=c.uncertain?'Unresolved: neutral placeholder':c.hex;if(c.uncertain)dot.className='unresolved';colours.append(dot);}row.append(colours);this.legend.append(row);}
   this.legend.append(make('p','Region sizes and colour placement are illustrative. Glow and shape-slot geometry are not reproduced.','hint'));
   this.fallbackDraw(a);if(this.key!==item.key){this.key=item.key;this.home();}this.resize();this.render();
  }
  fallbackDraw(a){if(!this.fallback)return;const c=this.fallback.getContext('2d');c.clearRect(0,0,650,580);c.fillStyle='#101a28';c.fillRect(0,0,650,580);const colour=roles=>this.part(a,roles).colours[0]?.hex||NEUTRAL;
   c.strokeStyle='#94a4b7';c.lineWidth=2;if(a.weapon){c.save();c.translate(330,300);c.rotate(.25);c.fillStyle=colour(['body','edge']);c.beginPath();c.moveTo(-35,120);c.lineTo(-45,-170);c.lineTo(0,-240);c.lineTo(45,-170);c.lineTo(35,120);c.closePath();c.fill();c.stroke();c.fillStyle=colour(['handle']);c.fillRect(-14,120,28,100);c.fillStyle=colour(['trim']);c.fillRect(-75,110,150,15);c.restore();}else{c.fillStyle=NEUTRAL;c.beginPath();c.arc(325,92,35,0,Math.PI*2);c.fill();c.fillRect(245,165,32,210);c.fillRect(375,165,32,210);c.fillStyle=colour(['stockings','trousers']);c.fillRect(283,340,35,170);c.fillRect(333,340,35,170);c.fillStyle=colour(['top','coat']);c.fillRect(277,140,95,150);c.fillStyle=colour(['skirt','trousers']);c.beginPath();c.moveTo(277,270);c.lineTo(373,270);c.lineTo(420,410);c.lineTo(230,410);c.closePath();c.fill();} }
  home(){this.camera.position.set(0,.20,5.1);this.camera.lookAt(0,0,0);if(this.controls){this.controls.target.set(0,0,0);this.controls.update();}this.render();}
  resize(){if(!this.renderer)return;const w=this.stage.clientWidth,h=this.stage.clientHeight;if(!w||!h)return;this.camera.aspect=w/h;this.camera.updateProjectionMatrix();this.renderer.setSize(w,h,false);this.render();}
  render(){if(this.renderer&&this.model){this.renderer.render(this.scene,this.camera);this.renderCount++;}}
 }
 window.NarakaColourSketch={Sketch,analyse};
})();
