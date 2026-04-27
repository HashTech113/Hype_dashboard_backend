from __future__ import annotations


class AppError(Exception):
    status_code: int = 500
    code: str = "app_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class AlreadyExistsError(AppError):
    status_code = 409
    code = "already_exists"


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class InvalidStateError(AppError):
    status_code = 409
    code = "invalid_state"


class AuthenticationError(AppError):
    status_code = 401
    code = "authentication_error"


class AuthorizationError(AppError):
    status_code = 403
    code = "authorization_error"


class FaceRecognitionError(AppError):
    status_code = 400
    code = "face_recognition_error"


class NoFaceDetectedError(FaceRecognitionError):
    code = "no_face_detected"


class MultipleFacesError(FaceRecognitionError):
    code = "multiple_faces"


class LowQualityFaceError(FaceRecognitionError):
    code = "low_quality_face"


class FrameUnavailableError(AppError):
    status_code = 503
    code = "frame_unavailable"
