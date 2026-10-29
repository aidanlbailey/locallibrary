import datetime

from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import RestrictedError
from django.forms import inlineformset_factory
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.views import generic
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from .forms import RenewBookForm
from .models import Book, Author, BookAuthor, BookInstance, Genre

def index(request):
    """View function for home page of site."""

    # Generate counts of some of the main objects
    num_books = Book.objects.all().count()
    num_instances = BookInstance.objects.all().count()

    # Available books (status = 'a')
    num_instances_available = BookInstance.objects.filter(status__exact='a').count()

    # The 'all()' is implied by default.
    num_authors = Author.objects.count()

    # challenge: counts for genres/books with a given word in them
    word = 'the'
    num_genres = Genre.objects.count()
    num_genres_with_word = Genre.objects.filter(name__icontains=word).count()
    num_books_with_word = Book.objects.filter(title__icontains=word).count()

    # Number of visits to this view, as counted in the session variable.
    num_visits = request.session.get('num_visits', 0)
    num_visits += 1
    request.session['num_visits'] = num_visits

    context = {
        'num_books': num_books,
        'num_instances': num_instances,
        'num_instances_available': num_instances_available,
        'num_authors': num_authors,
        'num_genres': num_genres,
        'word': word,
        'num_genres_with_word': num_genres_with_word,
        'num_books_with_word': num_books_with_word,
        'num_visits': num_visits,
    }

    # Render the HTML template index.html with the data in the context variable
    return render(request, 'index.html', context=context)


class BookListView(generic.ListView):
    model = Book
    # Book has no Meta.ordering, and paginating an unordered queryset makes django whine
    queryset = Book.objects.order_by('title')
    paginate_by = 10


class BookDetailView(generic.DetailView):
    model = Book


class AuthorListView(generic.ListView):
    model = Author
    paginate_by = 10


class AuthorDetailView(generic.DetailView):
    model = Author


class LoanedBooksByUserListView(LoginRequiredMixin, generic.ListView):
    """Generic class-based view listing books on loan to current user."""
    model = BookInstance
    template_name = 'catalog/bookinstance_list_borrowed_user.html'
    paginate_by = 10

    def get_queryset(self):
        return (
            BookInstance.objects.filter(borrower=self.request.user)
            .filter(status__exact='o')
            .order_by('due_back')
        )


class LoanedBooksAllListView(PermissionRequiredMixin, generic.ListView):
    """Every book on loan, with who has it. Librarians only."""
    model = BookInstance
    permission_required = 'catalog.can_mark_returned'
    template_name = 'catalog/bookinstance_list_borrowed_all.html'
    paginate_by = 10

    def get_queryset(self):
        return BookInstance.objects.filter(status__exact='o').order_by('due_back')


@login_required
@permission_required('catalog.can_mark_returned', raise_exception=True)
def renew_book_librarian(request, pk):
    """View function for renewing a specific BookInstance by librarian."""
    book_instance = get_object_or_404(BookInstance, pk=pk)

    if request.method == 'POST':
        form = RenewBookForm(request.POST)

        if form.is_valid():
            book_instance.due_back = form.cleaned_data['renewal_date']
            book_instance.save()
            return HttpResponseRedirect(reverse('all-borrowed'))

    else:
        proposed_renewal_date = datetime.date.today() + datetime.timedelta(weeks=3)
        form = RenewBookForm(initial={'renewal_date': proposed_renewal_date})

    context = {
        'form': form,
        'book_instance': book_instance,
    }

    return render(request, 'catalog/book_renew_librarian.html', context)


class AuthorCreate(PermissionRequiredMixin, CreateView):
    model = Author
    fields = ['first_name', 'last_name', 'date_of_birth', 'date_of_death']
    permission_required = 'catalog.add_author'


class AuthorUpdate(PermissionRequiredMixin, UpdateView):
    model = Author
    fields = ['first_name', 'last_name', 'date_of_birth', 'date_of_death']
    permission_required = 'catalog.change_author'


class AuthorDelete(PermissionRequiredMixin, DeleteView):
    model = Author
    success_url = reverse_lazy('authors')
    permission_required = 'catalog.delete_author'

    def form_valid(self, form):
        # BookAuthor.author is RESTRICT, so this blows up if they still have books
        try:
            self.object.delete()
            return HttpResponseRedirect(self.success_url)
        except RestrictedError:
            return HttpResponseRedirect(reverse('author-delete', kwargs={'pk': self.object.pk}))


# authors go through BookAuthor (for author_order), so they get edited as a formset
BookAuthorFormSet = inlineformset_factory(
    Book, BookAuthor, fields=['author', 'author_order'], extra=2)


class BookAuthorFormSetMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.method == 'POST':
            context['author_formset'] = BookAuthorFormSet(self.request.POST, instance=self.object)
        else:
            context['author_formset'] = BookAuthorFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        # no formset posted (scripts/tests hitting the url directly), so save the book on its own
        # and take a plain `authors` list if there is one, in the order given
        if f'{BookAuthorFormSet.get_default_prefix()}-TOTAL_FORMS' not in self.request.POST:
            self.object = form.save()
            author_ids = self.request.POST.getlist('authors')
            if author_ids:
                self.object.bookauthor_set.all().delete()
                authors = Author.objects.in_bulk(author_ids)
                for order, pk in enumerate(author_ids, start=1):
                    BookAuthor.objects.create(book=self.object, author=authors[int(pk)], author_order=order)
            return HttpResponseRedirect(self.get_success_url())

        author_formset = BookAuthorFormSet(self.request.POST, instance=form.instance)
        if not author_formset.is_valid():
            return self.form_invalid(form)
        self.object = form.save()
        author_formset.instance = self.object
        author_formset.save()
        return HttpResponseRedirect(self.get_success_url())


class BookCreate(PermissionRequiredMixin, BookAuthorFormSetMixin, CreateView):
    model = Book
    fields = ['title', 'summary', 'isbn', 'genre', 'language']
    permission_required = 'catalog.add_book'


class BookUpdate(PermissionRequiredMixin, BookAuthorFormSetMixin, UpdateView):
    model = Book
    fields = ['title', 'summary', 'isbn', 'genre', 'language']
    permission_required = 'catalog.change_book'


class BookDelete(PermissionRequiredMixin, DeleteView):
    model = Book
    success_url = reverse_lazy('books')
    permission_required = 'catalog.delete_book'

    def form_valid(self, form):
        # BookInstance.book is RESTRICT, copies have to go first
        try:
            self.object.delete()
            return HttpResponseRedirect(self.success_url)
        except RestrictedError:
            return HttpResponseRedirect(reverse('book-delete', kwargs={'pk': self.object.pk}))
