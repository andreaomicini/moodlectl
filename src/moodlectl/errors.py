class moodlectlError(Exception):
    """Expected error with a user-actionable message."""


class LoginRequired(moodlectlError):
    """The saved browser profile is not authenticated."""


class AmbiguousMatch(moodlectlError):
    """A name matched multiple Moodle entities."""


class MoodleFormError(moodlectlError):
    """A Moodle form changed or rejected a request."""
