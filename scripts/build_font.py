import math, sys
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.basePen import decomposeQuadraticSegment

SRC = sys.argv[1] if len(sys.argv) > 1 else 'NotoSC-Bold.ttf'
LAT = sys.argv[2] if len(sys.argv) > 2 else '../cp.ttf'
OUT = sys.argv[3] if len(sys.argv) > 3 else 'ChakraPetchSC-Bold.ttf'
STYLE = sys.argv[4] if len(sys.argv) > 4 else 'Bold'
LIMIT = int(sys.argv[5]) if len(sys.argv) > 5 else 0
OUTER_C, HOLE_C, DP_TOL = (58, 34, 9.0) if STYLE=="Bold" else (48, 28, 8.0)

def qpt(p0, p1, p2, t):
    a = (1-t)**2; b = 2*(1-t)*t; c = t*t
    return (a*p0[0]+b*p1[0]+c*p2[0], a*p0[1]+b*p1[1]+c*p2[1])

def cpt(p0, p1, p2, p3, t):
    m = 1-t
    return (m**3*p0[0]+3*m*m*t*p1[0]+3*m*t*t*p2[0]+t**3*p3[0],
            m**3*p0[1]+3*m*m*t*p1[1]+3*m*t*t*p2[1]+t**3*p3[1])

def contours_from(rec):
    out = []; cur = None; start = None
    for op, args in rec:
        if op == 'moveTo':
            cur = [args[0]]; start = args[0]
        elif op == 'lineTo':
            cur.append(args[0])
        elif op == 'qCurveTo':
            pts = list(args)
            if pts[-1] is None:  # closed contour with only off-curves
                pts = pts[:-1]
                # implied on-curve start
                mid = ((pts[-1][0]+pts[0][0])/2, (pts[-1][1]+pts[0][1])/2)
                cur = [mid]; start = mid; pts = pts + [mid]
            p0 = cur[-1]
            for (c1, p2) in decomposeQuadraticSegment(pts):
                for i in range(1, 9):
                    cur.append(qpt(p0, c1, p2, i/8))
                p0 = p2
        elif op == 'curveTo':
            p0 = cur[-1]; c1, c2, p3 = args
            for i in range(1, 11):
                cur.append(cpt(p0, c1, c2, p3, i/10))
        elif op in ('closePath', 'endPath'):
            if cur:
                if len(cur) > 1 and dist(cur[0], cur[-1]) < 0.5:
                    cur.pop()
                if len(cur) >= 3:
                    out.append(cur)
            cur = None
    return out

def dist(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])

def dp(pts, tol):
    if len(pts) < 3: return pts
    a, b = pts[0], pts[-1]
    dx, dy = b[0]-a[0], b[1]-a[1]; L = math.hypot(dx, dy)
    best, idx = -1, 0
    for i in range(1, len(pts)-1):
        p = pts[i]
        d = abs(dy*(p[0]-a[0]) - dx*(p[1]-a[1]))/L if L > 1e-9 else dist(p, a)
        if d > best: best, idx = d, i
    if best > tol:
        return dp(pts[:idx+1], tol)[:-1] + dp(pts[idx:], tol)
    return [a, b]

def simplify_closed(pts, tol):
    # split at farthest pair from point 0 for closed DP
    n = len(pts)
    i0 = 0
    far = max(range(n), key=lambda i: dist(pts[0], pts[i]))
    a = dp(pts[:far+1], tol)
    b = dp(pts[far:] + [pts[0]], tol)
    res = a[:-1] + b[:-1]
    # remove near-collinear / duplicate points
    changed = True
    while changed and len(res) > 3:
        changed = False
        for i in range(len(res)):
            p, q, r = res[i-1], res[i], res[(i+1) % len(res)]
            if dist(p, q) < 1.5:
                res.pop(i); changed = True; break
            v1 = (q[0]-p[0], q[1]-p[1]); v2 = (r[0]-q[0], r[1]-q[1])
            cr = v1[0]*v2[1]-v1[1]*v2[0]
            l1, l2 = math.hypot(*v1), math.hypot(*v2)
            if l1*l2 > 0 and abs(cr)/(l1*l2) < 0.02 and v1[0]*v2[0]+v1[1]*v2[1] > 0:
                res.pop(i); changed = True; break
    return res

def area(pts):
    s = 0
    for i in range(len(pts)):
        x1, y1 = pts[i-1]; x2, y2 = pts[i]
        s += x1*y2 - x2*y1
    return s/2

def chamfer(pts, is_hole, outer_sign):
    n = len(pts); res = []
    for i in range(n):
        p, q, r = pts[i-1], pts[i], pts[(i+1) % n]
        v1 = (q[0]-p[0], q[1]-p[1]); v2 = (r[0]-q[0], r[1]-q[1])
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        if l1 < 1 or l2 < 1:
            res.append(q); continue
        cr = (v1[0]*v2[1]-v1[1]*v2[0])/(l1*l2)
        dt = (v1[0]*v2[0]+v1[1]*v2[1])/(l1*l2)
        turn = math.degrees(math.atan2(cr, dt))
        convex = (turn > 0) == (outer_sign > 0)
        ok = 55 <= abs(turn) <= 125
        if is_hole:
            # hole corners: in filled-region terms they are concave
            if ok and not convex:
                c = min(HOLE_C, 0.3*min(l1, l2))
                if c >= 8:
                    res.append((q[0]-v1[0]/l1*c, q[1]-v1[1]/l1*c))
                    res.append((q[0]+v2[0]/l2*c, q[1]+v2[1]/l2*c)); continue
        else:
            if ok and convex and min(l1, l2) > 150:
                c = min(OUTER_C, 0.28*min(l1, l2))
                res.append((q[0]-v1[0]/l1*c, q[1]-v1[1]/l1*c))
                res.append((q[0]+v2[0]/l2*c, q[1]+v2[1]/l2*c)); continue
        res.append(q)
    return res

