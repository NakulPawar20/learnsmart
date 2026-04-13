from rest_framework import serializers
from .models import Course


class CourseSerializer(serializers.ModelSerializer):
    tags = serializers.ListField(child=serializers.CharField(), allow_empty=True, required=False)
    categories = serializers.ListField(child=serializers.CharField(), allow_empty=True, required=False)

    class Meta:
        model = Course
        fields = ['id', 'title', 'description', 'tags', 'categories', 'created_at', 'updated_at']

    def create(self, validated_data):
        return Course.objects.create(**validated_data)

    def update(self, instance, validated_data):
        instance.title = validated_data.get('title', instance.title)
        instance.description = validated_data.get('description', instance.description)
        instance.tags = validated_data.get('tags', instance.tags)
        instance.categories = validated_data.get('categories', instance.categories)
        instance.save()
        return instance