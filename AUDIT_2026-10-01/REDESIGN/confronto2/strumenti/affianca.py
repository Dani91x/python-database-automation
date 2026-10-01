# Immagine affiancata: prototipo | pagina col guscio acceso (v2), stessa larghezza
# di partenza (1600), ridotte a meta' e affiancate; tavolozza a 256 colori per
# tenere leggero il repo. Uso:
#   python3 affianca.py <prototipo.png> <v2.png> <uscita.png> [altezza_max=3600]
import sys
from PIL import Image
P, V, OUT = sys.argv[1:4]; HMAX = int(sys.argv[4]) if len(sys.argv) > 4 else 3600
a = Image.open(P).convert('RGB'); b = Image.open(V).convert('RGB')
def mezzo(im):
    w = 800; h = round(im.height * w / im.width)
    return im.resize((w, h), Image.LANCZOS)
a, b = mezzo(a), mezzo(b)
h = min(max(a.height, b.height), HMAX)
tela = Image.new('RGB', (a.width + b.width + 8, h), (40, 40, 40))
tela.paste(a.crop((0, 0, a.width, min(a.height, h))), (0, 0))
tela.paste(b.crop((0, 0, b.width, min(b.height, h))), (a.width + 8, 0))
tela.quantize(256).save(OUT, optimize=True)
print(OUT, tela.size)
