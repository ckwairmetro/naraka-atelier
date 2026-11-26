"""UI regression checks against a private server. Never calls apply/recover."""
import json,sys
from pathlib import Path
from playwright.sync_api import sync_playwright

def main():
    state=Path(sys.argv[1] if len(sys.argv)>1 else 'D:/naraka_unlocker/work/atelier-v021-qa')
    url=json.loads((state/'session.json').read_text())['url'];checks=[];requests=[];errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1050})
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:requests.append((r.method,r.url,r.post_data)))
        page.goto(url);page.wait_for_function('()=>document.querySelector("#buildChip").textContent.includes("verified")',timeout=60000)
        token=page.evaluate('()=>window.SESSION_TOKEN');headers={'X-Session-Token':token}
        data=page.request.get(url+'/api/bootstrap',headers=headers).json();items={i['key']:i for i in data['items']}
        def check(name,condition):
            assert condition,name;checks.append(name)
        def values(id):return page.locator('#'+id+' option').evaluate_all('(es)=>es.map(e=>e.value)')
        def ready():page.wait_for_function('()=>!document.querySelector("#addSwap").disabled')
        def target(key):
            page.wait_for_function('(k)=>[...document.querySelector("#targetSelect").options].some(o=>o.value===k)',arg=key)
            page.select_option('#targetSelect',key);page.wait_for_function('(k)=>document.querySelector("#targetSelect").value===k&&!document.querySelector("#addSwap").disabled',arg=key)
        def clear():
            if not page.locator('#clearQueue').is_visible():page.locator('[data-tab=compose]').click()
            page.locator('#clearQueue').click()
        def added():page.locator('#addSwap').click();page.wait_for_function('()=>Number(document.querySelector("#queueCount").textContent)>0')
        check('28 installed swaps preserved',len(data['profile']['selections'])==28)
        page.select_option('#quality','4');ready();check('target dropdown follows rarity',all(items[k]['q']==4 for k in values('targetSelect')))
        check('source independent of target rarity',page.locator('#sourceSelect').input_value()=='hair:100036')
        page.select_option('#sourceQuality','3');ready();check('source dropdown follows own rarity',all(items[k]['q']==3 for k in values('sourceSelect')))
        page.select_option('#sourceQuality','');page.select_option('#quality','');ready()
        qualities=[items[k]['q'] for k in values('targetSelect')];check('target dropdown sorted high to low',qualities==sorted(qualities,reverse=True))
        target('hair:100076');check('no-override hides all colour inputs',page.locator('#dyeFields select:visible,#dyeFields input:visible').count()==0)
        modes=page.locator('[data-control=color_mode] option').evaluate_all('(es)=>es.map(e=>e.value)');check('non-highlight hairstyle hides highlights','streaks' not in modes)
        page.select_option('[data-control=color_mode] select','plain');check('solid has one colour editor only',page.locator('#dyeFields input:visible').count()==1 and page.locator('#dyeFields input[type=color]').count()==1 and page.locator('#dyeFields select:visible').count()==0 and page.locator('[data-control=sliders]:visible').count()==0)
        page.select_option('[data-control=color_mode] select','flourish');check('flourish has one selector only',page.locator('#dyeFields select:visible').count()==1 and page.locator('#dyeFields input:visible').count()==0)
        page.select_option('#dyeFields select','36');added()
        calls=[json.loads(body) for method,u,body in requests if u.endswith('/api/validate')]
        hair=next(s for s in calls[-1]['selections'] if s['source']=='hair:100036')
        check('flourish payload retained with no irrelevant fields',hair['options']=={'color_mode':'flourish','colors':[36]})
        check('pending summary shows finish and colour','多彩·库金' in page.locator('#queueRows').inner_text())
        check('ink-wash treatment is disclosed',page.locator('#appearanceTreatment').is_visible())
        clear();target('hair:100097');page.select_option('[data-control=color_mode] select','gradient')
        check('gradient exposes only three colours and three sliders',page.locator('#dyeFields select:visible').count()==3 and page.locator('#dyeFields input:visible').count()==3)
        for n,v in enumerate(['12','10','18']):page.locator('#dyeFields select').nth(n).select_option(v)
        added();check('gradient summary is explicit','碧落 / 多彩·浅云 / 哑光·晴山' in page.locator('#queueRows').inner_text() and '35/38/100' in page.locator('#queueRows').inner_text())
        clear();target('hair:100038');page.select_option('[data-control=color_mode] select','streaks')
        check('highlights use named native groups',page.locator('[data-group]').count()>1 and page.locator('[data-control=regions]').count()==0)
        g=page.locator('[data-group]').nth(1);g.locator('[data-enable]').check();g.locator('[data-part=colors] select').select_option('36');added()
        check('highlight summary names the group','挑染部位' in page.locator('#queueRows').inner_text())
        clear();page.select_option('#category','pose');page.wait_for_function('()=>document.querySelector("#targetSelect").options.length>0')
        check('poses under character and hero-specific',all(1000004 in items[k]['h'] for k in values('targetSelect')))
        page.locator('[data-domain=environment]').click();check('poses removed from environment','pose' not in values('category'))
        page.locator('[data-domain=character]').click();page.select_option('#category','skill');page.wait_for_selector('#targetGrid [data-key="skill:104001"]')
        check('skill effects grouped by six native abilities',page.locator('#targetGrid .effect-group').count()==6)
        page.locator('#targetGrid [data-key="skill:104001"]').click();page.wait_for_function('()=>document.querySelector("#queueCount").textContent==="1"')
        check('linked selections shown across ability variants',page.locator('#targetGrid .card[aria-pressed=true]').count()==3)
        page.locator('#targetGrid [data-key="skill:104004"]').click();page.wait_for_function('()=>document.querySelector("#queueCount").textContent==="2"')
        check('independent skill and ultimate families coexist',page.locator('#targetGrid .card[aria-pressed=true]').count()==6)
        page.locator('#targetGrid [data-key="skill:104004"]').click();page.wait_for_function('()=>document.querySelector("#queueCount").textContent==="1"')
        page.locator('#targetGrid [data-key="skill:104002"]').click();page.wait_for_function('()=>document.querySelector("#queueCount").textContent==="0"');check('linked selection toggles off',page.locator('#targetGrid .card[aria-pressed=true]').count()==0)
        page.locator('[data-domain=weapon]').click();page.select_option('#weapon',str(items['weapon:2311500']['w']));page.wait_for_function('()=>[...document.querySelector("#sourceSelect").options].some(o=>o.value==="weapon:2311500")');page.select_option('#sourceSelect','weapon:2311500');target('weapon:2311558');added()
        page.select_option('#category','effect|weapon');page.wait_for_selector('#targetGrid [data-key="effect:w10043"]');page.locator('#targetGrid [data-key="effect:w10043"]').click();page.wait_for_function('()=>document.querySelector("#queueCount").textContent==="2"');page.locator('#targetGrid [data-key="effect:w10005"]').click();page.wait_for_function('()=>document.querySelector("#queueCount").textContent==="3"')
        check('separate weapon combo slots coexist',page.locator('#targetGrid .card[aria-pressed=true]').count()==2)
        clear();page.wait_for_selector('#targetGrid [data-key="effect:w10043"]',state='detached');check('effect choices refresh when pending model is cleared',page.locator('#targetGrid [data-key="effect:w10043"]').count()==0)
        page.locator('[data-tab=active]').click();page.locator('#managedRows .row').filter(has_text='hair:100036').get_by_role('button',name='Edit',exact=True).click();page.wait_for_selector('#hairStudio');ready();check('installed no-override settings reopen accurately',page.locator('[data-control=color_mode] select').input_value()=='')
        page.locator('[data-tab=active]').click();page.locator('#managedRows .row').first.get_by_role('button',name='Remove',exact=True).click();check('removing installed swap queues removal',page.locator('#queueCount').inner_text()=='1')
        clear();page.locator('[data-tab=compose]').click()
        fake={'build':{'ok':False,'errors':['Resource differs during write'],'version':'1.5.9.2','fingerprint_files':17},'job':{'busy':True,'message':'Applying fixture','error':None},'profile':data['profile'],'pending':True}
        page.route('**/api/status',lambda route:route.fulfill(json=fake));page.evaluate('()=>poll()');page.wait_for_function('()=>document.querySelector("#buildChip").textContent.includes("Applying")')
        check('busy status hides false recovery and mismatch warnings',not page.locator('#recover').is_visible() and not page.locator('#buildErrors').is_visible() and page.locator('#apply').is_disabled())
        page.unroute('**/api/status');page.wait_for_function('()=>document.querySelector("#buildChip").textContent.includes("verified")')
        for hero in data['catalogue']['heroes']:
            source=next((i for i in data['items'] if i['c']=='pose' and hero['id'] in i.get('h',[])),None)
            if source:
                r=page.request.get(url+'/api/targets?source='+source['key']+'&hero='+str(hero['id'])+'&category=pose',headers=headers)
                assert r.ok
                assert all(hero['id'] in items[k]['h'] for k in r.json()['keys'])
        check('pose targets remain valid across all 30 heroes',len(data['catalogue']['heroes'])==30)
        page.screenshot(path=str(Path('D:/naraka_unlocker/reports')/('atelier-v021-'+state.name+'.png')),full_page=True)
        check('no apply or recover calls',not any(u.endswith(('/api/apply','/api/recover')) for _,u,_ in requests))
        check('no browser exceptions',not errors)
        page.request.post(url+'/api/shutdown',headers=headers,data='{}');browser.close()
    result={'passed':True,'checks':checks,'count':len(checks),'game_files_modified':False}
    Path('D:/naraka_unlocker/reports/atelier-v021-'+state.name+'-ui.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=='__main__':main()
