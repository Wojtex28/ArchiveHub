from django.apps import AppConfig


class AlbumsConfig(AppConfig):
    name = "albums"
    verbose_name = "Albumy"

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from .models import Comment
        from .search import refresh_search_text

        # Komentarze też są przeszukiwane: dodanie i usunięcie (także w panelu) odświeża zdjęcie.
        def comment_changed(sender, instance, **kwargs):
            refresh_search_text([instance.photo_id])

        post_save.connect(comment_changed, sender=Comment, dispatch_uid="albums-comment-search")
        post_delete.connect(comment_changed, sender=Comment, dispatch_uid="albums-comment-search-delete")