def contains(poly, pt):
    x, y = pt; ins = False
    for i in range(len(poly)):
        x1, y1 = poly[i-1]; x2, y2 = poly[i]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y-y1)*(x2-x1)/(y2-y1): ins = not ins
    return ins

def transform(rec):
    cs = [simplify_closed(c, DP_TOL) for c in contours_from(rec)]
    cs = [c for c in cs if len(c) >= 3 and abs(area(c)) > 4]
    if not cs: return []
    big = max(cs, key=lambda c: abs(area(c)))
    outer_sign = 1 if area(big) > 0 else -1
    out = []
    for c in cs:
        a = area(c)
        is_hole = (a > 0) != (outer_sign > 0)
        out.append(chamfer(c, is_hole, outer_sign))
    return out

def draw(contours, glyphset):
    pen = TTGlyphPen(glyphset)
    for c in contours:
        pen.moveTo((round(c[0][0]), round(c[0][1])))
        for p in c[1:]:
            pen.lineTo((round(p[0]), round(p[1])))
        pen.closePath()
    return pen.glyph()

CJK_RANGES = [(0x2E80, 0x2FDF), (0x3000, 0x303F), (0x3040, 0x30FF), (0x3100, 0x312F),
              (0x3190, 0x31FF), (0x3200, 0x33FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF),
              (0xF900, 0xFAFF), (0xFE30, 0xFE4F), (0xFF00, 0xFFEF), (0x20000, 0x3FFFF)]

def in_cjk(u):
    return any(a <= u <= b for a, b in CJK_RANGES)

f = TTFont(SRC)
lat = TTFont(LAT)
gs = f.getGlyphSet(); glyf = f['glyf']; hmtx = f['hmtx']
cmap = f.getBestCmap()
rev = {}
for u, g in cmap.items(): rev.setdefault(g, []).append(u)

latin_cps = set()
lcm = lat.getBestCmap()
for u in lcm:
    if u < 0x2E80 and u in cmap: latin_cps.add(u)

# glyphs to transform: everything except glyphs mapped only to non-CJK codepoints
targets = []
for g in f.getGlyphOrder():
    us = rev.get(g)
    if g == '.notdef': continue
    if us and not any(in_cjk(u) for u in us): continue
    targets.append(g)
if LIMIT: targets = targets[:LIMIT]
print('transforming', len(targets), flush=True)

newglyphs = {}
for k, g in enumerate(targets):
    rec = DecomposingRecordingPen(gs); gs[g].draw(rec)
    newglyphs[g] = draw(transform(rec.value), gs)
    if k % 3000 == 0: print(k, flush=True)
for g, gl in newglyphs.items():
    glyf[g] = gl

# Latin from Chakra Petch: copy outlines + advance widths into Noto's slots
lgs = lat.getGlyphSet()
for u in latin_cps:
    tg = cmap[u]; sg = lcm[u]
    # don't overwrite a glyph shared with CJK codepoints
    if any(in_cjk(x) for x in rev.get(tg, [])): continue
    rec = DecomposingRecordingPen(lgs); lgs[sg].draw(rec)
    pen = TTGlyphPen(None); rec.replay(pen)
    glyf[tg] = pen.glyph()
    hmtx[tg] = (lat['hmtx'][sg][0], 0)
print('latin replaced', len(latin_cps), flush=True)

for tg in list(glyf.keys()):
    g = glyf[tg]
    if hasattr(g, 'program'):
        from fontTools.ttLib.tables import ttProgram
        p = ttProgram.Program(); p.fromBytecode(b''); g.program = p
    try: g.recalcBounds(glyf)
    except Exception: pass
# lsb sync
for g in f.getGlyphOrder():
    gl = glyf[g]
    adv, _ = hmtx[g]
    hmtx[g] = (adv, getattr(gl, 'xMin', 0) if gl.numberOfContours else 0)

if 'GPOS' in f: del f['GPOS']
for t in ('fpgm', 'prep', 'cvt ', 'gasp', 'hdmx', 'LTSH', 'VDMX', 'DSIG'):
    if t in f: del f[t]

fam = 'Chakra Petch SC'
name = f['name']
name.names = [n for n in name.names if n.nameID not in (1, 2, 3, 4, 6, 7, 16, 17, 21, 22, 25)]
def setn(i, s):
    name.setName(s, i, 3, 1, 0x409); name.setName(s, i, 1, 0, 0)
setn(0, 'Copyright 2018 The Chakra Petch Project Authors (https://github.com/m4rc1e/Chakra-Petch.git). Han glyphs derived from Noto Sans SC, (c) 2014-2021 Adobe, with Reserved Font Name \'Source\'. Modified 2026.')
RIBBI = STYLE in ('Regular', 'Bold')
zh = 'Chakra Petch 中文'
setn(1, fam if RIBBI else f'{fam} {STYLE}'); setn(2, STYLE if RIBBI else 'Regular')
setn(3, f'{fam} {STYLE};2026'); setn(4, f'{fam} {STYLE}'); setn(6, (fam+'-'+STYLE).replace(' ', ''))
setn(5, 'Version 1.000')
name.setName(zh if RIBBI else f'{zh} {STYLE}', 1, 3, 1, 0x804)
name.setName(STYLE if RIBBI else 'Regular', 2, 3, 1, 0x804)
if not RIBBI:
    setn(16, fam); setn(17, STYLE)
    name.setName(zh, 16, 3, 1, 0x804); name.setName(STYLE, 17, 3, 1, 0x804)
f.save(OUT)
print('saved', OUT)
