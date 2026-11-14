
from rest_framework.response import Response


def success_response(
    message="Success",
    data=None,
    status_code=200,
    **extra,
):
    response_data = {
        "success": True,
        "message": message,
    }

    # Pagination metadata appears before data
    response_data.update(extra)

    response_data["data"] = data

    return Response(response_data, status=status_code)


def error_response(message="Something went wrong", errors=None, status_code=400):
    return Response({
        "success": False,
        "message": message,
        "data": None,
        "errors": errors,
    }, status=status_code)