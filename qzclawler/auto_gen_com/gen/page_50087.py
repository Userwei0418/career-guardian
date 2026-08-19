def crawl_page(page):
    try:
        # 定位下一页按钮（用文本匹配）
        next_page_button = page.get_by_text("下一页")
        if next_page_button:
            href = next_page_button.get_attribute('href') or ""
            # 检查是否可以点击
            if "javascript:__doPostBack" in href:
                next_page_button.click()
                return True
            else:
                print("下一页按钮不可点击（可能是最后一页）")
        else:
            print("未找到下一页按钮")
    except Exception as e:
        print(f"翻页时出现错误: {e}")
    return False
