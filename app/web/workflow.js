/* Receiver-aware outfit effects, weapon appearance sets and apply progress. */
let effectSequence=0,progressValue=0,progressJobId=null,progressTracking=false;
const manualAssignment=new Set();
let revealDraft=null;
const characterExpansion=new Map(),weaponExpansion=new Map();
let outfitEffectSequence=0,outfitEffectSignature=null;
function currentFeatures(){return {global_reveal:revealDraft??B.features?.global_reveal??false};}
function featurePending(){return revealDraft!==null&&revealDraft!==!!B.features?.global_reveal;}
function renderFeature(){
 const pendingFeature=featurePending();$('globalReveal').checked=currentFeatures().global_reveal;$('globalReveal').disabled=!!B.busy;
 $('globalRevealStatus').textContent=(pendingFeature?'Pending · ':'Installed · ')+(currentFeatures().global_reveal?'On':'Off');
 $('featureApply').hidden=!pendingFeature;$('featureApply').disabled=!!B.busy||!buildOK;
}
function automaticOutfit(hero=Number($('hero').value)){
 const matching=s=>items[s.target].c==='outfit'&&(s.hero===hero||items[s.target].h?.includes(hero));
 return [...pending.values()].reverse().find(matching)||[...B.profile.selections].reverse().find(s=>matching(s)&&!removed.has(selectionKey(s)));
}
const originalSourceChanged=sourceChanged;
sourceChanged=async function(){
 $('outfitEffectsPanel').hidden=true;outfitEffectSignature=null;++outfitEffectSequence;const f=filters(),context=f.c==='skill'||f.c==='effect'&&f.kind==='outfit',receiver=automaticOutfit(f.hero),automatic=context&&!manualAssignment.has(f.hero)&&!!receiver;
 $('autoReceiverRow').hidden=!context;$('autoReceiver').checked=context&&!manualAssignment.has(f.hero);$('assignedOutfit').hidden=!context;
 $('assignedOutfit').textContent=receiver?'Tracked outfit: '+items[receiver.source].zh+' → '+items[receiver.target].zh:'No outfit tracked for this character. Choose a source or queue an outfit first.';
 if(automatic){if(!$('sourceSelect').querySelector(`option[value="${receiver.source}"]`)){const opt=node('option',items[receiver.source].zh);opt.value=receiver.source;$('sourceSelect').append(opt);}$('sourceSelect').value=receiver.source;}
 $('sourceHeading').textContent=automatic?'OUTFIT · AUTOMATIC ASSIGNMENT':'FROM · OWNED SOURCE';$('sourceHint').textContent=automatic?'Follows the pending or installed outfit shown above.':'Choose an item you can equip. The app does not read account ownership.';['sourceSelect','sourceQuality','sourceSearch'].forEach(id=>$(id).disabled=automatic);$('sourcePicker').classList.toggle('automatic',automatic);
 await originalSourceChanged();
};
function effectSections(host,list,kind){
 const groups=new Map();for(const i of list){const key=kind==='skill'?String(i.skill):i.kind==='outfit'?'kill':String(i.type);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(i);}
 for(const [key,ls] of groups){const first=ls[0],sk=B.catalogue.skills[key],section=node('section','','effect-group');section.dataset.slot=key;const heading=node('div','','sectiontitle');heading.append(node('h3',kind==='skill'?(sk?sk.zh+' · '+sk.en:'Extra effects'):first.ability+' · '+first.abilityEn));
 const chosen=currentEffect($('sourceSelect').value,first);heading.append(node('span',chosen?(pending.has(selectionKey(chosen))?'Pending · ':'Installed · ')+items[chosen.target].zh:'No local override'));section.append(heading);
 if(kind==='skill'&&ls.some(i=>(i._affectedSkills||[]).length>1))section.append(node('p','Linked native ability variants change together.','hint'));
 const grid=node('div','','grid'),off=node('button','No local override · 取消本地覆盖','effect-off'+(!chosen?' chosen':''));off.setAttribute('aria-pressed',String(!chosen));off.disabled=B.busy;off.onclick=()=>toggleEffect(first,true);grid.append(off);
 for(const item of ls){const active=currentEffect($('sourceSelect').value,item),selected=!!active&&sameLook(items[active.target],item),el=card(item,()=>toggleEffect(item),selected);el.setAttribute('aria-pressed',String(selected));el.disabled=B.busy;if(selected)el.append(node('span',pending.has(selectionKey(active))?'Pending ✓':'Installed ✓','selection-badge'));if(item._requiredModels?.length)el.append(node('small','Requires this native controller','restriction'));grid.append(el);}
 section.append(grid);host.append(section);}
}
const originalRenderTargets=renderTargetGrid;
renderTargetGrid=function(){
 if(filters().c!=='effect'||filters().kind!=='outfit'){originalRenderTargets();return;}
 const ls=targetCandidates(),hero=Number($('hero').value),own=ls.filter(i=>i._ownerHeroes?.includes(hero)),others=ls.filter(i=>!i._ownerHeroes?.includes(hero));$('targetGrid').classList.add('effect-groups');$('targetGrid').replaceChildren();$('moreTargets').hidden=true;$('resultCount').textContent=ls.length+' compatible defeat effects';
 for(const [title,records] of [['For '+B.catalogue.heroes.find(h=>h.id===hero).zh+' · Character effects',own],['Other compatible defeat effects',others]]){const box=node('section','','effect-collection');box.dataset.collection=records===own?'hero':'other';box.append(node('h3',title));if(records.length)effectSections(box,records,'outfit');else box.append(node('p','No character-specific defeat effect in this catalogue.','hint'));$('targetGrid').append(box);}
};
async function renderWeaponEffects(){
 const seq=++effectSequence,target=items[$('targetSelect').value],source=items[$('sourceSelect').value];$('weaponEffectsPanel').hidden=domain!=='weapon'||filters().c!=='weapon'||!target;
 if($('weaponEffectsPanel').hidden)return;$('weaponEffectsFor').textContent='For '+target.zh+' · selections are queued with this model';$('weaponEffectsGrid').replaceChildren(node('p','Checking compatible effects…','hint'));
 try{const r=await api('targets?source='+encodeURIComponent(source.key)+'&category=effect&kind=weapon&visual='+target.id);if(seq!==effectSequence)return;$('weaponEffectsGrid').replaceChildren();effectSections($('weaponEffectsGrid'),sorted(r.keys.map(k=>items[k])),'weapon');if(!r.keys.length)$('weaponEffectsGrid').append(node('p','No custom effect slots for this weapon family.','hint'));}catch(e){if(seq===effectSequence)$('weaponEffectsGrid').replaceChildren(node('p',e.message,'hint'));}
}
const originalTargetChanged=targetChanged;
targetChanged=async function(values){await originalTargetChanged(values);await Promise.all([renderWeaponEffects(),renderOutfitEffects()]);};
const originalQueue=renderQueue;
renderQueue=function(){originalQueue();const f=filters(),r=automaticOutfit(f.hero);if((f.c==='skill'||f.c==='effect'&&f.kind==='outfit')&&!manualAssignment.has(f.hero)&&r&&$('sourceSelect').value!==r.source)sourceChanged();
 const count=pending.size+removed.size+(featurePending()?1:0);$('queueCount').textContent=count;$('apply').disabled=!count||!buildOK||B.busy;$('operationLabel').textContent=count?count+' pending change'+(count===1?'':'s'):'Ready to compose';
 if(featurePending()){for(const empty of $('queueRows').querySelectorAll('.empty'))empty.remove();const row=node('div','','row feature-pending');row.append(node('strong','Reveal hidden cosmetics → '+(currentFeatures().global_reveal?'On':'Off')),node('span','Pending','tag'));const undo=node('button','Undo','quiet');undo.disabled=!!B.busy;undo.onclick=()=>{revealDraft=null;renderQueue();};row.append(undo);$('queueRows').append(row);}renderFeature();
};
const originalTreatment=renderTreatment;
renderTreatment=function(){originalTreatment();if(domain!=='character'||!['hair','outfit'].includes(filters().c))$('appearanceTreatment').hidden=true;};
function stageRemove(s){pending.delete(selectionKey(s));if(B.profile.selections.some(p=>selectionKey(p)===selectionKey(s)))removed.add(selectionKey(s));}
function stage(s){for(const old of merged())if(old.source===s.source&&overlap(items[old.target],items[s.target]))stageRemove(old);pending.set(selectionKey(s),s);removed.delete(selectionKey(s));}
async function queueBatch(selections){
 const oldP=new Map(pending),oldR=new Set(removed);try{
  for(const s of selections){const t=items[s.target];
   if(t.c==='weapon'){const valid=await api('targets?source='+encodeURIComponent(s.source)+'&category=effect&kind=weapon&visual='+t.id);for(const old of merged())if(old.source===s.source&&items[old.target].c==='effect'&&items[old.target].kind==='weapon'&&!valid.keys.includes(old.target))stageRemove(old);}
   if(t.c==='outfit'&&!manualAssignment.has(s.hero)){const oldReceiver=automaticOutfit(s.hero);if(oldReceiver&&oldReceiver.source!==s.source){const linked=merged().filter(old=>old.source===oldReceiver.source&&(items[old.target].c==='skill'||items[old.target].c==='effect'&&items[old.target].kind==='outfit'));for(const old of linked){stageRemove(old);stage({...old,source:s.source});}}}
   stage(s);
  }
  await api('validate',{selections:merged()});renderQueue();renderActive();renderTargetGrid();await Promise.all([renderWeaponEffects(),renderOutfitEffects()]);notice('Appearance set queued. Start change installs the pending profile.');
 }catch(e){pending=oldP;removed=oldR;renderQueue();renderActive();notice(e.message,true);}
}
queueSelection=s=>queueBatch([s]);
const originalToggleEffect=toggleEffect;
toggleEffect=async function(item,off=false){
 if(item.kind!=='weapon'&&!(item.kind==='outfit'&&filters().c==='outfit'))return originalToggleEffect(item,off);
 const source=$('sourceSelect').value,active=currentEffect(source,item);if(off||active&&sameLook(items[active.target],item)){await originalToggleEffect(item,true);await Promise.all([renderWeaponEffects(),renderOutfitEffects()]);return;}
 try{const model={source,target:$('targetSelect').value,hero:domain==='weapon'?null:Number($('hero').value),options:selectedOptions()};await queueBatch([model,{source,target:item.key,hero:model.hero,options:{}}]);}catch(e){notice(e.message,true);}
};
const originalEdit=editSelection;
editSelection=async function(s){if(items[s.target].c==='effect'){const category=items[s.target].kind;s=merged().find(x=>x.source===s.source&&items[x.target].c===category)||{source:s.source,target:s.source,hero:s.hero,options:{}};}await originalEdit(s);};
const originalActive=renderActive;
function installedGroup(selection){
 const item=items[selection.target]||items[selection.source];
 if(item?.c==='weapon'||item?.c==='effect'&&item.kind==='weapon')return 'weapon';
 return ['broadcast','lootpile','rescue','music'].includes(item?.c)?'environment':'character';
}
function renderInstalledGroups(container,entries){
 const groups=[['character','Characters, backgrounds & pedestals'],['weapon','Weapons'],['environment','Environment']];
 container.replaceChildren(...groups.map(([key,label])=>{
  const matching=entries.filter(entry=>installedGroup(entry.selection)===key).sort(installedCompare),section=node('section','','installed-group'),heading=node('div','','installed-group-heading'),rows=node('div','','rows');
  section.dataset.installGroup=key;section.setAttribute('aria-label',label);heading.append(node('h3',label),node('span',matching.reduce((n,entry)=>n+entry.count,0)+' changes','tag'));
  if(key==='character'&&matching.length){
   const byHero=new Map();for(const entry of matching){const s=entry.selection,a=items[s.source],t=items[s.target],id=Number(s.hero)||Number(a?.h?.length===1?a.h[0]:t?.h?.length===1?t.h[0]:0);if(!byHero.has(id))byHero.set(id,[]);byHero.get(id).push(entry);}
   const heroes=[...byHero.keys()].sort((a,b)=>heroRank(a)-heroRank(b)),preferred=heroes.includes(Number($('hero').value))?Number($('hero').value):heroes[0];
   const tools=node('div','','fold-tools');for(const [label,open] of [['Expand all',true],['Collapse all',false]]){const button=node('button',label,'quiet');button.onclick=()=>{for(const id of heroes)characterExpansion.set(id,open);for(const details of container.querySelectorAll('.character-group[data-hero]'))details.open=open;renderActive();};tools.append(button);}heading.append(tools);
   for(const id of heroes){const group=byHero.get(id),hero=B.catalogue.heroes.find(h=>Number(h.id)===id),details=node('details','','character-group'),summary=node('summary');details.dataset.hero=id;details.open=characterExpansion.has(id)?characterExpansion.get(id):id===preferred;summary.append(node('strong',hero?hero.zh+' · '+hero.en:'Shared character items'),node('span',group.reduce((n,e)=>n+e.count,0)+' changes','tag'));const content=node('div','','rows');content.append(...group.map(e=>e.element));details.append(summary,content);details.addEventListener('toggle',()=>{if(details.isConnected)characterExpansion.set(id,details.open);});rows.append(details);}
  }else if(key==='weapon'&&matching.length){
   for(const [category,label] of [[100,'Melee weapons · 近战'],[101,'Ranged weapons · 远程'],[0,'Other weapons']]){const group=matching.filter(e=>weaponOrder(e.selection).category===category);if(!group.length)continue;const fold=node('details','','character-group weapon-group'),title=node('summary');fold.dataset.weaponKind=category;fold.open=weaponExpansion.get(category)??true;title.append(node('strong',label),node('span',group.reduce((n,e)=>n+e.count,0)+' changes','tag'));const content=node('div','','rows');content.append(...group.map(e=>e.element));fold.append(title,content);fold.addEventListener('toggle',()=>{if(fold.isConnected)weaponExpansion.set(category,fold.open);});rows.append(fold);}
  }else rows.append(...matching.map(entry=>entry.element));
  if(!matching.length)rows.append(node('div','No changes installed in this group.','empty'));
  section.append(heading,rows);return section;
 }));
}
function heroRank(id){const h=B.catalogue.heroes.find(h=>Number(h.id)===id);return h?.sort??9999;}
function weaponOrder(s){const i=items[s.source],t=items[s.target],id=i?.w||t?.w;return {...(B.ordering?.weaponTypes?.[String(id)]||{category:0,sort:9999}),id};}
function installedCompare(a,b){
 const x=a.selection,y=b.selection,ix=items[x.source],iy=items[y.source],tx=items[x.target],ty=items[y.target];
 if(installedGroup(x)==='weapon'&&installedGroup(y)==='weapon'){const wx=weaponOrder(x),wy=weaponOrder(y);return (wx.category||999)-(wy.category||999)||wx.sort-wy.sort||String(ix.id).localeCompare(String(iy.id),undefined,{numeric:true});}
 const categories=['outfit','hair','accessory','grapple','voice','skill','effect','background','pose','platform','broadcast','lootpile','rescue','music'],slot=id=>{const n=B.catalogue.slots.findIndex(s=>s.id===id);return n<0?999:n;};
 return categories.indexOf(tx.c)-categories.indexOf(ty.c)||slot(ix?.s)-slot(iy?.s)||rank(ty)-rank(tx)||String(x.source).localeCompare(String(y.source),undefined,{numeric:true});
}
renderActive=function(){
 for(const details of $('managedRows').querySelectorAll('.character-group[data-hero]'))characterExpansion.set(Number(details.dataset.hero),details.open);for(const details of $('managedRows').querySelectorAll('.weapon-group'))weaponExpansion.set(Number(details.dataset.weaponKind),details.open);
 originalActive();const all=B.profile.selections,fx=all.filter(s=>items[s.target].c==='effect'),display=all.filter(s=>!fx.includes(s));for(const f of fx)if(!display.some(s=>s.source===f.source&&items[s.target].c===items[f.source].c))display.push({source:f.source,target:f.source,hero:f.hero,options:{},displayOnly:true});
 const entries=display.map(s=>{const weapon=items[s.target].c==='weapon',children=['weapon','outfit'].includes(items[s.target].c)?fx.filter(f=>f.source===s.source):[],container=node('div','','appearance-set');
 const parent=row(s,()=>{if(!s.displayOnly)stageRemove(s);children.forEach(stageRemove);renderQueue();renderActive();},removed.has(selectionKey(s))?'Removal queued':'Installed');container.dataset.source=s.source;container.dataset.target=s.target;if(weapon){container.dataset.weaponType=weaponOrder(s).id;const family=B.catalogue.weaponTypes.find(w=>w.id===Number(weaponOrder(s).id));if(family){const sub=parent.querySelector('.rowtext small');sub.textContent=family.zh+' · '+family.en+' · '+sub.textContent;}}if(s.displayOnly)parent.querySelector('.rowtext strong').textContent=items[s.source].zh+' · Native appearance with custom effects';const edit=node('button','Edit','quiet');edit.disabled=B.busy;edit.onclick=()=>editSelection(s);parent.append(edit);container.append(parent);
 for(const effect of children){const child=node('div','','weapon-property '+(i=>i.kind==='outfit'?'outfit-property':'')(items[effect.target])),i=items[effect.target];child.dataset.target=effect.target;child.append(node('span',i.ability+' · '+i.zh),node('small',removed.has(selectionKey(effect))?'Removal queued':'Installed'));const remove=node('button','Remove effect','quiet');remove.disabled=B.busy;remove.onclick=()=>{stageRemove(effect);renderQueue();renderActive();};const editEffect=node('button','Edit','quiet');editEffect.disabled=B.busy;editEffect.onclick=()=>editSelection(effect);child.append(remove,editEffect);container.append(child);}return {selection:s,element:container,count:(s.displayOnly?0:1)+children.length};});
 renderInstalledGroups($('managedRows'),entries);
 if(B.active.length)renderInstalledGroups($('baselineRows'),B.active.map(s=>({selection:s,element:row(s,null,'Imported base'),count:1})));
};
function showProgress(message){progressValue=0;progressJobId=null;progressTracking=false;$('progressBar').value=0;$('progressPercent').textContent='0%';$('progressTitle').textContent='Applying changes';$('progressMessage').textContent=message;$('progressSummary').textContent='';$('progressClose').disabled=true;if(!$('applyProgress').open)$('applyProgress').showModal();}
function renderProgress(){
 if(!$('applyProgress').open||operationStarting||!progressTracking)return;
 const job=B.job;if(!job||expectedJobId&&job.id!==expectedJobId)return;
 if(progressJobId!==job.id){progressValue=0;progressJobId=job.id;$('progressSummary').textContent='';}
 progressValue=Math.max(progressValue,Math.max(0,Math.min(job.busy?99:100,Number(job.percent)||0)));
 $('progressBar').value=progressValue;$('progressPercent').textContent=Math.floor(progressValue)+'%';$('progressMessage').textContent=job.error||job.message||'';$('progressClose').disabled=!!job.busy;
 $('progressTitle').textContent=job.busy?'Applying changes':job.error?'Change stopped':'Changes complete';
 if(!job.busy&&job.result)$('progressSummary').textContent=job.result.files+' files written · '+job.result.unchanged_files+' unchanged · '+job.result.reused_bundles+' verified bundles reused';
}
const originalStart=start;
start=async function(selections){if(B.busy||operationStarting)return false;showProgress('Validating selections and every appearance number…');const started=await originalStart(selections);if(!started){$('progressTitle').textContent='Validation stopped';$('progressMessage').textContent=$('notice').textContent;$('progressClose').disabled=false;}else{progressTracking=true;renderProgress();}return started;};
const originalPoll=poll;
poll=async function(){await originalPoll();renderProgress();};
function exclusiveAllowed(item,visual){const required=item.only?.length?item.only:(!item.copy&&!item.isDefault?item._owners:[]);return (!required?.length&&(item.copy||item.isDefault))||required?.includes(visual);}
const originalInit=init;
init=async function(){await originalInit();$('globalReveal').onchange=()=>{revealDraft=$('globalReveal').checked;renderQueue();};$('featureApply').onclick=()=>start(merged());const clear=$('clearQueue').onclick;$('clearQueue').onclick=()=>{revealDraft=null;clear();};$('refreshVisuals').onclick=()=>queueBatch(B.profile.selections.filter(s=>items[s.target].c==='weapon'));$('autoReceiver').onchange=()=>{const h=Number($('hero').value);if($('autoReceiver').checked)manualAssignment.delete(h);else manualAssignment.add(h);sourceChanged();};$('progressClose').onclick=()=>$('applyProgress').close();$('applyProgress').oncancel=e=>{if(B.busy)e.preventDefault();};renderFeature();};

