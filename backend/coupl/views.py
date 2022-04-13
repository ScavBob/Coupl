import datetime
import json

from django.contrib.auth import authenticate
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db.models import Max
from django.http import JsonResponse
from rest_framework import authentication, permissions
from rest_framework.authtoken.models import Token
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from django.forms.models import model_to_dict
from django.core.exceptions import ObjectDoesNotExist

from coupl.serializers import UserSerializer, EventSerializer, TagSerializer, UserDisplaySerializer, \
    ProfileSerializer, MatchSerializer, ProfilePictureSerializer
from coupl.models import Event, Tag, Profile, Match, ProfilePicture
from coupl.mixins import UserInEventMixin, LikeInEventMixin, SkipInEventMixin
from itertools import chain


# todo Send user login token when successfully logged in
class LoginView(APIView):
    def post(self, request, format=None):
        username = request.data['username']
        password = request.data['password']
        authenticated_user = authenticate(username=username, password=password)
        if authenticated_user is not None:
            get, create = Token.objects.get_or_create(user=authenticated_user)
            token = get if get is not None else create
            request.user = authenticated_user
            return JsonResponse(token.key, status=200, safe=False)
        return Response(False)


class UserLoginView(APIView):
    def get(self, request, format=None):
        users = User.objects.all()
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)

    def post(self, request, format=None):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse(serializer.data, status=201)
        return JsonResponse(serializer.errors, status=400)


class ListProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, format=None):
        profiles = Profile.objects.all()
        serializer = ProfileSerializer(profiles, many=True)
        # todo
        # i broke something and i dunno what
        return Response(serializer.data)


class UpdateProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        profile = request.user.profile
        serializer = ProfileSerializer(data=request.data)
        if serializer.is_valid():
            serializer.update(profile, serializer.validated_data)
        return JsonResponse(serializer.data, status=201)


class AddProfilePicture(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        profile = request.user.profile
        last_pic = ProfilePicture.objects.filter(profile_id=profile.pk).aggregate(Max('order'))
        request.data['order'] = last_pic['order__max'] + 1
        data = request.data
        data['profile'] = profile.pk
        profile_pic = ProfilePictureSerializer(data=data)
        if profile_pic.is_valid():
            profile_pic.save()
            return JsonResponse(profile_pic.data, status=201)
        return JsonResponse(profile_pic.errors, status=400)


class RemoveProfilePicture(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        profile = request.user.profile
        pp = ProfilePicture.objects.get(profile_id=profile.pk, order=request.data['order'])
        pp.delete()
        rest = ProfilePicture.objects.filter(profile__user_id=request.data['id'], order__gt=request.data['order'])
        for pic in rest:
            pic.order = pic.order - 1
            pic.save()
        profile = Profile.objects.get(user_id=request.data['id'])
        serializer = ProfileSerializer(profile)
        return JsonResponse(serializer.data, status=201)


class SwapProfilePicture(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        first_order = request.data['first_order']
        second_order = request.data['second_order']
        profile = request.user.profile
        first = ProfilePicture.objects.get(profile_id=profile.pk, order=first_order)
        second = ProfilePicture.objects.get(profile_id=profile.pk, order=second_order)
        first.order = second_order
        second.order = first_order
        first.save()
        second.save()
        serializer = ProfileSerializer(profile)
        return JsonResponse(serializer.data)


class CreateProfileView(APIView):
    # jank fest omegalul
    def post(self, request):
        user_serializer = UserSerializer(data=request.data['user'])
        user = None
        if user_serializer.is_valid():
            user = User.objects.create_user(username=user_serializer.data['username'], password=user_serializer.data['password'])
        else:
            return JsonResponse("Can't create user", status=400, safe=False)
        request.data.pop('user', None)
        profile_data = request.data
        profile_serializer = ProfileSerializer(data=request.data)
        if profile_serializer.is_valid():
            profile = Profile.objects.create(user=user, **profile_data)
            data = ProfileSerializer(profile)
            return JsonResponse(data.data, status=201)
        user.delete()  # if profile is not valid the user will should be deleted from the database as well
        return JsonResponse(profile_serializer.errors, status=400)


class ProfileGetView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, format=None):
        profile = request.user.profile
        serializer = ProfileSerializer(profile)

        return Response(serializer.data, status=201)


class EventListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, format=None):
        events = Event.objects.all()
        serializer = EventSerializer(events, many=True)
        return Response(serializer.data)


class EventGetView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        event_id = request.data['event_id']
        event = Event.objects.get(pk=event_id)

        serializer = EventSerializer(event)

        return Response(serializer.data, status=201)


class EventAddView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        serializer = EventSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse(serializer.data, status=201)
        return JsonResponse(serializer.errors, status=400)


class EventJoinView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        event_id = request.data['event_id']
        user = request.user
        try:
            event = Event.objects.get(pk=event_id)
        except ObjectDoesNotExist:
            return JsonResponse('Event with the given id is not found.', status=400, safe=False)
        event.event_attendees.add(user)
        return JsonResponse('Successfully joined the event', status=201, safe=False)


class EventLeaveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        user = request.user
        event = Event.objects.get(pk=request.data['event_id'])

        event.event_attendees.remove(user)

        return JsonResponse('Successfully left event', status=201, safe=False)


class TagCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        serializer = TagSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse(serializer.data, status=201)
        return JsonResponse(serializer.errors, status=400)


class EventAddTagView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        event_id = request.data['event_id']
        tag_id = request.data['tag_id']
        try:
            event = Event.objects.get(pk=event_id)
        except ObjectDoesNotExist:
            return JsonResponse('Event with the given id is not found.', status=400, safe=False)
        try:
            tag = Tag.objects.get(pk=tag_id)
        except ObjectDoesNotExist:
            return JsonResponse('Tag with the given id is not found.', status=400, safe=False)
        event.eventTags.add(tag)
        return JsonResponse('Successfully added tag to the event', status=201, safe=False)


class TagListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, format=None):
        tags = Tag.objects.all()
        serializer = TagSerializer(tags, many=True)
        return Response(serializer.data)


