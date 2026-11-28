'use strict';

const picker = document.getElementById('demo-case');
const filter = document.getElementById('case-filter');
const scenarioFilter = document.getElementById('case-scenario');
const search = document.getElementById('case-search');
const previous = document.getElementById('prev-cases');
const next = document.getElementById('next-cases');
const pageSize = 25;
let tablePage=0;
const params=new URLSearchParams(location.search);
const requested=params.get('ca');
const isChallenge=params.get('bo')==='thu-thach'||/^Q\d{2}$/.test(requested);
const data=isChallenge?window.SONARNET_CHALLENGE:window.SONARNET_COMPARISON;
const {cases: results,timing,rules_per_case:rulesPerCase,default_case:defaultCase,
  exception_cases:exceptionCases} = data;
const bank=isChallenge?window.SONARNET_STUDY.cases:window.SONARNET_REVIEW_BANK;
const samples = new Map(bank.map(c=>[c.id,c]));
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
const caseURL=id=>'?'+(isChallenge?'bo=thu-thach&':'')+'ca='+encodeURIComponent(id)+'#compare-panels';
document.getElementById('table-link').textContent='Xem bảng '+results.length+' ca';
document.getElementById('case-table-heading').textContent='Đối chiếu '+results.length+' ca';
document.getElementById('bank-description').textContent=isChallenge
  ? 'Bộ thử thách chủ động chọn ca khó và có gợi ý sai. Kết quả được báo riêng.'
  : 'Bộ 200 ca có 4 nhóm hành vi và 5 mức chất lượng AIS, 10 ca mỗi tổ hợp. Ca được chọn trước khi chấm gợi ý.';
if(isChallenge){
  document.getElementById('case-csv').hidden=true;
  document.getElementById('case-json').href='proxy-study-challenge-16.json';
}
const bankLink=document.createElement('a');
bankLink.href=isChallenge?'compare.html':'?bo=thu-thach';
bankLink.textContent=isChallenge?'Về bộ 200 ca':'Xem bộ thử thách 16 ca';
document.getElementById('case-examples').append(bankLink);

for(const row of results){
  const option=document.createElement('option');
  option.value=row.id;
  option.textContent=row.id+' · '+row.reference+' · '+row.scenario_label;
  picker.append(option);
}

for(const [key,label] of new Map(results.map(r=>[r.scenario,r.scenario_label]))){
  const option=document.createElement('option');
  option.value=key;
  option.textContent=label;
  scenarioFilter.append(option);
}
for(const id of [defaultCase,...exceptionCases]){
  const result=summary.get(id);
  const action=id===defaultCase?'Gợi ý thuận lợi':result.priority?'Nguy cơ bỏ sót':'Nguy cơ cờ nhầm';
  const link=document.createElement('a');
  link.href=caseURL(id);
  link.textContent=action+' · '+id;
  document.getElementById('case-examples').append(link);
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
  const query=search.value.trim().toUpperCase();
  const rows=results.filter(row=>{
    if(query && !row.id.includes(query)) return false;
    if(scenarioFilter.value!=='all' && row.scenario!==scenarioFilter.value) return false;
    const changed=row.improved+row.worsened>0;
    switch(filter.value){
      case 'changed': return changed;
      case 'conflict': return row.priority!==row.hint_priority;
      case 'stable': return !changed;
      default: return true;
    }
  });
  const pageCount=Math.max(1,Math.ceil(rows.length/pageSize));
  tablePage=Math.min(tablePage,pageCount-1);
  const start=tablePage*pageSize;
  for(const row of rows.slice(start,start+pageSize)){
    const link=document.createElement('a');
    link.href=caseURL(row.id);
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
  document.getElementById('filter-count').textContent=rows.length
    ? 'Hiển thị '+(start+1)+'–'+Math.min(start+pageSize,rows.length)+' / '+rows.length+' ca phù hợp trong '+results.length+' ca.'
    : 'Không có ca phù hợp.';
  document.getElementById('case-page').textContent='Trang '+(tablePage+1)+'/'+pageCount;
  previous.disabled=tablePage===0;
  next.disabled=tablePage+1>=pageCount;
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
for(const field of [filter,scenarioFilter,search]) field.addEventListener('input',()=>{
  tablePage=0;
  renderTable();
});
previous.addEventListener('click',()=>{tablePage--;renderTable();});
next.addEventListener('click',()=>{tablePage++;renderTable();});
picker.value=summary.has(requested)?requested:defaultCase;
render(picker.value);
renderTable();
document.getElementById('timing-summary').textContent=
  'Trung vị bấm tự động là '+number.format(timing.control.median_ms)+' ms khi không gợi ý và '+
  number.format(timing.ai.median_ms)+' ms khi có gợi ý. Chênh trung vị trên '+timing.delta.n+
  ' cặp cùng ca, quy tắc và vị trí lượt là '+sign(timing.delta.median_ms)+
  ' ms (có AI trừ không AI). Chưa đo thời gian suy nghĩ của người.';
