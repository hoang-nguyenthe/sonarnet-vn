"""Exercise the review ZIP in a fresh Streamlit runtime without scan assets."""
import argparse
from importlib.metadata import version
import json
from pathlib import Path
import platform
import time

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def verify():
    if (ROOT/'assets/real_scan/published').exists():
        raise RuntimeError('Run this verifier from a fresh extraction of the Chặng 1 review ZIP')
    app = AppTest.from_file(str(ROOT/'scripts/demo_app.py'),default_timeout=45)
    app.query_params['trang'] = 'minh-chung'
    actions = {}

    def step(name, control):
        started = time.perf_counter()
        control.run()
        if app.exception:
            raise RuntimeError(f'{name}: {app.exception[0].message}')
        actions[name] = round(time.perf_counter()-started,3)

    step('direct_evidence_link', app)
    assert app.radio(key='main_section').value == 'Minh chứng cải tiến'
    downloads = {button.proto.label for button in app.get('download_button')}
    assert 'Tải báo cáo nộp Chặng 1 · 20 trang' in downloads
    recall = AppTest.from_file(str(ROOT/'scripts/demo_app.py'), default_timeout=45)
    recall.query_params['trang'] = 'minh-chung'
    recall.query_params['muc'] = 'recall'
    started = time.perf_counter()
    recall.run()
    assert not recall.exception
    available = {button.proto.label for button in recall.get('download_button')}
    assert 'Tải kết quả thử radar hai kênh' in available
    assert 'Tải đối chứng gộp hạng trên sáu cảnh AIS' in available
    actions['direct_recall_and_rank_downloads'] = round(time.perf_counter()-started, 3)
    assert any(m.label=='Ứng viên radar' and m.value=='77' for m in app.metric)
    assert any('Ghép sai mã' in table.value.columns for table in app.dataframe)
    case = app.selectbox(key='evidence_case')
    step('ais_veto_on_stale_proposal', case.set_value('AIS gần nhất đã cũ, có tín hiệu khác gần đó'))
    response = next(t.value for t in app.dataframe if 'Mã AIS mẫu' in t.value.columns)
    assert (response.loc[0,'Mã AIS mẫu'],response.loc[0,'Trạng thái']) == ('Chưa ghép','Thiếu dữ liệu')
    step('open_fixed_image',app.toggle(key='evidence_open_snapshot').set_value(True))
    assert any('Chưa có kết luận nghiệp vụ' in item.value for item in app.info)

    step('observation_map', app.radio(key='main_section').set_value('Quan sát'))
    step('interactive_review_without_archive', app.radio(key='observation_workflow').set_value('Kiểm tra chi tiết'))
    assert any('hồ sơ mẫu từ ảnh thật' in item.value for item in app.info)
    key = app.selectbox(key='review_tile').value
    assert app.session_state['review_active_notes'] == {}
    context = f"{key}_{app.session_state['review_active_identities'][key]}"
    step('switch_to_raw_radar', app.radio(key='review_image_view').set_value('Ảnh radar nguồn'))
    point = next(item.value for item in app.selectbox if item.label=='Mở điểm cần kiểm tra')
    app.radio(key=f"candidate_status_{context}_{point['id']}").set_value('Có khả năng là tàu')
    save_candidate = next(button for button in app.button if button.label=='Lưu đánh giá')
    step('save_candidate_review',save_candidate.click())
    app.radio(key=f'verdict_{context}').set_value('Cần kiểm tra tiếp')
    note = 'Kiểm thử cục bộ: cần đối chiếu nguồn AIS.'
    app.text_area(key=f'note_{context}').set_value(note)
    save_note = next(button for button in app.button if button.label=='Lưu ghi chú ô ảnh')
    step('save_review_note',save_note.click())
    review = app.session_state['review_active_notes'][key]
    assert review['note'] == note
    assert review['candidate_labels'][str(point['id'])] == 'Có khả năng là tàu'
    assert any(node.proto.label=='Tải hồ sơ kèm ảnh' for node in app.get('download_button'))

    from demo_snapshot import load_snapshot
    from review_packet import read_evidence_packet
    from review_workspace import evidence_bundle
    tile, images, _ = load_snapshot(ROOT)
    bundle = evidence_bundle(ROOT,tile,review,tile['observation_day_utc'],fixed_images=images)
    metadata, files, hashes = read_evidence_packet(bundle)
    assert metadata['review'] == review
    assert metadata['operational_assessment']['conclusion'] is None
    printable = files['review.html'].decode()
    assert 'Đánh giá của người rà' in printable and 'Có khả năng là tàu' in printable
    step('research_page', app.radio(key='main_section').set_value('Nghiên cứu'))
    step('help_page', app.radio(key='main_section').set_value('Hướng dẫn'))
    versions = {name:version(name) for name in ('streamlit','numpy','pandas','scipy','folium','pillow','shapely','plotly')}
    return dict(python=platform.python_version(),platform=platform.platform(),versions=versions,
                scope='AppTest from extracted Chặng 1 ZIP, no assets/real_scan/published directory or server credentials',
                steps_elapsed_s=actions, artifact_zip_bytes=len(bundle),
                verified_files=hashes, evidence_state=metadata['data_status'])


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    report=json.dumps(verify(),ensure_ascii=False,indent=2)+'\n'
    if args.output:
        args.output.write_text(report)
    print(report,end='')
