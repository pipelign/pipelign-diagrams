import unittest

from app.models import (
    InternalErrorResponse,
    RenderRequest,
    ValidationIssue,
    ValidationResult,
)


class TestRenderRequest(unittest.TestCase):
    def test_minimal_request(self) -> None:
        req = RenderRequest(source="@startuml\n@enduml")
        self.assertEqual(req.source, "@startuml\n@enduml")
        self.assertIsNone(req.options)

    def test_request_with_options(self) -> None:
        req = RenderRequest(
            source="@startuml\n@enduml",
            options={"theme": "sketch"},
        )
        self.assertEqual(req.options, {"theme": "sketch"})


class TestValidationModels(unittest.TestCase):
    def test_validation_issue_fields(self) -> None:
        issue = ValidationIssue(message="Syntax Error?", line=5)
        self.assertEqual(issue.message, "Syntax Error?")
        self.assertEqual(issue.line, 5)

    def test_validation_result_ok(self) -> None:
        result = ValidationResult(ok=True, errors=[], warnings=[])
        self.assertTrue(result.ok)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.warnings, [])

    def test_validation_result_with_errors(self) -> None:
        issue = ValidationIssue(message="Syntax Error?", line=5)
        result = ValidationResult(ok=False, errors=[issue], warnings=[])
        self.assertFalse(result.ok)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].message, "Syntax Error?")


class TestInternalErrorResponse(unittest.TestCase):
    def test_defaults_and_overrides(self) -> None:
        err = InternalErrorResponse(message="Something went wrong")
        self.assertFalse(err.ok)
        self.assertEqual(err.errorType, "internal_error")
        self.assertEqual(err.message, "Something went wrong")
        self.assertIsNone(err.details)

        err_with_details = InternalErrorResponse(
            message="Failed",
            details={"reason": "timeout"},
        )
        self.assertEqual(err_with_details.details, {"reason": "timeout"})


if __name__ == "__main__":
    unittest.main()