async function renderOutfitEffects(){
 const target=items[$('targetSelect').value],source=items[$('sourceSelect').value];const signature=JSON.stringify([domain,filters().c,source?.key,target?.key,$('hero').value,!!B.busy,merged().filter(s=>items[s.target].c==='effect').map(s=>[s.source,s.target,pending.has(selectionKey(s))])]);if(signature===outfitEffectSignature)return;outfitEffectSignature=signature;const seq=++outfitEffectSequence;$('outfitEffectsPanel').hidden=domain!=='character'||filters().c!=='outfit'||!target||!source;
 if($('outfitEffectsPanel').hidden)return;const hero=Number($('hero').value);$('outfitEffectsFor').textContent='For '+target.zh+' · attached to '+source.zh;$('outfitEffectsGrid').replaceChildren(node('p','Checking compatible effects…','hint'));
 try{const result=await api('targets?source='+encodeURIComponent(source.key)+'&hero='+hero+'&category=effect&kind=outfit');if(seq!==outfitEffectSequence)return;const list=sorted(result.keys.map(k=>items[k])),own=list.filter(i=>i._ownerHeroes?.includes(hero)),other=list.filter(i=>!i._ownerHeroes?.includes(hero)),host=$('outfitEffectsGrid');host.replaceChildren();const personal=node('section','','effect-collection');personal.dataset.collection='hero';personal.append(node('h3','For '+B.catalogue.heroes.find(h=>h.id===hero).zh+' · Character effects'));if(own.length)effectSections(personal,own,'outfit');else personal.append(node('p','No character-specific defeat effect in this catalogue.','hint'));host.append(personal);
  if(other.length){const fold=node('details','','other-effects'),heading=node('summary','Other compatible defeat effects · '+other.length);fold.dataset.collection='other';fold.append(heading);effectSections(fold,other,'outfit');host.append(fold);}
 }catch(e){if(seq===outfitEffectSequence){outfitEffectSignature=null;$('outfitEffectsGrid').replaceChildren(node('p',e.message,'hint'));}}
}
const refreshQueueEffects=renderQueue;
renderQueue=function(){refreshQueueEffects();void renderOutfitEffects();};

