from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (("Archiwum", {"fields": ("display_name",)}),)
    list_display = ("username", "display_name", "is_active", "is_superuser", "last_login")
