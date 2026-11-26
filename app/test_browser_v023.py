"""Receiver/set/progress browser checks. Game writes are never requested."""
import json,sys,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

def main():
    state=Path(sys.argv[1] if len(sys.argv)>1 else 'D:/naraka_unlocker/work/atelier-v023-qa');checks=[];errors=[];real_mutations=[];deadline=time.monotonic()+30
    while True:
        try:
            url=json.loads((state/'session.json').read_text())['url'];urllib.request.urlopen(url,timeout=2).close();break
        except (OSError,ValueError):
            if time.monotonic()>deadline:raise
            time.sleep(.2)
    with sync_playwright() as p:
        browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:real_mutations.append(r.url) if r.url.endswith(('/api/recover',)) else None)
        page.goto(url);page.wait_for_function('()=>document.querySelector("#buildChip").textContent.includes("verified")',timeout=60000)
        token=page.evaluate('()=>window.SESSION_TOKEN');headers={'X-Session-Token':token};data=page.request.get(url+'/api/bootstrap',headers=headers).json();items={i['key']:i for i in data['items']}
        def check(n,c):assert c,n;checks.append(n)
        def ready():page.wait_for_function('()=>!document.querySelector("#addSwap").disabled')
        def target(k):page.select_option('#targetSelect',k);ready();page.wait_for_selector('#weaponEffectsGrid .effect-group',state='attached') if items[k]['c']=='weapon' else None
        def clear():
            if not page.locator('#clearQueue').is_visible():page.locator('[data-tab=compose]').click()
            page.locator('#clearQueue').click()
        check('all 60 saved selections preserved',len(data['profile']['selections'])==60)
        page.select_option('#category','effect|outfit');page.wait_for_selector('[data-collection=hero]')
        check('Matari-specific defeat effects first',page.locator('[data-collection=hero] .card .id').all_text_contents()==['o10002'])
        check('other compatible effects below',page.locator('[data-collection=other] .card').count()>30)
        check('automatic outfit assignment disables manual source',page.locator('#sourceSelect').is_disabled() and page.locator('#sourceSelect').input_value()=='outfit:3400127')
        page.locator('#autoReceiver').uncheck();check('manual override remains available',page.locator('#sourceSelect').is_enabled());page.locator('#autoReceiver').check()
        page.select_option('#category','outfit');ready();page.select_option('#sourceSelect','outfit:3400100');ready();target('outfit:3400117');page.locator('#addSwap').click();page.wait_for_function('()=>Number(document.querySelector("#queueCount").textContent)>0')
        page.select_option('#category','effect|outfit');page.wait_for_function('()=>document.querySelector("#sourceSelect").value==="outfit:3400100"')
        check('pending outfit wins automatic receiver assignment',page.locator('#sourceSelect').is_disabled());clear();page.wait_for_function('()=>document.querySelector("#sourceSelect").value==="outfit:3400127"')
        check('clearing pending restores installed outfit assignment',page.locator('#sourceSelect').input_value()=='outfit:3400127')
        page.locator('[data-domain=weapon]').click();page.select_option('#weapon',str(items['weapon:2311558']['w']));ready();page.select_option('#sourceSelect','weapon:2311522');ready();target('weapon:2311558');page.wait_for_selector('#weaponEffectsGrid [data-key="effect:w10043"]')
        check('weapon effects appear on skin page',page.locator('#category option[value="effect|weapon"]').count()==0 and page.locator('#weaponEffectsPanel').is_visible())
        page.locator('#weaponEffectsGrid [data-key="effect:w10043"]').click();page.wait_for_function('()=>document.querySelector("#queueCount").textContent==="2"')
        check('Longxiang exclusive queued together with required model','龙骧' in page.locator('#queueRows').inner_text())
        clear();target('weapon:2311547');page.wait_for_selector('#weaponEffectsGrid [data-key="effect:w10043"]',state='detached');check('actual native controller requirement retained',page.locator('#weaponEffectsGrid [data-key="effect:w10043"]').count()==0)
        page.select_option('#weapon',str(items['weapon:2311837']['w']));ready();check('Universe Slash absent from dual halberds',page.locator('#weaponEffectsGrid [data-key="effect:w10005"]').count()==0)
        page.select_option('#weapon',str(items['weapon:2314008']['w']));ready();page.select_option('#sourceSelect','weapon:2314016');ready();target('weapon:2314008');page.wait_for_selector('#weaponEffectsGrid [data-key="effect:w10046"]');check('tested cross-copy not blocked by catalogue purchase rule',page.locator('#weaponEffectsGrid [data-key="effect:w10046"]').count()==1)
        page.locator('[data-tab=active]').click();check('weapon effects are nested properties',page.locator('#managedRows .weapon-property').count()==sum(i['target'].startswith('effect:w') for i in data['profile']['selections']))
        page.locator('#refreshVisuals').click();page.wait_for_function('()=>document.querySelector("#queueCount").textContent==="14"');check('refresh queues current weapon visuals without replacing effects',page.locator('#activeCount').inner_text()=='60');clear();page.locator('[data-tab=active]').click()
        page.locator('[data-tab=compose]').click();page.select_option('#weapon',str(items['weapon:2310049']['w']));ready();page.select_option('#sourceSelect','weapon:2310032');ready();target('weapon:2310049')
        check('standalone colours automatic without a dropdown',page.locator('[data-control=preview_colours]').count()==0)
        check('every number slot shows valid range',page.locator('[data-control=numbers] .input-range').count()==4)
        slots=page.locator('[data-control=numbers] input');slots.nth(0).fill('1000');page.locator('#addSwap').click();check('invalid slot prevented from entering queue',page.locator('#queueCount').inner_text()=='0')
        slots.nth(0).fill('999');page.locator('#addSwap').click();page.wait_for_function('()=>document.querySelector("#queueCount").textContent==="1"')
        fake={'build':{'ok':False,'errors':[],'version':'1.5.9.2','fingerprint_files':17},'profile':data['profile'],'pending':True,'job':{'id':'job-one','busy':True,'percent':42,'message':'Packing verified candidate','error':None}}
        ack={'id':'job-one','busy':True,'percent':2,'message':'Checking client','error':None};apply_calls=[];page.route('**/api/apply',lambda route:(apply_calls.append(True),route.fulfill(json={'started':True,'job':ack})))
        page.route('**/api/status',lambda route:route.fulfill(json=fake));page.locator('#apply').click();page.wait_for_selector('#applyProgress',state='visible');page.wait_for_function('()=>document.querySelector("#progressPercent").textContent==="42%"')
        check('apply shows modal numerical progress',page.locator('#progressClose').is_disabled());check('validation completed before apply',len(apply_calls)==1)
        fake['pending']=False;fake['build']['ok']=True;fake['job']={'id':'job-one','busy':False,'percent':100,'message':'Completed','error':None,'result':{'files':2,'unchanged_files':5,'reused_bundles':4}}
        page.wait_for_function('()=>document.querySelector("#progressPercent").textContent==="100%"');check('completion reports actual changed-file count','2 files written' in page.locator('#progressSummary').inner_text());page.locator('#progressClose').click()
        # Hold an old completed status request across the second submission.
        page.unroute('**/api/status');stale=[]
        def status_route(route):
            if not stale:stale.append(route)
            else:route.fulfill(json=fake)
        page.route('**/api/status',status_route);page.evaluate('()=>{void poll();}')
        for _ in range(60):
            if stale:break
            page.wait_for_timeout(50)
        check('previous status request held before next apply',len(stale)==1)
        page.locator('#addSwap').click();page.wait_for_function('()=>document.querySelector("#queueCount").textContent==="1"')
        validation=[];page.route('**/api/validate',lambda route:validation.append(route));page.locator('#apply').click()
        check('second validation starts at zero without previous completion',page.locator('#progressPercent').inner_text()=='0%' and page.locator('#progressTitle').inner_text()=='Applying changes' and page.locator('#progressSummary').inner_text()=='' and page.locator('#progressClose').is_disabled())
        page.evaluate('()=>poll()');check('old completion cannot render while submitting',page.locator('#progressPercent').inner_text()=='0%')
        ack={'id':'job-two','busy':True,'percent':2,'message':'Checking client','error':None};validation[0].fulfill(json={'valid':True});page.wait_for_function('()=>expectedJobId==="job-two"&&!operationStarting');page.unroute('**/api/validate')
        stale[0].fulfill(json=fake);page.wait_for_function('()=>!checking')
        check('late previous status neither completes nor clears second queue',page.locator('#progressPercent').inner_text()=='2%' and page.locator('#progressTitle').inner_text()=='Applying changes' and page.locator('#queueCount').inner_text()=='1' and page.locator('#progressSummary').inner_text()=='')
        fake['job']={'id':'job-two','busy':True,'percent':3,'message':'Compiling 1/72 · outfit 3400153','error':None};page.evaluate('()=>poll()')
        check('second compile shows its own live percentage and title',page.locator('#progressPercent').inner_text()=='3%' and page.locator('#progressTitle').inner_text()=='Applying changes' and page.locator('#progressClose').is_disabled())
        fake['job']['percent']=2;page.evaluate('()=>poll()');check('progress is monotonic within this job only',page.locator('#progressPercent').inner_text()=='3%')
        fake['job']={'id':'job-two','busy':False,'percent':100,'message':'Completed','error':None,'result':{'files':1,'unchanged_files':6,'reused_bundles':5}};page.evaluate('()=>poll()')
        check('second completion shows only second file counts',page.locator('#progressPercent').inner_text()=='100%' and '1 files written' in page.locator('#progressSummary').inner_text() and '5 verified bundles' in page.locator('#progressSummary').inner_text());page.locator('#progressClose').click()
        page.locator('#addSwap').click();page.wait_for_function('()=>document.querySelector("#queueCount").textContent==="1"');page.route('**/api/validate',lambda route:route.fulfill(status=400,json={'error':'Deliberate test validation rejection'}));page.locator('#apply').click();page.wait_for_function('()=>document.querySelector("#progressTitle").textContent==="Validation stopped"');page.evaluate('()=>poll()')
        check('validation rejection cannot be replaced by previous success',page.locator('#progressTitle').inner_text()=='Validation stopped' and page.locator('#progressPercent').inner_text()=='0%' and page.locator('#progressSummary').inner_text()=='' and page.locator('#queueCount').inner_text()=='1');page.locator('#progressClose').click();page.unroute('**/api/status');page.unroute('**/api/validate')
        check('no page exceptions',not errors);check('no recovery endpoint invoked',not real_mutations)
        page.screenshot(path='D:/naraka_unlocker/reports/atelier-v023-ui.png',full_page=True);page.request.post(url+'/api/shutdown',headers=headers,data='{}');browser.close()
    result={'passed':True,'checks':checks,'count':len(checks),'apply_was_browser_mock_only':True,'game_files_modified':False};Path('D:/naraka_unlocker/reports/atelier-v023-'+state.name+'-ui.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=='__main__':main()
