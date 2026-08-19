def crawl_page(page, target_page_num=None):
    """
    Playwright 翻页到指定页码，未指定时默认点击下一页
    """
    if target_page_num is None:
        # 点击下一页按钮
        next_btn = page.locator("form#pagination-doctor a.pagination-toLast")
        if next_btn.count() > 0 and "disabled" not in next_btn.first.get_attribute("class"):
            next_btn.first.click()
            page.wait_for_timeout(1000)
            print("已翻到下一页")
            return True
        else:
            print("没有找到下一页按钮或已到最后一页")
            return False

    # 如果指定了页码，则按原逻辑跳转
    locator = page.locator(f"form#pagination-doctor ul.pagination li a:text('{target_page_num}')")
    if locator.count() > 0:
        locator.first.click()
        page.wait_for_timeout(1000)
        print(f"已跳转到第 {target_page_num} 页")
        return True
    else:
        # 使用输入框跳转
        input_box = page.locator("form#pagination-doctor input.pagination-to")
        submit_btn = page.locator("form#pagination-doctor input.pagination-submit")
        if input_box.count() > 0 and submit_btn.count() > 0:
            input_box.fill(str(target_page_num))
            submit_btn.click()
            page.wait_for_timeout(1000)
            print(f"已通过输入框跳转到第 {target_page_num} 页")
            return True
        else:
            print(f"没有找到第 {target_page_num} 页按钮或跳转输入框")
            return False
