def crawl_page(page, action="next"):
    btn = page.locator("div[ng-click=\"onPagingClick('next')\"]")
    if not btn.get_attribute("class").count("disable"):
        btn.click()
        return True
    else:
        print("到最后一页了")
        return False

