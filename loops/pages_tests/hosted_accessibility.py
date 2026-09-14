"""Measured rendered checks for the affected buttons and prose/footer links."""
import re

def luminance(color):
    rgb=[float(x)/255 for x in re.findall(r'[\d.]+',color)[:3]]
    assert len(rgb)==3, 'Unknown computed color format'
    return sum(w*(v/12.92 if v<=0.04045 else ((v+.055)/1.055)**2.4) for w,v in zip([.2126,.7152,.0722],rgb))

def inspect(page):
    rows=page.locator('.btn:visible,main a:not(.btn):visible,footer a:visible').evaluate_all('''es=>es.map(e=>{
      const c=getComputedStyle(e);let bg=null;
      for(let p=e;p;p=p.parentElement){const b=getComputedStyle(p).backgroundColor;if(b.startsWith('rgb(')){bg=b;break;}}
      return {button:e.classList.contains('btn'),height:e.getBoundingClientRect().height,color:c.color,background:bg,underline:c.textDecorationLine.includes('underline')};
    })''')
    assert rows and any(not r['button'] for r in rows), 'No prose/footer links measured'
    for row in rows:
        assert row['background'], 'Background unavailable; contrast UNKNOWN'
        a,b=sorted([luminance(row['color']),luminance(row['background'])])
        row['contrast']=(b+.05)/(a+.05)
        assert row['contrast']>=4.5, 'Text contrast below 4.5: '+str(row)
        if row['button']:assert row['height']>=44
        else:assert row['underline'], 'Prose/footer link indistinguishable from text'
    return rows
