from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def menu_open(context, url_keyword):
    """
    현재 URL 경로에 url_keyword가 포함되어 있으면 'menu-open' 클래스를 반환
    """
    request = context.get('request')
    if request and url_keyword in request.path:
        return "menu-open"
    return ""


@register.simple_tag(takes_context=True)
def active_nav(context, url_keyword):
    """
    현재 URL 경로에 url_keyword가 포함되어 있으면 'active' 클래스를 반환
    """
    request = context.get('request')
    if not request:
        return ""

    # 자바의 request.getRequestURI().contains(url_keyword)와 동일
    if url_keyword in request.path:
        return "active"
    return ""
