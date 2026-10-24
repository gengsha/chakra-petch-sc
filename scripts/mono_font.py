import sys, math
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.pointPen import SegmentToPointPen
from fontTools.pens.recordingPen import RecordingPointPen

SRC, OUT, STYLE = sys.argv[1], sys.argv[2], sys.argv[3]
HALF, FULL, SB, K = 550, 1100, 30, 0.85

f = TTFont(SRC)
glyf = f['glyf']; hmtx = f['hmtx']; gs = f.getGlyphSet()
cmap = f.getBestCmap()
# stem width from 'l'
lg = glyf[cmap[ord('l')]]; STEM = lg.xMax - lg.xMin
print('stem', STEM)

def contours_of(name):
    rec = DecomposingRecordingPen(gs); gs[name].draw(rec)
    cs = []; cur = None
    for op, args in rec.value:
        if op == 'moveTo': cur = [(args[0], True)]
        elif op == 'lineTo': cur.append((args[0], True))
        elif op == 'qCurveTo':
            pts = list(args)
            if pts[-1] is None: pts = pts[:-1]; cur = cur or []
            for p in pts[:-1]: cur.append((p, False))
            cur.append((pts[-1], True))
        elif op == 'curveTo':
            for p in args[:-1]: cur.append((p, False))
            cur.append((args[-1], True))
        elif op in ('closePath', 'endPath'):
            if cur and len(cur) > 1 and cur[0][0] == cur[-1][0]: cur.pop()
            if cur and len(cur) >= 2: cs.append(cur)
            cur = None
    return cs

def sgn(v):
    return 0 if abs(v) < 1e-6 else (1 if v > 0 else -1)

def xbold(cs, d):
    if d <= 0.5: return cs
    out = []
    for c in cs:
        n = len(c); res = []
        for i in range(n):
            (p, _), (q, on), (r, _) = c[i-1], c[i], c[(i+1) % n]
            e1 = (q[0]-p[0], q[1]-p[1]); e2 = (r[0]-q[0], r[1]-q[1])
            s1 = sgn(-e1[1]); s2 = sgn(-e2[1])  # outward normal x = -dy
            if s1 == 0: s1 = s2
            if s2 == 0: s2 = s1
            if s1 == s2 or not on:
                s = s1 if s1 == s2 else 0
                res.append(((q[0]+s*d, q[1]), on))
            else:
                res.append(((q[0]+s1*d, q[1]), on)); res.append(((q[0]+s2*d, q[1]), on))
        out.append(res)
    return out

def xform(cs, s, dx):
    return [[((p[0]*s+dx, p[1]), on) for p, on in c] for c in cs]

def build(cs):
    pen = TTGlyphPen(None)
    pp = pen  # use point pen API
    from fontTools.pens.ttGlyphPen import TTGlyphPointPen
    ppen = TTGlyphPointPen(None)
    for c in cs:
        ppen.beginPath()
        for (x, y), on in c:
            ppen.addPoint((round(x), round(y)), 'line' if on else None)
        ppen.endPath()
    return ppen.glyph()

def bounds(cs):
    xs = [p[0] for c in cs for p, _ in c]
    return (min(xs), max(xs)) if xs else (0, 0)

full_set = set()
for u, g in cmap.items():
    if hmtx[g][0] >= 900: full_set.add(g)

from fontTools.ttLib.tables import ttProgram
done = 0
for g in f.getGlyphOrder():
    adv = hmtx[g][0]
    if adv == 0:  # combining marks: leave
        continue
    target = FULL if adv >= 900 else HALF
    cs = contours_of(g)
    if not cs:
        hmtx[g] = (target, 0); glyf[g] = build([]); continue
    x0, x1 = bounds(cs); w = x1 - x0
    T = target - 2*SB if target == HALF else target
    if target == FULL:
        cs2 = xform(cs, 1, (FULL - adv)/2)
    elif w > T:
        st = min(STEM, w*0.4)
        s = (T - K*st)/(w - K*st)
        d = K*st*(1-s)/2
        cs2 = xbold(xform(cs, s, 0), d)
        a, b = bounds(cs2); cs2 = xform(cs2, 1, (HALF-(b-a))/2 - a)
    else:
        cs2 = xform(cs, 1, (HALF - w)/2 - x0)
    gl = build(cs2)
    p = ttProgram.Program(); p.fromBytecode(b''); gl.program = p
    glyf[g] = gl
    gl.recalcBounds(glyf)
    hmtx[g] = (target, gl.xMin if gl.numberOfContours else 0)
    done += 1
print('glyphs', done)

# slashed zero
zg = cmap[ord('0')]; zc = contours_of(zg)
if len(zc) >= 2:
    def area(c):
        return sum(c[i-1][0][0]*c[i][0][1]-c[i][0][0]*c[i-1][0][1] for i in range(len(c)))/2
    hole = min(zc, key=lambda c: abs(area(c)))
    xs=[p[0] for p,_ in hole]; ys=[p[1] for p,_ in hole]
    ix0,ix1,iy0,iy1=min(xs),max(xs),min(ys),max(ys)
    t = 0.8*STEM; mx=0.16*(ix1-ix0); my=0.1*(iy1-iy0)
    ax,ay,bx,by = ix0+mx+t/2, iy0+my, ix1-mx-t/2, iy1-my
    slash=[((ax-t/2,ay),True),((bx-t/2,by),True),((bx+t/2,by),True),((ax+t/2,ay),True)]
    gl = build(zc+[slash]); p = ttProgram.Program(); p.fromBytecode(b''); gl.program = p
    glyf[zg] = gl; gl.recalcBounds(glyf)
