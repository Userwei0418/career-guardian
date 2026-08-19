def crawl_page(page):
    try:
        # 定位到“下一页”的 li 标签
        next_li = page.locator("li.ant-pagination-next")

        # 读取 aria-disabled 状态
        disabled = next_li.get_attribute("aria-disabled")
        if disabled == "true":
            print("下一页按钮不可用，已经是最后一页")
            return False

        # 点击内部的 button
        next_li.locator("button.ant-pagination-item-link").click()
        page.wait_for_timeout(1000)  # 给页面一次自然刷新时间

        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
