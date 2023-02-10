from django.contrib.auth import get_user_model
from django_filters.rest_framework import FilterSet, filters
from recipes.models import Ingredient, Recipe, Tag

User = get_user_model()


class IngredientFilter(FilterSet):
    name = filters.CharFilter(lookup_expr='startswith')

    class Meta:
        model = Ingredient
        fields = ['name']


class RecipeFilter(FilterSet):
    tags = filters.ModelMultipleChoiceFilter(
        field_name='tags__slug',
        to_field_name='slug',
        queryset=Tag.objects.all(),
    )

    is_favorited = filters.BooleanFilter(method='filter_user_list')
    is_in_shopping_cart = filters.BooleanFilter(
        method='filter_user_list')

    def filter_user_list(self, queryset, name, value):
        user = self.request.user
        if value and not user.is_anonymous:
            if name == 'is_favorited':
                return queryset.filter(favorites__user=user)
            if name == 'is_in_shopping_cart':
                return queryset.filter(shopping_cart__user=user)
        return queryset

    class Meta:
        model = Recipe
        fields = ('tags', 'author',)
