def crawl_page(page, action="next", wait_time=5000):
    """
    爬取分页：支持 'next' 和 'prev'
    如果按钮禁用，则终止操作
    """
    if action not in ["next", "prev"]:
        raise ValueError("action 必须是 'next' 或 'prev'")

    # 根据动作选择按钮
    button_selector = (
        "li.ant-pagination-next:not([aria-disabled='true'])"
        if action == "next"
        else "li.ant-pagination-prev:not([aria-disabled='true'])"
    )

    print(f"按钮选择器：{button_selector}")
    btn = page.locator(button_selector)

    # 等待按钮可见，最多等待 wait_time 毫秒
    try:
        btn.wait_for(state="visible", timeout=wait_time)  # 等待按钮出现
        print("按钮可见")
    except Exception as e:
        print(f"按钮不可见: {e}")
        return False

    # 检查按钮是否禁用
    aria_disabled = btn.get_attribute("aria-disabled")
    button_class = btn.get_attribute("class")

    if aria_disabled == "true" or "disabled" in button_class:
        print("按钮已禁用，翻页结束")
        return False

    try:
        print("点击按钮")
        btn.click()

        # 等待页面加载完成
        page.wait_for_load_state("domcontentloaded", timeout=wait_time)  # 等待页面加载完成
        page.wait_for_selector("ul.ant-pagination", timeout=wait_time)  # 确保分页按钮更新

        return True
    except Exception as e:
        print(f"点击失败: {e}")
        return False
