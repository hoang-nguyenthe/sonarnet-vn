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

function nextCase() {
  const block=blocks[blockIndex],sample=block.cases[caseIndex];
  byId('progress').textContent='Lượt '+(blockIndex+1)+'/2 · Ca '+(caseIndex+1)+'/8';
  byId('condition').textContent=block.hint?'Có gợi ý AI':'Không có gợi ý AI';
  byId('case-title').textContent='Ca '+sample.id;
  window.SonarNetReviewView.evidence(byId('track'),byId('speed'),byId('observations'),sample);
  const hint=byId('hint');
  hint.hidden=!block.hint;
  hint.textContent=block.hint?window.SonarNetReviewView.hintText(sample):'';
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
