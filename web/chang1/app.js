const $ = id => document.getElementById(id);
const number = new Intl.NumberFormat('vi-VN');
const formatCount = value => number.format(value);
const fraction = item => `${item.matched}/${item.labels}`;
const vnMethods = {
  map: 'Mô hình trên bản đồ',
  previous_best: 'YOLO với các lượt quét bổ sung',
  weak_echoes: 'Quét tín hiệu yếu',
  xview3: 'Phối hợp YOLO và xView3',
};
const aisMethods = {
  original: 'YOLO trên ảnh nguyên',
  prior: 'YOLO sau xử lý trùng lặp',
  fused_xview3: 'Phối hợp YOLO và xView3',
  xview3_first: 'Ưu tiên xView3',
};
const matchMethods = {
  distance_only: 'Chỉ dùng khoảng cách',
  previous_gates: 'Các điều kiện lọc cũ',
  '100m_guard': 'Điều kiện lọc với bán kính 100 m',
  propose_then_veto: 'Đề xuất cặp rồi kiểm tra',
};

function option(value, label) {
  const element = document.createElement('option');
  element.value = value;
  element.textContent = label;
  return element;
}

function addRow(table, name, ...values) {
  const row = document.createElement('tr');
  const header = document.createElement('th');
  header.scope = 'row';
  header.textContent = name;
  row.append(header);
  for (const value of values) {
    const cell = document.createElement('td');
    cell.append(value);
    row.append(cell);
  }
  table.append(row);
}

function recallCell(item) {
  const result = document.createElement('span');
  result.className = 'fraction';
  result.textContent = fraction(item);

  const bar = document.createElement('span');
  bar.className = 'metric-bar';
  bar.setAttribute('aria-hidden', 'true');
  const progress = document.createElement('span');
  progress.style.width = `${item.matched / item.labels * 100}%`;
  bar.append(progress);

  const group = document.createDocumentFragment();
  group.append(result, bar);
  return group;
}

function addLinks(container, links) {
  container.replaceChildren();
  for (const [name, url] of links) {
    const link = document.createElement('a');
    link.href = url;
    link.textContent = name;
    container.append(link);
  }
}

function renderExample(example) {
  $('examples-description').textContent = `${example.area} · ${formatCount(example.reviewed)} ứng viên cần rà trong cảnh. Hai ảnh hiển thị cùng vùng cắt.`;
  $('before-image').src = `data/${example.imagePrefix}-before.png`;
  $('after-image').src = `data/${example.imagePrefix}-after.png`;
  $('before-caption').textContent = `Trước cải tiến · ${example.before}/${example.labels} nhãn khớp trong cảnh`;
  $('after-caption').textContent = `Phối hợp YOLO và xView3 · ${example.after}/${example.labels} nhãn khớp trong cảnh`;
  $('examples-note').textContent = example.note;
}

function renderRecall(data) {
  const cohort = $('cohort').value;
  const isAis = cohort === 'ais';
  const mode = $('queue').value;
  const radius = $('radius').value;
  const methods = isAis ? aisMethods : {
    ...vnMethods,
    xview3: mode === 'equal_incumbent' ? 'xView3 chạy riêng' : vnMethods.xview3,
  };
  const rows = isAis
    ? Object.fromEntries(Object.entries(data.ais[mode]).map(([key, values]) => [key, values[radius]]))
    : data.vietnam[cohort][mode];
  const base = isAis ? rows.original : rows.previous_best;
  const transfer = isAis ? rows.fused_xview3 : rows.xview3;
  $('metric-summary').textContent = `${fraction(base)} → ${fraction(transfer)} nhãn khớp · ${formatCount(base.predictions)} lượt rà · ${radius} m`;
  const table = $('metrics');
  table.replaceChildren();
  for (const [key, label] of Object.entries(methods)) {
    const value = rows[key];
    addRow(table, label, recallCell(value), formatCount(value.unmatched));
  }

  const scope = isAis
    ? '13 mốc vị trí AIS lịch sử ít dịch chuyển, chọn trước khi nhìn kết quả radar. Khi rà rộng, YOLO sau xử lý trùng lặp cũng đạt 13/13 ở 100 m.'
    : 'Nhãn điểm Ai2, ghép một–một ở 100 m. Số lượt rà được giữ riêng cho từng cảnh.';
  $('cohort-note').textContent = scope;
  addLinks($('recall-links'), isAis ? [
    ['Kết quả SAR và AIS theo cảnh', data.links.aisResults],
    ['Quy trình đối chứng', data.links.aisProtocol],
  ] : [
    ['Bảng số liệu và phạm vi tập chấm', data.links.vnResults],
    ['Hướng dẫn tái lập', data.links.vnProtocol],
  ]);
}

