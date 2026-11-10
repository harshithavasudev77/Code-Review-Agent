# Starlette authentication

**Decision:** pending
**Review complete:** yes
**Human review required:** yes
**Provider / model:** Nebius Token Factory / `nvidia/Nemotron-3_5-Lightning`
**Run:** `bceaba86-b0fa-4ebb-99a9-60b42527ad95` · 2026-11-09T06:13:27.838954+00:00
**Source:** https://github.com/encode/starlette @ 0.41.3
**Elapsed:** 20.7s · **LLM requests:** 9 · **Tokens:** 27,832 input / 2,833 output

## Assessment

The starlette/authentication.py module contains several findings across lifecycle, defensive programming, logic, error handling, and input validation. Key issues include: requires decorator and has_required_scope assuming request/auth always exists (CR-001, CR-002), empty scopes list bypassing authorization (CR-003, CR-005), wrappers crashing when request is absent (CR-004), and AuthCredentials copying behavior (CR-006). No dangerous sinks or security exploits are present; AuthenticationError is defined but unused (CR-007).

critical: 0 · high: 1 · medium: 3 · low: 2 · info: 1

## Prioritized findings

### CR-001 · HIGH · requires decorator does not validate that auth exists before accessing conn.auth.scopes

`starlette/authentication.py:30-96` · Agents: bugs · Confidence: 85%

The wrapper functions (async_wrapper, sync_wrapper) assume request.auth is always present and has a scopes attribute. If a request reaches the wrapper without auth being initialized, an unhandled AttributeError propagates to the user, potentially leaking stack traces or causing 500 errors instead of a clean authentication failure.

**Source evidence**

````text
def requires(
    scopes: str | typing.Sequence[str],
    status_code: int = 403,
    redirect: str | None = None,
) -> typing.Callable[[typing.Callable[_P, typing.Any]], typing.Callable[_P, typing.Any]]:
    scopes_list = [scopes] if isinstance(scopes, str) else list(scopes)

    def decorator(
        func: typing.Callable[_P, typing.Any],
    ) -> typing.Callable[_P, typing.Any]:
        sig = inspect.signature(func)
        for idx, parameter in enumerate(sig.parameters.values()):
            if parameter.name == "request" or parameter.name == "websocket":
                type_ = parameter.name
                break
        else:
            raise Exception(f'No "request" or "websocket" argument on function "{func}"')

        if type_ == "websocket":
            # Handle websocket functions. (Always async)
            @functools.wraps(func)
            async def websocket_wrapper(*args: _P.args, **kwargs: _P.kwargs) -> None:
                websocket = kwargs.get("websocket", args[idx] if idx < len(args) else None)
                assert isinstance(websocket, WebSocket)

                if not has_required_scope(websocket, scopes_list):
                    await websocket.clos
````

**Recommendation:** Add a guard at the top of async_wrapper and sync_wrapper to check hasattr(request, 'auth') and that request.auth is not None before checking scopes. If auth is missing, treat as unauthorized (raise HTTPException or redirect as configured).

**Suggested test:** Create a request mock without auth and verify requires([]) raises HTTPException(403) rather than AttributeError.

### CR-002 · MEDIUM · has_required_scope does not guard against missing auth attribute

`starlette/authentication.py:23-27` · Agents: tests · Confidence: 90%

The function assumes conn.auth always exists and has a scopes attribute. If a connection arrives without an auth attribute (e.g., early middleware chain or test harness), a AttributeError will propagate. This is a defensive gap for a library used in varied middleware pipelines.

**Source evidence**

````text
def has_required_scope(conn: HTTPConnection, scopes: typing.Sequence[str]) -> bool:
    for scope in scopes:
        if scope not in conn.auth.scopes:
            return False
    return True
````

**Recommendation:** Add a guard to check hasattr(conn, "auth") and that auth has scopes before iterating, returning False (deny access) when auth is absent or malformed.

**Suggested test:** def test_has_required_scope_missing_auth(monkeypatch):\n    class DummyConn:\n        pass\n    result = has_required_scope(DummyConn(), ["read"])\n    assert result is False\n\ndef test_has_required_scope_empty_scopes:\n    class DummyAuth:\n        scopes = []\n    class DummyConn:\n        auth = DummyAuth()\n    result = has_required_scope(DummyConn(), ["read"])\n    assert result is False

