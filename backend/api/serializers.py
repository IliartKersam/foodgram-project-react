from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from djoser.serializers import UserCreateSerializer, UserSerializer
from drf_extra_fields.fields import Base64ImageField
from recipes.models import Ingredient, IngredientInRecipe, Recipe, Tag
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.fields import IntegerField, SerializerMethodField
from rest_framework.relations import PrimaryKeyRelatedField
from rest_framework.serializers import ModelSerializer

from users.models import Subscribe

User = get_user_model()


class CustomUserCreateSerializer(UserCreateSerializer):
    class Meta:
        model = User
        fields = tuple(User.REQUIRED_FIELDS) + (
            User.USERNAME_FIELD,
            'password',
        )


class CustomUserSerializer(UserSerializer):
    is_subscribed = SerializerMethodField(read_only=True)

    def get_is_subscribed(self, obj):
        user = self.context.get('request').user
        if user.is_anonymous:
            return False
        return Subscribe.objects.filter(user=user, author=obj).exists()

    class Meta:
        model = User
        fields = (
            'email',
            'id',
            'username',
            'first_name',
            'last_name',
            'is_subscribed',
        )


class SubscribeSerializer(CustomUserSerializer):
    recipes_count = SerializerMethodField()
    recipes = SerializerMethodField()

    def validate(self, data):
        author = self.instance
        user = self.context.get('request').user
        if Subscribe.objects.filter(author=author, user=user).exists():
            raise ValidationError(
                detail='Вы уже подписаны на этого пользователя!',
                code=status.HTTP_400_BAD_REQUEST
            )
        if user == author:
            raise ValidationError(
                detail='Вы не можете подписаться на самого себя!',
                code=status.HTTP_400_BAD_REQUEST
            )
        return data

    def get_recipes_count(self, obj):
        return obj.recipes.count()

    def get_recipes(self, obj):
        request = self.context.get('request')
        limit = request.GET.get('recipes_limit')
        int_limit = int(limit)
        recipes = obj.recipes.all()
        if limit:
            recipes = recipes[:int_limit]
        serializer = RecipeShortSerializer(recipes, many=True, read_only=True)
        return serializer.data

    class Meta(CustomUserSerializer.Meta):
        fields = CustomUserSerializer.Meta.fields + (
            'recipes_count', 'recipes'
        )
        read_only_fields = ('email', 'username')


class IngredientSerializer(ModelSerializer):
    class Meta:
        model = Ingredient
        fields = '__all__'


class TagSerializer(ModelSerializer):
    class Meta:
        model = Tag
        fields = '__all__'


class RecipeReadSerializer(ModelSerializer):
    tags = TagSerializer(many=True, read_only=True)
    author = CustomUserSerializer(read_only=True)
    ingredients = SerializerMethodField()
    image = Base64ImageField()
    is_favorited = SerializerMethodField(read_only=True)
    is_in_shopping_cart = SerializerMethodField(read_only=True)

    def user_is_anonymous(self):
        return self.context.get('request').user.is_anonymous

    def get_ingredients(self, obj):
        recipe = obj
        ingredients = recipe.ingredients.values(
            'id',
            'name',
            'measurement_unit',
            amount=F('ingredientinrecipe__amount')
        )
        return ingredients

    def get_is_favorited(self, obj):
        user = self.context.get('request').user
        return (not self.user_is_anonymous() and
                user.favorites.filter(recipe=obj).exists())

    def get_is_in_shopping_cart(self, obj):
        user = self.context.get('request').user
        return (not self.user_is_anonymous() and
                user.shopping_cart.filter(recipe=obj).exists())

    class Meta:
        model = Recipe
        fields = (
            'id',
            'tags',
            'author',
            'ingredients',
            'is_favorited',
            'is_in_shopping_cart',
            'name',
            'image',
            'text',
            'cooking_time',
        )


class IngredientInRecipeWriteSerializer(ModelSerializer):
    id = IntegerField(write_only=True)

    class Meta:
        model = IngredientInRecipe
        fields = ('id', 'amount')


class RecipeWriteSerializer(ModelSerializer):
    tags = PrimaryKeyRelatedField(queryset=Tag.objects.all(),
                                  many=True)
    author = CustomUserSerializer(read_only=True)
    ingredients = IngredientInRecipeWriteSerializer(many=True)
    image = Base64ImageField()

    @transaction.atomic
    def create_ingredients_amounts(self, ingredients, recipe):
        IngredientInRecipe.objects.bulk_create(
            [IngredientInRecipe(
                ingredient=Ingredient.objects.get(id=ingredient['id']),
                recipe=recipe,
                amount=ingredient['amount']
            ) for ingredient in ingredients]
        )

    @transaction.atomic
    def create(self, validated_data):
        tags = validated_data.pop('tags')
        ingredients = validated_data.pop('ingredients')
        recipe = Recipe.objects.create(**validated_data)
        recipe.tags.set(tags)
        self.create_ingredients_amounts(recipe=recipe,
                                        ingredients=ingredients)
        return recipe

    @transaction.atomic
    def update(self, instance, validated_data):
        tags = validated_data.pop('tags')
        ingredients = validated_data.pop('ingredients')
        instance = super().update(instance, validated_data)
        instance.tags.clear()
        instance.tags.set(tags)
        instance.ingredients.clear()
        self.create_ingredients_amounts(recipe=instance,
                                        ingredients=ingredients)
        instance.save()
        return instance

    def to_representation(self, instance):
        request = self.context.get('request')
        context = {'request': request}
        return RecipeReadSerializer(instance,
                                    context=context).data

    class Meta:
        model = Recipe
        fields = (
            'id',
            'tags',
            'author',
            'ingredients',
            'name',
            'image',
            'text',
            'cooking_time',
        )


class RecipeShortSerializer(ModelSerializer):
    image = Base64ImageField()

    class Meta:
        model = Recipe
        fields = (
            'id',
            'name',
            'image',
            'cooking_time'
        )
