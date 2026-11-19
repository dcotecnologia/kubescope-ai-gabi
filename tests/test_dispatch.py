import pytest

from kubescope.gabi import actions, dispatch


def _request(action: str, **args) -> actions.Request:
    return actions.Request(actions.BY_NAME[action], args)


@pytest.mark.parametrize(
    ("request_", "method", "arguments"),
    [
        (
            _request("scale", namespace="ns", name="web", replicas=2),
            "scale_deployment",
            ("ctx", "ns", "web", 2),
        ),
        (
            _request("restart", namespace="ns", name="web"),
            "restart_deployment",
            ("ctx", "ns", "web"),
        ),
        (
            _request("evict_pod", namespace="ns", name="p"),
            "evict_pod",
            ("ctx", "ns", "p"),
        ),
        (
            _request("delete", kind="Pod", namespace="ns", name="p"),
            "delete_pod",
            ("ctx", "ns", "p"),
        ),
        (
            _request("delete", kind="Service", namespace="ns", name="s"),
            "delete_resource",
            ("ctx", "Service", "ns", "s"),
        ),
        (
            _request(
                "replace", kind="Pod", namespace="ns", name="p", document={"a": 1}
            ),
            "replace_resource",
            ("ctx", "Pod", "ns", "p", {"a": 1}),
        ),
    ],
)
def test_each_change_runs_the_change_of_the_context_with_its_arguments(
    request_, method, arguments, app
) -> None:
    function, given = dispatch.write_call(request_, "ctx")

    assert function.__name__ == method and given == arguments


def test_a_change_is_made_only_with_the_write_mode_on(app, monkeypatch) -> None:
    from kubescope.sdk import WriteModeOff

    from kubescope import writes

    made: list = []
    monkeypatch.setattr(writes, "evict_pod", lambda *a: made.append(a))
    function, arguments = dispatch.write_call(
        _request("evict_pod", namespace="ns", name="p"), "ctx"
    )

    app.write_mode = False
    with pytest.raises(WriteModeOff):
        function(*arguments)
    assert made == []
    app.write_mode = True
    function(*arguments)
    assert made == [("ctx", "ns", "p")]


def test_what_does_not_change_the_cluster_is_refused(app) -> None:
    with pytest.raises(ValueError, match="does not change"):
        dispatch.write_call(_request("refresh"), "ctx")
