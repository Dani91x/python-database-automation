import urllib.request
from PIL import Image
import os
import requests

url = 'https://tempfile.aiquickdraw.com/workers/nano/image_1771878846709_tuiox4.jpg'
filename = 'C:/Users/Admin/.gemini/antigravity/brain/90ec1ba9-0c45-466a-a21e-2dd392528d94/final_real_logo2.jpg'
transpname = 'final_transp2.png'

try:
    print('Downloading user logo...')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response, open(filename, 'wb') as out_file:
        out_file.write(response.read())
        
    print('Opening image to verify...', filename)
    img = Image.open(filename).convert('RGBA')
    datas = img.getdata()
    
    # Process transp
    newData = []
    for item in datas:
        if item[0] < 45 and item[1] < 45 and item[2] < 45: 
            newData.append((255, 255, 255, 0))
        else:
            newData.append(item)
            
    img.putdata(newData)
    
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
        
    img.save(transpname)
    print('Transparent logo saved.')

    # Catbox upload
    print('Uploading to catbox...')
    with open(transpname, 'rb') as f:
        r = requests.post('https://catbox.moe/user/api.php', data={'reqtype': 'fileupload'}, files={'fileToUpload': f})
        print(r.text)

except Exception as e:
    print(f'Error: {e}')
