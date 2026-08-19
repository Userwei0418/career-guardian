def crawl_page(page):
    try:
        # 1. 点击「士兰集科」
        more_btn = page.locator("div.join-button", has_text="查看更多")
        more_btn.wait_for(state="visible", timeout=5000)
        more_btn.click()

        return True

    except Exception as e:
        print("点击流程异常:", e)
        return False