let ownershipDialogState=null,ownershipEditSource=null;
const allSources=sources;
function ownershipScope(){const f=filters(),category=f.c==='effect'?f.kind:f.c==='skill'?'outfit':f.c;return category+':'+(domain==='weapon'?f.w:category==='music'?0:f.hero)+':'+(f.s||0);}
sources=function(){const list=allSources(),prefs=B.ownership||{keys:[],scopes:[]};return prefs.scopes.includes(ownershipScope())?list.filter(i=>prefs.keys.includes(i.key)||i.key===ownershipEditSource):list;};
function ownershipCandidates(){const search=$('sourceSearch').value,quality=$('sourceQuality').value;$('sourceSearch').value='';$('sourceQuality').value='';try{return allSources();}finally{$('sourceSearch').value=search;$('sourceQuality').value=quality;}}
const ownershipSourceChanged=sourceChanged;
sourceChanged=async function(){await ownershipSourceChanged();const filtered=(B.ownership?.scopes||[]).includes(ownershipScope());if(!$('sourceSelect').disabled)$('sourceHint').textContent=filtered?'Showing your marked owned items. Select owned items to update this list.':'Choose an item you can equip. Use Select owned items to save a shorter source list.';$('chooseOwned').disabled=!!B.busy;};
function openOwnership(){
 const list=ownershipCandidates(),prefs=B.ownership||{keys:[],scopes:[]};ownershipDialogState={scope:ownershipScope(),list,keys:new Set(prefs.keys),scopes:new Set(prefs.scopes)};$('ownedOnly').checked=ownershipDialogState.scopes.has(ownershipDialogState.scope)||!list.some(i=>ownershipDialogState.keys.has(i.key));$('ownedSearch').value='';$('ownedQuality').innerHTML=$('quality').innerHTML;$('ownedStatus').textContent='';renderOwnership();$('ownedDialog').showModal();
}
function visibleOwnership(){return ownershipDialogState.list.filter(i=>matches(i,Number($('ownedQuality').value),$('ownedSearch').value.trim().toLocaleLowerCase()));}
function renderOwnership(){
 const state=ownershipDialogState,list=visibleOwnership();$('ownedCount').textContent=state.list.filter(i=>state.keys.has(i.key)).length+' marked · '+list.length+' shown';$('ownedGrid').replaceChildren(...list.map(i=>{const label=node('label','','owned-card q'+rank(i)),check=node('input');check.type='checkbox';check.checked=state.keys.has(i.key);check.dataset.key=i.key;check.onchange=()=>{if(check.checked)state.keys.add(i.key);else state.keys.delete(i.key);$('ownedCount').textContent=state.list.filter(i=>state.keys.has(i.key)).length+' marked · '+visibleOwnership().length+' shown';};const image=node('div','','owned-image');image.innerHTML=icon(i);label.append(check,image,node('strong',i.zh),node('small',(i.en||'')+' · '+i.id));return label;}));
}
const originalSwitchTab=switchTab;
switchTab=function(value){originalSwitchTab(value);if(domain!=='character')return;const effect=$('category').querySelector('option[value="effect|outfit"]');if(value==='catalogue'&&!effect){const option=node('option',B.labels.effect);option.value='effect|outfit';$('category').append(option);}else if(value==='compose'&&effect){const selected=effect.selected;effect.remove();if(selected){$('category').value='outfit';void refresh();}}};
const ownershipEdit=editSelection;
editSelection=async function(s){ownershipEditSource=s.source;try{await ownershipEdit(s);}finally{ownershipEditSource=null;}};
const ownershipInit=init;
init=async function(){$('chooseOwned').onclick=openOwnership;$('ownedCancel').onclick=()=>$('ownedDialog').close();$('ownedSearch').oninput=renderOwnership;$('ownedQuality').onchange=renderOwnership;for(const [id,mark] of [['ownedMarkVisible',true],['ownedClearVisible',false]])$(id).onclick=()=>{for(const i of visibleOwnership())if(mark)ownershipDialogState.keys.add(i.key);else ownershipDialogState.keys.delete(i.key);renderOwnership();};$('ownedSave').onclick=async()=>{const s=ownershipDialogState;if($('ownedOnly').checked)s.scopes.add(s.scope);else s.scopes.delete(s.scope);$('ownedSave').disabled=true;try{B.ownership=await api('ownership',{keys:[...s.keys],scopes:[...s.scopes]});$('ownedDialog').close();await refresh();notice('Owned-item marks saved locally. Your game and pending swaps are unchanged.');}catch(e){$('ownedStatus').textContent=e.message;}finally{$('ownedSave').disabled=false;}};await ownershipInit();};