# distinguish I and l
def rect(x0,y0,x1,y1):
    return [((x0,y0),True),((x0,y1),True),((x1,y1),True),((x1,y0),True)]
def setg(name, cs):
    gl = build(cs); p = ttProgram.Program(); p.fromBytecode(b''); gl.program = p
    glyf[name] = gl; gl.recalcBounds(glyf); hmtx[name] = (HALF, gl.xMin)
bar = 0.8*STEM
gI = cmap[ord('I')]; cI = contours_of(gI); x0,x1 = bounds(cI)
ys=[p[1] for c in cI for p,_ in c]; cap=max(ys); cx=(x0+x1)/2; w=HALF*0.62
setg(gI, cI+[rect(cx-w/2,0,cx+w/2,bar), rect(cx-w/2,cap-bar,cx+w/2,cap)])
gl_ = cmap[ord('l')]; cl = contours_of(gl_); x0,x1 = bounds(cl); ys=[p[1] for c in cl for p,_ in c]; top=max(ys)
foot = HALF*0.26
sh = -foot/2
cl = xform(cl,1,sh); x0+=sh; x1+=sh
setg(gl_, cl+[rect(x1-2,0,x1+foot,bar), rect(x0-foot*0.8,top-bar,x0+2,top)])
# curved-ish parens (distinct from [ ])
gp = cmap[ord('(')]; cp_ = contours_of(gp)
xs=[p[0] for c in cp_ for p,_ in c]; ys=[p[1] for c in cp_ for p,_ in c]
L_, R_, B_, T_ = min(xs), max(xs), min(ys), max(ys)
t = STEM; xl = L_; xr = R_ - t; k = 2.4*(xr-xl)
par = [((xr,B_),True),((xl,B_+k),True),((xl,T_-k),True),((xr,T_),True),((xr+t,T_),True),((xl+t,T_-k),True),((xl+t,B_+k),True),((xr+t,B_),True)]
setg(gp, [par])
cx = HALF/2
mir = [((2*cx-x, y),on) for (x,y),on in reversed(par)]
setg(cmap[ord(')')], [mir])
# drop ligature features (bad for code)
if 'GSUB' in f:
    fl = f['GSUB'].table.FeatureList
    keep = [i for i,fr in enumerate(fl.FeatureRecord) if fr.FeatureTag not in ('liga','dlig','clig','calt','locl')]
    remap = {old:new for new,old in enumerate(keep)}
    fl.FeatureRecord = [fl.FeatureRecord[i] for i in keep]; fl.FeatureCount = len(keep)
    for sr in f['GSUB'].table.ScriptList.ScriptRecord:
        langs = [sr.Script.DefaultLangSys] + [l.LangSys for l in sr.Script.LangSysRecord]
        for ls in langs:
            if ls is None: continue
            ls.FeatureIndex = [remap[i] for i in ls.FeatureIndex if i in remap]; ls.FeatureCount = len(ls.FeatureIndex)
            if ls.ReqFeatureIndex != 0xFFFF: ls.ReqFeatureIndex = remap.get(ls.ReqFeatureIndex, 0xFFFF)
f['post'].isFixedPitch = 1
f['OS/2'].panose.bProportion = 9
f['OS/2'].xAvgCharWidth = HALF
f['hhea'].advanceWidthMax = FULL
if 'GPOS' in f: del f['GPOS']
# drop GSUB features that change widths (halt/palt/vpal etc.) - keep the rest
if 'GSUB' in f: pass

fam = 'Chakra Petch SC Mono'
name = f['name']
name.names = [n for n in name.names if n.nameID not in (1, 2, 3, 4, 6, 16, 17)]
def setn(i, s):
    name.setName(s, i, 3, 1, 0x409); name.setName(s, i, 1, 0, 0)
RIBBI = STYLE in ('Regular', 'Bold'); zh = 'Chakra Petch 中文等宽'
setn(1, fam if RIBBI else f'{fam} {STYLE}'); setn(2, STYLE if RIBBI else 'Regular')
setn(3, f'{fam} {STYLE};2026'); setn(4, f'{fam} {STYLE}')
setn(6, (fam + '-' + STYLE).replace(' ', ''))
name.setName(zh if RIBBI else f'{zh} {STYLE}', 1, 3, 1, 0x804); name.setName(STYLE if RIBBI else 'Regular', 2, 3, 1, 0x804)
if not RIBBI:
    setn(16, fam); setn(17, STYLE); name.setName(zh, 16, 3, 1, 0x804); name.setName(STYLE, 17, 3, 1, 0x804)
f.save(OUT); print('saved', OUT)
