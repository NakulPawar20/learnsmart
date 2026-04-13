from django.urls import path
from django.contrib.auth import views as auth_views
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views
from .api_views import LoginAPIView, RegisterAPIView, ProfileAPIView, LogoutAPIView, UserProfileListCreateAPIView, UserProfileRetrieveUpdateAPIView, RecommendViaFastAPIAPIView

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='users/password_reset.html'), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='users/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='users/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='users/password_reset_complete.html'), name='password_reset_complete'),

    # JWT API endpoints
    path('api/auth/register/', RegisterAPIView.as_view(), name='api_register'),
    path('api/auth/login/', LoginAPIView.as_view(), name='api_login'),
    path('api/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/logout/', LogoutAPIView.as_view(), name='api_logout'),
    path('api/auth/profile/', ProfileAPIView.as_view(), name='api_profile'),

    # API endpoints for UserProfile data
    path('api/user-profiles/', UserProfileListCreateAPIView.as_view(), name='api_user_profiles'),
    path('api/user-profiles/<int:pk>/', UserProfileRetrieveUpdateAPIView.as_view(), name='api_user_profile_detail'),

    # FastAPI recommendation proxy
    path('api/recommend/<str:user_id>/', RecommendViaFastAPIAPIView.as_view(), name='api_recommend_via_fastapi'),
]