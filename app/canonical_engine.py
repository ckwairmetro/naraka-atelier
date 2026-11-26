"""Restricted app adapter for the accepted canonical outfit route.

Not yet the packaged launcher's engine. Build on preserved sources only;
the inherited installer retains its fingerprint/closed-client/rollback guards.
"""
from core import Engine
from generalized import GeneralizedEngine
from canonical_outfit import stage_outfit


class CanonicalEngine(GeneralizedEngine):
    def outfit_reason(self,item):
        if any(item.get(k) for k in ('z','fm','lv','_folded')):
            return 'Numbered, switchable-form and upgrade outfits require their dedicated appearance adapter'
        info=self.general['outfits'].get(str(item['id']))
        if not info or info.get('placeholder') or not info.get('temps'):
            return 'No resolved native outfit template'
        for t in info['temps']:
            if len(t['parts'])!=1:return 'Split main-body templates require a dedicated adapter'
            p=t['parts'][0]
            if not p.get('battle') or not p['battle'].get('path'):return 'Missing battle prefab'
            if (p.get('wardrobe') or p['battle'])['path']!=p['battle']['path']:
                return 'Separate wardrobe/battle prefabs require a dedicated adapter'
            if p['battle']['path'] not in self.assets:return 'Outfit resource is missing from the installed build'
        return None

    def intrinsic(self,item):
        if item['c']=='outfit':return self.outfit_reason(item)
        return super().intrinsic(item)

    def compatible(self,src,tgt,hero=None):
        if src['c']!=tgt['c'] or src['c']!='outfit':return super().compatible(src,tgt,hero)
        if src['key']==tgt['key']:return 'Choose a different target'
        for i in (src,tgt):
            reason=self.outfit_reason(i)
            if reason:return reason
        if hero is None or int(hero) not in set(src.get('h',[]))&set(tgt.get('h',[])):
            return 'Both outfits must support the selected hero'
        return self.variant_reason(src,tgt,0)

    def variant_reason(self,src,tgt,variant):
        a=self.general['outfits'][str(src['id'])]['temps'][0]
        b=self.general['outfits'][str(tgt['id'])]['temps'][variant]
        if a['body_size']!=b['body_size']:return 'Native body families differ'
        if a['parts'][0]['battle']['bundle']!=b['parts'][0]['battle']['bundle']:
            return 'Cross-bundle outfit substitution is not yet implemented'
        if self.row('CharacterConfig','CharacterConfig_ActorTemp',a['id'])['_FootType']!=self.row('CharacterConfig','CharacterConfig_ActorTemp',b['id'])['_FootType']:
            return 'This target variant needs different native foot metadata'
        sa=self.row('FashionConfig','FashionConfig_FashionBody',src['id'])
        ta=self.row('FashionConfig','FashionConfig_FashionBody',tgt['id'])
        for k in ('_HairID','_FacePartReplace','_OrnamentConfigIDs','_EnableTranslucentFunc','_TranslucentDisableDefault'):
            if sa[k]!=ta[k]:return 'Target needs additional outfit attachment or visibility handling: '+k
        return None

    def recipes(self,s):
        if self.items[s['target']]['c']=='outfit':return []
        return super().recipes(s)

    def validate(self,selections):
        jobs=super().validate(selections);sources={};targets=set()
        for s in selections:
            a,b=self.items[s['source']],self.items[s['target']]
            if b['c']!='outfit':continue
            opts=s.get('options',{})
            if set(opts)-{'variant'}:raise ValueError('Unknown outfit options')
            variant=opts.get('variant',0)
            if type(variant) is not int:raise ValueError('Outfit variant must be an integer')
            reason=self.variant_reason(a,b,variant)
            if reason:raise ValueError(reason)
            source=self.general['outfits'][str(a['id'])]['temps'][0]['parts'][0]['battle']['path']
            target=self.general['outfits'][str(b['id'])]['temps'][variant]['parts'][0]['battle']['path']
            if source in sources:raise ValueError('Two selected outfits share the same source prefab; independent swaps would conflict')
            if target in targets:raise ValueError('The same target root cannot use two source binding contexts')
            sources[source]=target;targets.add(target)
        if set(sources)&targets:raise ValueError('Chained/shared outfit root aliases are not supported')
        return jobs

    def _outfit(self,s,session,common,bindings,proof):
        self.validate([s])
        proof.append(stage_outfit(self,session,common,self.general,
                                 self.items[s['source']]['id'],self.items[s['target']]['id'],
                                 int(s['hero']),s.get('options',{}).get('variant',0)))
