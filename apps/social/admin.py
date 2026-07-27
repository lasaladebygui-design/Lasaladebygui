from django.contrib import admin

from .models import FriendRequest, Message


@admin.register(FriendRequest)
class FriendRequestAdmin(admin.ModelAdmin):
    list_display = ("from_user", "to_user", "accepted", "created_at")
    list_filter = ("accepted",)
    search_fields = ("from_user__username", "to_user__username", "from_user__email", "to_user__email")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("sender", "recipient", "created_at", "read_at")
    search_fields = ("sender__username", "recipient__username", "body")
