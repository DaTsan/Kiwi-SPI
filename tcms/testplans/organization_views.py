import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from tcms.testplans.organization import OrganizationConflict, organize


@require_POST
def case_organization(request, pk):
    if not request.user.is_authenticated:
        return JsonResponse({"error": _("Permission denied")}, status=403)
    try:
        if len(request.body) > 1024 * 1024:
            raise ValidationError(_("Invalid organization request."))
        data = json.loads(request.body)
        return JsonResponse(organize(request.user, pk, data))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": _("Invalid organization request.")}, status=400)
    except OrganizationConflict as error:
        return JsonResponse({"error": " ".join(error.messages)}, status=409)
    except ValidationError as error:
        return JsonResponse({"error": " ".join(error.messages)}, status=400)
    except PermissionDenied:
        return JsonResponse({"error": _("Permission denied")}, status=403)
    except Http404:
        return JsonResponse(
            {"error": _("The section no longer exists. Refresh the page.")}, status=404
        )