let numberPreviewSequence=0,numberPreviewTimer=null;
function renderNumberColours(data){
 $('numberColourStatus').textContent=data.numbers.join('–')+' · '+data.calculated+' calculated'+(data.endpoints_only?' · '+data.endpoints_only+' endpoints only':'');$('numberColourNote').textContent='Approximate · '+data.note;
 const groups=data.groups.map(group=>{const box=node('details','','number-colour-group');box.open=false;box.append(node('summary',group.name));const grid=node('div','','number-swatch-grid');
  for(const colour of group.colours){const card=node('div','','number-swatch'),visual=node('div','','number-swatch-visual');const values=colour.colour?[colour.colour]:[colour.start,colour.end];for(const value of values){const sample=node('span');sample.style.backgroundColor=value.hex;sample.title=value.hex;visual.append(sample);}card.append(visual,node('strong',colour.name));if(colour.colour){card.append(node('small',colour.colour.hex.toUpperCase()+(colour.hdr?' · glow ×'+colour.colour.strength:'')));}else{card.classList.add('range-only');card.append(node('small','Band endpoints · 精确颜色待验证'));}card.title=colour.status==='endpoints'?colour.method:'Calculated material colour; final rendered appearance can differ.';grid.append(card);}
  box.append(grid);return box;});$('numberColourGroups').replaceChildren(...groups);if(!groups.length)$('numberColourGroups').append(node('p','No colour rules mapped for this item.','hint'));
}
function scheduleNumberPreview(){
 clearTimeout(numberPreviewTimer);const seq=++numberPreviewSequence,target=items[$('targetSelect').value],panel=$('numberColourPreview');panel.hidden=!target?.z||!$('advancedControls').querySelector('[data-control=numbers]');if(panel.hidden){$('numberColourGroups').replaceChildren();$('numberColourModel').hidden=true;return;}
 let numbers;try{numbers=readNumbers($('advancedControls').querySelector('[data-control=numbers]'));}catch(e){$('numberColourModel').hidden=true;$('numberColourStatus').textContent='Check the slot ranges above';$('numberColourGroups').replaceChildren();$('numberColourNote').textContent='Enter a valid integer in every slot to preview colours.';return;}
 $('numberColourStatus').textContent='Updating colour palette…';$('numberColourModel').classList.add('preview-updating');$('numberColourGroups').classList.add('preview-updating');numberPreviewTimer=setTimeout(async()=>{try{const data=await api('number-preview',{target:target.key,numbers});if(seq!==numberPreviewSequence)return;renderNumberColours(data);}catch(e){if(seq!==numberPreviewSequence)return;$('numberColourModel').hidden=true;$('numberColourStatus').textContent='Preview unavailable';$('numberColourGroups').replaceChildren();$('numberColourNote').textContent=e.message;}finally{if(seq===numberPreviewSequence){$('numberColourModel').classList.remove('preview-updating');$('numberColourGroups').classList.remove('preview-updating');}}},220);
}
const colourPreviewControls=renderControls;
renderControls=function(input){colourPreviewControls(input);const fields=$('advancedControls').querySelector('[data-control=numbers]');if(fields)for(const field of fields.querySelectorAll('input'))field.addEventListener('input',scheduleNumberPreview);scheduleNumberPreview();};
const colourPreviewSourceChanged=sourceChanged;
sourceChanged=async function(){clearTimeout(numberPreviewTimer);++numberPreviewSequence;$('numberColourPreview').hidden=true;await colourPreviewSourceChanged();};

const colourPreviewTargetChanged=targetChanged;
targetChanged=async function(values){clearTimeout(numberPreviewTimer);++numberPreviewSequence;$('numberColourPreview').hidden=true;await colourPreviewTargetChanged(values);};

let numberColourSketch=null;
const detailedNumberColours=renderNumberColours;
renderNumberColours=function(data){
 detailedNumberColours(data);const item=items[data.target],family=B.catalogue.weaponTypes.find(w=>w.id===item.w);$('numberColourModel').hidden=false;
 if(!numberColourSketch)numberColourSketch=new NarakaColourSketch.Sketch($('numberColourModel'));
 numberColourSketch.set(item,data,family);
 $('numberColourStatus').textContent=data.numbers.join('–')+' · Shape & colour sketch';
 $('numberColourNote').textContent='Simplified shape and colour placement. Drag to rotate; scroll to zoom. Compare in-game for the final appearance.';
 $('numberColourDetailsTitle').textContent='Material details · 材质详情 · '+data.calculated+' calculated'+(data.endpoints_only?' · '+data.endpoints_only+' endpoints only':'');
};

init();
