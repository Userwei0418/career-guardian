def crawl_page(page):
    from playwright.sync_api import sync_playwright
    import time


    # 查找可点击的“下一页”按钮
    next_button = page.query_selector('button.cursor-pointer:not([disabled])')

    if not next_button:
        print("已到最后一页，停止翻页。")
        return False
    # 点击按钮
    next_button.click()
    print("翻到下一页...")
    return True

