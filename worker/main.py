import asyncio
import random


from playwright.async_api import async_playwright
import pytz
import loguru


import helpers
import xpaths
import connection
import constants


async def scrape_linkedin(
        worker_id: int, *args, **kwargs
) -> list:
    """
    Scrape LinkedIn job postings for different countries.

    :param worker_id: ID of the worker executing the scraping.
    :param used_countries: List of countries that have been used in previous
           scraping.

    :return: List of used countries after scraping.
    """
    try:
        async with async_playwright() as driver:
            info, is_done = helpers.get_country_and_job()
            if is_done == 1:
                loguru.logger.info("Sleeping for 30 minutes, since all jobs have been scraped")
                asyncio.sleep(60*30)
            loguru.logger.info(f"[WORKER {worker_id}] This round is: {info}")
            country, job = info
            browser = await driver.firefox.launch(
                headless=True,
                args=[
                    '--start-maximized',
                    '--foreground',
                    '--disable-backgrounding-occluded-windows'
                ],
                firefox_user_prefs=constants.FIREFOX_SETTINGS
            )

            timezone_id = random.choice(pytz.all_timezones)
            context = await browser.new_context(
                timezone_id=timezone_id,
                accept_downloads=True,
                is_mobile=False,
                has_touch=False,
                proxy=helpers.get_random_proxy()
            )

            page = await context.new_page()
            await page.bring_to_front()
            await page.set_viewport_size(
                {
                    "width": 1920,
                    "height": 1080
                }
            )

            await page.add_init_script(
                constants.SPOOF_FINGERPRINT % helpers.generate_device_specs()
            )
            await page.goto(helpers.get_url(location=country, job=job))
            all_ads = await page.locator(xpaths.JOB_LI).all()
            loguru.logger.info(f"[WORKER {worker_id}] Found {len(all_ads)} Advertisements")
            exists = 0
            for index, div in enumerate(all_ads):
                await asyncio.sleep(2)
                if index == 100 or exists == 7:
                    break
                await div.click(
                    timeout=5000
                )
                title_a_tag = page.locator(xpaths.JOB_ID_A_TAG)
                ads_id = await title_a_tag.get_attribute('href')
                ads_id = ads_id.split("?refId")[0].split("-")[-1]
                if not helpers.does_ads_exists(ads_id):
                    company_name = await helpers.safe_get_element_text(
                        page, xpaths.COMPANY_NAME, timeout=5000
                    )
                    location = await helpers.safe_get_element_text(
                        page, xpaths.LOCATION, timeout=5000
                    )
                    title = await helpers.safe_get_element_text(
                        page, xpaths.TITLE, timeout=5000
                    )
                    await page.locator(xpaths.SHOW_MORE).click(timeout=5000)
                    info = await helpers.get_element_text(
                        page, xpaths.BODY_INFO, False, timeout=5000
                    )
                    await connection.create_ads(
                        ads_id, location, info.strip(), company_name,
                        title, 1, employement_type="", level="",
                        country=country,
                    )
                    loguru.logger.info(
                        f"[WORKER {worker_id}] Finished {ads_id}"
                    )

                else:
                    loguru.logger.info(
                        f"[WORKER {worker_id}] {ads_id} Already exists"
                    )
                    exists += 1

        return
    except Exception:
        return await scrape_linkedin(worker_id)


async def run_scrapers(workers: int = 1):
    while True:
        tasks = []
        for i in range(workers):
            tasks.append(asyncio.create_task(scrape_linkedin(worker_id=i+1)))
            asyncio.sleep(random.randint(1, 3))  # Overhead of browsers launch
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    used_countries = asyncio.run(run_scrapers(workers=5))
