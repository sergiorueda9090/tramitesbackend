from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from users.models import Module, UserModulePermission

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'password']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        validated_data['password'] = make_password(validated_data['password'])
        return super(UserSerializer, self).create(validated_data)

    def update(self, instance, validated_data):
        password = validated_data.get('password', None)
        if password:
            instance.password = make_password(password)
        return super(UserSerializer, self).update(instance, validated_data)


class ModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = ['id', 'name', 'code']


class UserModulePermissionSerializer(serializers.ModelSerializer):
    module = serializers.SlugRelatedField(slug_field='code', queryset=Module.objects.all())

    class Meta:
        model = UserModulePermission
        fields = ['module', 'can_view', 'can_create', 'can_edit', 'can_delete']