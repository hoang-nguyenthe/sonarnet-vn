'use strict';

const byId = id => document.getElementById(id);
const bank = window.SONARNET_STUDY;
const layouts = [
  [['A',false],['B',true]],
  [['B',true],['A',false]],
  [['A',true],['B',false]],
  [['B',false],['A',true]],
];
const reviewPanels = ['intro','task','between','done'];
let participant, blocks, layoutIndex, blockIndex=0, caseIndex=0, openedAt, trialStarted;
let hiddenAtStart, hiddenEvents=0, phase='intro';
const answers=[];

document.addEventListener('visibilitychange',()=>{
  if (document.hidden && phase==='task') hiddenEvents+=1;
});

function show(panel) {
  phase=panel;
  for(const id of reviewPanels) byId(id).hidden=id!==panel;
  window.scrollTo(0,0);
}

function seededOrder(rows,seed) {
  const copy=[...rows];
  let state=seed;
  for(let index=copy.length-1;index>0;index--){
    state=(Math.imul(state,1664525)+1013904223)>>>0;
    const other=state%(index+1);
    [copy[index],copy[other]]=[copy[other],copy[index]];
  }
  return copy;
}

function svgNode(name,attributes,text) {
  const node=document.createElementNS('http://www.w3.org/2000/svg',name);
  for(const [key,value] of Object.entries(attributes)) node.setAttribute(key,value);
  if(text!==undefined)node.textContent=text;
  return node;
}

function plot(id,xs,ys,xLabel,yLabel,equalScale=false) {
  const panel=byId(id);
  const xmin=Math.min(...xs), ymin=Math.min(...ys);
  const xmax=Math.max(...xs), ymax=Math.max(...ys);
  let xSpan=Math.max(xmax-xmin,1), ySpan=Math.max(ymax-ymin,1);
  if(equalScale){const m=Math.max(xSpan/270,ySpan/133); xSpan=m*270; ySpan=m*133;}
  const x0=(xmin+xmax-xSpan)/2, y0=(ymin+ymax-ySpan)/2;
  const px=v=>53+(v-x0)*270/xSpan, py=v=>151-(v-y0)*133/ySpan;
  const nice=v=>Math.abs(v)>=10?Math.round(v):v.toFixed(1);
  panel.replaceChildren();
  for(let i=0;i<=4;i++){
    const x=53+270*i/4,y=151-133*i/4;
    panel.append(svgNode('line',{x1:x,x2:x,y1:18,y2:151,stroke:'#d6e6e8'}),
      svgNode('line',{x1:53,x2:323,y1:y,y2:y,stroke:'#d6e6e8'}),
      svgNode('text',{x,y:166,fill:'#4d636e','text-anchor':'middle','font-size':10},nice(x0+xSpan*i/4)),
      svgNode('text',{x:49,y:y+3,fill:'#4d636e','text-anchor':'end','font-size':10},nice(y0+ySpan*i/4)));
  }
  panel.append(svgNode('text',{x:187,y:187,fill:'#284654','font-size':11,'text-anchor':'middle'},xLabel),
    svgNode('text',{x:12,y:85,transform:'rotate(-90 12 85)',fill:'#284654','font-size':11,'text-anchor':'middle'},yLabel),
    svgNode('polyline',{points:xs.map((x,i)=>px(x)+','+py(ys[i])).join(' '),fill:'none',stroke:'#007d73','stroke-width':2}));
  xs.forEach((x,i)=>panel.append(svgNode('circle',{cx:px(x),cy:py(ys[i]),r:i===0||i===xs.length-1?4:2.2,
    fill:i===0?'#b25418':i===xs.length-1?'#17314d':'#007d73'})));
}

function nextCase() {
  const block=blocks[blockIndex],sample=block.cases[caseIndex];
  byId('progress').textContent='Lượt '+(blockIndex+1)+'/2 · Ca '+(caseIndex+1)+'/8';
  byId('condition').textContent=block.hint?'Có gợi ý AI':'Không có gợi ý AI';
  byId('case-title').textContent='Ca '+sample.id;
  plot('track',sample.east_m,sample.north_m,'Đông tương đối (m)','Bắc tương đối (m)',true);
  plot('speed',sample.elapsed_min,sample.speed_kn,'Thời gian (phút)','Tốc độ (kn)');
  const n=sample.speed_kn.length, minutes=sample.elapsed_min.at(-1);
  byId('observations').textContent=n+' bản tin trong '+minutes+' phút · Tốc độ gần nhất '+sample.speed_kn.at(-1)+' kn · Hướng gần nhất '+sample.course_deg.at(-1)+'°.';
  const hint=byId('hint');
  hint.hidden=!block.hint;
  hint.textContent=block.hint?'Gợi ý mô hình: '+(sample.hint_priority?'ưu tiên rà':'chưa ưu tiên')+
    ' · Mẫu dự đoán '+sample.hint_class.toLowerCase()+'. Bạn tự quyết định dựa trên quỹ đạo.':'';
  show('task');
  byId('case-title').focus({preventScroll:true});
  hiddenAtStart=hiddenEvents;
  openedAt=performance.now();
}

byId('enroll').addEventListener('submit',event=>{
  event.preventDefault();
  const code=byId('reviewer').value.trim().toUpperCase();
  const number=Number(code.slice(1));
  if(!Number.isInteger(number)||number<1||!bank)return;
  participant={code,experience:byId('role').value,consent:true};
  layoutIndex=(number-1)%layouts.length;
  blocks=layouts[layoutIndex].map(([pack,hint],i)=>({
    pack,hint,cases:seededOrder(bank.cases.filter(row=>row.pack===pack),number*101+i+1)
  }));
  trialStarted=new Date().toISOString();
  nextCase();
});

document.querySelectorAll('[data-answer]').forEach(button=>button.addEventListener('click',()=>{
  if(phase!=='task')return;
  const block=blocks[blockIndex],sample=block.cases[caseIndex];
  const decision=button.dataset.answer;
  answers.push({case_id:sample.id,pack:block.pack,block:blockIndex+1,condition:block.hint?'ai':'control',
    decision,time_ms:Math.round(performance.now()-openedAt),tab_hidden_events:hiddenEvents-hiddenAtStart});
  if(++caseIndex<block.cases.length){nextCase();return;}
  if(blockIndex===0){show('between');return;}
  show('done');
  byId('finish-summary').textContent='Đã ghi '+answers.length+' quyết định cho mã '+participant.code+'.';
}));

byId('continue').addEventListener('click',()=>{
  if(phase!=='between')return;
  blockIndex=1;caseIndex=0;nextCase();
});

byId('download').addEventListener('click',()=>{
  if(phase!=='done')return;
  const content={schema:1,bank_sha256:bank.sha256,participant,layout:layoutIndex+1,
    started_at:trialStarted,finished_at:new Date().toISOString(),responses:answers};
  const link=document.createElement('a');
  link.href=URL.createObjectURL(new Blob([JSON.stringify(content,null,2)+'\n'],{type:'application/json'}));
  link.download='sonarnet-chang2-'+participant.code+'.json';link.click();
  setTimeout(()=>URL.revokeObjectURL(link.href),1000);
});
