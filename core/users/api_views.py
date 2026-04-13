import os
import requests
from datetime import datetime
from pymongo import MongoClient
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from .models import CustomUser

from .serializers import RegisterSerializer, UserSerializer, UserProfileSerializer
from .models import UserProfile


def get_mongo_client():
    mongo_uri = os.getenv('MONGO_HOST', 'mongodb://localhost:27017')
    return MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)


def get_mongo_db():
    client = get_mongo_client()
    db_name = os.getenv('MONGO_DB_NAME', 'learnsmart_db')
    return client[db_name]


class RegisterAPIView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer


class ProfileAPIView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class UserProfileListCreateAPIView(generics.ListCreateAPIView):
    queryset = UserProfile.objects.all().order_by('-created_at')
    serializer_class = UserProfileSerializer
    permission_classes = [AllowAny]


class UserProfileRetrieveUpdateAPIView(generics.RetrieveUpdateAPIView):
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]


class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        user = authenticate(request, username=username, password=password)
        if not user:
            return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
        }, status=status.HTTP_200_OK)


class RecommendViaFastAPIAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        profile = getattr(user, 'userprofile', None)
        skills = profile.skills if profile and profile.skills else []
        interests = profile.interests if profile and profile.interests else []

        # Save user raw data in MongoDB
        db = get_mongo_db()
        users_coll = db['users']
        recommendations_coll = db['recommendations']

        users_coll.update_one(
            {'user_id': str(user.id)},
            {'$set': {
                'user_id': str(user.id),
                'username': user.username,
                'email': user.email,
                'skills': skills,
                'interests': interests,
                'updated_at': datetime.utcnow(),
            }},
            upsert=True,
        )

        fastapi_url = os.getenv('FASTAPI_RECOMMENDATION_URL', 'http://fastapi:8001/recommendations')
        payload = {
            'user_id': str(user.id),
            'skills': skills,
            'interests': interests,
            'top_n': 5,
        }

        try:
            r = requests.post(fastapi_url, json=payload, timeout=10)
            r.raise_for_status()
        except requests.Timeout:
            return Response({'error': 'FastAPI recommendation request timed out'}, status=status.HTTP_504_GATEWAY_TIMEOUT)
        except requests.ConnectionError:
            return Response({'error': 'Cannot connect to FastAPI recommendation service'}, status=status.HTTP_502_BAD_GATEWAY)
        except requests.HTTPError:
            return Response({'error': 'FastAPI recommendation service error', 'details': r.text}, status=r.status_code)
        except Exception as e:
            return Response({'error': 'Unexpected error', 'details': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            data = r.json()
        except ValueError:
            return Response({'error': 'Invalid JSON from FastAPI service'}, status=status.HTTP_502_BAD_GATEWAY)

        # Save recommendations in MongoDB for the user
        if data and 'recommendations' in data:
            recommendations_coll.update_one(
                {'user_id': str(user.id)},
                {'$set': {
                    'user_id': str(user.id),
                    'recommendations': data.get('recommendations', []),
                    'generated_at': data.get('generated_at'),
                }},
                upsert=True,
            )

        return Response(data, status=r.status_code)


class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'detail': 'Refresh token is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'detail': 'Logout successful.'}, status=status.HTTP_205_RESET_CONTENT)
        except Exception:
            return Response({'detail': 'Invalid or expired refresh token.'}, status=status.HTTP_400_BAD_REQUEST)
