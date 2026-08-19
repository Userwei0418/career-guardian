def crawl_page(page):
    """
    点击新的分页按钮，只翻一页
    """
    next_btns = page.query_selector_all("div.fr.module-page-switch a")
    for next_btn in next_btns:
        if "下一页" in next_btn.inner_text():
            next_btn.click()
            page.wait_for_timeout(500)  # 等待页面刷新
            print("已翻到下一页")
            return True


    else:
        print("没有找到下一页按钮或已到最后一页")
        return False
