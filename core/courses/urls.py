from django.urls import path
from .api_views import CourseListCreateAPIView, CourseRetrieveUpdateDestroyAPIView

urlpatterns = [
    path('api/courses/', CourseListCreateAPIView.as_view(), name='course_list_create'),
    path('api/courses/<int:pk>/', CourseRetrieveUpdateDestroyAPIView.as_view(), name='course_detail'),
]
