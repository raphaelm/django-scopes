import django
import pytest
from django.db import models
from django.db.models import Value

from django_scopes import scope, ScopeError, get_scope, scopes_disabled
from .testapp.models import Site, Post, Comment, Bookmark


@pytest.fixture
def site1():
    return Site.objects.create(name="Ceasar's blog")


@pytest.fixture
def site2():
    return Site.objects.create(name="Augustus' blog")


@pytest.fixture
def post1(site1):
    return Post.objects.create(site=site1, title="I was stabbed")


@pytest.fixture
def post2(site2):
    return Post.objects.create(site=site2, title="I'm in power now!")


@pytest.fixture
def comment1(post1):
    return Comment.objects.create(post=post1, text="I'm so sorry.")


@pytest.fixture
def comment2(post2):
    return Comment.objects.create(post=post2, text="Cheers!")


@pytest.mark.django_db
def test_allow_unaffected_models(site1, site2):
    assert list(Site.objects.all()) == [site1, site2]


@pytest.mark.django_db
def test_require_scope():
    with pytest.raises(ScopeError):
        Post.objects.count()
    with pytest.raises(ScopeError):
        Post.objects.all()


@pytest.mark.django_db
def test_none_works():
    assert list(Post.objects.none()) == []


@pytest.mark.django_db
def test_require_scope_survive_clone():
    Post.objects.using('default')
    with pytest.raises(ScopeError):
        Post.objects.using('default').all()
    with pytest.raises(ScopeError):
        Post.objects.all().all().all().count()


@pytest.mark.django_db
def test_require_scope_iterate():
    q = Post.objects.using('default')
    with pytest.raises(ScopeError):
        list(Post.objects.using('default'))

    with pytest.raises(ScopeError):
        with scope(site=site1):
            assert list(q) == [post1]


@pytest.mark.django_db
def test_require_scope_at_definition_not_evaluation(site1, post1, post2):
    with pytest.raises(ScopeError):
        Post.objects.all()

    with scope(site=site1):
        p = Post.objects.all()
    assert list(p) == [post1]


@pytest.mark.django_db
def test_scope_add_filter(site1, site2, post1, post2):
    with pytest.raises(ScopeError):
        Post.objects.all()

    with scope(site=site1):
        assert get_scope() == {'site': site1, '_enabled': True}
        assert list(Post.objects.all()) == [post1]
    with scope(site=site2):
        assert get_scope() == {'site': site2, '_enabled': True}
        assert list(Post.objects.all()) == [post2]


@pytest.mark.django_db
def test_scope_keep_filter(site1, site2, post1, post2):
    with pytest.raises(ScopeError):
        Post.objects.all()

    with scope(site=site1):
        assert list(Post.objects.annotate(c=Value(3, output_field=models.IntegerField())).distinct().all()) == [post1]
    with scope(site=site2):
        assert list(Post.objects.annotate(c=Value(3, output_field=models.IntegerField())).distinct().all()) == [post2]


@pytest.mark.django_db
def test_scope_advanced_lookup(site1, site2, comment1, comment2):
    with pytest.raises(ScopeError):
        Post.objects.all()

    with scope(site=site1):
        assert list(Comment.objects.all()) == [comment1]
    with scope(site=site2):
        assert list(Comment.objects.all()) == [comment2]


@pytest.mark.django_db
def test_scope_nested(site1, site2, comment1, comment2):
    with pytest.raises(ScopeError):
        Post.objects.all()

    with scope(site=site1):
        assert list(Comment.objects.all()) == [comment1]
        assert get_scope() == {'site': site1, '_enabled': True}
        with scope(site=site2):
            assert get_scope() == {'site': site2, '_enabled': True}
            assert list(Comment.objects.all()) == [comment2]
        assert get_scope() == {'site': site1, '_enabled': True}
        assert list(Comment.objects.all()) == [comment1]


@pytest.mark.django_db
def test_scope_multisite(site1, site2, comment1, comment2):
    with scope(site=[site1]):
        assert list(Comment.objects.all()) == [comment1]
    with scope(site=[site1, site2]):
        assert list(Comment.objects.all()) == [comment1, comment2]
        assert get_scope() == {'site': [site1, site2], '_enabled': True}


@pytest.mark.django_db
def test_scope_as_decorator(site1, site2, comment1, comment2):
    @scope(site=site1)
    def inner():
        assert list(Comment.objects.all()) == [comment1]

    inner()


@pytest.mark.django_db
def test_scope_opt_out(site1, site2, comment1, comment2):
    with scopes_disabled():
        assert get_scope() == {'_enabled': False}
        assert list(Comment.objects.all()) == [comment1, comment2]


@pytest.mark.django_db
def test_scope_opt_out_decorator(site1, site2, comment1, comment2):
    @scopes_disabled()
    def inner():
        assert list(Comment.objects.all()) == [comment1, comment2]

    inner()


@pytest.fixture
def bm1_1(post1):
    return Bookmark.objects.create(post=post1, userid=1)


@pytest.fixture
def bm1_2(post1):
    return Bookmark.objects.create(post=post1, userid=2)


@pytest.fixture
def bm2_1(post2):
    return Bookmark.objects.create(post=post2, userid=1)


@pytest.mark.django_db
def test_multiple_dimensions(site1, site2, bm2_1, bm1_1, bm1_2):
    with pytest.raises(ScopeError):
        Bookmark.objects.all()

    with scope(site=site1):
        with pytest.raises(ScopeError):
            Bookmark.objects.all()

    with scope(user_id=1):
        with pytest.raises(ScopeError):
            Bookmark.objects.all()

    with scope(site=site1):
        with scope(user_id=1):
            assert list(Bookmark.objects.all()) == [bm1_1]
            with scope(site=site2):
                assert list(Bookmark.objects.all()) == [bm2_1]
            assert list(Bookmark.objects.all()) == [bm1_1]

        with scope(user_id=2):
            assert list(Bookmark.objects.all()) == [bm1_2]

    with scope(site=site1, user_id=1):
        assert list(Bookmark.objects.all()) == [bm1_1]
