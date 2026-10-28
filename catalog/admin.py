from django.contrib import admin

from .models import Author, Genre, Book, BookAuthor, BookInstance, Language

admin.site.register(Genre)
admin.site.register(Language)
admin.site.register(BookAuthor)


class BookAuthorInline(admin.TabularInline):
    """Shows up on both Book and Author so you can link them from either side."""
    model = BookAuthor
    extra = 0


class BooksInstanceInline(admin.TabularInline):
    """Copies of a book, shown on the book page. extra=0 so there are no blank rows."""
    model = BookInstance
    extra = 0


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name', 'date_of_birth', 'date_of_death')

    fields = ['first_name', 'last_name', ('date_of_birth', 'date_of_death')]

    inlines = [BookAuthorInline]


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'display_genre')

    inlines = [BookAuthorInline, BooksInstanceInline]


@admin.register(BookInstance)
class BookInstanceAdmin(admin.ModelAdmin):
    list_display = ('book', 'status', 'borrower', 'due_back', 'id')

    list_filter = ('status', 'due_back')

    fieldsets = (
        (None, {
            'fields': ('book', 'imprint', 'id')
        }),
        ('Availability', {
            'fields': ('status', 'due_back', 'borrower')
        }),
    )