class UserGetMatches(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        user = request.user
        event = Event.objects.get(pk=request.data["event_id"])
        liked = Match.objects.filter(event__match__liker=request.data["user_id"]).values_list('liked_id', flat=True,
                                                                                              named=False)

        attendees = event.event_attendees.exclude(pk=request.data["user_id"]).exclude(pk__in=liked).filter(
            profile__gender__in=Profile.preference_list[int(user.profile.preference)])
        serializer = UserSerializer(attendees, many=True)
        return Response(serializer.data)


class UserGetBestMatch(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        user = request.user
        event = Event.objects.get(pk=request.data["event_id"])
        liked = Match.objects.filter(event__match__liker=request.data["user_id"]).values_list('liked_id', flat=True,
                                                                                              named=False)

        attendee = event.event_attendees.exclude(pk=request.data["user_id"]).exclude(pk__in=liked).filter(
            profile__gender__in=Profile.preference_list[int(user.profile.preference)]).first()
        if not attendee:
            raise ObjectDoesNotExist
        serializer = ProfileSerializer(attendee.profile)
        return Response(serializer.data)


class UserLike(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        liked_id = request.data["liked_id"]
        event_id = request.data["event_id"]

        liker = request.user
        liked = User.objects.get(pk=liked_id)
        event = Event.objects.get(pk=event_id)

        # Liked user also previously liked the liker, match confirms
        match_qs = Match.objects.filter(liked=liker, liker=liked, skip=False)
        if match_qs:
            for match in match_qs:
                match.confirmed = True
                match.save()
        # Else create new match
        else:
            match = Match(liker=liker, liked=liked, event=event)
            match.save()

        serializer = MatchSerializer(match)
        return Response(serializer.data)


class UserSkip(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        skipper_id = request.data["skipper_id"]
        skipped_id = request.data["skipped_id"]
        event_id = request.data["event_id"]

        skipper = request.user
        skipped = User.objects.get(pk=skipped_id)
        event = Event.objects.get(pk=event_id)

        skip_qs = Match.objects.filter(liked=skipper, liker=skipped)
        if skip_qs:
            for skip in skip_qs:
                skip.skip = True
                skip.save()
        else:
            skip = Match(liker=skipper, liked=skipped, event=event, skip=True)
            skip.save()

        serializer = MatchSerializer(skip)
        return Response(serializer.data)


class UserGetMutualLikes(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        event_id = request.data["event_id"]
        user = request.user
        event = Event.objects.get(pk=event_id)

        mutuals_as_liker = Match.objects.filter(liker=user, event=event, confirmed=True).values_list('liked', flat=True,
                                                                                                     named=False)
        mutuals_as_liked = Match.objects.filter(liked=user, event=event, confirmed=True).values_list('liker', flat=True,
                                                                                                     named=False)

        mutuals = list(chain(mutuals_as_liker, mutuals_as_liked))
        mutuals = User.objects.filter(pk__in=mutuals)

        # mutuals = match.liked.exclude(pk=user_id).filter(
        #    event__match__liker=user_id, event__pk=event_id, event__match__confirmed=True)

        serializer = UserSerializer(mutuals, many=True)
        return Response(serializer.data)
