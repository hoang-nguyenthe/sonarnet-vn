'use strict';

const picker = document.getElementById('demo-case');
const panels = [...document.querySelectorAll('[data-mode]')];
const examples = {
  Q16: 'Gợi ý “Ưu tiên rà” trùng nhãn mô phỏng câu. Người rà có thể bắt đầu bằng giả thuyết này rồi kiểm tra tốc độ và quỹ đạo.',
  Q02: 'Gợi ý “Chưa ưu tiên” mâu thuẫn với nhãn mô phỏng câu. Nếu chỉ làm theo gợi ý, ca cần rà có thể bị bỏ qua.',
  Q08: 'Gợi ý “Ưu tiên rà” mâu thuẫn với nhãn mô phỏng quá cảnh. Nếu chấp nhận ngay, ca âm có thể bị đưa nhầm vào hàng rà.',
};
const decisions = {
  priority:'Ưu tiên rà',
  not_priority:'Chưa ưu tiên',
  insufficient:'Chưa đủ dữ liệu',
};

function render(id) {
  const sample = window.SONARNET_STUDY.cases.find(row => row.id===id);
  for (const panel of panels) {
    const field = selector => panel.querySelector(selector);
    field('[data-case-number]').textContent = 'Ca '+id;
    window.SonarNetReviewView.evidence(field('[data-track]'),field('[data-speed]'),field('[data-observations]'),sample);
    if (panel.dataset.mode==='ai') field('[data-hint]').textContent=window.SonarNetReviewView.hintText(sample);
    field('[data-feedback]').hidden=true;
    for (const button of panel.querySelectorAll('[data-answer]')) button.setAttribute('aria-pressed','false');
  }
  document.getElementById('example-explanation').textContent=examples[id];
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
const initial=new URLSearchParams(location.search).get('ca');
if(Object.hasOwn(examples,initial)) picker.value=initial;
render(picker.value);
