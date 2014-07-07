from django.db import backend
from django.db import connection
from django.db import models
from django.db.models.fields import Field, subclassing
from django.db.models.query import QuerySet
from django.db.models.sql.constants import QUERY_TERMS

db_backends_allowed = ('postgresql')


def get_prep_lookup(self, lookup_type, value):
    try:
        return self.get_prep_lookup_origin(lookup_type, value)
    except TypeError as e:
        if lookup_type in NEW_LOOKUP_TYPE:
            return value
        raise e


def get_db_prep_lookup(self, lookup_type, value, *args, **kwargs):
    try:
        value_returned = self.get_db_prep_lookup_origin(lookup_type, value,
                                                        *args, **kwargs)
    except TypeError as e:  # Django 1.1
        if lookup_type in NEW_LOOKUP_TYPE:
            return [value]
        raise e
    if value_returned is None and lookup_type in NEW_LOOKUP_TYPE:  # Dj > 1.1
        return [value]
    return value_returned


def monkey_get_db_prep_lookup(cls):
    cls.get_db_prep_lookup_origin = cls.get_db_prep_lookup
    cls.get_db_prep_lookup = get_db_prep_lookup
    if hasattr(subclassing, 'call_with_connection_and_prepared'):  # Dj > 1.1
        setattr(cls, 'get_db_prep_lookup',
                subclassing.call_with_connection_and_prepared(cls.get_db_prep_lookup))
        for new_cls in cls.__subclasses__():
            monkey_get_db_prep_lookup(new_cls)


backend_allowed = reduce(
    lambda x, y: x in backend.__name__ or y, db_backends_allowed)

if backend_allowed:

    if isinstance(QUERY_TERMS, set):
        QUERY_TERMS.add('similar')
    else:
        QUERY_TERMS['similar'] = None

    connection.operators['similar'] = "%%%% %s"

    NEW_LOOKUP_TYPE = ('similar', )

    monkey_get_db_prep_lookup(Field)
    if hasattr(Field, 'get_prep_lookup'):
        Field.get_prep_lookup_origin = Field.get_prep_lookup
        Field.get_prep_lookup = get_prep_lookup


class SimilarQuerySet(QuerySet):

    def filter_o(self, **kwargs):
        qs = super(SimilarQuerySet, self).filter(**kwargs)
        for lookup, query in kwargs.items():
            if lookup.endswith('__similar'):
                field = lookup.replace('__similar', '')
                select = {'%s_distance' % field: "similarity(%s, '%s')" % (field, query)}
                qs = qs.extra(select=select).order_by('-%s_distance' % field)
        return qs


class SimilarManager(models.Manager):

    def get_queryset(self):
        return SimilarQuerySet(self.model, using=self._db)

    def filter_o(self, **kwargs):
        return self.get_queryset().filter_o(**kwargs)
