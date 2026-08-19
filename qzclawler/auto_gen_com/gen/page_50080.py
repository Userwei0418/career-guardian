def crawl_page(page):
    try:
        # 定位下一页按钮
        next_btn_li = page.query_selector("li.ant-pagination-next")
        if not next_btn_li:
            print("未找到下一页按钮结构（可能分页不存在）")
            return False

        # 判断是否被禁用（最后一页）
        aria_disabled = next_btn_li.get_attribute("aria-disabled")
        if aria_disabled == "true":
            print("已经是最后一页，停止翻页")
            return False

        # 真正的点击按钮
        next_button = next_btn_li.query_selector("button.ant-pagination-item-link")
        if next_button:
            next_button.click()
            page.wait_for_timeout(1500)
            return True
        else:
            print("找到下一页 li，但内部按钮不存在")
            return False

    except Exception as e:
        print(f"翻页时发生异常: {e}")
        return False
