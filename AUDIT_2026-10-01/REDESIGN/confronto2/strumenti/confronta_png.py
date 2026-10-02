# Confronto pixel per pixel di due cartelle di screenshot (stessi nomi), con Pillow.
# Uso: python3 confronta_png.py <cartellaA> <cartellaB> [filtro]
import sys, os
from PIL import Image, ImageChops
A, B = sys.argv[1], sys.argv[2]; F = sys.argv[3] if len(sys.argv) > 3 else ''
tutti = True
for n in sorted(x for x in os.listdir(A) if x.endswith('.png') and F in x):
    a = Image.open(os.path.join(A, n)).convert('RGB'); b = Image.open(os.path.join(B, n)).convert('RGB')
    if a.size != b.size:
        tutti = False; print(n, 'dimensioni diverse', a.size, b.size); continue
    d = ImageChops.difference(a, b); box = d.getbbox()
    if box is None: print(n, 'identica'); continue
    tutti = False
    n_px = sum(1 for p in d.getdata() if p != (0, 0, 0))
    print(n, 'pixel diversi', n_px, 'riquadro', box)
print('IDENTICHE' if tutti else 'DIFFERENZE')
