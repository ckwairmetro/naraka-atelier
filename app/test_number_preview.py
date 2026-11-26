import unittest,tempfile,json,types
from pathlib import Path
from number_preview import evaluate,preview,display

def rule(kind=5,mode=1,start=0xff000000,end=0xffffffff,shuffle=0):
    sub={'interpolation':mode,'subRuleStartNumber':0,'subRuleEndNumber':10,
         'color32StartValue':{'rgba':start},'color32EndValue':{'rgba':end},
         'vectorStartValue':dict(zip('xyzw',[0,0,0,1])),
         'vectorEndValue':dict(zip('xyzw',[2,1,.5,1]))}
    return {'paramType':kind,'shuffleIndex':shuffle},sub

class ColourMathTests(unittest.TestCase):
    def test_packed_channels_and_constant(self):
        r,s=rule(mode=0,start=0x44332211);self.assertEqual(evaluate(r,s,5)[0],[17,34,51,68])
    def test_linear_and_smooth(self):
        r,s=rule();self.assertEqual(evaluate(r,s,5)[0],[127,127,127,255])
        s['interpolation']=5;self.assertEqual(evaluate(r,s,0)[0],[0,0,0,255]);self.assertEqual(evaluate(r,s,10)[0],[255,255,255,255])
        self.assertLess(evaluate(r,s,2)[0][0],51)
    def test_rgb_lattice_is_not_lerp(self):
        r,s=rule(mode=2,start=0xff000000,end=0xff010101);s['subRuleEndNumber']=7
        self.assertEqual(evaluate(r,s,1)[0],[1,0,0,0]);self.assertEqual(evaluate(r,s,2)[0],[0,1,0,0]);self.assertEqual(evaluate(r,s,4)[0],[0,0,1,0])
    def test_shuffle_is_never_guessed(self):
        r,s=rule(shuffle=1);self.assertIsNone(evaluate(r,s,5)[0]);self.assertEqual(evaluate(r,s,10)[0],[255,255,255,255])
        s['interpolation']=0;self.assertIsNotNone(evaluate(r,s,5)[0])
    def test_unsupported_lattices_explicit(self):
        r,s=rule(mode=4);self.assertIsNone(evaluate(r,s,5)[0]);r,s=rule(kind=6,mode=2);self.assertIsNone(evaluate(r,s,5)[0])
    def test_hdr_exposure_preserves_strength(self):
        d=display([4,0,0,1],6);self.assertEqual(d,{'hex':'#ff0000','strength':4})
        self.assertEqual(display([.5,.5,.5,1],6)['hex'],'#bcbcbc')
    def test_reversed_channel_lattice(self):
        r,s=rule(mode=2,start=0xff000001,end=0xff000000);s['subRuleEndNumber']=1
        self.assertEqual(evaluate(r,s,0)[0],[1,0,0,0]);self.assertEqual(evaluate(r,s,1)[0],[0,0,0,0])

if __name__=='__main__':unittest.main(verbosity=2)
