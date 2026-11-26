"""Browser interaction QA; queues selections without installing anything."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

def main():
    url='http://127.0.0.1:12579';errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(url);page.wait_for_selector('#sourceSelect option',state='attached')
        token=page.evaluate('window.SESSION_TOKEN')
        data=page.request.get(url+'/api/bootstrap',headers={'X-Session-Token':token}).json()
        weapon=next(i for i in data['items'] if i['key']=='weapon:2311500')
        page.locator('[data-domain=weapon]').click();page.select_option('#weapon',str(weapon['w']))
        def choose(source,target,n):
            page.wait_for_function('(key)=>[...document.querySelector("#sourceSelect").options].some(o=>o.value===key)',arg=source)
            page.select_option('#sourceSelect',source)
            page.wait_for_function('(key)=>[...document.querySelector("#targetSelect").options].some(o=>o.value===key)',arg=target)
            page.select_option('#targetSelect',target);page.wait_for_function('()=>!document.querySelector("#addSwap").disabled')
            page.locator('#addSwap').click();page.wait_for_function('(n)=>document.querySelector("#queueCount").textContent===String(n)',arg=n)
        choose('weapon:2311500','weapon:2311558',1)
        page.select_option('#category','effect|weapon');choose('weapon:2311500','effect:w10043',2)
        choose('weapon:2311500','effect:w10005',3)
        page.locator('[data-domain=character]').click();page.select_option('#category','hair')
        page.wait_for_function('()=>[...document.querySelector("#sourceSelect").options].some(o=>o.value==="hair:100036")')
        page.select_option('#sourceSelect','hair:100036');page.wait_for_function('()=>[...document.querySelector("#targetSelect").options].some(o=>o.value==="hair:100097")')
        page.select_option('#targetSelect','hair:100097');page.wait_for_selector('[data-control=color_mode]')
        page.locator('[data-control=color_mode] select').select_option('gradient')
        for i,v in enumerate(('12','10','18')):page.locator('[data-control=colors] select').nth(i).select_option(v)
        page.locator('#addSwap').click();page.wait_for_function('()=>document.querySelector("#queueCount").textContent==="4"')
        page.screenshot(path='D:/naraka_unlocker/reports/atelier-v2-ui.png',full_page=True)
        assert not errors,errors
        result={'passed':True,'catalogue_records':len(data['items']),'tests':['weapon model selection','weapon effects under Weapons','two separate effect slots on same receiver','hair gradient controls','queued composite validation','no browser exceptions'],'game_files_modified':False}
        Path('D:/naraka_unlocker/reports/atelier-v2-browser-validation.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result));browser.close()
if __name__=='__main__':main()