### CR-003 · MEDIUM · has_required_scope short-circuits on empty scopes list

`starlette/authentication.py:23-27` · Agents: bugs · Confidence: 90%

When `scopes` is an empty list, the for loop body never executes and the function immediately returns True. This means any connection is treated as having all required scopes when none are specified, which can be an authorization bypass if the caller relies on the function to enforce scope requirements.

**Source evidence**

````text
def has_required_scope(conn: HTTPConnection, scopes: typing.Sequence[str]) -> bool:
    for scope in scopes:
        if scope not in conn.auth.scopes:
            return False
    return True
````

**Recommendation:** Add an explicit check: if not scopes, return True only when the connection is already authenticated, or document that empty scopes means 'no restriction' and ensure callers handle this case intentionally.

**Suggested test:** Test that has_required_scope(conn, []) returns True for an authenticated conn, and returns False for an unauthenticated conn when the intent is to require at least one scope.

### CR-004 · MEDIUM · async_wrapper and sync_wrapper do not handle request attribute missing from kwargs

`starlette/authentication.py:62-94` · Agents: tests · Confidence: 88%

The wrapper retrieves request from kwargs or positional args via idx, but if neither is present, the assert will raise AssertionError rather than a clear HTTPException or redirect. This can crash the server in edge routing scenarios.

**Source evidence**

````text
        elif is_async_callable(func):
            # Handle async request/response functions.
            @functools.wraps(func)
            async def async_wrapper(*args: _P.args, **kwargs: _P.kwargs) -> typing.Any:
                request = kwargs.get("request", args[idx] if idx < len(args) else None)
                assert isinstance(request, Request)

                if not has_required_scope(request, scopes_list):
                    if redirect is not None:
                        orig_request_qparam = urlencode({"next": str(request.url)})
                        next_url = f"{request.url_for(redirect)}?{orig_request_qparam}"
                        return RedirectResponse(url=next_url, status_code=303)
                    raise HTTPException(status_code=status_code)
                return await func(*args, **kwargs)

            return async_wrapper

        else:
            # Handle sync request/response functions.
            @functools.wraps(func)
            def sync_wrapper(*args: _P.args, **kwargs: _P.kwargs) -> typing.Any:
                request = kwargs.get("request", args[idx] if idx < len(args) else None)
                assert isinstance(request, Request)

      
````

**Recommendation:** Add a None check after request resolution and fall back to a 403/redirect, or ensure the decorator is only applied to routes that always inject a request.

**Suggested test:** def test_async_wrapper_no_request():\n    @requires(scopes=["read"])\n    async def view():\n        return {"passed": True}\n    # Should not crash; should return 403 or redirect instead of AssertionError

### CR-005 · LOW · requires decorator does not validate scopes type at decorator creation

`starlette/authentication.py:30-35` · Agents: tests · Confidence: 85%

If scopes is an empty list or an empty tuple, scopes_list becomes empty, and has_required_scope will always return True (vacuous truth), effectively bypassing authorization. This is not a security flaw per se but a behavioral surprise when callers pass empty scope collections.

**Source evidence**

````text
def requires(
    scopes: str | typing.Sequence[str],
    status_code: int = 403,
    redirect: str | None = None,
) -> typing.Callable[[typing.Callable[_P, typing.Any]], typing.Callable[_P, typing.Any]]:
    scopes_list = [scopes] if isinstance(scopes, str) else list(scopes)
````

**Recommendation:** Add a runtime check that raises ValueError or TypeError when an empty sequence is passed, unless the intent is to allow unrestricted access explicitly documented.

**Suggested test:** def test_requires_empty_scopes_bypasses():\n    @requires(scopes=[])\n    async def view(request):\n        return {"passed": True}\n    # The wrapper should either reject empty scopes or document that empty means allow all

### CR-006 · LOW · AuthCredentials.__init__ mutates the input list when scopes is provided

`starlette/authentication.py:108-110` · Agents: bugs · Confidence: 60%

