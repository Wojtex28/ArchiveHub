from django.contrib import admin

from .models import Album, SyncReport


@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    list_display = ["title", "folder", "photo_count", "is_hidden", "folder_missing"]
    filter_horizontal = ["groups"]


@admin.register(SyncReport)
class SyncReportAdmin(admin.ModelAdmin):
    list_display = ["started_at", "albums_total", "photos_total", "error"]
