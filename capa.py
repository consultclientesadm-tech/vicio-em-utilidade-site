import json,sys
from PIL import Image,ImageDraw,ImageFont,ImageFilter
F='/usr/share/fonts/truetype/higgsfield/Montserrat-ExtraBold.ttf'
W,H=1080,1920
def fit(img,w,h):
    r=min(w/img.width,h/img.height);return img.resize((int(img.width*r),int(img.height*r)),Image.LANCZOS)
def cover(img,w,h):
    r=max(w/img.width,h/img.height);i=img.resize((int(img.width*r)+1,int(img.height*r)+1));x=(i.width-w)//2;y=(i.height-h)//2;return i.crop((x,y,x+w,y+h))
def make(k,photo,lines,hl,nota,out):
    im=Image.open(photo).convert('RGB')
    bg=cover(im,W,H).filter(ImageFilter.GaussianBlur(40))
    bg=Image.blend(bg,Image.new('RGB',(W,H),(15,15,18)),0.55)
    d=ImageDraw.Draw(bg)
    # headline
    y=300
    for i,t in enumerate(lines):
        size=100
        while True:
            f=ImageFont.truetype(F,size)
            if d.textlength(t,font=f)<=980 or size<56: break
            size-=4
        tw=d.textlength(t,font=f)
        col=(255,214,0) if i==hl else (255,255,255)
        d.text(((W-tw)/2,y),t,font=f,fill=col,stroke_width=6,stroke_fill=(0,0,0))
        y+=size+18
    # card
    top=max(y+30,700); bot=1430
    ph=fit(im,920,bot-top-40)
    cw,ch=ph.width+40,ph.height+40
    cx=(W-cw)//2; cy=top+((bot-top)-ch)//2
    sh=Image.new('RGBA',(W,H),(0,0,0,0));ImageDraw.Draw(sh).rounded_rectangle((cx+8,cy+14,cx+cw+8,cy+ch+14),36,fill=(0,0,0,140))
    bg.paste(sh.filter(ImageFilter.GaussianBlur(14)),(0,0),sh.filter(ImageFilter.GaussianBlur(14)))
    d=ImageDraw.Draw(bg)
    d.rounded_rectangle((cx,cy,cx+cw,cy+ch),36,fill=(255,255,255))
    m=Image.new('L',ph.size,0);ImageDraw.Draw(m).rounded_rectangle((0,0,ph.width,ph.height),24,fill=255)
    bg.paste(ph,(cx+20,cy+20),m)
    # pill
    f=ImageFont.truetype(F,52);t=f'NOTA {nota} NA SHOPEE'
    stars='★★★★★'
    tw=d.textlength(t,font=f);py=1470
    d.rounded_rectangle(((W-tw)/2-44,py,(W+tw)/2+44,py+96),48,fill=(255,87,34))
    d.text(((W-tw)/2,py+18),t,font=f,fill=(255,255,255))
    try: fs=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',58)
    except: fs=f
    sw=d.textlength(stars,font=fs);d.text(((W-sw)/2,py+112),stars,font=fs,fill=(255,214,0))
    fb=ImageFont.truetype(F,34);b='VÍCIO EM UTILIDADE · eu garimpo, você aproveita'
    d.text(((W-d.textlength(b,font=fb))/2,1720),b,font=fb,fill=(255,255,255))
    bg.save(out,quality=90)
cfg=json.load(open(sys.argv[1]))
for c in cfg: make(**c,out=f"capa_{c['k']}.jpg")