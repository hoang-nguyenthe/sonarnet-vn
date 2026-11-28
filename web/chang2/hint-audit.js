'use strict';

window.SonarNetHintAudit = (() => {
  const featureLabels = {
    speed_mean:['Tốc độ trung bình','kn'], speed_std:['Độ lệch chuẩn tốc độ','kn'],
    speed_median:['Trung vị tốc độ','kn'], speed_p10:['Phân vị 10 tốc độ','kn'],
    speed_p90:['Phân vị 90 tốc độ','kn'], speed_max:['Tốc độ lớn nhất','kn'],
    speed_cv:['Độ lệch chuẩn / tốc độ trung bình',''],
    turn_abs_mean:['Đổi hướng trung bình','°'], turn_abs_std:['Độ lệch chuẩn góc đổi hướng','°'],
    turn_abs_p90:['Phân vị 90 góc đổi hướng','°'],
    turn_sign_changes:['Tỷ lệ đổi chiều quay giữa các bước','%'],
    stop_fraction:['Tỷ lệ bản tin dưới 0,8 kn','%'], moving_fraction:['Tỷ lệ bản tin từ 0,8 kn','%'],
    straightness:['Độ thẳng đường đi',''], radius_gyration_m:['Bán kính phân tán quanh tâm','m'],
    path_length_m:['Tổng độ dài các đoạn nối bản tin','m'],
    net_displacement_m:['Khoảng cách từ đầu đến cuối','m'],
    bbox_diag_m:['Đường chéo vùng bao quỹ đạo','m'], area_coverage_ratio:['Tổng độ dài / đường chéo vùng bao',''],
    accel_abs_mean:['Gia tốc tuyệt đối trung bình','m/s²'],
    accel_abs_std:['Độ lệch chuẩn gia tốc tuyệt đối','m/s²'],
    course_autocorr_lag1:['Tự tương quan góc đổi hướng ở độ trễ 1',''],
    course_spectral_peak:['Vị trí đỉnh phổ đổi hướng đã chuẩn hóa',''],
    course_spectral_ratio:['Tỷ trọng đỉnh phổ đổi hướng','%'],
    speed_autocorr_lag1:['Tự tương quan tốc độ ở độ trễ 1',''], n_points:['Số bản tin',''],
  };
  const decimal = new Intl.NumberFormat('vi-VN',{maximumFractionDigits:3});
  const score = new Intl.NumberFormat('vi-VN',{style:'percent',maximumFractionDigits:2});
  const signed = value => (value>0?'+':'')+decimal.format(value);

  function node(tag,text) {
    const value=document.createElement(tag);
    if(text!==undefined) value.textContent=text;
    return value;
  }

  function table(headers, rows) {
    const wrap=node('div');
    wrap.className='table-wrap';
    const grid=node('table');
    const heading=grid.createTHead().insertRow();
    headers.forEach(label=>{
      const field=node('th',label);
      field.scope='col';
      heading.append(field);
    });
    const body=grid.createTBody();
    rows.forEach(values=>{
      const row=body.insertRow();
      row.append(...values.map(value=>node('td',value)));
    });
    wrap.append(grid);
    return wrap;
  }

  function render(container,sample) {
    container.replaceChildren();
    const bank=window.SONARNET_HINT_EXPLANATIONS;
    const data=bank?.cases[sample.id];
    if(!data || bank.classes[data.winner]!==sample.hint_class){
      container.append(node('p','Chưa có bản giải thích đã xác minh cho ca này.'));
      return;
    }
    const winner=bank.classes[data.winner], runner=bank.classes[data.runner_up];
    const ranking=data.scores.map((value,index)=>({label:bank.classes[index],value}))
      .sort((a,b)=>b.value-a.value);
    const features=bank.features.map((name,index)=>{
      const [label,unit]=featureLabels[name];
      const value=data.inputs[index];
      const delta=data.feature_gaps[index];
      const shown=unit==='%'?score.format(value):decimal.format(value)+(unit?' '+unit:'');
      return {label,shown,delta};
    });
    const sorted=[...features].sort((a,b)=>Math.abs(b.delta)-Math.abs(a.delta));
    const featureRow=({label,shown,delta})=>[label,shown,signed(delta)];
    const more=node('details');
    more.append(node('summary','Xem đủ 26 đầu vào và công thức'),table(
      ['Đặc trưng','Giá trị dùng','Δ điểm thô'],features.map(featureRow)));
    more.append(node('p','Điểm thô là tổng điểm từ các cây XGBoost. Softmax chia exp(điểm mỗi lớp) cho tổng exp(điểm bốn lớp). Chênh giữa hai lớp = chênh nền + tổng chênh TreeSHAP của 26 đầu vào. Giá trị hiển thị đã làm tròn.'));
    const research=node('a','Xem cách tính đặc trưng');
    research.href='https://github.com/hoang-nguyenthe/sonarnet-vn/blob/chang-2/src/sonarnet/behavior/features.py';
    const exportButton=node('button','Tải dữ liệu giải thích ca này');
    exportButton.type='button';
    exportButton.className='secondary';
    exportButton.addEventListener('click',()=>{
      const content={case_id:sample.id,model:bank.model,seed:bank.seed,versions:bank.versions,
        booster_sha256:bank.booster_sha256,banks_sha256:bank.banks_sha256,classes:bank.classes,
        features:bank.features,observations:{elapsed_min:sample.elapsed_min,east_m:sample.east_m,
          north_m:sample.north_m,speed_kn:sample.speed_kn,course_deg:sample.course_deg},...data};
      const link=node('a');
      link.href=URL.createObjectURL(new Blob([JSON.stringify(content,null,2)],{type:'application/json'}));
      link.download='sonarnet-giai-thich-'+sample.id+'.json';
      link.click();
      setTimeout(()=>URL.revokeObjectURL(link.href),1000);
    });
    const actions=node('div');
    actions.className='links';
    actions.append(research,exportButton);
    const maxGap=Math.max(...sample.elapsed_min.slice(1).map((end,index)=>end-sample.elapsed_min[index]));
    const scoreText=ranking.map(({label,value})=>label+' '+score.format(value)).join(' · ');
    container.append(
      node('h3','1. AI chấm bốn lớp thế nào?'),
      node('p',scoreText),
      node('p','Lớp cao nhất là '+winner+'. Hệ thống chỉ gợi ý ưu tiên khi lớp đứng đầu là Câu hoặc Kéo lưới. Các điểm đã chuẩn hóa trên mô hình học từ mô phỏng, chưa hiệu chỉnh độ tin cậy thực địa.'),
      node('h3','2. Điều gì nghiêng về '+winner+'?'),
      node('p','Đối thủ gần nhất là '+runner+'. Chênh điểm thô '+signed(data.gap)+' gồm chênh nền '+signed(data.base_gap)+' và đóng góp của 26 đầu vào. Dấu + nghiêng về '+winner+', dấu − nghiêng về '+runner+'.'),
      table(['Đặc trưng đóng góp lớn nhất','Giá trị dùng','Δ điểm thô'],sorted.slice(0,4).map(featureRow)),
      more,
      node('h3','3. Tự đối chiếu với bản tin'),
      node('p','So tốc độ trong bảng với đồ thị bên trên. So hướng đổi và độ thẳng với các đoạn nối trên quỹ đạo. Khoảng cách dài nhất giữa hai bản tin là '+decimal.format(maxGap)+' phút. Các đoạn nối qua khoảng trống chỉ nối những điểm đã quan sát. AIS nhiễu hoặc thiếu mốc có thể đổi gợi ý.'),
      node('p','Chọn nhận định của bạn rồi mở “Đối chiếu với nhãn mô phỏng” dưới hai khung để chấm cả lớp hành vi và quyết định ưu tiên.'),
      actions,
    );
  }

  return {render};
})();
