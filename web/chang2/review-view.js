'use strict';

window.SonarNetReviewView = (() => {
function svgNode(name,attributes,text) {
  const node=document.createElementNS('http://www.w3.org/2000/svg',name);
  for(const [key,value] of Object.entries(attributes)) node.setAttribute(key,value);
  if(text!==undefined)node.textContent=text;
  return node;
}

function plot(panel,xs,ys,xLabel,yLabel,equalScale=false) {
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


function evidence(track, speed, observations, sample) {
  plot(track,sample.east_m,sample.north_m,'Đông tương đối (m)','Bắc tương đối (m)',true);
  plot(speed,sample.elapsed_min,sample.speed_kn,'Thời gian (phút)','Tốc độ (kn)');
  observations.textContent=sample.speed_kn.length+' bản tin trong '+sample.elapsed_min.at(-1)+
    ' phút · Tốc độ gần nhất '+sample.speed_kn.at(-1)+' kn · Hướng gần nhất '+sample.course_deg.at(-1)+'°.';
}

function hintText(sample) {
  return 'Gợi ý mô hình: '+(sample.hint_priority?'ưu tiên rà':'chưa ưu tiên')+
    ' · Mẫu dự đoán '+sample.hint_class.toLowerCase()+'. Bạn tự quyết định dựa trên quỹ đạo.';
}

return {evidence,hintText};
})();
