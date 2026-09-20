#!/usr/bin/env python3
"""Generate visual-review candidates; a perceptual hash never proves scene isolation."""
import argparse,json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
c=np.cos(np.pi*(np.arange(32)[None,:]+.5)*np.arange(8)[:,None]/32)
def ph(path):
 image=np.asarray(Image.open(path).convert('L').resize((32,32)),dtype=float);x=(c@image@c.T).flatten()[1:];return x>np.median(x)
train=sorted((a.dataset/'images/train').glob('*.jpg'));hashes=np.array([ph(path) for path in train])
for split in ['test','val']:
 rows=[]
 for path in sorted((a.dataset/'images'/split).glob('*.jpg')):
  distances=np.count_nonzero(hashes!=ph(path),axis=1);j=int(distances.argmin());rows.append({split:path.name,'train':train[j].name,'phash_hamming63':int(distances[j])})
 rows.sort(key=lambda r:r['phash_hamming63']);(a.output/f'{split}-nearest.json').write_text(json.dumps(rows,indent=2)+'\n');sheet=Image.new('RGB',(1200,1000),'white');draw=ImageDraw.Draw(sheet)
 for k,r in enumerate(rows[:8]):
  x=k%2*600;y=k//2*250;draw.text((x,y),str(r),fill='black')
  for j,s in enumerate([split,'train']):
   image=Image.open(a.dataset/'images'/s/r[s]);image.thumbnail((295,220));sheet.paste(image,(x+j*300,y+25))
 sheet.save(a.output/f'{split}-nearest.jpg',quality=90)
 print(split,rows[:8])
