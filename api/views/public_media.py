"""The logo and cover of the public page (branches/media.py, docs/15 D8).

    GET    /api/public-media/                              the group's and the clinics' images, and what awaits approval
    POST   /api/public-media/group/                        Owner: `logo` and/or `cover` (multipart) — live at once
    DELETE /api/public-media/group/<kind>/                 Owner: take one down
    POST   /api/public-media/branches/<uuid>/              `logo` and/or `cover` (multipart)
                                                           Owner: live at once · Admin (own clinic): waits for approval
    DELETE /api/public-media/branches/<uuid>/<kind>/       take the live image down (`?pending=1`: withdraw the waiting one)
    POST   /api/public-media/branches/<uuid>/review/       Owner: `{decision: approve|reject, note}`

The public page (`portal.registration.PublicAboutView`) shows only the approved
files; a pending file's address is only ever returned here, to the people who
may see it.
"""

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.roles import is_owner, sees_all_branches
from api.permissions import IsClinicAdmin, IsGroupOwner
from branches import media
from branches.models import Branch


def _branch_payload(branch):
    return {
        "uuid": str(branch.uuid),
        "name": branch.name,
        "logo": media.url_of(branch.public_logo),
        "cover": media.url_of(branch.public_cover),
        "pending_logo": media.url_of(branch.pending_public_logo),
        "pending_cover": media.url_of(branch.pending_public_cover),
        "status": branch.media_status,
        "review_note": branch.media_review_note,
    }


def _group_payload(tenant):
    return {"logo": media.url_of(tenant.public_logo), "cover": media.url_of(tenant.public_cover)}


def _branches_for(user):
    """The Owner reaches every clinic; an Admin only their own."""
    queryset = Branch.objects.all()
    if sees_all_branches(user):
        return queryset
    return queryset.filter(pk=user.branch_id) if user.branch_id else queryset.none()


def _uploads(request):
    """`{kind: validated file}` for whichever of logo/cover were sent, or an
    error response body as the second value."""
    found, errors = {}, {}
    for kind in media.KINDS:
        upload = request.FILES.get(kind)
        if upload is None:
            continue
        try:
            found[kind] = media.validate_image(upload, kind)
        except ValidationError as error:
            errors[kind] = list(error.messages)
    if not found and not errors:
        errors["detail"] = ["أرسل صورة الشعار أو الغلاف."]
    return found, errors


class PublicMediaListView(APIView):
    permission_classes = [IsClinicAdmin]

    def get(self, request):
        user = request.user
        return Response({
            "group": _group_payload(user.tenant) if is_owner(user) else None,
            "can_approve": is_owner(user),
            "branches": [_branch_payload(b) for b in _branches_for(user).order_by("name")],
        })


class GroupMediaView(APIView):
    permission_classes = [IsGroupOwner]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        found, errors = _uploads(request)
        if errors:
            return Response(errors, status=400)
        tenant = request.user.tenant
        for kind, upload in found.items():
            media.delete_file(getattr(tenant, f"public_{kind}"))
            getattr(tenant, f"public_{kind}").save(upload.name, upload, save=False)
        tenant.save(update_fields=[f"public_{kind}" for kind in found])
        return Response(_group_payload(tenant), status=201)


class GroupMediaKindView(APIView):
    permission_classes = [IsGroupOwner]

    def delete(self, request, kind):
        if kind not in media.KINDS:
            return Response(status=404)
        tenant = request.user.tenant
        media.delete_file(getattr(tenant, f"public_{kind}"))
        setattr(tenant, f"public_{kind}", None)
        tenant.save(update_fields=[f"public_{kind}"])
        return Response(status=204)


class BranchMediaView(APIView):
    permission_classes = [IsClinicAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, uuid):
        branch = get_object_or_404(_branches_for(request.user), uuid=uuid)
        found, errors = _uploads(request)
        if errors:
            return Response(errors, status=400)
        if is_owner(request.user):
            # The Owner is the approver: their upload is the approved image, and
            # replaces (and clears) anything an Admin had waiting for that kind.
            for kind, upload in found.items():
                media.delete_file(getattr(branch, f"public_{kind}"))
                media.delete_file(getattr(branch, f"pending_public_{kind}"))
                setattr(branch, f"pending_public_{kind}", None)
                getattr(branch, f"public_{kind}").save(upload.name, upload, save=False)
            if not any(getattr(branch, f"pending_public_{kind}") for kind in media.KINDS):
                branch.media_status = ""
                branch.media_review_note = ""
        else:
            for kind, upload in found.items():
                media.delete_file(getattr(branch, f"pending_public_{kind}"))
                getattr(branch, f"pending_public_{kind}").save(upload.name, upload, save=False)
            branch.media_status = "pending"
            branch.media_review_note = ""
        branch.save()
        return Response(_branch_payload(branch), status=201)


class BranchMediaKindView(APIView):
    permission_classes = [IsClinicAdmin]

    def delete(self, request, uuid, kind):
        if kind not in media.KINDS:
            return Response(status=404)
        branch = get_object_or_404(_branches_for(request.user), uuid=uuid)
        # Taking an image down only ever shows the public less, so an Admin may
        # do it to their own clinic without the Owner.
        field = f"pending_public_{kind}" if request.query_params.get("pending") == "1" else f"public_{kind}"
        media.delete_file(getattr(branch, field))
        setattr(branch, field, None)
        if not any(getattr(branch, f"pending_public_{k}") for k in media.KINDS) and branch.media_status == "pending":
            branch.media_status = ""
        branch.save()
        return Response(status=204)


class BranchMediaReviewView(APIView):
    permission_classes = [IsGroupOwner]

    def post(self, request, uuid):
        branch = get_object_or_404(Branch.objects.all(), uuid=uuid)
        if branch.media_status != "pending":
            return Response({"detail": "لا توجد صور بانتظار الموافقة لهذه العيادة."}, status=400)
        decision = request.data.get("decision")
        if decision == "approve":
            media.approve_branch(branch, request.user)
        elif decision == "reject":
            media.reject_branch(branch, request.user, request.data.get("note", ""))
        else:
            return Response({"decision": ["approve أو reject."]}, status=400)
        return Response(_branch_payload(branch))