function selectCohort(data) {
  const isAis = $('cohort').value === 'ais';
  const counts = isAis
    ? Object.entries(data.ais).map(([key, mode]) => [key, mode.original['100'].predictions])
    : Object.entries(data.vietnam[$('cohort').value]).map(([key, mode]) => [key, mode.map.predictions]);
  $('queue').replaceChildren(...counts.map(([key, count]) => option(key, formatCount(count))));
  $('queue').value = $('cohort').value === 'held_out' ? 'equal_relaxed' : counts[0][0];
  const radii = isAis ? ['50', '100', '150'] : ['100'];
  $('radius').replaceChildren(...radii.map(radius => option(radius, `${radius} m`)));
  $('radius').value = '100';
  $('radius').disabled = !isAis;
  renderRecall(data);
  renderExample(isAis ? data.examples.ais : data.examples.vietnam);
}

function renderAssociation(data) {
  const group = data.association[$('ais-cohort').value];
  const guard = group.counts['100m_guard'];
  const improved = group.counts.propose_then_veto;
  $('ais-summary').textContent = `${improved.agree}/${group.paired_references} mốc đồng ý · ${guard.proposed_without_reference} → ${improved.proposed_without_reference} đề xuất chưa có mốc kiểm chứng`;
  const table = $('ais-metrics');
  table.replaceChildren();
  for (const [key, label] of Object.entries(matchMethods)) {
    const value = group.counts[key];
    addRow(table, label, formatCount(value.agree), formatCount(value.disagree), formatCount(value.proposed_without_reference));
  }
}

function drawCasePositions(payload) {
  const canvas = $('case-positions');
  const {width, height} = canvas.getBoundingClientRect();
  const density = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * density);
  canvas.height = Math.round(height * density);
  const context = canvas.getContext('2d');
  context.scale(density, density);

  const sar = payload.sar_east_m;
  const ais = payload.ais_east_m;
  const positions = [...sar, ...Object.values(ais)];
  const padding = Math.max(9, (Math.max(...positions) - Math.min(...positions)) * .13);
  const lower = Math.floor(Math.min(...positions) - padding);
  const upper = Math.ceil(Math.max(...positions) + padding);
  const start = 43;
  const end = width - 25;
  const x = value => start + (value - lower) * (end - start) / (upper - lower);
  const first = 31;
  const second = 77;

  context.font = '12px system-ui';
  context.textBaseline = 'middle';
  context.fillStyle = '#445d66';
  context.fillText('SAR', 1, first);
  context.fillText('AIS', 1, second);
  context.strokeStyle = '#adc1c5';
  context.lineWidth = 1;
  for (const row of [first, second]) {
    context.beginPath();
    context.moveTo(start, row);
    context.lineTo(end, row);
    context.stroke();
  }
  context.strokeStyle = '#00645d';
  context.lineWidth = 2;
  for (const [index, key] of Object.entries(payload.matches)) {
    context.beginPath();
    context.moveTo(x(sar[index]), first);
    context.lineTo(x(ais[key]), second);
    context.stroke();
  }
  context.fillStyle = '#12598e';
  for (const value of sar) {
    context.beginPath();
    context.arc(x(value), first, 5, 0, Math.PI * 2);
    context.fill();
  }
  context.fillStyle = '#9b4d12';
  for (const value of Object.values(ais)) {
    context.fillRect(x(value) - 4, second - 4, 8, 8);
  }
  context.fillStyle = '#445d66';
  context.textAlign = 'center';
  context.fillText(`${lower} m`, start, 104);
  context.fillText(`${upper} m`, end, 104);
}

