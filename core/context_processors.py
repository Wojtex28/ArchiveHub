from django.conf import settings


def site(request):
    return {"site_title": settings.SITE_TITLE}
