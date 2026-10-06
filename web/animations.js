'use strict';
window.GameAnimation = (() => {
  let code = null, lastId = 0, ready = false, layer = null, timer = null;
  const active = new Set();
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const key = ref => !ref ? '' : `p${ref.player}:${ref.unit ? 'u'+ref.unit : ref.hand != null ? 'h'+ref.hand : 'hero'}`;
  function snapshot() {
    const nodes = new Map();
    document.querySelectorAll('#app [data-fx-key]').forEach(node => {
      const rect = node.getBoundingClientRect();
      if (rect.width && rect.height) nodes.set(node.dataset.fxKey,{node,rect});
    });
    return nodes;
  }
  function clear() {
    clearTimeout(timer);
    for (const animation of active) animation.cancel();
    active.clear(); layer?.remove(); layer=null;
  }
  function animate(node, frames, options={}) {
    if (!node?.animate) return;
    const animation = node.animate(frames,{duration:360,easing:'ease-out',...options});
    active.add(animation);
    animation.onfinish = () => active.delete(animation);
  }
  function prepare(room) {
    if (!room || !['active','finished'].includes(room.phase)) {
      code=null;lastId=0;ready=false;clear();return null;
    }
    const events=room.visual_events || [];
    const latest=events.reduce((n,e)=>Math.max(n,e.id),0);
    if (!ready || code !== room.code) {code=room.code;lastId=latest;ready=true;return null;}
    const fresh=events.filter(e=>e.id>lastId);
    lastId=Math.max(lastId,latest);
    if (!fresh.length || document.hidden) return null;
    const event=fresh[fresh.length-1];
    const age=Date.now()/1000-event.at;
    if (age>=10 || age < -30) return null;
    return {event,old:snapshot()};
  }
  function position(node,rect) {
    Object.assign(node.style,{left:`${rect.left}px`,top:`${rect.top}px`,width:`${rect.width}px`,height:`${rect.height}px`});
  }
  function ghost(item) {
    if (!item) return null;
    const node=item.node.cloneNode(true);
    node.removeAttribute('id');node.classList.remove('selected','target','ready');
    node.classList.add('fx-ghost');node.setAttribute('aria-hidden','true');node.inert=true;
    position(node,item.rect);layer.append(node);return node;
  }
  function number(item,kind,amount,offset,delay) {
    if (!item) return;
    const label=document.createElement('span');
    label.className=`fx-number fx-${kind}`;
    label.textContent=kind==='block'?'Блок':`${kind==='heal'?'+':'−'}${amount}`;
    Object.assign(label.style,{left:`${item.rect.left+item.rect.width/2+offset}px`,top:`${item.rect.top+item.rect.height/2}px`});
    layer.append(label);
    animate(label,reduced.matches?[{opacity:0},{opacity:1,offset:0.15},{opacity:1,offset:0.8},{opacity:0}]:[
      {opacity:0,transform:'translate(-50%,-10%) scale(.7)'},
      {opacity:1,transform:'translate(-50%,-55%) scale(1.12)',offset:.18},
      {opacity:1,transform:'translate(-50%,-90%) scale(1)',offset:.65},
      {opacity:0,transform:'translate(-50%,-150%) scale(.95)'}],{duration:760,delay,fill:'both'});
  }
  function beam(from,to,heal=false) {
    if (!from || !to || reduced.matches) return;
    const dot=document.createElement('span');dot.className=`fx-bolt${heal?' fx-bolt-heal':''}`;
    const x=from.rect.left+from.rect.width/2,y=from.rect.top+from.rect.height/2;
    Object.assign(dot.style,{left:`${x}px`,top:`${y}px`});layer.append(dot);
    animate(dot,[{opacity:0,transform:'translate(-50%,-50%) scale(.5)'},
      {opacity:1,offset:.15},
      {opacity:1,transform:`translate(${to.rect.left+to.rect.width/2-x}px,${to.rect.top+to.rect.height/2-y}px) scale(1.4)`,offset:.85},
      {opacity:0}],{duration:240,fill:'both'});
  }
  function play(batch,room) {
    if (!batch || document.hidden) return;
    clear();layer=document.createElement('div');layer.className='fx-layer';
    layer.setAttribute('aria-hidden','true');layer.inert=true;document.body.append(layer);
    const {event,old}=batch,current=snapshot();
    const find=ref=>current.get(key(ref)) || old.get(key(ref));
    let source=old.get(key(event.source)) || find(event.source);
    if (!source) source=find({player:event.actor,hero:true});
    const target=find(event.target);
    let impact=0;
    if (event.action==='attack' && source && target && !reduced.matches) {
      const attacker=ghost(source);
      const dx=(target.rect.left+target.rect.width/2)-(source.rect.left+source.rect.width/2);
      const dy=(target.rect.top+target.rect.height/2)-(source.rect.top+source.rect.height/2);
      const scale=Math.min(0.72,180/Math.max(1,Math.hypot(dx,dy)));
      const currentAttacker=current.get(key(event.source))?.node;
      if(currentAttacker)animate(currentAttacker,[{opacity:0},{opacity:0},{opacity:1}],{duration:340});
      animate(attacker,[{transform:'translate(0,0)',opacity:1},
        {transform:`translate(${dx*scale}px,${dy*scale}px) rotate(-5deg)`,opacity:1,offset:.45},
        {transform:'translate(0,0)',opacity:0}],{duration:340,fill:'forwards'});
      impact=145;
    } else if(event.action==='spell') {
      const targets=event.target?[event.target]:event.effects.filter(e=>['damage','heal','block'].includes(e.kind)).map(e=>e.target);
      const seen=new Set();
      for(const ref of targets){if(!seen.has(key(ref))){seen.add(key(ref));beam(source,find(ref),event.effects.some(e=>e.kind==='heal'&&key(e.target)===key(ref)));}}
      impact=reduced.matches?0:190;
    }
    const offsets=new Map();
    for(const effect of event.effects){
      const item=find(effect.target);
      if(!item)continue;
      if(['damage','heal','block'].includes(effect.kind)){
        const count=offsets.get(key(effect.target))||0;offsets.set(key(effect.target),count+1);
        number(item,effect.kind,effect.amount,count?38:0,impact+count*80);
        const live=current.get(key(effect.target))?.node;
        if(live){
          const color=effect.kind==='heal'?'#76ecae':effect.kind==='block'?'#efc66d':'#ff766d';
          const frames=[{boxShadow:`0 0 0px ${color}`,filter:'brightness(1)'},
            {boxShadow:`0 0 25px ${color}`,filter:'brightness(1.5)',offset:.3},
            {boxShadow:`0 0 0px ${color}`,filter:'brightness(1)'}];
          if(!reduced.matches && effect.kind==='damage'){
            frames[0].transform='translateX(0)';frames[1].transform='translateX(-5px)';
            frames.splice(2,0,{transform:'translateX(5px)',offset:.55});frames[3].transform='translateX(0)';
          }
          animate(live,frames,{delay:impact+count*80,duration:360});
        }
      }else if(['death','leave'].includes(effect.kind)){
        const dead=ghost(old.get(key(effect.target)));
        if(dead)animate(dead,reduced.matches?[{opacity:1},{opacity:0}]:[
          {opacity:1,transform:'scale(1)'},{opacity:0,transform:'translateY(20px) scale(.82)',filter:'grayscale(1)'}],
          {delay:impact+130,duration:400,fill:'forwards'});
      }else if(effect.kind==='enter'){
        const node=current.get(key(effect.target))?.node;
        if(node)animate(node,reduced.matches?[{opacity:0},{opacity:1}]:[
          {opacity:0,transform:'translateY(20px) scale(.82)'},
          {opacity:1,transform:'translateY(-3px) scale(1.04)',offset:.7},{opacity:1,transform:'translateY(0) scale(1)'}],{duration:390});
      }
    }
    if(event.action==='play' || event.action==='spell'){
      const card=ghost(old.get(key(event.source)));
      if(card)animate(card,[{opacity:.85},{opacity:0}],{duration:220,fill:'forwards'});
    }
    if(event.turn===room.player_number){
      const turn=document.querySelector('.turn-label');
      if(turn)animate(turn,[{boxShadow:'0 0 0 #83d9aa'},{boxShadow:'0 0 28px #83d9aa',offset:.4},{boxShadow:'0 0 0 #83d9aa'}],{duration:550});
    }
    if(event.winner){
      const result=document.querySelector('.result');
      const won=event.winner===room.player_number;
      if(result)animate(result,reduced.matches?[{opacity:0},{opacity:1}]:[
        {opacity:0,transform:'translateY(12px) scale(.96)'},
        {opacity:1,transform:'translateY(0) scale(1)',boxShadow:won?'0 0 30px #efc66d60':'0 0 20px #ff766d30'}],{duration:600});
    }
    timer=setTimeout(clear,1400);
  }
  document.addEventListener('visibilitychange',()=>{if(document.hidden){ready=false;clear();}});
  window.addEventListener('resize',clear);
  window.addEventListener('scroll',clear,{passive:true});
  return {prepare,play};
})();
