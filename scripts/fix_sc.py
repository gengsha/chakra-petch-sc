import sys
from fontTools.ttLib import TTFont
f=TTFont(sys.argv[1]); g=f['GSUB'].table; fl=g.FeatureList
keep=[i for i,fr in enumerate(fl.FeatureRecord) if fr.FeatureTag not in ('locl','liga','dlig')]; remap={o:n for n,o in enumerate(keep)}
fl.FeatureRecord=[fl.FeatureRecord[i] for i in keep]; fl.FeatureCount=len(keep)
for sr in g.ScriptList.ScriptRecord:
    for ls in [sr.Script.DefaultLangSys]+[l.LangSys for l in sr.Script.LangSysRecord]:
        if ls is None: continue
        ls.FeatureIndex=[remap[i] for i in ls.FeatureIndex if i in remap]; ls.FeatureCount=len(ls.FeatureIndex)
        if ls.ReqFeatureIndex!=0xFFFF: ls.ReqFeatureIndex=remap.get(ls.ReqFeatureIndex,0xFFFF)
f.save(sys.argv[1])
