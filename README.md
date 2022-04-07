django-scopes
=============

![Build status](https://github.com/raphaelm/django-scopes/actions/workflows/tests.yml/badge.svg)
![PyPI](https://img.shields.io/pypi/v/django-scopes.svg)
[![Python versions](https://img.shields.io/pypi/pyversions/django-scopes.svg)](https://pypi.org/project/django-scopes/)
![PyPI - Django Version](https://img.shields.io/pypi/djversions/django-scopes)

Motivation
----------

Many of us use Django to build multi-tenant applications where every user only ever
gets access to a small, separated fraction of the data in our application, while
at the same time having *some* global functionality that makes separate databases per
client infeasible. While Django does a great job protecting us from building SQL
injection vulnerabilities and similar errors, Django can't protect us from logic
errors and one of the most dangerous types of security issues for multi-tenant
applications is that we leak data across tenants.

It's so easy to forget that one ``.filter`` call and it's hard to catch these errors
in both manual and automated testing, since you usually do not have a lot of clients
in your development setup. Leaving [radical, database-dependent ideas](https://github.com/bernardopires/django-tenant-schemas)
aside, there aren't many approaches available in the ecosystem to prevent these mistakes
from happening aside from rigorous code review.

We'd like to propose this module as a flexible line of defense. It is meant to have
little impact on your day-to-day work, but act as a safeguard in case you build a
faulty query.

Installation
------------

There's nothing required apart from a simple

	pip install django-scopes

Compatibility
-------------

This library is tested against **Python 3.8-3.10** and **Django 3.2-4.0**.

Usage
-----

Let's assume we have a multi-tenant blog application consisting of the three models ``Site``,
``Post``, and ``Comment``:

```python
from django.db import models

class Site(models.Model):
	name = models.CharField(…)

class Post(models.Model):
	site = models.ForeignKey(Site, …)
	title = models.CharField(…)

class Comment(models.Model):
	post = models.ForeignKey(Post, …)
	text = models.CharField(…)
```

In this case, our model `Site` acts as the tenant for the blog posts and their comments, hence
our application will probably be full of statements like
``Post.objects.filter(site=current_site)``, ``Comment.objects.filter(post__site=current_site)``,
or more complex when more flexible permission handling is involved. With **django-scopes**, we
encourage you to still write these queries with your custom permission-based filters, but
we add a custom model manager that has knowledge about posts and comments being part of a
tenant scope:

```python
from django_scopes import ScopedManager

class Post(models.Model):
	site = models.ForeignKey(Site, …)
	title = models.CharField(…)

	objects = ScopedManager(site='site')

class Comment(models.Model):
	post = models.ForeignKey(Post, …)
	text = models.CharField(…)

	objects = ScopedManager(site='post__site')
```

The keyword argument ``site`` defines the name of our **scope dimension**, while the string
``'site'`` or ``'post__site'`` tells us how we can look up the value for this scope dimension
in ORM queries.

You could have multi-dimensional scopes by passing multiple keyword arguments to
``ScopedManager``, e.g. ``ScopedManager(site='post__site', user='author')`` if that is
relevant to your usecase.

Now, with this custom manager, all queries are banned at first:

	>>> Comment.objects.all()
	ScopeError: A scope on dimension "site" needs to be active for this query.

The only thing that will work is ``Comment.objects.none()``, which is useful e.g. for Django
generic view definitions.

### Activate scopes in contexts

You can now use our context manager to specifically allow queries to a specific blogging site,
e.g.:

```python
from django_scopes import scope

with scope(site=current_site):
	Comment.objects.all()
```

This will *automatically* add a ``.filter(post__site=current_site)`` to all of your queries.
Again, we recommend that you *still* write them explicitly, but it is nice to know to have a
safeguard.

Of course, you can still explicitly enter a non-scoped context to access all the objects in your
system:

```python
with scope(site=None):
	Comment.objects.all()
```

This also works correctly nested within a previously defined scope. You can also activate multiple
values at once:

```python
with scope(site=[site1, site2]):
	Comment.objects.all()
```

Sounds cumbersome to put those ``with`` statements everywhere? Maybe not at all: You probably
already have a middleware that determines the site (or tenant, in general) for every request
based on URL or logged in user, and you can easily use it there to just automatically wrap
it around all your tenant-specific views.

Functions can opt out of this behavior by using

```python
from django_scopes import scopes_disabled


with scopes_disabled():
    …

# OR

@scopes_disabled()
def fun(…):
    …
```

Please note that **django-scopes** is also active during migrations, so if you are writing a
data migration – or have written one in the past! – you'll have to add appropriate scoping
or use the ``scopes_disabled`` context.

### Custom manager classes

If you were already using a custom manager class, you can pass it to a `ScopedManager` with the `_manager_class`
keyword like this:
from django.db import models

```python
from django.db import models

class SiteManager(models.Manager):

	def get_queryset(self):
		return super().get_queryset().exclude(name__startswith='test')

class Site(models.Model):
	name = models.CharField(…)

	objects = ScopedManager(site='site', _manager_class=SiteManager)
```


### Scoping the User model

Assume you've got two models `User` and `Post`. Using the examples above, you can ensure that users only ever see their own diary posts. But how about leaking other users to the currently logged in user? If you application doesn't have much (or any) interaction between users, you can scope the user model. Please note that you'll need a [custom user model](https://docs.djangoproject.com/en/dev/topics/auth/customizing/#specifying-a-custom-user-model). Which base classes your user and manager work off will very between projects.

```python
class User(AbstractUser):
	objects = ScopedManager(user='pk', _manager_class=UserManager)

	# (...)
```

Activating the scope comes with a little caveat - you need to use the users primary key, not the whole object:

```python
with scope(user=request.user.pk):
	# do something :)
```

Caveats
-------

### Admin

**django-scopes** is not compatible with the django admin out of the box, integration requires a
custom middleware. (If you write one, please open a PR to include it in this package!)

### Testing

We want to enforce scoping by default to stay safe, which unfortunately
breaks the Django test runner as well as pytest-django. For now, we haven't found
a better solution than to monkeypatch it:

```python
from django.test import utils
from django_scopes import scopes_disabled

utils.setup_databases = scopes_disabled()(utils.setup_databases)
```

You can wrap many of your test and fixtures inside ``scopes_disabled()`` as well, but we wouldn't advise to do it with all of them: Especially when writing higher-level functional tests, such as tests using Django's test client or tests testing celery tasks, you should make sure that your application code runs as it does in production. Therefore, writing tests for a project using django-scopes often looks like this:

```python
@pytest.mark.django_db
def test_a_view(client):
    with scopes_disabled():
        u = User.objects.create(...)
    client.post('/user/{}/delete'.format(u.pk))
    with scopes_disabled():
    	assert not User.objects.filter(pk=u.pk).exists()
```

If you want to disable scoping or activate a certain scope whenever a specific fixture is used, you can do so in py.test like this:

```python
@pytest.fixture
def site():
    s = Site.objects.create(...)
    with scope(site=s):
        yield s
```

When trying to port a project with *lots* of fixtures, it can be helpful to roll a small py.test plugin in your ``conftest.py`` to just globally disable scoping for all fixtures which are not yielding fixtures (like the one above):

```python
@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef, request):
    if inspect.isgeneratorfunction(fixturedef.func):
        yield
    else:
        with scopes_disabled():
            yield
```

### ModelForms

When using model forms, Django will automatically generate choice fields on foreign
keys and many-to-many fields. This won't work here, so we supply helper field
classes ``SafeModelChoiceField`` and ``SafeModelMultipleChoiceField`` that use an
empty queryset instead:

```python
from django.forms import ModelForm
from django_scopes.forms import SafeModelChoiceField

class PostMethodForm(ModelForm):
    class Meta:
        model = Comment
        field_classes = {
            'post': SafeModelChoiceField,
        }
```

### django-filter

We noticed that ``django-filter`` also runs some queries when generating filtersets.
Currently, our best workaround is this:

```python
from django_scopes import scopes_disabled

with scopes_disabled():
    class CommentFilter(FilterSet):
        …
```

### Uniqueness

One subtle class of bug that can be introduced by adding django-scopes to your project is if you try to generate unique identifiers in your database with a pattern like this:

```python

def generate_unique_value():
    while True:
        key = _generate_random_key()
        if not Model.objects.filter(key=key).exists():
            return key
```

If you want keys to be unique across tenants, make sure to wrap such functions with ``scopes_disabled()``!

When using a [ModelForm](https://docs.djangoproject.com/en/dev/topics/forms/modelforms/) (or [class based view](https://docs.djangoproject.com/en/dev/topics/class-based-views/)) to create or update a model, unexpected IntegrityErrors may occur. ModelForms perform a uniqueness check before actually saving the model. If that check runs in a scoped context, it cannot find conflicting instances, leading to an IntegrityErrors once the actual `.save()` happens. To combat this, wrap the call in ``scopes_disabled()``.

```python
class Site(models.Model):
    name = models.CharField(unique=True, …)

    # (...)

    def validate_unique(self, *args, **kwargs):
        with scopes_disabled():
            super().validate_unique(*args, **kwargs)
```

## Further reading

If you'd like to read more about the practical use of django-scopes, there is a [blog
post](https://behind.pretix.eu/2019/06/17/scopes/) about its introduction in the [pretix](https://pretix.eu) project.

[Here](https://rixx.de/blog/using-the-django-shell-with-django-scopes/) is a guide on how to write a ``shell_scoped``
django-admin command to provide a scoped Django shell.
