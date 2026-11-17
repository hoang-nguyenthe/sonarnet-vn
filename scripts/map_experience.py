"""Map controls for dense observations. Clusters count candidates, never vessels."""
from branca.element import MacroElement, Template
from folium.plugins import MarkerCluster


def add_observation_cluster(group):
    """Keep every evidence popup while making coincident candidates reachable."""
    return MarkerCluster(
        name='Cụm điểm cần kiểm tra', control=False,
        options={
            'maxClusterRadius': 45, 'chunkedLoading': True,
            'showCoverageOnHover': False, 'spiderfyOnMaxZoom': True,
            'zoomToBoundsOnClick': True,
        },
        icon_create_function="""function(cluster) {
            const count = cluster.getChildCount();
            return L.divIcon({className:'observation-cluster',iconSize:[44,44],
                html:'<div title="'+count+' điểm cần kiểm tra; bấm để phóng to" '+
                'style="width:40px;height:40px;border-radius:50%;background:#0d526b;'+
                'border:2px solid #bde8ee;color:white;display:grid;place-items:center;'+
                'font:700 14px system-ui;box-shadow:0 2px 10px #0004">'+count+'</div>'});
        }""",
    ).add_to(group)


class RadarControl(MacroElement):
    """Opacity is display-only, separate from detection and evidence data."""
    _template = Template('''
    {% macro script(this, kwargs) %}
    (function() {
        const map = {{ this.map_name }}, radar = {{ this.radar_name }};
        const control = L.control({position:'bottomleft'});
        control.onAdd = function() {
            const box = L.DomUtil.create('div');
            box.style.cssText='background:#fff;color:#193547;border-radius:10px;padding:10px 12px;max-width:235px;box-shadow:0 2px 12px #0003;font:12px system-ui';
            const label = L.DomUtil.create('label','',box);
            label.textContent='Độ đậm ảnh radar: ';
            const output = L.DomUtil.create('span','',label); output.textContent='82%';
            const slider = L.DomUtil.create('input','',label);
            slider.type='range'; slider.min='0'; slider.max='100'; slider.value='82';
            slider.setAttribute('aria-label','Độ đậm ảnh radar'); slider.style.width='100%';
            slider.oninput = function() {
                output.textContent=slider.value+'%';
                radar.eachLayer(function(layer) {if(layer.setOpacity) layer.setOpacity(Number(slider.value)/100);});
            };
            const hint=L.DomUtil.create('div','',box);
            hint.textContent='Cụm số = số điểm cần kiểm tra. Bấm để mở rộng.';
            hint.style.cssText='margin-top:4px;line-height:1.4';
            L.DomEvent.disableClickPropagation(box); L.DomEvent.disableScrollPropagation(box);
            return box;
        };
        control.addTo(map);
    })();
    {% endmacro %}
    ''')

    def __init__(self, chart, radar):
        super().__init__()
        self.map_name = chart.get_name()
        self.radar_name = radar.get_name()


def add_radar_control(chart, radar):
    return RadarControl(chart, radar).add_to(chart)
