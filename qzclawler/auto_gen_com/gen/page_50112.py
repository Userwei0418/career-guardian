def crawl_page(page):
    try:
        # 定位下一页按钮并点击
        next_page_button = page.query_selector("p span.text:has-text('下一页')")

        # 判断按钮是否可以点击，并检查是否锁定
        if next_page_button:
            # 检查是否有 "lock" 类，表示按钮被锁定（即最后一页）
            if "lock" in next_page_button.get_attribute("class"):
                print("已经是最后一页")
                return False
            elif next_page_button.is_enabled():
                # 获取 aria-disabled 属性，确保按钮未被禁用
                aria_disabled = next_page_button.get_attribute('aria-disabled')
                if aria_disabled != 'true' and aria_disabled is not None:
                    next_page_button.click()
                    return True
                else:
                    print("下一页按钮被禁用")
        else:
            print("找不到下一页按钮")
    except Exception as e:
        print(f"翻页时出现错误: {e}")
    return False