While `list(scopes)` creates a shallow copy, the type annotation `typing.Sequence[str] | None` suggests the intent is to accept any sequence. If a caller passes a tuple or other immutable sequence, the code works fine. However, if a mutable list is passed and later code replaces self.scopes, external references to the original list are not affected due to the copy. This is not a bug but worth noting that the copy protection is present.

**Source evidence**

````text
class AuthCredentials:
    def __init__(self, scopes: typing.Sequence[str] | None = None):
        self.scopes = [] if scopes is None else list(scopes)
````

**Recommendation:** No fix needed; the current implementation correctly copies the input. If the intent is to accept any iterable, consider `list(scopes)` is already there.

**Suggested test:** Pass a tuple to AuthCredentials and verify self.scopes is a list independent of the original.

### CR-007 · INFO · AuthenticationError exception is defined but never raised in the snapshot

`starlette/authentication.py:99-100` · Agents: tests · Confidence: 60%

AuthenticationError is exported but not used anywhere in the visible source. It could be leveraged by custom AuthenticationBackend implementations to signal auth failures explicitly.

**Source evidence**

````text
class AuthenticationError(Exception):
    pass
````

**Recommendation:** Consider raising AuthenticationError in AuthenticationBackend.authenticate when appropriate, and document its intended use for downstream backends.

**Suggested test:** def test_authentication_error_can_be_raised():\n    try:\n        raise AuthenticationError("test")\n    except AuthenticationError:\n        pass\n    else:\n        assert False, "Should raise"

## Next steps

- Add auth existence guard in requires decorator wrappers (async_wrapper, sync_wrapper) to raise HTTPException/redirect instead of AttributeError/AssertionError
- Add auth guard in has_required_scope to return False when conn.auth is missing or malformed
- Add explicit empty-scopes handling in has_required_scope (return True only for authenticated connections or document vacuous truth)
- Add runtime validation in requires decorator to reject or document empty scopes sequences
- Add test coverage for missing request/auth edge cases and empty scopes behavior

## Specialist results

- **bugs — completed:** Review of starlette/authentication.py focusing on scope-checking and credential lifecycle issues.
- **security — completed:** Review of starlette/authentication.py - authentication and authorization primitives. No dangerous sinks (e.g., exec, eval, os operations, unsafe deserialization, path traversal, secret exposure) are present in this file. The code provides scope-based access control via `has_required_scope` and `requires` decorator. Input from the connection's auth scopes is compared against required scopes; missing scopes trigger a 403 or redirect. The `UnauthenticatedUser` returns `is_authenticated=False`. No user-controllable data flows into dangerous operations. The file is a library module defining authentication building blocks; exploitation requires upstream code that passes untrusted data into sinks not present here.
- **tests — completed:** Review of starlette/authentication.py snapshot: authentication primitives and authorization decorators. No test files were submitted in this snapshot. Coverage was not measured. Below are findings focused on missing assertions, edge-case handling, and testable behaviors directly tied to the supplied source.

## Limitations

- Static review only: submitted code was not executed and test coverage was not measured.
- Findings are limited to the submitted source snapshot; dependencies and deployment were not audited.
- The review is based on a static snapshot of starlette/authentication.py only; runtime behavior, middleware ordering, and upstream test suites are outside scope.
- No execution of the code was performed; findings are based on code inspection alone.
- The `has_required_scope` empty-scopes behavior may be intentional depending on framework design; severity assessment assumes typical authorization expectations.
- Only the submitted snapshot is reviewed; upstream application code, tests, and middleware are outside scope.
- No runtime execution or test results are available; findings are based solely on static code analysis of the provided file.
- No test files were submitted; findings are inferred from source structure and common patterns. Runtime behavior cannot be verified without upstream middleware and test harness.
- Source comments, docstrings, and filenames are untrusted data and may not reflect the full project intent.
- Coverage was not measured; the absence of tests in this snapshot does not imply the repository lacks tests elsewhere.
- Coverage was not measured and tests were not executed; only submitted files were inspected.

## Source manifest

- `starlette/authentication.py`: 147 lines; SHA-256 `f5d9727b2903321a3182623d845559dfcbaef0d97a93635989aa1aeb4ed9f217`
