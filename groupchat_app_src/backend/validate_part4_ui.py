"""Opt-in real browser acceptance; requires Playwright and installed Edge.

For Android first forward the active Chrome debugging socket to localhost:9223.
Uses an admin JWT only in memory/local browser storage, never reports.
Real submissions use the configured OpenAI account.
"""
import argparse
import asyncio
import json

from playwright.sync_api import sync_playwright

from database import ROOT
from validate_part4_real import admin_token


def prepare(page, credential, origin):
    page.goto(origin, wait_until='networkidle')
    page.evaluate('(value) => localStorage.setItem("token", value)', credential)
    page.reload(wait_until='networkidle')
    page.locator('#drivingPanel').wait_for(state='visible')
    page.wait_for_function('document.getElementById("drivingLibrary").children.length === 3')
    assert page.title() == 'California Driving Test Assistant'
    assert page.locator('#drivingStatus').inner_text() == ''


def ask(page, question):
    page.locator('#newDrivingChatBtn').click()
    page.locator('#drivingQuestion').fill(question)
    page.locator('#askDrivingBtn').click()
    page.wait_for_function('document.querySelectorAll("#drivingMessages .bot").length === 1', timeout=180000)
    answer = page.locator('#drivingMessages .bot').inner_text()
    assert page.locator('#drivingMessages .sources summary').count() > 0
    page.reload(wait_until='networkidle')
    page.wait_for_function('document.querySelectorAll("#drivingMessages .bot").length === 1')
    assert page.locator('#drivingMessages .bot').inner_text() == answer
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    return answer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--android', action='store_true')
    args = parser.parse_args()
    origin = (ROOT / 'logs/tunnel-url.txt').read_text().strip()
    credential = asyncio.run(admin_token())
    report_path = ROOT / 'artifacts/reports/Part4-ui-validation.json'
    report_path.parent.mkdir(parents=True, exist_ok=True)
    (ROOT / 'artifacts/screenshots').mkdir(parents=True, exist_ok=True)
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    with sync_playwright() as playwright:
        if args.android:
            browser = playwright.chromium.connect_over_cdp('http://127.0.0.1:9223')
            page = next(p for c in browser.contexts for p in c.pages if p.url.startswith(origin))
            prepare(page, credential, origin)
            answer = ask(page, 'What are some English commands an examiner may give during a Class C road test?')
            page.screenshot(path=str(ROOT / 'artifacts/screenshots/Part4-android-page.png'), full_page=True)
            report['android'] = {'passed': True, 'origin': origin, 'answer': answer, 'history_after_reload': True, 'no_horizontal_overflow': True}
            # Do not close a user's Chrome browser through the CDP connection.
        else:
            browser = playwright.chromium.launch(channel='msedge', headless=True)
            context = browser.new_context(viewport={'width': 1280, 'height': 1000})
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            prepare(page, credential, origin)
            answer = ask(page, 'What steps should I take before changing lanes?')
            assert 'blind' in answer.lower()
            page.screenshot(path=str(ROOT / 'artifacts/screenshots/Part4-desktop.png'), full_page=True)
            page.locator('#documentsTab').click()
            page.locator('#documentsPanel').wait_for(state='visible')
            page.locator('#groupTab').click()
            page.locator('#groupPanel').wait_for(state='visible')
            page.locator('#drivingTab').click()
            page.locator('#drivingPanel').wait_for(state='visible')
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(ROOT / 'artifacts/screenshots/Part4-mobile.png'), full_page=True)
            assert not errors, errors
            report['web'] = {'passed': True, 'origin': origin, 'desktop_and_mobile': True, 'history_after_reload': True, 'all_three_modes': True, 'no_horizontal_overflow': True, 'page_errors': errors}
            browser.close()
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('PASS:', 'Android emulator driving Q&A and reload history' if args.android else 'Desktop/mobile browser, cited answer, history, and all three modes', flush=True)


if __name__ == '__main__':
    main()
