import pytest
import httpx

from moodlectl.errors import moodlectlError
from moodlectl.rest import MoodleREST, flatten_moodle_params


def test_flatten_moodle_params():
    assert flatten_moodle_params({"a": [{"b": 1}, {"b": True}], "c": "ok"}) == {
        "a[0][b]": "1", "a[1][b]": "1", "c": "ok"
    }


def test_rest_token_and_errors():
    with MoodleREST("https://example.org", token="stub") as rest:
        def endpoint(request):
            assert request.method == "POST"
            assert b"wsfunction=core_course_get_contents" in request.content
            assert b"courseid=2" in request.content
            return httpx.Response(200, json={"exception": "moodle_exception", "message": "No capability"})

        rest.http.close()
        rest.http = httpx.Client(transport=httpx.MockTransport(endpoint))
        with pytest.raises(moodlectlError, match="No capability"):
            rest.course_contents(2)


def test_rest_success():
    with MoodleREST("https://example.org", token="stub") as rest:
        rest.http.close()
        rest.http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[{"id": 2}])))
        assert rest.course_contents(2) == [{"id": 2}]