function setupCaseDemo(data) {
  const grid = data.scenarios;
  const choices = $('case-type');
  const age = $('case-age');
  const sigma = $('case-sigma');
  const button = $('case-export');
  choices.replaceChildren(...Object.entries(grid.cases).map(([name, item]) => option(name, item.label)));
  age.replaceChildren(...grid.age_options_s.map(value => option(value, formatCount(value))));
  sigma.replaceChildren(...grid.sigma_options_m.map(value => option(value, formatCount(value))));
  $('case-thresholds').textContent =
    `Tuổi AIS tối đa ${grid.thresholds.max_ais_age_s} giây, độ bất định tối đa ${grid.thresholds.max_position_sigma_m} m. ` +
    `Bán kính ghép dùng ${grid.thresholds.match_sigma_multiplier} lần độ bất định kết hợp, tối đa ${grid.thresholds.max_match_distance_m} m. ` +
    'Khi đề xuất ban đầu bị từ chối, bộ ghép giữ ca để rà.';
  $('case-code').href = data.links.scenarioCode;

  let current;
  function render() {
    const selected = grid.cases[choices.value];
    current = selected.samples[`${age.value}:${sigma.value}`];
    const payload = current.payload;
    const pairs = Object.keys(payload.matches).length;
    const aisCount = Object.keys(payload.ais_east_m).length;
    $('case-description').textContent = selected.description;
    $('case-figure-note').textContent =
      `${payload.sar_east_m.length} điểm SAR · ${aisCount} mốc AIS · ${pairs} cặp vị trí. Trục ngang là độ lệch về phía đông.`;
    $('case-status').textContent = 'Kết luận nghiệp vụ đang chờ người có chuyên môn xác minh.';
    const table = $('case-results');
    table.replaceChildren();
    for (const row of current.rows) {
      const status = document.createElement('strong');
      status.textContent = row['Trạng thái'];
      const reason = document.createElement('small');
      reason.textContent = row['Lý do'];
      const detail = document.createDocumentFragment();
      detail.append(status, reason);
      const key = row['Mã AIS mẫu'];
      const pair = key === 'Chưa ghép' ? key : `AIS ${key} · ${formatCount(row['Khoảng cách (m)'])} m`;
      addRow(table, row['Điểm SAR'], detail, pair);
    }
    drawCasePositions(payload);
  }

  function choose() {
    age.value = grid.cases[choices.value].default_age;
    sigma.value = 20;
    age.disabled = sigma.disabled = choices.value === 'missing';
    render();
  }

  choices.addEventListener('change', choose);
  age.addEventListener('change', render);
  sigma.addEventListener('change', render);
  button.addEventListener('click', () => {
    const record = {source_commit: data.commit, ...current.payload, rows: current.rows};
    downloadJson('SonarNet_ket_qua_mo_phong_AIS.json', record);
  });
  choose();
  button.disabled = false;
  new ResizeObserver(() => drawCasePositions(current.payload)).observe($('case-positions'));
}

function downloadJson(filename, payload) {
  const file = new Blob([JSON.stringify(payload, null, 2) + '\n'], {type: 'application/json'});
  const download = document.createElement('a');
  download.href = URL.createObjectURL(file);
  download.download = filename;
  download.click();
  setTimeout(() => URL.revokeObjectURL(download.href), 1000);
}

function downloadReview(data) {
  const payload = {
    evidence_version: data.commit,
    sample_sha256: data.sample.zipSha256,
    image_sha256: data.sample.imageSha256,
    sample_key: data.sample.key,
    candidate_id: data.sample.candidateId,
    review_status: $('review-status').value,
    note: $('review-note').value.trim(),
  };
  downloadJson('SonarNet_ghi_chu_ra_soat.json', payload);
  $('review-result').textContent = 'Đã tạo tệp JSON có mã băm liên kết với hồ sơ mẫu.';
}

async function start() {
  const response = await fetch('data/minh-chung.json');
  if (!response.ok) throw new Error(`Evidence HTTP ${response.status}`);
  const data = await response.json();
  const requested = new URL(location.href).searchParams.get('tap');
  if (['held_out', 'confirmation', 'ais'].includes(requested)) $('cohort').value = requested;
  selectCohort(data);
  renderAssociation(data);
  setupCaseDemo(data);
  addLinks($('ais-links'), [['Kết quả ghép theo cảnh', data.links.associationResults]]);
  $('source-code').href = data.links.code;
  $('version').textContent = `Dữ liệu và báo cáo ghim theo Git ${data.commit.slice(0, 10)}.`;
  $('cohort').addEventListener('change', () => selectCohort(data));
  for (const control of ['queue', 'radius']) {
    $(control).addEventListener('change', () => renderRecall(data));
  }
  $('ais-cohort').addEventListener('change', () => renderAssociation(data));
  $('review').onsubmit = event => {
    event.preventDefault();
    downloadReview(data);
  };
}

$('review').onsubmit = event => event.preventDefault();
start().catch(error => {
  $('metric-summary').textContent = 'Không tải được số liệu. Hãy tải lại trang hoặc mở báo cáo PDF.';
  $('review-result').textContent = 'Hãy tải hồ sơ mẫu để kiểm tra ảnh và mã băm.';
  $('review').querySelector('button').disabled = true;
  console.error(error);
});
