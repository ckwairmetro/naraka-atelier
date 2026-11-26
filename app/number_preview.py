"""Read-only numbered material colour study, with explicit unsupported cases.

Evidence: recovered LogicSubRule readers, RandomMaterialVisual.CacheDataByID,
and the RGB lattice implementation used in the original fixed-bow experiment.
This previews rule colours, not the final textured/illuminated game model.
"""
import gzip,json,math,struct
from functools import lru_cache

def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]

@lru_cache(maxsize=32)
def load(path):
    with gzip.open(path,'rt',encoding='utf8') as f:return json.load(f)

def rgba32(value):return [(value['rgba']>>(8*i))&255 for i in range(4)]
def vector(value):return [value[k] for k in 'xyzw']

def endpoints(sub,kind):
    return ([rgba32(sub[k]) for k in ('color32StartValue','color32EndValue')] if kind==5
            else [vector(sub[k]) for k in ('vectorStartValue','vectorEndValue')])

def evaluate(rule,sub,value):
    """Return rule-space colour or None; never substitute an invented shuffle."""
    a,b=endpoints(sub,rule['paramType']);mode=sub['interpolation']
    lo,hi=sub['subRuleStartNumber'],sub['subRuleEndNumber']
    if mode==0 or a==b:return a,'constant'
    if rule['shuffleIndex'] and value not in (lo,hi):return None,'Native shuffle is not evaluated in this preview.'
    if mode in (1,3,5):
        t=0.0 if value<=lo else 1.0 if value>=hi else f32(f32(value-lo)/f32(hi-lo))
        if mode==5:t=f32(f32(t*t)*f32(3-f32(2*t)))
        result=[f32(x+f32(f32(y-x)*t)) for x,y in zip(a,b)]
        if rule['paramType']==5:result=[int(x)&255 for x in result]
        return result,'smooth' if mode==5 else 'linear'
    if mode==2 and rule['paramType']==5:
        # Native per-channel RGB lattice; not a straight line between colours.
        dims=[abs(y-x)+1 for x,y in zip(a[:3],b[:3])]
        index=round(f32(f32(f32(value-lo)/f32(hi-lo+1))*f32(math.prod(dims))))
        xyz=[index%dims[0],(index//dims[0])%dims[1],index//(dims[0]*dims[1])]
        if any(n>=limit for n,limit in zip(xyz,dims)):return None,'RGB lattice boundary needs game verification.'
        rgb=[x+((y>x)-(y<x))*n for x,y,n in zip(a,b,xyz)]
        return [*rgb,0],'rgb-lattice'
    return None,('HSV lattice is not evaluated in this preview.' if mode==4
                 else 'HDR lattice is not evaluated in this preview.' if mode==2
                 else 'Unsupported native interpolation.')

def display(value,kind):
    rgb=value[:3];peak=max(0.0,*rgb)
    if kind==5:rgb=[v/255 for v in rgb]
    else:
        # Hue-preserving exposure for HDR; keep original strength in metadata.
        rgb=[max(0,v)/max(1,peak) for v in rgb]
        rgb=[12.92*v if v<=.0031308 else 1.055*v**(1/2.4)-.055 for v in rgb]
    return {'hex':'#'+''.join(f'{min(255,max(0,round(v*255))):02x}' for v in rgb),
            'strength':round(peak,3) if kind==6 else None}

def preview(engine,target,numbers=None):
    item=engine.items.get(target)
    if not item or not item.get('z'):raise ValueError('Select a numbered cosmetic')
    data=load(str(engine.resources/'rare_rules'/(str(item['id'])+'.json.gz')));tree=data['tree'];slots=item['z']['slots']
    if numbers is None:code=data['default_code']
    else:
        if not isinstance(numbers,list) or len(numbers)!=len(slots):raise ValueError('Provide one integer for each slot')
        digits=['0']*tree['usedDigitCount']
        for slot,value in zip(slots,numbers):
            lo,hi=slot['range']
            if type(value) is not int or not lo<=value<=hi:raise ValueError('Number outside the displayed slot range')
            a,b=slot['digitPos'];text=str(value).zfill(b-a+1)
            if len(text)!=b-a+1:raise ValueError('Number exceeds native digit width')
            digits[a:b+1]=text
        code=''.join(digits)
    groups=[];calculated=limited=0
    for gi,group in enumerate(tree['ruleGroups']):
        colours=[]
        for ri,rule in enumerate(group['ruleDatas']):
            a,b=rule['ruleIndexRange']['x'],rule['ruleIndexRange']['y'];value=int(code[a:b+1])
            # Native selection is first matching inclusive band.
            sub=next((s for s in rule['subRules'] if s['subRuleStartNumber']<=value<=s['subRuleEndNumber']),None)
            if sub is None:raise ValueError('Number falls outside an authored rule band')
            if rule['paramType'] not in (5,6):continue
            if sub['paramType']!=rule['paramType']:raise ValueError('Native colour type mismatch')
            result,method=evaluate(rule,sub,value);kind=rule['paramType'];starts,ends=endpoints(sub,kind)
            record={'id':f'{gi}:{ri}','name':rule['ruleName'] or f'Colour {ri+1}','hdr':kind==6,
                    'status':'calculated' if result is not None else 'endpoints','method':method,
                    'colour':display(result,kind) if result is not None else None,
                    'start':display(starts,kind),'end':display(ends,kind),
                    'band':[sub['subRuleStartNumber'],sub['subRuleEndNumber']]}
            colours.append(record)
            if result is None:limited+=1
            else:calculated+=1
        if colours:groups.append({'name':group['groupName'] or f'Part {gi+1}','colours':colours})
    return {'target':target,'code':code,'numbers':[int(code[s['digitPos'][0]:s['digitPos'][1]+1]) for s in slots],
            'groups':groups,'calculated':calculated,'endpoints_only':limited,'approximate':True,
            'note':'Material palette only. Textures, lighting, reference colours and effects can change the final appearance. HDR brightness is normalized for this screen.'}
