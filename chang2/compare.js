'use strict';

const picker = document.getElementById('demo-case');
const filter = document.getElementById('case-filter');
const {cases: results,timing,rules_per_case:rulesPerCase} = window.SONARNET_COMPARISON;
const samples = new Map(window.SONARNET_STUDY.cases.map(c=>[c.id,c]));
const summary = new Map(results.map(c=>[c.id,c]));
const panels = [...document.querySelectorAll('[data-mode]')];
const conditions = ['control','ai'];
const decisions = {
  priority:'Ưu tiên rà',
  not_priority:'Chưa ưu tiên',
  insufficient:'Chưa đủ dữ liệu',
};
const number = new Intl.NumberFormat('vi-VN',{maximumFractionDigits:1});
const yesNo = value=>value?'Có':'Không';
const sign = value=>value>0?'+'+number.format(value):number.format(value);

for(const row of results){
  const option=document.createElement('option');
  option.value=row.id;
  option.textContent=row.id+' · '+row.reference+' · '+row.scenario_label;
  picker.append(option);
}

function addRow(parent,values){
  const tr=document.createElement('tr');
  values.forEach((value,index)=>{
    const cell=document.createElement(index===0?'th':'td');
    if(index===0) cell.scope='row';
    if(value instanceof Node) cell.append(value);
    else cell.textContent=value;
    tr.append(cell);
  });
  parent.append(tr);
}

function render(id){
  const sample=samples.get(id), result=summary.get(id);
  for(const panel of panels){
    const field=selector=>panel.querySelector(selector);
    field('[data-case-number]').textContent='Ca '+id;
    window.SonarNetReviewView.evidence(field('[data-track]'),field('[data-speed]'),field('[data-observations]'),sample);
    if(panel.dataset.mode==='ai') field('[data-hint]').textContent=window.SonarNetReviewView.hintText(sample);
    field('[data-feedback]').hidden=true;
    for(const button of panel.querySelectorAll('[data-answer]')) button.setAttribute('aria-pressed','false');
  }
  document.getElementById('example-explanation').textContent=
    id+' có nhãn mô phỏng “'+result.reference+'”. Gợi ý ưu tiên '+
    (result.priority===result.hint_priority?'phù hợp':'mâu thuẫn')+
    ' với nhãn. Trong '+rulesPerCase+' quy tắc, '+result.improved+
    ' đổi từ lỗi sang đúng và '+result.worsened+' đổi từ đúng sang lỗi.';
  const metrics=document.getElementById('case-metrics');
  metrics.replaceChildren();
  for(const [key,label] of Object.entries(decisions))
    addRow(metrics,[label,...conditions.map(c=>(result.counts[c][key]||0)+'/'+rulesPerCase)]);
  addRow(metrics,[result.priority?'Bỏ sót':'Cờ nhầm',...conditions.map(c=>result.errors[c]+'/'+rulesPerCase)]);
  addRow(metrics,['Trung vị bấm tự động',...conditions.map(c=>
    number.format(result.timing[c].median_ms)+' ms ('+result.timing[c].n+' lượt)')]);
  addRow(metrics,['Phân vị 90 bấm tự động',...conditions.map(c=>number.format(result.timing[c].p90_ms)+' ms')]);
  const rules=document.getElementById('case-rules');
  rules.replaceChildren();
  for(const row of result.rules) addRow(rules,[row.name,decisions[row.control],decisions[row.ai]]);
}

function renderTable(){
  const tbody=document.getElementById('all-case-rows');
  tbody.replaceChildren();
  const rows=results.filter(row=>{
    const changed=row.improved+row.worsened>0;
    switch(filter.value){
      case 'changed': return changed;
      case 'conflict': return row.priority!==row.hint_priority;
      case 'stable': return !changed;
      default: return true;
    }
  });
  for(const row of rows){
    const link=document.createElement('a');
    link.href='?ca='+encodeURIComponent(row.id)+'#compare-panels';
    link.textContent=row.id;
    link.addEventListener('click',event=>{
      if(event.ctrlKey||event.metaKey||event.shiftKey||event.altKey) return;
      event.preventDefault();
      picker.value=row.id;
      render(row.id);
      document.getElementById('compare-panels').scrollIntoView();
      picker.focus({preventScroll:true});
    });
    const join=(fn)=>conditions.map(fn).join(' / ');
    addRow(tbody,[link,row.reference,yesNo(row.hint_priority),
      join(c=>row.counts[c].priority||0),join(c=>row.errors[c]),
      join(c=>number.format(row.timing[c].median_ms))]);
  }
  document.getElementById('filter-count').textContent='Đang xem '+rows.length+'/'+results.length+' ca.';
}

for(const panel of panels){
  const buttons=[...panel.querySelectorAll('[data-answer]')];
  for(const button of buttons) button.addEventListener('click',()=>{
    for(const item of buttons) item.setAttribute('aria-pressed',String(item===button));
    const feedback=panel.querySelector('[data-feedback]');
    feedback.textContent='Đã chọn: '+decisions[button.dataset.answer]+'.';
    feedback.hidden=false;
  });
}

picker.addEventListener('change',()=>render(picker.value));
filter.addEventListener('change',renderTable);
const initial=new URLSearchParams(location.search).get('ca');
picker.value=summary.has(initial)?initial:'Q16';
render(picker.value);
renderTable();
document.getElementById('timing-summary').textContent=
  'Trung vị bấm tự động là '+number.format(timing.control.median_ms)+' ms khi không gợi ý và '+
  number.format(timing.ai.median_ms)+' ms khi có gợi ý. Chênh trung vị trên '+timing.delta.n+
  ' cặp cùng ca, quy tắc và vị trí lượt là '+sign(timing.delta.median_ms)+
  ' ms (có AI trừ không AI). Chưa đo thời gian suy nghĩ của người.';
