"""Compatibility and routing checks for the restricted canonical adapter."""
import copy,unittest
from canonical_engine import CanonicalEngine
from canonical_outfit import stage_outfit

class CanonicalChecks(unittest.TestCase):
    def setUp(self):
        self.e=object.__new__(CanonicalEngine)
        self.e.items={f'outfit:{i}':{'key':f'outfit:{i}','id':i,'c':'outfit','h':[10]} for i in range(1,5)}
        self.e.assets=set();self.e.general={'outfits':{}}
        for i in range(1,5):
            route={'path':f'assets/{i}.prefab','bundle':'body'};self.e.assets.add(route['path'])
            self.e.general['outfits'][str(i)]={'temps':[{'id':i,'body_size':1,'parts':[{'id':i,'battle':route,'wardrobe':route}]}]}
        self.e.row=lambda table,section,id: {'_FootType':1} if section.endswith('ActorTemp') else {
            '_HairID':0,'_FacePartReplace':0,'_OrnamentConfigIDs':None,'_EnableTranslucentFunc':False,'_TranslucentDisableDefault':False}
        self.pair={'source':'outfit:1','target':'outfit:2','hero':10}

    def test_valid_same_bundle_pair(self):self.assertEqual(self.e.validate([self.pair]),[])
    def test_wrong_hero(self):
        with self.assertRaisesRegex(ValueError,'selected hero'):self.e.validate([dict(self.pair,hero=11)])
    def test_cross_bundle(self):
        self.e.general['outfits']['2']['temps'][0]['parts'][0]['battle']['bundle']='other'
        with self.assertRaisesRegex(ValueError,'Cross-bundle'):self.e.validate([self.pair])
    def test_split_templates(self):
        self.e.general['outfits']['2']['temps'][0]['parts'][0]['wardrobe']={'path':'other'}
        with self.assertRaisesRegex(ValueError,'Separate wardrobe'):self.e.validate([self.pair])
    def test_shared_source_paths(self):
        self.e.general['outfits']['3']=copy.deepcopy(self.e.general['outfits']['1'])
        with self.assertRaisesRegex(ValueError,'share the same source'):
            self.e.validate([self.pair,{'source':'outfit:3','target':'outfit:4','hero':10}])
    def test_target_context_reuse(self):
        with self.assertRaisesRegex(ValueError,'same target root'):
            self.e.validate([self.pair,{'source':'outfit:3','target':'outfit:2','hero':10}])
    def test_advanced_items_blocked(self):
        self.e.items['outfit:2']['fm']={'forms':[1]}
        with self.assertRaisesRegex(ValueError,'dedicated appearance'):self.e.validate([self.pair])
    def test_options_and_boolean_variant(self):
        for opts in ({'variant':True},{'private_path':'x'}):
            with self.assertRaises(ValueError):self.e.validate([dict(self.pair,options=opts)])
    def test_changed_battle_lookup_rejected_before_session_access(self):
        self.e.row=lambda *args:{'_PrefabPath':'canonical','_UICharacterPrefabPath':'canonical'}
        class Common:
            def get(self,*args):return {'_PrefabPath':'private','_UICharacterPrefabPath':'canonical'}
        with self.assertRaisesRegex(ValueError,'Canonical source lookup'):
            stage_outfit(self.e,None,Common(),self.e.general,1,2,10)

if __name__=='__main__':unittest.main(verbosity=2)
