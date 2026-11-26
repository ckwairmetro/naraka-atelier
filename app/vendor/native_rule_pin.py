"""Pin native numeric rule evaluation without reproducing shuffle/interpolation.

All valid original numeric codes gain an implicit leading zero by increasing
usedDigitCount by one. Each rule reads that zero and its band endpoints are
translated by minus the requested subnumber. Offsets/counts and native shader
reference values are unchanged. Runtime acceptance remains an experiment.
"""
import copy


def pin_rule_config(old,code):
    n=old['usedDigitCount']
    if len(code)!=n or not code.isdecimal() or not 0<n<18:
        raise ValueError('Unsupported code width')
    new=copy.deepcopy(old)
    new['usedDigitCount']=n+1
    proof=[]
    for gi,g in enumerate(old['ruleGroups']):
        for ri,r in enumerate(g['ruleDatas']):
            a,b=r['ruleIndexRange']['x'],r['ruleIndexRange']['y']
            if not 0<=a<=b<n:
                raise ValueError('Original digit range invalid')
            v=int(code[a:b+1])
            selected=[j for j,s in enumerate(r['subRules']) if s['subRuleStartNumber']<=v<=s['subRuleEndNumber']]
            if not selected:
                raise ValueError('Requested subnumber outside native rule bands')
            nr=new['ruleGroups'][gi]['ruleDatas'][ri]
            nr['ruleIndexRange']={'x':0,'y':0}
            for j,(s,t) in enumerate(zip(r['subRules'],nr['subRules'])):
                t['subRuleStartNumber']=s['subRuleStartNumber']-v
                t['subRuleEndNumber']=s['subRuleEndNumber']-v
                if not -(2**31)<=t['subRuleStartNumber']<=t['subRuleEndNumber']<2**31:
                    raise ValueError('Translated interval exceeds signed int32')
                if {k for k in s if s[k]!=t[k]}-{'subRuleStartNumber','subRuleEndNumber'}:
                    raise ValueError('Native interpolation/colour data changed')
            picked=[j for j,s in enumerate(nr['subRules']) if s['subRuleStartNumber']<=0<=s['subRuleEndNumber']]
            if picked!=selected:
                raise ValueError('Native band selection not preserved')
            for band in selected:
                s=r['subRules'][band];t=nr['subRules'][band]
                if (v-s['subRuleStartNumber'],s['subRuleEndNumber']-s['subRuleStartNumber'])!=(0-t['subRuleStartNumber'],t['subRuleEndNumber']-t['subRuleStartNumber']):
                    raise ValueError('Interpolation offset/span mismatch')
            s=r['subRules'][selected[0]];t=nr['subRules'][selected[0]]
            # Shader shuffle uses the same offset, count and iteration salt.
            # Its returned integer differs only by the same interval shift.
            for permutation_value in range(512):
                old_output=s['subRuleStartNumber']+permutation_value
                new_output=t['subRuleStartNumber']+permutation_value
                signed=lambda x:((x+2**31)%2**32)-2**31
                if signed(new_output)!=signed(old_output-v):
                    raise ValueError('Signed shuffle translation mismatch')
            proof.append({'group':gi,'rule':ri,'requested_subnumber':v,'original_range':[s['subRuleStartNumber'],s['subRuleEndNumber']],
                          'translated_range':[t['subRuleStartNumber'],t['subRuleEndNumber']],
                          'native_shuffle_preserved':bool(r['shuffleIndex']),'native_mode':s['interpolation'],'kind':s['paramType'],
                          'selected_bands_preserved_in_original_order':selected})
    for k in old:
        if k not in ('usedDigitCount','ruleGroups') and new[k]!=old[k]:
            raise ValueError('Rule application/reference metadata changed')
    # The maximum original-width numeric input also reads leading digit zero.
    for value in (0,1,int(code),10**n-1):
        if (value%(10**(n+1)))//10**n!=0:
            raise ValueError('Leading-zero selector proof failed')
    return new,{'method':'native-evaluated interval translation','requested_code':code,'original_width':n,'authored_width':n+1,
                'rules':proof,'shader_particle_gameobject_references_unchanged':True,
                'note':'Static arithmetic proof; native iFix paths/optimization and runtime rendering still require observation.'}
